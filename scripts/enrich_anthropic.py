#!/usr/bin/env python3
"""
OB1 Serie C - Enrichment via Tavily + Anthropic Claude
Replaces Gemini-based enricher when GEMINI_API_KEY is unavailable.
"""

import os
import sys
import json
import time
import requests
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import anthropic

DATA_FILE = Path("data/opportunities.json")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
RATE_LIMIT_DELAY = 2

# Load from .env if not in environment
if not TAVILY_API_KEY:
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith('TAVILY_API_KEY='):
                TAVILY_API_KEY = line.split('=', 1)[1].strip()


def search_transfermarkt(player_name: str, session: requests.Session) -> dict | None:
    """Search Transfermarkt via Tavily API"""
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": f"site:transfermarkt.it {player_name} profilo giocatore",
        "search_depth": "basic",
        "max_results": 1,
        "include_domains": ["transfermarkt.it"],
        "include_raw_content": True,
    }
    try:
        resp = session.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0]
    except Exception as e:
        print(f"  [TAVILY ERROR] {e}")
    return None


def extract_with_claude(client: anthropic.Anthropic, content: str, url: str, player_name: str) -> dict:
    """Use Claude to extract structured data from TM page content"""
    # Truncate long content
    if len(content) > 15000:
        content = content[:15000] + "..."

    prompt = f"""Sei un data analyst sportivo. Estrai i dati esatti da questo contenuto di pagina Transfermarkt per il giocatore "{player_name}".
URL: {url}

Rispondi SOLO con un oggetto JSON valido, nessun altro testo:
{{
  "full_name": "Nome completo del giocatore",
  "birth_date": "YYYY-MM-DD" o null,
  "nationality": "Nazionalità principale",
  "second_nationality": "Seconda nazionalità o null",
  "height_cm": numero intero o null,
  "foot": "destro" | "sinistro" | "ambidestro" | null,
  "current_club": "Nome Club" o "Svincolato",
  "contract_expires": "YYYY-MM-DD" o null,
  "market_value": numero intero in euro (es. 150000 per €150k, 1500000 per €1.5M) o null,
  "market_value_formatted": "stringa formattata (es. €150k, €1.5M)" o null,
  "main_position": "Ruolo principale in italiano",
  "agent": "Nome Agenzia" o null,
  "player_image_url": "URL immagine profilo" o null,
  "appearances": numero intero presenze stagione 2024/25 o 2025/26 (la più recente disponibile, tutte le competizioni) o null,
  "goals": numero intero gol stagione corrente o null,
  "assists": numero intero assist stagione corrente o null,
  "minutes_played": numero intero minuti giocati stagione corrente o null
}}

REGOLE:
- Usa null se un dato non è presente nel testo
- Per market_value usa il numero intero in euro (150000, non "€150k")
- Per le statistiche cerca tabelle con presenze/gol/assist della stagione più recente
- Se trovi statistiche per più stagioni, usa la stagione 2024/25 o 2025/26 (la più recente)
- Somma le presenze di tutte le competizioni (Serie C + Coppa Italia + altro)

CONTENUTO PAGINA:
{content}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        # Clean up potential markdown wrapping
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  [PARSE ERROR] {e}")
        return {}
    except Exception as e:
        print(f"  [CLAUDE ERROR] {e}")
        return {}


def main():
    if not DATA_FILE.exists():
        print("No data file found!")
        return

    if not TAVILY_API_KEY:
        print("TAVILY_API_KEY not found!")
        return

    print("Loading opportunities...")
    opps = json.load(open(DATA_FILE, 'r', encoding='utf-8'))
    print(f"Total: {len(opps)}")

    client = anthropic.Anthropic()
    session = requests.Session()

    # Find entries needing enrichment (no stats)
    to_enrich = []
    for i, opp in enumerate(opps):
        has_stats = (opp.get('appearances') or opp.get('goals') or opp.get('minutes_played') or
                     (opp.get('player_profile', {}) or {}).get('appearances'))
        if not has_stats and not opp.get('_enrichment_failed'):
            to_enrich.append((i, opp))

    print(f"Need enrichment: {len(to_enrich)}")

    updated = 0
    errors = 0

    for idx, (i, opp) in enumerate(to_enrich):
        name = opp.get('player_name', 'N/D')
        print(f"\n[{idx+1}/{len(to_enrich)}] {name}")

        # Search on Transfermarkt
        result = search_transfermarkt(name, session)
        if not result:
            print(f"  No TM profile found")
            opp['_enrichment_failed'] = True
            errors += 1
            time.sleep(1)
            continue

        raw_content = result.get("raw_content", "")
        tm_url = result.get("url", "")

        if not raw_content or len(raw_content) < 100:
            print(f"  Empty content from TM page")
            opp['_enrichment_failed'] = True
            errors += 1
            time.sleep(1)
            continue

        print(f"  TM URL: {tm_url}")

        # Extract with Claude
        tm_data = extract_with_claude(client, raw_content, tm_url, name)
        if not tm_data:
            opp['_enrichment_failed'] = True
            errors += 1
            time.sleep(RATE_LIMIT_DELAY)
            continue

        # Apply enrichment data
        enrichment_fields = [
            'nationality', 'second_nationality', 'foot', 'market_value',
            'market_value_formatted', 'height_cm', 'contract_expires',
            'agent', 'appearances', 'goals', 'assists', 'minutes_played',
            'player_image_url'
        ]

        for key in enrichment_fields:
            val = tm_data.get(key)
            if val is not None:
                opp[key] = val

        # Set TM URL
        if tm_url:
            opp['tm_url'] = tm_url

        # Calculate age from birth_date if missing
        if not opp.get('age') and tm_data.get('birth_date'):
            try:
                birth_year = int(tm_data['birth_date'][:4])
                opp['age'] = 2026 - birth_year
            except (ValueError, TypeError):
                pass

        # Update role from TM if we have it
        if tm_data.get('main_position'):
            opp['role_name'] = tm_data['main_position']

        # Update current_club if empty
        if not opp.get('current_club') and tm_data.get('current_club'):
            opp['current_club'] = tm_data['current_club']

        # Update player_profile
        profile = opp.setdefault('player_profile', {})
        for key in enrichment_fields:
            val = tm_data.get(key)
            if val is not None:
                profile[key] = val

        opp['tm_enriched'] = True
        updated += 1

        stats_str = f"app={tm_data.get('appearances', '?')} gol={tm_data.get('goals', '?')} ast={tm_data.get('assists', '?')}"
        mv_str = tm_data.get('market_value_formatted', 'N/A')
        age_str = opp.get('age', '?')
        print(f"  OK: age={age_str} {stats_str} MV={mv_str}")

        # Save periodically
        if updated % 5 == 0:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(opps, f, ensure_ascii=False, indent=2)
            print(f"  [SAVED] {updated} enriched so far")

        time.sleep(RATE_LIMIT_DELAY)

    # Final save
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(opps, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"ENRICHMENT COMPLETE: {updated} updated, {errors} errors out of {len(to_enrich)} attempted")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
