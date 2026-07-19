#!/usr/bin/env python3
"""
Enrichment Transfermarkt — free direct read first, Gemini-batch as fallback.

Two engines, tried in order per player:
  1. src/tm_scraper — direct HTTP read of the Transfermarkt profile page.
     Free, no LLM, no daily cap. Primary path whenever it can find the player.
  2. src/enricher_tm.TransfermarktEnricher — Gemini-grounded batch enrichment
     (Grok's circuit-breaker: stops cleanly the moment the daily quota dies,
     no wasted retries). Fallback only for players the free path can't find —
     e.g. if a datacenter IP gets blocked by Transfermarkt's anti-bot, or the
     player genuinely isn't indexed under that name.

This keeps the pipeline's steady-state cost near zero (most players resolve
via #1) while keeping a proven, production-tested safety net (#2) instead of
depending entirely on an unverified-in-CI direct-fetch path.
"""
import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from src import tm_scraper
from src.enricher_tm import TransfermarktEnricher, BATCH_SIZE

DATA_FILE = Path("data/opportunities.json")
DATA_FILE_DOCS = Path("docs/data.json")

POLITE_DELAY = 0.6         # seconds between direct-TM requests — be a good citizen
SAVE_EVERY = 10            # checkpoint during the direct-TM pass
DELAY_BETWEEN_BATCHES = 5  # seconds between Gemini fallback batches

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


def _is_implausible_namesake(tm: dict) -> bool:
    """A Serie C radar never targets a 40+/retired player, so a TM match
    that old or retired is almost certainly the wrong person (namesake)."""
    if not tm:
        return False
    age = None
    if tm.get('birth_date'):
        try:
            age = datetime.now().year - int(str(tm['birth_date'])[:4])
        except (ValueError, TypeError):
            age = None
    club = (tm.get('current_club') or '').lower()
    return bool((age is not None and age > 39) or 'ritir' in club or 'retired' in club)


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


def enrich_direct(pending: list, all_opps: list) -> list:
    """Pass 1: free direct Transfermarkt read. Returns the players still
    unenriched afterwards (to hand off to the Gemini fallback)."""
    still_pending = []
    found = enriched = 0
    for i, opp in enumerate(pending, 1):
        name = opp['player_name']
        tm = {}
        try:
            tm = tm_scraper.enrich(name, opp.get('tm_url'))
        except Exception as e:
            print(f"  [{i}/{len(pending)}] {name}: errore direct-TM {e}")

        if _is_implausible_namesake(tm):
            print(f"  [{i}/{len(pending)}] ⚠ {name}: match implausibile su TM "
                  f"({tm.get('current_club')}) — scartato")
            tm = {}

        if tm:
            found += 1
            if apply_tm_data(opp, tm):
                enriched += 1
                print(f"  [{i}/{len(pending)}] ✅ {name}: {tm.get('market_value_text') or '?'} · "
                      f"{tm.get('main_position') or '?'} · scad. {tm.get('contract_expires') or '?'}")
            else:
                print(f"  [{i}/{len(pending)}] ~ {name}: trovato ma dati insufficienti")
                still_pending.append(opp)
        else:
            still_pending.append(opp)

        if i % SAVE_EVERY == 0:
            _save(all_opps)
        time.sleep(POLITE_DELAY)

    print(f"\nDirect-TM: {found}/{len(pending)} trovati, {enriched} arricchiti (costo: 0)")
    return still_pending


def enrich_gemini_fallback(pending: list, all_opps: list) -> int:
    """Pass 2: Gemini-grounded batch enrichment for whatever pass 1 missed."""
    if not pending:
        return 0
    enricher = TransfermarktEnricher()
    enriched = 0
    batches = [pending[i:i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
    if len(batches) > MAX_BATCHES_PER_RUN:
        skipped = len(batches) - MAX_BATCHES_PER_RUN
        print(f"Backlog alto: {skipped} batch rinviati alla prossima run.")
        batches = batches[:MAX_BATCHES_PER_RUN]

    for bi, batch in enumerate(batches, 1):
        if enricher.gemini_disabled:
            print(f"  [STOP] Gemini off — batch {bi}–{len(batches)} rinviati (niente thrash)")
            break
        names = [o['player_name'] for o in batch]
        print(f"\n[batch {bi}/{len(batches)}] {', '.join(names)}")
        results = enricher.enrich_players_batch(names)
        for opp in batch:
            tm = results.get(opp['player_name']) or {}
            if _is_implausible_namesake(tm):
                print(f"  ⚠ {opp['player_name']}: match implausibile — scartato")
                continue
            if tm and apply_tm_data(opp, tm):
                enriched += 1
                print(f"  ✅ {opp['player_name']}: "
                      f"{tm.get('market_value_text') or '?'} | age={opp.get('age')} "
                      f"| apps={tm.get('appearances', '?')}")
        _save(all_opps)
        if bi < len(batches) and not enricher.gemini_disabled:
            time.sleep(DELAY_BETWEEN_BATCHES)

    print(f"\nGemini fallback: {enriched}/{len(pending)} arricchiti "
          f"({len(batches)} chiamate batch)")
    return enriched


def _save(opportunities):
    DATA_FILE.write_text(json.dumps(opportunities, ensure_ascii=False, indent=2), encoding='utf-8')


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

    still_pending = enrich_direct(pending, opportunities)
    _save(opportunities)

    gemini_enriched = enrich_gemini_fallback(still_pending, opportunities)
    _save(opportunities)

    total_enriched = sum(1 for o in pending if o.get('tm_enriched') is True)
    if total_enriched and DATA_FILE_DOCS.exists():
        DATA_FILE_DOCS.write_text(json.dumps(opportunities, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\nTotale: {len(pending)} candidati | Arricchiti: {total_enriched} "
          f"(di cui {gemini_enriched} via Gemini fallback)")


if __name__ == "__main__":
    main()
