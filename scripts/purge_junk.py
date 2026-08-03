#!/usr/bin/env python3
"""
Purga le entry su cui non ha senso spendere.

Di default NON scrive niente: stampa cosa farebbe. Serve `--apply` per toccare
il database, e in quel caso viene salvato prima uno snapshot.

    python scripts/purge_junk.py                # report
    python scripts/purge_junk.py --apply        # rimuove la spazzatura
    python scripts/purge_junk.py --apply --drop-out-of-scope

`junk` (non è una persona) viene rimosso. `out_of_scope` (giocatore vero ma
fuori fascia Serie C) viene solo marcato: cancellarlo è una scelta di chi
gestisce il radar, non del filtro.
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.entity_gate import JUNK, OUT_OF_SCOPE, classify, find_particle_duplicates

DATA_FILE = Path("data/opportunities.json")
SNAPSHOT_DIR = Path("data/snapshots")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="scrive le modifiche")
    ap.add_argument("--drop-out-of-scope", action="store_true",
                    help="rimuove anche i giocatori fuori fascia (default: solo marcati)")
    ap.add_argument("--max-market-value", type=int, default=None,
                    help="cap valore di mercato in euro (default 5.000.000)")
    ap.add_argument("--file", default=str(DATA_FILE))
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"File non trovato: {path}")
        return 1
    opportunities = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(opportunities, list):
        print("Formato inatteso: attesa una lista di opportunità")
        return 1

    junk, out_of_scope, keep = [], [], []
    for opp in opportunities:
        verdict = classify(opp, max_market_value=args.max_market_value)
        if verdict.kind == JUNK:
            junk.append((opp, verdict.reason))
        elif verdict.kind == OUT_OF_SCOPE:
            out_of_scope.append((opp, verdict.reason))
        else:
            keep.append(opp)

    dupes = find_particle_duplicates([o.get("player_name") for o in opportunities])

    print(f"Analizzate {len(opportunities)} entry\n")
    if junk:
        print(f"SPAZZATURA — da rimuovere ({len(junk)}):")
        for opp, reason in junk:
            enriched = "già arricchita" if opp.get("tm_enriched") else "mai arricchita"
            print(f"  - {str(opp.get('player_name'))[:38]:40s} {reason} [{enriched}]")
    if out_of_scope:
        action = "da rimuovere" if args.drop_out_of_scope else "solo marcati"
        print(f"\nFUORI SCOPO — {action} ({len(out_of_scope)}):")
        for opp, reason in out_of_scope:
            print(f"  - {str(opp.get('player_name'))[:38]:40s} {reason}")
    if dupes:
        print(f"\nDUPLICATI da preposizione ({len(dupes)}):")
        for artifact, canonical in dupes.items():
            print(f"  - '{artifact}' → probabile duplicato di '{canonical}'")

    removed = [o for o, _ in junk]
    if args.drop_out_of_scope:
        removed += [o for o, _ in out_of_scope]
    else:
        # Solo marcatura: a bloccare la spesa ci pensa già il gate, che li
        # riclassifica out_of_scope a ogni passaggio. Il flag serve alla
        # dashboard e a chi deve decidere se tenerli.
        for opp, reason in out_of_scope:
            opp["out_of_scope"] = True
            opp["out_of_scope_reason"] = reason
        keep += [o for o, _ in out_of_scope]

    # Risparmio: ogni entry rimossa avrebbe consumato ricerca + fetch + LLM a
    # ogni ciclo di refresh, per sempre.
    print(f"\nRimarrebbero {len(keep)} entry ({len(removed)} rimosse)")
    print(f"Spesa evitata: ~{len(removed) * 26} operazioni/anno "
          f"(refresh ogni 14 giorni per entry)")

    if not args.apply:
        print("\nDry-run: nessun file modificato. Aggiungi --apply per scrivere.")
        return 0

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    snapshot = SNAPSHOT_DIR / f"pre_purge_{stamp}.json"
    shutil.copy2(path, snapshot)
    print(f"\nSnapshot: {snapshot}")

    keep.sort(key=lambda o: str(o.get("player_name") or ""))
    path.write_text(json.dumps(keep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Scritto {path} ({len(keep)} entry)")
    # docs/data.json NON si tocca qui: ha il formato dashboard (dict con
    # opportunities/stats/quality_gate), non la lista grezza. Va rigenerato.
    print("\nOra rigenera la dashboard:  python scripts/generate_dashboard.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
