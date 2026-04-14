#!/usr/bin/env python3
"""
OB1 Serie C — Gemini Audit Relay: Query Scouting Profiles
Processes structured query configs against data/opportunities.json
and returns PLAYER_SCHEMA standard output per query.

Usage:
    python scripts/query_scouting_profiles.py [query_config.json]
    (if no file given, runs the built-in INTER/TRIESTINA/CESENA/JUVE_STABIA config)
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from scoring import OB1Scorer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent / 'data'

# Query-format position codes → internal role codes
POSITION_MAP = {
    'MF':  {'CC', 'MED', 'REG', 'TRQ'},
    'ST':  {'PC', 'AT', 'ATT'},
    'CB':  {'DC'},
    'WG':  {'ED', 'ES', 'AD', 'AS'},
    'GK':  {'PO'},
    'FB':  {'TD', 'TS'},
}

# Role-name keywords per position
POSITION_NAME_KEYWORDS = {
    'MF': ['centrocampista', 'mediano', 'regista', 'trequartista', 'mezzala', 'interno'],
    'ST': ['punta', 'centravanti', 'attaccante', 'prima punta', 'seconda punta'],
    'CB': ['difensore centrale', 'centrale difensivo', 'difensore'],
    'WG': ['ala', 'esterno offensivo', 'esterno'],
    'GK': ['portiere'],
    'FB': ['terzino'],
}

TODAY = date.today()


# ---------------------------------------------------------------------------
# Built-in query config (from the Gemini Audit Relay 2026-04-14)
# ---------------------------------------------------------------------------

BUILTIN_QUERIES = {
    "meta": {
        "generated_by": "Claude — Gemini Audit Relay",
        "date": "2026-04-14",
        "purpose": "Query config per OB1 Lega Pro: estrazione profili reali per gap strategici identificati da Gemini Research Intelligence",
        "target_clubs": ["Inter U23", "US Triestina", "Cesena FC", "SS Juve Stabia"],
        "output_format": "PLAYER_SCHEMA standard"
    },
    "queries": [
        {
            "query_id": "INTER_U23_MEDIANO",
            "target_club": "Inter Under 23",
            "tier": "Serie C - Girone A",
            "strategic_context": "Progetto neonato 2025/26, struttura scouting in integrazione con prima squadra. Cercano profili pronti per il salto Serie A/B.",
            "critical_role": "Mediano metodista",
            "filters": {
                "position": ["MF"],
                "position_detail": ["Mediano", "Regista", "Centrocampista centrale"],
                "age_range": [19, 23],
                "contract_expires_before": "2027-06-30",
                "min_appearances_season": 15,
                "sort_by": "minutes_desc",
                "max_results": 5
            },
            "scoring_boost": {
                "patterns": {
                    "recupero palla": 3,
                    "costruzione dal basso": 3,
                    "verticalizzazione": 2,
                    "passaggi progressivi": 2,
                    "under.*nazionale": 2
                },
                "min_score": 4.0
            },
            "notes": "Profilo tipo: regista di palleggio con capacità di filtro."
        },
        {
            "query_id": "INTER_U23_PUNTA",
            "target_club": "Inter Under 23",
            "tier": "Serie C - Girone A",
            "strategic_context": "Cercano punta centrale fisica come alternativa ai profili tecnici già nel vivaio.",
            "critical_role": "Punta centrale fisica",
            "filters": {
                "position": ["ST"],
                "position_detail": ["Centravanti", "Prima punta", "Attaccante centrale"],
                "age_range": [19, 23],
                "contract_expires_before": "2027-06-30",
                "min_goals_season": 5,
                "min_appearances_season": 12,
                "sort_by": "goals_desc",
                "max_results": 5
            },
            "scoring_boost": {
                "patterns": {
                    "fisicità": 3,
                    "gioco aereo": 3,
                    "sponda": 2,
                    "profondità": 2,
                    "gol di testa": 2
                },
                "min_score": 4.0
            },
            "notes": "Centravanti fisico, bravo nel gioco aereo e sponde."
        },
        {
            "query_id": "TRIESTINA_MONEYBALL_ATT",
            "target_club": "US Triestina",
            "tier": "Serie C - Girone A",
            "strategic_context": "Filosofia Moneyball/Web3. Cercano asimmetrie pure: valore reale >> costo di acquisizione.",
            "critical_role": "Attaccante esterno/seconda punta con asimmetria di valore",
            "filters": {
                "position": ["WG", "ST"],
                "position_detail": ["Ala", "Esterno offensivo", "Seconda punta", "Trequartista"],
                "age_range": [18, 24],
                "contract_expires_before": "2027-06-30",
                "market_value_max_eur": 300000,
                "min_goal_contributions_season": 5,
                "sort_by": "asymmetry_index_desc",
                "max_results": 5
            },
            "scoring_boost": {
                "patterns": {
                    "svincol": 4,
                    "scadenza": 3,
                    "serie d.*promosso": 3,
                    "doppia cifra": 3,
                    "basso costo": 2,
                    "svincolato": 4
                },
                "min_score": 5.0
            },
            "asymmetry_logic": "Rapporto goal_contributions / market_value.",
            "notes": "Filtro esteso a Serie D."
        },
        {
            "query_id": "TRIESTINA_MONEYBALL_DIF",
            "target_club": "US Triestina",
            "tier": "Serie C - Girone A",
            "strategic_context": "Stessa logica Moneyball: difensore centrale giovane con metriche aeree sopra media.",
            "critical_role": "Difensore centrale con asimmetria di valore",
            "filters": {
                "position": ["CB"],
                "position_detail": ["Difensore centrale", "Centrale difensivo"],
                "age_range": [19, 24],
                "contract_expires_before": "2027-06-30",
                "market_value_max_eur": 250000,
                "min_appearances_season": 15,
                "sort_by": "asymmetry_index_desc",
                "max_results": 5
            },
            "scoring_boost": {
                "patterns": {
                    "duelli aerei vinti": 3,
                    "intercett": 2,
                    "anticipo": 2,
                    "impostazione": 2,
                    "svincol": 4,
                    "under.*nazionale": 2
                },
                "min_score": 4.0
            },
            "notes": "Difensore di prospettiva con costo irrisorio."
        },
        {
            "query_id": "CESENA_SHPENDI_PATTERN",
            "target_club": "Cesena FC",
            "tier": "Serie B",
            "strategic_context": "Modello sostenibilità JRL Investment. Cercano il prossimo Shpendi: bomber U22 da C o D.",
            "critical_role": "Bomber Under-22 da Serie C/D",
            "filters": {
                "position": ["ST"],
                "position_detail": ["Centravanti", "Prima punta", "Seconda punta"],
                "age_range": [18, 22],
                "contract_expires_before": "2027-06-30",
                "min_goals_season": 8,
                "sort_by": "goals_desc",
                "max_results": 5
            },
            "scoring_boost": {
                "patterns": {
                    "doppia cifra": 4,
                    "capocannoniere": 3,
                    "under.*gol": 3,
                    "serie d.*bomber": 3,
                    "origine albanese|kosovaro|balcanico": 2,
                    "basso costo": 2,
                    "cresciuto.*settore giovanile": 2
                },
                "min_score": 5.0
            },
            "reference_pattern": {
                "player": "Stiven Shpendi",
                "trajectory": "Serie C bassa → Cesena Serie B → 15+ gol → interesse Serie A",
                "key_metric": "Goals / appearances ratio > 0.35 in under-22"
            },
            "notes": "Serie D inclusa. Filtro aggressivo su età e gol."
        },
        {
            "query_id": "JUVE_STABIA_CENTRAVANTI",
            "target_club": "SS Juve Stabia",
            "tier": "Serie B",
            "strategic_context": "Brera Holdings, quotata NASDAQ. Ossessione plusvalenza.",
            "critical_role": "Centravanti U23 (plusvalenza target)",
            "filters": {
                "position": ["ST"],
                "position_detail": ["Centravanti", "Prima punta"],
                "age_range": [19, 23],
                "contract_expires_before": "2027-06-30",
                "market_value_max_eur": 500000,
                "min_goals_season": 6,
                "sort_by": "value_growth_potential_desc",
                "max_results": 5
            },
            "scoring_boost": {
                "patterns": {
                    "progressione": 3,
                    "miglioramento": 2,
                    "crescita": 2,
                    "prima stagione.*gol": 3,
                    "doppia cifra": 3,
                    "under.*nazionale": 2
                },
                "min_score": 4.0
            },
            "valuation_logic": "Rapporto TM_value_current / acquisition_cost. Target: <500K → proiezione >1.5M in 18 mesi.",
            "notes": "Brera Holdings: comprare a X, dimostrare crescita a 3X in 18 mesi."
        },
        {
            "query_id": "JUVE_STABIA_MEZZALA",
            "target_club": "SS Juve Stabia",
            "tier": "Serie B",
            "strategic_context": "Modello plusvalenza applicato a centrocampo.",
            "critical_role": "Mezzala d'inserimento",
            "filters": {
                "position": ["MF"],
                "position_detail": ["Mezzala", "Centrocampista offensivo", "Interno"],
                "age_range": [19, 23],
                "contract_expires_before": "2027-06-30",
                "min_goal_contributions_season": 4,
                "min_appearances_season": 15,
                "sort_by": "goal_contributions_desc",
                "max_results": 5
            },
            "scoring_boost": {
                "patterns": {
                    "inserimento": 3,
                    "gol.*centrocampo": 3,
                    "box to box": 2,
                    "dinamismo": 2,
                    "assist": 2,
                    "under.*nazionale": 2
                },
                "min_score": 4.0
            },
            "notes": "Mezzala con numeri offensivi da Serie C: 4+ gol+assist."
        }
    ]
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_date(date_str: str) -> date | None:
    """Parse ISO date string to date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def age_is_valid(age) -> bool:
    """Return True if age value looks like actual age (not birth year)."""
    return isinstance(age, (int, float)) and 14 <= age <= 45


