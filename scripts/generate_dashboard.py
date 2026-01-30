#!/usr/bin/env python3
"""
OB1 Scout - Generate Dashboard HTML
"""

import json
from pathlib import Path
from datetime import datetime


def main():
    print("🌐 Generating dashboard...")

    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / 'data'
    docs_dir = base_dir / 'docs'
    docs_dir.mkdir(exist_ok=True)

    # Load data
    opps_file = data_dir / 'opportunities.json'
    stats_file = data_dir / 'stats.json'

    opportunities = []
    stats = {}

    if opps_file.exists():
        opportunities = json.loads(opps_file.read_text())
    if stats_file.exists():
        stats = json.loads(stats_file.read_text())

    # Generate opportunities HTML
    opps_html = ""
    for opp in opportunities[:10]:
        player = opp.get('player_name', 'N/D')
        club = opp.get('current_club', 'N/D')
        opp_type = opp.get('opportunity_type', 'mercato')
        summary = (opp.get('summary', '') or '')[:100]
        type_class = f'type-{opp_type.lower()}' if opp_type else ''

        opps_html += f'''
            <div class="opportunity">
                <h3>{player}</h3>
                <div class="meta">📍 {club}</div>
                <div class="meta">{summary}...</div>
                <span class="type-badge {type_class}">{opp_type}</span>
            </div>
'''

    # Generate HTML
    html = f'''<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OB1 Scout - Dashboard</title>
    <meta name="theme-color" content="#0f172a">
    <link rel="manifest" href="manifest.json">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #e2e8f0;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        header {{ text-align: center; padding: 30px 0; }}
        .logo {{ font-size: 3em; }}
        h1 {{ font-size: 1.8em; margin: 10px 0; }}
        .badge {{
            display: inline-block;
            background: #22c55e;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: rgba(30, 41, 59, 0.8);
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: #3b82f6; }}
        .stat-label {{ color: #94a3b8; font-size: 0.9em; margin-top: 5px; }}
        .card {{
            background: rgba(30, 41, 59, 0.8);
            border-radius: 12px;
            padding: 20px;
            margin: 15px 0;
        }}
        .card h2 {{ margin-bottom: 15px; font-size: 1.2em; }}
        .opportunity {{
            background: rgba(15, 23, 42, 0.6);
            padding: 15px;
            border-radius: 8px;
            margin: 10px 0;
            border-left: 4px solid #3b82f6;
        }}
        .opportunity h3 {{ color: #fff; font-size: 1.1em; }}
        .opportunity .meta {{ color: #94a3b8; font-size: 0.85em; margin-top: 5px; }}
        .type-badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.75em;
            margin-top: 8px;
        }}
        .type-svincolato {{ background: #22c55e; }}
        .type-prestito {{ background: #3b82f6; }}
        .type-rescissione {{ background: #f59e0b; }}
        .type-scadenza {{ background: #ef4444; }}
        footer {{
            text-align: center;
            padding: 30px 0;
            color: #64748b;
            font-size: 0.85em;
        }}
        @media (max-width: 500px) {{
            .stats-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">⚽</div>
            <h1>OB1 Scout Radar</h1>
            <span class="badge">Serie C & D</span>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{len(opportunities)}</div>
                <div class="stat-label">Opportunita Totali</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stats.get('new_opportunities', 0)}</div>
                <div class="stat-label">Ultime 6 Ore</div>
            </div>
        </div>

        <div class="card">
            <h2>🔥 Ultime Opportunita</h2>
            {opps_html if opps_html else '<p style="color: #64748b;">Nessuna opportunita trovata ancora. Il sistema si aggiorna ogni 6 ore.</p>'}
        </div>

        <footer>
            <p>Ultimo aggiornamento: {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
            <p>OB1 Scout Radar - Intelligence Before Headlines</p>
        </footer>
    </div>

    <script>
        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.register('sw.js');
        }}
    </script>
</body>
</html>'''

    (docs_dir / 'index.html').write_text(html)

    # Create manifest
    manifest = {
        'name': 'OB1 Scout Radar',
        'short_name': 'OB1 Scout',
        'start_url': '/',
        'display': 'standalone',
        'background_color': '#0f172a',
        'theme_color': '#0f172a',
        'icons': [
            {'src': 'icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
            {'src': 'icon-512.png', 'sizes': '512x512', 'type': 'image/png'}
        ]
    }
    (docs_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2))

    # Create service worker
    sw = '''const CACHE_NAME = 'ob1-scout-v1';
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('fetch', e => {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});'''
    (docs_dir / 'sw.js').write_text(sw)

    print("✅ Dashboard generated!")


if __name__ == "__main__":
    main()
