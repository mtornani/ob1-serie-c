# OB1 Lega Pro — Dev Log

Tutto quello che è stato fatto, in ordine. Bug, fix, decisioni architetturali.

---

## Architettura finale

```
Gemini Search Grounding + Tavily
        ↓
   ouroboros_run.py          (discovery + gate scoring)
        ↓
   run_enrichment.py         (Transfermarkt via Gemini grounding)
        ↓
   generate_dashboard.py     (SCORE-002 + minutaggio FIGC)
        ↓
   docs/data.json            (servito da CF Pages / GitHub Pages)
        ↓
   docs/index.html + app.js  (dashboard)
        ↓
   send_notification.py      (Telegram HOT/WARM/COLD)
```

Pipeline automatica ogni 6 ore via GitHub Actions (`ingest.yml`).

---

## Bug log — problemi trovati e risolti

### BUG-001 — Enrichment bloccato (tm_enriched skip troppo largo)
**File:** `scripts/run_enrichment.py`
**Problema:** La condizione di skip era `if market_value or appearances or contract_expires`. Qualsiasi player con anche solo un campo compilato veniva saltato, impedendo l'arricchimento completo. Risultato: `tm_enriched = 0` su 67 entries.
**Fix:** Cambiato a `if opp.get('tm_enriched') is True`. Solo i player con enrichment completo vengono saltati.

---

### BUG-002 — Gate scoring inutilizzabile (freshness cliff)
**File:** `src/scoring_global.py` (ora eliminato)
**Problema:** Formula freshness `100 - (days_old * 20)` arrivava a 0 dopo 5 giorni. Notizie di una settimana fa avevano score massimo 4/5, difficilmente superavano il gate.
Inoltre `market_value` e `league_fit` erano definiti come fattori ma non venivano mai calcolati — score sempre parziale.
**Fix:** Eliminato `scoring_global.py` interamente. Gate ora usa `OB1Scorer` da `scoring.py` (unico scorer), soglia `ob1_score >= 55` (WARM floor).

---

### BUG-003 — Due scorer divergenti
**File:** `src/scoring_global.py` e `src/scoring.py`
**Problema:** Il gate in `ouroboros_run.py` usava `scoring_global.py`, la dashboard usava `scoring.py`. Stessi fattori con pesi diversi, nessuna garanzia che un player passasse il gate con lo stesso punteggio mostrato in dashboard.
**Fix:** Eliminato `scoring_global.py`. `ouroboros_run.py` converte `MarketOpportunity` in dict e chiama `OB1Scorer.score()` direttamente. Un solo scorer per tutto il sistema.

---

### BUG-004 — Age model sbagliato
**File:** `src/scoring.py`
**Problema:** Fascia massima `22-28 = 100`. Non allineato con FIGC minutaggio (U23 = nati 2003+, ≤22 anni nel 2026). I 25enni ricevevano punteggio identico ai 20enni.
**Fix:** `18-22 = 100`, `23-26 = 90`, `27-29 = 75`, `30-32 = 45`, `33+ = 25`.

---

### BUG-005 — Scrapling page.text vuoto
**File:** `src/scraper_global.py`
**Problema:** `deep_scrape()` usava `page.text` che restituisce stringa vuota in Scrapling. Documentato in CLAUDE.md ma mai fixato nel codice.
**Fix:** `page.text` → `page.get_all_text()`.

---

### BUG-006 — Chat ID Telegram hardcoded
**File:** `src/notifier.py`
**Problema:** `DEFAULT_CHAT_ID = "1465485090"` come class attribute. Se `TELEGRAM_CHAT_IDS` non fosse impostato, i messaggi andavano sempre a quell'ID — silenzioso, non tracciabile, non configurabile.
**Fix:** Rimosso il class attribute. `_parse_chat_ids()` legge `TELEGRAM_CHAT_IDS` (comma-separated) poi fallback su `TELEGRAM_CHAT_ID` env var. Se nessuno dei due è impostato, lista vuota (nessun invio silenzioso).

---

