#!/usr/bin/env python3
"""
OB1 Serie C - Transfermarkt Enricher v3

Free-first: l'arricchimento funziona con la sola GROQ_API_KEY (o qualunque
altra rotta free del gateway). Nessuna chiave è obbligatoria di per sé —
l'unico requisito è che esista *una* via per fare inferenza (has_any_llm()).

Percorsi, in ordine:
  1. free: ricerca senza chiave (DDG/SearXNG) -> fetch pagina -> regex -> LLM sul residuo
  2. gemini grounded: solo se GEMINI_API_KEY c'è e OB1_LLM_MODE lo consente
"""

import os
import re
import json
import html
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv è opzionale: senza, si usano le env vars reali
    def load_dotenv(*_a, **_kw):
        return False

try:
    from google import genai
except ImportError:  # google-genai non installato: si gira solo free
    genai = None

try:
    from src.llm_fallback import resolve_fallback, chat_json
    from src.free_stack import (free_web_search, has_any_llm, llm_complete_json,
                                llm_mode, llm_source_label, describe_stack)
except ImportError:  # layout PYTHONPATH=src
    from llm_fallback import resolve_fallback, chat_json
    from free_stack import (free_web_search, has_any_llm, llm_complete_json,
                            llm_mode, llm_source_label, describe_stack)

load_dotenv()

try:
    from src.metrics import get_metrics
except ImportError:  # layout PYTHONPATH=src
    try:
        from metrics import get_metrics
    except ImportError:
        get_metrics = None


def _metric(name: str, *args) -> None:
    """Contatore ARCH-002. Una metrica rotta non deve fermare un arricchimento."""
    if get_metrics is None:
        return
    try:
        getattr(get_metrics(), name)(*args)
    except Exception:
        pass


# Cache URL Transfermarkt per giocatore: un profilo TM non cambia mai indirizzo,
# quindi la ricerca si paga una volta sola nella vita del giocatore.
TM_URL_CACHE = Path("data/tm_urls.json")

# ARCH-002 Fase 2 — validatori HTTP per pagina: ETag e Last-Modified.
# Una pagina TM cambia circa una volta a settimana, ma la pipeline gira ogni 6
# ore: senza richiesta condizionale si riscarica e si ri-parsifica lo stesso
# identico contenuto ~28 volte a settimana. Con il 304 quel lavoro sparisce, e
# con lui la chiamata LLM sul residuo.
TM_ETAG_CACHE = Path("data/tm_etags.json")

_TM_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "it-IT,it;q=0.9",
}

# Batch size for grounded enrichment. One Gemini call covers this many
# players — the main cost lever (N players -> N/BATCH calls instead of N).
# Kept small so grounding still searches each player properly.
BATCH_SIZE = 5
_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds


