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


def is_generic_tm_page(url: str) -> bool:
    """Detect generic Transfermarkt league/transfer pages (not player profiles)"""
    if not url:
        return False
    url_lower = url.lower()
    generic_patterns = [
        '/transfers/wettbewerb/',
        '/serie-d-girone',
        '/serie-c-girone',
        '/startseite/wettbewerb/',
        '/spieltagtabelle/',
    ]
    return any(p in url_lower for p in generic_patterns)


def generate_recommendation(opp: dict) -> str:
    """Auto-genera una nota scouting dalla data disponibile"""
    parts = []
    age = opp.get('age')
    opp_type = (opp.get('opportunity_type', '') or '').lower()
    market_value = opp.get('market_value', 0) or 0
    appearances = opp.get('appearances', 0) or 0
    goals = opp.get('goals', 0) or 0
    assists = opp.get('assists', 0) or 0
    previous_clubs = opp.get('previous_clubs', []) or []
    summary = opp.get('summary', '') or ''
    nationality = opp.get('nationality', '') or ''
    foot = opp.get('foot', '') or ''

    # Age profile
    if age:
        if age <= 21:
            parts.append(f"Profilo giovane ({age} anni), potenziale di crescita")
        elif age <= 25:
            parts.append(f"Età ideale ({age} anni), nel pieno della maturazione")
        elif age <= 28:
            parts.append(f"Piena maturità ({age} anni), pronto per impatto immediato")
        elif age <= 31:
            parts.append(f"Esperienza ({age} anni), può portare leadership")
        else:
            parts.append(f"Giocatore esperto ({age} anni)")

    # Contract situation
    if opp_type == 'svincolato':
        parts.append("Disponibile a parametro zero")
    elif opp_type == 'rescissione':
        parts.append("In uscita dal club, costo contenuto")
    elif opp_type == 'prestito':
        parts.append("Valutabile in prestito")

    # Stats
    if appearances > 50:
        stat_str = f"{appearances} presenze"
        if goals > 0:
            stat_str += f", {goals} gol"
        if assists > 0:
            stat_str += f", {assists} assist"
        parts.append(stat_str)

    # Market value
    if market_value >= 200000:
        parts.append(f"Valore di mercato interessante ({market_value // 1000}k€)")

    # Previous clubs
    notable = [c for c in previous_clubs if c.lower() not in ('svincolato', '', 'n/d')]
    if len(notable) >= 2:
        parts.append(f"Passato da {', '.join(notable[:3])}")

    # Use summary if nothing else
    if not parts and summary:
        return summary[:150]

    return '. '.join(parts[:3]) + '.' if parts else ''


