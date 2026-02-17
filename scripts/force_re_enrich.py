#!/usr/bin/env python3
"""
Force Re-Enrichment Utility
Riesegue l'enrichment TM per i giocatori esistenti che mancano dei nuovi campi:
agent, appearances, goals, assists, minutes_played
"""

import sys, os, json, time
from pathlib import Path
from io import TextIOWrapper

# Force UTF-8 output
sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

sys.path.append(str(Path(__file__).parent.parent))
from src.enricher_tm import TransfermarktEnricher

DATA_FILE = Path("data/opportunities.json")
NEW_FIELDS = ["agent", "appearances", "goals", "assists", "minutes_played"]


def backup_data():
    """Crea backup del file data before modifica"""
    backup_path = DATA_FILE.parent / "opportunities_backup_pre_reenrich.json"
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] Backup creato: {backup_path}")
    return backup_path


def is_player_complete(player):
    """Verifica se il giocatore ha tutti i nuovi campi popolati"""
    for field in NEW_FIELDS:
        if player.get(field) is None:
            return False
    return True


def merge_new_fields(existing_player, new_tm_data):
    """Aggiorna SOLO i nuovi campi senza sovrascrivere dati esistenti"""
    updated = False
    for field in NEW_FIELDS:
        if field in new_tm_data and new_tm_data[field] is not None:
            if existing_player.get(field) != new_tm_data[field]:
                existing_player[field] = new_tm_data[field]
                updated = True
    return updated


def main():
    print("=" * 60)
    print("FORCE RE-ENRICHMENT - Nuovi campi Transfermarkt")
    print("=" * 60)

    if not DATA_FILE.exists():
        print(f"[ERROR] File {DATA_FILE} non trovato!")
        return

    backup_data()

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    opportunities = data if isinstance(data, list) else data.get("opportunities", [])
    print(f"Trovate {len(opportunities)} opportunità.")

    enricher = TransfermarktEnricher()

    total_processed = 0
    total_updated = 0
    total_skipped_no_tm = 0
    total_skipped_complete = 0
    total_errors = 0

    new_fields_populated = {field: 0 for field in NEW_FIELDS}

    for i, opp in enumerate(opportunities):
        player_name = opp.get("player_name")
        tm_url = opp.get("tm_url")

        if not tm_url:
            total_skipped_no_tm += 1
            continue

        if is_player_complete(opp):
            total_skipped_complete += 1
            continue

        total_processed += 1
        print(f"\n[{total_processed}] Re-enriching: {player_name}")

        try:
            tm_data = enricher.enrich_player(player_name)

            if not tm_data:
                print("  [WARN] Nessun dato trovato")
                total_errors += 1
                continue

            updated = merge_new_fields(opp, tm_data)

            if updated:
                total_updated += 1
                print(
                    f"  [OK] Aggiornati {sum(1 for f in NEW_FIELDS if opp.get(f) is not None)} campi"
                )

                for field in NEW_FIELDS:
                    if opp.get(field) is not None:
                        new_fields_populated[field] += 1
            else:
                print(
                    "  [WARN] Nessun campo aggiornato (dati già presenti o non trovati)"
                )

            if total_updated % 5 == 0:
                with open(DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print("  [SAVE] Salvataggio progressivo...")

            time.sleep(3)

        except Exception as e:
            print(f"  [ERROR] Errore: {e}")
            total_errors += 1

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("[SUMMARY]")
    print("=" * 60)
    print(f"Totale giocatori processati: {total_processed}")
    print(f"Giocatori aggiornati: {total_updated}")
    print(f"Saltati (no tm_url): {total_skipped_no_tm}")
    print(f"Saltati (già completi): {total_skipped_complete}")
    print(f"Errori: {total_errors}")
    print("\nNuovi campi popolati:")
    for field, count in new_fields_populated.items():
        print(f"  - {field}: {count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
