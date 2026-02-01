# OB1 Serie C - Roadmap to Production

## Da MVP a "Serendipity" per Lega Pro

**Goal:** Trasformare OB1 da semplice aggregatore a vero assistente di scouting che anticipa le esigenze dei DS.

---

## Stato Attuale (2026-02-01)

```
v2.5 - INTELLIGENT SCOUTING ASSISTANT

✅ Completato:
  [x] Scraper automatico ogni 6h (Serper + Tavily)
  [x] RAG su Gemini File Search + Tavily full content
  [x] Agent conversazionale
  [x] Dashboard PWA responsive (UX-001)
  [x] Onboarding tutorial
  [x] Telegram Bot su Cloudflare Workers (BOT-001)
  [x] NLP: Linguaggio naturale per il bot (NLP-001)
  [x] OB1 Score Algorithm (SCORE-001)
  [x] Enhanced Telegram Alerts (NOTIF-001)
  [x] GitHub Actions pipeline

🔄 In Progress:
  [ ] SCORE-002: Watch Criteria System
  [ ] NOTIF-002: Priority Filtering

📋 Prossimi:
  - DATA-001: Transfermarkt Integration
  - DATA-002: Player History Tracking
  - REPORT-001: Weekly PDF Report
```

**Dashboard:** https://mtornani.github.io/ob1-serie-c/
**Telegram Bot:** @Ob1LegaPro_bot

---

## PHASE 0: UX Foundation ✅ COMPLETATO

### UX-001: Dashboard Responsive Design ✅
**Status:** DONE | **Completed:** 2026-01-30

- [x] Layout responsive (mobile/tablet/desktop)
- [x] Score badges visuali (HOT/WARM/COLD)
- [x] Filter chips interattivi
- [x] Bottom navigation mobile
- [x] PWA enhancements (pull-to-refresh, offline)
- [x] Dark/light mode auto
- [x] Onboarding tutorial

---

## PHASE 0.5: Bot Interattivo ✅ COMPLETATO

### BOT-001: Telegram Bot su Cloudflare Workers ✅
**Status:** DONE | **Completed:** 2026-01-31

- [x] Architettura Cloudflare Workers
- [x] Comandi: /start, /hot, /warm, /all, /search, /stats, /help
- [x] Fetch dati da GitHub Pages data.json
- [x] Formattazione messaggi HTML
- [x] Webhook setup automatico

### NLP-001: Natural Language Processing ✅
**Status:** DONE | **Completed:** 2026-02-01

- [x] Riconoscimento intent in italiano
- [x] Filtri per ruolo, tipo, età
- [x] Query composite
- [x] Fallback permissivo (mostra dati nel dubbio)

---

## PHASE 1: Intelligent Scoring ✅ PARZIALMENTE COMPLETATO

### SCORE-001: OB1 Score Algorithm ✅
**Status:** DONE | **Completed:** 2026-01-31

Sistema di scoring multi-fattore:
```python
OB1_SCORE = (
    freshness        × 20% +   # Quanto recente
    opportunity_type × 20% +   # Svincolato > prestito > rumors
    experience       × 20% +   # Presenze in categoria
    age              × 20% +   # Fascia età target (21-28)
    source           × 10% +   # Affidabilità fonte
    completeness     × 10%     # Dati disponibili
)
```

**Output:**
- Score 1-100 per ogni opportunità
- Classificazione: HOT (80+), WARM (60-79), COLD (<60)
- Score breakdown dettagliato

---

### SCORE-002: Watch Criteria System
**Priority:** HIGH | **Estimate:** 2 giorni
**Status:** TODO

Filtri personalizzabili per utente/club:
```python
WATCH_CRITERIA = {
    "max_age": 28,
    "min_appearances": 10,
    "preferred_roles": ["CC", "DC", "ES"],
    "categories": ["Serie C", "Serie B"],
    "alert_types": ["svincolato", "rescissione"]
}
```

---

## PHASE 2: Rich Notifications ✅ PARZIALMENTE COMPLETATO

### NOTIF-001: Enhanced Telegram Alerts ✅
**Status:** DONE | **Completed:** 2026-01-31

- [x] HOT alerts con dettagli completi
- [x] Inline keyboard (Salva, Ignora, Dettagli, Dashboard)
- [x] WARM daily digest
- [x] COLD summary
- [x] Score breakdown nei dettagli

---

### NOTIF-002: Priority Filtering
**Priority:** HIGH | **Estimate:** 1-2 giorni
**Status:** TODO

- [ ] Notifica PUSH solo per score > 80
- [ ] Daily digest per score 60-79
- [ ] Weekly summary per il resto
- [ ] Quiet hours (23:00-07:00)

---

## PHASE 3: Data Enrichment

### DATA-001: Transfermarkt Integration
**Priority:** HIGH | **Estimate:** 3-4 giorni
**Status:** TODO

- Valore attuale giocatore
- Storico valutazioni
- Statistiche carriera complete
- Scadenza contratto

### DATA-002: Player History Tracking
**Priority:** MEDIUM | **Estimate:** 2-3 giorni
**Status:** TODO

- Prima volta visto
- Evoluzione score
- Status changes (svincolato → firmato)

---

## PHASE 4: Reporting

### REPORT-001: Weekly PDF Report
**Priority:** MEDIUM | **Estimate:** 2-3 giorni
**Status:** TODO

Report automatico ogni lunedì:
- Top 10 opportunità della settimana
- Movimenti completati
- Giocatori in scadenza

### REPORT-002: Comparison Tool
**Priority:** LOW | **Estimate:** 2 giorni
**Status:** TODO

Comparazione side-by-side tra giocatori

---

## Progress Summary

| Feature | Status | Completed |
|---------|--------|-----------|
| UX-001 Dashboard | ✅ DONE | 2026-01-30 |
| BOT-001 Telegram | ✅ DONE | 2026-01-31 |
| NLP-001 Natural Language | ✅ DONE | 2026-02-01 |
| SCORE-001 Algorithm | ✅ DONE | 2026-01-31 |
| NOTIF-001 Enhanced Alerts | ✅ DONE | 2026-01-31 |
| SCRAPER-002 Tavily | ✅ DONE | 2026-01-31 |
| SCORE-002 Watch Criteria | 📋 TODO | - |
| NOTIF-002 Priority Filter | 📋 TODO | - |
| DATA-001 Transfermarkt | 📋 TODO | - |
| DATA-002 History | 📋 TODO | - |
| REPORT-001 PDF | 📋 TODO | - |

**Completion:** 6/11 features (55%)

---

**Last Updated:** 2026-02-01