def main():
    print("Generating dashboard data with SCORE-002 scoring...")

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
        opportunities = json.loads(opps_file.read_text(encoding='utf-8'))
        print(f"Loaded {len(opportunities)} raw opportunities")
    else:
        print("No opportunities file found")

    if stats_file.exists():
        stats = json.loads(stats_file.read_text())

    # === PRE-FILTER: remove junk entries ===
    filtered = []
    skipped_generic = 0
    skipped_foreign = 0
    skipped_no_entity = 0
    for opp in opportunities:
        # Skip generic Transfermarkt league pages
        if is_generic_tm_page(opp.get('source_url', '')):
            skipped_generic += 1
            continue
        # Skip entries without player name
        if not opp.get('player_name') or opp.get('player_name') in ('N/D', ''):
            continue

        # --- FIX: Geographic filter ---
        # Only allow Italian league entries or legacy entries (no league_id)
        league_id = opp.get('league_id', '')
        if league_id and not league_id.startswith('italy'):
            skipped_foreign += 1
            continue

        # --- FIX: Entity validation ---
        # Skip entries whose "name" is clearly a page title, not a player.
        # Real players can lack age/role (un-enriched), so we only filter on name patterns.
        player_name = opp.get('player_name', '')
        name_lower = player_name.lower()

        # Strip league prefix like "[ITALY] " for the check
        clean_name = player_name
        if clean_name.startswith('[') and '] ' in clean_name:
            clean_name = clean_name.split('] ', 1)[1]

        if '|' in clean_name or any(term in name_lower for term in [
            'transfermarkt', 'calciomercato', 'svincolati', 'la casa di c',
            'jugadores libres', 'ranking', 'classifica', 'tabella',
            'sul mercato', 'quanti svincolati', 'notizie di',
            'occasioni a zero', 'acquisti ufficiali', 'giocatori senza contratto',
            'tuttocampo', 'tuttomercato',
        ]):
            skipped_no_entity += 1
            continue

        filtered.append(opp)
    print(f"Pre-filter: {len(filtered)} kept, {skipped_generic} generic TM, "
          f"{skipped_foreign} foreign league, {skipped_no_entity} non-entity removed")
    opportunities = filtered

    # === DEDUP: by normalized player_name (keep first = most recent) ===
    seen_names = set()
    deduped = []
    for opp in opportunities:
        name_key = opp.get('player_name', '').strip().lower()
        if name_key and name_key not in seen_names:
            seen_names.add(name_key)
            deduped.append(opp)
    print(f"Dedup: {len(deduped)} unique players (removed {len(opportunities) - len(deduped)} duplicates)")
    opportunities = deduped

    # Initialize scorer
    scorer = OB1Scorer()

    # Transform opportunities for dashboard format with advanced scoring
    dashboard_opportunities = []
    for opp in opportunities:
        # Apply SCORE-001 advanced scoring
        score_result = scorer.score(opp)

        # Helper to get data from root or player_profile
        profile = opp.get('player_profile', {}) or {}
        
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
            'appearances': opp.get('appearances') or profile.get('appearances') or 0,
            'goals': opp.get('goals') or profile.get('goals') or 0,
            'assists': opp.get('assists') or profile.get('assists') or 0,
            'minutes_played': opp.get('minutes_played') or profile.get('minutes_played') or 0,
            'summary': opp.get('summary', ''),
            
            # DATA-001: New enriched fields
            'nationality': opp.get('nationality') or profile.get('nationality'),
            'second_nationality': opp.get('second_nationality') or profile.get('second_nationality'),
            'foot': opp.get('foot') or profile.get('foot'),
            'market_value': opp.get('market_value') or profile.get('market_value'),
            'market_value_formatted': opp.get('market_value_formatted') or profile.get('market_value_formatted'),
            'player_image_url': opp.get('player_image_url') or profile.get('player_image_url'),

            # DATA-003 QW-1: Agent field
            'agent': opp.get('agent') or profile.get('agent'),

            # Discovered timestamp (for stale detection)
            'discovered_at': opp.get('discovered_at', ''),

            # SCORE-002 results
            'ob1_score': score_result['ob1_score'],
            'classification': score_result['classification'],
            'score_breakdown': score_result['score_breakdown'],

            # Auto-generated recommendation
            'recommendation': generate_recommendation(opp),
        }

        # Fix missing/bad role names - map codes to readable names
        ROLE_MAP = {
            'PO': 'Portiere', 'DC': 'Difensore Centrale', 'TD': 'Terzino Destro',
            'TS': 'Terzino Sinistro', 'CC': 'Centrocampista', 'ED': 'Esterno Destro',
            'ES': 'Esterno Sinistro', 'TQ': 'Trequartista', 'AT': 'Attaccante',
            'AD': 'Ala Destra', 'AS': 'Ala Sinistra', 'MED': 'Mediano',
            'REG': 'Regista', 'PC': 'Punta Centrale',
        }
        role_name = dashboard_opp['role_name']
        if not role_name or role_name.lower() in ('non specificato', '', 'n/d'):
            role_code = dashboard_opp.get('role', '')
            dashboard_opp['role_name'] = ROLE_MAP.get(role_code.upper(), role_code or 'N/D')
        elif role_name.upper() in ROLE_MAP:
            dashboard_opp['role_name'] = ROLE_MAP[role_name.upper()]

        # DATA-003 QW-4: Calculate days_without_contract for svincolati/rescissioni
        opp_type = dashboard_opp['opportunity_type']
        if opp_type in ('svincolato', 'rescissione'):
            discovered = opp.get('discovered_at', '')
            if discovered:
                try:
                    discovered_date = datetime.fromisoformat(discovered.replace('Z', '+00:00')).date() if 'T' in discovered else datetime.strptime(discovered[:10], '%Y-%m-%d').date()
                    days = (datetime.now().date() - discovered_date).days
                    dashboard_opp['days_without_contract'] = max(0, days)
                except (ValueError, TypeError):
                    dashboard_opp['days_without_contract'] = 0
            else:
                dashboard_opp['days_without_contract'] = 0

            # Flag stale free agent: >30 days without contract AND appearances >= 10
            appearances = dashboard_opp.get('appearances', 0) or 0
            days_wc = dashboard_opp.get('days_without_contract', 0)
            dashboard_opp['stale_free_agent'] = (days_wc > 30 and appearances >= 10)
        else:
            dashboard_opp['days_without_contract'] = 0
            dashboard_opp['stale_free_agent'] = False

        dashboard_opportunities.append(dashboard_opp)

    # Sort by score (highest first)
    dashboard_opportunities.sort(key=lambda x: x['ob1_score'], reverse=True)

    # Calculate stats
    hot_count = sum(1 for o in dashboard_opportunities if o['classification'] == 'hot')
    warm_count = sum(1 for o in dashboard_opportunities if o['classification'] == 'warm')
    cold_count = sum(1 for o in dashboard_opportunities if o['classification'] == 'cold')
    today = datetime.now().strftime('%Y-%m-%d')
    today_count = sum(1 for o in dashboard_opportunities if o['reported_date'] == today)
    stale_count = sum(1 for o in dashboard_opportunities if o.get('stale_free_agent'))
    svincolati_count = sum(1 for o in dashboard_opportunities if o['opportunity_type'] in ('svincolato', 'rescissione'))

    # Create data.json for the dashboard
    dashboard_data = {
        'opportunities': dashboard_opportunities,
        'stats': {
            'total': len(dashboard_opportunities),
            'hot': hot_count,
            'warm': warm_count,
            'cold': cold_count,
            'today': today_count,
            'svincolati': svincolati_count,
            'stale_free_agents': stale_count
        },
        'last_update': datetime.now().isoformat(),
        'scoring_version': 'SCORE-002'
    }

    # Write data.json to docs folder
    data_json_path = docs_dir / 'data.json'
    data_json_path.write_text(json.dumps(dashboard_data, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Dashboard data generated: {data_json_path}")
    print(f"   Total: {len(dashboard_opportunities)}, HOT: {hot_count}, WARM: {warm_count}, COLD: {cold_count}")
    if stale_count:
        print(f"   ⚠️ Stale free agents (>30gg senza contratto, >=10 presenze): {stale_count}")

    # Print top 5 for verification
    if dashboard_opportunities:
        print("\nTop 5 opportunities:")
        for i, opp in enumerate(dashboard_opportunities[:5], 1):
            tag = 'HOT' if opp['classification'] == 'hot' else 'WARM' if opp['classification'] == 'warm' else 'COLD'
            print(f"  {i}. [{tag}] {opp['player_name']} - {opp['ob1_score']}/100 ({opp['opportunity_type']})")


def calculate_age(birth_year):
    """Calculate age from birth year"""
    if birth_year:
        return datetime.now().year - birth_year
    return None


if __name__ == "__main__":
    main()
