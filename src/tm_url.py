#!/usr/bin/env python3
"""
Validazione degli URL Transfermarkt.

Il contesto: questi link finiscono in un report che un osservatore apre davanti
al direttore sportivo. Un link che porta al giocatore sbagliato non è un
dettaglio estetico — è il motivo per cui il report non viene più aperto.
**Meglio nessun link che un link sbagliato.**

Sul database reale, 101 URL su 370 erano rotti (27%), in quattro modi:

  43  /profil/spieler/ senza ID     -> l'LLM costruisce lo slug ma l'ID non può
                                       saperlo: gli era stato chiesto un dato
                                       che non possiede
  27  redirect vertexaisearch...    -> URL di grounding Gemini, scadono
   8  /startseite/verein/           -> pagina squadra presa come primo risultato
   7  altre pagine TM               -> es. /gemeinsameSpiele/, non il profilo
  16  slug di un ALTRO giocatore    -> "Berardini Alessandro" che punta a
                                       "stefano-del-sante"

Le regole qui sono deterministiche: un ID è un numero, uno slug o contiene il
nome o non lo contiene. Nessun modello serve per deciderlo.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional, Set

# Un profilo giocatore ha SEMPRE questa forma, ID numerico incluso.
_PROFILE_RE = re.compile(
    r"^https?://(?:www\.)?transfermarkt\.[a-z.]{2,6}/([^/]+)/profil/spieler/(\d+)",
    re.IGNORECASE,
)

# Host che non sono Transfermarkt anche quando il link nasce da una sua ricerca.
_REDIRECT_MARKERS = ("grounding-api-redirect", "vertexaisearch", "/url?q=",
                     "webcache.googleusercontent")

# Token che compaiono negli slug ma non sono parte del nome.
_SLUG_NOISE = {"fc", "us", "ac", "ssd", "asd", "calcio", "spa", "srl"}

_MIN_TOKEN_LEN = 3


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _tokens(text: str) -> Set[str]:
    return {t for t in _norm(text).split()
            if len(t) >= _MIN_TOKEN_LEN and t not in _SLUG_NOISE}


def is_profile_url(url: object) -> bool:
    """True solo per un URL di profilo giocatore completo di ID numerico."""
    if not isinstance(url, str) or not url.strip():
        return False
    low = url.lower()
    if any(m in low for m in _REDIRECT_MARKERS):
        return False
    return bool(_PROFILE_RE.match(url.strip()))


def profile_id(url: object) -> Optional[str]:
    if not isinstance(url, str):
        return None
    m = _PROFILE_RE.match(url.strip())
    return m.group(2) if m else None


def profile_slug(url: object) -> str:
    if not isinstance(url, str):
        return ""
    m = _PROFILE_RE.match(url.strip())
    return m.group(1) if m else ""


def matches_player(url: object, player_name: object) -> bool:
    """
    Lo slug dell'URL e il nome del giocatore devono condividere almeno un
    token significativo. Regge le varianti reali — "Rizzo Pinna" contro
    "andrea-rizzo-pinna", "CHIOETTO JHONATAN DAVID" contro
    "jhonatan-chioetto" — e ferma i cambi di persona.

    Senza nome non si può giudicare: si risponde True e decide chi chiama.
    """
    if not is_profile_url(url):
        return False
    name_tokens = _tokens(str(player_name or ""))
    if not name_tokens:
        return True
    return bool(name_tokens & _tokens(profile_slug(url).replace("-", " ")))


def clean(url: object, player_name: object = None) -> Optional[str]:
    """
    L'URL se è pubblicabile, altrimenti None. Con `player_name` verifica anche
    che punti a quella persona. È l'unico punto da cui far passare un link
    prima di scriverlo nel database o in un report.
    """
    if not is_profile_url(url):
        return None
    u = url.strip()
    if player_name is not None and not matches_player(u, player_name):
        return None
    return u


def diagnose(url: object, player_name: object = None) -> str:
    """Motivo dello scarto, per i log e per lo script di bonifica."""
    if not isinstance(url, str) or not url.strip():
        return "vuoto"
    low = url.lower()
    if any(m in low for m in _REDIRECT_MARKERS):
        return "redirect di grounding, non un URL Transfermarkt"
    if "transfermarkt" not in low:
        return "non è Transfermarkt"
    if "/profil/spieler/" in low and not re.search(r"/profil/spieler/\d+", low):
        return "profilo senza ID: costruito, non osservato"
    if "/startseite/verein/" in low:
        return "pagina squadra, non profilo giocatore"
    if not _PROFILE_RE.match(url.strip()):
        return "pagina Transfermarkt che non è un profilo giocatore"
    if player_name is not None and not matches_player(url, player_name):
        return (f"profilo di un altro giocatore: slug '{profile_slug(url)}' "
                f"contro '{player_name}'")
    return "valido"
