#!/usr/bin/env python3
"""
Da che categoria arriva un giocatore svincolato.

Il CU dice chi ha svincolato e da quale societa'. Non dice in che campionato
gioca quella societa' — ma i calendari lo dicono, e sono allegati agli stessi
comunicati. Incrociando le due cose, "scarto di Serie D" smette di essere
un'intuizione e diventa un filtro.

Il livello e' l'unica cosa vicina a una misura di impatto che questi documenti
permettano: **non dicono se ha giocato, quanto e come**. Chi legge deve saperlo,
ed e' il motivo per cui le schede parlano di "categoria di provenienza" e mai
di quanto un giocatore sia forte.

Il problema vero non e' il parsing, e' il **nome della societa'**: il CU degli
svincoli scrive "IMOLESE FC SSD", il calendario "IMOLESE FOOTBALL CLUB SSD",
un altro documento "U.S. EDELWEISS JOLLY SSDARL". Si normalizza togliendo le
forme giuridiche e si confronta sul nucleo del nome.

Test: PYTHONIOENCODING=utf-8 python -m unittest tests.test_livelli -v
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional

REGISTRO = Path("config/club_categorie.json")

# Ordinate dall'alto. Il numero serve a calcolare il salto, non a giudicare.
LIVELLO = {
    "serie_d": 4,
    "eccellenza": 3,
    "promozione": 2,
    "prima_categoria": 1,
}
ETICHETTA = {
    "serie_d": "Serie D",
    "eccellenza": "Eccellenza",
    "promozione": "Promozione",
    "prima_categoria": "Prima Categoria",
}

# Forme giuridiche e sigle che le societa' mettono e tolgono a piacere. Vanno
# via prima del confronto: sono rumore, non identita'.
_SIGLE = re.compile(
    r"\b(a\.?s\.?d\.?|s\.?s\.?d\.?(?:\s*a\.?r\.?l\.?)?|a\.?r\.?l\.?|s\.?r\.?l\.?|"
    r"u\.?s\.?d\.?|a\.?c\.?d\.?|p\.?g\.?s\.?|f\.?c\.?|a\.?c\.?|u\.?s\.?|a\.?s\.?|"
    r"s\.?s\.?|calcio|football\s+club|societa'?\s+sportiva|polisportiva|ssdarl)\b",
    re.IGNORECASE)
_NON_ALFA = re.compile(r"[^a-z0-9]+")


def normalizza(nome: str) -> str:
    """
    'IMOLESE FOOTBALL CLUB SSD' e 'IMOLESE FC SSD' -> 'imolese'.

    L'anno di fondazione resta ('1922'): distingue societa' omonime di paesi
    diversi, ed e' l'unica parte numerica che significa qualcosa.
    """
    if not nome:
        return ""
    testo = _SIGLE.sub(" ", str(nome).lower())
    return _NON_ALFA.sub(" ", testo).strip()


def _nucleo(nome_normalizzato: str) -> str:
    """La prima parola: quella che sopravvive a ogni abbreviazione."""
    parti = nome_normalizzato.split()
    return parti[0] if parti else ""


def costruisci_mappa(calendari: Dict[str, str]) -> Dict[str, str]:
    """
    {categoria: testo del calendario} -> {nome normalizzato: categoria}.

    Codice puro: il testo lo scarica chi chiama. Le squadre si leggono dalle
    righe delle partite, che nei calendari hanno forma "CASA – TRASFERTA".
    """
    mappa: Dict[str, str] = {}
    for categoria, testo in calendari.items():
        for casa, fuori in re.findall(
                r"^\s*(.+?)\s+[–—-]\s+(.+?)\s*$", testo or "", re.M):
            for grezzo in (casa, fuori):
                if any(x in grezzo.lower() for x in ("andata", "ritorno", "giornata")):
                    continue
                n = normalizza(grezzo)
                if len(n) < 3:
                    continue
                # Una societa' compare in un solo campionato: se ricapita,
                # tiene la categoria piu' alta gia' vista. Un conflitto vero
                # (stesso nome in due categorie) e' quasi sempre due societa'
                # omonime, e la prima parola non basta a separarle: meglio
                # sovrastimare il livello che dichiararne uno piu' basso.
                if n not in mappa or LIVELLO[categoria] > LIVELLO[mappa[n]]:
                    mappa[n] = categoria
    return mappa


# Righe di contorno dei PDF federali: intestazioni, indirizzi, piè di pagina.
# Senza questa lista "FEDERAZIONE ITALIANA GIUOCO CALCIO" diventa una squadra
# di Serie D, e da lì in poi ogni svincolato di quella "societa'" risulta
# arrivare dalla categoria più alta.
_CONTORNO = re.compile(
    r"federazione|lega nazionale|dipartimento|comitato|sito internet|"
    r"stagione sportiva|comunicato|piazzale|tel\.|pag\.|girone|"
    r"^\s*\d+\s*$|dilettanti$", re.IGNORECASE)


def costruisci_da_elenco(testo: str, categoria: str) -> Dict[str, str]:
    """
    Formato "elenco": un'intestazione GIRONE e sotto una societa' per riga.

    E' come il Dipartimento Interregionale pubblica i gironi di Serie D — non
    un calendario di partite, una lista. Si accettano solo le righe in
    maiuscolo che seguono un GIRONE e non sono contorno del documento.
    """
    mappa: Dict[str, str] = {}
    dentro = False
    for riga in (testo or "").splitlines():
        r = riga.strip()
        if re.match(r"^GIRONE\s+[A-Z]\b", r, re.IGNORECASE):
            dentro = True
            continue
        if not dentro or not r or _CONTORNO.search(r):
            continue
        lettere = [c for c in r if c.isalpha()]
        if len(lettere) < 3 or len(r) > 42:
            continue
        # Maiuscolo: e' cosi' che sono scritte le societa' in questi elenchi,
        # e distingue il nome dalla prosa che a volte si infila fra i gironi.
        if sum(1 for c in lettere if c.isupper()) / len(lettere) < 0.9:
            continue
        n = normalizza(r)
        if len(n) >= 3:
            mappa.setdefault(n, categoria)
    return mappa


def categoria_di(societa: str, mappa: Dict[str, str]) -> Optional[str]:
    """
    In che campionato gioca questa societa', o None.

    Prima il confronto esatto sul nome normalizzato, poi sul nucleo. Il
    secondo passaggio serve perche' il CU degli svincoli abbrevia; non si va
    oltre, perche' cercare per sottostringa farebbe combaciare "REAL" con
    mezzo campionato.
    """
    n = normalizza(societa)
    if not n:
        return None
    if n in mappa:
        return mappa[n]
    nucleo = _nucleo(n)
    if len(nucleo) < 4:
        return None      # nuclei corti ("real", "us") non identificano niente
    candidati = {c for chiave, c in mappa.items() if _nucleo(chiave) == nucleo}
    return candidati.pop() if len(candidati) == 1 else None


def salto_verso(categoria_provenienza: Optional[str],
                categoria_obiettivo: str = "eccellenza") -> Optional[int]:
    """
    Quanti gradini sopra (o sotto) l'obiettivo. None se non lo sappiamo.

    +1 = viene da una categoria superiore, 0 = stesso livello, -1 = sotto.
    """
    if categoria_provenienza not in LIVELLO:
        return None
    return LIVELLO[categoria_provenienza] - LIVELLO.get(categoria_obiettivo, 3)


def carica_registro(percorso: Path = REGISTRO) -> Dict[str, str]:
    try:
        return json.loads(Path(percorso).read_text(encoding="utf-8"))["club"]
    except (OSError, ValueError, KeyError):
        return {}


def salva_registro(mappa: Dict[str, str], percorso: Path = REGISTRO) -> None:
    Path(percorso).write_text(json.dumps(
        {"_meta": {"scopo": "societa' -> categoria, dai calendari allegati ai CU. "
                            "Rigenerabile con scripts/costruisci_livelli.py"},
         "club": dict(sorted(mappa.items()))},
        ensure_ascii=False, indent=1), encoding="utf-8")
