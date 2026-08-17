# 🎯 OB1 Lega Pro

**Radar di opportunità di mercato per la Serie C italiana** — svincolati, prestiti, rescissioni, con verifica su Transfermarkt e lettura dei Comunicati Ufficiali di giustizia sportiva.

**Live:** [ob1legapro.matchanalysispro.online](https://ob1legapro.matchanalysispro.online)
**Bot Telegram:** [@Ob1LegaPro_bot](https://t.me/Ob1LegaPro_bot)

---

## Cosa fa

Non è uno scanner di notizie di calciomercato: è un radar che traccia **operazioni di mercato reali** per un direttore sportivo di Serie C, e le mette in regola con la giustizia sportiva prima di consegnarle.

1. **Scraping** (`scripts/ouroboros_run.py`) — Tavily/Serper su fonti di calciomercato, estrazione LLM (catena free-first: Groq → Cerebras → OpenRouter → NVIDIA, Gemini solo come fallback a pagamento)
2. **Enrichment** (`scripts/run_enrichment.py`) — verifica su Transfermarkt (profilo, presenze, valore di mercato); quando il profilo non arriva, il dato resta dichiaratamente incompleto, mai stimato
3. **Scoring** (`scripts/generate_dashboard.py`, SCORE-002) — 7 fattori pesati in codice, zero AI nel punteggio:

   | Fattore | Peso |
   |---|---|
   | Esperienza verificata (presenze) | 20% |
   | Profilo anagrafico (età target U23) | 18% |
   | Attualità della segnalazione | 15% |
   | Valore di mercato (fascia Serie C) | 15% |
   | Pertinenza Serie C | 15% |
   | Tipo di opportunità (svincolato > prestito > mercato) | 12% |
   | Affidabilità della fonte | 5% |

   Classificazione: **HOT** ≥ 70 · **WARM** ≥ 57 · **COLD** < 57
4. **Giustizia sportiva** (`src/cu_parser.py`, `src/brief.py`) — legge i Comunicati Ufficiali dei comitati regionali (regex, **zero LLM**), traccia squalificati/diffidati, e genera il brief del giovedì per il DS: chi è fermo, chi rischia, prima della partita
5. **Sanity check** (`scripts/sanity_check.py`) — verifica automatica di ogni run prima di pubblicare (file presenti, struttura dati, freschezza, costo per fatto nuovo)
6. **Delivery** — dashboard pubblica + notifiche broadcast su Telegram (`scripts/send_notification.py`) a una lista di iscritti reali

Costo per run: **zero AI a pagamento** in condizioni normali — la catena free-first copre estrazione ed enrichment; Gemini entra solo se esplicitamente configurato come fallback.

---

## Architettura

```
Scraping (Tavily/Serper + LLM free-first)
        ↓
Enrichment Transfermarkt (profilo, presenze, valore)
        ↓
Scoring SCORE-002 (7 fattori, in codice)
        ↓
Dashboard pubblica (docs/data.json → Cloudflare Pages)
        ↓
Sanity check → Notifica Telegram (broadcast abbonati)

Giustizia sportiva (in parallelo, indipendente):
Comunicati Ufficiali → parser regex → brief del giovedì (Telegram, al DS)
```

Pipeline automatica ogni 6h (`.github/workflows/ingest.yml`). Il brief del giovedì gira separatamente (`.github/workflows/brief-giovedi.yml`).

> Limite noto: l'enrichment Transfermarkt viene talvolta bloccato dagli IP datacenter dei runner GitHub Actions (risposta HTTP non-200 anti-bot) — quando succede, il circuito si spegne per la run e si torna alla ricerca web, in log senza falsi silenzi (vedi commenti in `src/enricher_tm.py`).

---

## Run locale

```bash
git clone https://github.com/mtornani/ob1-serie-c.git
cd ob1-serie-c
cp .env.example .env   # API keys: vedi sezione sotto
pip install -r requirements.txt

python scripts/ouroboros_run.py       # scraping
python scripts/run_enrichment.py      # enrichment Transfermarkt + LLM
python scripts/generate_dashboard.py  # scoring + export docs/data.json
python scripts/sanity_check.py        # verifica prima di pubblicare

# brief del giovedì (solo, senza il giro completo)
python scripts/brief_giovedi.py --club "NOME CLUB" --dry-run
```

### API keys (`.env`)

| Servizio | Obbligatoria | Note |
|---|:---:|---|
| `TAVILY_API_KEY` | ✅ | ricerca notizie di mercato |
| `SERPER_API_KEY` | ⬜ | ricerca alternativa |
| `GROQ_API_KEY` / `OPENROUTER_API_KEY` | ✅ (almeno una) | catena LLM free-first |
| `GEMINI_API_KEY` | ⬜ | fallback a pagamento, non necessario in condizioni normali |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID(S)` | ⬜ | notifiche broadcast |

---

## Struttura del repo

```
src/
  scraper_global.py    # scraping fonti di mercato
  enricher_tm.py        # enrichment Transfermarkt
  entity_gate.py         # filtro strutturale anti-junk
  scoring.py              # SCORE-002
  cu_parser.py             # parser Comunicati Ufficiali (giustizia sportiva)
  brief.py                  # formattazione brief del giovedì
  cu_feed.py                 # scoperta CU da canale Telegram del comitato
  notifier.py                 # invio Telegram
  free_stack.py, llm_fallback.py  # catena LLM free-first
scripts/
  ouroboros_run.py        # orchestratore scraping
  run_enrichment.py        # orchestratore enrichment
  generate_dashboard.py     # scoring + export dashboard
  sanity_check.py            # verifica pre-pubblicazione
  send_notification.py        # notifiche Telegram
  brief_giovedi.py             # CLI brief del giovedì
data/
  opportunities.json     # database principale
  cu_facts.json           # memoria versionata giustizia sportiva (il .db è gitignored)
docs/                    # dashboard pubblica (Cloudflare Pages)
workers/telegram-bot/    # bot Telegram (Cloudflare Worker, l'unico bot attivo)
.github/workflows/
  ingest.yml              # pipeline principale, ogni 6h
  brief-giovedi.yml         # brief del giovedì
  weekly-report.yml          # report settimanale
  verify-enrichment.yml       # controllo enrichment
  tests.yml                    # CI
```

---

## Limiti onesti

- **L'enrichment Transfermarkt è spesso bloccato in produzione.** I runner GitHub Actions vengono a volte respinti dal sistema anti-bot di TM (HTTP non-200 verso IP datacenter). Il circuito ora lo dice in log invece di restare muto, e da poco c'è un fallback via `sports-skills` (backend di terzi), ma la copertura su svincolati di Serie C/D oscuri non è garantita — verificata solo su un caso passato da un'academy di club grande.
- **`publishable` non richiede corroborazione.** Il gate è `identity_complete` da solo — la seconda fonte (o il profilo TM) è un bonus nello score, non un requisito, finché la pipeline non accumula abbastanza storia multi-fonte per renderlo un hard-gate senza svuotare la dashboard.
- **La giustizia sportiva copre un solo comitato regionale per ora** (Emilia-Romagna, `DEFAULT_CHANNEL`). Un DS fuori regione riceve correttamente "nessuna società nei CU" — non è un bug, ma la copertura reale è quella.
- **Nessun tabellone.** Non tracciamo se un'opportunità segnalata "HOT" è stata poi davvero chiamata, provata o firmata — il DS riceve il suggerimento, il sistema non chiude il cerchio con l'esito.
- **Il valore di mercato viene da una sola fonte** (Transfermarkt, diretto o via sports-skills) — nessun incrocio con una seconda valutazione quando quella prima è stale o sbagliata.

---

## Test

```bash
PYTHONIOENCODING=utf-8 python -m unittest discover tests -v
```