def position_matches(player: dict, query_positions: list[str]) -> bool:
    """
    Returns True if player's role matches any of the query position codes.
    Uses both internal role codes and role_name keyword matching.
    If no position info at all, returns True (soft match).
    """
    role = (player.get('role') or '').upper()
    role_name = (player.get('role_name') or '').lower()

    if not role and not role_name:
        return True  # no position data — include tentatively

    for pos_code in query_positions:
        internal_codes = POSITION_MAP.get(pos_code, set())
        if role in internal_codes:
            return True
        keywords = POSITION_NAME_KEYWORDS.get(pos_code, [])
        if any(kw in role_name for kw in keywords):
            return True

    return False


def age_matches(player: dict, age_range: list[int] | None) -> bool:
    """
    Returns True if player age is within range.
    If age is missing/invalid, returns True (soft pass — don't exclude unknowns).
    """
    if not age_range:
        return True
    age = player.get('age')
    if not age_is_valid(age):
        return True  # unknown age → keep in pool
    return age_range[0] <= age <= age_range[1]


def contract_matches(player: dict, expires_before: str | None) -> bool:
    """
    Returns True if contract expires before the threshold date.
    Free agents (svincolato/rescissione) always pass — they're already available.
    If contract data is missing, returns True (soft pass).
    """
    if not expires_before:
        return True
    # Svincolati/rescissioni are always available regardless of stored contract date
    opp_type = (player.get('opportunity_type') or '').lower()
    if opp_type in ('svincolato', 'rescissione'):
        return True
    contract_date = parse_date(player.get('contract_expires'))
    if not contract_date:
        return True  # no contract info — keep
    threshold = parse_date(expires_before)
    if not threshold:
        return True
    return contract_date <= threshold


