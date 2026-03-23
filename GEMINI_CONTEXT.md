# OB1 Serie C Dev — Documentazione Completa per Gemini

## Panoramica Progetto

**OB1 Scout Serie C** e un sistema automatizzato di scouting calcistico per la Serie C e Serie D italiana. Un agente intelligente che monitora il mercato 24/7, scopre opportunita (svincolati, rescissioni, prestiti), arricchisce i profili giocatore con dati Transfermarkt, calcola punteggi di opportunita e distribuisce insight tramite dashboard PWA e bot Telegram.

**Obiettivo**: Aiutare scout e direttori sportivi a individuare le migliori opportunita di mercato in modo automatico, con costo operativo ~$0-5/mese.

**Versione corrente**: v3.4

---

## Tech Stack Completo

| Livello | Tecnologia |
|---------|-----------|
| Backend/Scraper | Python 3.11-3.12 (locale) / 3.11 (GitHub Actions) |
| Telegram Bot | TypeScript + Cloudflare Workers |
| AI/LLM | Gemini 2.5-Flash (Google), Gemma 3 27B (OpenRouter via Cloudflare) |
| Web Search | Serper.dev + Tavily APIs |
| Enrichment dati | Transfermarkt (via Tavily scraping + Gemini parsing) |
| Knowledge Base | Google Gemini File Search (RAG) |
| Dashboard | HTML/CSS/JS Vanilla + GitHub Pages (PWA) |
| Report | Python (matplotlib, reportlab per PDF) |
| CI/CD | GitHub Actions (4 workflow) |
| KV Storage | Cloudflare Workers KV (per profili watch utente) |
| DNA Matching | Matching semantico AI (Gemini-based) |
| Web Framework | Cloudflare Workers (serverless) |

---

## Dipendenze

### Python (requirements.txt)

```
requests>=2.31.0
python-dotenv>=1.0.0
google-genai>=0.3.0
tavily-python>=0.3.0
python-telegram-bot>=21.0
fpdf2>=2.8.0
pyyaml>=6.0
```

### TypeScript (workers/telegram-bot/package.json)

```json
{
  "devDependencies": {
    "@cloudflare/workers-types": "^4.20240117.0",
    "typescript": "^5.3.3",
    "wrangler": "^3.25.0"
  }
}
```

### API Esterne

- Google Gemini 2.5-Flash (LLM + File Search)
- Serper.dev (Web search, 2500 free/mese)
- Tavily (Scraping avanzato)
- OpenRouter (Gemma 3 27B per voice/search)
- Telegram Bot API
- Transfermarkt (enrichment via scraping)

---

## Struttura Progetto

