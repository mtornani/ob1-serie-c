# OB1 Scout Serie C - Project Status

**Ultimo aggiornamento:** 2026-02-26
**Versione:** v3.4
**Percorso progetto:** `D:\AI\ob1-serie-c-dev`
**Branch attivo:** `main`
**Ultimo commit:** `428f375` - DS report: enforce quality filters, variable player count

> **NOTA PER AI ASSISTENTI:** Questo e' l'UNICO file di stato del progetto.
> Aggiornalo quando fai modifiche significative. NON creare file di stato alternativi.
> I file in `src/satarch/` e `config/satarch.yaml` sono un progetto separato, NON fanno parte di OB1 Scout.

---

## Cos'e' OB1 Scout?

Sistema di **scouting calcistico automatizzato** per la Serie C italiana. Scrapa notizie di mercato, arricchisce i dati con Transfermarkt, calcola un punteggio di opportunita', e li rende disponibili tramite:
- **Bot Telegram** (@Ob1LegaPro_bot) - ricerca naturale, wizard, alert
- **Dashboard Web** (GitHub Pages) - filtri interattivi, PWA
- **Report HTML narrativo** - player card da scout professionista
- **Report settimanali** - HTML + PDF DS-Ready + social posts

---

## Stato Completamento: ALPHA + Post-Alpha Features

### Componenti Core (Alpha - Completi)

| Componente | Stato | Note |
|---|---|---|
| Bot Telegram | Completo | Cloudflare Workers, LLM search (Gemma 3 27B via OpenRouter) |
| Dashboard Web | Completo | PWA, responsive, dark/light mode, tutorial |
| Report HTML narrativo | Completo | Player card, score breakdown, per reparto |
| Backend Scraper | Completo | Ogni 6h via GitHub Actions (Serper + Tavily) |
| Enrichment Transfermarkt | Completo | Nazionalita', eta', club precedenti, agente, stats |
| DNA Club Matching | Completo | Profili club, scoring affinita' |
| Notifiche | Completo | HOT alerts push, daily digest, watch profiles |
| Filtro notizie stale | Completo | date_filter.py - scarta articoli >60 giorni |
| OB1 Score | Completo | 6 fattori ponderati (freshness, type, experience, age, source, completeness) |

### Features Post-Alpha (Feb 2026)

| Feature | Stato | Note |
|---|---|---|
| Snapshot storico opportunita' | Completo | data/snapshots/ con timestamp |
| Campo `agent` da Transfermarkt | Completo | Salvato nell'enrichment |
| Stats stagionali da TM | Completo | Presenze, gol, assist, minuti |
| Alert svincolato stale | Completo | Segnalazione automatica |
| Report settimanale HTML | Completo | docs/reports/ con stats + top10 |
| Report DS-Ready PDF | Completo | PDF con filtri qualita', diversificazione |
| Social post generator | Completo | Post X + Telegram automatici |
| Canale Telegram pubblico | Completo | Report + murales settimanali |
| Quick ingest | Completo | Script per aggiornamento rapido KB |

---

## Dati Attuali (2026-02-20)

