#!/usr/bin/env python3
"""
OB1 Serie C - Generate Individual + Summary Scouting Reports
For external evaluation by professional scouts.
"""

import sys
import os
import json
import re
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scoring import OB1Scorer

DATA_DIR = Path(__file__).parent.parent / 'data'
DOCS_DIR = Path(__file__).parent.parent / 'docs'
REPORTS_DIR = DOCS_DIR / 'reports' / 'scouting'

# ============================================================================
# HELPERS
# ============================================================================

ROLE_LABELS = {
    'PO': 'Portiere', 'DC': 'Difensore Centrale', 'TD': 'Terzino Destro',
    'TS': 'Terzino Sinistro', 'CC': 'Centrocampista Centrale', 'MED': 'Mediano',
    'TRQ': 'Trequartista', 'AT': 'Attaccante', 'ATT': 'Attaccante',
    'PC': 'Punta Centrale', 'AD': 'Ala Destra', 'AS': 'Ala Sinistra',
    'ED': 'Esterno Destro', 'ES': 'Esterno Sinistro',
}

REPARTO_MAP = {
    'Difesa': ['DC', 'TD', 'TS', 'PO'],
    'Centrocampo': ['CC', 'MED', 'TRQ', 'REG'],
    'Attacco': ['AT', 'ATT', 'PC', 'AD', 'AS', 'ED', 'ES'],
}

TYPE_LABELS = {
    'svincolato': 'Svincolato',
    'rescissione': 'Rescissione consensuale',
    'prestito': 'Disponibile in prestito',
    'scadenza': 'Contratto in scadenza',
    'mercato': 'Sul mercato',
}


def get_role_label(opp):
    return opp.get('role_name') or ROLE_LABELS.get(opp.get('role', ''), opp.get('role', 'N/D'))


def get_type_label(opp):
    raw = (opp.get('opportunity_type', '') or '').lower()
    return TYPE_LABELS.get(raw, raw.capitalize() if raw else 'N/D')


def get_reparto(opp):
    role = opp.get('role', '')
    for reparto, roles in REPARTO_MAP.items():
        if role in roles:
            return reparto
    # Fallback: try role_name
    role_name = (opp.get('role_name', '') or '').lower()
    if any(k in role_name for k in ['portiere', 'difens', 'terzino']):
        return 'Difesa'
    elif any(k in role_name for k in ['centroc', 'median', 'trequart', 'regist', 'mezzala']):
        return 'Centrocampo'
    elif any(k in role_name for k in ['attacc', 'ala', 'punta', 'esterno']):
        return 'Attacco'
    return 'Altro'


def safe_filename(name):
    """Convert player name to safe filename"""
    name = name.lower().strip()
    name = re.sub(r'[àáâã]', 'a', name)
    name = re.sub(r'[èéêë]', 'e', name)
    name = re.sub(r'[ìíîï]', 'i', name)
    name = re.sub(r'[òóôõ]', 'o', name)
    name = re.sub(r'[ùúûü]', 'u', name)
    name = re.sub(r'[^a-z0-9]+', '_', name)
    return name.strip('_')


def format_date_it(dt=None):
    if dt is None:
        dt = datetime.now()
    months = {1:'Gennaio',2:'Febbraio',3:'Marzo',4:'Aprile',5:'Maggio',6:'Giugno',
              7:'Luglio',8:'Agosto',9:'Settembre',10:'Ottobre',11:'Novembre',12:'Dicembre'}
    return f"{dt.day} {months[dt.month]} {dt.year}"


def format_market_value(opp):
    mvf = opp.get('market_value_formatted')
    if mvf and mvf not in ('N/A', 'null', 'None'):
        return mvf
    mv = opp.get('market_value')
    if mv and isinstance(mv, (int, float)) and mv > 0:
        if mv >= 1_000_000:
            return f"€{mv/1_000_000:.1f}M"
        elif mv >= 1_000:
            return f"€{int(mv/1_000)}k"
        else:
            return f"€{int(mv)}"
    return None


