#!/usr/bin/env python3
"""
Gate entità: decide se vale la pena SPENDERE su un record.

È il quanto più economico della pipeline (ARCH-002, corollario zero): una entry
che non è un giocatore — o che è un giocatore fuori portata per la Serie C —
viene cercata, scaricata e arricchita a ogni ciclo, per sempre. Il filtro qui
costa zero e taglia quella spesa alla radice.

Tre esiti:
  player        -> si spende
  junk          -> non è una persona: va rimossa dal DB
  out_of_scope  -> è un giocatore vero ma non un'opportunità di Serie C
                   (es. valore 35 mln €). Non si spende, ma non si butta:
                   la decisione di cancellarlo è di chi gestisce il radar.

Perché non una blacklist di stringhe: una lista di frasi già viste cattura solo
ciò che è già passato. Qui si ragiona su **token**, così "La Serie" e "Summer
Transfer Big Board" cadono, mentre "La Gumina", "Da Riva" e "Della Morte"
restano — sono cognomi veri che una blacklist per sottostringa distruggerebbe.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Optional

PLAYER = "player"
JUNK = "junk"
OUT_OF_SCOPE = "out_of_scope"

# Un giocatore di Serie C non vale queste cifre: se il valore è questo, il
# record è corretto ma non è un'opportunità per questo radar.
DEFAULT_MAX_MARKET_VALUE = 5_000_000

# Vocabolario editoriale/organizzativo. Confrontato per TOKEN, mai per
# sottostringa. Volutamente esclusi i termini che sono anche cognomi italiani
# comuni (Marino, Costa, Monti, Riva, Longo, Grillo...).
_JUNK_TOKENS = {
    # editoria e media
    "comunicato", "ufficiale", "ufficialita", "news", "notizie", "notiziario",
    "radio", "tv", "web", "magazine", "giornale", "quotidiano", "portale",
    "redazione", "editoriale", "esclusiva", "focus", "report", "rassegna",
    "intervista", "video", "podcast", "live", "diretta", "ultime", "ultimissime",
    # mercato e gergo da titolo
    "mercato", "calciomercato", "transfer", "transfers", "board", "summer",
    "winter", "big", "top", "flop", "parametro", "svincolati", "svincolato",
    "trattativa", "trattative", "affare", "colpo", "ufficialmente",
    # competizioni e strutture
    "classifica", "ranking", "tabella", "calendario", "risultati", "spareggi",
    "playoff", "playout", "campionato", "serie", "lega", "girone", "coppa",
    "torneo", "trofeo", "federazione", "dipartimento", "associazione",
    "rappresentativa", "juniores", "eccellenza", "promozione", "dilettanti",
    # ruoli non-giocatore
    "presidente", "direttore", "allenatore", "mister", "procuratore",
    "societa", "squadra", "club", "staff", "dirigenza",
    # inglese da aggregatori
    "football", "soccer", "league", "season", "update", "preview", "roundup",
    "wiki", "official", "statement",
}

# Prime parole che, da sole, non aprono mai un nome di persona.
_JUNK_FIRST_TOKENS = {
    "the", "tutto", "tutti", "nuova", "nuovo", "cinque", "tanti", "un", "una",
    "quanti", "quante", "ecco", "come", "perche", "chi", "cosa", "quale",
}

# Preposizioni e articoli legittimi dentro un cognome (La Gumina, Da Riva,
# De Rossi, Van Dijk). Non sono un segnale di spazzatura di per sé.
_NAME_PARTICLES = {
    "la", "le", "lo", "da", "dal", "de", "del", "della", "delle", "degli", "di",
    "van", "von", "der", "den", "dos", "das", "do", "el", "al", "ben", "mac", "mc",
}

_MONTHS = {
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
    "agosto", "settembre", "ottobre", "novembre", "dicembre",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}


@dataclass
class Verdict:
    kind: str
    reason: str = ""

    @property
    def spend_allowed(self) -> bool:
        """Unica domanda che conta a monte: ci spendo una ricerca e un LLM?"""
        return self.kind == PLAYER

    @property
    def is_junk(self) -> bool:
        return self.kind == JUNK

    def __bool__(self) -> bool:
        return self.spend_allowed


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.split())


def classify_name(name: Any) -> Verdict:
    """Verdetto sul solo nome. Non richiede che il record sia arricchito."""
    if not isinstance(name, str):
        return Verdict(JUNK, "non è una stringa")

    raw = " ".join(name.split())
    if len(raw) < 3:
        return Verdict(JUNK, "troppo corto")
    if len(raw) > 40:
        return Verdict(JUNK, "troppo lungo per un nome")
    if "|" in raw or "_" in raw or "@" in raw:
        return Verdict(JUNK, "contiene separatori da titolo/handle")
    if any(c.isdigit() for c in raw):
        return Verdict(JUNK, "contiene cifre")

    flat = _norm(raw).lower()
    tokens = flat.split()
    if len(tokens) < 2:
        return Verdict(JUNK, "nome singolo")
    if len(tokens) > 4:
        return Verdict(JUNK, f"{len(tokens)} token: è una frase, non un nome")

    if tokens[0] in _JUNK_FIRST_TOKENS:
        return Verdict(JUNK, f"inizia con '{tokens[0]}'")

    hits = [t for t in tokens if t in _JUNK_TOKENS]
    if hits:
        return Verdict(JUNK, f"vocabolario editoriale: {', '.join(hits)}")
    if any(t in _MONTHS for t in tokens):
        return Verdict(JUNK, "contiene un mese")

    # Un nome fatto solo di particelle non è un nome ("Di Del", "La De")
    if all(t in _NAME_PARTICLES for t in tokens):
        return Verdict(JUNK, "solo particelle nominali")

    return Verdict(PLAYER)


def classify(opp: Dict[str, Any], max_market_value: Optional[int] = None) -> Verdict:
    """
    Verdetto sul record completo: nome + plausibilità dei valori.
    Da chiamare PRIMA di qualsiasi ricerca, fetch o chiamata LLM.
    """
    verdict = classify_name(opp.get("player_name") or opp.get("name"))
    if not verdict.spend_allowed:
        return verdict

    cap = DEFAULT_MAX_MARKET_VALUE if max_market_value is None else max_market_value
    profile = opp.get("player_profile") or {}
    for key in ("market_value", "market_value_eur"):
        raw = opp.get(key) if opp.get(key) is not None else profile.get(key)
        try:
            mv = float(raw)
        except (TypeError, ValueError):
            continue
        if mv > cap:
            return Verdict(
                OUT_OF_SCOPE,
                f"valore {mv / 1e6:.1f} mln € fuori fascia Serie C (cap {cap / 1e6:.0f} mln)",
            )
    return verdict


def is_player_name(name: Any) -> bool:
    """Compat: True se il nome supera il gate strutturale."""
    return classify_name(name).spend_allowed


def find_particle_duplicates(names) -> Dict[str, str]:
    """
    "Da Bernardo Silva" quando esiste già "Bernardo Silva": è un artefatto di
    parsing (preposizione incollata dal testo), non un secondo giocatore.
    Ritorna {nome_artefatto: nome_canonico}.
    """
    canonical = {_norm(n).lower(): n for n in names if isinstance(n, str)}
    out = {}
    for n in names:
        if not isinstance(n, str):
            continue
        tokens = _norm(n).lower().split()
        if len(tokens) < 3 or tokens[0] not in _NAME_PARTICLES:
            continue
        tail = " ".join(tokens[1:])
        if tail in canonical and canonical[tail] != n:
            out[n] = canonical[tail]
    return out