```
ob1-serie-c-dev/
├── src/                              # Backend Python (13 file core)
│   ├── scraper.py                    # Raccolta notizie (Serper API)
│   ├── scraper_tavily.py             # Raccolta notizie (Tavily API)
│   ├── scraper_global.py             # Scraper multi-lega
│   ├── date_filter.py                # Estrazione e filtro date articoli
│   ├── enricher_tm.py                # Arricchimento Transfermarkt
│   ├── scoring.py                    # OB1 Score (singola lega)
│   ├── scoring_global.py             # OB1 Score (multi-lega)
│   ├── history.py                    # Tracking evoluzione opportunita
│   ├── reporter.py                   # Generazione PDF
│   ├── agent.py                      # Interfaccia RAG conversazionale
│   ├── ingest.py                     # Uploader Gemini File Search
│   ├── notifier.py                   # Notifiche Telegram
│   ├── models.py                     # Strutture dati
│   └── dna/                          # Sistema DNA 2.0 Matching
│       ├── engine_global.py          # Matcher semantico AI (Gemini)
│       ├── matcher.py                # Matching locale giocatore-club
│       ├── scorer.py                 # Calcolo DNA score
│       └── models.py                 # DataClasses (PlayerDNA, ClubDNA, MatchResult)
│
├── scripts/                          # Pipeline eseguibili (16 script)
│   ├── ouroboros_run.py              # Pipeline globale (scrape + score + DNA + ingest)
│   ├── run_ingest.py                 # Trigger ingest legacy
│   ├── run_enrichment.py             # Pipeline enrichment
│   ├── run_cleanup.py                # Pulizia dati
│   ├── generate_dashboard.py         # Aggiorna data.json con filtri
│   ├── generate_report.py            # Report HTML narrativo
│   ├── generate_weekly_report.py     # Digest settimanale HTML
│   ├── generate_ds_report.py         # Report PDF DS-Ready
│   ├── generate_matches.py           # Lista match DNA
│   ├── generate_social_post.py       # Contenuto social media
│   ├── send_notification.py          # Push Telegram
│   ├── send_public_report.py         # Pubblicazione canale pubblico
│   ├── enrich_all_players.py         # Enrichment massivo
│   ├── force_re_enrich.py            # Re-run enrichment
│   ├── scrape_squadre_b.py           # Scraper squadre giovanili
│   └── quick_ingest.py               # Aggiornamento rapido KB
│
├── workers/telegram-bot/             # TypeScript Cloudflare Worker
│   ├── src/
│   │   ├── index.ts                  # Entry worker (webhook + cron)
│   │   ├── handlers.ts               # Gestori messaggi/comandi (35KB)
│   │   ├── types.ts                  # Definizioni tipi
│   │   ├── telegram.ts               # Wrapper Telegram API
│   │   ├── data.ts                   # Caricamento dati (JSON da GitHub Pages)
│   │   ├── smart-search.ts           # Ricerca LLM-powered (OpenRouter)
│   │   ├── scout-wizard.ts           # Guida interattiva stile Akinator
│   │   ├── talent-search.ts          # Filtro talenti U23
│   │   ├── dna.ts                    # Integrazione DNA matching
│   │   ├── dna-adapter.ts            # Adapter DNA per bot
│   │   ├── conversational.ts         # Gestione messaggi vocali
│   │   ├── response-generator.ts     # Risposte con persona AI
│   │   ├── nlp.ts                    # Natural language parsing
│   │   ├── llm-classifier.ts         # Classificatore LLM fallback
│   │   ├── openrouter.ts             # Client API OpenRouter
│   │   ├── formatters.ts             # Formattazione output
│   │   ├── watch/                    # Sistema profili watch
│   │   └── notifications/            # Sistema digest + alert
│   ├── package.json
│   └── wrangler.toml                 # Config Cloudflare (webhook, KV, cron)
│
├── config/                           # Configurazione YAML
│   ├── sources.yaml                  # Query scraping + regole validazione
│   ├── clubs.yaml                    # Database club Serie C (60+ club)
│   ├── leagues.yaml                  # Config multi-lega (IT, BR, AR)
│   ├── dna_manifestos.yaml           # Archetipi strategia club
│   └── prompts.yaml                  # Template prompt LLM
│
├── data/                             # Dati runtime
│   ├── opportunities.json            # DB master (~100 entry)
│   ├── stats.json                    # Statistiche aggregate
│   ├── dna_matches.json              # Risultati DNA match
│   ├── history_log.json              # Evoluzione opportunita
│   ├── sent_history.json             # Tracking notifiche
│   ├── clubs/                        # Profili DNA club (20 JSON)
│   ├── players/squadre_b.json        # Talenti Primavera/Next Gen
│   ├── snapshots/                    # Backup storici (9+ snapshot)
│   └── social/                       # Post social generati
│
├── docs/                             # GitHub Pages (output pubblico)
│   ├── index.html                    # Dashboard PWA principale
│   ├── data.json                     # Feed dati live (auto-aggiornato)
│   ├── dna_matches.json              # Feed risultati DNA
│   ├── report.html                   # Report narrativo ultimo
│   ├── manifest.json                 # Manifest PWA
│   ├── sw.js                         # Service worker
│   ├── js/app.js                     # Logica dashboard
│   ├── js/dna-engine.js              # Engine UI DNA
│   ├── css/style.css                 # Styling responsive
│   └── reports/                      # Report settimanali (datati)
│
├── .github/workflows/                # CI/CD (4 workflow)
│   ├── ingest.yml                    # Ogni 6h: scrape->enrich->dashboard->report->notify
│   ├── weekly-report.yml             # Lunedi 08:00 UTC: digest + PDF + social
│   ├── cleanup.yml                   # Pulizia dati settimanale
│   └── pages.yml                     # Deploy GitHub Pages
│
├── .env.example                      # Template variabili ambiente
├── requirements.txt                  # Dipendenze Python
├── AGENTS.md                         # Istruzioni AI assistant
└── README.md                         # Documentazione principale
```

---

## Modelli Dati

### MarketOpportunity (Entita Primaria)

```python
@dataclass
class MarketOpportunity:
    league_id: str              # "it_serie_c", "br_serie_a", etc.
    opportunity_type: OpportunityType  # SVINCOLATO, RESCISSIONE, PRESTITO, etc.
    player_name: str
    description: str
    relevance_score: int        # 0-5 (pre-scoring)
    source_url: str
    source_name: str
    reported_date: str          # "YYYY-MM-DD"
    dna_matches: Dict[str, Dict]  # Punteggi fit strategico
```

### Campi in data.json (Post-scoring)