def build_scouting_note(opp):
    """Build a football-language scouting note (no tech jargon)"""
    parts = []
    role = get_role_label(opp)
    age = opp.get('age')
    club = opp.get('current_club', '')
    prev = opp.get('previous_clubs', []) or []
    opp_type = (opp.get('opportunity_type', '') or '').lower()
    summary = opp.get('summary', '') or ''
    nationality = opp.get('nationality', '')
    foot = opp.get('foot', '')
    mv = format_market_value(opp)
    appearances = opp.get('appearances')
    goals = opp.get('goals')
    assists = opp.get('assists')
    minutes = opp.get('minutes_played')

    # Opening - status
    if opp_type == 'svincolato':
        club_suffix = f" dopo l'esperienza al {club}" if club else ""
        parts.append(f"{role}, attualmente svincolato{club_suffix}.")
    elif opp_type == 'rescissione':
        parts.append(f"{role}, ha risolto il contratto con {club}." if club else f"{role}, reduce da rescissione consensuale.")
    elif opp_type == 'prestito':
        parts.append(f"{role}{f' in forza al {club}' if club else ''}, disponibile in prestito.")
    else:
        parts.append(f"{role}{f', attualmente al {club}' if club else ''}.")

    # Age context
    if age:
        birth_year = 2026 - age
        if age <= 20:
            parts.append(f"Classe {birth_year}, profilo giovanissimo con margini di crescita importanti.")
        elif age <= 23:
            parts.append(f"Classe {birth_year}, nel pieno del percorso di maturazione.")
        elif age <= 26:
            parts.append(f"Classe {birth_year}, profilo che unisce gioventù ed esperienza.")

    # Nationality + foot
    extra = []
    if nationality:
        nat_str = nationality.strip().title()
        second_nat = opp.get('second_nationality', '')
        if second_nat and second_nat.lower() not in ('null', 'none', ''):
            nat_str += f"/{second_nat.strip().title()}"
        extra.append(f"nazionalità {nat_str}")
    if foot and foot.lower() not in ('null', 'none', ''):
        foot_map = {'destro': 'piede destro naturale', 'sinistro': 'mancino naturale', 'ambidestro': 'ambidestro'}
        extra.append(foot_map.get(foot.lower(), foot))
    if extra:
        joined = ', '.join(extra)
        parts.append(joined[0].upper() + joined[1:] + '.')

    # Career path
    notable_prev = [c for c in prev if c and c.lower() not in ('', 'n/d', 'svincolato')]
    if len(notable_prev) >= 2:
        parts.append(f"Percorso: {', '.join(notable_prev[:4])}{'...' if len(notable_prev) > 4 else ''}.")
    elif notable_prev:
        parts.append(f"Provenienza: {notable_prev[0]}.")

    # Stats (only if available and meaningful)
    if appearances and appearances > 0:
        stat_parts = [f"{appearances} presenze"]
        if goals and goals > 0:
            stat_parts.append(f"{goals} reti")
        if assists and assists > 0:
            stat_parts.append(f"{assists} assist")
        if minutes and minutes > 0:
            stat_parts.append(f"{minutes:,} minuti".replace(',', '.'))
        parts.append(f"Stagione corrente: {', '.join(stat_parts)}.")

    # Market value
    if mv:
        parts.append(f"Valutazione Transfermarkt: {mv}.")

    # Summary info (only if adds value)
    if summary and len(summary) > 40:
        # Don't repeat what we already said
        clean = summary.strip()
        # Only include if it adds new info
        if not any(keyword in clean.lower() for keyword in [club.lower() if club else 'zzz', 'svincolato', 'rescissione']):
            parts.append(clean)

    return ' '.join(parts)


# ============================================================================
# SHARED CSS
# ============================================================================

