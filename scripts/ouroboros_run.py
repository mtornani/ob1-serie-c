"""
OUROBOROS - Global Pipeline v5
Ultra-robust version with fixed scoring and nation tagging.
"""

import os
import sys
import json
import hashlib
import time
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from src.scraper_global import GlobalScraper
from src.scoring_global import OB1Scorer
from src.dna.engine_global import DNAEngine
from src.ingest import OB1Ingest, GEMINI_AVAILABLE
from src.models import MarketOpportunity

OPPS_FILE = Path("data/opportunities.json")

def load_existing_opps():
    if OPPS_FILE.exists():
        try:
            return json.loads(OPPS_FILE.read_text(encoding='utf-8'))
        except:
            return []
    return []

def save_opps(opps):
    OPPS_FILE.write_text(json.dumps(opps, indent=2, ensure_ascii=False), encoding='utf-8')

def is_valid_player_name(name: str) -> bool:
    """Validate that a name looks like a real person, not a page title."""
    if not name or len(name) < 3:
        return False
    # Must not contain typical page-title separators
    if '|' in name:
        return False
    junk_terms = [
        'transfermarkt', 'calciomercato', 'svincolati', 'la casa di c',
        'jugadores libres', 'ranking', 'classifica', 'tabella',
        'sul mercato', 'quanti svincolati',
    ]
    name_lower = name.lower()
    if any(term in name_lower for term in junk_terms):
        return False
    return True


def purge_junk_entries(opps: list) -> list:
    """Remove existing junk entries from the database (one-time cleanup)."""
    clean = []
    removed = 0
    for opp in opps:
        name = opp.get('player_name', '')
        if not is_valid_player_name(name):
            removed += 1
            continue
        clean.append(opp)
    if removed:
        print(f"  [PURGE] Removed {removed} junk entries from existing data")
    return clean


def run_ouroboros():
    print("=" * 60)
    print("🐍 OUROBOROS - GLOBAL CYCLE START (v5.1)")
    print("=" * 60)

    scraper = GlobalScraper(config_path="config/leagues.yaml")
    dna_engine = DNAEngine(manifesto_path="config/dna_manifestos.yaml")
    ingest = OB1Ingest() if GEMINI_AVAILABLE else None

    existing_opps = load_existing_opps()

    # One-time cleanup: purge any junk entries already in the DB
    existing_opps = purge_junk_entries(existing_opps)

    new_opps_count = 0
    skipped_count = 0

    leagues = scraper.leagues
    for league_id, league_conf in leagues.items():
        print(f"\n🌍 Scouting: {league_conf['name']} ({league_id})")

        try:
            # Discovery
            raw_opps = scraper.scrape_league(league_id)
            if not raw_opps: continue

            # Scoring
            # Ensure league_conf is a dict
            if not isinstance(league_conf, dict):
                print(f"  [ERROR] Invalid config for {league_id}")
                continue

            scorer = OB1Scorer(league_conf)
            league_prefix = league_id.split('_')[0].upper() # IT, BR, AR

            for opp in raw_opps:
                try:
                    # Validate player name before expensive DNA matching
                    if not is_valid_player_name(opp.player_name):
                        skipped_count += 1
                        continue

                    opp.relevance_score = scorer.calculate_score(opp)

                    if opp.relevance_score >= 3:
                        # DNA Matching with 3s delay
                        print(f"  [INTEL] Analyzing {opp.player_name}...")
                        time.sleep(3) # Heavy Anti-429

                        dna_results = dna_engine.calculate_dna_fit(opp)
                        dna_fit = {k: v for k, v in dna_results.items() if isinstance(v, dict)}

                        # Structured Dict for Bot/Dashboard
                        opp_dict = {
                            "id": hashlib.md5(f"{opp.player_name}_{opp.source_url}".encode()).hexdigest(),
                            "player_name": f"[{league_prefix}] {opp.player_name}",
                            "opportunity_type": opp.opportunity_type.value,
                            "description": opp.description,
                            "ob1_score": opp.relevance_score * 20,
                            "source_name": opp.source_name,
                            "source_url": opp.source_url,
                            "discovered_at": datetime.now().isoformat(),
                            "league_id": league_id,
                            "dna_strategic_fit": dna_fit
                        }

                        # Dedup and Add
                        if not any(o['id'] == opp_dict['id'] for o in existing_opps):
                            existing_opps.append(opp_dict)
                            new_opps_count += 1
                except Exception as e:
                    print(f"  [SKIP] Player error: {e}")

            # Ingest to RAG
            if ingest and raw_opps:
                ingest.ingest_opportunities(league_id, raw_opps)

        except Exception as e:
            print(f"❌ Error in {league_id}: {e}")

    # Final Save
    save_opps(existing_opps)
    print(f"\n✅ OUROBOROS COMPLETED. Added {new_opps_count} new, skipped {skipped_count} invalid.")
    print("=" * 60)

if __name__ == "__main__":
    run_ouroboros()
