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
# Le voci sono RADICI, non nomi di comune: le societa' si chiamano come il
# paese ma declinato ("Savignanese" da Savignano), e cercare il nome esatto
# le manca tutte. "savignan" prende entrambi.
BACINI = {
    "rimini": {
        "vicino": ["rimini", "santarcangelo", "riccione", "cattolica", "bellaria",
                   "igea marina", "novafeltria", "verucchio", "coriano", "morciano",
                   "san marino", "sammaurese", "san mauro", "savignan", "gatteo",
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

    def __init__(self, base: str = "rimini", giorni_freschezza: int = 45,
                 finestra: str = "gennaio"):
        self.base = base
        # Quando riguardare chi oggi e' bloccato. Parametro e non costante:
        # le finestre di tesseramento dei dilettanti cambiano per stagione e
        # per comitato, e questo file non e' il posto dove asserirle.
        self.finestra = finestra
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
                return ("la fonte è un link che scade, fra un mese non si apre "
                        "più e non possiamo mostrarla a nessuno")
            return "nessuno ha aperto la sua scheda per controllare i dati"

        pres = opp.get("appearances")
        if not pres or int(pres) < 5:
            # La soglia nel testo, non il numero del singolo: cosi' gli scarti
            # si contano insieme (stessa ragione del blocco freschezza sotto).
            return "ha giocato meno di 5 partite, troppo poco per dirne qualcosa"

        eta = opp.get("age")
        if not eta:
            return "non sappiamo quanti anni ha"

        # Il ri-controllo puo' smentire la segnalazione: e' il suo mestiere.
        # "Svincolato" a marzo e tesserato oggi non e' un'opportunita', ed e'
        # meglio saperlo qui che dopo aver fatto la telefonata.
        # Tre stati: None = non lo sappiamo, "" = la pagina lo da' libero,
        # altrimenti e' il nome della squadra. Solo il terzo caso smentisce
        # una segnalazione di svincolo; il primo non prova niente e viene
        # gestito dalla freschezza, che senza conferma resta vecchia.
        stato = opp.get("club_attuale_verificato")
        tipo = (opp.get("opportunity_type") or "").lower()
        if stato == "RITIRATO":
            return "ha smesso di giocare"
        if stato and tipo in ("svincolato", "rescissione"):
            return f"oggi risulta tesserato per {stato}"

        giorni = self._giorni_dall_ultima_prova(opp)
        if giorni is not None and giorni > self.giorni_freschezza:
            # Il motivo e' la SOGLIA, non i giorni del singolo record: chi
            # aggrega gli scarti (valuta_lista) deve poterli contare insieme,
            # e "87 giorni" e "190 giorni" sono lo stesso problema.
            # "non lo controlliamo da" e non "la segnalazione ha": ora l'ancora
            # e' la data della verifica, e la frase deve dire cio' che misura.
            return (f"non lo controlliamo da più di {self.giorni_freschezza} "
                    f"giorni e può aver già firmato altrove")
        return None

    def _giorni_dall_ultima_prova(self, opp: Dict[str, Any]) -> Optional[int]:
        """
        Da quanto non guardiamo davvero questo giocatore.

        L'ancora e' `tm_verified_at`, non `refreshed_at`. Sembrano la stessa
        cosa e non lo sono: il ri-controllo scrive `refreshed_at` **sempre**
        (ci ha provato), ma rinnova `tm_verified_at` **solo se la pagina ha
        detto qualcosa sulla disponibilita'**. Usare `refreshed_at` farebbe
        passare per fresca una segnalazione di marzo su cui abbiamo solo
        bussato senza ricevere risposta — e il gate la accetterebbe su un
        presupposto falso.
        """
        raw = (opp.get("tm_verified_at") or opp.get("reported_date")
               or opp.get("discovered_at") or "")
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

    # ------------------------------------------------------------ spiegazione
    # Un numero non dice a nessuno perche' quel nome e' in cima. Chi legge non
    # e' un analista: e' un direttore sportivo con dieci minuti, o un allenatore
    # in macchina. Ogni componente qui diventa una frase che dice la
    # CONSEGUENZA, non la misura — "abita in zona" invece di "prossimita 100".
    def _frasi(self, opp: Dict[str, Any], b: Dict[str, int]) -> list:
        f = []

        if b["prossimita"] >= 100:
            f.append("Abita in zona e può venire ad allenarsi senza stravolgere la settimana.")
        elif b["prossimita"] >= 65:
            f.append("Sta a circa un'ora di macchina, fattibile ma va chiesto a lui.")
        else:
            f.append("Non risulta un legame con la zona: prima di tutto il resto, "
                     "va capito se verrebbe.")

        tipo = (opp.get("opportunity_type") or "").lower()
        if tipo == "svincolato":
            f.append("È svincolato, non c'è da trattare con nessun club.")
        elif tipo == "rescissione":
            f.append("Ha risolto il contratto, quindi è libero.")
        elif tipo == "scadenza":
            f.append("Va in scadenza: se ne può parlare, ma non subito.")
        elif tipo == "prestito":
            club = (opp.get("club_attuale_verificato") or "").strip()
            f.append(f"Servirebbe l'accordo del {club}." if club
                     else "Servirebbe l'accordo del club che lo tiene sotto contratto.")
        else:
            f.append("La situazione contrattuale non è chiara.")

        if b["sostenibilita"] >= 80:
            f.append("Economicamente alla portata.")
        elif b["sostenibilita"] >= 45:
            f.append("Costa più della media della categoria, da capire cosa chiede.")
        else:
            f.append("Ha un valore da categoria superiore: difficile che accetti.")

        if b["coerenza"] >= 100:
            f.append("Viene da un livello da cui si scende normalmente.")
        elif b["coerenza"] >= 55:
            f.append("Viene dai professionisti: la prima domanda da fargli è perché scenderebbe.")
        elif b["coerenza"] <= 20:
            f.append("Ha un passato di categoria molto alta, quasi certamente non è per noi.")

        eta = opp.get("age")
        if eta:
            e = int(eta)
            if e <= 20:
                f.append(f"Ha {e} anni: utile anche per le quote giovani.")
            elif e <= 28:
                f.append(f"Ha {e} anni, età da titolare.")
            elif e <= 32:
                f.append(f"Ha {e} anni: può reggere, ma è una scelta di esperienza.")
            else:
                f.append(f"Ha {e} anni: solo se serve uno che guidi lo spogliatoio.")
        return f

    # ------------------------------------------------------------ da seguire
    # Le componenti che a gennaio saranno le stesse di oggi. Dove abita, da
    # che livello viene e quanti anni ha non cambiano perche' passa il tempo;
    # l'essere sotto contratto o il chiedere troppo, si'.
    STABILI = ("prossimita", "coerenza", "eta")

    def _merito_stabile(self, b: Dict[str, int]) -> int:
        peso = sum(PESI[k] for k in self.STABILI)
        return int(round(sum(b[k] * PESI[k] for k in self.STABILI) / peso))

    def _freno_temporaneo(self, opp: Dict[str, Any], b: Dict[str, int]):
        """
        Cosa lo blocca **oggi** e potrebbe non bloccarlo a gennaio, o None.

        Due casi, entrambi reali:
      - e' legato a un club (prestito, contratto in scadenza): non e' una
        questione di merito, e' una data;
      - e' libero ma chiede da categoria superiore. A settembre dice no; dopo
        mesi da fermo la stessa persona risponde in un altro modo. Non e' un
        giudizio sul giocatore, e' come funziona il mercato dei dilettanti.
        """
        tipo = (opp.get("opportunity_type") or "").lower()
        if tipo == "prestito":
            club = (opp.get("club_attuale_verificato") or "").strip()
            return f"è sotto contratto con il {club}" if club else "è sotto contratto con un altro club"
        if tipo == "scadenza":
            return "ha un contratto ancora in corso"
        if b["sostenibilita"] <= 20:
            # senza "oggi": il chiamante scrive gia' "Oggi non e'
            # disponibile perche' {freno}" e usciva due volte
            return "il suo valore è ancora da categoria superiore"
        return None

    # ----------------------------------------------------------------- score
    def score(self, opp: Dict[str, Any]) -> Dict[str, Any]:
        motivo = self.perche_non_valutabile(opp)
        if motivo:
            return {"valutabile": False, "motivo": motivo,
                    "spiegazione": [f"Non lo proponiamo: {motivo}."],
                    "riassunto": f"Non lo proponiamo: {motivo}.",
                    "punteggio": None, "fascia": None, "breakdown": {}}

        b = {
            "prossimita": self._prossimita(opp),
            "disponibilita": self._disponibilita(opp),
            "sostenibilita": self._sostenibilita(opp),
            "coerenza": self._coerenza(opp),
            "eta": self._eta(opp),
        }
        punteggio = int(round(sum(b[k] * PESI[k] for k in PESI)))
        frasi = self._frasi(opp, b)

        # Quarta uscita: il giocatore va bene, non e' il momento. Senza questa
        # finiva in "fuori profilo" insieme a chi non va bene — e sono due cose
        # diverse: una si archivia, l'altra si mette in agenda.
        freno = self._freno_temporaneo(opp, b)
        merito = self._merito_stabile(b)
        rivedere_a = None
        if freno and merito >= 70:
            fascia = "da seguire"
            rivedere_a = self.finestra
            frasi.append(f"Oggi non è disponibile perché {freno}: "
                         f"se ne può riparlare a {self.finestra}.")
        else:
            fascia = ("da chiamare" if punteggio >= 75
                      else "da valutare" if punteggio >= 55
                      else "fuori profilo")

        return {"valutabile": True, "motivo": None, "punteggio": punteggio,
                "fascia": fascia, "breakdown": b,
                "merito_stabile": merito, "rivedere_a": rivedere_a,
                "spiegazione": frasi,
                # Una riga sola, da leggere ad alta voce al telefono.
                "riassunto": f"{fascia.capitalize()} ({punteggio}/100). " + " ".join(frasi)}


def valuta_lista(opportunita: list, base: str = "rimini") -> Dict[str, Any]:
    """Applica ECC-001 a una lista e riporta anche l'imbuto degli scarti."""
    s = EccellenzaScorer(base=base)
    valutati, scartati = [], {}
    for o in opportunita:
        r = s.score(o)
        if r["valutabile"]:
            valutati.append({**o, "ecc_score": r["punteggio"],
                             "ecc_fascia": r["fascia"], "ecc_breakdown": r["breakdown"],
                             "ecc_rivedere_a": r["rivedere_a"]})
        else:
            scartati[r["motivo"]] = scartati.get(r["motivo"], 0) + 1
    valutati.sort(key=lambda x: x["ecc_score"], reverse=True)
    da_seguire = [v for v in valutati if v["ecc_fascia"] == "da seguire"]
    return {"valutati": valutati, "scartati_per_motivo": scartati,
            "da_seguire": da_seguire, "totale_esaminati": len(opportunita)}