def stat_threshold_passes(value, minimum, allow_null=True) -> bool:
    """
    Hard filter on numeric stat. If value is None/0, allow_null decides pass/fail.
    For most stats we use allow_null=True (don't exclude data gaps).
    """
    if value is None:
        return allow_null
    return value >= minimum


def calc_asymmetry_index(player: dict) -> float:
    """
    Triestina Moneyball: goal_contributions / market_value_in_100k
    Higher = more undervalued.
    """
    goals = player.get('goals') or 0
    assists = player.get('assists') or 0
    gc = goals + assists
    mv = player.get('market_value') or 0
    if mv <= 0:
        return gc * 10.0 if gc > 0 else 0.0
    return (gc / (mv / 100000))


def calc_boost_score(player: dict, query: dict) -> float:
    """
    Applies regex pattern boosts from query.scoring_boost.patterns
    against player summary + notes.
    Returns total boost score.
    """
    boost_cfg = query.get('scoring_boost', {})
    patterns = boost_cfg.get('patterns', {})
    if not patterns:
        return 0.0

    text = ' '.join([
        (player.get('summary') or ''),
        (player.get('notes') or ''),
        (player.get('current_club') or ''),
        (player.get('role_name') or ''),
    ]).lower()

    opp_type = (player.get('opportunity_type') or '').lower()
    total = 0.0
    matched_patterns = []

    for pattern, weight in patterns.items():
        try:
            if re.search(pattern, text, re.IGNORECASE):
                total += weight
                matched_patterns.append(f"+{weight} [{pattern}]")
            # Special: opportunity type bonus
            elif pattern in ('svincol', 'svincolato') and opp_type in ('svincolato', 'rescissione'):
                total += weight
                matched_patterns.append(f"+{weight} [opportunity_type={opp_type}]")
            elif pattern == 'scadenza' and opp_type == 'scadenza':
                total += weight
                matched_patterns.append(f"+{weight} [opportunity_type=scadenza]")
        except re.error:
            pass

    return total


