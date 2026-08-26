#!/usr/bin/env python3
"""
Apre ogni profilo Transfermarkt del database e guarda di chi è davvero.

Perché serve uno script e non basta il filtro sintattico
-------------------------------------------------------
`src/tm_url.py` scarta gli ID palesemente costruiti (tondi: 939000,
1000000). Ne ha tolti 188 su 525. Ma un ID inventato che *sembra* vero non
lo prende nessuna regola sulla forma del numero — e la prima misura dal
vivo, 26 ago 2026 sui link sopravvissuti al filtro, dice quanto conta:

    12 link controllati aprendo la pagina
     3 confermati
     6 di UN'ALTRA PERSONA        <- meta' dei link verificabili
     3 non verificabili al momento

    Rizzo Pinna            -> Emre Dalgalidere
    Achraf El Bouchataoui  -> Tomaso Lorenzi
    Antonis Siatounis      -> Tokia Russell
    Francesco Pio Petito   -> Vladislav Sutin
    Christian Dimarco      -> Lucas Russo

Un direttore sportivo che apre uno di quei link vede la scheda di un altro
essere umano, sotto il nostro bollino.

Cosa fa
-------
Per ogni giocatore col link: apre il profilo via Jina Reader, confronta il
nome, e a seconda dell'esito

    combacia        scrive tm_verified_at (data_verified diventa vero) e
                    porta a bordo data di nascita e SQUADRA ATTUALE dalla
                    pagina — cioe' eta' dichiarata e staleness risolta
    non combacia    RIMUOVE il link. Meglio nessun link che un link a
                    un'altra persona: e' la regola dichiarata in cima a
                    src/tm_url.py, qui applicata a un caso che quel file
                    non poteva vedere
    non verificabile lascia tutto com'e' e NON scrive tm_verified_at:
                    "non lo so" resta diverso da "non combacia"

Di default non scrive niente.

    python scripts/verify_tm_links.py              # rapporto
    python scripts/verify_tm_links.py --apply      # scrive
    python scripts/verify_tm_links.py --limit 20   # solo i primi N
"""

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tm_verify import VerificatoreTM

DATI = Path("data/opportunities.json")
SNAPSHOT = Path("data/snapshots")
CAMPI_URL = ("tm_url", "transfermarkt_url")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--file", default=str(DATI))
    args = ap.parse_args()

    percorso = Path(args.file)
    if not percorso.exists():
        print(f"File non trovato: {percorso}")
        return 1
    opportunita = json.loads(percorso.read_text(encoding="utf-8"))

    v = VerificatoreTM()
    esiti = Counter()
    smascherati, aggiornati = [], []

    da_fare = [o for o in opportunita if any(o.get(c) for c in CAMPI_URL)]
    if args.limit:
        da_fare = da_fare[:args.limit]
    print(f"Profili da aprire: {len(da_fare)}\n")

    for o in da_fare:
        nome = o.get("player_name") or ""
        url = next((o.get(c) for c in CAMPI_URL if o.get(c)), "")
        r = v.verifica(nome, url)

        if r is None:
            esiti["non verificabile"] += 1
            continue

        if not r.combacia:
            esiti["ID DI UN'ALTRA PERSONA"] += 1
            smascherati.append((nome, r.nome_sul_profilo))
            for c in CAMPI_URL:
                if o.get(c):
                    o[c] = None
            o.pop("tm_verified_at", None)
            continue

        esiti["verificato"] += 1
        o["tm_verified_at"] = r.verificato_il
        cambi = []
        # La squadra letta sul profilo e' il dato piu' fresco che abbiamo:
        # in dashboard "Rizzo Pinna" risultava all'Ascoli da marzo, il
        # profilo dice Union Brescia. La segnalazione era morta.
        if r.squadra and r.squadra != o.get("current_club"):
            cambi.append(f"club {o.get('current_club')!r} -> {r.squadra!r}")
            o["current_club"] = r.squadra
        eta = r.eta()
        if eta is not None and eta != o.get("age"):
            cambi.append(f"eta {o.get('age')} -> {eta}")
            o["age"] = eta
        if r.data_nascita:
            o["birth_date"] = r.data_nascita
        if r.contratto_fino and r.contratto_fino != o.get("contract_expires"):
            cambi.append(f"contratto -> {r.contratto_fino}")
            o["contract_expires"] = r.contratto_fino
        if cambi:
            aggiornati.append((nome, "; ".join(cambi)))

    print("=== esito ===")
    for k, n in esiti.most_common():
        print(f"  {n:4d}  {k}")
    print(f"\n  {v.riepilogo()}")

    if smascherati:
        print(f"\n=== link che portavano a un'ALTRA persona ({len(smascherati)}) ===")
        for nome, altro in smascherati:
            print(f"  {nome[:30]:32s} -> {altro}")

    if aggiornati:
        print(f"\n=== dati corretti dal profilo vero ({len(aggiornati)}) ===")
        for nome, cambio in aggiornati[:25]:
            print(f"  {nome[:30]:32s} {cambio}")

    if not args.apply:
        print("\nDry-run: nessun file modificato. Aggiungi --apply per scrivere.")
        return 0

    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    stampo = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    shutil.copy2(percorso, SNAPSHOT / f"pre_tmverify_{stampo}.json")
    percorso.write_text(json.dumps(opportunita, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\nScritto {percorso}")
    print("Ora rigenera la dashboard:  python scripts/generate_dashboard.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
