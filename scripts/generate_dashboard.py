#!/usr/bin/env python3
"""
OB1 Scout - Generate Dashboard Data
Genera solo data.json, la dashboard è statica in docs/
"""

import json
from pathlib import Path
from datetime import datetime


def main():
    print("📊 Generating dashboard data...")

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
        print(f"📂 Loaded {len(opportunities)} opportunities")
    else:
        print("⚠️ No opportunities file found")

    if stats_file.exists():
        stats = json.loads(stats_file.read_text())

    # Transform opportunities for dashboard format
    dashboard_opportunities = []
    for opp in opportunities:
        # Calculate a basic score (will be replaced by SCORE-001)
        score = calculate_basic_score(opp)
        classification = 'hot' if score >= 80 else 'warm' if score >= 60 else 'cold'

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
            'ob1_score': score,
            'classification': classification
        }
        dashboard_opportunities.append(dashboard_opp)

    # Sort by score (highest first)
    dashboard_opportunities.sort(key=lambda x: x['ob1_score'], reverse=True)

    # Calculate stats
    hot_count = sum(1 for o in dashboard_opportunities if o['classification'] == 'hot')
    warm_count = sum(1 for o in dashboard_opportunities if o['classification'] == 'warm')
    today = datetime.now().strftime('%Y-%m-%d')
    today_count = sum(1 for o in dashboard_opportunities if o['reported_date'] == today)

    # Create data.json for the dashboard
    dashboard_data = {
        'opportunities': dashboard_opportunities,
        'stats': {
            'total': len(dashboard_opportunities),
            'hot': hot_count,
            'warm': warm_count,
            'today': today_count
        },
        'last_update': datetime.now().isoformat()
    }

    # Write data.json to docs folder
    data_json_path = docs_dir / 'data.json'
    data_json_path.write_text(json.dumps(dashboard_data, indent=2, ensure_ascii=False))
    print(f"✅ Dashboard data generated: {data_json_path}")
    print(f"   📊 Total: {len(dashboard_opportunities)}, HOT: {hot_count}, WARM: {warm_count}")


def calculate_basic_score(opp: dict) -> int:
    """
    Basic scoring algorithm (placeholder for SCORE-001)
    Returns a score 1-100
    """
    score = 50  # Base score

    # Opportunity type bonus
    opp_type = opp.get('opportunity_type', '').lower()
    type_scores = {
        'svincolato': 25,
        'rescissione': 20,
        'prestito': 10,
        'scadenza': 15,
        'mercato': 5
    }
    score += type_scores.get(opp_type, 0)

    # Age bonus (22-28 is ideal)
    age = opp.get('age') or calculate_age(opp.get('birth_year'))
    if age:
        if 22 <= age <= 28:
            score += 15
        elif 20 <= age < 22 or 28 < age <= 30:
            score += 10
        elif age < 20 or age > 30:
            score += 5

    # Experience bonus
    appearances = opp.get('appearances', 0)
    if appearances >= 100:
        score += 10
    elif appearances >= 50:
        score += 7
    elif appearances >= 20:
        score += 5

    return min(100, max(1, score))


def calculate_age(birth_year):
    """Calculate age from birth year"""
    if birth_year:
        return datetime.now().year - birth_year
    return None


if __name__ == "__main__":
    main()