### BUG-007 — URL sorgente Gemini = vertexaisearch.cloud.google.com
**File:** `src/scraper_global.py`, `src/notifier.py`
**Problema:** Gemini Search Grounding restituisce redirect URL interni (`vertexaisearch.cloud.google.com/grounding-api-redirect/...`) come source_url. Nel Telegram alert appariva "📰 vertexaisearch.cloud.google.com" — incomprensibile.
**Fix:** `_source_name()` helper: se URL contiene `vertexaisearch` o `grounding-api`, restituisce `"Gemini Search"`. Nei Telegram alert, URL di grounding vengono soppressi completamente.

---

### BUG-008 — Score breakdown nel Telegram alert (rumore)
**File:** `src/notifier.py`
**Problema:** `format_hot_alert()` includeva 8 righe di score breakdown (`freshness: 100`, `experience: 50`, ecc.). Ogni HOT alert era 25+ righe. Nessun valore informativo per il destinatario.
**Fix:** Score breakdown rimosso dagli alert Telegram. Rimane solo nel drawer della dashboard.

---

### BUG-009 — Ruolo N/D nel Telegram alert
**File:** `src/notifier.py`
**Problema:** `📍 N/D` compariva su ogni alert dove il ruolo non era ancora disponibile (pre-enrichment). Clutter senza informazione.
**Fix:** La riga ruolo viene mostrata solo se il valore non è `N/D`, `N/A`, o stringa vuota.

---

### BUG-010 — Gemini grounding prompt: "Cognome Nome" → blocklist
**File:** `src/scraper_global.py`
**Problema:** Il prompt chiedeva a Gemini di restituire i nomi nel formato "Cognome Nome". Un giocatore come "Francesco Cinque" veniva restituito come "Cinque Francesco". Il primo token "Cinque" non era nella blocklist, ma per altri giocatori il cognome coincideva con termini bloccati.
**Fix:** Formato cambiato a "Nome Cognome" nel prompt.

---

### BUG-011 — Falsy-zero nel filtro "verified"
**File:** `docs/app.js`
**Problema:** `o.market_value || o.appearances` escludeva i player con `appearances = 0` (zero presenze è dato valido, diverso da dato mancante).
**Fix:** `o.market_value != null || o.appearances != null`.

---

### BUG-012 — URL domain extraction crash
**File:** `src/scraper_global.py`
**Problema:** `url.split('/')[2]` falliva su URL relativi o malformati.
**Fix:** `url.lstrip('/').split('://')[-1].split('/')[0]` — robusto su qualsiasi formato.

---

### BUG-013 — Filtro "TOP 10" incoerente con il counter
**File:** `docs/app.js`, `docs/index.html`
**Problema:** Il chip "TOP 10" mostrava il count dei player HOT (es. 16), ma il filtro mostrava solo i primi 10. Cliccando "TOP 10 [16]" vedevi 10 risultati — confuso.
**Fix:** Filtro mostra tutti i player HOT (≥70), chip rinominato "HOT". Counter e risultati ora sempre coerenti.

---

### BUG-014 — U23 threshold sbagliato nel frontend
**File:** `docs/app.js`
**Problema:** Filtro U23 usava `age <= 21`. La regola FIGC è U23 = nati 2003+, ≤22 anni nel 2026.
**Fix:** `age <= 22` nel filtro, nel counter, e nel tag sulla card.

---

### BUG-015 — Timer urgency in ALL CAPS
**File:** `docs/app.js`
**Problema:** "94 GG LIBERO", "26 GG AL CTR.", "MESI AL CTR." — pesante, grezzo.
**Fix:** Lowercase: "gg libero", "gg al ctr.", "mesi". `letter-spacing` ridotto da `.12em` a `.04em`.

---

### BUG-016 — Tag U21 ridondante sulla card
**File:** `docs/app.js`
**Problema:** La card mostrava già l'età nella riga meta ("Centrocampista · 20a · Atalanta U23"). Il tag U21 verde ripeteva la stessa informazione.
**Fix:** Tag U21 rimosso dalla card. Sostituito con tag "TM ✓" (blu) sui player arricchiti via Transfermarkt — informazione effettivamente nuova.

---

### BUG-017 — Scoring breakdown incomprensibile
**File:** `docs/app.js`, `docs/index.html`
**Problema:** Il drawer mostrava 8 barre orizzontali con numeri 0-100 per fattore. Un osservatore non tecnico non capisce cosa significa "experience: 50" o "league_fit: 80".
**Fix:** Barre sostituite con righe leggibili:
- Icona ✅/⚡/❌ in base al valore
- Label fattore + peso percentuale (es. "Esperienza 20%")
- Frase in italiano (es. "21 anni — profilo U23, ideale FIGC")
- Voto numerico colorato
Aggiunto verdict sentence sopra il breakdown (es. "parametro zero + U23 (21a) — Penalizza: presenze da verificare — Contattare subito.")