def build_match_reasons(player: dict, query: dict, boost_score: float) -> list[str]:
    """Generate human-readable match reasons for a player→query match."""
    reasons = []
    f = query.get('filters', {})

    age = player.get('age')
    if age_is_valid(age):
        ar = f.get('age_range', [])
        if ar and ar[0] <= age <= ar[1]:
            reasons.append(f"Età {age}a nella fascia target [{ar[0]}-{ar[1]}]")

    opp_type = (player.get('opportunity_type') or '').lower()
    if opp_type in ('svincolato', 'rescissione'):
        reasons.append(f"Disponibile a costo zero ({opp_type})")
    elif opp_type == 'scadenza':
        exp = player.get('contract_expires', '')
        reasons.append(f"Contratto in scadenza ({exp})")
    elif opp_type == 'prestito':
        reasons.append("Valutabile in prestito")

    goals = player.get('goals') or 0
    assists = player.get('assists') or 0
    apps = player.get('appearances') or 0
    if apps > 0:
        reasons.append(f"{apps} presenze stagionali")
    if goals > 0:
        gc = goals + assists
        reasons.append(f"{goals} gol, {assists} assist ({gc} contributi offensivi)")

    mv = player.get('market_value')
    if mv:
        mv_max = f.get('market_value_max_eur')
        if mv_max and mv <= mv_max:
            reasons.append(f"Valore TM {mv//1000}k€ (sotto soglia {mv_max//1000}k€)")
        elif not mv_max:
            reasons.append(f"Valore TM {mv//1000}k€")

    if boost_score > 0:
        reasons.append(f"Pattern boost +{boost_score:.1f}pts (testo/profilo)")

    prev = [c for c in (player.get('previous_clubs') or []) if c.lower() not in ('', 'n/d')]
    if len(prev) >= 2:
        reasons.append(f"Esperienza in: {', '.join(prev[:3])}")

    return reasons


def sort_key(player: dict, sort_by: str):
    """
    Returns a sortable tuple for the given sort_by strategy.
    Data tier is always the primary discriminator: fully enriched players rank first.
    """
    tier = -data_tier(player)  # negate: higher tier = more negative = sorts first

    if sort_by == 'goals_desc':
        return (tier, -(player.get('goals') or 0), -(player.get('query_boost_score') or 0))
    elif sort_by == 'goal_contributions_desc':
        gc = (player.get('goals') or 0) + (player.get('assists') or 0)
        return (tier, -gc, -(player.get('query_boost_score') or 0))
    elif sort_by == 'minutes_desc':
        return (tier, -(player.get('minutes_played') or 0), -(player.get('ob1_score') or 0))
    elif sort_by == 'asymmetry_index_desc':
        return (tier, -calc_asymmetry_index(player), -(player.get('query_boost_score') or 0))
    elif sort_by == 'value_growth_potential_desc':
        # Proxy: young age + goals + low market value = high growth potential
        age = player.get('age') if age_is_valid(player.get('age')) else 25
        goals = player.get('goals') or 0
        mv = player.get('market_value') or 999999
        score = goals * 10 - (age or 25) + (500000 - min(mv, 500000)) / 50000
        return (tier, -score)
    else:
        return (tier, -(player.get('ob1_score') or 0), -(player.get('query_boost_score') or 0))


def _completeness_note(player: dict) -> str:
    """Returns a short note describing what data is available/missing."""
    parts = []
    if player.get('appearances'):
        parts.append(f"{player['appearances']} pres.")
    else:
        parts.append('presenze: N/D')
    if player.get('goals') is not None and player.get('appearances'):
        parts.append(f"{player.get('goals', 0)} gol")
    if player.get('market_value'):
        parts.append(f"TM {player['market_value']//1000}k€")
    else:
        parts.append('valore TM: N/D')
    if player.get('contract_expires'):
        parts.append(f"scadenza {player['contract_expires'][:7]}")
    else:
        parts.append('contratto: N/D')
    tier = data_tier(player)
    tier_label = {3: 'ENRICHED', 2: 'PARTIAL', 1: 'MINIMAL'}[tier]
    return f"[{tier_label}] {' | '.join(parts)}"


