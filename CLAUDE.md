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

## FREEZE PILOTA K-SPORT (2026-05-27 → ~Settembre 2026)

**I file di scoring sono congelati per tutta la durata del pilota K-Sport.**

### Regole FREEZE — OBBLIGATORIE

NON modificare pesi, soglie, formule o classificazioni in questi file:

**Python (src/):**
- `src/scoring.py` — OB1Scorer SCORE-002
- `src/scoring_global.py` — OB1Scorer Global
- `src/dna/scorer.py` — DNA scorer
- `src/notifier.py` — Notifier (logica alert)
- `src/reporter.py` — Reporter
- `src/dna/engine_global.py` — DNA engine

**Python (scripts/):**
- `scripts/generate_dashboard.py`
- `scripts/generate_scouting_reports.py`
- `scripts/generate_report.py`
- `scripts/backtest_score.py`
- `scripts/generate_ds_report.py`
- `scripts/generate_weekly_report.py`

**TypeScript (workers/):**
- `workers/telegram-bot/src/watch/types.ts`
- `workers/telegram-bot/src/watch/matcher.ts`
- `workers/telegram-bot/src/watch/wizard.ts`

### Cosa è VIETATO durante il freeze

- Modificare pesi dello scoring (es. freshness 15%, experience 20%, ...)
- Modificare soglie di classificazione (HOT ≥ 70, WARM ≥ 57, COLD < 57)
- Modificare formule di calcolo del punteggio
- Aggiungere nuovi fattori di scoring
- Modificare la logica di matching del Watch bot

### Cosa è PERMESSO durante il freeze

- Documentazione e commenti
- Error handling, logging, robustezza
- Presentazione dei dati esistenti (HTML, formatting)
- Tracciabilità accessi e analytics
- Bug fix che NON cambiano l'output numerico dello scoring
- Qualsiasi modifica richiede **approvazione esplicita scritta di Mirko Tornani**

---

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

### 2026-06-01 — Backend robustness (K-Sport pilot prep)
- Fix 1: html.escape su tutti i campi dinamici Telegram, rimossa troncatura summary
- Fix 2: admin_alert(severity, source, message) in notifier.py + wired in ouroboros_run.py + ingest.yml failure step + TELEGRAM_CHAT_ID fix
- Fix 3: sanity_check.py — validazione post-pipeline (file existence, count, scoring sanity, freshness)
- Fix 5: FREEZE PILOTA K-SPORT in CLAUDE.md — regole obbligatorie per tutta la durata del pilota

### 2026-03-24 — Pipeline refresh + Security hardening
- Fresh scraping via Tavily: 4 nuove opportunità (Cinque, Rosa, Capanni, Kljajic)
- Enrichment Scrapling: 10/12 U23 arricchiti con stats reali da Transfermarkt
- Database cleanup: rimossi 67 entries spazzatura (non-giocatori, fonti estere)
- Report filtrati: solo giocatori Serie C con stats verificabili (esclusi Serie D)
- Security: API keys rimosse da .claude/settings.local.json, file rimosso dal tracking git
- Security: reports/scouting/ aggiunto a .gitignore (report privati, non pubblici)
- Security: .claude/settings.local.json aggiunto a .gitignore
- Dashboard docs/data.json rigenerato con scoring SCORE-002 aggiornato
- Fix: generate_scouting_reports.py output path corretto (reports/ invece di docs/reports/)
- 5 report U23 finali: Levak, Shpendi, Buffon, Doumbia, Gallea

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
