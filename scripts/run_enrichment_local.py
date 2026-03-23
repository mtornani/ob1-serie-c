#!/usr/bin/env python3
"""
Local enrichment runner - sets API keys before dotenv can override them.
"""
import os
import sys

# IMPORTANT: Set env vars BEFORE any import that calls load_dotenv()
# This ensures the real keys aren't overridden by .env placeholders
_gemini_key = os.environ.get("GEMINI_API_KEY", "")
_tavily_key = os.environ.get("TAVILY_API_KEY", "")

# Now import and run
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

# Re-set after potential dotenv override
if _gemini_key:
    os.environ["GEMINI_API_KEY"] = _gemini_key
if _tavily_key:
    os.environ["TAVILY_API_KEY"] = _tavily_key

import json
import time
from src.enricher_tm import TransfermarktEnricher

DATA_FILE = Path("data/opportunities.json")
MAX_RETRIES = 2
RATE_LIMIT_DELAY = 3


def main():
    print(f"GEMINI_API_KEY: {'SET' if os.environ.get('GEMINI_API_KEY','')[:5] != 'your_' else 'PLACEHOLDER'}")
    print(f"TAVILY_API_KEY: {'SET' if os.environ.get('TAVILY_API_KEY','')[:4] == 'tvly' else 'CHECK'}")

    if not DATA_FILE.exists():
        print("No data file!")
        return

    opps = json.load(open(DATA_FILE, 'r', encoding='utf-8'))
    print(f"Loaded {len(opps)} opportunities")

    enricher = TransfermarktEnricher()
    updated = 0
    errors = 0

    for i, opp in enumerate(opps):
        name = opp.get('player_name', '')

        # Skip if already has stats
        has_stats = (opp.get('appearances') or opp.get('goals') or opp.get('minutes_played'))
        if has_stats:
            continue

        print(f"\n[{i+1}/{len(opps)}] Enriching: {name}")

        try:
            tm_data = enricher.enrich_player(name)
            if not tm_data:
                print(f"  No data found")
                errors += 1
                time.sleep(1)
                continue

            # Apply all fields
            for key in ['nationality', 'second_nationality', 'foot', 'height_cm',
                        'contract_expires', 'agent', 'player_image_url',
                        'appearances', 'goals', 'assists', 'minutes_played']:
                val = tm_data.get(key)
                if val is not None:
                    opp[key] = val

            # Market value
            mv = tm_data.get('market_value_eur') or tm_data.get('market_value')
            if mv:
                opp['market_value'] = mv
            mvf = tm_data.get('market_value_text') or tm_data.get('market_value_formatted')
            if mvf:
                opp['market_value_formatted'] = mvf

            # TM URL
            if tm_data.get('tm_url'):
                opp['tm_url'] = tm_data['tm_url']

            # Age from birth_date
            if not opp.get('age') and tm_data.get('birth_date'):
                try:
                    opp['age'] = 2026 - int(tm_data['birth_date'][:4])
                except:
                    pass

            # Role
            if tm_data.get('main_position'):
                opp['role_name'] = tm_data['main_position']

            # Current club
            if not opp.get('current_club') and tm_data.get('current_club'):
                opp['current_club'] = tm_data['current_club']

            # Update profile sub-dict
            p = opp.setdefault('player_profile', {})
            for key in ['nationality', 'second_nationality', 'market_value',
                        'market_value_formatted', 'foot', 'agent',
                        'appearances', 'goals', 'assists', 'minutes_played']:
                val = tm_data.get(key)
                if val is not None:
                    p[key] = val

            opp['tm_enriched'] = True
            updated += 1

            stats = f"app={tm_data.get('appearances','?')} gol={tm_data.get('goals','?')} ast={tm_data.get('assists','?')} min={tm_data.get('minutes_played','?')}"
            age = opp.get('age', '?')
            mv_str = tm_data.get('market_value_text') or tm_data.get('market_value_formatted', 'N/A')
            print(f"  OK: age={age} {stats} MV={mv_str}")

            # Save every 5
            if updated % 5 == 0:
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(opps, f, ensure_ascii=False, indent=2)
                print(f"  [SAVED]")

            time.sleep(RATE_LIMIT_DELAY)

        except Exception as e:
            print(f"  ERROR: {e}")
            errors += 1
            time.sleep(2)

    # Final save
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(opps, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"DONE: {updated} enriched, {errors} errors")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
