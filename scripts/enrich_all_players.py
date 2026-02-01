#!/usr/bin/env python3
"""
DATA-001: Batch Enrichment Script
Arricchisce tutti i giocatori in opportunities.json con dati Transfermarkt
"""

import json
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from enricher_tm import TransfermarktEnricher


def main():
    print("=" * 60)
    print("DATA-001: Transfermarkt Enrichment")
    print("=" * 60)

    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data'

    # Load opportunities
    opps_file = data_dir / 'opportunities.json'
    if not opps_file.exists():
        print("ERROR: opportunities.json not found!")
        return

    opportunities = json.loads(opps_file.read_text())
    print(f"Loaded {len(opportunities)} opportunities")

    # Initialize enricher
    try:
        enricher = TransfermarktEnricher()
    except ValueError as e:
        print(f"ERROR: {e}")
        print("\nPer usare questo script, configura le API keys:")
        print("  1. Crea il file .env nella root del progetto")
        print("  2. Aggiungi: TAVILY_API_KEY=your_key")
        print("  3. Aggiungi: GEMINI_API_KEY=your_key")
        return

    # Track stats
    enriched = 0
    skipped = 0
    failed = 0

    # Process each player
    for i, opp in enumerate(opportunities):
        player_name = opp.get('player_name', '')

        # Skip if already has nationality data
        if opp.get('nationality'):
            print(f"[{i+1}/{len(opportunities)}] SKIP {player_name} (già arricchito)")
            skipped += 1
            continue

        print(f"\n[{i+1}/{len(opportunities)}] Enriching: {player_name}")

        try:
            tm_data = enricher.enrich_player(player_name)

            if tm_data:
                # Merge enriched data
                opp['nationality'] = tm_data.get('nationality')
                opp['second_nationality'] = tm_data.get('second_nationality')
                opp['foot'] = tm_data.get('foot')
                opp['market_value'] = tm_data.get('market_value_eur')
                opp['market_value_formatted'] = tm_data.get('market_value_text')
                opp['height_cm'] = tm_data.get('height_cm')
                opp['birth_date'] = tm_data.get('birth_date')
                opp['contract_expires'] = tm_data.get('contract_expires')
                opp['tm_url'] = tm_data.get('tm_url')

                # Calculate age from birth_date if we didn't have it
                if not opp.get('age') and tm_data.get('birth_date'):
                    try:
                        from datetime import datetime
                        bd = datetime.strptime(tm_data['birth_date'], '%Y-%m-%d')
                        opp['age'] = (datetime.now() - bd).days // 365
                    except:
                        pass

                enriched += 1
                print(f"  ✅ {tm_data.get('nationality', 'N/A')} | {tm_data.get('market_value_text', 'N/A')}")
            else:
                failed += 1
                print(f"  ❌ No data found")

        except Exception as e:
            failed += 1
            print(f"  ⚠️ Error: {e}")

        # Rate limiting - be nice to APIs
        time.sleep(2)

    # Save enriched data
    print("\n" + "=" * 60)
    print(f"Enrichment complete!")
    print(f"  ✅ Enriched: {enriched}")
    print(f"  ⏭️ Skipped: {skipped}")
    print(f"  ❌ Failed: {failed}")
    print("=" * 60)

    # Save back
    opps_file.write_text(json.dumps(opportunities, indent=2, ensure_ascii=False))
    print(f"\nSaved to: {opps_file}")

    # Also regenerate dashboard data
    print("\nRegenerating dashboard data...")
    import subprocess
    subprocess.run([sys.executable, str(base_dir / 'scripts' / 'generate_dashboard.py')])

    print("\n🎉 Done! Now run: git add . && git commit && git push")


if __name__ == "__main__":
    main()
