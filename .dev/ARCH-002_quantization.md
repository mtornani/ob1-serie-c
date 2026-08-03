# ARCH-002 — Quantizzazione: dal lavoro a orologio al lavoro a evento

**Stato**: spec, non implementata
**Data**: 2026-08-03
**Prerequisito**: ARCH-001 (gateway LLM free-tier) — implementato, Fasi 1-3
**Obiettivo**: rendere il costo proporzionale all'**informazione nuova** invece che
al passare del tempo. Nessuna riscrittura: uno strato sopra quello esistente.

---

## 1. Il principio

> Il quanto minimo di lavoro AI è **il più piccolo input che può cambiare l'output**.

Tutto il resto è lavoro rifatto. Da questo discendono quattro corollari, in
ordine di risparmio decrescente:

1. **Mai chiamare un modello su qualcosa già visto** — hash del *contenuto*,
   prima ancora di costruire il prompt. La cache di ARCH-001 lavora sul prompt:
   arriva troppo tardi, dopo che fetch e costruzione del prompt sono già stati pagati.
2. **Mai chiamare un modello per ciò che un parser decide** — deterministic-first.
   *Già fatto* (`parse_tm_text` prima, LLM solo sul residuo).
3. **Mai chiamare un modello a orologio** — si chiama su un **segnale di
   cambiamento**. *Questo manca, ed è il grosso del risparmio.*
4. **Mai usare un modello grande dove uno piccolo chiude il caso** — task class.
   *Già fatto* (triage / extract / reason).

Corollario zero, che vale più di tutti: **la spazzatura costa per sempre**. Ogni
entry non-giocatore che supera il gate viene cercata, scaricata e arricchita a
ogni ciclo, all'infinito. In `data/opportunities.json` c'è un "Comunicato
Ufficiale" con valore di mercato 50 mln €, arricchito e validato. Il filtro
deterministico a monte è il quanto più economico dell'intero sistema.

---

## 2. La metrica che manca

**Costo per fatto nuovo verificato.** Non per run, non per giocatore.

```
costo_per_fatto = (ricerche + chiamate_llm + fetch) / campi_nuovi_verificati
```

Senza questo numero ogni discussione architetturale resta un'opinione. Con
questo numero ogni modifica diventa un esperimento con un esito misurabile.
**Va implementata per prima**, prima di qualsiasi ottimizzazione: altrimenti non
si sa se le ottimizzazioni funzionano.

---

## 3. Diagnosi: cosa scala e cosa no

| Gamba | Complessità attuale | Costo marginale | Stato |
|---|---|---|---|
| Ricerca URL Transfermarkt | **O(giocatori nuovi)** | ~$0.001 una tantum | già quantizzata (cache `data/tm_urls.json`) |
| Fetch pagina | O(refresh) | $0 banda | **da quantizzare** (manca ETag/304) |
| Estrazione regex | O(fetch) | $0 | già ottimale |
| Chiamata LLM enrichment | O(campi mancanti) | $0 free tier | già quantizzata |
| **Discovery** | **O(leghe × query × run)** | cresce col **tempo** | **rotta: è qui il problema** |
| **Refresh profili** | **O(profili / 14 giorni)** | quasi tutto sprecato | **rotta: timer invece che segnale** |

Le due righe in grassetto crescono indipendentemente dal fatto che sia successo
qualcosa. A 30 leghe: 1.440 ricerche discovery/giorno + 1.430 refresh/giorno
≈ 86.000 operazioni/mese, quasi tutte su contenuto identico a ieri.

**Stima del post-quantizzazione** (assunzioni, non misure — ma la conclusione
regge finché *articoli nuovi ≪ query × run*): ~500-1.000 chiamate LLM/giorno
contro ~5.000 di capacità free aggregata, e $2-5/mese di ricerca. Circa
**10-20× di differenza a parità di scala**.

---

## 4. Verifica preliminare già fatta (2026-08-03)

Le fonti hanno feed. Controllato dal vivo:

