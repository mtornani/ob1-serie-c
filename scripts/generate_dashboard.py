#!/usr/bin/env python3
"""
OB1 Lega Pro - Generate Dashboard Data
Genera data.json con scoring SCORE-003 + quality gate (identity_complete,
src/quality_gate.py, allineato a global-scout v2: publishable richiede
identity_complete AND corroborated, hard-gate).

Pubblica solo profili publishable (nome+età+club+fonte). Tracking in stats.
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).parent.parent

# Add src to path for scoring module
sys.path.insert(0, str(REPO_ROOT / 'src'))

from scoring import OB1Scorer, assess_follow
from minutaggio import genera_intel_badge
from quality_gate import apply_gate, normalize_age


def _version_and_build() -> tuple:
    """
    (version, build) per il footer "e' aggiornato al deploy giusto?" — stesso
    pattern di OB1 Global (vedi export_dashboard_v2.py). Deploy statico via
    commit della pipeline: niente revision iniettata da una piattaforma,
    quindi build = short SHA del commit che ha girato questo export.
    Non deve mai poter rompere l'export: qualunque errore ripiega su
    "0.0.0"/"dev" invece di sollevare.
    """
    version = "0.0.0"
    try:
        version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip() or version
    except OSError:
        pass
    build = "dev"
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=5,
        )
        if sha.returncode == 0 and sha.stdout.strip():
            build = sha.stdout.strip()
    except Exception:
        pass
    return version, build


def _first(*vals):
    """Primo valore non-None, lo zero VERO compreso. Nessuna coercizione."""
    for v in vals:
        if v is not None:
            return v
    return None


def _tm_url(url):
    """
    L'url solo se è un link Transfermarkt vero, quindi verificabile da chi
    legge — non un redirect di grounding né spazzatura. Altrimenti None.
    """
    if isinstance(url, str) and 'transfermarkt' in url.lower() and url.startswith('http'):
        return url
    return None


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
    print("Generating dashboard data with SCORE-003 scoring...")

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

        # Normalize age early (birth year dumped as age → real age)
        norm_age = normalize_age(
            opp.get('age'),
            birth_date=opp.get('birth_date'),
            birth_year=opp.get('birth_year'),
        )
        if norm_age is not None:
            opp = dict(opp)
            opp['age'] = norm_age

        # Entity: need age OR real role (page titles die here)
        has_age = opp.get('age') is not None
        role_raw = (opp.get('role_name') or opp.get('role') or '').strip()
        has_role = role_raw not in ('', 'N/D', 'Non specificato')
        if not has_age and not has_role:
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

    # Transform + score + quality gate
    all_scored = []
    for opp in opportunities:
        opp = apply_gate(opp)
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
            # Fiducia: una statistica ignota resta null, non diventa 0. Un "0
            # presenze" inventato si legge come "non ha mai giocato" — e chi
            # scopre una volta che il numero era finto non torna più.
            'appearances': _first(opp.get('appearances'), profile.get('appearances')),
            'goals': _first(opp.get('goals'), profile.get('goals')),
            'assists': _first(opp.get('assists'), profile.get('assists')),
            'minutes_played': _first(opp.get('minutes_played'), profile.get('minutes_played')),
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

            # Link Transfermarkt verificabile (vale solo un url TM vero) e il
            # flag che la UI usa per separare i dati controllabili dalle stime.
            # È il gate delle due fonti reso visibile sulla singola scheda.
            'tm_url': _tm_url(opp.get('tm_url') or profile.get('tm_url')),
            'data_verified': bool(_tm_url(opp.get('tm_url') or profile.get('tm_url'))),

            # Discovered timestamp (for stale detection)
            'discovered_at': opp.get('discovered_at', ''),

            # SCORE-003
            'ob1_score': score_result['ob1_score'],
            'classification': score_result['classification'],
            'score_breakdown': score_result['score_breakdown'],

            # Quality gate — nomi storici, mantenuti per compatibilità con
            # chi legge già data.json così com'è (nessun consumer in docs/
            # li usa oggi, verificato, ma restano per chi guarda il JSON
            # a mano). Stesso nome di campo e stessa soglia di OB1 Global:
            # publishable = identity_complete AND corroborated (hard-gate,
            # vedi src/quality_gate.py). I market_* sotto sono lo stesso
            # dato con un nome che lo dice da solo, senza dover aprire
            # quality_gate.py per scoprirlo.
            'identity_complete': opp.get('identity_complete', False),
            'corroborated': opp.get('corroborated', False),
            'publishable': opp.get('publishable', False),
            'review_flags': opp.get('review_flags', ''),
            'n_sources': opp.get('n_sources', 1),
            'out_of_scope': opp.get('out_of_scope', False),
            'out_of_scope_reason': opp.get('out_of_scope_reason', ''),

            # Stessi valori, nome che porta il significato (dossier
            # "identità distinte": non toglie i campi storici sopra, li
            # affianca)
            'market_identity_complete': opp.get('identity_complete', False),
            'market_corroborated': opp.get('corroborated', False),
            'market_publishable': opp.get('publishable', False),
            'market_n_sources': opp.get('n_sources', 1),

            # Auto-generated recommendation
            'recommendation': generate_recommendation(opp),
        }

        # ── INTEL Engine: ROI Minutaggio + Traffic Light FIGC + Signals ──
        intel_input = dict(dashboard_opp)
        intel_input['contract_expires'] = opp.get('contract_expires') or profile.get('contract_expires', '')
        intel = genera_intel_badge(intel_input, league='serie_c')
        dashboard_opp['intel'] = intel
        dashboard_opp['contract_expires'] = intel_input.get('contract_expires', '')

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

        # Perché sì / no — after days_without_contract is known (no LLM)
        dashboard_opp['assessment'] = assess_follow(dashboard_opp, score_result)

        all_scored.append(dashboard_opp)

    tracking_total = len(all_scored)
    # out_of_scope: giocatore vero ma fuori fascia Serie C (es. valore 35 mln €).
    # Non è un'opportunità per questo radar, quindi non entra nel feed pubblico.
    out_of_scope_n = sum(1 for o in all_scored if o.get('out_of_scope'))
    publishable_list = [o for o in all_scored
                        if o.get('publishable') and not o.get('out_of_scope')]
    tracking_only = tracking_total - len(publishable_list)
    if out_of_scope_n:
        print(f"   Esclusi fuori fascia Serie C: {out_of_scope_n}")

    # Public feed = only publishable
    dashboard_opportunities = publishable_list
    dashboard_opportunities.sort(key=lambda x: x['ob1_score'], reverse=True)

    # Calculate stats (public list)
    hot_count = sum(1 for o in dashboard_opportunities if o['classification'] == 'hot')
    warm_count = sum(1 for o in dashboard_opportunities if o['classification'] == 'warm')
    cold_count = sum(1 for o in dashboard_opportunities if o['classification'] == 'cold')
    today = datetime.now().strftime('%Y-%m-%d')
    today_count = sum(1 for o in dashboard_opportunities if o['reported_date'] == today)
    stale_count = sum(1 for o in dashboard_opportunities if o.get('stale_free_agent'))
    svincolati_count = sum(1 for o in dashboard_opportunities if o['opportunity_type'] in ('svincolato', 'rescissione'))
    corroborated_count = sum(1 for o in dashboard_opportunities if o.get('corroborated'))

    # ── INTEL Stats ──
    intel_stats = {'elite': 0, 'high': 0, 'medium': 0, 'low': 0, 'none': 0}
    for o in dashboard_opportunities:
        roi_class = (o.get('intel') or {}).get('roi_class', 'none')
        if roi_class in intel_stats:
            intel_stats[roi_class] += 1

    # Create data.json for the dashboard
    version, build = _version_and_build()
    dashboard_data = {
        'opportunities': dashboard_opportunities,
        'stats': {
            'total': len(dashboard_opportunities),
            'hot': hot_count,
            'warm': warm_count,
            'cold': cold_count,
            'today': today_count,
            'svincolati': svincolati_count,
            'stale_free_agents': stale_count,
            'intel_roi': intel_stats,
            'tracking_total': tracking_total,
            'tracking_only': tracking_only,
            'publishable': len(dashboard_opportunities),
            'corroborated': corroborated_count,
        },
        'last_update': datetime.now().isoformat(),
        'version': version,
        'build': build,
        'scoring_version': 'SCORE-003',
        'intel_version': 'INTEL-001',
        'quality_gate': 'identity_complete+corroborated',
    }

    # Write data.json to docs folder
    data_json_path = docs_dir / 'data.json'
    data_json_path.write_text(json.dumps(dashboard_data, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Dashboard data generated: {data_json_path}")
    print(f"   Tracking: {tracking_total} | Publishable: {len(dashboard_opportunities)} "
          f"(gated {tracking_only}) | Corroborated: {corroborated_count}")
    print(f"   Public: HOT {hot_count}, WARM {warm_count}, COLD {cold_count}")
    if stale_count:
        print(f"   ⚠️ Stale free agents (>30gg senza contratto, >=10 presenze): {stale_count}")

    # INTEL summary
    print(f"   INTEL ROI: {intel_stats['elite']} Elite, {intel_stats['high']} High, "
          f"{intel_stats['medium']} Medium, {intel_stats['low']} Low, {intel_stats['none']} No contrib.")

    # Print top 5 for verification
    if dashboard_opportunities:
        print("\nTop 5 publishable:")
        for i, opp in enumerate(dashboard_opportunities[:5], 1):
            tag = 'HOT' if opp['classification'] == 'hot' else 'WARM' if opp['classification'] == 'warm' else 'COLD'
            intel = opp.get('intel', {})
            roi_lbl = intel.get('roi_label', '—')
            print(f"  {i}. [{tag}] {opp['player_name']} ({opp.get('age')}a) "
                  f"- {opp['ob1_score']}/100 ({opp['opportunity_type']}) | ROI: {roi_lbl}")
    else:
        print("\n⚠️ Nessun profilo publishable — arricchire età/club.")


def calculate_age(birth_year):
    """Calculate age from birth year"""
    if birth_year:
        return datetime.now().year - birth_year
    return None


if __name__ == "__main__":
    main()
