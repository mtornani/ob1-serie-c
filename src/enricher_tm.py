#!/usr/bin/env python3
"""
OB1 Serie C - Transfermarkt Enricher v2
Uses Gemini Search Grounding for TM data extraction — bypasses Cloudflare/JS rendering.
Fallback: Tavily advanced search.
"""

import os
import re
import json
import time
from typing import Dict, Any, List, Optional
import requests
from dotenv import load_dotenv
from google import genai

load_dotenv()

# Batch size for grounded enrichment. One Gemini call covers this many
# players — the main cost lever (N players -> N/BATCH calls instead of N).
# Kept small so grounding still searches each player properly.
BATCH_SIZE = 5
_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds


def _is_daily_quota_error(msg: str) -> bool:
    m = (msg or "").lower()
    return (
        "free_tier" in m
        or "perday" in m
        or "per_day" in m
        or "generaterequestsperday" in m
    )

_GROUNDING_PROMPT = """Cerca su Transfermarkt il profilo del calciatore "{name}".
Estrai i dati reali dalla pagina profilo Transfermarkt (transfermarkt.it o transfermarkt.com).

Rispondi ESCLUSIVAMENTE con JSON valido, nessun testo aggiuntivo:
{{
  "full_name": "Nome completo" o null,
  "birth_date": "YYYY-MM-DD" o null,
  "nationality": "Nazionalità principale (es. Italia)" o null,
  "second_nationality": "Seconda nazionalità" o null,
  "height_cm": numero intero o null,
  "foot": "destro" | "sinistro" | "ambidestro" | null,
  "current_club": "Nome Club" o "Svincolato" o null,
  "contract_expires": "YYYY-MM-DD" o null,
  "market_value_eur": numero intero (es. 150000) o null,
  "market_value_text": "es. 150 mila €" o null,
  "main_position": "Ruolo principale" o null,
  "agent": "Nome agenzia" o null,
  "tm_url": "URL profilo Transfermarkt" o null,
  "appearances": numero presenze nell'ultima stagione disponibile (2025/26 o 2024/25) o null,
  "goals": numero gol nell'ultima stagione disponibile o null,
  "assists": numero assist nell'ultima stagione disponibile o null,
  "minutes_played": numero minuti nell'ultima stagione disponibile o null,
  "season": "stagione di riferimento per le stats, es. 2025/26" o null
}}

Se il calciatore non è trovato su Transfermarkt, rispondi esattamente: {{}}"""

_BATCH_PROMPT = """Cerca su Transfermarkt (transfermarkt.it o transfermarkt.com) il profilo di OGNUNO di questi calciatori:
{names}

Rispondi ESCLUSIVAMENTE con un oggetto JSON valido, nessun testo aggiuntivo.
Le chiavi devono essere ESATTAMENTE i nomi come scritti sopra. Per ogni calciatore il valore è:
{{
  "birth_date": "YYYY-MM-DD" o null,
  "nationality": "Nazionalità principale" o null,
  "second_nationality": "Seconda nazionalità" o null,
  "height_cm": numero intero o null,
  "foot": "destro" | "sinistro" | "ambidestro" | null,
  "current_club": "Nome Club" o "Svincolato" o null,
  "contract_expires": "YYYY-MM-DD" o null,
  "market_value_eur": numero intero o null,
  "market_value_text": "es. 150 mila €" o null,
  "main_position": "Ruolo principale" o null,
  "agent": "Nome agenzia" o null,
  "tm_url": "URL profilo Transfermarkt" o null,
  "appearances": presenze ultima stagione disponibile o null,
  "goals": gol ultima stagione o null,
  "assists": assist ultima stagione o null,
  "minutes_played": minuti ultima stagione o null,
  "season": "es. 2025/26" o null
}}

Se un calciatore non è trovato su Transfermarkt, usa {{}} come suo valore. Non inventare dati."""