| Fonte | Endpoint | Item |
|---|---|---|
| tuttoc.com | `/rss` | 21 |
| tuttolegapro.com | `/rss` | 21 |
| lacasadic.com | `/rss` | 21 |
| sportitalia.com | `/rss` | 51 |
| tuttomercatoweb.com | `/sitemap.xml` | 91 |
| calciomercato.com | — | nessuno: resta su ricerca |

5 fonti su 6 sono pollabili a costo zero. **L'architettura poggia su un fatto
verificato, non su un'assunzione.**

---

## 5. Cosa sviluppare, e dove

### 5.1 Nuovo package `src/watch/`

```
src/watch/__init__.py
src/watch/sources.py   # config/sources.yaml -> oggetti Source (rss | sitemap | search)
src/watch/poller.py    # Source -> [Item(url, title, published_at, content_hash)]
src/watch/seen.py      # store "cosa ho già visto": hash -> prima/ultima vista
src/watch/queue.py     # coda lavoro deduplicata: WorkItem(kind, entity, reason, source_version)
```

- `poller.py`: parsing RSS e sitemap con `xml.etree` (niente feedparser: dipendenza
  inutile). Rispetta `ETag`/`Last-Modified`: un feed immutato costa un 304.
- `seen.py`: la chiave è `sha256(url + contenuto_normalizzato)`. Un articolo
  ripubblicato con lo stesso testo **non** è un evento.
- `queue.py`: dedup per `(kind, entity, source_version)`. Due articoli sullo
  stesso giocatore nello stesso giorno = un solo work item.

### 5.2 Nuovo `config/sources.yaml`

Per lega, la lista dei feed con il tipo. Da popolare con la tabella §4.
Le `trusted_sources` in `config/leagues.yaml` restano come sono (le usa la
ricerca): questo file è additivo, non le sostituisce.

### 5.3 Metriche — `src/metrics.py` (nuovo)

Contatore per run: ricerche, chiamate LLM, fetch, 304, campi nuovi verificati,
costo stimato. Persiste in `data/metrics.jsonl` (una riga per run: serve la
serie storica, non lo stato). Aggancio in:
- `src/llm/gateway.py` → già ha `run_summary()`, va esteso
- `scripts/sanity_check.py` → soglia di allarme se `costo_per_fatto` peggiora

### 5.4 Modifiche a file esistenti

| File | Modifica |
|---|---|
| `src/enricher_tm.py` | `_fetch_page_text`: mandare `If-None-Match`/`If-Modified-Since`, gestire 304 → salta parse e LLM. Store ETag in `data/tm_etags.json` |
| `src/scraper_global.py` | `discover_players`: consuma la coda di `src/watch`; le query di ricerca restano come **bootstrap** (lega nuova) e come rete per le fonti senza feed |
| `scripts/run_enrichment.py` | Il pending non è più "tutti i non arricchiti" ma "quelli con un segnale": comparsi in un articolo nuovo, ETag TM cambiato, o mai arricchiti |
| `src/quality_gate.py` / `scripts/ouroboros_run.py` | Irrigidire `is_valid_player_name`: il caso "Comunicato Ufficiale" deve essere respinto **prima** di qualsiasi spesa. Aggiungere purge delle entry già in DB |
| `.github/workflows/ingest.yml` | Nuovo step `poll sources` prima della discovery; il DB di stato va nell'artifact |

### 5.5 Storage — il prezzo onesto da pagare

Il change detection **richiede stato persistente e interrogabile**. Gli hash
crescono: ~800 articoli/giorno × 90 giorni = ~72.000 righe. Un JSON committato a
ogni run è insostenibile per git.

- **Fase 1-3**: SQLite in `data/ob1.db`, **gitignorato**, trasportato via artifact
  GitHub Actions. Prune delle righe oltre 60 giorni a fine pipeline.