# ---------------------------------------------------------------------------
# Core query processor
# ---------------------------------------------------------------------------

def process_query(query: dict, players: list[dict], scorer: OB1Scorer) -> dict:
    """
    Process a single query against the full player pool.
    Returns a PLAYER_SCHEMA result block.
    """
    qid = query['query_id']
    f = query.get('filters', {})
    boost_cfg = query.get('scoring_boost', {})
    min_score = boost_cfg.get('min_score', 0.0)

    positions = f.get('position', [])
    age_range = f.get('age_range')
    expires_before = f.get('contract_expires_before')
    max_results = f.get('max_results', 5)
    sort_by = f.get('sort_by', 'ob1_score_desc')
    mv_max = f.get('market_value_max_eur')
    min_goals = f.get('min_goals_season')
    min_apps = f.get('min_appearances_season')
    min_gc = f.get('min_goal_contributions_season')

    candidates = []

    for raw in players:
        # --- Position filter (soft) ---
        if positions and not position_matches(raw, positions):
            continue

        # --- Age filter (soft for nulls) ---
        if not age_matches(raw, age_range):
            continue

        # --- Contract filter (soft for nulls) ---
        if not contract_matches(raw, expires_before):
            continue

        # --- Market value hard cap (only if we have data) ---
        mv = raw.get('market_value')
        if mv_max and mv and mv > mv_max:
            continue

        # --- Stats thresholds ---
        # Soft enforcement: only hard-filter if the player clearly misses
        # the bar (< 50% of threshold). Players without stats pass through.
        # This avoids false negatives from incomplete enrichment.
        goals = raw.get('goals') or 0
        assists = raw.get('assists') or 0
        apps = raw.get('appearances') or 0
        gc = goals + assists

        if min_goals and goals > 0 and goals < min_goals * 0.5:
            continue
        if min_apps and apps > 0 and apps < min_apps * 0.5:
            continue
        if min_gc and gc > 0 and gc < min_gc * 0.5:
            continue

        # --- Compute OB1 base score ---
        score_result = scorer.score(raw)

        # --- Compute boost score ---
        boost = calc_boost_score(raw, query)

        # Note: min_score (text pattern boost threshold) is NOT used for hard
        # exclusion — our auto-generated summaries are too sparse for reliable
        # pattern matching. Boost score is used only for ranking.

        total_score = score_result['ob1_score'] + boost * 2

        tier = data_tier(raw)
        player_result = {
            **raw,
            'ob1_score': score_result['ob1_score'],
            'classification': score_result['classification'],
            'query_boost_score': round(boost, 1),
            'total_score': round(total_score, 1),
            'asymmetry_index': round(calc_asymmetry_index(raw), 3),
            'goal_contributions': gc,
            'data_tier': tier,
        }
        player_result['match_reasons'] = build_match_reasons(player_result, query, boost)
        candidates.append(player_result)

    # Sort
    candidates.sort(key=lambda p: sort_key(p, sort_by))

    # Limit results
    top = candidates[:max_results]

    # Format output records
    matches = []
    for rank, p in enumerate(top, 1):
        matches.append({
            'rank': rank,
            'player_name': p.get('player_name', 'N/D'),
            'age': p.get('age') if age_is_valid(p.get('age')) else None,
            'role': p.get('role', ''),
            'role_name': p.get('role_name', ''),
            'current_club': p.get('current_club', ''),
            'nationality': p.get('nationality'),
            'second_nationality': p.get('second_nationality'),
            'foot': p.get('foot'),
            'appearances_season': p.get('appearances') or 0,
            'goals_season': p.get('goals') or 0,
            'assists_season': p.get('assists') or 0,
            'goal_contributions': p.get('goal_contributions', 0),
            'minutes_played': p.get('minutes_played') or 0,
            'market_value_eur': p.get('market_value'),
            'market_value_formatted': p.get('market_value_formatted'),
            'contract_expires': p.get('contract_expires'),
            'opportunity_type': p.get('opportunity_type'),
            'previous_clubs': p.get('previous_clubs', []),
            'agent': p.get('agent'),
            'ob1_score': p.get('ob1_score'),
            'classification': p.get('classification'),
            'query_boost_score': p.get('query_boost_score'),
            'total_score': p.get('total_score'),
            'asymmetry_index': p.get('asymmetry_index'),
            'match_reasons': p.get('match_reasons', []),
            'summary': p.get('summary', ''),
            'tm_url': p.get('tm_url'),
            'source_url': p.get('source_url'),
            'source_name': p.get('source_name'),
            # Data quality
            'data_tier': p.get('data_tier', 1),
            'data_completeness_note': _completeness_note(p),
        })

    return {
        'query_id': qid,
        'target_club': query.get('target_club', ''),
        'tier': query.get('tier', ''),
        'critical_role': query.get('critical_role', ''),
        'strategic_context': query.get('strategic_context', ''),
        'notes': query.get('notes', ''),
        'filters_applied': {
            'position': positions,
            'age_range': age_range,
            'contract_expires_before': expires_before,
            'market_value_max_eur': mv_max,
            'min_goals_season': min_goals,
            'min_appearances_season': min_apps,
            'min_goal_contributions_season': min_gc,
        },
        'total_candidates': len(candidates),
        'total_returned': len(matches),
        'matches': matches,
    }


