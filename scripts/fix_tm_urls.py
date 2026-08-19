#!/usr/bin/env python3
"""
Bonifica i link Transfermarkt già nel database.

Un link che porta al giocatore sbagliato è peggio di nessun link: chi legge il
report clicca, vede un altro giocatore, e smette di fidarsi di tutto il resto.
Qui i link non validi vengono **rimossi**, non corretti — l'URL giusto lo
ritrova l'enrichment alla prossima passata, con la verifica ora attiva.

Di default non scrive niente.

    python scripts/fix_tm_urls.py            # report
    python scripts/fix_tm_urls.py --apply    # rimuove i link rotti
"""

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tm_url import clean, diagnose

DATA_FILE = Path("data/opportunities.json")
URL_CACHE = Path("data/tm_urls.json")
SNAPSHOT_DIR = Path("data/snapshots")

_URL_FIELDS = ("tm_url", "transfermarkt_url")


def _scrub(container: dict, player_name: str, reasons: Counter, bad: list) -> int:
    removed = 0
    for field in _URL_FIELDS:
        url = container.get(field)
        if not url:
            continue
        if clean(url, player_name):
            continue
        reason = diagnose(url, player_name)
        reasons[reason.split(":")[0]] += 1
        bad.append((player_name, reason, url))
        container[field] = None
        removed += 1
    return removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--file", default=str(DATA_FILE))
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"File non trovato: {path}")
        return 1
    opportunities = json.loads(path.read_text(encoding="utf-8"))

    reasons: Counter = Counter()
    bad: list = []
    total_urls = removed = 0

    for opp in opportunities:
        name = opp.get("player_name") or ""
        for container in (opp, opp.get("player_profile") or {}):
            total_urls += sum(1 for f in _URL_FIELDS if container.get(f))
            removed += _scrub(container, name, reasons, bad)

    print(f"URL Transfermarkt esaminati: {total_urls}")
    print(f"Da rimuovere: {removed} ({100 * removed / total_urls:.0f}%)\n" if total_urls
          else "Nessun URL da esaminare\n")
    for reason, n in reasons.most_common():
        print(f"  {n:4d}  {reason}")

    wrong_player = [b for b in bad if b[1].startswith("profilo di un altro")]
    if wrong_player:
        print(f"\nI più gravi — puntano a un'altra persona ({len(wrong_player)}):")
        for name, reason, url in wrong_player[:15]:
            print(f"  {str(name)[:26]:28s} {reason[:70]}")

    # La cache degli URL è permanente: un link sbagliato lì resta per sempre.
    cache_removed = 0
    cache = {}
    if URL_CACHE.exists():
        try:
            cache = json.loads(URL_CACHE.read_text(encoding="utf-8"))
        except ValueError:
            cache = {}
        keep = {k: v for k, v in cache.items() if clean(v, k)}
        cache_removed = len(cache) - len(keep)
        print(f"\nCache {URL_CACHE}: {len(cache)} voci, {cache_removed} da scartare")

    if not args.apply:
        print("\nDry-run: nessun file modificato. Aggiungi --apply per scrivere.")
        return 0

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    shutil.copy2(path, SNAPSHOT_DIR / f"pre_tmurl_fix_{stamp}.json")
    path.write_text(json.dumps(opportunities, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nScritto {path}")
    if cache:
        URL_CACHE.write_text(
            json.dumps({k: v for k, v in cache.items() if clean(v, k)},
                       ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Ripulita {URL_CACHE}")
    print("Ora rigenera la dashboard:  python scripts/generate_dashboard.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
