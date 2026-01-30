# OB1 Serie C Radar - Project Overview

## Vision

**OB1** = "Osservatorio B1" - Scout AI per Serie C e Serie D italiana.

A differenza di un semplice aggregatore di notizie, OB1 è un **agente conversazionale** che:
- Accumula conoscenza nel tempo (RAG su Gemini File Search)
- Risponde in linguaggio naturale
- Impara dai criteri di ricerca degli utenti
- Costa quasi nulla (~$5/mese)

## Target Users

| Persona | Ruolo | Esigenza Primaria |
|---------|-------|-------------------|
| **Mauro Cevoli** | DS / Scout | Alert immediati su svincolati interessanti |
| **Claudio Chiellini** | Dirigente | Report settimanali per riunioni |
| **Giorgio Chiellini** | Investitore/Advisor | Overview mercato categoria |

## Current State (v2.0)

```
Status: MVP ONLINE (GitHub Actions running)
LOC: ~1,200
Costo: ~$5/mese

Funzionante:
  - Scraper automatico (ogni 6h via GitHub Actions)
  - Gemini File Search RAG integration
  - Agent conversazionale CLI
  - Telegram Bot basic
  - Dashboard PWA (GitHub Pages)
  - Notifiche Telegram (configurate)

Mancante per Lega Pro:
  - Scoring intelligente opportunita
  - Notifiche arricchite (valore TM, match score)
  - Filtri personalizzabili per utente
  - Integrazione Transfermarkt
  - Report PDF settimanale
  - Tracking storico giocatori
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                 GITHUB ACTIONS (ogni 6h)                │
│  • Trigger: cron + workflow_dispatch                    │
│  • Jobs: scrape → ingest → notify → dashboard           │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                      SCRAPER                            │
│  • Serper API → news mercato Serie C/D                  │
│  • Parsing strutturato → MarketOpportunity              │
│  • Deduplication by URL                                 │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                 GEMINI FILE SEARCH                      │
│  • Auto-chunking documenti                              │
│  • Embedding semantici                                  │
│  • Storage persistente RAG                              │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                      AGENT                              │
│  • Query linguaggio naturale                            │
│  • Retrieval semantico dal knowledge base               │
│  • Risposte con citazioni                               │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   INTERFACES                            │
│  • CLI interattiva                                      │
│  • Telegram Bot                                         │
│  • Dashboard PWA (GitHub Pages)                         │
└─────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Cost |
|-------|------------|------|
| Scraping | Serper.dev API | $0-5/mo (2500 free) |
| RAG | Gemini File Search | $0 storage + $0.50 indexing |
| LLM | Gemini 2.5 Flash | ~$1-3/mo queries |
| Automation | GitHub Actions | Free (2000 min/mo) |
| Hosting | GitHub Pages | Free |
| Notifications | Telegram Bot API | Free |

**Total: ~$5/mese** vs $50-100+ per RAG tradizionale

## Key Files

| File | Purpose | LOC |
|------|---------|-----|
| `src/scraper.py` | News collection + parsing | ~350 |
| `src/models.py` | Data structures | ~230 |
| `src/agent.py` | Conversational AI | ~250 |
| `src/ingest.py` | Upload to Gemini | ~150 |
| `src/notifier.py` | Telegram notifications | ~100 |
| `bot/telegram_bot.py` | Mobile interface | ~200 |

## Development Workflow

1. **Spec-driven**: Ogni feature ha spec in `.dev/`
2. **Test su GitHub Actions**: Push → verifica workflow
3. **Iterate**: feedback → miglioramenti

## Links

- **Repo**: https://github.com/mtornani/ob1-serie-c
- **Dashboard**: https://mtornani.github.io/ob1-serie-c/
- **Telegram Bot**: @Ob1LegaPro_bot

---

**Last Updated**: 2026-01-30
**Maintainer**: Mirko Tornani
