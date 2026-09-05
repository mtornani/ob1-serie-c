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
- `data/` — opportunities.json (database principale), backtest
- `config/` — YAML configs
- `workers/` — Cloudflare Workers (Telegram bot — l'unico bot attivo)

### File chiave
- `data/opportunities.json` — Database opportunità (100 entries)
- `docs/data.json` — Dashboard data (generato da generate_dashboard.py)
- `src/scoring.py` — OB1Scorer con pesi SCORE-002
- `scripts/generate_scouting_reports.py` — Genera report HTML individuali
- `scripts/enrich_scrapling.py` — Enrichment via Scrapling + Gemini
- `scripts/generate_dashboard.py` — Scoring + export dashboard

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
- Git post-merge: dopo ogni PR merge → `git fetch origin main && git rebase origin/main && git push --force-with-lease origin <branch>`. Mantiene il branch sincronizzato con main e silenzia lo stop-hook GPG (il range origin/branch..HEAD diventa vuoto).

## Sicurezza
- Report scouting in `reports/` (NON in `docs/` — non devono essere pubblici)
- `.env` è in .gitignore
- `.claude/settings.local.json` NON deve contenere API keys reali
- La repo è pubblica su GitHub — attenzione a cosa si committa

## GitHub Secrets (Settings → Secrets → Actions)

### Pipeline (ingest.yml)
| Secret | Descrizione |
|--------|-------------|
| `GEMINI_API_KEY` | Google AI Studio |
| `TAVILY_API_KEY` | Tavily search API |
| `SERPER_API_KEY` | Serper.dev API |
| `TELEGRAM_BOT_TOKEN` | Token del bot @Ob1LegaPro_bot |
| `TELEGRAM_CHAT_ID` | Chat ID broadcast principale (es. 1465485090) |
| `TELEGRAM_OFFICE_CHAT_ID` | Chat ID admin alert (privato) |

### Cloudflare Pages (deploy-cf-pages.yml)
| Secret | Come ottenerlo |
|--------|----------------|
| `CLOUDFLARE_API_TOKEN` | CF Dashboard → My Profile → API Tokens → Create Token → "Edit Cloudflare Pages" template |
| `CLOUDFLARE_ACCOUNT_ID` | CF Dashboard → qualsiasi sito → barra destra → Account ID |

## Cloudflare Setup (passi manuali da dashboard)

### 1. Cloudflare Pages — primo deploy
Il workflow `deploy-cf-pages.yml` crea automaticamente il progetto `ob1-lega-pro`
al primo run. Dopo il deploy sarà accessibile a:
`https://ob1-lega-pro.pages.dev`

### 2. Custom Domain
CF Dashboard → Pages → ob1-lega-pro → Custom domains → Add custom domain
- Esempio: `scout.ob1.io` o `ob1.ksport.it`
- Aggiungere il record CNAME nel DNS: `scout CNAME ob1-lega-pro.pages.dev`

### 3. Zero Trust Access (login obbligatorio)
CF Dashboard → Zero Trust → Access → Applications → Add an application → Self-hosted

Compilare:
- **Application name**: OB1 Lega Pro Scout
- **Application domain**: `scout.ob1.io` (il custom domain)
- **Session duration**: 24h

Policy (Add a policy):
- **Policy name**: Authorized Users
- **Action**: Allow
- **Include**: Email → `mirkotornani@gmail.com`
- Aggiungere altri indirizzi per K-Sport

**Authentication**: One-time PIN (email OTP) — zero setup aggiuntivo

### Architettura finale
```
GitHub repo (public)
  ↓ push to main
  ├─ pages.yml       → GitHub Pages (pubblico, fallback)
  └─ deploy-cf-pages.yml → Cloudflare Pages (protetto con Zero Trust)
                              ↑
                         custom domain
                         + login email OTP
```

## Contesto business
- I report sono destinati a osservatori professionisti (es. Daniele Corazza, Ascoli)
- Devono contenere SOLO dati verificabili (Transfermarkt, FBRef, Lega Pro)
- Zero errori = test di credibilità. Niente gergo tecnico, solo linguaggio calcistico
- Focus: Under 23, mix di ruoli, Serie C italiana

## Changelog

### 2026-09-05 — ARCH-003: la catena Eccellenza rimessa in piedi (fonte morta, parser che mentiva)

- **Il canale Telegram del comitato E-R non esiste piu'.** `telegram_census.py`
  rilanciato dal vivo: `@lndemiliaromagna` da `attivo` (839 iscritti, 7/8/2026) a
  `inesistente`. Era l'unica via d'accesso ai CU: la Fase 3 con una fonte sola
  non era una catena, era un filo
- **`src/cu_site.py`** — fonte sostitutiva: l'elenco pubblico del sito del
  comitato (`figccrer.it/comunicati?page=N`), che pubblica per obbligo federale
  e non per scelta di chi amministra un canale. Il WAF risponde HTTP **200** con
  un interstiziale: si riconosce, si ritenta, e se non passa si solleva
  `ListingUnavailable` — "non ho potuto guardare" non e' "non c'era niente"
  (lezione @lndlombardia, gia' pagata una volta). Stesso ritentativo in
  `read_pdf`: senza, si perdeva un comunicato su due
- `brief_giovedi.py` ora legge **due fonti** (sito + canale, se vivo) e marca
  il CU come visto **solo dopo l'ingest riuscito**: `SeenStore.is_new_url()` e'
  in sola lettura. Prima un download fallito marcava comunque, e quel CU non
  veniva piu' ritentato — un buco permanente nella serie storica
- **Dove gioca il Rimini, da atti ufficiali**: LND CU 75 del 5/8/2026 richiama
  il CU FIGC 104/A del 28/11/2025, *revoca dell'affiliazione a Rimini Football
  Club s.r.l.*; il calendario CRER da' **`RIMINI CALCIO SSD ARL` in Eccellenza
  E-R girone B**. Il nome esatto conta: e' quello che va in `OB1_CLUB`
- **Il parser mentiva, e si e' visto solo lanciandolo sui CU veri.** Primo giro:
  7 sanzioni, **6 inventate** (`CESENA (FC)`, `S.R.L. (U21)`, motivazioni da
  3.000 caratteri di regolamento) e **1 vera mancante** — un dirigente inibito,
  cioe' l'errore che manda in panchina uno squalificato. Quattro correzioni:
  quantita' obbligatoria in `SQUALIFICA PER <n> GARE`, data completa in
  `GARE DEL`, reset del blocco all'intestazione del campionato successivo,
  e `SQUALIFICA A GARE: FINO AL` riconosciuta. Ora l'estratto corrisponde
  esattamente al documento: CU 24 → 2 sanzioni, 16 risultati; CU 25 → 0 e 0
- `CUStore.clubs()` unisce sanzioni **e risultati**: a una squadra che ha giocato
  senza prendere provvedimenti il brief rispondeva "non corrisponde a nessuna
  societa'" (errore di configurazione) invece di "nessuno squalificato". Era
  esattamente il caso del Rimini alla 1ª giornata
- Primo giro pulito: 25 CU ingeriti, fra i risultati
  `INTER SM SAMMAURESE 0-2 RIMINI CALCIO SSD ARL`. Brief provato end-to-end sul
  Pietracuta (che una sanzione ce l'ha): messaggio completo, con la fonte citata
- **`comunicati.lnd.it`** censito e scartato per l'Eccellenza: JSON paginato e
  `robots.txt` permissivo, ma i department sono solo nazionali (LND, Serie D,
  femminile). E' la fonte pulita per la **Serie D**, non per i comitati regionali
- 389 test offline (erano 380), nuovo `tests/test_cu_site.py`. Zero rete nei test
- **Da fare a mano su GitHub** (Settings → Secrets and variables → Actions →
  Variables): `OB1_CLUB = RIMINI CALCIO SSD ARL`. Facoltative: `OB1_AVVERSARIO`,
  `OB1_CU_SITE`, `OB1_CU_PAGES`. Senza `OB1_CLUB` il workflow ingerisce e non
  manda niente

### 2026-08-03 — ARCH-002 Fasi 1-2: la metrica, poi il 304
- **Fase 1 — `src/metrics.py`**: `costo_per_fatto = (ricerche + chiamate_llm +
  fetch) / campi_nuovi_verificati`. Contatori alimentati dove i costi nascono
  (gateway, free_stack, enricher) e una riga per run in `data/metrics.jsonl` —
  scritta *sempre*, anche quando non c'è stato lavoro: un buco nella serie
  storica non si ricostruisce. Zero fatti ⇒ costo **indefinito**, non infinito
- `scripts/sanity_check.py`: nuovo blocco efficienza. Se il costo per fatto
  supera 1,5× la mediana delle run precedenti è un **warning**, non un errore —
  la pipeline ha prodotto dati validi, sta solo pagando di più per ottenerli
- **Fase 2 — ETag/304**: `enricher_tm.fetch_page()` manda `If-None-Match` /
  `If-Modified-Since` (validatori in `data/tm_etags.json`). Un 304 salta parse,
  LLM **e** il fallback grounded: contenuto invariato non è "profilo non
  trovato", e chiamare il percorso a consumo lì sarebbe pagare per gli stessi dati
- **Fase 2 — `src/watch/seen.py`**: memoria "cosa ho già visto" su SQLite
  (`data/ob1.db`, gitignorato, via artifact). Chiave = `sha256(url +
  contenuto_normalizzato)`: un articolo ripubblicato identico, o con `?utm_source=`
  diverso, non è un evento. Prune a 60 giorni
- Interruttori (vincolo ARCH-002 §7): `OB1_METRICS=0`, `OB1_ETAG=0`, `OB1_WATCH=0`
  riportano al comportamento precedente senza rollback di codice
- 121 test offline (erano 74): `tests/test_metrics.py`, `tests/test_watch.py`,
  più il 304 in `tests/test_enricher.py`. I criteri di uscita delle due fasi sono
  test, non promesse: la seconda run consecutiva fa ≥80% di 304 e 0 chiamate LLM
- **Ancora da fare**: Fase 3 (poller RSS/sitemap + coda)

### 2026-08-03 — ARCH-002 corollario zero: gate entità (la spazzatura costa per sempre)
- `src/entity_gate.py`: una sola fonte di verità al posto di tre liste divergenti
  (`ouroboros_run`, `run_enrichment`, `quality_gate`). Regole **su token**, non su
  sottostringa: cadono "La Serie" e "Summer Transfer Big Board", restano "La Gumina",
  "Da Riva", "Della Morte" — cognomi veri che una blacklist per sottostringa uccide
- Tre verdetti: `player` / `junk` (non è una persona → si rimuove) / `out_of_scope`
  (giocatore vero ma 35 mln € non è un'opportunità di Serie C → si marca, non si
  butta: è una decisione di chi gestisce il radar, non del filtro)
- Agganciato dove si spende: `ouroboros_run.is_valid_player_name`,
  `run_enrichment._is_enrichable`, e la dashboard non pubblica più i fuori fascia
  (Camara Mohamed, 9 mln €, era nella top 5 pubblica)
- `scripts/purge_junk.py`: report di default, `--apply` per scrivere, snapshot prima
- DB ripulito: 739 → 723 entry, 16 rimosse ("Comunicato Ufficiale", "Beach Soccer",
  "Saudi Pro League", "Frieren Wiki" — 4 già arricchite), 8 marcate fuori fascia.
  ~416 operazioni/anno risparmiate
- Fix di un bug latente trovato applicando la purga: `run_enrichment` scriveva la
  lista grezza su `docs/data.json`, che ha il formato dashboard. In CI era mascherato
  perché `generate_dashboard.py` gira subito dopo, ma l'enrichment da solo lasciava
  la dashboard pubblica corrotta

### 2026-08-02 — ARCH-001: LLM gateway multi-provider (Fase 1)
- Spec architettura produzione: `.dev/ARCH-001_production_llm.md` (modello di costo,
  matrice provider free-tier, piano migrazione in 4 fasi)
- Nuovo layer `src/llm/`: registry (YAML→rotte), ledger quote persistito
  (`data/llm_ledger.json`), cache risposte (`data/llm_cache/`, gitignorata), gateway
  con failover automatico. Un solo protocollo: OpenAI-compatible /chat/completions
- `config/llm_providers.yaml`: Cerebras, Groq, Mistral, OpenRouter, NVIDIA NIM, Gemini
  (ora ultima rotta, priorità 80). Task class: triage / extract / reason
- `src/llm_fallback.py` è ora uno shim sul gateway; `OB1_LLM_GATEWAY=0` torna al legacy
- Kill switch costi: `OB1_LLM_ALLOW_PAID=0` di default → nessuna chiamata fatturabile
- 30 test offline (`tests/test_llm_gateway.py`) + workflow `tests.yml`
- **Ancora da fare (Fase 4)**: multi-lega (matrix/Workers) + consenso 2 modelli

### 2026-08-03 — ARCH-002: spec quantizzazione (lavoro a evento, non a orologio)
- `.dev/ARCH-002_quantization.md`: principio del "quanto minimo", 4 corollari,
  metrica costo-per-fatto-nuovo, piano in 5 fasi con percorsi repo
- Diagnosi: enrichment è già O(giocatori nuovi) grazie alla cache URL TM, ma
  discovery è O(leghe × query × run) e il refresh è a timer → ~86k operazioni/mese
  a 30 leghe, quasi tutte su contenuto identico al giorno prima
- Verificato dal vivo: tuttoc/tuttolegapro/lacasadic hanno `/rss`, tuttomercatoweb
  ha sitemap, sportitalia ha `/rss`. 5 fonti su 6 pollabili a costo zero
- Da sviluppare: `src/watch/` (poller, seen-store, coda), `config/sources.yaml`,
  `src/metrics.py`, ETag/304 nel fetch TM
- **Non implementata**: è una spec

### 2026-08-02 — ARCH-001 Fasi 2-3: free search + free LLM (grounding fuori)
- `src/free_stack.py`: catena ricerca senza chiavi obbligatorie
  (cache 7g → DuckDuckGo → SearXNG → Tavily* → Serper*) e `llm_complete_json` /
  `has_any_llm` sopra il gateway. `OB1_SEARCH_MODE=serper` torna al legacy
- `OB1_LLM_MODE`: `free_first` (default) | `free_only` | `gemini_first`
- Enricher: **non solleva più** senza GEMINI_API_KEY/SERPER_API_KEY — l'unico
  requisito è `has_any_llm()`. La sola `GROQ_API_KEY` basta per arricchire
- `enrich_player_free`: URL TM cachato (`data/tm_urls.json`, la ricerca si paga
  una volta per giocatore) → fetch → `parse_tm_text` regex → LLM solo sul residuo.
  Deterministic-first: il regex non viene mai sovrascritto dall'LLM
- Discovery: `GlobalScraper.discover_players` free-first; grounding Gemini solo con
  `OB1_LLM_MODE=gemini_first`. Su vuoto ricade sul percorso Tavily preesistente
- `run_enrichment.py`: lo stop non è più `gemini_disabled` ma `enricher.stalled`
  (altrimenti il percorso free si fermava subito). Campo `enrichment_source` persistito
- Registry: `base_url_env`/`name_env`/`requires_key` → supporto COMPARE_BASE_URL
  (endpoint OpenAI-compatible locale) e GEMINI_MODEL configurabile
- 62 test offline (gateway + free_stack + enricher), zero rete

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
