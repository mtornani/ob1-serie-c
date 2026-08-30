#!/usr/bin/env python3
"""
OB1 Lega Pro — confronto A/B sulla route "compare" (Ollama Cloud/locale)

Perché
------
Con Groq rate-limited, OpenRouter morto e NVIDIA su 404 (vedi PR #48/#49),
"compare" (endpoint OpenAI-compatible self-hosted — Ollama Cloud nel caso
d'uso reale, vedi PR #50) è diventata un'alternativa concreta per il task
`triage`. Prima di scegliere un modello a intuito, questo script lo prova
sugli STESSI articoli reali e con lo STESSO prompt che userebbe la pipeline
in produzione (src/scraper_global.py, _extract_players) — non un prompt
di prova inventato per l'occasione.

Zero scritture: non tocca data/opportunities.json né il seen-store di
produzione. OB1_WATCH=0 forza "tutto sembra nuovo" invece di consumare la
memoria condivisa — lanciare questo test più volte di fila non fa sparire
articoli dalla prossima run vera del cron.

Uso
---
Lanciato da .github/workflows/test-compare-model.yml, un modello alla
volta (env COMPARE_MODEL): un dispatch per candidato, si confrontano i log.
Nessun'altra chiave LLM va passata nell'ambiente di questo job — così il
gateway ha UNA sola rotta possibile per il triage e il confronto non è
inquinato da un fallback silenzioso su groq/nvidia/altro.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("OB1_WATCH", "0")

from src.scraper_global import GlobalScraper
from src.watch.poller import load_sources, poll_new_items
from src.free_stack import describe_stack, has_any_llm

LEAGUE = "italy_serie_c_d"
CHUNK_SIZE = 8      # stesso FEED_TRIAGE_CHUNK di scraper_global.py
SAMPLE_CHUNKS = 2   # 2 blocchi reali, non tutto il feed: un test, non un run


def main() -> int:
    model = os.getenv("COMPARE_MODEL", "")
    print(f"=== Test triage — modello: {model or '(COMPARE_MODEL non impostata)'} ===")
    print(f"Catena attiva: {describe_stack()}")
    if not has_any_llm():
        print("Nessuna rotta LLM disponibile — controllare COMPARE_BASE_URL/COMPARE_MODEL/COMPARE_API_KEY")
        return 1

    sources = load_sources(league_id=LEAGUE)
    print(f"Fonti feed configurate: {len(sources)}")
    items = poll_new_items(sources)
    print(f"Articoli reali trovati: {len(items)}")
    if not items:
        print("Nessun articolo disponibile in questo momento — impossibile testare su dati reali")
        return 1

    scraper = GlobalScraper()
    chunks = [items[i:i + CHUNK_SIZE] for i in range(0, len(items), CHUNK_SIZE)][:SAMPLE_CHUNKS]

    totale_giocatori = 0
    totale_articoli = 0
    t_start = time.time()
    for i, chunk in enumerate(chunks):
        results = [it.as_search_result() for it in chunk]
        t0 = time.time()
        players = scraper._extract_players(results, context="Serie C, D & Eccellenza Italiana")
        dt = time.time() - t0
        totale_articoli += len(chunk)
        print(f"--- blocco {i + 1}/{len(chunks)}: {len(chunk)} articoli, {dt:.1f}s ---")
        if not players:
            print("  nessun giocatore estratto (0 risultati o chiamata fallita)")
        for p in players:
            desc = (p.get("description") or "")[:60]
            print(f"  + {p.get('player_name')!r} | {p.get('opportunity_type')} | {desc}")
        totale_giocatori += len(players)

    print(f"\n=== esito ({model or '?'}) ===")
    print(f"articoli testati: {totale_articoli}")
    print(f"giocatori estratti: {totale_giocatori}")
    print(f"tempo totale: {time.time() - t_start:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
