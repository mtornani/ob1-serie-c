# ARCH-001 — Architettura di produzione: LLM a costo zero

**Stato**: Fasi 1-3 implementate (grounding fuori dal percorso caldo), Fase 4 da fare
**Data**: 2026-08-02
**Obiettivo**: portare OB1 da pipeline di sviluppo (single-tenant, free tier Gemini,
throughput 30 chiamate/giorno) a pipeline di produzione multi-lega, con costo di
inferenza LLM ≈ €0 e nessun single point of failure su un solo vendor.

---

## 1. Diagnosi: cosa costa davvero

L'architettura attuale usa **Gemini Search Grounding** come mattone unico per due
cose diverse:

| Uso | File | Cosa fa in una sola chiamata |
|-----|------|------------------------------|
| Discovery | `src/scraper_global.py:search_grounded` | cerca su Google + estrae nomi giocatori |
| Enrichment | `src/enricher_tm.py:enrich_players_batch` | cerca su Transfermarkt + estrae JSON profilo |

Il grounding è comodo perché fa **ricerca + fetch + estrazione** in un colpo solo.
È anche il motivo per cui non scala: si paga il bundle, non i token.

Prezzi di riferimento (verificati 2026-08-02, da riverificare ogni trimestre):

- Gemini 2.5: 1.500 prompt groundizzati/giorno gratis, poi **$35 / 1.000**
- Gemini 3.x: 5.000 prompt groundizzati/**mese** gratis, poi **$14 / 1.000**
- Un singolo prompt può generare **più query di ricerca, ognuna fatturata**
- Free tier Google: 5–15 RPM, 20–1.500 RPD a seconda del modello; i Pro sono
  fuori dal free tier da aprile 2026

Il secondo problema, oggi più urgente del primo: il free tier limita il **throughput**.
Con `GEMINI_DISCOVERY_BUDGET=4` e `MAX_ENRICH_BATCHES=4` la pipeline fa ~32 chiamate
groundizzate al giorno. Con 739 opportunità in `data/opportunities.json` e batch da 5,
lo smaltimento completo del backlog richiede giorni — e ogni run nuova ne aggiunge.
Non è un problema di prezzo: è un tetto strutturale che impedisce di aggiungere leghe.

### Modello di costo su tre scenari

Assunzioni: 4 run/giorno, `BATCH_SIZE=5`, refresh profilo ogni 14 giorni.

| | A — oggi (dev) | B — pilota K-Sport | C — scala |
|---|---|---|---|
| Leghe × query | 1 × 8 | 10 × 10 | 30 × 12 |
| Profili attivi | ~740 | ~5.000 | ~20.000 |
| Discovery groundizzata/giorno | 16 | 400 | 1.440 |
| Batch enrichment/giorno | 16 | 72 | 286 |
| **Prompt groundizzati/mese** | ~960 | ~14.200 | ~51.800 |
| Costo su Gemini 3.x (1 query/prompt) | $0 | ~$129 | ~$655 |
| Costo realistico (2–4 query/prompt) | $0 | **$260–520** | **$1.300–2.600** |
| Vincolo vero | throughput | throughput + costo | costo |

Lo scenario B è il pilota che è già in agenda. Lo scenario C è il modello di business
(vendere lo stesso radar su più campionati). In entrambi il costo del grounding è
superiore a tutto il resto dell'infrastruttura messo insieme — GitHub Actions e
Cloudflare Pages sono gratis a questi volumi.

---

## 2. Principio: separare ciò che Gemini fonde

Il grounding costa perché fonde tre operazioni con costi marginali molto diversi:

```
ricerca (SERP)     →  $0,30–1,00 / 1.000   (Serper), o gratis (Tavily 1.000/mese, RSS, sitemap)
fetch pagina       →  $0                    (HTTP dal runner CI)
estrazione JSON    →  $0                    (free tier LLM aggregati)
─────────────────────────────────────────────
grounding Gemini   →  $14–35 / 1.000 prompt, × numero di query interne
```

**L'intera architettura target discende da qui: scomporre il bundle e pagare ogni
pezzo al suo prezzo marginale reale, che per due pezzi su tre è zero.**

Le cinque leve, in ordine di impatto:

1. **Scomporre il grounding** (search / fetch / extract separati) — elimina la voce di costo
2. **Cache** — a 4 run/giorno lo stesso profilo viene ri-chiesto ~28 volte a settimana,
   ma la pagina TM cambia una volta a settimana. Hit rate atteso 60–80%
3. **Deterministic-first** — `parse_tm_text` (regex) già estrae la maggior parte dei
   campi. L'LLM va chiamato **solo sul residuo**, non come parser di default
4. **Routing multi-provider free-tier** — nessun singolo free tier basta; l'unione di
   6 free tier sì, con margine 7–10×
5. **Batching** — già fatto (5 giocatori/chiamata), da mantenere e tarare sul contesto

---

## 3. Architettura target

```
┌── L1 DISCOVERY ─────────────────────────────────────────────────┐
│  adapter di ricerca intercambiabili:                            │
│    Tavily (1.000 credits/mese free) · Serper ($1/1k)            │
│    RSS/sitemap delle trusted_sources (costo 0, latenza minima)  │
│  → coda URL, dedup per hash(url) + hash(contenuto)              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌── L2 FETCH ─────────────────────────────────────────────────────┐
│  HTTP + Scrapling per le pagine JS · rispetto robots/ratelimit  │
│  cache pagine su ETag/Last-Modified → il 90% dei refetch è 304  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌── L3 EXTRACT ───────────────────────────────────────────────────┐
│  3a. parser deterministici (regex TM, microdata, JSON-LD)  €0   │
│  3b. LLM GATEWAY  ← solo sui campi che 3a non ha risolto        │
│      routing free-tier · ledger quote · cache risposte          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌── L4 VERIFY ────────────────────────────────────────────────────┐
│  schema + range check (età 15–45, presenze ≤ 60/stagione, …)    │
│  consenso 2 modelli sui campi critici → confidence per campo    │
│  sotto soglia = campo NON pubblicato (regola "solo verificabile")│
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌── L5 SCORE & PUBLISH ───────────────────────────────────────────┐
│  SCORE-002 · dashboard · report scouting · Telegram (invariati) │
└─────────────────────────────────────────────────────────────────┘
```

L1+L2+L3 insieme fanno esattamente quello che faceva il grounding. La differenza è
che ogni strato è sostituibile, misurabile e — per L2 e L3 — gratuito.

---

## 4. Il layer LLM (implementato)

```
src/llm/
  registry.py   YAML → rotte ordinate per priorità; una rotta = (modello, chiave API)
  ledger.py     contatori RPM/RPD/TPM/TPD persistiti, cooldown, circuit breaker
  cache.py      cache risposte su disco, chiave = hash(task+prompt+system+versione)
  gateway.py    cache → routing → chiamata → failover → contabilità
config/llm_providers.yaml   registry provider, limiti free tier, licenze
data/llm_ledger.json        stato quote (committato dalla CI)
data/llm_cache/             cache risposte (gitignorata, sopravvive via artifact)
```

### 4.1 Un solo protocollo

Il gateway parla **esclusivamente** OpenAI-compatible `/chat/completions`. Groq,
Cerebras, Mistral, OpenRouter, NVIDIA NIM e **anche Gemini** (endpoint
`/v1beta/openai`) lo espongono. Aggiungere un provider = 6 righe di YAML, zero codice.
Gemini smette di essere un caso speciale e diventa una rotta come le altre — con
priorità 80, cioè penultima.

### 4.2 Task class, non "modello"

Il chiamante non sceglie il modello, sceglie il **tipo di lavoro**:

| Task | Serve | Volume | Rotte |
|------|-------|--------|-------|
| `triage` | è un giocatore? è spam? | altissimo | modelli piccoli, i più abbondanti |
| `extract` | testo → JSON profilo | alto | mid tier, prompt fino a 24k caratteri |
| `reason` | dedup semantico, sintesi report | basso | solo frontier (DeepSeek V3.2, Qwen3-235B) |

Questo è ciò che rende sostenibile il costo zero: i modelli frontier gratuiti hanno
free tier stretti (50–1.000 richieste/giorno), ma servono solo per il 5% delle chiamate.
Il 95% del volume gira su tier con budget a milioni di token/giorno.

### 4.3 Ledger: si controlla prima, non dopo il 429

La CI è stateless. Senza stato persistente ogni run riparte da zero, sbatte contro i
rate limit e brucia minuti di runner in backoff. Il ledger tiene per ogni bucket
(`provider:modello:indice_chiave`) i contatori RPM/RPD/TPM/TPD con rollover UTC
automatico, e il gateway **salta** le rotte esaurite invece di provarle.

Un 429 non è un errore da ritentare: è informazione. Il gateway distingue
"quota del minuto" da "quota del giorno" (dai marker nel body) e chiude il bucket
per il tempo giusto, poi passa alla rotta successiva. Un 401/403 spegne il bucket
per 24 ore — una chiave revocata non guarisce ritentando.

### 4.4 Sharding orizzontale del free tier

`api_key_env` accetta più chiavi separate da virgola: `GROQ_API_KEY=k1,k2,k3`.
Ogni chiave diventa un bucket indipendente con il proprio budget. È la via
lecita per scalare (account separati per ambiente/progetto); da usare nei limiti
dei ToS di ciascun provider, non per aggirarli.

### 4.5 Cache: la leva più grande

Chiave = `sha256(task | versione_prompt | tier | system | prompt)`. Il modello
**fisico** non entra nella chiave: se domani lo stesso prompt esce da Cerebras invece
che da Groq, la risposta in cache resta valida. Cambiare il prompt invalida
automaticamente le entry vecchie (basta bumpare `prompt_version`).

TTL per task class: 720h per `triage` (un nome o è un giocatore o non lo è),
336h per `extract` (i dati TM cambiano a fine mercato), 168h per `reason`.

---

## 5. Matrice provider (verificata 2026-08-02)

| Provider | Free tier | Modelli | Uso commerciale | Training sui dati |
|---|---|---|---|---|
| **Cerebras** | ~1M token/giorno, 30 RPM, no carta | Llama 3.3 70B, Qwen3-235B | sì | no |
| **Groq** | 1.000 RPD, 30 RPM, 100k TPD | Llama 3.3 70B | sì | no |
| **Mistral** | ~1B token/mese | Small/Large/Codestral | sì | **sì** (tier Experiment) |
| **OpenRouter** | 20 RPM, 50 RPD (1.000 dopo top-up $10 una tantum) | DeepSeek V3.2, Qwen3-235B, Llama free | sì | no |
| **NVIDIA NIM** | ~1.000 richieste/giorno | DeepSeek V3.1, Nemotron | sì | no |
| **Google AI Studio** | 5–15 RPM, fino a 1.500 RPD | Gemini 2.5 Flash / Flash-Lite | sì | **sì** fuori UE/UK/EEA |
| **Cloudflare Workers AI** | 10k neuroni/giorno | 20+ open weights | sì | no |
| ~~Cohere~~ | 100 RPD | Command R+ | **NO — solo non commerciale** | — |

Due vincoli non tecnici che vanno rispettati, perché OB1 vende a club:

1. **Licenza**: Cohere free è non commerciale → escluso dal registry.
   Il flag `commercial_use: false` esclude una rotta da qualsiasi output cliente
   (`OB1_LLM_COMMERCIAL_ONLY=1`, default).
2. **Training**: Mistral free e Google free possono usare i prompt per il training.
   Per i dati OB1 (notizie pubbliche + Transfermarkt) è accettabile. Se un domani
   entrano note private di osservatori o valutazioni K-Sport, quel materiale non
   passa da lì: `OB1_LLM_ALLOW_TRAINING=0` esclude quelle rotte.

Ogni riga della tabella ha un corrispettivo in `config/llm_providers.yaml` con
limiti al ~80% del reale, per lasciare margine.

**Capacità aggregata stimata** (scenario C, dopo cache al 70%): ~600 chiamate LLM
reali/giorno contro ~5.000 di capacità free disponibile. Margine ~8×.

---

## 6. Sostituire il grounding (Fasi 2-3 — implementate)

Il pezzo che azzera davvero la voce di costo. Vive in `src/free_stack.py`:

```
free_web_search(query, include_domains=...)   cache 7g -> DDG -> SearXNG -> Tavily* -> Serper*
llm_complete_json(system, user, ...)          gateway free -> Gemini in coda
has_any_llm()                                 c'è almeno una via per fare inferenza?
```
`*` = solo se la chiave esiste. Con **zero** chiavi configurate la ricerca funziona
comunque (DuckDuckGo non richiede registrazione), e l'inferenza richiede una sola
chiave qualsiasi — `GROQ_API_KEY` da sola basta per l'intero enrichment.

**Discovery** (`GlobalScraper.discover_players`):
```
prima:  Gemini grounded  →  nomi giocatori                    [$14–35/1k prompt]
ora:    free_web_search (DDG/SearXNG, source-first sulle       [$0 + €0 inferenza]
        trusted_sources) → llm_complete_json("triage") → stessa forma di output
```
Il grounding resta raggiungibile con `OB1_LLM_MODE=gemini_first`; su risultato
vuoto la pipeline ricade sul percorso Tavily preesistente, invariato.

**Enrichment** (`enricher_tm.enrich_player_free`):
```
prima:  Gemini grounded su TM  →  JSON profilo
ora:    URL TM da cache permanente (data/tm_urls.json) o ricerca free
        → fetch pagina
        → parse_tm_text() regex          ← risolve la maggioranza dei campi
        → llm_complete_json("extract")   ← SOLO sui campi rimasti vuoti
```
La cache dell'URL TM toglie la ricerca dal 99% delle chiamate: un giocatore ha un
solo profilo TM, per sempre. Verifica su dato reale (Cosimo Patierno, nessuna
chiave a pagamento): DDG trova l'URL corretto, la pagina scarica, il regex estrae
data di nascita, valore di mercato, piede, ruolo e altezza — l'LLM interviene solo
sul residuo (nel caso specifico: il club).

Il merge è **deterministic-first**: `if v is not None and not data.get(k)`.
Un valore estratto dal regex non viene mai sovrascritto dall'LLM (test
`test_deterministic_data_is_never_overwritten_by_the_llm`).

---

## 7. Qualità con modelli gratuiti

I modelli free sono più deboli di gemini-2.5-flash su estrazione strutturata.
Il vincolo di business ("solo dati verificabili, zero errori") non si negozia,
quindi la qualità va difesa a valle, non sperando nel modello:

1. **Schema + range check** — un `market_value` di €400M in Serie C è un errore di
   parsing, non una notizia. Campi fuori range → scartati, non pubblicati
2. **Deterministic wins** — se la regex ha estratto un campo, il valore dell'LLM
   **non** lo sovrascrive. L'LLM riempie i buchi, non corregge i dati certi
3. **Consenso a due modelli** sui campi critici (età, club, valore): due rotte
   diverse, stesso prompt. Se concordano → confidence alta. Se divergono → campo
   marcato `unverified` e non entra nel report cliente
4. **Confidence per campo** già presente nel modello dati (`quality_gate.py`):
   estenderla con l'origine (`regex` | `llm:consenso` | `llm:singolo`)

Il costo del consenso è una seconda chiamata sui campi critici: ~15% di volume in
più, su una capacità con margine 8×. Si può permettere.

---

## 8. Scalare a N leghe

Il collo di bottiglia non è più l'LLM ma l'orchestrazione. Due opzioni:

**A. GitHub Actions con matrix (consigliata per il pilota)**
```yaml
strategy:
  matrix:
    league: [italy_serie_c_d, france_national, spain_primera_rfef, ...]
  max-parallel: 3   # più shard in parallelo = più RPM aggregati consumati
```
Ogni shard scrive un file parziale, un job finale fa merge + scoring + publish.
Il ledger va condiviso: o serializzando gli shard, o dando a ogni shard un set di
chiavi dedicato (`GROQ_API_KEY_SHARD_1`, …) per evitare corse sui contatori.
Il ledger attuale è thread-safe **ma non multi-processo**: due shard che scrivono
lo stesso file si sovrascrivono a vicenda. Con chiavi per shard il problema non si
pone; se un giorno serve un ledger condiviso, il posto giusto è D1/KV, non un file.

**B. Cloudflare Workers + Queues + D1 (target a regime)**
L'infrastruttura c'è già (`workers/`, CF Pages). Discovery come cron trigger, fetch
come consumer di coda, D1 come database opportunità, R2 per gli HTML grezzi.
Vantaggi: niente limite di 6 ore tra run, backpressure vera, stato condiviso reale
(il ledger diventa una tabella D1 e il problema multi-processo sparisce).
Da fare **dopo** il pilota: è una migrazione di storage, non di logica.

Regola di dimensionamento: 1 lega ≈ 40 chiamate LLM/giorno dopo cache.
Con ~5.000 chiamate/giorno di capacità free → **~100 leghe** prima di dover pagare.

---

## 9. Osservabilità e sicurezza operativa

- `gateway.run_summary()` a fine pipeline: chiamate, hit rate cache, fallimenti,
  distribuzione per rotta. Va in log CI e nell'admin alert Telegram
- `sanity_check.py`: aggiungere una soglia sul hit rate cache (un crollo = cache
  non persistita tra le run) e sul numero di rotte disponibili
- **Kill switch**: `OB1_LLM_ALLOW_PAID=0` (default) garantisce che nessuna chiamata
  possa generare fattura. Va tenuto a 0 finché non c'è un budget esplicito
- **Degradazione**: se tutte le rotte sono esaurite la pipeline **non fallisce** —
  salta l'arricchimento e rinvia alla run successiva (comportamento già presente in
  `run_enrichment.py`, da mantenere)
- **Verifica trimestrale** dei limiti free tier: cambiano spesso e senza preavviso.
  Il file `config/llm_providers.yaml` porta la data dell'ultimo check in testa

---

## 10. Piano di migrazione

| Fase | Contenuto | Rischio | Stato |
|---|---|---|---|
| **1** | Layer LLM (gateway, ledger, cache, registry) + test offline. `llm_fallback.chat_json` delega al gateway, path legacy come via di fuga | basso — tocca solo il fallback | **fatto** |
| **2** | Enrichment senza grounding: `src/free_stack.py` (ricerca senza chiavi) + cache URL TM + fetch + regex-first + gateway sul residuo | medio — è il cuore del dato | **fatto**, A/B da eseguire |
| **3** | Discovery senza grounding: `GlobalScraper.discover_players` free-first, grounding solo con `OB1_LLM_MODE=gemini_first` | medio | **fatto** |
| **4** | Multi-lega (matrix o Workers) + consenso 2 modelli sui campi critici | alto — nuovo carico | da fare |

**A/B ancora da eseguire prima di considerare chiusa la Fase 2**: su 50 giocatori
già arricchiti via grounding, la catena free deve concordare su `birth_date`,
`current_club` e `market_value` in ≥95% dei casi. Finché il confronto non è fatto,
`OB1_LLM_MODE=gemini_first` resta la via per tornare al comportamento noto.

Ogni fase è indipendente e reversibile: `OB1_LLM_GATEWAY=0` riporta al comportamento
precedente senza rollback di codice.

**Costo atteso a fine Fase 3**, scenario C: ricerca $17–43/mese (Serper con dedup e
cache), inferenza **$0**, resto dell'infrastruttura $0. Contro $1.300–2.600/mese
della pipeline attuale portata alla stessa scala.

---

## 11. Rischi

| Rischio | Impatto | Mitigazione |
|---|---|---|
| Un provider chiude il free tier | perde ~1/6 della capacità | 6 provider, rimozione = 6 righe di YAML |
| Free tier che degradano tutti insieme | pipeline ferma | ultimo anello a pagamento in registry, spento di default; si accende con una env var |
| Modelli free peggiori sull'estrazione | dati sbagliati ai club | regex-first + range check + consenso (§7) |
| Rate limit più stretti del dichiarato | throughput sotto le attese | limiti a ~80% del reale + failover automatico |
| Ledger condiviso tra shard paralleli | contatori sballati | chiavi per shard nel pilota, D1 a regime (§8) |
| ToS: uso free tier per fini commerciali | rischio legale | `commercial_use` per provider; Cohere già escluso |

---

## 12. Runbook

Nuove variabili d'ambiente (tutte opzionali — senza nessuna, il gateway non ha rotte
e il codice ricade sul path legacy):

```bash
CEREBRAS_API_KEY=      # https://cloud.cerebras.ai   — volume alto, priorità 10
GROQ_API_KEY=          # https://console.groq.com
MISTRAL_API_KEY=       # https://console.mistral.ai
OPENROUTER_API_KEY=    # https://openrouter.ai       — frontier free
NVIDIA_API_KEY=        # https://build.nvidia.com
GEMINI_API_KEY=        # già presente, ora ultima rotta e senza grounding

OB1_LLM_GATEWAY=1          # 0 = torna al fallback legacy (via di fuga)
OB1_LLM_CACHE=1            # 0 = disabilita la cache (debug)
OB1_LLM_ALLOW_PAID=0       # 1 = abilita le rotte a pagamento (kill switch)
OB1_LLM_COMMERCIAL_ONLY=1  # 0 = ammette modelli con licenza non commerciale
OB1_LLM_ALLOW_TRAINING=1   # 0 = esclude provider che si addestrano sui prompt
```

Diagnostica:

```bash
PYTHONIOENCODING=utf-8 python -m unittest discover -s tests -v
PYTHONIOENCODING=utf-8 python -c "from src.llm import get_gateway; \
  g=get_gateway(); print(g.registry.describe()); print(g.available_routes('extract'))"
```

I secret nuovi vanno aggiunti in GitHub → Settings → Secrets → Actions e passati
allo step `Enrich with Transfermarkt data` di `.github/workflows/ingest.yml`.

---

## Fonti (verificate 2026-08-02)

- [Gemini API pricing 2026 — CloudZero](https://www.cloudzero.com/blog/gemini-pricing/)
- [Gemini API free tier: limiti e quote](https://pecollective.com/tools/gemini-free-tier-guide/)
- [Free LLM API 2026: 13 provider a confronto — OpenRouter](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/)
- [Best free LLM API tiers 2026: Groq, Cerebras, GitHub Models](https://wetheflywheel.com/en/ai-model-access/free-llm-api-tiers-2026/)
- [Free LLM API resources — cheahjs/free-llm-api-resources](https://github.com/cheahjs/free-llm-api-resources)
- [Serper.dev pricing 2026](https://serp.fast/tools/serper-dev)
- [Tavily — crediti e pricing](https://docs.tavily.com/documentation/api-credits)