class TransfermarktEnricher:
    """
    Arricchisce profili giocatori con dati TM via Gemini Search Grounding.
    Fallback Tavily per casi dove grounding non trova risultati.
    """

    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")

        if not self.gemini_key:
            raise ValueError("GEMINI_API_KEY mancante")

        self.session = requests.Session()
        self.gemini_client = genai.Client(api_key=self.gemini_key)
        self.gemini_disabled = False  # daily quota circuit breaker

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Extract and parse JSON from Gemini response text."""
        if not text:
            return {}
        text = text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            return {}

    def enrich_player_grounded(self, player_name: str) -> Dict[str, Any]:
        """Primary enrichment: Gemini Search Grounding on Transfermarkt."""
        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=_GROUNDING_PROMPT.format(name=player_name),
                config=genai.types.GenerateContentConfig(
                    tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())],
                    temperature=0.0,
                ),
            )
            data = self._parse_json_response(response.text or "")
            if data:
                print(f"  [GROUNDED] {player_name}: mv={data.get('market_value_eur')} apps={data.get('appearances')}")
            return data
        except Exception as e:
            print(f"  [GROUNDED ERROR] {player_name}: {e}")
            return {}

    def enrich_player_tavily(self, player_name: str) -> Dict[str, Any]:
        """Fallback: Tavily search + Gemini parse (original approach)."""
        if not self.tavily_key:
            return {}

        query = f"site:transfermarkt.it {player_name} profilo giocatore"
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 1,
            "include_domains": ["transfermarkt.it"],
            "include_raw_content": True,
        }

        try:
            res = self.session.post("https://api.tavily.com/search", json=payload, timeout=30)
            res.raise_for_status()
            results = res.json().get("results", [])
            if not results:
                return {}

            result = results[0]
            raw_content = result.get("raw_content", "")
            url = result.get("url", "")
            if not raw_content:
                return {}

            prompt = (
                f"Estrai dati strutturati da questa pagina Transfermarkt per {player_name}.\n"
                f"URL: {url}\n\n"
                "Rispondi SOLO con JSON (stessi campi del profilo TM standard — "
                "nationality, birth_date, current_club, contract_expires, market_value_eur, "
                "market_value_text, appearances, goals, assists, minutes_played, foot, agent, tm_url).\n\n"
                f"CONTENUTO:\n{raw_content[:15000]}"
            )
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            data = self._parse_json_response(response.text or "")
            if url and not data.get("tm_url"):
                data["tm_url"] = url
            return data
        except Exception as e:
            print(f"  [TAVILY ERROR] {player_name}: {e}")
            return {}

    def enrich_player(self, player_name: str) -> Dict[str, Any]:
        """Main entry: grounding first, Tavily fallback."""
        data = self.enrich_player_grounded(player_name)
        if data:
            return data
        print(f"  [FALLBACK] Trying Tavily for {player_name}...")
        return self.enrich_player_tavily(player_name)

    def enrich_players_batch(self, names: List[str]) -> Dict[str, Dict[str, Any]]:
        """Enrich up to BATCH_SIZE players with ONE grounded call.

        Returns {input_name: tm_data} — players the model couldn't find map
        to {} and stay eligible for the next run. Retries transient 429/503
        with backoff before giving up on the whole batch.
        Daily free-tier exhaustion → circuit open, no more retries this process.
        """
        if not names:
            return {}
        if self.gemini_disabled:
            print("  [BATCH SKIP] Gemini daily quota already exhausted")
            return {}
        prompt = _BATCH_PROMPT.format(names="\n".join(f"- {n}" for n in names))

        response = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())],
                        temperature=0.0,
                    ),
                )
                break
            except Exception as e:
                msg = str(e)
                if _is_daily_quota_error(msg):
                    self.gemini_disabled = True
                    print(f"  [BATCH QUOTA] daily free tier dead — stop enrichment this run")
                    return {}
                msg_l = msg.lower()
                transient = any(k in msg_l for k in (
                    '429', '503', 'resource_exhausted', 'unavailable', 'overloaded'))
                if transient and attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_BASE * (2 ** attempt)
                    print(f"  [BATCH RETRY] attempt {attempt + 1} failed, backoff {wait}s")
                    time.sleep(wait)
                    continue
                print(f"  [BATCH ERROR] {e}")
                return {}

        raw = self._parse_json_response(response.text or "") if response else {}
        if not isinstance(raw, dict):
            return {}

        # Match model keys back to input names (tolerant to case/spacing drift).
        def _norm(s: str) -> str:
            return re.sub(r'\s+', ' ', s).strip().lower()
        by_norm = {_norm(k): v for k, v in raw.items() if isinstance(v, dict)}
        out = {}
        for name in names:
            out[name] = by_norm.get(_norm(name), {})
        found = sum(1 for v in out.values() if v)
        print(f"  [BATCH] {found}/{len(names)} profili trovati in 1 chiamata")
        return out


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "Sergej Levak"
    enricher = TransfermarktEnricher()
    print(f"Enriching: {name}")
    result = enricher.enrich_player(name)
    print(json.dumps(result, indent=2, ensure_ascii=False))
