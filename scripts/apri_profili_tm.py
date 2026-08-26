#!/usr/bin/env python3
"""
Cerca il profilo Transfermarkt dei giocatori che non ne hanno uno aperto, lo
apre, e porta a bordo quello che c'è scritto.

Perché serve
------------
Dal 26 ago 2026 età, piede, procuratore, presenze e gol si pubblicano solo se
qualcuno ha aperto la scheda (`src/provenienza.py`). Prima uscivano lo stesso,
presi da un LLM a cui chiedevamo "cerca su Transfermarkt e dimmi i gol": su
143 procuratori a schermo, 132 non venivano da nessuna pagina.

Quella regola da sola però svuota il prodotto: applicata al database del 26
agosto porta le schede pubblicabili da 66 a 28. È giusto — le 38 uscite sono
in buona parte gli stessi nomi il cui link portava a un'altra persona — ma è
metà del lavoro. L'altra metà è questa: riempire di nuovo, leggendo davvero.

E `scripts/run_enrichment.py` non può farlo. Salta chi ha già `tm_enriched`,
cioè esattamente i ~377 record riempiti dall'LLM: per lui sono fatti, e non
li ripassa mai più. Questo script guarda l'altro flag — `tm_verified_at`, che
scrive solo chi la pagina l'ha aperta.

Come
----
Nessun LLM. Per ogni giocatore senza profilo aperto:

    1. la ricerca INTERNA di Transfermarkt (via Jina Reader) propone i
       candidati — l'indice di TM stesso, non un motore generico
    2. si aprono uno alla volta finché il nome sulla pagina combacia
    3. dal profilo giusto si prendono data di nascita, squadra, ruolo,
       piede, scadenza e procuratore, e si scrive `tm_verified_at`

Se nessun candidato combacia non si scrive niente: "non lo so" resta diverso
da "ecco il dato".

    python scripts/apri_profili_tm.py                # rapporto, non scrive
    python scripts/apri_profili_tm.py --apply        # scrive
    python scripts/apri_profili_tm.py --limit 30     # tetto per questo giro
"""

import argparse
import json
import os
import shutil
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tm_verify import VerificatoreTM, cerca_profili, nomi_combaciano_forte
from src.entity_gate import classify

DATI = Path("data/opportunities.json")
SNAPSHOT = Path("data/snapshots")

# Quanti nomi per run. Ogni nome costa 1 ricerca + 1..N aperture di pagina su
# Jina; il tetto keyless è 20 richieste al minuto, con JINA_API_KEY 200. Il
# backlog si smaltisce su più run invece di sbattere contro il limite in una
# volta sola — stesso criterio di MAX_ENRICH_BATCHES.
TETTO = int(os.getenv("MAX_TM_PROFILI", "25"))

# Jina Reader: 20 richieste al minuto senza chiave, 200 con. Ogni nome ne
# costa almeno due (la ricerca, poi l'apertura del profilo), quindi senza
# chiave si può fare un nome ogni ~7 secondi.
#
# Non è un dettaglio di cortesia: superando il tetto la risposta torna vuota,
# e una risposta vuota qui si legge come "questo giocatore non esiste su
# Transfermarkt". Misurato il 26 ago 2026, correndo senza pause su 90 nomi:
# 61 risultavano introvabili, ma rifacendo le stesse ricerche distanziate il
# profilo usciva al primo colpo. Il limite di un servizio stava diventando un
# fatto sul giocatore — la stessa specie di errore silenzioso che tutto questo
# lavoro serve a togliere.
PAUSA = float(os.getenv("TM_PAUSA_SEC", "0" if os.getenv("JINA_API_KEY") else "7"))