# ---------------------------------------------------------------------------
# Dedup & pre-filter (mirror generate_dashboard.py logic)
# ---------------------------------------------------------------------------

JUNK_NAMES = {
    'N/D', '', 'n/d',
    'La Página Millonaria', 'Contrato Libre Mercado Pases Argentina',
    'Assistir Esporte Espetacular', 'La Casa', 'Portal Brazuca',
    'De Chiquito Romero', 'Primera Nacional', 'Paulo Sub',
    # News brands / sites scraped as player names
    'Tutto Calcio Catania', 'Le Ultime Notizie', 'Sky Sport', 'Ultimo Uomo',
}

# Minimal player name: must have at least 2 "words" OR be known short single-name nickname
# Single-word entries that are role_name="Non Specificato" with no stats are low-confidence
_SINGLE_NAME_MIN_CHARS = 5   # "Saio" is ok, but "Bra" is a club name

# Club/organization name keywords that appear in "player_name" by mistake
ENTITY_BLACKLIST_KEYWORDS = [
    'calcio', 'sport', 'notizie', 'uomo', 'catania', 'portal', 'primera',
    'news', 'blog', 'rivista', 'magazine', 'tv', 'radio',
]

# Role names that signal no useful position data
NULL_ROLE_VALUES = {'', 'n/d', 'non specificato', 'non specificato', 'calciatore', 'allenatore'}


def is_plausible_player(p: dict) -> bool:
    """
    Heuristic entity validation: True if this entry looks like a real player,
    False if it looks like a news source, club name, or catch-all article.
    """
    name = (p.get('player_name') or '').strip()

    # 1. Reject known junk
    if name in JUNK_NAMES:
        return False

    # 2. Name must not contain organization keywords
    name_lower = name.lower()
    if any(kw in name_lower for kw in ENTITY_BLACKLIST_KEYWORDS):
        return False

    # 3. Must have EITHER a real age OR a real role (from generate_dashboard.py logic)
    has_age = p.get('age') is not None
    role_raw = (p.get('role_name') or p.get('role') or '').strip().lower()
    has_role = role_raw not in NULL_ROLE_VALUES

    if not has_age and not has_role:
        return False  # pure junk

    # 4. If single-word name + role_name="Non Specificato" + no stats → low-confidence, skip
    words = name.split()
    role_name_lower = (p.get('role_name') or '').strip().lower()
    if (len(words) == 1 and
            role_name_lower in ('non specificato', 'n/d', '') and
            not p.get('appearances') and
            not p.get('goals') and
            not p.get('market_value')):
        return False

    return True


def prefilter_players(raw: list[dict]) -> list[dict]:
    """Remove junk entries, deduplicate by name."""
    generic_patterns = [
        '/transfers/wettbewerb/', '/serie-d-girone', '/serie-c-girone',
        '/startseite/wettbewerb/', '/spieltagtabelle/',
    ]

    seen_names = set()
    out = []
    for p in raw:
        name = (p.get('player_name') or '').strip()
        if not name:
            continue

        # Entity validation
        if not is_plausible_player(p):
            continue

        src_url = (p.get('source_url') or '').lower()
        if any(pat in src_url for pat in generic_patterns):
            continue

        league_id = p.get('league_id', '')
        if league_id and not league_id.startswith('italy'):
            continue

        # Birth year stored as age → normalize
        age = p.get('age')
        if isinstance(age, int) and 1980 <= age <= 2010:
            p = dict(p)
            p['age'] = TODAY.year - age

        key = name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        out.append(p)

    return out


