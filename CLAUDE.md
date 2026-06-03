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