- **Fase 5**: Cloudflare D1 (l'infrastruttura c'è già: `workers/`, CF Pages).
  Il motivo per spostarsi **non è il compute**, è avere una memoria condivisa e
  interrogabile di cosa è già stato visto. Questo chiude anche il problema del
  ledger non multi-processo (ARCH-001 §8).

---

## 6. Ordine di implementazione

| Fase | Contenuto | Criterio di uscita |
|---|---|---|
| **1** | `src/metrics.py` + aggancio a gateway e sanity_check | Una run stampa `costo_per_fatto`; il valore finisce in `data/metrics.jsonl` |
| **2** | ETag/304 nel fetch TM + `seen.py` | Una seconda run consecutiva sugli stessi giocatori fa ≥80% di 304 e 0 chiamate LLM |
| **3** | `poller.py` + `sources.yaml` + coda; discovery consuma la coda | La discovery su una lega non fa ricerche quando non ci sono articoli nuovi |
| **4** | Enrichment a segnale invece che a timer | Il numero di refresh/giorno scende di ≥70% senza perdere campi |
| **5** | Migrazione stato su D1 (solo se i volumi lo chiedono) | Due shard paralleli non si sovrascrivono il ledger |

Ogni fase è indipendente e misurabile con la metrica della Fase 1. **Non partire
dalla 3**: senza la 1 non si sa se ha funzionato.

---

## 7. Vincoli — cosa NON fare

- **Non rompere `ingest.yml`**: gira ogni 6 ore in produzione. Ogni fase deve
  poter essere disattivata con una env var (`OB1_WATCH=0` → comportamento attuale)
- **Non reintrodurre chiavi obbligatorie**: né Serper né Gemini. L'unico requisito
  resta `has_any_llm()`
- **Non buttare gateway, ledger, cache, `free_stack`**: sono il pezzo costoso da
  scrivere, e un'architettura nuova dovrebbe ricostruirli identici
- **Non cambiare lo schema di `opportunities.json`** senza test: ci girano
  scoring, dashboard, report e bot
- **Non committare** DB binari, cache, `.env`
- **`OB1_LLM_ALLOW_PAID=0`** resta il default: nessuna chiamata fatturabile
- **Non trasformare la pipeline in un agente**: il loop agentico distrugge la
  cache (traiettorie path-dependent → cache miss) e moltiplica le chiamate. Vale
  al bordo interattivo (MCP), non nel nucleo batch

---

## 8. Test attesi

Offline, senza rete, come i 74 esistenti (`tests/`):

- `tests/test_watch.py`: parsing RSS e sitemap da fixture; ETag → 304; un
  articolo ripubblicato identico non genera evento; dedup della coda
- `tests/test_metrics.py`: il costo per fatto è calcolato correttamente anche con
  denominatore zero
- Estendere `tests/test_enricher.py`: il 304 salta parse e LLM
- Estendere `tests/test_llm_gateway.py` solo se il gateway cambia

---

## 9. Stato del repo per una sessione a freddo

- Branch di lavoro: `claude/production-architecture-gemini-costs-i90elw`
  (ARCH-001 Fasi 1-3, **non ancora su main**). Partire da lì, o da main se nel
  frattempo è stato mergiato
- `src/llm/` — gateway, ledger quote, cache risposte, registry provider
- `src/free_stack.py` — ricerca free (DDG → SearXNG → Tavily* → Serper*) e
  `llm_complete_json` / `has_any_llm`
- `src/enricher_tm.py` — `enrich_player_free`: URL cachato → fetch → regex → LLM
  sul residuo. `parse_tm_text` è il parser deterministico
- `config/llm_providers.yaml` — rotte e limiti free tier
- Test: `PYTHONIOENCODING=utf-8 python -m unittest discover -s tests`
- Attenzione nota: DuckDuckGo blocca dopo ~5 ricerche ravvicinate (HTTP 202 +
  pagina anti-bot). Gestito in `free_stack`, ma è il motivo per cui serve
  `TAVILY_API_KEY` nei secret prima di aumentare i volumi
