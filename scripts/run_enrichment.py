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
from src.entity_gate import classify
from src.metrics import METRICS_FILE, get_metrics

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
            'enrichment_source',
            'market_value_formatted', 'height_cm', 'birth_date', 'contract_expires',
            'tm_url', 'agent', 'appearances', 'goals', 'assists', 'minutes_played',
            'current_club']


def _is_enrichable(opp) -> bool:
    """
    Si spende su questo record? Il gate è condiviso con la discovery
    (src/entity_gate.py): una sola fonte di verità invece di tre liste
    divergenti. Accetta un dict o, per compatibilità, un nome.
    """
    if isinstance(opp, str):
        opp = {"player_name": opp}
    return classify(opp).spend_allowed


def apply_tm_data(opp: dict, tm: dict) -> bool:
    """
    Merge TM data into an opportunity. Returns True if locked as enriched.

    Conta anche i FATTI NUOVI (ARCH-002 Fase 1): un campo che prima era vuoto e
    ora ha un valore. Non si contano le riscritture dello stesso dato — quelle
    sono lavoro rifatto, non informazione nuova, ed è proprio la differenza che
    il costo per fatto deve rendere visibile.
    """
    metrics = get_metrics()
    if tm.get('market_value_eur') and not tm.get('market_value'):
        tm['market_value'] = tm['market_value_eur']
    if tm.get('market_value_text') and not tm.get('market_value_formatted'):
        tm['market_value_formatted'] = tm['market_value_text']

    for key in _TM_KEYS:
        if tm.get(key) is not None:
            if not opp.get(key):
                metrics.fact(key)
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
                metrics.fact('age')
        except (ValueError, TypeError):
            pass

    # Role from TM main_position if missing
    if tm.get('main_position') and not (opp.get('role_name') or opp.get('role')):
        opp['role_name'] = tm['main_position']
        opp['role'] = tm['main_position']
        metrics.fact('role_name')

    # Lock only when substantive data arrived; otherwise retry next run.
    has_substance = any(tm.get(k) for k in [
        'market_value', 'appearances', 'contract_expires', 'goals', 'birth_date', 'current_club',
    ])
    opp['tm_enriched'] = has_substance
    return has_substance


def _report_metrics() -> None:
    """
    Riga di metriche di fine run (ARCH-002 Fase 1). Va emessa anche quando non
    c'è stato niente da fare: una run a vuoto è essa stessa un'informazione
    (coda vuota), e i buchi nella serie storica non si possono ricostruire.
    """
    try:
        from src.llm import get_gateway
        print(get_gateway().run_summary())
    except Exception:
        pass
    metrics = get_metrics()
    print(metrics.summary())
    if metrics.write(METRICS_FILE):
        print(f"  [METRICS] riga aggiunta a {METRICS_FILE}")


def main():
    if not DATA_FILE.exists():
        print(f"File {DATA_FILE} non trovato!")
        _report_metrics()
        return
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    opportunities = data if isinstance(data, list) else data.get('opportunities', [])
    print(f"Trovate {len(opportunities)} opportunità.")

    pending = [o for o in opportunities
               if _is_enrichable(o) and o.get('tm_enriched') is not True]
    skipped = len(opportunities) - len(pending) - sum(
        1 for o in opportunities if o.get('tm_enriched') is True)
    if skipped > 0:
        print(f"Scartati dal gate (nessuna spesa): {skipped}")
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
        _report_metrics()
        return

    enricher = TransfermarktEnricher()
    enriched = 0
    batches = [pending[i:i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
    if len(batches) > MAX_BATCHES_PER_RUN:
        skipped = len(batches) - MAX_BATCHES_PER_RUN
        print(f"Backlog alto: {skipped} batch rinviati alla prossima run.")
        batches = batches[:MAX_BATCHES_PER_RUN]

    for bi, batch in enumerate(batches, 1):
        if enricher.stalled:
            print(f"  [STOP] nessuna rotta LLM — batch {bi}–{len(batches)} rinviati")
            break
        names = [o['player_name'] for o in batch]
        get_metrics().player_touched(len(names))
        print(f"\n[batch {bi}/{len(batches)}] {', '.join(names)}")
        results = enricher.enrich_players_batch(names)
        for opp in batch:
            tm = results.get(opp['player_name']) or {}
            if tm and apply_tm_data(opp, tm):
                enriched += 1
                print(f"  ✅ {opp['player_name']}: "
                      f"{tm.get('market_value_text') or '?'} | age={opp.get('age')} "
                      f"| apps={tm.get('appearances', '?')}")
        DATA_FILE.write_text(json.dumps(opportunities, ensure_ascii=False, indent=2), encoding='utf-8')
        if bi < len(batches) and not enricher.stalled:
            time.sleep(DELAY_BETWEEN_BATCHES)

    # NB: docs/data.json ha il formato dashboard (dict con opportunities/stats),
    # non la lista grezza. Scriverci la lista lo corrompe finché
    # generate_dashboard.py non gira. Lo rigenera lui, subito dopo in ingest.yml.
    print(f"\nTotale: {len(pending)} candidati | Arricchiti: {enriched} | "
          f"Batch elaborati: {len(batches)}")
    # ARCH-002 Fase 1: il numero che dice se le ottimizzazioni funzionano.
    _report_metrics()


if __name__ == "__main__":
    main()
