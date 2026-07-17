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

from src.llm_fallback import resolve_fallback, chat_json

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
        or "prepayment credits" in m
        or "resource_exhausted" in m
        or "quota" in m
    )


def parse_tm_text(raw: str, url: str = "") -> Dict[str, Any]:
    """
    Regex extract from Transfermarkt page text (Tavily raw) — zero LLM.
    TM.it format tipico:
      * Nato il:  03/05/2006 (20)
      * Posizione:  Centrocampista
      [Atalanta U23](/atalanta-u23/...)
      2,80 mln €
    """
    if not raw:
        return {}
    text = raw
    out: Dict[str, Any] = {}
    if url and "/profil/spieler/" in url:
        out["tm_url"] = url

    # Birth: "Nato il: 03/05/2006 (20)" / "Date of birth/Age: May 3, 2006 (20)"
    m = re.search(
        r"(?:Nato il|Data di nascita|Date of birth(?:/Age)?|Born(?: on)?)\s*:?\s*"
        r"(\d{1,2})[./](\d{1,2})[./](\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1980 <= y <= 2012:
            out["birth_date"] = f"{y:04d}-{mo:02d}-{d:02d}"
    if not out.get("birth_date"):
        m = re.search(
            r"(?:Nato il|Date of birth(?:/Age)?|Born(?: on)?)\s*:?\s*"
            r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})",
            text,
            re.IGNORECASE,
        )
        if m:
            months = {
                "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
                "gen": 1, "mag": 5, "giu": 6, "lug": 7, "ago": 8, "set": 9,
                "ott": 10, "dic": 12,
            }
            mon = months.get(m.group(1)[:3].lower())
            y = int(m.group(3))
            if mon and 1980 <= y <= 2012:
                out["birth_date"] = f"{y:04d}-{mon:02d}-{int(m.group(2)):02d}"

    # Age in parens after birth year: "(20)"
    m = re.search(r"\b(19\d{2}|20[01]\d)\s*\((\d{1,2})\)", text)
    if m and not out.get("birth_date"):
        y = int(m.group(1))
        if 1980 <= y <= 2012:
            out["birth_date"] = f"{y}-01-01"

    _JUNK_CLUB = {
        "giocatori", "nuovo arrivo", "nuovi arrivi", "rientro", "senza club",
        "svincolato", "transfermarkt", "squadra", "club", "unknown", "nato il",
        "data di nascita", "posizione", "piede", "altezza",
    }

    def _ok_club(c: str) -> bool:
        cl = (c or "").strip().lower()
        return bool(cl) and cl not in _JUNK_CLUB and "transfermarkt" not in cl and len(cl) > 2

    # Club: markdown link near top "[Atalanta U23](/atalanta-u23/startseite/verein/..."
    for m in re.finditer(
        r"\[([^\]]{2,50})\]\(/[^\s\)]*startseite/verein[^\)]*\)",
        text,
    ):
        club = m.group(1).strip()
        if _ok_club(club):
            out["current_club"] = club[:80]
            break
    if not out.get("current_club"):
        m = re.search(
            r"(?:Club attuale|Current club)\s*:?\s*([^\n\r|*]+)",
            text,
            re.IGNORECASE,
        )
        if m:
            club = re.sub(r"\s{2,}", " ", m.group(1).strip())[:80]
            if _ok_club(club):
                out["current_club"] = club

    # Market value: "2,80 mln €" or "150 mila €"
    m = re.search(
        r"([\d]+(?:[.,]\d+)?)\s*(mln|milioni|mila)\s*€",
        text,
        re.IGNORECASE,
    )
    if m:
        try:
            num_s = m.group(1).replace(".", "").replace(",", ".")
            num = float(num_s)
            unit = m.group(2).lower()
            val = int(num * (1_000_000 if unit.startswith("ml") else 1_000))
            if 1000 <= val <= 50_000_000:
                out["market_value_eur"] = val
                out["market_value"] = val
                out["market_value_text"] = m.group(0).strip()[:40]
        except ValueError:
            pass

    # Foot
    m = re.search(
        r"(?:Piede|Foot)\s*:?\s*(destro|sinistro|ambidestro|right|left|both)",
        text,
        re.I,
    )
    if m:
        foot = m.group(1).lower()
        out["foot"] = {
            "right": "destro", "left": "sinistro", "both": "ambidestro",
        }.get(foot, foot)

    # Position: "* Posizione:  Centrocampista"
    m = re.search(
        r"(?:Posizione|Main position|Ruolo)\s*:?\s*([A-Za-zàèéìòùÀÈÉÌÒÙ /\-]{3,40})",
        text,
        re.IGNORECASE,
    )
    if m:
        out["main_position"] = m.group(1).strip()[:40]

    # Height: "1,95 m"
    m = re.search(r"(?:Altezza|Height)\s*:?\s*(\d)[.,](\d{2})\s*m", text, re.I)
    if m:
        try:
            out["height_cm"] = int(m.group(1)) * 100 + int(m.group(2))
        except ValueError:
            pass

    return out

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
        self.gemini_disabled = False  # daily quota / credits circuit breaker
        self.fallback_cfg = resolve_fallback()
        if self.fallback_cfg:
            print(f"  [LLM] fallback pronto: {self.fallback_cfg['label']} (solo single-player)")

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
            if _is_daily_quota_error(str(e)):
                self.gemini_disabled = True
            print(f"  [GROUNDED ERROR] {player_name}: {e}")
            return {}

    def _parse_prompt_for_player(self, player_name: str, url: str, raw_content: str) -> str:
        return (
            f"Estrai dati strutturati da questa pagina Transfermarkt per {player_name}.\n"
            f"URL: {url}\n\n"
            "Rispondi SOLO con JSON con campi: nationality, birth_date (YYYY-MM-DD), "
            "current_club, contract_expires, market_value_eur, market_value_text, "
            "appearances, goals, assists, minutes_played, foot, agent, tm_url, main_position.\n"
            "Null se assente. Non inventare.\n\n"
            f"CONTENUTO:\n{raw_content[:12000]}"
        )

    def enrich_player_tavily(self, player_name: str) -> Dict[str, Any]:
        """Single-player: Tavily page + regex (opz. Groq se thin). Non usato in batch CI."""
        if not self.tavily_key:
            return {}
        try:
            res = self.session.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.tavily_key,
                    "query": f"site:transfermarkt.it {player_name} profilo giocatore",
                    "search_depth": "basic",
                    "max_results": 3,
                    "include_domains": ["transfermarkt.it"],
                    "include_raw_content": True,
                },
                timeout=30,
            )
            if res.status_code == 432:
                print(f"  [TAVILY] 432 rate limit — skip {player_name}")
                return {}
            res.raise_for_status()
            results = res.json().get("results") or []
            url, raw = "", ""
            for r in results:
                u = r.get("url") or ""
                if "/profil/spieler/" in u.lower():
                    url, raw = u, (r.get("raw_content") or r.get("content") or "")
                    break
            if not url and results:
                url = results[0].get("url") or ""
                raw = results[0].get("raw_content") or results[0].get("content") or ""
            if not raw:
                return {}
            data = parse_tm_text(raw, url)
            if data.get("birth_date") or data.get("current_club"):
                print(
                    f"  [REGEX] {player_name}: {data.get('birth_date')} / {data.get('current_club')}"
                )
            # Groq only if regex thin and configured
            thin = not (data.get("birth_date") and data.get("current_club"))
            if thin and self.fallback_cfg:
                try:
                    text = chat_json(self._parse_prompt_for_player(player_name, url, raw))
                    llm = self._parse_json_response(text)
                    for k, v in (llm or {}).items():
                        if v is not None and not data.get(k):
                            data[k] = v
                except Exception as e:
                    print(f"  [FALLBACK ERROR] {player_name}: {e}")
            if url and data and not data.get("tm_url"):
                data["tm_url"] = url
            return data or {}
        except Exception as e:
            print(f"  [TAVILY ERROR] {player_name}: {e}")
            return {}

    def enrich_player(self, player_name: str) -> Dict[str, Any]:
        """Single: Gemini grounding, else Tavily+regex."""
        if not self.gemini_disabled:
            data = self.enrich_player_grounded(player_name)
            if data:
                return data
        return self.enrich_player_tavily(player_name)

    def enrich_players_batch(self, names: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Path CI: SOLO Gemini grounded batch (1 call / BATCH_SIZE).
        Se Gemini morto → stop pulito, backlog alla prossima run.
        Niente cascata Tavily/Serper/Jina: brucia tempo e quote senza gain.
        """
        if not names:
            return {}
        if self.gemini_disabled:
            print("  [BATCH SKIP] Gemini off — rinvio enrich (no thrash fallback)")
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
                    print("  [BATCH QUOTA] Gemini dead — stop enrich this run")
                    return {}
                msg_l = msg.lower()
                transient = any(
                    k in msg_l
                    for k in ("429", "503", "resource_exhausted", "unavailable", "overloaded")
                )
                if transient and attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_BASE * (2 ** attempt)
                    print(f"  [BATCH RETRY] attempt {attempt + 1}, backoff {wait}s")
                    time.sleep(wait)
                    continue
                print(f"  [BATCH ERROR] {e}")
                return {}

        raw = self._parse_json_response(response.text or "") if response else {}
        if not isinstance(raw, dict):
            return {}

        def _norm(s: str) -> str:
            return re.sub(r"\s+", " ", s).strip().lower()

        by_norm = {_norm(k): v for k, v in raw.items() if isinstance(v, dict)}
        out = {name: by_norm.get(_norm(name), {}) for name in names}
        found = sum(1 for v in out.values() if v)
        print(f"  [BATCH] {found}/{len(names)} profili in 1 chiamata")
        return out


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "Sergej Levak"
    enricher = TransfermarktEnricher()
    print(f"Enriching: {name}")
    result = enricher.enrich_player(name)
    print(json.dumps(result, indent=2, ensure_ascii=False))
