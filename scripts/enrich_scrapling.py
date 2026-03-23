#!/usr/bin/env python3
"""
OB1 Serie C - Enrichment via Scrapling + Gemini
Uses Scrapling (headless browser) to render TM pages with JS tables,
then Gemini to extract structured data including season stats.
"""

import os
import sys
import json
import time
import re
import requests
from pathlib import Path

# API keys - set before dotenv can override
_gemini_key = os.environ.get("GEMINI_API_KEY", "")
_tavily_key = os.environ.get("TAVILY_API_KEY", "")

sys.path.insert(0, str(Path(__file__).parent.parent))

# Re-set after potential dotenv override
if _gemini_key:
    os.environ["GEMINI_API_KEY"] = _gemini_key
if _tavily_key:
    os.environ["TAVILY_API_KEY"] = _tavily_key

from scrapling import StealthyFetcher

DATA_FILE = Path("data/opportunities.json")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")
RATE_LIMIT = 3  # seconds between Gemini calls

session = requests.Session()
fetcher = None  # Lazy init


def get_fetcher():
    global fetcher
    if fetcher is None:
        fetcher = StealthyFetcher(headless=True)
    return fetcher


def find_tm_url(player_name: str) -> str:
    """Use Tavily to find the TM profile URL (fast, no rendering needed)"""
    if not TAVILY_KEY:
        return ""
    payload = {
        "api_key": TAVILY_KEY,
        "query": f"site:transfermarkt.it {player_name} profilo giocatore",
        "search_depth": "basic",
        "max_results": 1,
        "include_domains": ["transfermarkt.it"],
        "include_raw_content": False,
    }
    try:
        r = session.post("https://api.tavily.com/search", json=payload, timeout=15)
        r.raise_for_status()
        results = r.json().get("results", [])
        if results:
            url = results[0].get("url", "")
            # Must be a player profile, not a club/league page
            if "/profil/spieler/" in url or "/leistungsdaten/spieler/" in url:
                return url
            # Try to extract player profile URL from the result
            if "/spieler/" in url:
                return url
    except Exception as e:
        print(f"  [TAVILY] {e}")
    return ""


def scrape_tm_page(url: str) -> str:
    """Use Scrapling to render TM page with JS (gets stats tables)"""
    try:
        f = get_fetcher()
        # Fetch with network_idle to wait for JS tables to load
        page = f.fetch(url, network_idle=True)
        return page.get_all_text() or ""
    except Exception as e:
        print(f"  [SCRAPLING] {e}")
        return ""


def scrape_tm_stats_page(profile_url: str) -> str:
    """Convert profile URL to stats page URL and scrape it"""
    # TM profile: /spieler/12345 -> stats: /leistungsdaten/spieler/12345
    stats_url = profile_url.replace("/profil/spieler/", "/leistungsdaten/spieler/")
    if stats_url == profile_url:
        # Fallback: append leistungsdaten
        stats_url = profile_url.replace("/spieler/", "/leistungsdaten/spieler/")
    try:
        f = get_fetcher()
        page = f.fetch(stats_url, network_idle=True)
        return page.get_all_text() or ""
    except Exception as e:
        print(f"  [SCRAPLING STATS] {e}")
        return ""


