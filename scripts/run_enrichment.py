#!/usr/bin/env python3
"""
Enrichment Transfermarkt — batched.

One grounded Gemini call enriches BATCH_SIZE players at once (the cost
lever: N players -> ceil(N/BATCH_SIZE) calls instead of N). Players the
model can't find stay unlocked and retry on the next run.
"""
import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from src.enricher_tm import TransfermarktEnricher, BATCH_SIZE

DATA_FILE = Path("data/opportunities.json")
DATA_FILE_DOCS = Path("docs/data.json")
DELAY_BETWEEN_BATCHES = 5  # seconds

# Cap Gemini calls per run: backlog spikes (e.g. a big discovery day) get
# spread over multiple runs instead of burning quota in one.
# Free tier ≈20 RPD shared with discovery — keep enrichment lean.
MAX_BATCHES_PER_RUN = int(os.getenv("MAX_ENRICH_BATCHES", "4"))

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

_TM_KEYS = ['nationality', 'second_nationality', 'foot', 'market_value',
            'market_value_formatted', 'height_cm', 'birth_date', 'contract_expires',
            'tm_url', 'agent', 'appearances', 'goals', 'assists', 'minutes_played',
            'current_club']


def _is_enrichable(name) -> bool:
    if not isinstance(name, str) or len(name) < 3 or '|' in name:
        return False
    # real person: at least 2 tokens, not ALL CAPS dump, not article title
    tokens = name.split()
    if len(tokens) < 2:
        return False
    if name.isupper() and len(tokens) >= 2:
        return False
    n = name.lower()
    return not any(t in n for t in _JUNK_TERMS)


def apply_tm_data(opp: dict, tm: dict) -> bool:
    """Merge TM data into an opportunity. Returns True if locked as enriched."""
    if tm.get('market_value_eur') and not tm.get('market_value'):
        tm['market_value'] = tm['market_value_eur']
    if tm.get('market_value_text') and not tm.get('market_value_formatted'):
        tm['market_value_formatted'] = tm['market_value_text']

    for key in _TM_KEYS:
        if tm.get(key) is not None:
            opp[key] = tm[key]
    # setdefault would return an existing null value; guard for that.
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

    # Role from TM main_position if missing
    if tm.get('main_position') and not (opp.get('role_name') or opp.get('role')):
        opp['role_name'] = tm['main_position']
        opp['role'] = tm['main_position']

    # Lock only when substantive data arrived; otherwise retry next run.
    has_substance = any(tm.get(k) for k in [
        'market_value', 'appearances', 'contract_expires', 'goals', 'birth_date', 'current_club',
    ])
    opp['tm_enriched'] = has_substance
    return has_substance


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
    # Priority: missing age first (blocks publish gate), then missing club
    pending.sort(key=lambda o: (
        0 if o.get('age') in (None, '') else 1,
        0 if not (o.get('current_club') or '').strip() else 1,
        o.get('player_name') or '',
    ))
    no_age = sum(1 for o in pending if o.get('age') in (None, ''))
    print(f"Da arricchire: {len(pending)} (senza età: {no_age})")
    if not pending:
        print("Niente da fare.")
        return

    enricher = TransfermarktEnricher()
    enriched = 0
    batches = [pending[i:i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
    if len(batches) > MAX_BATCHES_PER_RUN:
        skipped = len(batches) - MAX_BATCHES_PER_RUN
        print(f"Backlog alto: {skipped} batch rinviati alla prossima run.")
        batches = batches[:MAX_BATCHES_PER_RUN]

    for bi, batch in enumerate(batches, 1):
        names = [o['player_name'] for o in batch]
        mode = "gemini" if not enricher.gemini_disabled else "fallback"
        print(f"\n[batch {bi}/{len(batches)} {mode}] {', '.join(names)}")
        results = enricher.enrich_players_batch(names)
        for opp in batch:
            tm = results.get(opp['player_name']) or {}
            if tm and apply_tm_data(opp, tm):
                enriched += 1
                print(f"  ✅ {opp['player_name']}: "
                      f"{tm.get('market_value_text') or '?'} | age={opp.get('age')} "
                      f"| apps={tm.get('appearances', '?')}")
        # Save after every batch so a crash never loses completed work.
        DATA_FILE.write_text(json.dumps(opportunities, ensure_ascii=False, indent=2), encoding='utf-8')
        if bi < len(batches):
            # Fallback path is slower (per-player Tavily); slightly longer pause
            delay = DELAY_BETWEEN_BATCHES if mode == "gemini" else 3
            time.sleep(delay)

    if enriched and DATA_FILE_DOCS.exists():
        DATA_FILE_DOCS.write_text(json.dumps(opportunities, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\nTotale: {len(pending)} candidati | Arricchiti: {enriched} | "
          f"Chiamate Gemini: {len(batches)} (era {len(pending)} prima del batching)")


if __name__ == "__main__":
    main()
