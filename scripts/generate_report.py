#!/usr/bin/env python3
"""
Script per generare il report PDF settimanale
"""

import sys
import os
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from reporter import ReportGenerator
from history import HistoryTracker

DATA_DIR = Path(__file__).parent.parent / 'data'
DOCS_DIR = Path(__file__).parent.parent / 'docs'

def main():
    print("Generazione Report PDF...")
    
    # Load Opportunities
    opps_file = DATA_DIR / 'opportunities.json'
    if not opps_file.exists():
        print("❌ Nessun file opportunità trovato.")
        return
        
    try:
        data = json.loads(opps_file.read_text(encoding='utf-8'))
        opportunities = data if isinstance(data, list) else data.get('opportunities', [])
    except Exception as e:
        print(f"❌ Errore caricamento opportunità: {e}")
        return

    # Load DNA Matches (optional)
    dna_file = DOCS_DIR / 'dna_matches.json'
    dna_matches = []
    if dna_file.exists():
        try:
            dna_data = json.loads(dna_file.read_text(encoding='utf-8'))
            dna_matches = dna_data.get('top_matches', [])
        except:
            pass
            
    # Generate Report
    gen = ReportGenerator(output_dir=str(DOCS_DIR / 'reports'))
    filepath = gen.generate_weekly_report(opportunities, dna_matches)
    
    # Copy to latest for easy access
    import shutil
    latest_path = DOCS_DIR / 'report_latest.pdf'
    shutil.copy(filepath, latest_path)
    print(f"✅ Report salvato in: {latest_path}")
    
    # Output variable for GitHub Actions
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.getenv('GITHUB_OUTPUT'), 'a') as f:
            f.write(f'report_path={latest_path}\n')

if __name__ == "__main__":
    main()