```json
{
  "id": "opp_hash",
  "player_name": "String",
  "age": "Integer | null",
  "role": "AT|CC|DC|etc",
  "opportunity_type": "svincolato|rescissione|prestito|mercato",
  "current_club": "String",
  "nationality": "String",
  "ob1_score": "0-100",
  "classification": "hot|warm|cold",
  "score_breakdown": {
    "freshness": "0-100",
    "opportunity_type": "0-100",
    "experience": "0-100",
    "age": "0-100",
    "market_value": "0-100",
    "league_fit": "0-100",
    "source": "0-100",
    "completeness": "0-100"
  },
  "discovery_date": "ISO timestamp",
  "dna_strategic_fit": {
    "archetype_id": {"score": "0-100", "verdict": "string"}
  }
}
```

### PlayerDNA (Per matching)

```python
@dataclass
class PlayerDNA:
    id: str
    name: str
    birth_year: int
    nationality: str
    primary_position: str       # "CC", "AT", "DC", etc.
    current_team: str
    appearances: int
    minutes_played: int
    skills: PlayerSkills        # 8 attributi tecnici (0-100)
    transfermarkt_url: str
```

### ClubDNA (Per matching)

```python
@dataclass
class ClubDNA:
    id: str
    name: str
    primary_formation: str      # "4-3-3"
    playing_styles: List[str]   # ["pressing_alto", "possesso"]
    needs: List[ClubNeed]       # Requisiti posizione + tipo giocatore
    budget_type: str            # "solo_prestiti", "acquisti"
```

### OpportunityType Enum

- `SVINCOLATO` — Parametro zero
- `RESCISSIONE` — Risoluzione contrattuale
- `PRESTITO` — Disponibile in prestito
- `INFORTUNIO` — Infortunio/recupero
- `TALENT` — Prospetto (U23)
- `PERFORMANCE` — Prestazione recente di rilievo
- `TRANSFER_RUMOR` — Voce di mercato

---

## Algoritmi Chiave

### OB1 Score (scoring.py)

Sistema di scoring a 8 fattori pesati:

| Fattore | Peso | Descrizione |
|---------|------|-------------|
| Freshness | 20% | Quanto e recente la notizia |
| Opportunity Type | 20% | Svincolato > Prestito > Rumor |
| Experience | 20% | Club precedenti in Serie C |
| Age Profile | 20% | Range ideale 22-28 |
| Market Value | 15% | Attrattivita economica |
| League Fit | 15% | Storico in leghe rilevanti |
| Source Quality | 5% | Affidabilita giornalistica |
| Completeness | 5% | Ricchezza dati |

**Classificazione**:
- **HOT** (80+): Opportunita top
- **WARM** (60-79): Buoni match
- **COLD** (<60): Casi marginali

Nota: La ricalibrazione SCORE-002 ha aggiustato i pesi per ottenere ~15% hot, ~50% warm.

### DNA 2.0 Matching (engine_global.py)

- Usa API Gemini per valutare fit strategico giocatore-club
- Confronta profilo giocatore con "manifesti" club (stile di gioco, esigenze, budget)
- Restituisce punteggio match semantico (0-100) + verdetto scouting
- Throttling anti-429: 3 secondi di delay tra chiamate API

### NLP Bot (nlp.ts)

1. Prova parser locale prima (gratuito, veloce) per query strutturate
2. Fallback a LLM (OpenRouter Gemma 3 27B) per query complesse
3. Classifica intent: search, filter, alert, report, etc.

### Watch Profile System (Cloudflare KV)

- Utenti creano alert per giocatori/posizioni specifiche
- Salvati in KV namespace, persistenti tra richieste
- Controllati al cron giornaliero per nuovi match

---

## Comandi Telegram Bot

| Comando | Funzione |
|---------|----------|
| `/start` | Messaggio benvenuto |
| `/help` | Guida completa |
| `/report` | Report mercato istantaneo |
| `/hot` | Score 80+ (top opportunita) |
| `/warm` | Score 60-79 (buoni match) |
| `/all` | Lista completa |
| `/search <nome>` | Cerca giocatore specifico |
| `/watch` / `/watch add` | Crea/gestisci alert |
| `/digest` | Preview digest giornaliero |
| `/talenti` | Top talenti U23 |
| `/dna <club>` | DNA match per club |
| `/scout` | Wizard interattivo stile Akinator |
| `/stats` | Aggregati mercato |
| `/stale` | Svincolati da 30+ giorni |
| Testo libero | Query in linguaggio naturale (NLP) |
| Messaggio vocale | Trascrizione + ricerca |

---

## Endpoint e Feed Dati

### Telegram Bot (Cloudflare Worker)

- `POST /webhook` — Riceve aggiornamenti Telegram
- `GET /` — Health check
- `GET /webhook-info` — Stato webhook
- `GET /setup?url=<url>` — Setup webhook una tantum
- `GET /setup-commands` — Registra menu comandi bot
- `GET /trigger-cron` — Trigger manuale digest
- **Cron**: `0 7 * * *` — Digest giornaliero ore 07:00 UTC

