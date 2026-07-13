#!/usr/bin/env python3
"""
Enrichment via Transfermarkt — direct, free, no LLM, no daily cap.

Reads real Transfermarkt profiles (src/tm_scraper) instead of Gemini grounding.
The data is authoritative (straight from the source) and costs nothing, so the
free-tier 20/day Gemini cap no longer gates the pipeline — Gemini is left only
for discovery (~8 calls/day, well under the cap).
"""
import sys
import json
import time
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from src import tm_scraper

DATA_FILE = Path("data/opportunities.json")
DATA_FILE_DOCS = Path("docs/data.json")
POLITE_DELAY = 0.6       # seconds between requests — be a good citizen
MAX_PER_RUN = 80         # spread a large backlog across runs (still free)
SAVE_EVERY = 10

_JUNK_TERMS = [
    'transfermarkt', 'calciomercato', 'svincolati', 'la casa di c',
    'rádio', 'fischio finale', 'ultime notizie', 'football club',
    'web radio', 'il portale', 'il piccolo', 'management magazine',
    'next pro wiki', 'chiamarsi bomber', 'spareggi nazionali', 'spareggi',
    'stagione sportiva', 'sport news', 'giornale', 'magazine',
    'notiziario', 'dipartimento', 'interregionale', 'associazione',
    'sky sport', 'rappresentativa', 'juniores cup', 'parametro zero',
    'football italy', 'migliori giovani', 'giovani talenti', 'occasione serie',
    'notizie calcio', 'scuola superiore', 'tutto mercato', 'calciomercato live',
    'accordo collettivo', 'guardian', 'ultimo uomo', 'mediaset',
    'jugadores libres', 'ranking', 'classifica', 'tabella',
    'reserve league', 'liga profesional', 'selección', 'seleccion',
]

_TM_KEYS = ['nationality', 'foot', 'market_value', 'market_value_formatted',
            'height_cm', 'birth_date', 'contract_expires', 'tm_url', 'agent',
            'appearances', 'goals', 'assists', 'minutes_played']


def _is_enrichable(name) -> bool:
    if not isinstance(name, str) or len(name) < 3 or '|' in name:
        return False
    n = name.lower()
    return not any(t in n for t in _JUNK_TERMS)


def apply_tm_data(opp: dict, tm: dict) -> bool:
    """Merge Transfermarkt data into an opportunity. Returns True if locked."""
    if tm.get('market_value_eur') and not tm.get('market_value'):
        tm['market_value'] = tm['market_value_eur']
    if tm.get('market_value_text') and not tm.get('market_value_formatted'):
        tm['market_value_formatted'] = tm['market_value_text']

    for key in _TM_KEYS:
        if tm.get(key) is not None:
            opp[key] = tm[key]
    # role from TM position (only if we don't already have one)
    if tm.get('main_position') and not (opp.get('role_name') or opp.get('role')):
        opp['role_name'] = tm['main_position']
    if tm.get('current_club') and not opp.get('current_club'):
        opp['current_club'] = tm['current_club']

    profile = opp.get('player_profile')
    if not isinstance(profile, dict):
        profile = {}
        opp['player_profile'] = profile
    for key in _TM_KEYS:
        if tm.get(key) is not None:
            profile[key] = tm[key]

    if not opp.get('age') and tm.get('birth_date'):
        try:
            age = datetime.now().year - int(str(tm['birth_date'])[:4])
            if 10 <= age <= 60:
                opp['age'] = age
        except (ValueError, TypeError):
            pass

    # Lock as enriched only when there's a real TM link + substantive data.
    verified = isinstance(tm.get('tm_url'), str) and 'transfermarkt' in tm['tm_url']
    has_substance = any(tm.get(k) for k in ['market_value', 'contract_expires', 'birth_date'])
    opp['tm_enriched'] = bool(verified and has_substance)
    return opp['tm_enriched']


def main():
    if not DATA_FILE.exists():
        print(f"File {DATA_FILE} non trovato!")
        return
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    opportunities = data if isinstance(data, list) else data.get('opportunities', [])
    print(f"Trovate {len(opportunities)} opportunità.")

    pending = [o for o in opportunities
               if _is_enrichable(o.get('player_name')) and o.get('tm_enriched') is not True]
    print(f"Da arricchire via Transfermarkt: {len(pending)} (limite run: {MAX_PER_RUN})")
    if not pending:
        print("Niente da fare.")
        return

    enriched = found = 0
    for i, opp in enumerate(pending[:MAX_PER_RUN], 1):
        name = opp['player_name']
        tm = {}
        try:
            tm = tm_scraper.enrich(name, opp.get('tm_url'))
        except Exception as e:
            print(f"  [{i}] {name}: errore {e}")
        # Guard against namesakes: a Serie C radar never targets a 40+/retired
        # player, so an implausible TM match is almost certainly the wrong person.
        tm_age = None
        if tm.get('birth_date'):
            try:
                tm_age = datetime.now().year - int(str(tm['birth_date'])[:4])
            except (ValueError, TypeError):
                tm_age = None
        club = (tm.get('current_club') or '').lower()
        if tm and (tm_age is not None and tm_age > 39 or 'ritir' in club or 'retired' in club):
            print(f"  [{i}] ⚠ {name}: match implausibile su TM ({tm_age}a, {tm.get('current_club')}) — scartato")
            tm = {}

        if tm:
            found += 1
            if apply_tm_data(opp, tm):
                enriched += 1
                print(f"  [{i}] ✅ {name}: {tm.get('market_value_text') or '?'} · "
                      f"{tm.get('main_position') or '?'} · scad. {tm.get('contract_expires') or '?'}")
            else:
                print(f"  [{i}] ~ {name}: trovato ma dati insufficienti")
        else:
            print(f"  [{i}] — {name}: non trovato su Transfermarkt")
        if i % SAVE_EVERY == 0:
            DATA_FILE.write_text(json.dumps(opportunities, ensure_ascii=False, indent=2), encoding='utf-8')
        time.sleep(POLITE_DELAY)

    DATA_FILE.write_text(json.dumps(opportunities, ensure_ascii=False, indent=2), encoding='utf-8')
    if enriched and DATA_FILE_DOCS.exists():
        DATA_FILE_DOCS.write_text(json.dumps(opportunities, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\nProcessati: {min(len(pending), MAX_PER_RUN)} | Trovati su TM: {found} | "
          f"Verificati: {enriched} | Costo: 0 (nessuna chiamata a pagamento)")


if __name__ == "__main__":
    main()
