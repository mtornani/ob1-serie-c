#!/usr/bin/env python3
"""
OB1 Scout - Generate Professional Scouting Report (HTML)
Report narrativo stile osservatore professionista.
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / 'data'
DOCS_DIR = Path(__file__).parent.parent / 'docs'

# ============================================================================
# NARRATIVE HELPERS
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
    'Centrocampo': ['CC', 'MED', 'TRQ'],
    'Attacco': ['AT', 'ATT', 'PC', 'AD', 'AS', 'ED', 'ES'],
}

TYPE_LABELS = {
    'svincolato': 'Svincolato',
    'rescissione': 'Rescissione consensuale',
    'prestito': 'Disponibile in prestito',
    'scadenza': 'Contratto in scadenza',
    'mercato': 'Sul mercato',
}

SCORE_FACTOR_LABELS = {
    'freshness': 'Attualità notizia',
    'opportunity_type': 'Tipo opportunità',
    'experience': 'Esperienza verificata',
    'age': 'Profilo anagrafico',
    'source': 'Affidabilità fonte',
    'completeness': 'Completezza dati',
}

SCORE_WEIGHTS = {
    'freshness': 20,
    'opportunity_type': 20,
    'experience': 20,
    'age': 20,
    'source': 10,
    'completeness': 10,
}


def get_role_label(opp):
    """Role label from role_name or role code."""
    return opp.get('role_name') or ROLE_LABELS.get(opp.get('role', ''), opp.get('role', 'N/D'))


def get_type_label(opp):
    """Human-readable opportunity type."""
    raw = (opp.get('opportunity_type', '') or '').lower()
    return TYPE_LABELS.get(raw, raw.capitalize() if raw else 'N/D')


def get_age_label(opp):
    """Age with category context."""
    age = opp.get('age')
    if not age:
        return 'Età da verificare'
    if age <= 21:
        return f'{age} anni (giovane, alto potenziale)'
    elif age <= 25:
        return f'{age} anni (fascia ideale)'
    elif age <= 28:
        return f'{age} anni (piena maturità)'
    elif age <= 31:
        return f'{age} anni (esperienza, affidabilità)'
    else:
        return f'{age} anni (veterano)'


def build_narrative(opp):
    """Genera un paragrafo narrativo stile osservatore per il giocatore."""
    name = opp.get('player_name', 'N/D')
    role = get_role_label(opp)
    age = opp.get('age')
    club = opp.get('current_club', '')
    prev = opp.get('previous_clubs', []) or []
    opp_type = (opp.get('opportunity_type', '') or '').lower()
    summary = opp.get('summary', '') or ''
    nationality = opp.get('nationality')
    foot = opp.get('foot')
    market_value = opp.get('market_value_formatted') or opp.get('market_value')

    parts = []

    # Opening line - role + status
    if opp_type == 'svincolato':
        if club:
            parts.append(f'{role}, svincolato dopo l\'esperienza con {club}.')
        else:
            parts.append(f'{role}, attualmente svincolato e disponibile a parametro zero.')
    elif opp_type == 'rescissione':
        parts.append(f'{role}, ha risolto consensualmente il contratto con {club}.' if club
                      else f'{role}, reduce da una rescissione consensuale.')
    elif opp_type == 'prestito':
        parts.append(f'{role} di proprietà {club}, disponibile in prestito.' if club
                      else f'{role}, disponibile in prestito.')
    else:
        parts.append(f'{role}{f", attualmente al {club}" if club else ""}.')

    # Age + nationality context
    age_parts = []
    if age:
        if age <= 23:
            age_parts.append(f'Classe {2026 - age}, profilo Under 23 interessante per investimento tecnico')
        elif age <= 28:
            age_parts.append(f'{age} anni, nel pieno della maturità calcistica')
        else:
            age_parts.append(f'{age} anni, porta esperienza e conoscenza della categoria')
    if nationality:
        age_parts.append(f'nazionalità {nationality}')
    if foot:
        foot_map = {'destro': 'piede destro', 'sinistro': 'mancino', 'ambidestro': 'ambidestro'}
        age_parts.append(foot_map.get(foot.lower(), foot))
    if age_parts:
        parts.append(', '.join(age_parts) + '.')

    # Career path
    if prev and len(prev) >= 2:
        clubs_str = ', '.join(prev[:4])
        parts.append(f'Percorso: {clubs_str}{"..." if len(prev) > 4 else ""}.')
    elif prev and len(prev) == 1:
        parts.append(f'Provenienza: {prev[0]}.')

    # Market value
    if market_value:
        if isinstance(market_value, (int, float)) and market_value > 0:
            if market_value >= 1_000_000:
                mv_str = f'€{market_value / 1_000_000:.1f}M'
            else:
                mv_str = f'€{market_value / 1_000:.0f}k'
            parts.append(f'Valutazione Transfermarkt: {mv_str}.')
        elif isinstance(market_value, str):
            parts.append(f'Valutazione Transfermarkt: {market_value}.')

    # Summary - use it if it adds info beyond what we already said
    if summary and len(summary) > 30:
        # Clean up summary: remove redundant info
        clean = summary.strip()
        # Don't repeat what we already said
        if name.lower() not in clean.lower()[:len(name)+5]:
            parts.append(clean)
        else:
            # Skip the name prefix and use the rest
            # e.g. "Alex Rolfini ha risolto..." -> skip, we already said it
            # But if it has unique info, keep it
            if len(clean) > 80:
                parts.append(clean)

    return ' '.join(parts)


def build_score_breakdown_html(opp):
    """Genera la barra di breakdown dello score."""
    breakdown = opp.get('score_breakdown', {})
    score = opp.get('ob1_score', 0)

    if not breakdown:
        return ''

    bars = []
    for key in ['freshness', 'opportunity_type', 'experience', 'age', 'source', 'completeness']:
        val = breakdown.get(key, 0)
        weight = SCORE_WEIGHTS.get(key, 0)
        label = SCORE_FACTOR_LABELS.get(key, key)
        contribution = round(val * weight / 100)  # Actual weighted contribution

        if val >= 80:
            color = '#27ae60'
        elif val >= 60:
            color = '#f39c12'
        else:
            color = '#e74c3c'

        bars.append(f'''<div class="factor-row">
                <span class="factor-label">{label} ({weight}%)</span>
                <div class="factor-bar-bg">
                    <div class="factor-bar" style="width:{val}%;background:{color}"></div>
                </div>
                <span class="factor-val">{val}</span>
            </div>''')

    return '\n'.join(bars)


def data_confidence_label(opp):
    """Returns a data confidence assessment."""
    filled = 0
    total = 6
    if opp.get('age'):
        filled += 1
    if opp.get('nationality'):
        filled += 1
    if opp.get('foot'):
        filled += 1
    if opp.get('market_value') or opp.get('market_value_formatted'):
        filled += 1
    if opp.get('previous_clubs') and len(opp.get('previous_clubs', [])) > 0:
        filled += 1
    if opp.get('summary') and len(opp.get('summary', '')) > 50:
        filled += 1

    if filled >= 5:
        return 'Profilo verificato', 'verified'
    elif filled >= 3:
        return 'Dati parziali', 'partial'
    else:
        return 'Da approfondire', 'minimal'


# ============================================================================
# HTML GENERATION
# ============================================================================

def generate_html_report(opportunities: list, dna_matches: list = None) -> str:
    """Genera report HTML con tono da osservatore professionista."""

    today = datetime.now()
    date_str = today.strftime("%d %B %Y").replace(
        'January', 'Gennaio').replace('February', 'Febbraio').replace(
        'March', 'Marzo').replace('April', 'Aprile').replace(
        'May', 'Maggio').replace('June', 'Giugno').replace(
        'July', 'Luglio').replace('August', 'Agosto').replace(
        'September', 'Settembre').replace('October', 'Ottobre').replace(
        'November', 'Novembre').replace('December', 'Dicembre')

    # Stats
    total = len(opportunities)
    hot = [o for o in opportunities if o.get('ob1_score', 0) >= 80]
    warm = [o for o in opportunities if 60 <= o.get('ob1_score', 0) < 80]
    svincolati = [o for o in opportunities if 'svincolato' in (o.get('opportunity_type', '') or '').lower()]
    rescissioni = [o for o in opportunities if 'rescissione' in (o.get('opportunity_type', '') or '').lower()]
    prestiti = [o for o in opportunities if 'prestito' in (o.get('opportunity_type', '') or '').lower()]

    # Top profiles (deduplicated by player name)
    seen_names = set()
    top_list = []
    for o in sorted(opportunities, key=lambda x: x.get('ob1_score', 0), reverse=True):
        name = o.get('player_name', '').lower()
        if name not in seen_names:
            seen_names.add(name)
            top_list.append(o)
        if len(top_list) >= 10:
            break

    # Group by reparto
    by_reparto = {}
    for reparto, roles in REPARTO_MAP.items():
        players = [o for o in opportunities if o.get('role', '') in roles]
        if players:
            by_reparto[reparto] = sorted(players, key=lambda x: x.get('ob1_score', 0), reverse=True)

    # Market narrative intro
    intro_parts = []
    if svincolati:
        intro_parts.append(f'{len(svincolati)} profili svincolati')
    if rescissioni:
        intro_parts.append(f'{len(rescissioni)} rescissioni consensuali')
    if prestiti:
        intro_parts.append(f'{len(prestiti)} disponibili in prestito')
    market_summary = ', '.join(intro_parts) if intro_parts else f'{total} opportunità monitorate'

    html = f'''<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OB1 Scout — Report Mercato {date_str}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Georgia', 'Times New Roman', serif;
            background: #fafafa;
            color: #2c2c2c;
            line-height: 1.7;
            font-size: 15px;
        }}
        .container {{ max-width: 860px; margin: 0 auto; padding: 20px; }}

        /* Header */
        header {{
            background: #1a1a2e;
            color: white;
            padding: 40px 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            position: relative;
            overflow: hidden;
        }}
        header::after {{
            content: '';
            position: absolute;
            top: 0; right: 0;
            width: 200px; height: 100%;
            background: linear-gradient(135deg, transparent 50%, rgba(255,255,255,0.03) 50%);
        }}
        header h1 {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 1.4em;
            font-weight: 700;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-bottom: 2px;
        }}
        header .date {{
            font-size: 1.1em;
            opacity: 0.9;
            margin-top: 8px;
        }}
        header .confidential {{
            font-size: 0.75em;
            opacity: 0.5;
            margin-top: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        /* Market pulse */
        .market-pulse {{
            background: white;
            border-left: 4px solid #1a1a2e;
            padding: 20px 25px;
            margin-bottom: 25px;
            border-radius: 0 8px 8px 0;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        }}
        .market-pulse h2 {{
            font-family: -apple-system, sans-serif;
            font-size: 0.85em;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #888;
            margin-bottom: 8px;
        }}
        .market-pulse .numbers {{
            display: flex;
            gap: 30px;
            margin-top: 12px;
            flex-wrap: wrap;
        }}
        .market-pulse .num {{
            text-align: center;
        }}
        .market-pulse .num .val {{
            font-family: -apple-system, sans-serif;
            font-size: 1.8em;
            font-weight: 700;
            color: #1a1a2e;
        }}
        .market-pulse .num .val.hot {{ color: #c0392b; }}
        .market-pulse .num .val.free {{ color: #27ae60; }}
        .market-pulse .num .lbl {{
            font-size: 0.75em;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        /* Player cards */
        .player-card {{
            background: white;
            border-radius: 8px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
            border-left: 4px solid #ddd;
            position: relative;
        }}
        .player-card.hot {{ border-left-color: #c0392b; }}
        .player-card.warm {{ border-left-color: #f39c12; }}

        .player-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 12px;
        }}
        .player-name {{
            font-family: -apple-system, sans-serif;
            font-size: 1.2em;
            font-weight: 700;
            color: #1a1a2e;
        }}
        .player-meta {{
            font-size: 0.85em;
            color: #666;
            margin-top: 2px;
        }}

        .score-badge {{
            font-family: -apple-system, sans-serif;
            font-weight: 700;
            font-size: 1.3em;
            padding: 6px 14px;
            border-radius: 6px;
            min-width: 50px;
            text-align: center;
        }}
        .score-badge.hot {{ background: #fdecea; color: #c0392b; }}
        .score-badge.warm {{ background: #fef5e7; color: #e67e22; }}
        .score-badge.cold {{ background: #eef2f7; color: #7f8c8d; }}

        .player-narrative {{
            color: #444;
            margin-bottom: 14px;
        }}

        .player-tags {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 14px;
        }}
        .tag {{
            font-family: -apple-system, sans-serif;
            font-size: 0.72em;
            padding: 3px 10px;
            border-radius: 3px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .tag.svincolato {{ background: #d5f5e3; color: #1e8449; }}
        .tag.rescissione {{ background: #fef9e7; color: #9a7d0a; }}
        .tag.prestito {{ background: #d6eaf8; color: #1a5276; }}
        .tag.mercato {{ background: #eaecee; color: #566573; }}
        .tag.scadenza {{ background: #fadbd8; color: #922b21; }}
        .tag.data-verified {{ background: #d5f5e3; color: #1e8449; }}
        .tag.data-partial {{ background: #fef9e7; color: #9a7d0a; }}
        .tag.data-minimal {{ background: #fadbd8; color: #922b21; }}

        /* Score breakdown */
        .score-detail {{
            background: #f9f9f9;
            border-radius: 6px;
            padding: 14px;
            margin-top: 10px;
        }}
        .score-detail-title {{
            font-family: -apple-system, sans-serif;
            font-size: 0.75em;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #888;
            margin-bottom: 8px;
        }}
        .factor-row {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }}
        .factor-label {{
            font-family: -apple-system, sans-serif;
            font-size: 0.75em;
            color: #666;
            min-width: 150px;
        }}
        .factor-bar-bg {{
            flex: 1;
            height: 6px;
            background: #e8e8e8;
            border-radius: 3px;
            overflow: hidden;
        }}
        .factor-bar {{
            height: 100%;
            border-radius: 3px;
            transition: width 0.3s;
        }}
        .factor-val {{
            font-family: -apple-system, sans-serif;
            font-size: 0.75em;
            font-weight: 600;
            color: #444;
            min-width: 25px;
            text-align: right;
        }}

        /* Reparto sections */
        .reparto {{
            background: white;
            border-radius: 8px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        }}
        .reparto h2 {{
            font-family: -apple-system, sans-serif;
            font-size: 1em;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #1a1a2e;
            margin-bottom: 15px;
            padding-bottom: 8px;
            border-bottom: 2px solid #eee;
        }}
        .reparto-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .reparto-table th {{
            font-family: -apple-system, sans-serif;
            font-size: 0.75em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #888;
            text-align: left;
            padding: 8px 6px;
            border-bottom: 1px solid #eee;
        }}
        .reparto-table td {{
            padding: 10px 6px;
            border-bottom: 1px solid #f5f5f5;
            font-size: 0.9em;
        }}
        .reparto-table tr:hover {{ background: #fafafa; }}

        .source-link {{
            color: #2980b9;
            text-decoration: none;
            font-size: 0.8em;
        }}
        .source-link:hover {{ text-decoration: underline; }}

        /* Footer */
        footer {{
            text-align: center;
            padding: 30px 20px;
            color: #aaa;
            font-size: 0.8em;
        }}
        footer a {{ color: #666; }}

        /* Print */
        @media print {{
            body {{ background: white; font-size: 12px; }}
            .container {{ max-width: 100%; padding: 0; }}
            .player-card, .reparto, .market-pulse {{ box-shadow: none; border: 1px solid #ddd; page-break-inside: avoid; }}
            header {{ background: #333 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
        }}

        @media (max-width: 600px) {{
            .player-header {{ flex-direction: column; gap: 8px; }}
            .market-pulse .numbers {{ gap: 15px; }}
            .factor-label {{ min-width: 100px; font-size: 0.65em; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>OB1 Scout</h1>
            <div class="date">Report Mercato — {date_str}</div>
            <div class="confidential">Serie C & D — Uso interno</div>
        </header>

        <div class="market-pulse">
            <h2>Polso del Mercato</h2>
            <p>{market_summary}. {total} profili monitorati dal radar OB1 nelle ultime 48 ore.</p>
            <div class="numbers">
                <div class="num">
                    <div class="val hot">{len(hot)}</div>
                    <div class="lbl">Priorità alta</div>
                </div>
                <div class="num">
                    <div class="val">{len(warm)}</div>
                    <div class="lbl">Da monitorare</div>
                </div>
                <div class="num">
                    <div class="val free">{len(svincolati)}</div>
                    <div class="lbl">A costo zero</div>
                </div>
                <div class="num">
                    <div class="val">{len(prestiti)}</div>
                    <div class="lbl">In prestito</div>
                </div>
            </div>
        </div>
'''

    # ── TOP PROFILES (FULL CARDS) ──
    html += '        <h2 style="font-family:-apple-system,sans-serif;font-size:0.85em;text-transform:uppercase;letter-spacing:1px;color:#888;margin:25px 0 15px 5px;">Segnalazioni principali</h2>\n'

    for opp in top_list:
        name = opp.get('player_name', 'N/D')
        score = opp.get('ob1_score', 0)
        classification = 'hot' if score >= 80 else 'warm' if score >= 60 else 'cold'
        role = get_role_label(opp)
        age = opp.get('age')
        opp_type = (opp.get('opportunity_type', '') or '').lower()
        club = opp.get('current_club', '')
        source_url = opp.get('source_url', '')

        narrative = build_narrative(opp)
        score_bars = build_score_breakdown_html(opp)
        confidence_text, confidence_class = data_confidence_label(opp)

        meta_parts = []
        if role:
            meta_parts.append(role)
        if age:
            meta_parts.append(f'{age} anni')
        if club:
            meta_parts.append(club)
        meta_line = ' · '.join(meta_parts)

        html += f'''
        <div class="player-card {classification}">
            <div class="player-header">
                <div>
                    <div class="player-name">{name}</div>
                    <div class="player-meta">{meta_line}</div>
                </div>
                <div class="score-badge {classification}">{score}</div>
            </div>

            <div class="player-tags">
                <span class="tag {opp_type}">{get_type_label(opp)}</span>
                <span class="tag data-{confidence_class}">{confidence_text}</span>
            </div>

            <div class="player-narrative">{narrative}</div>

            <div class="score-detail">
                <div class="score-detail-title">Perché questo score</div>
                {score_bars}
            </div>
'''
        if source_url:
            html += f'            <div style="margin-top:10px"><a class="source-link" href="{source_url}" target="_blank">↗ Fonte originale</a></div>\n'

        html += '        </div>\n'

    # ── PER REPARTO ──
    reparto_emoji = {'Difesa': '🛡', 'Centrocampo': '⚙', 'Attacco': '⚽'}

    for reparto, players in by_reparto.items():
        emoji = reparto_emoji.get(reparto, '')
        seen = set()
        deduped = []
        for p in players:
            pname = p.get('player_name', '').lower()
            if pname not in seen:
                seen.add(pname)
                deduped.append(p)
        top_5 = deduped[:8]

        html += f'''
        <div class="reparto">
            <h2>{emoji} {reparto} ({len(deduped)} profili)</h2>
            <table class="reparto-table">
                <thead>
                    <tr>
                        <th>Giocatore</th>
                        <th>Età</th>
                        <th>Ruolo</th>
                        <th>Status</th>
                        <th>Score</th>
                    </tr>
                </thead>
                <tbody>
'''
        for p in top_5:
            pname = p.get('player_name', 'N/D')
            page = p.get('age', '-') or '-'
            prole = get_role_label(p)
            ptype = get_type_label(p)
            pscore = p.get('ob1_score', 0)
            pclass = 'hot' if pscore >= 80 else 'warm' if pscore >= 60 else 'cold'
            pclub = p.get('current_club', '')

            html += f'''                    <tr>
                        <td><strong>{pname}</strong>{f'<br><small style="color:#999">{pclub}</small>' if pclub else ''}</td>
                        <td>{page}</td>
                        <td>{prole}</td>
                        <td><span class="tag {(p.get('opportunity_type','') or '').lower()}">{ptype}</span></td>
                        <td><span class="score-badge {pclass}" style="font-size:0.85em;padding:3px 8px">{pscore}</span></td>
                    </tr>
'''

        html += '''                </tbody>
            </table>
        </div>
'''

    # ── LEGENDA SCORE ──
    html += '''
        <div class="reparto" style="font-size:0.85em;">
            <h2>Come leggere lo Score OB1</h2>
            <p style="color:#666;margin-bottom:12px;">Lo Score OB1 (0-100) sintetizza 6 fattori ponderati per valutare l'opportunità di mercato, non il valore tecnico del giocatore.</p>
            <table class="reparto-table">
                <thead><tr><th>Fattore</th><th>Peso</th><th>Cosa misura</th></tr></thead>
                <tbody>
                    <tr><td>Attualità notizia</td><td>20%</td><td>Quanto è recente la segnalazione (oggi = 100, >2 settimane = 25)</td></tr>
                    <tr><td>Tipo opportunità</td><td>20%</td><td>Svincolato (100) > Rescissione (95) > Prestito (70) > Mercato (50)</td></tr>
                    <tr><td>Esperienza</td><td>20%</td><td>Presenze accumulate, club precedenti, categorie attraversate</td></tr>
                    <tr><td>Profilo anagrafico</td><td>20%</td><td>Fascia 22-28 = ideale. Under 22 = potenziale. Over 30 = penalizzato</td></tr>
                    <tr><td>Affidabilità fonte</td><td>10%</td><td>TuttoC/TuttoLegaPro (95) > TMW (80) > Fonti minori (50)</td></tr>
                    <tr><td>Completezza dati</td><td>10%</td><td>Quanti campi sono compilati (nome, età, ruolo, club, summary, URL)</td></tr>
                </tbody>
            </table>
            <p style="color:#999;margin-top:12px;font-size:0.9em;">⚠ Lo score indica la qualità dell'opportunità di mercato (disponibilità, timing, accessibilità), non il talento del giocatore. Un giocatore con score 70 può essere tecnicamente superiore a uno con score 90 se quest'ultimo è semplicemente più accessibile oggi.</p>
        </div>
'''

    # ── FOOTER ──
    html += f'''
        <footer>
            <p style="margin-bottom:5px;">Report generato da OB1 Scout — {date_str}</p>
            <p><a href="https://mtornani.github.io/ob1-serie-c/">Dashboard interattiva</a> · <a href="https://t.me/Ob1LegaPro_bot">Bot Telegram</a></p>
        </footer>
    </div>
</body>
</html>
'''

    return html


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("Generazione Report HTML (v2 narrativo)...")

    # Load from docs/data.json (has ob1_score already calculated)
    data_file = DOCS_DIR / 'data.json'
    if not data_file.exists():
        data_file = DATA_DIR / 'opportunities.json'

    if not data_file.exists():
        print("Nessun file dati trovato.")
        return

    try:
        data = json.loads(data_file.read_text(encoding='utf-8'))
        opportunities = data.get('opportunities', data) if isinstance(data, dict) else data
    except Exception as e:
        print(f"Errore caricamento: {e}")
        return

    print(f"Caricate {len(opportunities)} opportunita")

    # Load DNA Matches (optional)
    dna_file = DOCS_DIR / 'dna_matches.json'
    dna_matches = []
    if dna_file.exists():
        try:
            dna_data = json.loads(dna_file.read_text(encoding='utf-8'))
            dna_matches = dna_data.get('top_matches', [])
        except:
            pass

    # Generate HTML Report
    html_content = generate_html_report(opportunities, dna_matches)

    # Save report
    report_path = DOCS_DIR / 'report.html'
    report_path.write_text(html_content, encoding='utf-8')
    print(f"Report HTML salvato: {report_path}")

    # Output variable for GitHub Actions
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.getenv('GITHUB_OUTPUT'), 'a') as f:
            f.write(f'report_path={report_path}\n')

if __name__ == "__main__":
    main()
