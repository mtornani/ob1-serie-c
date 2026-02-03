#!/usr/bin/env python3
"""
Scrape REAL data from Transfermarkt for Serie C B-teams:
- Juventus Next Gen
- Milan Futuro
- Atalanta U23

Uses Tavily for search + Gemini for structured extraction.
"""

import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

TAVILY_API_KEY = os.getenv('TAVILY_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Squadre B in Serie C NOW (2025-26)
SQUADRE_B = {
    'juventus_next_gen': {
        'name': 'Juventus Next Gen',
        'parent_club': 'Juventus',
        'transfermarkt_id': '75949',
        'transfermarkt_url': 'https://www.transfermarkt.it/juventus-next-gen/startseite/verein/75949',
    },
    'milan_futuro': {
        'name': 'Milan Futuro',
        'parent_club': 'Milan',
        'transfermarkt_id': '109949',
        'transfermarkt_url': 'https://www.transfermarkt.it/milan-futuro/startseite/verein/109949',
    },
    'atalanta_u23': {
        'name': 'Atalanta U23',
        'parent_club': 'Atalanta',
        'transfermarkt_id': '107873',
        'transfermarkt_url': 'https://www.transfermarkt.it/atalanta-u-23/startseite/verein/107873',
    },
}

POSITION_MAP = {
    'portiere': 'PO',
    'difensore centrale': 'DC',
    'terzino destro': 'TD',
    'terzino sinistro': 'TS',
    'centrocampista centrale': 'CC',
    'centrocampista difensivo': 'MED',
    'centrocampista offensivo': 'TRQ',
    'ala destra': 'AD',
    'ala sinistra': 'AS',
    'esterno destro': 'ED',
    'esterno sinistro': 'ES',
    'attaccante': 'ATT',
    'punta': 'PC',
    'seconda punta': 'ATT',
}


def search_tavily(query: str, include_domains: List[str] = None) -> List[Dict]:
    """Search using Tavily API"""
    url = "https://api.tavily.com/search"

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": 5,
        "include_raw_content": True,
    }

    if include_domains:
        payload["include_domains"] = include_domains

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json().get('results', [])
    except Exception as e:
        print(f"  [!] Tavily error: {e}")
        return []


def extract_with_gemini(content: str, team_name: str) -> List[Dict]:
    """Use Gemini to extract player data from content"""

    prompt = f'''Analizza questo contenuto su {team_name} ed estrai i dati dei giocatori della rosa.

Per ogni giocatore estrai:
{{
  "name": "Nome Cognome",
  "birth_year": anno di nascita (numero),
  "age": eta attuale (numero),
  "nationality": "nazionalita",
  "position": "ruolo in italiano (es: difensore centrale, terzino destro, centrocampista, ala, attaccante)",
  "secondary_positions": ["altri ruoli"],
  "preferred_foot": "destro" o "sinistro",
  "contract_until": "YYYY-MM-DD" o null,
  "appearances_this_season": numero presenze stagione attuale,
  "minutes_played": minuti giocati,
  "goals": gol segnati,
  "assists": assist,
  "market_value_eur": valore di mercato in migliaia di euro (es: 500 = 500k),
  "transfer_status": "disponibile_prestito" | "in_uscita" | "incedibile" | "sconosciuto"
}}

IMPORTANTE:
- Estrai SOLO giocatori reali con dati verificabili
- Se un dato non e disponibile, usa null
- Restituisci un JSON array valido

CONTENUTO:
{content[:6000]}

JSON:'''

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4000,
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()

        text = data['candidates'][0]['content']['parts'][0]['text']

        # Clean JSON
        text = text.strip()
        if text.startswith('```json'):
            text = text[7:]
        if text.startswith('```'):
            text = text[3:]
        if text.endswith('```'):
            text = text[:-3]

        players = json.loads(text.strip())
        return players if isinstance(players, list) else []

    except json.JSONDecodeError as e:
        print(f"  [!] JSON parse error: {e}")
        return []
    except Exception as e:
        print(f"  [!] Gemini error: {e}")
        return []