def data_tier(player: dict) -> int:
    """
    Returns completeness tier for sorting:
    3 = fully enriched (stats + market_value + contract)
    2 = partially enriched (has market_value or stats)
    1 = minimal (just name/role/club from scraping)
    """
    has_stats = bool(player.get('appearances') or player.get('goals'))
    has_mv = bool(player.get('market_value'))
    has_contract = bool(player.get('contract_expires'))
    score = sum([has_stats, has_mv, has_contract])
    if score >= 2:
        return 3
    elif score == 1:
        return 2
    return 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Load players
    opps_file = DATA_DIR / 'opportunities.json'
    if not opps_file.exists():
        print(f"ERROR: {opps_file} not found", file=sys.stderr)
        sys.exit(1)

    raw_players = json.loads(opps_file.read_text(encoding='utf-8'))
    players = prefilter_players(raw_players)
    print(f"Loaded {len(raw_players)} raw entries → {len(players)} after prefilter")

    # Load query config
    if len(sys.argv) > 1:
        cfg_path = Path(sys.argv[1])
        config = json.loads(cfg_path.read_text(encoding='utf-8'))
        print(f"Using query config from: {cfg_path}")
    else:
        config = BUILTIN_QUERIES
        print("Using built-in Gemini Audit Relay query config (2026-04-14)")

    queries = config.get('queries', [])
    meta = config.get('meta', {})

    scorer = OB1Scorer()

    # Process each query
    results = []
    for query in queries:
        qid = query['query_id']
        print(f"\n--- Processing: {qid} ({query.get('target_club')}) ---")
        result = process_query(query, players, scorer)
        results.append(result)
        n = result['total_returned']
        total_c = result['total_candidates']
        print(f"    Candidates: {total_c}  |  Returned: {n}")
        for m in result['matches']:
            mv_str = f"  TM={m['market_value_eur']//1000}k€" if m['market_value_eur'] else ''
            print(f"    #{m['rank']:2} {m['player_name']:30} age={m['age']}  "
                  f"goals={m['goals_season']}  apps={m['appearances_season']}{mv_str}  "
                  f"boost={m['query_boost_score']}  total={m['total_score']}")

    # Build output document
    output_date = TODAY.strftime('%Y-%m-%d')
    output = {
        'meta': {
            **meta,
            'processed_at': datetime.now().isoformat(),
            'source_db': str(opps_file),
            'players_in_db': len(players),
            'queries_processed': len(results),
        },
        'results': results,
        'summary': {
            'by_club': {},
        }
    }

    # Summary by club
    for r in results:
        club = r['target_club']
        if club not in output['summary']['by_club']:
            output['summary']['by_club'][club] = []
        for m in r['matches']:
            output['summary']['by_club'][club].append({
                'query_id': r['query_id'],
                'critical_role': r['critical_role'],
                'player_name': m['player_name'],
                'age': m['age'],
                'total_score': m['total_score'],
                'opportunity_type': m['opportunity_type'],
                'market_value_eur': m['market_value_eur'],
            })

    # Save output
    out_file = DATA_DIR / f'scouting_queries_{output_date}.json'
    out_file.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"\nResults saved: {out_file}")

    # Print summary table
    print("\n" + "=" * 70)
    print("SUMMARY — PLAYER SCHEMA OUTPUT")
    print("=" * 70)
    for r in results:
        print(f"\n[{r['query_id']}] {r['target_club']} — {r['critical_role']}")
        if not r['matches']:
            print("  (no matches in current database)")
            continue
        for m in r['matches']:
            tag = m['classification'].upper() if m['classification'] else '???'
            mv = f"{m['market_value_eur']//1000}k€" if m['market_value_eur'] else '—'
            print(f"  #{m['rank']} {m['player_name']:<28} [{tag}]  "
                  f"age={m['age'] or '?'}  gol={m['goals_season']}  "
                  f"apps={m['appearances_season']}  MV={mv}  "
                  f"boost={m['query_boost_score']}")

    return out_file


if __name__ == '__main__':
    main()
