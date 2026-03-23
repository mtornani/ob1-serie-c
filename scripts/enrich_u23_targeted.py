#!/usr/bin/env python3
"""
Targeted enrichment for U23 players only.
Uses Tavily search + Gemini 2.5 Flash with strict JSON mode.
Focuses on getting: age, nationality, club, position, market value, season stats.
"""

import os
import sys
import json
import time
import re
import requests
from pathlib import Path

DATA_FILE = Path("data/opportunities.json")
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

session = requests.Session()


def tavily_search(query, max_results=3):
    """Search via Tavily"""
    payload = {
        "api_key": TAVILY_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_raw_content": True,
    }
    try:
        r = session.post("https://api.tavily.com/search", json=payload, timeout=30)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"  [TAVILY] {e}")
        return []


def gemini_extract(content, player_name):
    """Use Gemini to extract structured data with strict JSON"""
    if len(content) > 20000:
        content = content[:20000]

    prompt = f"""Analizza questo testo e estrai i dati del calciatore "{player_name}".

RISPONDI SOLO con un JSON valido. Nessun commento, nessun markdown, solo il JSON.

Schema richiesto:
{{
  "full_name": "string",
  "birth_date": "YYYY-MM-DD o null",
  "age": "numero intero o null",
  "nationality": "string o null",
  "second_nationality": "string o null",
  "height_cm": "numero o null",
  "foot": "destro o sinistro o ambidestro o null",
  "current_club": "string",
  "role": "string - ruolo in italiano",
  "market_value_eur": "numero intero in euro o null",
  "market_value_text": "stringa formattata o null",
  "contract_expires": "YYYY-MM-DD o null",
  "agent": "string o null",
  "season_2425_appearances": "numero intero presenze 2024-25 o null",
  "season_2425_goals": "numero intero gol 2024-25 o null",
  "season_2425_assists": "numero intero assist 2024-25 o null",
  "season_2425_minutes": "numero intero minuti 2024-25 o null",
  "season_2526_appearances": "numero intero presenze 2025-26 o null",
  "season_2526_goals": "numero intero gol 2025-26 o null",
  "season_2526_assists": "numero intero assist 2025-26 o null",
  "season_2526_minutes": "numero intero minuti 2025-26 o null"
}}

REGOLE:
- Usa null per dati non trovati nel testo
- market_value_eur deve essere un numero intero (150000 non "150k")
- Per le statistiche, cerca tabelle con presenze/gol per stagione
- Se trovi solo una stagione, compila quella e metti null per l'altra

TESTO:
{content}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 1500,
            "responseMimeType": "application/json",
        },
    }

    try:
        r = session.post(url, json=payload, timeout=45)
        r.raise_for_status()
        data = r.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return {}
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        if not text:
            return {}
        # Clean any markdown wrapping
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  [JSON ERROR] {e}")
        return {}
    except Exception as e:
        print(f"  [GEMINI ERROR] {e}")
        return {}


def enrich_player(name, opp):
    """Full enrichment pipeline for a single player"""
    print(f"\n  Searching TM for: {name}")

    # Search 1: TM profile
    results = tavily_search(f"site:transfermarkt.it {name} profilo giocatore", max_results=1)

    tm_data = {}
    tm_url = ""

    if results:
        tm_url = results[0].get("url", "")
        raw = results[0].get("raw_content", "")
        if raw and len(raw) > 200:
            print(f"  TM: {tm_url}")
            tm_data = gemini_extract(raw, name)
            time.sleep(2)

    # Search 2: Stats from football sites
    if not tm_data.get("season_2526_appearances") and not tm_data.get("season_2425_appearances"):
        print(f"  Searching stats...")
        stats_results = tavily_search(f"{name} statistiche 2025 presenze gol Serie C", max_results=2)
        if stats_results:
            combined_text = "\n".join(r.get("raw_content", "")[:5000] for r in stats_results if r.get("raw_content"))
            if combined_text and len(combined_text) > 100:
                stats_data = gemini_extract(combined_text, name)
                # Merge stats into tm_data (don't overwrite existing good data)
                for k in ['season_2425_appearances', 'season_2425_goals', 'season_2425_assists',
                          'season_2526_appearances', 'season_2526_goals', 'season_2526_assists',
                          'season_2526_minutes', 'season_2425_minutes']:
                    if stats_data.get(k) and not tm_data.get(k):
                        tm_data[k] = stats_data[k]
                time.sleep(2)

    if not tm_data:
        print(f"  No data extracted")
        return False

    # Apply data to opportunity
    if tm_data.get('full_name'):
        # Verify it's the right player (name similarity check)
        extracted = tm_data['full_name'].lower()
        search = name.lower()
        if not any(part in extracted for part in search.split()):
            print(f"  WARNING: Name mismatch: searched '{name}', got '{tm_data['full_name']}'")

    # Age
    if tm_data.get('birth_date'):
        try:
            birth_year = int(str(tm_data['birth_date'])[:4])
            if 1990 <= birth_year <= 2010:
                opp['age'] = 2026 - birth_year
        except:
            pass
    elif tm_data.get('age'):
        try:
            age_val = int(tm_data['age'])
            if 14 <= age_val <= 45:
                opp['age'] = age_val
        except:
            pass

    # Basic fields
    for src, dst in [('nationality', 'nationality'), ('second_nationality', 'second_nationality'),
                     ('foot', 'foot'), ('height_cm', 'height_cm'), ('agent', 'agent'),
                     ('contract_expires', 'contract_expires')]:
        val = tm_data.get(src)
        if val and str(val).lower() not in ('null', 'none', ''):
            opp[dst] = val

    # Role
    if tm_data.get('role') and str(tm_data['role']).lower() not in ('null', 'none', ''):
        opp['role_name'] = tm_data['role']

    # Club
    if tm_data.get('current_club') and str(tm_data['current_club']).lower() not in ('null', 'none', ''):
        if not opp.get('current_club'):
            opp['current_club'] = tm_data['current_club']

    # Market value
    mv = tm_data.get('market_value_eur')
    if mv and isinstance(mv, (int, float)) and mv > 0:
        opp['market_value'] = int(mv)
    mvt = tm_data.get('market_value_text')
    if mvt and str(mvt).lower() not in ('null', 'none', ''):
        opp['market_value_formatted'] = mvt

    # Stats - prefer 2025/26, fallback to 2024/25
    for season_prefix in ['season_2526', 'season_2425']:
        app = tm_data.get(f'{season_prefix}_appearances')
        if app and isinstance(app, int) and app > 0:
            opp['appearances'] = app
            opp['goals'] = tm_data.get(f'{season_prefix}_goals') or 0
            opp['assists'] = tm_data.get(f'{season_prefix}_assists') or 0
            opp['minutes_played'] = tm_data.get(f'{season_prefix}_minutes') or 0
            break

    if tm_url:
        opp['tm_url'] = tm_url
    opp['tm_enriched'] = True

    return True


def main():
    if not TAVILY_KEY or not GEMINI_KEY:
        print("Missing API keys!")
        return

    opps = json.load(open(DATA_FILE, 'r', encoding='utf-8'))
    print(f"Total opportunities: {len(opps)}")

    # Find U23 players (or potential U23 with missing age)
    u23_candidates = []
    for i, opp in enumerate(opps):
        age = opp.get('age')
        if age and age <= 23:
            u23_candidates.append((i, opp))
        # Also include players without age that might be young (from summary text)
        elif not age:
            summary = (opp.get('summary', '') or '').lower()
            if any(k in summary for k in ['giovane', 'classe 200', 'under', 'giovanili', 'primavera', 'youth']):
                u23_candidates.append((i, opp))

    print(f"U23 candidates to enrich: {len(u23_candidates)}")

    updated = 0
    for idx, (i, opp) in enumerate(u23_candidates):
        name = opp.get('player_name', '')
        print(f"\n[{idx+1}/{len(u23_candidates)}] {name}")

        if enrich_player(name, opp):
            updated += 1
            age = opp.get('age', '?')
            app = opp.get('appearances', '?')
            gol = opp.get('goals', '?')
            mv = opp.get('market_value_formatted', '?')
            nat = opp.get('nationality', '?')
            print(f"  -> age={age} nat={nat} app={app} gol={gol} MV={mv}")

        # Save every 5
        if updated % 5 == 0 and updated > 0:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(opps, f, ensure_ascii=False, indent=2)
            print(f"  [SAVED]")

        time.sleep(1)

    # Final save
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(opps, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"TARGETED ENRICHMENT DONE: {updated} updated out of {len(u23_candidates)}")

    # Final U23 list
    u23_final = [o for o in opps if o.get('age') and o['age'] <= 23]
    print(f"Final U23 count: {len(u23_final)}")
    for p in sorted(u23_final, key=lambda x: x.get('age', 99)):
        name = p.get('player_name', '?')
        age = p.get('age', '?')
        nat = p.get('nationality', '?')
        club = p.get('current_club', '?')
        app = p.get('appearances', '-')
        gol = p.get('goals', '-')
        mv = p.get('market_value_formatted', '-')
        print(f"  {name:25s} age={age:>2} nat={nat:15s} club={club:20s} app={app:>3} gol={gol:>3} MV={mv}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