def scrape_team(team_id: str, team_info: Dict) -> List[Dict]:
    """Scrape player data for a team"""

    team_name = team_info['name']
    print(f"\n{'='*60}")
    print(f"Scraping: {team_name}")
    print(f"{'='*60}")

    all_players = []
    seen_names = set()

    # Search queries
    queries = [
        f"{team_name} rosa giocatori 2025-26 transfermarkt",
        f"{team_name} formazione Serie C NOW giocatori",
        f"calciatori {team_name} statistiche stagione attuale",
    ]

    for query in queries:
        print(f"\n  Searching: {query[:50]}...")

        results = search_tavily(query, include_domains=['transfermarkt.it', 'transfermarkt.com'])

        for result in results:
            content = result.get('raw_content') or result.get('content', '')
            if not content or len(content) < 200:
                continue

            print(f"  Extracting from: {result.get('title', '')[:50]}...")

            players = extract_with_gemini(content, team_name)

            for player in players:
                name = player.get('name', '')
                if not name or name.lower() in seen_names:
                    continue
                seen_names.add(name.lower())

                # Map position
                pos_raw = (player.get('position') or '').lower()
                pos_code = POSITION_MAP.get(pos_raw, 'CC')

                # Build player object
                player_obj = {
                    'id': f"{team_id}_{len(all_players)+1:03d}",
                    'name': name,
                    'birth_year': player.get('birth_year'),
                    'age': player.get('age'),
                    'nationality': player.get('nationality', 'Sconosciuta'),
                    'primary_position': pos_code,
                    'secondary_positions': player.get('secondary_positions', []),
                    'preferred_foot': player.get('preferred_foot', 'destro'),
                    'parent_club': team_info['parent_club'],
                    'current_team': team_name,
                    'contract_until': player.get('contract_until'),
                    'appearances': player.get('appearances_this_season', 0),
                    'minutes_played': player.get('minutes_played', 0),
                    'goals': player.get('goals', 0),
                    'assists': player.get('assists', 0),
                    'market_value': player.get('market_value_eur', 0),
                    'transfer_status': player.get('transfer_status', 'sconosciuto'),
                    'transfermarkt_url': '',
                    'last_updated': datetime.now().strftime('%Y-%m-%d'),
                }

                all_players.append(player_obj)
                print(f"    + {name} ({pos_code})")

        time.sleep(1)  # Rate limiting

    print(f"\n  Total players found: {len(all_players)}")
    return all_players


