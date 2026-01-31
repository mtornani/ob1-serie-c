# OB1 Serie C - Roadmap to Production

## Da MVP a "Serendipity" per Lega Pro

**Goal:** Trasformare OB1 da semplice aggregatore a vero assistente di scouting che anticipa le esigenze dei DS.

---

## Stato Attuale (2026-01-31)

```
v2.1 DASHBOARD + BOT INTERATTIVO

Completato:
  [x] Scraper automatico ogni 6h
  [x] RAG su Gemini File Search
  [x] Agent conversazionale
  [x] Dashboard PWA responsive (UX-001)
  [x] Onboarding tutorial
  [x] Telegram Bot interattivo (BOT-001)
  [x] GitHub Actions pipeline

In Progress:
  [ ] Deploy bot su Cloudflare Workers

Mancante per uso professionale:
  - Scoring intelligente
  - Notifiche prioritizzate
  - Filtri personalizzati
  - Valutazioni Transfermarkt
  - Report automatici
  - Storico giocatori
```

---

## PHASE 0: UX Foundation (3-4 giorni) ✅ COMPLETATO

### UX-001: Dashboard Responsive Design ✅
**Priority:** CRITICAL | **Status:** DONE
**Spec:** `.dev/UX-001_spec.md`

Redesign completo mobile-first:
- [x] Layout responsive (mobile/tablet/desktop)
- [x] Score badges visuali (HOT/WARM/COLD)
- [x] Filter chips interattivi
- [x] Bottom navigation mobile
- [x] PWA enhancements (pull-to-refresh, offline)
- [x] Dark/light mode auto
- [x] Onboarding tutorial per nuovi utenti

**Deliverable:** https://mtornani.github.io/ob1-serie-c/

---

## PHASE 0.5: Bot Interattivo ✅ COMPLETATO

### BOT-001: Telegram Bot su Cloudflare Workers
**Priority:** HIGH | **Status:** READY TO DEPLOY
**Spec:** `.dev/BOT-001_spec.md`

Bot interattivo serverless:
- [x] Architettura Cloudflare Workers
- [x] Comandi: /start, /hot, /warm, /all, /search, /stats, /help
- [x] Fetch dati da GitHub Pages data.json
- [x] Formattazione messaggi HTML
- [x] Webhook setup automatico

**Deploy:** `workers/telegram-bot/`

---

## PHASE 1: Intelligent Scoring (1 settimana)

### SCORE-001: OB1 Score Algorithm
**Priority:** CRITICAL | **Estimate:** 2-3 giorni
**Spec:** `.dev/SCORE-001_spec.md`

Sistema di scoring per prioritizzare opportunita:

```python
OB1_SCORE = (
    role_fit      × 25% +   # Match con esigenze club
    age_fit       × 20% +   # Fascia eta target
    experience    × 25% +   # Presenze in categoria
    timing        × 15% +   # Urgenza (rescissione vs rumors)
    value_ratio   × 15%     # Rapporto qualita/costo
)
```

**Output:**
- Score 1-100 per ogni opportunita
- Classificazione: HOT (80+), WARM (60-79), COLD (<60)
- Ordinamento automatico nelle notifiche

---

### SCORE-002: Watch Criteria System
**Priority:** HIGH | **Estimate:** 2 giorni
**Spec:** `.dev/SCORE-002_spec.md`

Filtri personalizzabili per utente/club:

```python
WATCH_CRITERIA = {
    "max_age": 28,
    "min_appearances": 10,
    "preferred_roles": ["CC", "DC", "ES"],
    "max_estimated_salary": 150000,
    "categories": ["Serie C", "Serie B"],
    "alert_types": ["svincolato", "rescissione", "prestito"]
}
```

**Storage:** JSON file o GitHub Gist per persistenza

---

## PHASE 2: Rich Notifications (1 settimana)

### NOTIF-001: Enhanced Telegram Alerts
**Priority:** CRITICAL | **Estimate:** 2-3 giorni
**Spec:** `.dev/NOTIF-001_spec.md`

Da notifica generica:
```
Trovate 3 nuove opportunita
```