### Feed Dati (GitHub Pages)

- `https://mtornani.github.io/ob1-serie-c/data.json` — Opportunita live (aggiornate ogni 6h)
- `https://mtornani.github.io/ob1-serie-c/dna_matches.json` — Risultati match
- `https://mtornani.github.io/ob1-serie-c/report.html` — Narrativo HTML

---

## Variabili d'Ambiente

```bash
# Obbligatorie
GEMINI_API_KEY=...              # Google Gemini API
SERPER_API_KEY=...              # Web search (2500 free/mese)
TAVILY_API_KEY=...              # Scraping avanzato

# Opzionali
TELEGRAM_BOT_TOKEN=...          # Token bot
TELEGRAM_CHAT_IDS=123,456       # Destinatari notifiche
ALLOWED_TELEGRAM_USERS=123      # Whitelist
OPENROUTER_API_KEY=...          # LLM per voice/search
```

---

## Configurazione YAML

### sources.yaml — Query scraping

```yaml
queries:
  svincolato:
    - '"Serie C" "parametro zero" giocatore 2025'
    - '"Serie C" "svincolato" calciatore'
  prestito:
    - '"Serie C" "prestito" disponibile'
    - 'Juventus OR Milan "prestito Serie C"'
validation:
  skip_keywords: [allenatore, mister, presidente]
  player_keywords: [giocatore, calciatore, centrocampista]
  league_keywords: [serie c, lega pro]
```

### clubs.yaml — Registro club Serie C (60+ entry)

### leagues.yaml — Config multi-lega (IT, BR, AR)

### dna_manifestos.yaml — Archetipi strategia club

### wrangler.toml — Config Cloudflare Worker

```toml
[env.production]
DATA_URL = "https://mtornani.github.io/ob1-serie-c/data.json"
DASHBOARD_URL = "https://mtornani.github.io/ob1-serie-c/"
[triggers]
crons = ["0 7 * * *"]
[[kv_namespaces]]
binding = "USER_DATA"
```

---

## Installazione e Esecuzione

### Setup Locale

```bash
git clone <repo>
cd ob1-serie-c-dev
pip install -r requirements.txt
cp .env.example .env
# Edita .env con le tue API key

# Test scraper
PYTHONIOENCODING=utf-8 python src/scraper.py

# Pipeline completa
python scripts/ouroboros_run.py
```

### Deploy Cloud (GitHub Actions)

1. Push repo su GitHub
2. Aggiungi secrets: `SERPER_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`
3. Abilita GitHub Pages (source: GitHub Actions)
4. Abilita deploy Cloudflare Workers
5. Il workflow gira automaticamente ogni 6 ore

### Deploy Telegram Bot (Cloudflare Workers)

```bash
cd workers/telegram-bot
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put OPENROUTER_API_KEY
wrangler deploy
# Poi: https://worker-url.com/setup?url=https://your-worker/webhook
```

---

## CI/CD — GitHub Actions

| Workflow | Trigger | Azioni |
|----------|---------|--------|
| `ingest.yml` | Ogni 6h | Scrape -> Score -> Enrich -> Dashboard -> Report -> Notify |
| `weekly-report.yml` | Lunedi 08:00 UTC | Digest + PDF DS + Social posts |
| `cleanup.yml` | Settimanale | Pulizia dati |
| `pages.yml` | Push | Deploy GitHub Pages |

---

## Deployment Pubblico

- **Dashboard**: `https://mtornani.github.io/ob1-serie-c/`
- **Bot Telegram**: `@Ob1LegaPro_bot`
- **Webhook**: Cloudflare Workers (serverless)

---

## Costi Operativi

| Servizio | Costo |
|----------|-------|
| Serper (search) | $0-5/mese (2500 free) |
| Gemini API | ~$1-3/mese |
| Tavily | $0 (free tier) |
| OpenRouter | $0 (free tier) |
| Cloudflare Workers | $0 (free tier) |
| GitHub Actions | $0 (2000 min free) |
| GitHub Pages | $0 |
| **TOTALE** | **~$5/mese** |

---

## Filtri Anti-Junk (v3.4)

- Filtro geografico (solo Italia per dashboard)
- Blacklist pagine generiche Transfermarkt
- Validazione nomi giocatore (esclude "classifica", "svincolati" come nomi)
- Estrazione date pubblicazione da URL per filtrare articoli stale (>60 giorni)

---

## Note Tecniche

- **Zero test coverage**: Nessun pytest/unit test attualmente
- **Multi-lega ready**: Pipeline supporta IT Serie C, BR Serie A, AR Primera Division
- **Wizard stateless**: Scout wizard usa callback_data (max 25 byte) per lo stato
- **Score recalibration**: SCORE-002 per bilanciare distribuzione hot/warm/cold
