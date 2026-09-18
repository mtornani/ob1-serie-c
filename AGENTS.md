# OB1 Serie C Radar

## Stack
- Python 3.12
- Gemini API (`google-genai`) per discovery/enrichment
- Tavily per search (fallback Serper)
- Cloudflare Worker TypeScript per il bot Telegram (unico bot attivo)
- YAML per configurazione

## Struttura
- `src/` — Core: scraper_global, enricher_tm, scoring SCORE-003, quality_gate, notifier
- `scripts/` — Pipeline: ouroboros_run, run_enrichment, generate_dashboard, sanity_check
- `config/` — YAML (leagues, sources, clubs, prompts)
- `data/` — `opportunities.json` (DB principale)
- `docs/` — Dashboard pubblica (GitHub Pages)
- `reports/` — Report scouting privati (NON pubblici)
- `workers/telegram-bot/` — Bot Telegram live
- `bot/` — Legacy Python, non è il bot in produzione

## Convenzioni
- Configurazione tramite `.env` e YAML in `config/`
- Encoding: sempre `PYTHONIOENCODING=utf-8` sugli script Python
- API keys mai hardcoded; `.env` è gitignored
- Git: branch `main`, commit in inglese con prefisso semantico
- Report in `reports/` non vanno in `docs/`
- `src/satarch/` è progetto separato: non toccare senza richiesta

## Comandi utili
```bash
# Discovery
PYTHONIOENCODING=utf-8 python scripts/ouroboros_run.py

# Enrichment Transfermarkt
PYTHONIOENCODING=utf-8 python scripts/run_enrichment.py

# Dashboard + quality gate
PYTHONIOENCODING=utf-8 python scripts/generate_dashboard.py

# Sanity post-pipeline
PYTHONIOENCODING=utf-8 python scripts/sanity_check.py

# Unit test gate + score
PYTHONIOENCODING=utf-8 python -m unittest tests.test_quality_gate tests.test_scoring -v
```

Pipeline CI: `.github/workflows/ingest.yml` (cron 6h).
Jina (`JINA_API_KEY`): già nel workflow — Reader/Search per profili Transfermarkt. Non è discovery di notizie.