| Metrica | Valore |
|---|---|
| Opportunita' totali | **100** |
| HOT (ob1_score 80+) | 0 |
| WARM (ob1_score 60-79) | 77 |
| COLD (ob1_score <60) | 23 |
| Score range | 54 - 78 (media 64.5) |
| Profili club DNA | 20 (clubs/*.json) |
| Ultimo aggiornamento dati | 2026-02-19 18:57 UTC |

---

## Stack Tecnologico

| Componente | Tecnologia |
|---|---|
| Backend/Scraper | Python 3.12 (locale), 3.11 (GitHub Actions) |
| Bot Telegram | TypeScript, Cloudflare Workers |
| AI (bot search) | Gemma 3 27B via OpenRouter |
| AI (enrichment) | Google Gemini API |
| Scraping fonti | Serper.dev + Tavily |
| Dashboard | HTML/CSS/JS vanilla, GitHub Pages, PWA |
| CI/CD | GitHub Actions (4 workflow) |
| Report PDF | Python (matplotlib/reportlab) |

---

## Struttura Progetto

```
ob1-serie-c-dev/
├── src/                          # Backend Python (13 file, escluso satarch)
│   ├── scraper.py                # News collection (Serper) + filtro date
│   ├── scraper_tavily.py         # News collection (Tavily) + filtro date
│   ├── date_filter.py            # Estrae date da URL, filtra stale
│   ├── enricher_tm.py            # Transfermarkt enrichment
│   ├── scoring.py                # OB1 Score algorithm
│   ├── history.py                # Tracking evoluzione
│   ├── reporter.py               # PDF generation
│   ├── agent.py                  # Conversational AI
│   ├── ingest.py                 # Gemini File Search
│   ├── notifier.py               # Telegram notifications
│   ├── models.py                 # Data structures
│   ├── __init__.py
│   └── dna/                      # DNA matching system (4 file)
│       ├── matcher.py
│       ├── scorer.py
│       ├── models.py
│       └── __init__.py
│
├── scripts/                      # Pipeline scripts (15 file)
│   ├── run_ingest.py             # Pipeline principale
│   ├── run_enrichment.py         # Arricchimento TM
│   ├── run_cleanup.py            # Pulizia dati
│   ├── generate_dashboard.py     # Aggiorna data.json
│   ├── generate_report.py        # Report HTML narrativo
│   ├── generate_weekly_report.py # Report settimanale
│   ├── generate_ds_report.py     # Report PDF DS-Ready
│   ├── generate_matches.py       # DNA matches
│   ├── generate_social_post.py   # Post social settimanali
│   ├── send_notification.py      # Notifica Telegram
│   ├── send_public_report.py     # Report su canale pubblico
│   ├── enrich_all_players.py     # Enrichment bulk
│   ├── force_re_enrich.py        # Force re-enrichment
│   ├── scrape_squadre_b.py       # Scrape squadre B
│   └── quick_ingest.py           # Quick update KB
│
├── bot/
│   └── telegram_bot.py           # Bot entry point (legacy?)
│
├── workers/telegram-bot/src/     # Bot Telegram (26 file TS)
│   ├── index.ts                  # Worker entry point
│   ├── handlers.ts               # Message handlers
│   ├── smart-search.ts           # LLM-powered search
│   ├── telegram.ts               # Telegram API
│   ├── scout-wizard.ts           # Wizard stateless (v3.2)
│   ├── talent-search.ts          # Talent search
│   ├── dna.ts                    # DNA matching
│   ├── dna-adapter.ts            # DNA adapter
│   ├── conversational.ts         # Voice + NLP
│   ├── response-generator.ts     # AI Scout persona
│   ├── nlp.ts                    # Natural language parsing
│   ├── llm-classifier.ts         # LLM fallback classifier
│   ├── openrouter.ts             # OpenRouter client
│   ├── formatters.ts             # Output formatting
│   ├── data.ts                   # Data access
│   ├── types.ts                  # Type definitions
│   ├── watch/                    # Watch profiles (6 file)
│   └── notifications/            # Digest & alerts (4 file)
│
├── config/                       # Configurazione YAML
│   ├── sources.yaml              # Query scraping + fonti
│   ├── clubs.yaml                # Configurazione club
│   └── prompts.yaml              # Prompt templates
│
├── data/                         # Dati runtime
│   ├── opportunities.json        # Database opportunita'
│   ├── stats.json                # Statistiche aggregate
│   ├── dna_matches.json          # Match DNA
│   ├── history_log.json          # Storico evoluzione
│   ├── clubs/                    # 20 profili club DNA (.json)
│   ├── players/squadre_b.json    # Talenti squadre B
│   ├── snapshots/                # Snapshot storici (9+ file)
│   └── social/                   # Post social generati
│
├── docs/                         # GitHub Pages (output pubblico)
│   ├── index.html                # Dashboard principale
│   ├── report.html               # Report HTML narrativo
│   ├── presentation.html         # Presentazione
│   ├── data.json                 # Dati per dashboard (auto-updated)
│   ├── dna_matches.json          # DNA matches per dashboard
│   ├── js/app.js                 # Dashboard JS
│   ├── js/dna-engine.js          # DNA engine JS
│   ├── css/style.css             # Stili
│   ├── manifest.json             # PWA manifest
│   ├── sw.js                     # Service worker
│   └── reports/                  # Report settimanali
│       ├── latest.json
│       ├── 2026-02-16/           # (index.html, stats.json, top10.json)
│       ├── 2026-02-19/           # (index.html, stats.json, top10.json)
│       └── ds_report_2026-02-19.pdf
│
├── .github/workflows/            # CI/CD
│   ├── ingest.yml                # Ogni 6h: scrape + enrich + dashboard + report + notify
│   ├── weekly-report.yml         # Lunedi' 08:00 UTC: report + DS PDF + social
│   ├── cleanup.yml               # Pulizia dati
│   └── pages.yml                 # Deploy GitHub Pages
│
├── .dev/                         # Spec e roadmap (~15 file .md)
├── AGENTS.md                     # Istruzioni per AI assistenti
├── requirements.txt
└── .env.example
```

---

## OB1 Score - Composizione

| Fattore | Peso | Cosa Misura |
|---|---|---|
| Freshness | 20% | Quanto e' recente la notizia |
| Opportunity Type | 20% | Tipo operazione (svincolato > prestito > trasferimento) |
| Experience | 20% | Numero club precedenti in Serie C |
| Age Profile | 20% | Profilo anagrafico (fascia ideale 22-28) |
| Source Quality | 10% | Affidabilita' della fonte |
| Completeness | 10% | Quanti dati abbiamo sul giocatore |

**Nota:** Lo score NON misura il talento del giocatore, ma quanto l'opportunita' di mercato e' interessante e accessibile.

---

## GitHub Actions Workflow

### ingest.yml (ogni 6 ore)
```
1. ouroboros_run.py      -> Scraping globale (Tavily) + DNA matching + scoring
2. generate_dashboard.py -> Aggiorna data.json (con filtri anti-junk v3.4)
3. generate_report.py    -> Report HTML narrativo
4. send_notification.py  -> Notifica Telegram
5. Commit & Push         -> Pubblica su GitHub Pages
```

### weekly-report.yml (lunedi' 08:00 UTC)
```
1. generate_weekly_report.py -> Report settimanale HTML
2. generate_ds_report.py     -> Report PDF DS-Ready
3. generate_social_post.py   -> Post X + Telegram
4. send_public_report.py     -> Pubblica su canale Telegram
5. Commit & Push
```

---

## URLs Pubbliche

| Risorsa | URL |
|---|---|
| Dashboard | https://mtornani.github.io/ob1-serie-c/ |
| Report HTML | https://mtornani.github.io/ob1-serie-c/report.html |
| Bot Telegram | @Ob1LegaPro_bot |

---

## Comandi Bot

| Comando | Descrizione |
|---|---|
| `/start` | Avvia il bot |
| `/report` | Report mercato completo |
| `/hot` | Opportunita' top (score 80+) |
| `/warm` | Buone opportunita' (60-79) |
| `/all` | Lista completa |
| `/search <nome>` | Cerca giocatore |
| `/watch` / `/watch add` | Gestisci/crea alert |
| `/digest` | Anteprima digest |
| `/talenti` | Top talenti Under 23 |
| `/dna <club>` | DNA match per club |
| `/scout` | Wizard guidato (stateless) |
| `/stats` | Statistiche |
| `/stale` | Svincolati stale |
| `/help` | Guida completa |
| Testo libero | Ricerca naturale (LLM) |
| Messaggio vocale | Trascrizione + ricerca |

---

## Costi Operativi

| Servizio | Costo Mensile |
|---|---|
| Serper.dev | $0-5 (2500 query free/mese) |
| Tavily | $0 (free tier) |
| OpenRouter (Gemma) | $0 (free tier) |
| Cloudflare Workers | $0 (free tier) |
| GitHub Actions | $0 (free tier, 2000 min) |
| GitHub Pages | $0 |
| **TOTALE** | **~$0-5/mese** |

---

## Note Tecniche

- **Zero test nel progetto** - non esistono file di test. Da valutare se aggiungerne.
- Il campo score in `data.json` e' `ob1_score` (non `score`)
- Il wizard Scout e' 100% stateless (stato nel `callback_data` Telegram, max 25 bytes)
- Le date vengono estratte dagli URL delle notizie per filtrare articoli stale (>60 giorni)
- **Pipeline Ouroboros (v5.1)**: scraper globale multi-lega (IT/BR/AR), ma il dashboard filtra solo entries italiane
- **Filtri anti-junk (v3.4)**: geographic filter (solo italy*), blacklist URL generiche TM, blacklist nomi-pagina, purge al boot

---

## Roadmap Post-Alpha

| Feature | Priorita' | Note |
|---|---|---|
| Arricchimento TM piu' robusto (piede, valore) | Alta | Solo 2% piede, 1% valore attualmente |
| Comparison tool (side-by-side) | Media | |
| Test suite | Media | Attualmente zero test |
| Voice conversation (continua) | Bassa | |
| Multi-lingua (EN) | Bassa | |

---

*Documento aggiornato il 2026-02-20*
