"""
OUROBOROS - Global Pipeline v5
Ultra-robust version with fixed scoring and nation tagging.
"""

import os
import sys
import json
import hashlib
import re
import unicodedata
from datetime import datetime
from pathlib import Path

# Add project root (for 'from src.xxx') AND src/ (for internal 'from models' etc.)
_root = str(Path(__file__).parent.parent)
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, 'src'))

from src.scraper_global import GlobalScraper
from src.scoring import OB1Scorer
from src.ingest import OB1Ingest, GEMINI_AVAILABLE
from src.models import MarketOpportunity
from src.notifier import TelegramNotifier

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
    if '|' in name:
        return False
    # Normalize all unicode whitespace (handles \xa0, zero-width, etc.)
    name = ' '.join(name.split())
    junk_terms = [
        # Italian media / organizations (observed in CI logs)
        'sky sport', 'transfermarkt', 'calciomercato', 'svincolati',
        'web radio', 'il portale', 'il piccolo', 'management magazine',
        'next pro wiki', 'chiamarsi bomber', 'spareggi nazionali', 'spareggi',
        'stagione sportiva', 'sport news', 'giornale', 'magazine',
        'notiziario', 'dipartimento', 'interregionale', 'associazione',
        'rappresentativa', 'juniores cup', 'parametro zero',
        'football italy', 'football club', 'migliori giovani',
        'giovani talenti', 'occasione serie', 'notizie calcio',
        'scuola superiore', 'fischio finale', 'ultime notizie',
        'la casa di c', 'tutto mercato', 'calciomercato live',
        'accordo collettivo', 'accordo', 'collettivo',
        # Media / news outlets
        'guardian', 'ultimo uomo', 'mediaset', 'calcio professionistiche',
        'talenti serie', 'salerno in web', 'cosenza quotidiano', 'tutto calcio',
        # Spanish / Portuguese junk
        'jugadores libres', 'ranking', 'classifica', 'tabella',
        'sul mercato', 'quanti svincolati',
        'rádio', 'el gráfico', 'sitio oficial', 'diario democracia', 'portal brazuca',
        'libre comercio', 'mercado libre', 'economic freedom', 'sou tricolor',
        'craques do futebol',
        # League / competition names
        'reserve league', 'liga profesional', 'selección', 'seleccion',
        'mundial sub', 'sub-20', 'sub-23',
    ]
    name_lower = name.lower()
    if any(term in name_lower for term in junk_terms):
        return False
    # Reject org-like names starting with non-name words.
    # NOTE: do NOT include 'la','lo','da','dal','della','degli' — real players like
    # La Gumina, Da Silva, Della Morte would be incorrectly blocked.
    words = name.split()
    if not words:
        return False
    first_word = words[0].lower()
    if first_word in ('the', 'tutto', 'nuova', 'nuovo', 'cinque', 'tanti', 'un', 'una'):
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


# Clubs that play in Serie A or Serie B — not relevant for a Lega Pro radar.
# U23/NextGen teams are intentionally excluded (they play physically in Serie C).
_WRONG_LEAGUE_CLUBS = {
    'cesena fc', 'salernitana', 'reggiana', 'cremonese', 'juve stabia',
    'cittadella', 'catanzaro', 'lazio', 'roma', 'bologna', 'empoli',
    'lecce', 'spezia', 'modena', 'sudtirol', 'bari', 'palermo',
    'sampdoria', 'parma', 'pisa', 'brescia', 'cosenza',
}

def purge_wrong_league(opps: list) -> list:
    """Remove players contracted to Serie A/B clubs (not acquirable by Lega Pro teams)."""
    clean = []
    removed = 0
    for opp in opps:
        club = (opp.get('current_club') or '').lower().strip()
        if any(bad in club for bad in _WRONG_LEAGUE_CLUBS):
            removed += 1
            continue
        clean.append(opp)
    if removed:
        print(f"  [PURGE] Removed {removed} wrong-league entries (Serie A/B clubs)")
    return clean


def _normalize_name(name: str) -> str:
    n = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower().strip()
    return re.sub(r'\s+', ' ', n)


def deduplicate(opps: list) -> list:
    """Merge duplicate entries for the same player (different source articles).
    Keeps the entry with the most data; discards single-word names (surname-only).
    """
    # Drop single-word names first — unenrichable noise
    valid = [o for o in opps if len((o.get('player_name') or '').strip().split()) >= 2]
    dropped_singles = len(opps) - len(valid)

    def _score(o):
        return (
            bool(o.get('market_value')) * 100 +
            bool(o.get('appearances')) * 50 +
            bool(o.get('contract_expires')) * 30 +
            bool(o.get('goals')) * 20 +
            bool(o.get('agent')) * 10 +
            bool(o.get('nationality')) * 5 +
            len(o.get('description', '') or o.get('summary', '') or '') // 10
        )

    groups: dict = {}
    for o in valid:
        key = _normalize_name(o.get('player_name', ''))
        if key not in groups or _score(o) > _score(groups[key]):
            groups[key] = o

    result = list(groups.values())
    merged = len(valid) - len(result)
    if dropped_singles or merged:
        print(f"  [DEDUP] Removed {dropped_singles} single-word names, merged {merged} duplicates → {len(result)} unique")
    return result


def run_ouroboros():
    print("=" * 60)
    print("🐍 OUROBOROS - GLOBAL CYCLE START (v5.1)")
    print("=" * 60)

    scraper = GlobalScraper(config_path="config/leagues.yaml")
    ingest = OB1Ingest() if GEMINI_AVAILABLE else None
    notifier = TelegramNotifier()

    existing_opps = load_existing_opps()

    # Cleanup: purge junk names, wrong-league clubs, single-word names, duplicates
    existing_opps = purge_junk_entries(existing_opps)
    existing_opps = purge_wrong_league(existing_opps)
    existing_opps = deduplicate(existing_opps)

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

            scorer = OB1Scorer()
            league_prefix = league_id.split('_')[0].upper() # IT, BR, AR

            for opp in raw_opps:
                try:
                    # Validate player name before scoring
                    if not is_valid_player_name(opp.player_name):
                        skipped_count += 1
                        continue

                    # Gate with the same SCORE-002 used by the dashboard (pre-enrichment)
                    raw_dict = {
                        'player_name': opp.player_name,
                        'opportunity_type': opp.opportunity_type.value,
                        'discovered_at': opp.reported_date,
                        'source_name': opp.source_name,
                        'source_url': opp.source_url,
                        'summary': opp.description,
                    }
                    gate_score = scorer.score(raw_dict)['ob1_score']
                    opp.relevance_score = max(1, min(5, gate_score // 20))

                    if gate_score >= 55:  # WARM floor — worth enriching
                        opp_dict = {
                            "id": hashlib.md5(f"{opp.player_name}_{opp.source_url}".encode()).hexdigest(),
                            "player_name": opp.player_name,
                            "region": league_prefix,
                            "opportunity_type": opp.opportunity_type.value,
                            "description": opp.description,
                            "ob1_score": gate_score,
                            "source_name": opp.source_name,
                            "source_url": opp.source_url,
                            "discovered_at": datetime.now().isoformat(),
                            "league_id": league_id,
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
            notifier.admin_alert("ERROR", f"ouroboros/{league_id}", str(e))

    # Final Save
    save_opps(existing_opps)
    print(f"\n✅ OUROBOROS COMPLETED. Added {new_opps_count} new, skipped {skipped_count} invalid.")
    print("=" * 60)

if __name__ == "__main__":
    run_ouroboros()
