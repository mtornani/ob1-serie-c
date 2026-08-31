#!/usr/bin/env python3
"""
OB1 Lega Pro — Grafo delle fonti: cosa sappiamo, da chi, e chi vince quando
litigano.

Da dove viene
-------------
Portato da OuroborosCouncil (`discovery_engine.record_observation` /
`resolve_field`), gemello di `src/piramide_v2.py` su OB1 Global. Stessa
forma di proposito: è la stessa idea, e vederla uguale nei due prodotti vale
più che adattarla a ciascuno.

Il problema che risolve, misurato qui
-------------------------------------
Su questo prodotto i valori arrivano da due bocche diverse — la discovery
(stampa/ricerca, fresca) e l'arricchimento Transfermarkt (consolidato) — e
nessuno dei due punti sa cosa ha detto l'altro. Misurato il 31 ago 2026, in
`scripts/run_enrichment.py`, i due errori sono SPECULARI:

    current_club   `opp[key] = tm[key]` — Transfermarkt sovrascrive sempre.
                   Ma il club è un fatto VELOCE, e la scheda TM non dice a
                   quando si riferisce: qui dovrebbe vincere la notizia
                   datata, non l'archivio.

    age            `if not opp.get('age')` — vince il primo arrivato, e la
                   data di nascita che TM porta viene ignorata. Ma l'età è un
                   fatto LENTO: qui dovrebbe vincere proprio l'archivio.

Due campi, due errori, in direzioni opposte — che è esattamente il sintomo di
una piramide letta in un verso solo. Non è un caso che sul repo gemello
(OB1 Global) il difetto fosse lo stesso in una forma diversa:
`age = COALESCE(age, ?)`, il primo arrivato vince per sempre.

Le tre regole
-------------
1. **La conferma umana batte tutto.** Livello 0, oggi vuoto: nessun canale
   la produce. È dichiarato apposta invece che omesso — quando un direttore
   sportivo dirà "no, quello ormai è al Cesena", quel giudizio deve avere un
   posto dove atterrare sopra qualunque scraper.

2. **Se le fonti concordano, vince il valore condiviso.** Non c'è lite.

3. **In disaccordo, il verso dipende dal campo** (vedi REGOLE_CAMPO).

Puro: nessuna rete, nessun database, nessun file. Il grafo è un dict che
passa il chiamante.

Test: python3 -m src.piramide
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

# Livello 0 = la voce umana. Vuoto oggi, dichiarato apposta (vedi regola 1).
UMANO = "umano"

# Dai `type` di config/sources.json a una posizione sull'asse
# fresco -> consolidato. Chi non è qui dentro non entra nel grafo: mai un
# livello indovinato, che è la stessa regola di "mai un numero inventato".
LIVELLI: Dict[str, int] = {
    UMANO: 0,
    # cronaca: quello che la discovery trova in giro, la cosa più fresca
    "news": 2,
    # anagrafica consolidata: lenta sul presente, solida sull'identità
    "transfermarkt": 4,
}

# Come si legge la piramide, campo per campo.
REGOLE_CAMPO: Dict[str, str] = {
    "club": "dal_basso",              # fatto veloce: un trasferimento
    "eta": "dall_alto",               # fatto lento: una data di nascita
    "contract_expires": "dall_alto",  # sta sul contratto, non nella notizia
    "market_value": "dall_alto",      # è una stima di TM, non un fatto di cronaca
    "role": "dal_basso",
}
REGOLA_DI_DEFAULT = "dal_basso"

# Quante osservazioni per campo si tengono. Serve solo a non far crescere il
# grafo senza fine su un giocatore molto citato: le più vecchie della stessa
# fonte non aggiungono niente, perché la risoluzione guarda l'ULTIMA di
# ciascuna fonte.
MAX_OSSERVAZIONI_PER_CAMPO = 24


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def registra(grafo: dict, chiave: str, campo: str, valore, fonte: str,
             datato_al: str = "", url: str = "", nota: str = "") -> bool:
    """
    Aggiunge un'osservazione al grafo (in memoria). True se il grafo cambia.

    `fonte` è un TIPO del registro (federation, aggregator, ...), non un
    dominio: la piramide ragiona per genere di fonte, e due giornali diversi
    stanno allo stesso livello.

    Dedup: se l'ultima osservazione della STESSA fonte porta lo stesso
    valore è una conferma, non una riga nuova — si aggiorna quando l'abbiamo
    vista e basta. Se porta un valore diverso, è una riga nuova: il
    cambiamento è il dato.
    """
    valore = str(valore).strip() if valore is not None else ""
    if not valore or not chiave or fonte not in LIVELLI:
        return False
    osservazioni = grafo.setdefault(chiave, {}).setdefault(campo, [])
    adesso = _ora()
    for obs in reversed(osservazioni):
        if obs["fonte"] != fonte:
            continue
        if obs["valore"] == valore:
            obs["osservato_il"] = adesso
            if datato_al and not obs.get("datato_al"):
                obs["datato_al"] = datato_al
            return True
        break                      # l'ultima della stessa fonte dice altro
    voce = {"valore": valore, "fonte": fonte, "osservato_il": adesso}
    for k, v in (("datato_al", datato_al), ("url", url), ("nota", nota)):
        if v:
            voce[k] = v
    osservazioni.append(voce)
    del osservazioni[:-MAX_OSSERVAZIONI_PER_CAMPO]
    return True


def _ts(obs: dict, chiave: str = "osservato_il") -> str:
    return obs.get(chiave) or ""


def risolvi(grafo: dict, chiave: str, campo: str,
            ripiego=None, oggi: Optional[datetime] = None) -> Optional[dict]:
    """
    Il valore corrente di un campo secondo il grafo, con la spiegazione.
    Deterministico: stesse osservazioni, stessa risposta.

    `ripiego` è il valore che il chiamante ha già fuori dal grafo (la
    colonna in tabella): usato SOLO se il grafo non sa nulla, e dichiarato
    come tale nella spiegazione — così non si confonde "lo dice una fonte"
    con "ce l'avevamo scritto".

    Ritorna None quando non c'è né grafo né ripiego: l'assenza resta
    un'assenza, non diventa un valore.
    """
    osservazioni = (grafo.get(chiave) or {}).get(campo) or []
    if not osservazioni:
        if ripiego in (None, ""):
            return None
        return {"valore": ripiego, "fonte": None, "livello": None,
                "spiegazione": "valore di partenza, nessuna fonte lo osserva",
                "conflitto": False, "alternativa": None,
                "alternativa_fonte": None, "datato_al": "", "url": ""}

    # L'ultima osservazione di ciascuna fonte: le precedenti della stessa
    # fonte sono storia, non voci in più.
    per_fonte = {}
    for obs in osservazioni:
        per_fonte[obs["fonte"]] = obs
    voci = list(per_fonte.values())

    def esito(migliore: dict, spiegazione: str, conflitto: bool) -> dict:
        altre = sorted([o for o in voci if o["valore"] != migliore["valore"]],
                       key=_ts, reverse=True)
        return {
            "valore": migliore["valore"],
            "fonte": migliore["fonte"],
            "livello": LIVELLI.get(migliore["fonte"]),
            "datato_al": migliore.get("datato_al", ""),
            "url": migliore.get("url", ""),
            "spiegazione": spiegazione,
            "conflitto": conflitto,
            "alternativa": altre[0]["valore"] if altre else None,
            "alternativa_fonte": altre[0]["fonte"] if altre else None,
        }

    # 1. la voce umana batte tutto
    umane = [o for o in voci if LIVELLI.get(o["fonte"]) == 0]
    if umane:
        migliore = max(umane, key=_ts)
        discordi = any(o["valore"] != migliore["valore"] for o in voci)
        return esito(migliore,
                     f"confermato a mano il {migliore['osservato_il'][:10]}",
                     discordi)

    # 2. accordo pieno
    if len({o["valore"] for o in voci}) == 1:
        migliore = max(voci, key=_ts)
        spiegazione = (f"{len(voci)} fonti concordano" if len(voci) > 1
                       else f"unica fonte: {migliore['fonte']}")
        return esito(migliore, spiegazione, False)

    # 3. disaccordo: il verso dipende dal campo
    if REGOLE_CAMPO.get(campo, REGOLA_DI_DEFAULT) == "dall_alto":
        migliore = max(voci, key=lambda o: (LIVELLI.get(o["fonte"], -1), _ts(o)))
        return esito(migliore,
                     f"\"{migliore['valore']}\" secondo {migliore['fonte']} — "
                     f"su questo campo la fonte consolidata batte quella fresca",
                     True)

    datate = [o for o in voci if o.get("datato_al")]
    if datate:
        migliore = max(datate, key=lambda o: _ts(o, "datato_al"))
        return esito(migliore,
                     f"\"{migliore['valore']}\" secondo {migliore['fonte']} "
                     f"(datato {migliore['datato_al'][:10]}) — un'osservazione "
                     f"con una data batte un valore senza data",
                     True)
    migliore = min(voci, key=lambda o: (LIVELLI.get(o["fonte"], 9), _inverso(_ts(o))))
    return esito(migliore,
                 f"\"{migliore['valore']}\" secondo {migliore['fonte']} — nessuna "
                 f"fonte porta una data, vince quella più vicina al campo",
                 True)


def _inverso(iso: str) -> float:
    """Chiave d'ordinamento per "il più recente vince" dentro un min():
    timestamp negato. Una data assente o malformata torna 0.0, che è
    maggiore di ogni timestamp negato valido — quindi perde contro
    qualunque osservazione ben datata, e non solleva mai."""
    try:
        return -datetime.fromisoformat(iso).timestamp()
    except (ValueError, TypeError):
        return 0.0


def conflitti(grafo: dict, chiave: str,
              campi: Sequence[str] = ("club", "eta")) -> List[dict]:
    """I campi su cui le fonti non vanno d'accordo, già risolti. Serve a
    misurare quanto litigano prima di lasciar decidere il grafo, e a
    mostrarlo: un conflitto dichiarato vale più di uno risolto in silenzio."""
    fuori = []
    for campo in campi:
        r = risolvi(grafo, chiave, campo)
        if r and r["conflitto"]:
            fuori.append(dict(r, campo=campo))
    return fuori


# --------------------------------------------------------------- test

def _test() -> None:
    # I due casi veri di questo prodotto, presi da run_enrichment.py.

    # 1. CLUB — fatto veloce. La notizia datata batte la scheda TM, che non
    #    dice a quando si riferisce. Oggi il codice fa l'opposto:
    #    `opp['current_club'] = tm['current_club']`, sempre.
    G = {}
    assert registra(G, "p", "club", "Cesena FC", "transfermarkt")
    assert registra(G, "p", "club", "Virtus Entella", "news", datato_al="2026-08-28")
    r = risolvi(G, "p", "club")
    assert r["valore"] == "Virtus Entella", r
    assert r["conflitto"] and r["alternativa"] == "Cesena FC"
    assert "datato 2026-08-28" in r["spiegazione"], r["spiegazione"]

    # 2. ETA — fatto lento, stesso disaccordo, verso OPPOSTO. Vince
    #    l'anagrafica. Oggi il codice tiene il primo arrivato e butta la data
    #    di nascita che TM ha portato.
    G2 = {}
    assert registra(G2, "p", "eta", "22", "news", datato_al="2026-08-28")
    assert registra(G2, "p", "eta", "24", "transfermarkt")
    r = risolvi(G2, "p", "eta")
    assert r["valore"] == "24", r
    assert "consolidata batte quella fresca" in r["spiegazione"]
    assert r["conflitto"] and r["alternativa"] == "22"
    #    Due campi, due errori speculari: è il sintomo di una piramide letta
    #    in un verso solo.

    # 3. Il direttore sportivo batte tutti e due.
    assert registra(G2, "p", "eta", "23", UMANO)
    r = risolvi(G2, "p", "eta")
    assert r["valore"] == "23" and "confermato a mano" in r["spiegazione"]
    assert r["conflitto"], "se l'umano smentisce, il conflitto resta detto"

    # 4. Stessa fonte, stesso valore: conferma, non riga nuova.
    G3 = {}
    registra(G3, "p", "club", "AC Prato", "news")
    registra(G3, "p", "club", "AC Prato", "news")
    assert len(G3["p"]["club"]) == 1
    #    Valore diverso dalla stessa fonte: riga nuova, il cambiamento è il dato.
    registra(G3, "p", "club", "US Triestina", "news")
    assert len(G3["p"]["club"]) == 2

    # 5. Accordo pieno: nessun conflitto da dichiarare.
    G4 = {}
    registra(G4, "p", "club", "Sorrento 1945", "news")
    registra(G4, "p", "club", "Sorrento 1945", "transfermarkt")
    r = risolvi(G4, "p", "club")
    assert not r["conflitto"] and r["spiegazione"] == "2 fonti concordano"

    # 6. Una fonte non censita non entra: mai un livello indovinato. Vale
    #    anche per il redirect di grounding, che non è una fonte (vedi
    #    quality_gate.e_redirect_di_ricerca).
    assert not registra(G4, "p", "club", "Chissà", "gemini_search")
    assert len(G4["p"]["club"]) == 2

    # 7. Grafo vuoto: il ripiego si usa ma si dichiara tale.
    r = risolvi({}, "ignoto", "club", ripiego="Club nel record")
    assert r["valore"] == "Club nel record" and r["fonte"] is None
    assert "nessuna fonte lo osserva" in r["spiegazione"]
    assert risolvi({}, "ignoto", "club") is None

    # 8. Valori vuoti non entrano.
    assert not registra(G4, "p", "club", "", "news")
    assert not registra(G4, "p", "club", None, "news")

    # 9. I conflitti si chiedono tutti insieme, per misurarli prima di
    #    lasciar decidere il grafo.
    assert [c["campo"] for c in conflitti(G2, "p", campi=("club", "eta"))] == ["eta"]

    # 10. Un timestamp malformato non fa saltare la risoluzione.
    G5 = {}
    registra(G5, "p", "club", "A", "news")
    registra(G5, "p", "club", "B", "transfermarkt")
    G5["p"]["club"][0]["osservato_il"] = "non-una-data"
    assert risolvi(G5, "p", "club") is not None

    print("piramide: ok")


if __name__ == "__main__":
    _test()
