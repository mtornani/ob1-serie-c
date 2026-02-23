"""
OUROBOROS - OB1 WORLD™ Global Pipeline
The ultimate scouting engine for Ouroboros.
"""

import os
import sys
import hashlib
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from src.scraper_global import GlobalScraper
from src.scoring_global import OB1Scorer
from src.dna.engine_global import DNAEngine
from src.ingest import OB1Ingest, GEMINI_AVAILABLE
from src.models import MarketOpportunity

def run_ouroboros():
    print("=" * 60)
    print("🐍 OUROBOROS - OB1 WORLD™ - GLOBAL CYCLE START")
    print("=" * 60)
    
    # Init
    scraper = GlobalScraper(config_path="config/leagues.yaml")
    dna_engine = DNAEngine(manifesto_path="config/dna_manifestos.yaml")
    ingest = OB1Ingest() if GEMINI_AVAILABLE else None
    
    leagues = scraper.leagues
    
    for league_id, league_conf in leagues.items():
        print(f"\n🌍 Scouting: {league_conf['name']} ({league_id})")
        
        try:
            # 1. Scrape & Discover (Anti-Bot with Scrapling)
            raw_opps = scraper.scrape_league(league_id)
            if not raw_opps: continue
                
            # 2. Score & Intelligence (DNA 2.0 Semantic Match)
            scorer = OB1Scorer(league_conf)
            processed_opps = []
            
            for opp in raw_opps:
                opp.relevance_score = scorer.calculate_score(opp)
                
                if opp.relevance_score >= 3:
                    # DNA 2.0 Semantic Match
                    opp.dna_matches = dna_engine.calculate_dna_fit(opp)
                    processed_opps.append(opp)
            
            print(f"✨ Found {len(processed_opps)} high-quality signals.")
            
            # 3. Ingest to RAG (Gemini File Search)
            if ingest and processed_opps:
                ingest.ingest_opportunities(league_id, processed_opps)
                
        except Exception as e:
            print(f"❌ Error in league {league_id}: {e}")

    print("\n" + "=" * 60)
    print("🐍 OUROBOROS - CYCLE COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    run_ouroboros()