---

### BUG-018 — Blurb che va a capo su mobile
**File:** `docs/index.html`
**Problema:** `max-width: 54ch` troppo largo su schermo mobile. "ore." compariva su una riga separata.
**Fix:** `max-width: 46ch`.

---

## Codice eliminato

| File rimosso | Motivo |
|---|---|
| `src/scoring_global.py` | Divergeva da scoring.py, sostituito da scorer unificato |
| `src/agent.py` | Non chiamato da nessuna parte |
| `src/history.py` | Non chiamato da nessuna parte |
| `src/scraper.py` | Sostituito da scraper_global.py |
| `src/scraper_tavily.py` | Funzionalità integrata in scraper_global.py |
| `src/satarch_runner.py` + `src/satarch/` | Feature abbandonata |
| `bot/telegram_bot.py` + `bot/telegram_bot_premium.py` | Sostituiti dal Cloudflare Worker |
| `scripts/enrich_anthropic.py` | Mai usato in produzione |
| `scripts/generate_linkedin_posts.py` | Feature abbandonata |
| `scripts/generate_social_post.py` | Feature abbandonata |
| `scripts/generate_matches.py` | Feature abbandonata |
| `scripts/quick_ingest.py` | Duplicato |
| `scripts/run_enrichment_local.py` | Duplicato di run_enrichment.py |
| `scripts/run_ingest.py` | Duplicato di ouroboros_run.py |
| `scripts/scrape_squadre_b.py` | Fuori scope (Serie B) |
| `scripts/send_public_report.py` | Feature abbandonata |
| `scripts/force_re_enrich.py` | One-off script |
| `data/snapshots/` (178MB) | File binari enormi nel repo git |

---

## Modifiche architetturali

**Scorer unificato**
Prima: `ouroboros_run.py` usava `scoring_global.py` (gate), dashboard usava `scoring.py`. Ora: un solo `OB1Scorer` in `scoring.py` usato ovunque. Gate threshold: `ob1_score >= 55`.

**Source name per Gemini Grounding**
Prima: source_name estratto dall'URL (risultava "vertexaisearch.cloud.google.com"). Ora: `_source_name()` helper che restituisce "Gemini Search" per redirect interni di Gemini.

**Notifier: architettura canali**
| Env var | Uso |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token del bot |
| `TELEGRAM_CHAT_IDS` | Broadcast principale (comma-separated) |
| `TELEGRAM_CHAT_ID` | Fallback broadcast singolo |
| `TELEGRAM_OFFICE_CHAT_ID` | Admin alert (errori pipeline) |
| `TELEGRAM_PUBLIC_CHANNEL_ID` | Canale pubblico (alert HOT ≥85, max 1/giorno) |

---

## Cloudflare setup (da completare da desktop)

**Già configurato in repo:**
- `.github/workflows/deploy-cf-pages.yml` — deploy automatico a CF Pages dopo ogni ingest
- `docs/_headers` — security headers + cache policy
- `docs/_redirects` — SPA routing
- `cf-pages.toml` — riferimento configurazione

**Da fare manualmente (CF Dashboard):**
1. GitHub Secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `TELEGRAM_CHAT_ID`
2. GitHub Actions → "Deploy to Cloudflare Pages" → Run workflow (crea progetto `ob1-lega-pro`)
3. CF Pages → Custom domain → `ob1legapro.matchanalysispro.online`
4. Zero Trust → copia setup da `ob1global.matchanalysispro.online`
5. Tracking Worker → duplica da ob1global → punta al nuovo sottodominio

---

## PR history

| PR | Contenuto | Stato |
|----|-----------|-------|
| #19 | Gemini SDK, SCORE-002, pipeline modernization | Merged |
| #20 | 10 Gemini code review fixes | Merged |
| #21 | Scorer unificato, Telegram fix, dashboard minimization, scoring breakdown UX | Merged |
| #22 | Card polish K-Sport, CF Pages workflow, Zero Trust setup | Merged |
