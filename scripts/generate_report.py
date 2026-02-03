#!/usr/bin/env python3
"""
OB1 Scout - Generate HTML Report
Genera report settimanale in HTML (sostituisce il PDF problematico)
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent.parent / 'data'
DOCS_DIR = Path(__file__).parent.parent / 'docs'

def generate_html_report(opportunities: list, dna_matches: list = None) -> str:
    """Genera report HTML"""

    today = datetime.now()
    date_str = today.strftime("%d/%m/%Y")

    # Stats
    total = len(opportunities)
    hot = [o for o in opportunities if o.get('ob1_score', 0) >= 80]
    warm = [o for o in opportunities if 60 <= o.get('ob1_score', 0) < 80]
    svincolati = [o for o in opportunities if 'svincolato' in (o.get('opportunity_type', '') or '').lower()]

    # Top 15 by score
    top_list = sorted(opportunities, key=lambda x: x.get('ob1_score', 0), reverse=True)[:15]

    # Group by role
    by_role = {}
    for o in opportunities:
        role = o.get('role', 'Altro')
        if role not in by_role:
            by_role[role] = []
        by_role[role].append(o)

    html = f'''<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OB1 Scout Report - {date_str}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }}
        .container {{ max-width: 900px; margin: 0 auto; padding: 20px; }}

        header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            padding: 30px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
        }}
        header h1 {{ font-size: 2em; margin-bottom: 5px; }}
        header .subtitle {{ opacity: 0.8; font-size: 0.9em; }}
        header .date {{ margin-top: 10px; font-size: 1.1em; }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .stat-card .number {{ font-size: 2em; font-weight: bold; color: #1a1a2e; }}
        .stat-card .label {{ color: #666; font-size: 0.85em; }}
        .stat-card.hot .number {{ color: #e74c3c; }}
        .stat-card.warm .number {{ color: #f39c12; }}

        section {{
            background: white;
            padding: 25px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        section h2 {{
            color: #1a1a2e;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px 10px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
            color: #555;
        }}
        tr:hover {{ background: #f8f9fa; }}

        .score {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9em;
        }}
        .score.hot {{ background: #fdecea; color: #e74c3c; }}
        .score.warm {{ background: #fef5e7; color: #f39c12; }}
        .score.cold {{ background: #eef2f7; color: #7f8c8d; }}

        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.75em;
            font-weight: 500;
            text-transform: uppercase;
        }}
        .badge.svincolato {{ background: #d4edda; color: #155724; }}
        .badge.prestito {{ background: #cce5ff; color: #004085; }}
        .badge.rescissione {{ background: #fff3cd; color: #856404; }}
        .badge.mercato {{ background: #e2e3e5; color: #383d41; }}

        .role-section {{
            margin-bottom: 15px;
        }}
        .role-section h3 {{
            font-size: 1em;
            color: #666;
            margin-bottom: 8px;
        }}
        .role-players {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        .role-player {{
            background: #f8f9fa;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.85em;
        }}

        footer {{
            text-align: center;
            padding: 20px;
            color: #888;
            font-size: 0.85em;
        }}
        footer a {{ color: #1a1a2e; }}

        @media print {{
            body {{ background: white; }}
            .container {{ max-width: 100%; }}
            section {{ box-shadow: none; border: 1px solid #ddd; }}
        }}

        @media (max-width: 600px) {{
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            table {{ font-size: 0.85em; }}
            th, td {{ padding: 8px 5px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>OB1 SCOUT REPORT</h1>
            <div class="subtitle">Serie C & D Market Intelligence</div>
            <div class="date">{date_str}</div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="number">{total}</div>
                <div class="label">Totale Opportunita</div>
            </div>
            <div class="stat-card hot">
                <div class="number">{len(hot)}</div>
                <div class="label">HOT (80+)</div>
            </div>
            <div class="stat-card warm">
                <div class="number">{len(warm)}</div>
                <div class="label">WARM (60-79)</div>
            </div>
            <div class="stat-card">
                <div class="number">{len(svincolati)}</div>
                <div class="label">Svincolati</div>
            </div>
        </div>

        <section>
            <h2>TOP OPPORTUNITA</h2>
            <table>
                <thead>
                    <tr>
                        <th>Giocatore</th>
                        <th>Eta</th>
                        <th>Ruolo</th>
                        <th>Status</th>
                        <th>Score</th>
                    </tr>
                </thead>
                <tbody>
'''

    for opp in top_list:
        name = opp.get('player_name', 'N/D')
        age = opp.get('age', '-')
        role = opp.get('role_name') or opp.get('role', '-')
        opp_type = (opp.get('opportunity_type', 'mercato') or 'mercato').lower()
        score = opp.get('ob1_score', 0)
        classification = 'hot' if score >= 80 else 'warm' if score >= 60 else 'cold'
        club = opp.get('current_club', '')

        html += f'''                    <tr>
                        <td><strong>{name}</strong>{f'<br><small style="color:#888">{club}</small>' if club else ''}</td>
                        <td>{age}</td>
                        <td>{role}</td>
                        <td><span class="badge {opp_type}">{opp_type}</span></td>
                        <td><span class="score {classification}">{score}</span></td>
                    </tr>
'''

    html += '''                </tbody>
            </table>
        </section>

        <section>
            <h2>PER RUOLO</h2>
'''

    role_names = {
        'PO': 'Portieri', 'DC': 'Difensori Centrali', 'TD': 'Terzini Destri', 'TS': 'Terzini Sinistri',
        'CC': 'Centrocampisti', 'MED': 'Mediani', 'TRQ': 'Trequartisti',
        'AT': 'Attaccanti', 'ATT': 'Attaccanti', 'PC': 'Punte Centrali',
        'AD': 'Ali Destre', 'AS': 'Ali Sinistre', 'ED': 'Esterni Destri', 'ES': 'Esterni Sinistri'
    }

    for role, players in sorted(by_role.items(), key=lambda x: -len(x[1])):
        if len(players) > 0:
            role_display = role_names.get(role, role)
            top_players = sorted(players, key=lambda x: x.get('ob1_score', 0), reverse=True)[:5]

            html += f'''            <div class="role-section">
                <h3>{role_display} ({len(players)})</h3>
                <div class="role-players">
'''
            for p in top_players:
                score = p.get('ob1_score', 0)
                html += f'                    <span class="role-player">{p.get("player_name")} ({score})</span>\n'

            html += '''                </div>
            </div>
'''

    html += f'''        </section>

        <footer>
            <p>Generato automaticamente da OB1 Scout</p>
            <p><a href="https://mtornani.github.io/ob1-serie-c/">Dashboard</a> | <a href="https://t.me/Ob1LegaPro_bot">Telegram Bot</a></p>
        </footer>
    </div>
</body>
</html>
'''

    return html


def main():
    print("Generazione Report HTML...")

    # Load from docs/data.json (has ob1_score already calculated)
    data_file = DOCS_DIR / 'data.json'
    if not data_file.exists():
        # Fallback to opportunities.json
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