def _serve(o: dict) -> bool:
    """Vale la pena cercare il profilo di questo record?"""
    if o.get("tm_verified_at"):
        return False                      # già aperto
    if o.get("out_of_scope"):
        return False
    return classify(o).spend_allowed      # stesso gate di discovery/enrichment


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=TETTO)
    ap.add_argument("--file", default=str(DATI))
    args = ap.parse_args()

    percorso = Path(args.file)
    if not percorso.exists():
        print(f"File non trovato: {percorso}")
        return 1
    opportunita = json.loads(percorso.read_text(encoding="utf-8"))

    da_fare = [o for o in opportunita if _serve(o)]
    # Prima chi è più vicino a essere pubblicabile: senza età il gate lo
    # blocca comunque, quindi è lì che un profilo aperto rende di più.
    da_fare.sort(key=lambda o: (
        0 if o.get("age") in (None, "") else 1,
        -(o.get("ob1_score") or 0),
        o.get("player_name") or "",
    ))
    coda = len(da_fare)
    if args.limit:
        da_fare = da_fare[:args.limit]
    print(f"Senza profilo aperto: {coda}. Ne provo {len(da_fare)} in questo giro.\n")

    v = VerificatoreTM()
    esiti = Counter()
    trovati = []

    for i, o in enumerate(da_fare):
        nome = (o.get("player_name") or "").strip()
        if not nome:
            continue
        if i and PAUSA:
            time.sleep(PAUSA)
        candidati = cerca_profili(nome)
        if not candidati:
            esiti["la ricerca non ha proposto niente"] += 1
            continue

        # Adottare un profilo trovato in ricerca chiede più prova che togliere
        # un link già presente: qui il candidato lo ha proposto un motore per
        # somiglianza, e un cognome uguale non è un'identità. Vedi
        # nomi_combaciano_forte in src/tm_verify.py.
        vinti = []
        for url in candidati:
            r = v.verifica(nome, url)
            if r is None:
                continue
            if r.combacia and nomi_combaciano_forte(nome, r.nome_sul_profilo):
                vinti.append((url, r))

        if not vinti:
            esiti[f"nessuno dei candidati era lui"] += 1
            continue
        if len(vinti) > 1:
            # Due profili col nome giusto: sono omonimi, e sceglierne uno
            # sarebbe tirare a indovinare davanti a un direttore sportivo.
            esiti["omonimi: non si sceglie"] += 1
            print(f"  [OMONIMI] {nome}: "
                  + " | ".join(f"{r.nome_sul_profilo} ({r.data_nascita})"
                               for _u, r in vinti))
            continue
        vinto = vinti[0]

        url, r = vinto
        esiti["profilo trovato e aperto"] += 1
        scritti = []
        o["tm_url"] = url
        o["tm_verified_at"] = r.verificato_il
        if r.data_nascita:
            o["birth_date"] = r.data_nascita
            scritti.append(f"nato {r.data_nascita}")
        eta = r.eta()
        if eta is not None:
            o["age"] = eta
            scritti.append(f"{eta} anni")
        if r.squadra:
            o["current_club"] = r.squadra
            scritti.append(r.squadra)
        if r.ruolo:
            o["role_name"] = r.ruolo
        if r.piede:
            o["foot"] = r.piede
        if r.contratto_fino:
            o["contract_expires"] = r.contratto_fino
            scritti.append(f"contratto {r.contratto_fino}")
        if r.procuratore:
            o["agent"] = r.procuratore
            scritti.append(f"ag. {r.procuratore}")
        # Il valore letto dalla pagina riaccende il gate "fuori fascia Serie C"
        # (src/entity_gate.py, cap 5 mln), che esisteva già ed era giusto ma
        # riceveva un numero inventato da un modello — quindi quasi sempre
        # None, quindi non scattava. Senza, in dashboard finiva Nico Paz (80
        # mln, Como) come opportunità di Lega Pro.
        if r.valore_eur is not None:
            o["market_value"] = r.valore_eur
            o["market_value_eur"] = r.valore_eur
            scritti.append(f"valore {r.valore_eur/1e6:.1f} mln")
        if r.ritirato:
            o["out_of_scope"] = True
            o["out_of_scope_reason"] = "ha smesso di giocare (Transfermarkt: Ritiro)"
            scritti.append("RITIRATO")
        trovati.append((nome, "; ".join(scritti)))

    print("=== esito ===")
    for k, n in esiti.most_common():
        print(f"  {n:4d}  {k}")
    print(f"\n  {v.riepilogo()}")

    if trovati:
        print(f"\n=== profili aperti ({len(trovati)}) ===")
        for nome, cosa in trovati[:40]:
            print(f"  {nome[:30]:32s} {cosa}")

    restano = coda - esiti["profilo trovato e aperto"]
    print(f"\nRestano senza profilo aperto: {restano}")

    if not args.apply:
        print("Dry-run: nessun file modificato. Aggiungi --apply per scrivere.")
        return 0

    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    stampo = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    shutil.copy2(percorso, SNAPSHOT / f"pre_apriprofili_{stampo}.json")
    percorso.write_text(json.dumps(opportunita, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"Scritto {percorso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