SHARED_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: 'Georgia', 'Times New Roman', serif;
        background: #fafafa;
        color: #2c2c2c;
        line-height: 1.7;
        font-size: 15px;
    }
    .container { max-width: 960px; margin: 0 auto; padding: 20px; }
    .table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }

    header {
        background: #1a1a2e;
        color: white;
        padding: 35px 30px;
        border-radius: 8px;
        margin-bottom: 25px;
        position: relative;
        overflow: hidden;
    }
    header::after {
        content: '';
        position: absolute;
        top: 0; right: 0;
        width: 200px; height: 100%;
        background: linear-gradient(135deg, transparent 50%, rgba(255,255,255,0.03) 50%);
    }
    header h1 {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        font-size: 1.3em;
        font-weight: 700;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-bottom: 2px;
    }
    header .subtitle {
        font-size: 1em;
        opacity: 0.9;
        margin-top: 6px;
    }
    header .confidential {
        font-size: 0.72em;
        opacity: 0.5;
        margin-top: 10px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .card {
        background: white;
        border-radius: 8px;
        padding: 25px;
        margin-bottom: 20px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        border-left: 4px solid #ddd;
    }
    .card.hot { border-left-color: #c0392b; }
    .card.warm { border-left-color: #f39c12; }

    .player-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 12px;
    }
    .player-name {
        font-family: -apple-system, sans-serif;
        font-size: 1.3em;
        font-weight: 700;
        color: #1a1a2e;
    }
    .player-meta {
        font-size: 0.85em;
        color: #666;
        margin-top: 2px;
    }

    .score-badge {
        font-family: -apple-system, sans-serif;
        font-weight: 700;
        font-size: 1.3em;
        padding: 6px 14px;
        border-radius: 6px;
        min-width: 50px;
        text-align: center;
    }
    .score-badge.hot { background: #fdecea; color: #c0392b; }
    .score-badge.warm { background: #fef5e7; color: #e67e22; }
    .score-badge.cold { background: #eef2f7; color: #7f8c8d; }

    .tags {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 14px;
    }
    .tag {
        font-family: -apple-system, sans-serif;
        font-size: 0.72em;
        padding: 3px 10px;
        border-radius: 3px;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .tag.svincolato { background: #d5f5e3; color: #1e8449; }
    .tag.rescissione { background: #fef9e7; color: #9a7d0a; }
    .tag.prestito { background: #d6eaf8; color: #1a5276; }
    .tag.mercato { background: #eaecee; color: #566573; }
    .tag.scadenza { background: #fadbd8; color: #922b21; }
    .tag.reparto { background: #e8e8e8; color: #555; }

    .narrative {
        color: #444;
        margin-bottom: 14px;
        text-align: justify;
    }

    .info-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 8px 20px;
        background: #f9f9f9;
        border-radius: 6px;
        padding: 14px 18px;
        margin-bottom: 14px;
    }
    .info-item {
        font-size: 0.88em;
    }
    .info-label {
        font-family: -apple-system, sans-serif;
        font-size: 0.72em;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #888;
    }
    .info-value {
        color: #333;
        font-weight: 500;
    }

    .score-detail {
        background: #f9f9f9;
        border-radius: 6px;
        padding: 14px;
        margin-top: 10px;
    }
    .score-detail-title {
        font-family: -apple-system, sans-serif;
        font-size: 0.75em;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #888;
        margin-bottom: 8px;
    }
    .factor-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 4px;
    }
    .factor-label {
        font-family: -apple-system, sans-serif;
        font-size: 0.75em;
        color: #666;
        min-width: 160px;
    }
    .factor-bar-bg {
        flex: 1;
        height: 6px;
        background: #e8e8e8;
        border-radius: 3px;
        overflow: hidden;
    }
    .factor-bar {
        height: 100%;
        border-radius: 3px;
    }
    .factor-val {
        font-family: -apple-system, sans-serif;
        font-size: 0.75em;
        font-weight: 600;
        color: #444;
        min-width: 25px;
        text-align: right;
    }

    .source-link {
        color: #2980b9;
        text-decoration: none;
        font-size: 0.8em;
    }
    .source-link:hover { text-decoration: underline; }

    /* Summary table */
    .summary-table {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 20px;
    }
    .summary-table th {
        font-family: -apple-system, sans-serif;
        font-size: 0.75em;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #888;
        text-align: left;
        padding: 10px 8px;
        border-bottom: 2px solid #eee;
    }
    .summary-table td {
        padding: 10px 8px;
        border-bottom: 1px solid #f5f5f5;
        font-size: 0.9em;
    }
    .summary-table tr:hover { background: #fafafa; }
    .summary-table a { color: #1a1a2e; text-decoration: none; font-weight: 600; }
    .summary-table a:hover { text-decoration: underline; }

    footer {
        text-align: center;
        padding: 25px 20px;
        color: #aaa;
        font-size: 0.8em;
        border-top: 1px solid #eee;
        margin-top: 30px;
    }
    footer a { color: #666; }

    @media print {
        body { background: white; font-size: 12px; }
        .container { max-width: 100%; padding: 0; }
        .card, header { box-shadow: none; border: 1px solid #ddd; page-break-inside: avoid; }
        header { background: #333 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
    @media (max-width: 600px) {
        .player-header { flex-direction: column; gap: 8px; }
        .info-grid { grid-template-columns: 1fr; }
        .factor-label { min-width: 100px; font-size: 0.65em; }
    }
"""

SCORE_FACTOR_LABELS = {
    'freshness': 'Attualità notizia',
    'opportunity_type': 'Tipo opportunità',
    'experience': 'Esperienza verificata',
    'age': 'Profilo anagrafico',
    'market_value': 'Valore di mercato',
    'league_fit': 'Pertinenza Serie C',
    'source': 'Affidabilità fonte',
    'completeness': 'Completezza dati',
}


def build_score_bars_html(breakdown):
    if not breakdown:
        return ''
    bars = []
    for key in ['freshness', 'opportunity_type', 'experience', 'age', 'market_value', 'league_fit', 'source', 'completeness']:
        val = breakdown.get(key, 0)
        label = SCORE_FACTOR_LABELS.get(key, key)
        color = '#27ae60' if val >= 80 else '#f39c12' if val >= 60 else '#e74c3c'
        bars.append(f'''<div class="factor-row">
            <span class="factor-label">{label}</span>
            <div class="factor-bar-bg"><div class="factor-bar" style="width:{val}%;background:{color}"></div></div>
            <span class="factor-val">{val}</span>
        </div>''')
    return '\n'.join(bars)


# ============================================================================
# INDIVIDUAL REPORT
# ============================================================================

def generate_individual_report(opp, date_str):
    name = opp.get('player_name', 'N/D')
    score = opp.get('ob1_score', 0)
    classification = 'hot' if score >= 70 else 'warm' if score >= 57 else 'cold'
    role = get_role_label(opp)
    age = opp.get('age')
    club = opp.get('current_club', '')
    opp_type = (opp.get('opportunity_type', '') or '').lower()
    nationality = opp.get('nationality', '')
    foot = opp.get('foot', '')
    mv = format_market_value(opp)
    reparto = get_reparto(opp)
    tm_url = opp.get('tm_url', '')
    source_url = opp.get('source_url', '')
    appearances = opp.get('appearances')
    goals = opp.get('goals')
    assists = opp.get('assists')
    minutes = opp.get('minutes_played')
    agent = opp.get('agent', '')
    height = opp.get('height_cm')
    prev_clubs = opp.get('previous_clubs', []) or []

    narrative = build_scouting_note(opp)
    score_bars = build_score_bars_html(opp.get('score_breakdown', {}))

    meta_parts = [role]
    if age:
        meta_parts.append(f'{age} anni (classe {2026-age})')
    if club:
        meta_parts.append(club)
    meta_line = ' · '.join(meta_parts)

    # Info grid items
    info_items = []
    info_items.append(('Ruolo', role))
    if age:
        info_items.append(('Età', f'{age} anni (classe {2026-age})'))
    info_items.append(('Nazionalità', nationality or 'Da verificare'))
    if foot and foot.lower() not in ('null', 'none', ''):
        info_items.append(('Piede', foot.capitalize()))
    if height and str(height) not in ('null', 'None', '0'):
        info_items.append(('Altezza', f'{height} cm'))
    info_items.append(('Club attuale', club or 'Svincolato'))
    info_items.append(('Status', get_type_label(opp)))
    if mv:
        info_items.append(('Valore TM', mv))
    if agent and agent.lower() not in ('null', 'none', ''):
        info_items.append(('Agente', agent))

    # Stats section
    stats_items = []
    if appearances and appearances > 0:
        stats_items.append(('Presenze', str(appearances)))
    if goals is not None and goals > 0:
        stats_items.append(('Gol', str(goals)))
    if assists is not None and assists > 0:
        stats_items.append(('Assist', str(assists)))
    if minutes and minutes > 0:
        stats_items.append(('Minuti', f'{minutes:,}'.replace(',', '.')))

    info_grid_html = ''
    for label, value in info_items:
        info_grid_html += f'<div class="info-item"><div class="info-label">{label}</div><div class="info-value">{value}</div></div>\n'

    stats_html = ''
    if stats_items:
        stats_html = '<div class="info-grid" style="margin-top:12px;">\n'
        for label, value in stats_items:
            stats_html += f'<div class="info-item"><div class="info-label">{label} (stagione)</div><div class="info-value">{value}</div></div>\n'
        stats_html += '</div>\n'

    links_html = ''
    if tm_url and 'transfermarkt' in tm_url:
        links_html += f'<a class="source-link" href="{tm_url}" target="_blank">Profilo Transfermarkt</a> '
    if source_url and 'transfermarkt' not in source_url:
        links_html += f'<a class="source-link" href="{source_url}" target="_blank">Fonte originale</a>'

    html = f'''<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OB1 Scout — {name}</title>
    <style>{SHARED_CSS}</style>
</head>
<body>
    <div class="container">
        <header>
            <h1>OB1 Scout</h1>
            <div class="subtitle">Scheda Giocatore — {name}</div>
            <div class="confidential">Serie C · {date_str} · Uso interno</div>
        </header>

        <div class="card {classification}">
            <div class="player-header">
                <div>
                    <div class="player-name">{name}</div>
                    <div class="player-meta">{meta_line}</div>
                </div>
                <div class="score-badge {classification}">{score}</div>
            </div>

            <div class="tags">
                <span class="tag {opp_type}">{get_type_label(opp)}</span>
                <span class="tag reparto">{reparto}</span>
            </div>

            <div class="narrative">{narrative}</div>

            <div class="info-grid">
                {info_grid_html}
            </div>

            {stats_html}

            <div class="score-detail">
                <div class="score-detail-title">Analisi opportunità OB1</div>
                {score_bars}
            </div>

            {'<div style="margin-top:12px">' + links_html + '</div>' if links_html else ''}
        </div>

        <div style="background:white;border-radius:8px;padding:18px 22px;margin-top:15px;box-shadow:0 1px 4px rgba(0,0,0,0.06);font-size:0.85em;color:#666;">
            <strong style="color:#1a1a2e;">Come leggere lo Score OB1</strong><br>
            Lo score (0-100) valuta l'<em>opportunità di mercato</em>, non il talento del giocatore.
            Un punteggio alto indica: notizia recente, tipo di opportunità vantaggioso (svincolato &gt; prestito &gt; mercato),
            profilo anagrafico in target, esperienza verificata, fonte affidabile.
        </div>

        <footer>
            <p>OB1 Scout — Report generato il {date_str}</p>
            <p><a href="index.html">Torna al riepilogo</a></p>
        </footer>
    </div>
</body>
</html>'''
    return html


# ============================================================================
# SUMMARY REPORT
# ============================================================================

def generate_summary_report(players, date_str):
    total = len(players)
    hot = [p for p in players if p.get('ob1_score', 0) >= 70]
    warm = [p for p in players if 57 <= p.get('ob1_score', 0) < 70]

    # Count by reparto
    by_reparto = {}
    for p in players:
        rep = get_reparto(p)
        by_reparto[rep] = by_reparto.get(rep, 0) + 1

    # Count by type
    by_type = {}
    for p in players:
        t = get_type_label(p)
        by_type[t] = by_type.get(t, 0) + 1

    reparto_summary = ', '.join(f'{v} {k.lower()}' for k, v in sorted(by_reparto.items()))

    # Table rows
    table_rows = ''
    for i, p in enumerate(players, 1):
        name = p.get('player_name', 'N/D')
        score = p.get('ob1_score', 0)
        cls = 'hot' if score >= 70 else 'warm' if score >= 57 else 'cold'
        age = p.get('age', '-')
        role = get_role_label(p)
        club = p.get('current_club', '-')
        nationality = p.get('nationality', '-')
        opp_type = (p.get('opportunity_type', '') or '').lower()
        mv = format_market_value(p) or '-'
        filename = safe_filename(name) + '.html'
        reparto = get_reparto(p)

        # Stats inline
        app = p.get('appearances')
        gol = p.get('goals')
        stats_str = ''
        if app and app > 0:
            stats_str = f'{app} pres.'
            if gol and gol > 0:
                stats_str += f', {gol} gol'

        table_rows += f'''<tr>
            <td style="font-weight:600"><a href="{filename}">{name}</a></td>
            <td>{age if age and age != '-' else '-'}</td>
            <td>{role}</td>
            <td>{club}</td>
            <td>{nationality}</td>
            <td><span class="tag {opp_type}" style="font-size:0.7em">{get_type_label(p)}</span></td>
            <td>{mv}</td>
            <td>{stats_str or '-'}</td>
            <td><span class="score-badge {cls}" style="font-size:0.85em;padding:3px 8px">{score}</span></td>
        </tr>\n'''

    html = f'''<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OB1 Serie C — Top Segnalazioni Under 23</title>
    <style>{SHARED_CSS}
    .stats-bar {{
        display: flex;
        gap: 25px;
        flex-wrap: wrap;
        margin-top: 15px;
    }}
    .stat-item {{
        text-align: center;
    }}
    .stat-val {{
        font-family: -apple-system, sans-serif;
        font-size: 1.8em;
        font-weight: 700;
        color: #1a1a2e;
    }}
    .stat-val.hot {{ color: #c0392b; }}
    .stat-val.green {{ color: #27ae60; }}
    .stat-lbl {{
        font-family: -apple-system, sans-serif;
        font-size: 0.72em;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>OB1 Scout</h1>
            <div class="subtitle">Top Segnalazioni Under 23 — Serie C</div>
            <div class="confidential">{date_str} · Uso interno</div>
        </header>

        <div class="card" style="border-left-color:#1a1a2e;">
            <div class="score-detail-title">Panoramica</div>
            <p style="color:#444;margin-bottom:8px;">
                {total} profili Under 23 selezionati dal radar OB1 Serie C.
                Distribuzione per reparto: {reparto_summary}.
            </p>
            <div class="stats-bar">
                <div class="stat-item">
                    <div class="stat-val hot">{len(hot)}</div>
                    <div class="stat-lbl">Priorità alta</div>
                </div>
                <div class="stat-item">
                    <div class="stat-val">{len(warm)}</div>
                    <div class="stat-lbl">Da monitorare</div>
                </div>
                <div class="stat-item">
                    <div class="stat-val green">{total}</div>
                    <div class="stat-lbl">Totale U23</div>
                </div>
            </div>
        </div>

        <div class="card table-scroll" style="border-left-color:#1a1a2e;padding:15px 20px;">
            <table class="summary-table" style="min-width:800px;">
                <thead>
                    <tr>
                        <th>Giocatore</th>
                        <th>Età</th>
                        <th>Ruolo</th>
                        <th>Club</th>
                        <th>Naz.</th>
                        <th>Status</th>
                        <th>Valore</th>
                        <th>Stats</th>
                        <th>Score</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>

        <div style="background:white;border-radius:8px;padding:18px 22px;margin-top:15px;box-shadow:0 1px 4px rgba(0,0,0,0.06);font-size:0.85em;color:#666;">
            <strong style="color:#1a1a2e;">Note metodologiche</strong><br>
            Lo <strong>Score OB1</strong> (0-100) misura la qualità dell'opportunità di mercato: attualità della notizia,
            tipo di disponibilità (svincolato/prestito/mercato), profilo anagrafico, esperienza, affidabilità della fonte, pertinenza Serie C.
            <em>Non è un giudizio tecnico sul giocatore.</em><br><br>
            I dati sono raccolti da fonti pubbliche (TuttoC, Calciomercato.com, Transfermarkt) e verificabili.
            Clicca sul nome del giocatore per la scheda individuale completa.
        </div>

        <footer>
            <p>OB1 Scout — Report generato il {date_str}</p>
        </footer>
    </div>
</body>
</html>'''
    return html


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 60)
    print("OB1 SCOUTING REPORTS - Individual + Summary")
    print("=" * 60)

    # Load data
    data_file = DOCS_DIR / 'data.json'
    if not data_file.exists():
        data_file = DATA_DIR / 'opportunities.json'

    if not data_file.exists():
        print("No data file found!")
        return

    data = json.loads(data_file.read_text(encoding='utf-8'))
    opportunities = data.get('opportunities', data) if isinstance(data, dict) else data

    print(f"Loaded {len(opportunities)} opportunities")

    # Apply scoring if not already scored
    scorer = OB1Scorer()
    for opp in opportunities:
        if not opp.get('ob1_score'):
            result = scorer.score(opp)
            opp['ob1_score'] = result['ob1_score']
            opp['classification'] = result['classification']
            opp['score_breakdown'] = result['score_breakdown']

    # Filter: only Italian entries, valid player names, deduplicated
    seen = set()
    filtered = []
    for opp in opportunities:
        name = (opp.get('player_name', '') or '').strip()
        if not name or len(name) < 3:
            continue
        league = opp.get('league_id', '')
        if league and not league.startswith('italy'):
            continue
        name_key = name.lower()
        if name_key in seen:
            continue
        seen.add(name_key)
        filtered.append(opp)

    print(f"After dedup/filter: {len(filtered)} unique Italian players")

    # Filter U23 (born 2003 or later = age <= 23 in 2026)
    u23 = [o for o in filtered if o.get('age') and o['age'] <= 23]
    print(f"Under 23 players: {len(u23)}")

    # Sort by score
    u23.sort(key=lambda x: x.get('ob1_score', 0), reverse=True)

    # Take top 15 (or all if fewer)
    top = u23[:15]
    print(f"Top segnalazioni: {len(top)}")

    if not top:
        print("\nWARNING: No U23 players found with age data!")
        print("Falling back to all players with age data...")
        all_with_age = [o for o in filtered if o.get('age')]
        all_with_age.sort(key=lambda x: x.get('ob1_score', 0), reverse=True)
        top = all_with_age[:15]
        print(f"Fallback: using top {len(top)} players with age data")

    if not top:
        print("ERROR: No players with age data available. Cannot generate reports.")
        return

    # Create output directory
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    date_str = format_date_it()
    print(f"\nDate: {date_str}")

    # Print quality report
    print("\n--- DATA QUALITY CHECK ---")
    issues = []
    for p in top:
        name = p.get('player_name')
        missing = []
        if not p.get('age'):
            missing.append('età')
        if not p.get('nationality'):
            missing.append('nazionalità')
        if not p.get('current_club'):
            missing.append('club')
        if not p.get('role') and not p.get('role_name'):
            missing.append('ruolo')
        if missing:
            issues.append(f"  {name}: mancano {', '.join(missing)}")

    if issues:
        print("Dati incompleti:")
        for issue in issues:
            print(issue)
    else:
        print("Tutti i profili hanno dati completi.")

    # Generate individual reports
    print("\n--- GENERATING INDIVIDUAL REPORTS ---")
    for p in top:
        name = p.get('player_name', 'N/D')
        filename = safe_filename(name) + '.html'
        html = generate_individual_report(p, date_str)
        filepath = REPORTS_DIR / filename
        filepath.write_text(html, encoding='utf-8')
        score = p.get('ob1_score', 0)
        age = p.get('age', '?')
        print(f"  {name} (age={age}, score={score}) -> {filename}")

    # Generate summary report
    print("\n--- GENERATING SUMMARY REPORT ---")
    summary_html = generate_summary_report(top, date_str)
    summary_path = REPORTS_DIR / 'index.html'
    summary_path.write_text(summary_html, encoding='utf-8')
    print(f"  Summary -> {summary_path}")

    print(f"\n{'='*60}")
    print(f"DONE! {len(top)} individual reports + 1 summary")
    print(f"Output: {REPORTS_DIR}")
    print(f"{'='*60}")

    # Print final list
    print("\nGiocatori selezionati:")
    for i, p in enumerate(top, 1):
        name = p.get('player_name', 'N/D')
        age = p.get('age', '?')
        role = get_role_label(p)
        club = p.get('current_club', '?')
        score = p.get('ob1_score', 0)
        cls = 'HOT' if score >= 70 else 'WARM' if score >= 57 else 'COLD'
        print(f"  {i:2d}. [{cls:4s}] {name:25s} {str(age):>3s} {role:25s} {str(club):20s} Score: {score}")


if __name__ == "__main__":
    main()
