# OB1 Serie C — Contesto per AI

## Progetto
OB1 Serie C è un radar automatizzato di scouting calcistico per la Serie C italiana.
Monitora opportunità di mercato (svincolati, prestiti, rescissioni) e genera report
professionali per osservatori professionisti.

## Architettura

### Pipeline dati
```
Scraping (Tavily/Scrapling) → Enrichment (TM + Gemini) → Scoring (SCORE-002) → Report HTML
```

### Directory principali
- `src/` — Core: scraper, enricher, scorer, notifier, DNA engine
- `scripts/` — Pipeline scripts (enrichment, report generation, backtest)
- `reports/scouting/` — Report HTML individuali (PRIVATI, non in docs/)
- `docs/` — Dashboard pubblica (GitHub Pages serve da qui)
- `data/` — opportunities.json (database principale), backtest, satarch
- `bot/` — Telegram bot
- `config/` — YAML configs
- `workers/` — Cloudflare Workers (Telegram bot serverless)

### File chiave
- `data/opportunities.json` — Database opportunità (100 entries)
- `docs/data.json` — Dashboard data (generato da generate_dashboard.py)
- `src/scoring.py` — OB1Scorer con pesi SCORE-002
- `scripts/generate_scouting_reports.py` — Genera report HTML individuali
- `scripts/enrich_scrapling.py` — Enrichment via Scrapling + Gemini
- `scripts/generate_dashboard.py` — Scoring + export dashboard

## Scoring SCORE-002
8 fattori pesati (0-100):
- Attualità notizia (15%) — freshness della segnalazione
- Tipo opportunità (10%) — svincolato > prestito > mercato
- Esperienza verificata (20%) — presenze in carriera
- Profilo anagrafico (15%) — età target U23
- Valore di mercato (15%) — fascia Serie C
- Pertinenza Serie C (15%) — league fit
- Affidabilità fonte (5%) — qualità della source
- Completezza dati (5%) — dati disponibili

Classificazione: HOT ≥ 70, WARM ≥ 57, COLD < 57

## Convenzioni tecniche
- Python 3.12: `C:\Users\Mirko\AppData\Local\Programs\Python\Python312\python.exe`
- Sempre prefissare: `PYTHONIOENCODING=utf-8`
- API keys in `.env` (gitignored), MAI hardcoded
- `.env` ha un bug noto: `python-dotenv` sovrascrive env vars reali con placeholder.
  Gli script di enrichment salvano le env vars PRIMA di caricare dotenv.
- Gemini model: `gemini-2.5-flash` (NON 2.0-flash, è deprecato/404)
- Scrapling: usare `page.get_all_text()` (NON `page.text` che ritorna vuoto)
- Git: branch `main`, commit in inglese, push su origin

## Sicurezza
- Report scouting in `reports/` (NON in `docs/` — non devono essere pubblici)
- `.env` è in .gitignore
- `.claude/settings.local.json` NON deve contenere API keys reali
- La repo è pubblica su GitHub — attenzione a cosa si committa

## Contesto business
- I report sono destinati a osservatori professionisti (es. Daniele Corazza, Ascoli)
- Devono contenere SOLO dati verificabili (Transfermarkt, FBRef, Lega Pro)
- Zero errori = test di credibilità. Niente gergo tecnico, solo linguaggio calcistico
- Focus: Under 23, mix di ruoli, Serie C italiana

## Changelog

### 2026-03-23 — Scouting Reports v1
- Creato pipeline enrichment con Scrapling (headless browser) + Gemini 2.5 Flash
- 14 report individuali U23 con dati TM reali (presenze, gol, assist, valore, agente)
- Summary report con tabella riepilogativa e distribuzione per reparto
- Scoring SCORE-002 applicato a 82 giocatori (12 HOT, 55 WARM, 15 COLD)
- Fix: nazionalità Buffon/Pelamatti, deduplicazione Leoncini, model Gemini
- Security: report spostati da docs/ a reports/, API keys rimosse da settings
- Dati arricchiti: 18 U23 players con stats stagionali da Transfermarkt

### 2026-03-20 — Dashboard v2
- Redesign dashboard con filtri tipo, ordinamento, stats live
- Pipeline enrichment integrata con Tavily + Gemini
- OG tags per condivisione social
- Harmonize design system con ecosistema Ouroboros
