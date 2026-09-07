#!/usr/bin/env python3
"""
ECC-001 — Scoring per un club di Eccellenza regionale.

Perche' non basta SCORE-002 con altri pesi: due fattori hanno il segno
**invertito**, non l'intensita' diversa.

  - Valore di mercato. In Serie C un valore alto e' esperienza certificata e
    alza il punteggio. Per un club che riparte dai dilettanti e' il segnale
    che il giocatore e' fuori portata: non lo paghi e non scendera' mai di
    tre categorie. Qui vale di piu' chi un valore non ce l'ha.
  - Distanza. In Serie C e' quasi irrilevante, si trasferisce. In Eccellenza
    un tesserato lavora o studia, si allena tre sere e torna a casa: se sta a
    duecento chilometri, la trattativa non esiste. E' il primo filtro, non
    l'ultimo.

Il resto della differenza sta nel gate, non nei pesi. **Un profilo senza
fonte tracciabile non prende un punteggio basso: non prende punteggio.**
Restituisce `valutabile: False` con il motivo. Misurato il 7/9/2026 sul
database: dei 336 svincolati che passano il gate entita', 60 hanno presenze
verificate, 18 stanno in fascia, 1 ha un legame territoriale — e quell'uno ha
una presenza in carriera e una fonte che risponde 404. Un numero su quel
record sarebbe stato l'unica cosa peggiore di nessun numero.

Uso:
    from src.scoring_eccellenza import EccellenzaScorer
    s = EccellenzaScorer(base="rimini")
    s.score(opportunity)   # -> dict con valutabile / punteggio / perche'

Test: PYTHONIOENCODING=utf-8 python -m unittest tests.test_scoring_eccellenza -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.quality_gate import e_redirect_di_ricerca, is_tm_verified

# --- geografia: bacini realmente raggiungibili da una base -------------------
# Non sono province amministrative: sono "distanze da pendolare serale".
# Il primo anello e' quello da cui uno viene ad allenarsi tre sere a settimana
# senza pensarci; il secondo e' quello che si fa se il progetto convince.
BACINI = {
    "rimini": {
        "vicino": ["rimini", "santarcangelo", "riccione", "cattolica", "bellaria",
                   "igea marina", "novafeltria", "verucchio", "coriano", "morciano",
                   "san marino", "sammaurese", "san mauro", "savignano", "gatteo",
                   "cesenatico", "misano", "pietracuta"],
        "medio": ["cesena", "forl", "ravenna", "faenza", "lugo", "russi", "imola",
                  "pesaro", "fano", "urbino", "gabicce", "cervia", "bagnacavallo"],
    },
}

# Livelli da cui un tesserato scende in Eccellenza senza che sia un'anomalia.
LIVELLI_COERENTI = ("eccellenza", "promozione", "serie d", "prima categoria",
                    "juniores", "primavera")

PESI = {
    "prossimita": 0.30,     # senza questo non si tessera nessuno
    "disponibilita": 0.25,  # svincolato o niente
    "sostenibilita": 0.20,  # quanto e' realistico economicamente
    "coerenza": 0.15,       # viene da un livello da cui si scende davvero
    "eta": 0.10,            # mix rosa + quote giovani
}

TIPO = {"svincolato": 100, "rescissione": 90, "scadenza": 70,
        "prestito": 45, "mercato": 25, "altro": 20}


def _testo(opp: Dict[str, Any]) -> str:
    campi = ("current_club", "previous_clubs", "summary", "description",
             "source_title", "region", "player_name")
    return " ".join(str(opp.get(k) or "") for k in campi).lower()


def _valore(opp: Dict[str, Any]) -> Optional[int]:
    v = opp.get("market_value")
    try:
        return int(v) if v not in (None, "", 0) else None
    except (TypeError, ValueError):
        return None


class EccellenzaScorer:
    """Punteggio 0-100 per un club di Eccellenza, con rifiuto esplicito."""

    def __init__(self, base: str = "rimini", giorni_freschezza: int = 45):
        self.base = base
        self.bacino = BACINI.get(base, {"vicino": [], "medio": []})
        # Uno svincolato di tre mesi fa non e' piu' un'informazione: o ha
        # firmato, o c'e' un motivo per cui non ha firmato. In entrambi i casi
        # il dato che abbiamo non descrive piu' la realta'.
        self.giorni_freschezza = giorni_freschezza

    # ------------------------------------------------------------ ammissione
    def perche_non_valutabile(self, opp: Dict[str, Any]) -> Optional[str]:
        """Il motivo per cui questo record non merita un numero, o None."""
        if not is_tm_verified(opp):
            if e_redirect_di_ricerca(opp.get("source_url") or ""):
                return "fonte non tracciabile (redirect di ricerca, scade)"
            return "nessun profilo Transfermarkt aperto e verificato"

        pres = opp.get("appearances")
        if not pres or int(pres) < 5:
            return f"presenze insufficienti per un giudizio ({pres or 0})"

        eta = opp.get("age")
        if not eta:
            return "eta' sconosciuta"

        giorni = self._giorni_da_scoperta(opp)
        if giorni is not None and giorni > self.giorni_freschezza:
            # Il motivo e' la SOGLIA, non i giorni del singolo record: chi
            # aggrega gli scarti (valuta_lista) deve poterli contare insieme,
            # e "87 giorni" e "190 giorni" sono lo stesso problema.
            return f"segnalazione piu' vecchia di {self.giorni_freschezza} giorni"
        return None

    def _giorni_da_scoperta(self, opp: Dict[str, Any]) -> Optional[int]:
        raw = opp.get("reported_date") or opp.get("discovered_at") or ""
        try:
            d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days

    # ------------------------------------------------------------ componenti
    def _prossimita(self, opp: Dict[str, Any]) -> int:
        t = _testo(opp)
        if any(c in t for c in self.bacino["vicino"]):
            return 100
        if any(c in t for c in self.bacino["medio"]):
            return 65
        return 15          # non zero: un legame puo' esistere e non essere scritto

    def _disponibilita(self, opp: Dict[str, Any]) -> int:
        return TIPO.get((opp.get("opportunity_type") or "altro").lower(), 20)

    def _sostenibilita(self, opp: Dict[str, Any]) -> int:
        """Segno invertito rispetto a SCORE-002: qui il valore alto penalizza."""
        v = _valore(opp)
        if v is None:
            return 75      # tipico del dilettante: assenza di valore non e' un difetto
        if v <= 25_000:
            return 100
        if v <= 75_000:
            return 80
        if v <= 150_000:
            return 45
        if v <= 300_000:
            return 20
        return 5           # oltre: non scendera' in Eccellenza, e lo sappiamo

    def _coerenza(self, opp: Dict[str, Any]) -> int:
        t = _testo(opp)
        if any(l in t for l in LIVELLI_COERENTI):
            return 100
        if "serie c" in t or "lega pro" in t:
            return 55      # possibile ma va verificato a voce: perche' scende?
        if "serie a" in t or "serie b" in t:
            return 20
        return 50

    def _eta(self, opp: Dict[str, Any]) -> int:
        try:
            e = int(opp.get("age"))
        except (TypeError, ValueError):
            return 50
        if e <= 20:
            return 100     # utile anche per le quote giovani obbligatorie
        if e <= 23:
            return 90
        if e <= 28:
            return 80      # il centro della rosa
        if e <= 32:
            return 60
        return 35

    # ----------------------------------------------------------------- score
    def score(self, opp: Dict[str, Any]) -> Dict[str, Any]:
        motivo = self.perche_non_valutabile(opp)
        if motivo:
            return {"valutabile": False, "motivo": motivo,
                    "punteggio": None, "fascia": None, "breakdown": {}}

        b = {
            "prossimita": self._prossimita(opp),
            "disponibilita": self._disponibilita(opp),
            "sostenibilita": self._sostenibilita(opp),
            "coerenza": self._coerenza(opp),
            "eta": self._eta(opp),
        }
        punteggio = int(round(sum(b[k] * PESI[k] for k in PESI)))
        fascia = ("da chiamare" if punteggio >= 75
                  else "da valutare" if punteggio >= 55
                  else "fuori profilo")
        return {"valutabile": True, "motivo": None, "punteggio": punteggio,
                "fascia": fascia, "breakdown": b}


def valuta_lista(opportunita: list, base: str = "rimini") -> Dict[str, Any]:
    """Applica ECC-001 a una lista e riporta anche l'imbuto degli scarti."""
    s = EccellenzaScorer(base=base)
    valutati, scartati = [], {}
    for o in opportunita:
        r = s.score(o)
        if r["valutabile"]:
            valutati.append({**o, "ecc_score": r["punteggio"],
                             "ecc_fascia": r["fascia"], "ecc_breakdown": r["breakdown"]})
        else:
            scartati[r["motivo"]] = scartati.get(r["motivo"], 0) + 1
    valutati.sort(key=lambda x: x["ecc_score"], reverse=True)
    return {"valutati": valutati, "scartati_per_motivo": scartati,
            "totale_esaminati": len(opportunita)}
