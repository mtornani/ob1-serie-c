#!/usr/bin/env python3
"""
OB1 Lega Pro — Quality / publish gate (allineato a global-scout v2).

Promessa: ogni nome in dashboard regge una telefonata di verifica.
Gate in CODICE, non LLM. Per nicchia C/D:
  - identity_complete = nome completo + età valida + club + fonte
  - corroborated     = profilo TM giocatore OPPURE ≥2 domini
  - publishable      = identity_complete (corroboration = bonus, non hard yet
                       finché store non accumula prove multi-fonte)

Non richiede SQLite v2: lavora su dict opportunity esistenti.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse


# Età plausibile calciatore professionista / young talent C-D
AGE_MIN = 15
AGE_MAX = 42

# Anno di nascita confuso con "age" (bug enrichment)
BIRTH_YEAR_MIN = 1980
BIRTH_YEAR_MAX = 2012

_TM_PLAYER_RE = re.compile(
    r"transfermarkt\.[a-z.]+/.+/profil/spieler/\d+",
    re.IGNORECASE,
)


def normalize_age(age: Any, birth_date: Any = None, birth_year: Any = None) -> Optional[int]:
    """
    Ritorna età intera plausibile, o None.
    Converte anni di nascita finiti per sbaglio in campo age (es. 2005 → 21).
    """
    year_now = datetime.now().year

    if birth_date:
        try:
            s = str(birth_date)[:10]
            if len(s) >= 4 and s[:4].isdigit():
                by = int(s[:4])
                if BIRTH_YEAR_MIN <= by <= BIRTH_YEAR_MAX:
                    return year_now - by
        except (TypeError, ValueError):
            pass

    if birth_year is not None:
        try:
            by = int(birth_year)
            if BIRTH_YEAR_MIN <= by <= BIRTH_YEAR_MAX:
                return year_now - by
        except (TypeError, ValueError):
            pass

    if age is None or age == "":
        return None
    try:
        a = int(age)
    except (TypeError, ValueError):
        return None

    # birth year dumped into age field
    if BIRTH_YEAR_MIN <= a <= BIRTH_YEAR_MAX:
        return year_now - a

    if AGE_MIN <= a <= AGE_MAX:
        return a
    return None


def _source_domain(url: str) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def has_tm_player_profile(opp: dict) -> bool:
    """True se c'è URL profilo giocatore Transfermarkt (non pagina lega/generic)."""
    for key in ("tm_url", "transfermarkt_url", "source_url"):
        url = opp.get(key) or ""
        if _TM_PLAYER_RE.search(url):
            return True
    profile = opp.get("player_profile") or {}
    for key in ("tm_url", "transfermarkt_url", "url"):
        url = profile.get(key) or ""
        if _TM_PLAYER_RE.search(url):
            return True
    return False


def count_distinct_sources(opp: dict) -> int:
    """Conta domini distinti dalle prove disponibili sul record flat."""
    domains = set()
    for key in ("source_url", "tm_url", "transfermarkt_url"):
        d = _source_domain(opp.get(key) or "")
        if d:
            domains.add(d)
    sources = opp.get("sources") or []
    if isinstance(sources, list):
        for s in sources:
            if isinstance(s, dict):
                d = s.get("domain") or _source_domain(s.get("url") or "")
            else:
                d = _source_domain(str(s))
            if d:
                domains.add(d)
    return len(domains)


def assess_identity(opp: dict) -> dict:
    """
    Valuta identità + gate pubblicazione per un'opportunity Lega Pro / Serie D.
    """
    name = (opp.get("player_name") or opp.get("name") or "").strip()
    tokens = [t for t in name.split() if t]
    token_count = len(tokens)
    looks_like_handle = any(ch.isdigit() for ch in name) or "_" in name

    age = normalize_age(
        opp.get("age"),
        birth_date=opp.get("birth_date"),
        birth_year=opp.get("birth_year"),
    )
    club = (opp.get("current_club") or "").strip()
    source_url = (opp.get("source_url") or "").strip()
    n_sources = count_distinct_sources(opp)
    tm_ok = has_tm_player_profile(opp)

    flags = []
    if token_count <= 1:
        flags.append("nome_singolo")
    if looks_like_handle:
        flags.append("handle_o_soprannome")
    if not club or club.upper() in ("N/D", "ND", "-"):
        flags.append("club_mancante")
    if age is None:
        flags.append("eta_mancante")
    if not source_url:
        flags.append("fonte_mancante")
    if n_sources < 2 and not tm_ok:
        flags.append("fonte_singola")
    if not tm_ok and not (opp.get("appearances") or (opp.get("player_profile") or {}).get("appearances")):
        flags.append("stats_mancanti")

    identity_complete = (
        token_count >= 2
        and not looks_like_handle
        and bool(club and club.upper() not in ("N/D", "ND", "-"))
        and age is not None
        and bool(source_url)
    )
    # Nicchia C/D: profilo TM giocatore conta come seconda prova forte
    corroborated = n_sources >= 2 or tm_ok
    # Publishable: identità completa. Corroboration preferita ma non hard-gate
    # finché pipeline non accumula multi-fonte (altrimenti dashboard vuota).
    publishable = identity_complete

    return {
        "age_normalized": age,
        "name_token_count": token_count,
        "n_sources": n_sources,
        "tm_player_profile": tm_ok,
        "identity_complete": identity_complete,
        "corroborated": corroborated,
        "publishable": publishable,
        "review_flags": ",".join(flags),
    }


def apply_gate(opp: dict) -> dict:
    """Ritorna copia opportunity con età normalizzata + flag gate."""
    out = dict(opp)
    gate = assess_identity(opp)
    if gate["age_normalized"] is not None:
        out["age"] = gate["age_normalized"]
    out["identity_complete"] = gate["identity_complete"]
    out["corroborated"] = gate["corroborated"]
    out["publishable"] = gate["publishable"]
    out["review_flags"] = gate["review_flags"]
    out["n_sources"] = gate["n_sources"]
    return out
