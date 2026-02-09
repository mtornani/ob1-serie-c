#!/usr/bin/env python3
import sys, os, json, time
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from src.enricher_tm import TransfermarktEnricher
DATA_FILE = Path("data/opportunities.json")
DATA_FILE_DOCS = Path("docs/data.json")
MAX_RETRIES = 3
RETRY_DELAY = 3
RATE_LIMIT_DELAY = 5
def save_progress(data, opportunities, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(opportunities if isinstance(data, list) else data, f, ensure_ascii=False, indent=2)
def enrich_with_retry(enricher, player_name):
    for attempt in range(MAX_RETRIES):
        try:
            tm_data = enricher.enrich_player(player_name)
            return tm_data if tm_data else None
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  ⚠️ Errore: {e}")
                time.sleep(RETRY_DELAY)
            else:
                raise e
def main():
    if not DATA_FILE.exists():
        print(f"File {DATA_FILE} non trovato!")
        return
    print(f"Loading {DATA_FILE}...")
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    opportunities = data if isinstance(data, list) else data.get('opportunities', [])
    print(f"Trovate {len(opportunities)} opportunità.")
    enricher = TransfermarktEnricher()
    updated_count = 0
    errors = 0
    skipped = 0
    for i, opp in enumerate(opportunities):
        player_name = opp.get('player_name')
        profile = opp.get('player_profile', {}) or {}
        if profile.get('market_value') or opp.get('tm_enriched', False):
            skipped += 1
            continue
        print(f"\n[{i+1}/{len(opportunities)}] Arricchimento: {player_name}")
        try:
            tm_data = enrich_with_retry(enricher, player_name)
            if tm_data:
                for key in ['nationality', 'second_nationality', 'foot', 'market_value', 'market_value_formatted', 'height_cm', 'birth_date', 'contract_expires', 'tm_url']:
                    opp[key] = tm_data.get(key)
                p = opp.setdefault('player_profile', {})
                for key in ['nationality', 'second_nationality', 'market_value', 'market_value_formatted', 'contract_expiry', 'foot', 'height_cm', 'tm_url']:
                    p[key] = tm_data.get(key)
                if not opp.get('age') and tm_data.get('birth_date'):
                    try:
                        opp['age'] = 2026 - int(tm_data['birth_date'][:4])
                    except:
                        pass
                opp['tm_enriched'] = True
                updated_count += 1
                nat_str = tm_data.get('nationality', 'N/A')
                if tm_data.get('second_nationality'):
                    nat_str += f" / {tm_data.get('second_nationality')}"
                print(f"  ✅ {nat_str} | {tm_data.get('market_value_text', 'N/A')}")
                if updated_count % 5 == 0:
                    save_progress(data, opportunities, DATA_FILE)
                    print("  💾 Salvataggio...")
                time.sleep(RATE_LIMIT_DELAY)
            else:
                print("  ⚠️ Nessun dato trovato")
        except Exception as e:
            print(f"  ❌ Errore: {e}")
            errors += 1
    if updated_count > 0:
        print(f"\nSalvataggio finale ({updated_count})...")
        save_progress(data, opportunities, DATA_FILE)
        save_progress(data, opportunities, DATA_FILE_DOCS)
    else:
        print("\nNessun aggiornamento.")
    print(f"\nTotale: {len(opportunities)} | Aggiornati: {updated_count} | Saltati: {skipped} | Errori: {errors}")
if __name__ == "__main__":
    main()
