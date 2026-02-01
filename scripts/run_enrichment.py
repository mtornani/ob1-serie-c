#!/usr/bin/env python3
"""
Script per arricchire il database opportunità con dati Transfermarkt
"""

import sys
import os
import json
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.enricher_tm import TransfermarktEnricher

DATA_FILE = Path("data/opportunities.json")

def main():
    if not DATA_FILE.exists():
        print(f"File {DATA_FILE} non trovato!")
        return

    print(f"Loading {DATA_FILE}...")
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    opportunities = data.get('opportunities', [])
    print(f"Trovate {len(opportunities)} opportunità.")
    
    enricher = TransfermarktEnricher()
    updated_count = 0
    errors = 0
    
    # Process only recent opportunities to save API credits
    # Or process those missing market value
    
    for i, opp in enumerate(opportunities):
        player_name = opp.get('player_name')
        
        # Skip if already enriched (check market_value presence in player_profile or root)
        profile = opp.get('player_profile', {}) or {}
        if profile.get('market_value') or opp.get('tm_enriched', False):
            continue
            
        print(f"\n[{i+1}/{len(opportunities)}] Arricchimento: {player_name}")
        
        try:
            tm_data = enricher.enrich_player(player_name)
            
            if tm_data:
                # Update opportunity with TM data
                if 'player_profile' not in opp or not opp['player_profile']:
                    opp['player_profile'] = {}
                
                # Update profile fields
                p = opp['player_profile']
                p['market_value'] = tm_data.get('market_value_eur')
                p['market_value_formatted'] = tm_data.get('market_value_text')
                p['contract_expiry'] = tm_data.get('contract_expires')
                p['foot'] = tm_data.get('foot')
                p['height_cm'] = tm_data.get('height_cm')
                p['tm_url'] = tm_data.get('tm_url')
                
                # Also update root fields if missing
                if not opp.get('age') and tm_data.get('birth_date'):
                    # Calc age roughly
                    birth_year = int(tm_data['birth_date'][:4])
                    current_year = 2026
                    opp['age'] = current_year - birth_year
                
                opp['tm_enriched'] = True
                updated_count += 1
                
                # Save partial progress every 5 updates
                if updated_count % 5 == 0:
                    with open(DATA_FILE, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print("  💾 Salvataggio parziale...")
                
                # Be nice to APIs
                time.sleep(2)
            else:
                print("  ⚠️ Nessun dato trovato")
                
        except Exception as e:
            print(f"  ❌ Errore: {e}")
            errors += 1
            
    # Final save
    if updated_count > 0:
        print(f"\nSalvataggio finale ({updated_count} aggiornati)...")
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    else:
        print("\nNessun aggiornamento necessario.")
        
    print(f"\nFinito. Aggiornati: {updated_count}. Errori: {errors}")

if __name__ == "__main__":
    main()