def gemini_extract(content: str, player_name: str, page_type: str = "profile") -> dict:
    """Use Gemini to extract structured data from rendered TM content"""
    if not GEMINI_KEY:
        return {}

    # Truncate but keep more for stats tables
    max_chars = 25000 if page_type == "stats" else 20000
    if len(content) > max_chars:
        content = content[:max_chars]

    if page_type == "stats":
        prompt = f"""Analizza questa pagina di statistiche Transfermarkt per "{player_name}".
Estrai SOLO le statistiche stagionali. Rispondi con un JSON valido, nessun altro testo.

{{
  "seasons": [
    {{
      "season": "24/25 o 25/26",
      "competition": "nome competizione",
      "appearances": numero intero,
      "goals": numero intero,
      "assists": numero intero,
      "minutes": numero intero o null,
      "yellow_cards": numero intero o null,
      "red_cards": numero intero o null
    }}
  ],
  "total_appearances_current": "presenze totali stagione corrente (tutte competizioni)",
  "total_goals_current": "gol totali stagione corrente",
  "total_assists_current": "assist totali stagione corrente",
  "total_minutes_current": "minuti totali stagione corrente"
}}

REGOLE:
- Stagione corrente = 2025/26 se disponibile, altrimenti 2024/25
- Somma le presenze di TUTTE le competizioni per i totali
- Se non trovi dati, usa null
- I totali devono essere numeri interi, non stringhe

CONTENUTO:
{content}"""
    else:
        prompt = f"""Analizza questa pagina profilo Transfermarkt per "{player_name}".
Rispondi SOLO con un JSON valido, nessun altro testo.

{{
  "full_name": "Nome e Cognome completo",
  "birth_date": "YYYY-MM-DD o null",
  "nationality": "Nazionalità principale in italiano",
  "second_nationality": "Seconda nazionalità o null",
  "height_cm": numero intero o null,
  "foot": "destro | sinistro | ambidestro | null",
  "current_club": "Nome Club attuale",
  "contract_expires": "YYYY-MM-DD o null",
  "market_value_eur": numero intero in euro (es. 150000 per €150k) o null,
  "market_value_text": "stringa formattata (es. 150 mila €)" o null,
  "main_position": "Ruolo principale in italiano (es. Punta centrale, Terzino destro)",
  "agent": "Nome agente/agenzia o null",
  "appearances_current_season": numero intero presenze stagione corrente o null,
  "goals_current_season": numero intero gol stagione corrente o null,
  "assists_current_season": numero intero assist stagione corrente o null,
  "minutes_current_season": numero intero minuti stagione corrente o null
}}

REGOLE:
- Usa null per dati non trovati
- market_value_eur deve essere un numero intero
- Cerca "Valore di mercato attuale" o "Marktwert"
- Per statistiche cerca tabelle presenze/gol nella pagina
- Nazionalità in italiano (Italia, Albania, Croazia, ecc.)

CONTENUTO:
{content}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 2000,
            "responseMimeType": "application/json",
        },
    }

    try:
        r = session.post(url, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return {}
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if not text:
            return {}
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  [JSON] {e}")
        return {}
    except Exception as e:
        print(f"  [GEMINI] {e}")
        return {}


def enrich_player(name: str, opp: dict) -> bool:
    """Full enrichment: find URL -> scrape profile -> scrape stats -> extract"""

    # Step 1: Find TM URL
    tm_url = opp.get('tm_url', '')
    if not tm_url or '/profil/spieler/' not in tm_url:
        print(f"  Finding TM URL...")
        tm_url = find_tm_url(name)
        if not tm_url:
            print(f"  No TM profile found")
            return False
        time.sleep(1)

    print(f"  TM: {tm_url}")

    # Step 2: Scrape profile page with Scrapling (renders JS)
    print(f"  Scraping profile...")
    profile_html = scrape_tm_page(tm_url)
    if not profile_html or len(profile_html) < 500:
        print(f"  Empty/short profile page")
        return False

    print(f"  Got {len(profile_html)} chars, extracting with Gemini...")
    profile_data = gemini_extract(profile_html, name, "profile")
    time.sleep(RATE_LIMIT)

    if not profile_data:
        print(f"  Failed to extract profile data")
        return False

    # Step 3: Scrape stats page if profile didn't have stats
    has_stats = profile_data.get('appearances_current_season')
    if not has_stats:
        print(f"  Scraping stats page...")
        stats_html = scrape_tm_stats_page(tm_url)
        if stats_html and len(stats_html) > 500:
            print(f"  Got {len(stats_html)} chars stats, extracting...")
            stats_data = gemini_extract(stats_html, name, "stats")
            time.sleep(RATE_LIMIT)

            # Merge stats
            if stats_data:
                total_app = stats_data.get('total_appearances_current')
                total_gol = stats_data.get('total_goals_current')
                total_ast = stats_data.get('total_assists_current')
                total_min = stats_data.get('total_minutes_current')

                if total_app and isinstance(total_app, int):
                    profile_data['appearances_current_season'] = total_app
                if total_gol and isinstance(total_gol, int):
                    profile_data['goals_current_season'] = total_gol
                if total_ast and isinstance(total_ast, int):
                    profile_data['assists_current_season'] = total_ast
                if total_min and isinstance(total_min, int):
                    profile_data['minutes_current_season'] = total_min

    # Step 4: Apply data to opportunity
    # Full name
    if profile_data.get('full_name') and len(profile_data['full_name']) > len(name):
        opp['player_name'] = profile_data['full_name']

    # Age from birth_date
    if profile_data.get('birth_date'):
        try:
            birth_year = int(str(profile_data['birth_date'])[:4])
            if 1990 <= birth_year <= 2012:
                opp['age'] = 2026 - birth_year
        except (ValueError, TypeError):
            pass

    # Basic fields
    field_map = {
        'nationality': 'nationality',
        'second_nationality': 'second_nationality',
        'foot': 'foot',
        'height_cm': 'height_cm',
        'agent': 'agent',
        'contract_expires': 'contract_expires',
    }
    for src, dst in field_map.items():
        val = profile_data.get(src)
        if val and str(val).lower() not in ('null', 'none', '', 'n/a'):
            opp[dst] = val

    # Role
    if profile_data.get('main_position'):
        pos = profile_data['main_position']
        if pos.lower() not in ('null', 'none', ''):
            opp['role_name'] = pos
            # Update role code
            role_map = {
                'punta centrale': 'PC', 'centravanti': 'AT', 'attaccante': 'AT',
                'seconda punta': 'AT', 'ala destra': 'AD', 'ala sinistra': 'AS',
                'centrocampista': 'CC', 'centrocampista centrale': 'CC',
                'centrocampista offensivo': 'TRQ', 'trequartista': 'TRQ',
                'mediano': 'MED', 'regista': 'CC', 'mezzala': 'CC',
                'centrocampista difensivo': 'MED',
                'difensore centrale': 'DC', 'terzino destro': 'TD',
                'terzino sinistro': 'TS', 'esterno destro': 'ED',
                'esterno sinistro': 'ES', 'portiere': 'PO',
            }
            for role_name, code in role_map.items():
                if role_name in pos.lower():
                    opp['role'] = code
                    break

    # Club
    if profile_data.get('current_club'):
        club = profile_data['current_club']
        if club.lower() not in ('null', 'none', '', 'svincolato'):
            opp['current_club'] = club
        elif club.lower() == 'svincolato':
            opp['current_club'] = 'Svincolato'
            if opp.get('opportunity_type', '') == 'mercato':
                opp['opportunity_type'] = 'svincolato'

    # Market value
    mv = profile_data.get('market_value_eur')
    if mv and isinstance(mv, (int, float)) and mv > 0:
        opp['market_value'] = int(mv)
    mvt = profile_data.get('market_value_text')
    if mvt and str(mvt).lower() not in ('null', 'none', ''):
        opp['market_value_formatted'] = mvt

    # Season stats
    app = profile_data.get('appearances_current_season')
    if app and isinstance(app, int) and app > 0:
        opp['appearances'] = app
        opp['goals'] = profile_data.get('goals_current_season') or 0
        opp['assists'] = profile_data.get('assists_current_season') or 0
        opp['minutes_played'] = profile_data.get('minutes_current_season') or 0
        if isinstance(opp['goals'], str):
            try: opp['goals'] = int(opp['goals'])
            except: opp['goals'] = 0
        if isinstance(opp['assists'], str):
            try: opp['assists'] = int(opp['assists'])
            except: opp['assists'] = 0

    # TM URL
    opp['tm_url'] = tm_url
    opp['tm_enriched'] = True

    return True


def main():
    print("=" * 60)
    print("OB1 ENRICHMENT - Scrapling + Gemini")
    print("=" * 60)

    if not GEMINI_KEY or GEMINI_KEY.startswith('your_'):
        print("ERROR: GEMINI_API_KEY not set!")
        return

    opps = json.load(open(DATA_FILE, 'r', encoding='utf-8'))
    print(f"Total: {len(opps)}")

    # Process U23 first, then all players without stats
    u23 = [(i, o) for i, o in enumerate(opps) if o.get('age') and o['age'] <= 23]
    no_stats = [(i, o) for i, o in enumerate(opps)
                if not (o.get('appearances') and o['appearances'] > 0)
                and (i, o) not in u23]

    # Prioritize U23
    to_process = u23 + no_stats
    print(f"U23 to enrich: {len(u23)}")
    print(f"Others without stats: {len(no_stats)}")
    print(f"Total to process: {len(to_process)}")

    # Only do U23 for now (the demo focus)
    targets = u23
    print(f"\nProcessing {len(targets)} U23 players...")

    updated = 0
    errors = 0

    for idx, (i, opp) in enumerate(targets):
        name = opp.get('player_name', '')
        print(f"\n[{idx+1}/{len(targets)}] {name}")

        try:
            if enrich_player(name, opp):
                updated += 1
                age = opp.get('age', '?')
                app = opp.get('appearances', '-')
                gol = opp.get('goals', '-')
                ast = opp.get('assists', '-')
                mins = opp.get('minutes_played', '-')
                mv = opp.get('market_value_formatted', '-')
                nat = opp.get('nationality', '?')
                club = opp.get('current_club', '?')
                full_name = opp.get('player_name', name)
                print(f"  OK: {full_name} | age={age} nat={nat} club={club}")
                print(f"      app={app} gol={gol} ast={ast} min={mins} MV={mv}")
            else:
                errors += 1
        except Exception as e:
            print(f"  FATAL ERROR: {e}")
            errors += 1

        # Save every 3 players
        if (updated + errors) % 3 == 0:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(opps, f, ensure_ascii=False, indent=2)
            print(f"  [SAVED]")

        time.sleep(1)

    # Final save
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(opps, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"ENRICHMENT DONE: {updated} updated, {errors} errors")

    # Final U23 list
    u23_final = [o for o in opps if o.get('age') and o['age'] <= 23]
    print(f"\nU23 players ({len(u23_final)}):")
    for p in sorted(u23_final, key=lambda x: -(x.get('appearances') or 0)):
        name = p.get('player_name', '?')
        age = p.get('age', '?')
        nat = p.get('nationality', '?')
        club = p.get('current_club', '?')
        app = p.get('appearances', '-')
        gol = p.get('goals', '-')
        ast = p.get('assists', '-')
        mv = p.get('market_value_formatted', '-')
        print(f"  {str(name):25s} {str(age):>3s} {str(nat):15s} {str(club):20s} app={str(app):>3s} gol={str(gol):>3s} ast={str(ast):>3s} MV={mv}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