@dataclass
class FetchResult:
    """Esito di un fetch. `unchanged` = 304: contenuto identico a quello noto."""
    text: str = ""
    status: int = 0
    unchanged: bool = False


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
        # La pagina TM ripulita dai tag mette il label e il valore su righe
        # diverse ("Squadra attuale:\n\n\nUS Avellino 1912"), mentre il raw
        # markdown di Tavily li tiene sulla stessa riga. Si gestiscono entrambi
        # cercando il primo valore plausibile dopo il label.
        m = re.search(
            r"(?:Squadra attuale|Club attuale|Current club|Squadra)\s*:?",
            text,
            re.IGNORECASE,
        )
        if m:
            for line in text[m.end():m.end() + 300].splitlines():
                club = re.sub(r"\s{2,}", " ", line.strip())[:80]
                if club.endswith(":"):
                    continue  # è un altro label, non un valore
                if re.fullmatch(r"[\d/.,\-\s€%]+", club):
                    continue  # una data o un numero non è un nome di squadra
                if _ok_club(club):
                    out["current_club"] = club
                    break

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
    Arricchisce profili giocatori con dati Transfermarkt.

    Nessuna singola chiave è obbligatoria: serve solo che esista una rotta LLM
    (Groq da solo basta). Gemini e Serper, se ci sono, si aggiungono; se non
    ci sono, non bloccano niente.
    """

    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")

        # L'unico requisito reale: poter fare inferenza da qualche parte.
        if not has_any_llm():
            raise ValueError(
                "Nessuna rotta LLM configurata. Basta una tra GROQ_API_KEY, "
                "CEREBRAS_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, "
                "NVIDIA_API_KEY, COMPARE_BASE_URL o GEMINI_API_KEY."
            )

        self.session = requests.Session()
        self.mode = llm_mode()
        self.gemini_client = None
        if self.gemini_key and genai is not None and self.mode != "free_only":
            try:
                self.gemini_client = genai.Client(api_key=self.gemini_key)
            except Exception as e:
                print(f"  [GEMINI] client non inizializzato ({str(e)[:80]}) — si prosegue free")
        self.gemini_disabled = self.gemini_client is None
        self.fallback_cfg = resolve_fallback()
        self._tm_urls = self._load_tm_urls()
        # Fase 2 disattivabile senza rollback di codice (vincolo ARCH-002 §7)
        self._etag_enabled = os.getenv("OB1_ETAG", "1") != "0"
        self._etags = self._load_etags() if self._etag_enabled else {}
        # Ultimo giocatore risolto da un 304: niente parse, niente LLM, e
        # soprattutto niente fallback grounded (che sarebbe una spesa).
        self.last_unchanged = False
        # La ricerca interna di TM può essere bloccata sugli IP dei datacenter.
        # Non lo sappiamo prima di provare, quindi si prova una volta sola:
        # al primo rifiuto la rotta si spegne per il resto della run.
        # OB1_TM_SITE_SEARCH=0 la disattiva del tutto, senza toccare il codice.
        self._tm_search_dead = os.getenv("OB1_TM_SITE_SEARCH", "1") == "0"
        print(f"  [LLM] {describe_stack()}")

    # ------------------------------------------------------------ cache URL TM
    def _load_tm_urls(self) -> Dict[str, str]:
        try:
            data = json.loads(TM_URL_CACHE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_tm_urls(self) -> None:
        try:
            TM_URL_CACHE.parent.mkdir(parents=True, exist_ok=True)
            TM_URL_CACHE.write_text(
                json.dumps(self._tm_urls, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8")
        except OSError:
            pass

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
        """Gemini Search Grounding su TM. Disponibile solo se il client c'è."""
        if not self.gemini_client:
            return {}
        try:
            response = self.gemini_client.models.generate_content(
                model=os.getenv("GEMINI_MODEL") or "gemini-2.5-flash",
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

    # ------------------------------------------------------------ percorso free
    def _tm_url_from_site_search(self, player_name: str) -> str:
        """
        Chiede l'URL del profilo alla ricerca INTERNA di Transfermarkt.

        Il motore terzo (DDG/SearXNG) è il punto della catena che si blocca —
        è quello che produce la metrica search_blocked. Per trovare una pagina
        di Transfermarkt però il motore terzo non serve: TM ha la sua ricerca.
        Un salto in meno, e uno in meno che può essere bloccato.

        Resta un fallback e non una sostituzione: se anche TM blocca l'IP del
        runner, il percorso vecchio deve poter ancora provare.
        """
        # Traccia d'ingresso incondizionata — l'ultima cosa che poteva mancare
        # dopo due giri di diagnostica sui rami interni: se in produzione non
        # compare NEMMENO questa, la funzione non viene proprio raggiunta, e
        # il problema sta a monte (_tm_url_for o chi lo chiama), non qui dentro.
        print(f"  [TM SEARCH] tentativo per {player_name!r} "
              f"(dead={self._tm_search_dead})")

        # Se TM ha bloccato l'IP del runner, blocca TUTTE le richieste: insistere
        # per ogni giocatore costa un timeout a testa e non trova mai niente.
        # Un fallimento e la rotta si spegne per il resto della run.
        if self._tm_search_dead:
            return ""

        # Non passa da fetch_page: quella ripulisce i tag, e qui servono gli
        # href. Nemmeno serve la cache condizionale — l'URL trovato finisce in
        # _tm_urls e la ricerca non si rifà mai per lo stesso giocatore.
        try:
            import urllib.parse
            q = urllib.parse.quote(player_name)
            res = self.session.get(
                f"https://www.transfermarkt.it/schnellsuche/ergebnis/"
                f"schnellsuche?query={q}", headers=_TM_HEADERS, timeout=12)
            # Metrica separata di proposito: "fetch" conta le pagine profilo ed
            # è la base della misura dei 304 (ARCH-002). Contarci dentro anche
            # le query di ricerca falserebbe il risparmio del fetch condizionale.
            _metric("tm_site_search", res.status_code)
            if res.status_code != 200:
                if res.status_code in (403, 429, 503):
                    self._tm_search_dead = True
                    print(f"  [TM SEARCH] HTTP {res.status_code}: rotta spenta "
                          f"per questa run, si torna alla ricerca web")
                return ""
            page = res.text or ""
            if page:
                # Con un solo risultato esatto TM rimanda direttamente al
                # profilo: la pagina che abbiamo in mano è già un profilo, non
                # un elenco. La regex sui link prenderebbe allora il PRIMO
                # profilo presente (un compagno di squadra), arricchendo in
                # silenzio il giocatore sbagliato. Il canonical dice sempre
                # su che pagina siamo davvero.
                if "info-table__content" in page:
                    canon = re.search(r'<link rel="canonical" href="([^"]+)"', page)
                    if canon and "/profil/spieler/" in canon.group(1):
                        return canon.group(1)
                m = re.search(r'href="(/[^"]+/profil/spieler/\d+)"', page)
                if m:
                    return f"https://www.transfermarkt.it{m.group(1)}"
            # 200 senza un profilo da nessuna parte — corpo vuoto o pieno ma
            # senza match, due esiti diversi che prima di questa riga erano
            # LO STESSO ritorno muto, indistinguibile nel log da "provato e
            # non trovato". In produzione è successo 20 volte su 20 senza
            # lasciare traccia: mancava la prova per distinguere un blocco
            # anti-bot "leggero" (200 con corpo vuoto o quasi — verosimile
            # verso IP di datacenter come i runner CI) da un cambio di
            # formato della pagina (corpo pieno ma i marcatori non ci sono
            # più). Questa riga è quello che serve al prossimo run reale per
            # dirlo, invece di continuare a indovinare.
            print(f"  [TM SEARCH] 200 ma nessun profilo ({len(page)} char"
                  f"{', VUOTO' if not page else ''}, "
                  f"content-type={res.headers.get('content-type', '?')}, "
                  f"consent={'cookie' in page.lower() if page else '?'})")
            return ""
        except Exception as exc:
            _metric("tm_site_search_failed")
            self._tm_search_dead = True
            print(f"  [TM SEARCH] rotta spenta per questa run "
                  f"({type(exc).__name__}), si torna alla ricerca web")
            return ""

    def _tm_url_for(self, player_name: str) -> tuple:
        """
        (url TM, testo dallo snippet). Ricerca senza chiavi obbligatorie.
        L'URL viene cachato per sempre: un giocatore ha un solo profilo TM.
        """
        cached = self._tm_urls.get(player_name.lower())
        if cached:
            # Ramo che salterebbe la ricerca del tutto — se in produzione
            # tutti i 20 giocatori passano da qui, il file cache è la causa
            # del silenzio, non la ricerca stessa.
            print(f"  [TM URL/cache] {player_name}: {cached[:70]}")
            return cached, ""

        # Prima la ricerca interna di TM: nessun motore terzo da farsi bloccare.
        direct = self._tm_url_from_site_search(player_name)
        if direct:
            self._tm_urls[player_name.lower()] = direct
            self._save_tm_urls()
            print(f"  [TM URL/tm-search] {player_name}: {direct[:70]}")
            return direct, ""

        source, results = free_web_search(
            f"{player_name} profilo giocatore",
            max_results=5,
            include_domains=["transfermarkt.it", "transfermarkt.com"],
        )
        url, content = "", ""
        for r in results:
            if "/profil/spieler/" in (r.get("url") or "").lower():
                url, content = r["url"], r.get("content") or ""
                break
        if not url and results:
            url = results[0].get("url") or ""
            content = results[0].get("content") or ""
        if url:
            self._tm_urls[player_name.lower()] = url
            self._save_tm_urls()
            print(f"  [TM URL/{source}] {player_name}: {url[:70]}")
        return url, content

    # -------------------------------------------------------- cache condizionale
    def _load_etags(self) -> Dict[str, Dict[str, str]]:
        try:
            data = json.loads(TM_ETAG_CACHE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_etags(self) -> None:
        try:
            TM_ETAG_CACHE.parent.mkdir(parents=True, exist_ok=True)
            TM_ETAG_CACHE.write_text(
                json.dumps(self._etags, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8")
        except OSError:
            pass

    def _conditional_headers(self, url: str) -> Dict[str, str]:
        """If-None-Match / If-Modified-Since, se sappiamo com'era la pagina."""
        if not self._etag_enabled:
            return {}
        known = self._etags.get(url) or {}
        headers = {}
        if known.get("etag"):
            headers["If-None-Match"] = known["etag"]
        if known.get("last_modified"):
            headers["If-Modified-Since"] = known["last_modified"]
        return headers

    def _remember_validators(self, url: str, res) -> None:
        etag = (res.headers or {}).get("ETag") or ""
        last_mod = (res.headers or {}).get("Last-Modified") or ""
        if not (etag or last_mod):
            self._etags.pop(url, None)   # la pagina non è più validabile
            return
        self._etags[url] = {
            "etag": etag,
            "last_modified": last_mod,
            "seen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._save_etags()

    def fetch_page(self, url: str) -> FetchResult:
        """
        Scarica la pagina con richiesta condizionale.

        - 200 → testo ripulito, validatori memorizzati
        - 304 → `unchanged=True` e nessun testo: il chiamante NON deve
          parsificare né chiamare l'LLM, perché il contenuto è quello di prima
        - altro/errore → testo vuoto, `unchanged=False`: si riprova più avanti

        Distinguere 304 da errore è il punto: entrambi non danno testo, ma il
        primo è un successo (contenuto già noto) e il secondo è un buco.
        """
        if not url:
            return FetchResult("", 0, False)
        headers = dict(_TM_HEADERS)
        headers.update(self._conditional_headers(url))
        try:
            res = self.session.get(url, headers=headers, timeout=25)
        except requests.RequestException as e:
            print(f"  [FETCH ERROR] {type(e).__name__} su {url[:60]}")
            _metric("fetch", 0)
            return FetchResult("", 0, False)

        status = res.status_code
        _metric("fetch", status)
        if status == 304:
            print(f"  [FETCH 304] invariata: {url[:60]}")
            return FetchResult("", 304, True)
        if status != 200:
            print(f"  [FETCH] HTTP {status} su {url[:60]}")
            return FetchResult("", status, False)

        self._remember_validators(url, res)
        body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", res.text)
        text = re.sub(r"[ \t\r\f\v]+", " ",
                      html.unescape(re.sub(r"(?s)<[^>]+>", " ", body)))
        return FetchResult(text, 200, False)

    def _fetch_page_text(self, url: str) -> str:
        """Solo il testo. Nome storico: i call site esistenti non cambiano."""
        return self.fetch_page(url).text

    def enrich_player_free(self, player_name: str) -> Dict[str, Any]:
        """
        Percorso a costo zero: ricerca free -> fetch -> regex -> LLM sul residuo.
        Funziona con la sola GROQ_API_KEY, senza Serper e senza Gemini.
        """
        self.last_unchanged = False
        url, snippet = self._tm_url_for(player_name)
        fetched = self.fetch_page(url)
        if fetched.unchanged:
            # 304: la pagina è identica a quella già letta. Non c'è niente da
            # estrarre e niente da chiedere a un modello — è esattamente il
            # lavoro che ARCH-002 vuole smettere di rifare ogni 6 ore.
            self.last_unchanged = True
            return {}
        raw = fetched.text
        # TM risponde 403 di frequente: in quel caso resta lo snippet della
        # ricerca. Si tiene il testo più ricco tra i due, mai il più povero.
        if snippet and len(snippet) > len(raw):
            raw = snippet
        if not raw:
            return {}

        data = parse_tm_text(raw, url)  # regex: zero costo, zero allucinazioni
        if data.get("birth_date") or data.get("current_club"):
            print(f"  [REGEX] {player_name}: {data.get('birth_date')} / {data.get('current_club')}")

        thin = not (data.get("birth_date") and data.get("current_club"))
        if thin:
            llm = llm_complete_json(
                "Sei un estrattore di dati Transfermarkt. Rispondi SOLO con JSON valido.",
                self._parse_prompt_for_player(player_name, url, raw),
                gemini_client=self.gemini_client,
            )
            if isinstance(llm, dict):
                # Il deterministico vince: l'LLM riempie i buchi, non li corregge
                for k, v in llm.items():
                    if v is not None and not data.get(k):
                        data[k] = v

        if url and data and not data.get("tm_url"):
            data["tm_url"] = url
        if data:
            data["enrichment_source"] = llm_source_label() if thin else "Enrichment:regex"
        return data or {}

    # Nome storico: i call site esistenti continuano a funzionare.
    enrich_player_tavily = enrich_player_free

    @property
    def stalled(self) -> bool:
        """True quando non resta nessuna via per arricchire in questa run."""
        if not self.gemini_disabled:
            return False
        return not has_any_llm(free_only=True)

    def enrich_player(self, player_name: str) -> Dict[str, Any]:
        """Single player. Ordine deciso da OB1_LLM_MODE (default: free first)."""
        if self.mode == "gemini_first" and not self.gemini_disabled:
            data = self.enrich_player_grounded(player_name)
            if data:
                data.setdefault("enrichment_source", "Enrichment:gemini")
                return data

        data = self.enrich_player_free(player_name)
        if data:
            return data
        if self.last_unchanged:
            # Contenuto invariato non è "profilo non trovato": chiamare il
            # grounding qui vorrebbe dire pagare per riavere gli stessi dati.
            return {}

        if self.mode != "free_only" and not self.gemini_disabled:
            data = self.enrich_player_grounded(player_name)
            if data:
                data.setdefault("enrichment_source", "Enrichment:gemini")
        return data or {}

    def enrich_players_batch(self, names: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Batch. Con OB1_LLM_MODE=gemini_first e client attivo: 1 chiamata grounded
        ogni BATCH_SIZE giocatori (comportamento storico). Altrimenti percorso
        free per giocatore — nessuna chiamata fatturabile.
        """
        if not names:
            return {}

        if self.mode == "gemini_first" and not self.gemini_disabled:
            out = self._enrich_batch_grounded(names)
            if any(out.values()):
                return out

        out, unchanged = {}, 0
        for name in names:
            out[name] = self.enrich_player_free(name)
            unchanged += 1 if self.last_unchanged else 0
        found = sum(1 for v in out.values() if v)
        note = f", {unchanged} invariati (304)" if unchanged else ""
        print(f"  [BATCH FREE] {found}/{len(names)} profili{note} "
              f"(0 chiamate fatturabili)")
        return out

    def _enrich_batch_grounded(self, names: List[str]) -> Dict[str, Dict[str, Any]]:
        """1 chiamata Gemini grounded per BATCH_SIZE giocatori. Costo: a consumo."""
        if self.gemini_disabled:
            print("  [BATCH SKIP] Gemini off — percorso free")
            return {}

        prompt = _BATCH_PROMPT.format(names="\n".join(f"- {n}" for n in names))
        response = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = self.gemini_client.models.generate_content(
                    model=os.getenv("GEMINI_MODEL") or "gemini-2.5-flash",
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
        for prof in out.values():
            if prof:
                prof.setdefault("enrichment_source", "Enrichment:gemini")
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