def estimate_skills(player: Dict) -> Dict:
    """Estimate skills based on position, age, and stats"""

    pos = player.get('primary_position', 'CC')
    age = player.get('age', 22)
    appearances = player.get('appearances', 0)
    goals = player.get('goals', 0)
    assists = player.get('assists', 0)
    market_value = player.get('market_value', 500)

    # Base skills by position
    base_skills = {
        'PO': {'tecnica': 60, 'velocita': 55, 'fisico': 75, 'visione': 65, 'difesa': 78, 'pressing': 40, 'dribbling': 35, 'tiro': 30},
        'DC': {'tecnica': 62, 'velocita': 62, 'fisico': 78, 'visione': 60, 'difesa': 78, 'pressing': 70, 'dribbling': 50, 'tiro': 45},
        'TD': {'tecnica': 65, 'velocita': 75, 'fisico': 72, 'visione': 62, 'difesa': 72, 'pressing': 75, 'dribbling': 62, 'tiro': 52},
        'TS': {'tecnica': 65, 'velocita': 75, 'fisico': 72, 'visione': 62, 'difesa': 72, 'pressing': 75, 'dribbling': 62, 'tiro': 52},
        'MED': {'tecnica': 68, 'velocita': 68, 'fisico': 75, 'visione': 70, 'difesa': 72, 'pressing': 78, 'dribbling': 60, 'tiro': 58},
        'CC': {'tecnica': 72, 'velocita': 68, 'fisico': 68, 'visione': 72, 'difesa': 60, 'pressing': 72, 'dribbling': 68, 'tiro': 65},
        'TRQ': {'tecnica': 78, 'velocita': 70, 'fisico': 62, 'visione': 78, 'difesa': 45, 'pressing': 62, 'dribbling': 75, 'tiro': 72},
        'ED': {'tecnica': 72, 'velocita': 78, 'fisico': 68, 'visione': 68, 'difesa': 55, 'pressing': 70, 'dribbling': 75, 'tiro': 68},
        'ES': {'tecnica': 72, 'velocita': 78, 'fisico': 68, 'visione': 68, 'difesa': 55, 'pressing': 70, 'dribbling': 75, 'tiro': 68},
        'AD': {'tecnica': 75, 'velocita': 80, 'fisico': 65, 'visione': 70, 'difesa': 40, 'pressing': 65, 'dribbling': 78, 'tiro': 72},
        'AS': {'tecnica': 75, 'velocita': 80, 'fisico': 65, 'visione': 70, 'difesa': 40, 'pressing': 65, 'dribbling': 78, 'tiro': 72},
        'ATT': {'tecnica': 72, 'velocita': 75, 'fisico': 72, 'visione': 68, 'difesa': 35, 'pressing': 68, 'dribbling': 72, 'tiro': 78},
        'PC': {'tecnica': 70, 'velocita': 72, 'fisico': 75, 'visione': 65, 'difesa': 30, 'pressing': 70, 'dribbling': 68, 'tiro': 80},
    }

    skills = base_skills.get(pos, base_skills['CC']).copy()

    # Adjust for market value (higher value = better player)
    value_bonus = min(10, market_value // 500)
    for skill in skills:
        skills[skill] = min(95, skills[skill] + value_bonus)

    # Adjust for productivity
    if goals > 3:
        skills['tiro'] = min(95, skills['tiro'] + 5)
    if assists > 3:
        skills['visione'] = min(95, skills['visione'] + 5)

    # Younger players have more potential
    if age <= 20:
        for skill in skills:
            skills[skill] = max(55, skills[skill] - 5)  # Slightly lower but high potential

    return skills


def main():
    if not TAVILY_API_KEY or not GEMINI_API_KEY:
        print("ERROR: Set TAVILY_API_KEY and GEMINI_API_KEY in .env")
        return

    print("="*60)
    print("OB1 SERIE C - SQUADRE B SCRAPER")
    print("="*60)

    all_players = []

    for team_id, team_info in SQUADRE_B.items():
        players = scrape_team(team_id, team_info)

        # Add estimated skills
        for player in players:
            player['skills'] = estimate_skills(player)

            # Calculate minutes percentage (assuming 34 matches * 90 min)
            total_possible = 34 * 90
            player['minutes_percentage'] = round((player.get('minutes_played', 0) / total_possible) * 100, 1)
            player['is_underused'] = player['minutes_percentage'] < 50

        all_players.extend(players)
        time.sleep(2)  # Between teams

    # Save results
    output_dir = Path(__file__).parent.parent / 'data' / 'players'
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / 'squadre_b.json'

    # Backup old file
    if output_file.exists():
        backup_file = output_dir / f'squadre_b_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        output_file.rename(backup_file)
        print(f"\nBackup saved to: {backup_file}")

    output_file.write_text(json.dumps(all_players, indent=2, ensure_ascii=False))

    print(f"\n{'='*60}")
    print(f"DONE! Saved {len(all_players)} players to {output_file}")
    print(f"{'='*60}")

    # Summary
    print("\nSUMMARY:")
    for team_id, team_info in SQUADRE_B.items():
        count = len([p for p in all_players if p.get('parent_club') == team_info['parent_club']])
        print(f"  {team_info['name']}: {count} players")


if __name__ == "__main__":
    main()