A notifica actionable:
```
🔥 ALERT PRIORITA ALTA

🎯 Nicolas Viola (28 anni)
📍 Centrocampista - Ex Fiorentina/Cagliari
💼 SVINCOLATO da oggi
📊 OB1 Score: 87/100
⭐ Match: 92% (cerca CC esperto)

📰 Fonte: Calciomercato.com
🔗 [Dettagli] [Salva] [Ignora]
```

---

### NOTIF-002: Priority Filtering
**Priority:** HIGH | **Estimate:** 1-2 giorni
**Spec:** `.dev/NOTIF-002_spec.md`

- Notifica PUSH solo per score > 70
- Daily digest per score 50-69
- Weekly summary per il resto
- Configurable thresholds

---

## PHASE 3: Data Enrichment (1-2 settimane)

### DATA-001: Transfermarkt Integration
**Priority:** HIGH | **Estimate:** 3-4 giorni
**Spec:** `.dev/DATA-001_spec.md`

Scraping valutazioni di mercato:
- Valore attuale
- Storico valutazioni
- Statistiche carriera
- Scadenza contratto

**Approccio:** Transfermarkt API non esiste, serve scraping HTML o fonte alternativa (Football-Data.org, API-Football).

---

### DATA-002: Player History Tracking
**Priority:** MEDIUM | **Estimate:** 2-3 giorni
**Spec:** `.dev/DATA-002_spec.md`

Database storico:
- Prima volta visto
- Evoluzione score
- Status changes (svincolato → firmato)
- "Quel terzino era disponibile 3 mesi fa, cos'è successo?"

---

## PHASE 4: Reporting (1 settimana)

### REPORT-001: Weekly PDF Report
**Priority:** MEDIUM | **Estimate:** 2-3 giorni
**Spec:** `.dev/REPORT-001_spec.md`

Report automatico ogni lunedi:
- Top 10 opportunita della settimana
- Movimenti completati
- Giocatori in scadenza
- Trend di mercato

**Output:** PDF via email o Telegram

---

### REPORT-002: Comparison Tool
**Priority:** LOW | **Estimate:** 2 giorni
**Spec:** `.dev/REPORT-002_spec.md`

"Meglio Rossi o Bianchi per il nostro modulo?"
- Comparazione side-by-side
- Radar chart statistiche
- Pro/contro per contesto club

---

## Timeline

```
Week 0 (Jan 30 - Feb 2):
└─ UX-001: Dashboard Responsive Design ⬅️ START HERE

Week 1 (Feb 3-7):
├─ SCORE-001: OB1 Score Algorithm
└─ SCORE-002: Watch Criteria System

Week 2 (Feb 8-14):
├─ NOTIF-001: Enhanced Telegram Alerts
└─ NOTIF-002: Priority Filtering

Week 3-4 (Feb 15-28):
├─ DATA-001: Transfermarkt Integration
└─ DATA-002: Player History Tracking

Week 5 (Mar 1-7):
├─ REPORT-001: Weekly PDF Report
└─ REPORT-002: Comparison Tool (if time)
```

---

## Priority Matrix

| Feature | Impact per Lega Pro | Effort | Priority |
|---------|---------------------|--------|----------|
| UX-001 | 🔴 ALTO | 4d | P0 |
| SCORE-001 | 🔴 ALTO | 3d | P0 |
| NOTIF-001 | 🔴 ALTO | 3d | P0 |
| SCORE-002 | 🟡 MEDIO | 2d | P1 |
| NOTIF-002 | 🟡 MEDIO | 2d | P1 |
| DATA-001 | 🟡 MEDIO | 4d | P2 |
| DATA-002 | 🟢 BASSO | 3d | P2 |
| REPORT-001 | 🟡 MEDIO | 3d | P2 |
| REPORT-002 | 🟢 BASSO | 2d | P3 |

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Opportunita trovate/settimana | ~20 | ~50+ |
| % con score calcolato | 0% | 100% |
| Notifiche actionable | 0% | 80%+ |
| Tempo a prima notifica | N/A | <1h da news |
| User engagement (Telegram) | TBD | Daily active |

---

## Immediate Next Step

**Inizia con UX-001** (Dashboard Responsive):
- Mobile-first per DS in movimento
- Visualizza gli score (base per tutto)
- Professionalizza l'immagine
- Quick win visibile

Poi SCORE-001 → NOTIF-001 (scoring + notifiche arricchite)

---

**Last Updated:** 2026-01-30
