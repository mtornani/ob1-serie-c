#!/usr/bin/env python3
"""
OB1 Scout - Generate Dashboard Data
Genera data.json con scoring avanzato SCORE-001
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add src to path for scoring module
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from scoring import OB1Scorer


def main():
    print("Generating dashboard data with advanced scoring...")

    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data'
    docs_dir = base_dir / 'docs'
    docs_dir.mkdir(exist_ok=True)

    # Load opportunities from data folder
    opps_file = data_dir / 'opportunities.json'
    stats_file = data_dir / 'stats.json'

    opportunities = []
    stats = {}

    if opps_file.exists():
        opportunities = json.loads(opps_file.read_text())
        print(f"Loaded {len(opportunities)} opportunities")
    else:
        print("No opportunities file found")

    if stats_file.exists():
        stats = json.loads(stats_file.read_text())

    # Initialize scorer
    scorer = OB1Scorer()

    # Transform opportunities for dashboard format with advanced scoring
    dashboard_opportunities = []
    for opp in opportunities:
        # Apply SCORE-001 advanced scoring
        score_result = scorer.score(opp)

        dashboard_opp = {
            'id': opp.get('id', f"opp_{hash(opp.get('player_name', '')) % 10000:04d}"),
            'player_name': opp.get('player_name', 'N/D'),
            'age': opp.get('age') or calculate_age(opp.get('birth_year')),
            'role': opp.get('role', ''),
            'role_name': opp.get('role_name', opp.get('role', '')),
            'opportunity_type': opp.get('opportunity_type', 'mercato').lower(),
            'reported_date': opp.get('discovered_at', datetime.now().isoformat())[:10],
            'source_name': opp.get('source_name', 'N/D'),
            'source_url': opp.get('source_url', ''),
            'previous_clubs': opp.get('previous_clubs', []),
            'current_club': opp.get('current_club', ''),
            'appearances': opp.get('appearances', 0),
            'goals': opp.get('goals', 0),
            'summary': opp.get('summary', ''),
            # SCORE-001 results
            'ob1_score': score_result['ob1_score'],
            'classification': score_result['classification'],
            'score_breakdown': score_result['score_breakdown'],
        }
        dashboard_opportunities.append(dashboard_opp)

    # Sort by score (highest first)
    dashboard_opportunities.sort(key=lambda x: x['ob1_score'], reverse=True)

    # Calculate stats
    hot_count = sum(1 for o in dashboard_opportunities if o['classification'] == 'hot')
    warm_count = sum(1 for o in dashboard_opportunities if o['classification'] == 'warm')
    cold_count = sum(1 for o in dashboard_opportunities if o['classification'] == 'cold')
    today = datetime.now().strftime('%Y-%m-%d')
    today_count = sum(1 for o in dashboard_opportunities if o['reported_date'] == today)

    # Create data.json for the dashboard
    dashboard_data = {
        'opportunities': dashboard_opportunities,
        'stats': {
            'total': len(dashboard_opportunities),
            'hot': hot_count,
            'warm': warm_count,
            'cold': cold_count,
            'today': today_count
        },
        'last_update': datetime.now().isoformat(),
        'scoring_version': 'SCORE-001'
    }

    # Write data.json to docs folder
    data_json_path = docs_dir / 'data.json'
    data_json_path.write_text(json.dumps(dashboard_data, indent=2, ensure_ascii=False))
    print(f"Dashboard data generated: {data_json_path}")
    print(f"   Total: {len(dashboard_opportunities)}, HOT: {hot_count}, WARM: {warm_count}, COLD: {cold_count}")

    # Print top 5 for verification
    if dashboard_opportunities:
        print("\nTop 5 opportunities:")
        for i, opp in enumerate(dashboard_opportunities[:5], 1):
            emoji = '🔥' if opp['classification'] == 'hot' else '⚡' if opp['classification'] == 'warm' else '❄️'
            print(f"  {i}. {emoji} {opp['player_name']} - {opp['ob1_score']}/100 ({opp['opportunity_type']})")


def calculate_age(birth_year):
    """Calculate age from birth year"""
    if birth_year:
        return datetime.now().year - birth_year
    return None


if __name__ == "__main__":
    main()
