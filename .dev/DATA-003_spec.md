# DATA-003: Snapshot Storico & Market Intelligence

**Priority:** HIGH | **Estimate:** 4 Quick Wins + MW-3 Social Output
**Status:** DONE (incluso MW-3)
**Created:** 2026-02-17
**Objective:** Trasformare OB1 da tool di scouting informativo a macchina che produce prove pubbliche delle inefficienze del mercato Lega Pro.

---

## Contesto Strategico

L'output di OB1 verra' usato per generare post settimanali su X (Twitter) e alimentare un canale Telegram. Il tono e' critico, basato su dati oggettivi, stile "i numeri parlano da soli."

Per costruire questa narrazione servono 4 capacita' che il sistema attualmente non ha:
1. **Memoria storica** — cosa c'era ieri vs oggi
2. **Rete agenti** — chi gestisce i giocatori ignorati dal mercato
3. **Statistiche concrete** — presenze, gol, assist: i fatti
4. **Rilevamento anomalie** — svincolati con buone stats ignorati da troppo tempo

---

## QW-3: Snapshot Storico delle Opportunita'

### Requisito

Ad ogni esecuzione del workflow di ingest, **PRIMA** di sovrascrivere `data/opportunities.json`, viene salvata una copia in:
```
data/snapshots/opportunities_YYYYMMDD_HHMM.json
```

Se il file snapshot per quel timestamp esiste gia', viene sovrascritto.

### Implementazione

- **File:** `.github/workflows/ingest.yml`
- **Step aggiuntivo** posizionato PRIMA del run dello scraper:
  ```yaml
  - name: Snapshot current data
    run: |
      mkdir -p data/snapshots
      if [ -f data/opportunities.json ]; then
        cp data/opportunities.json "data/snapshots/opportunities_$(date -u +'%Y%m%d_%H%M').json"
        echo "Snapshot created"
      else
        echo "No existing data to snapshot"
      fi
  ```
- **`.gitignore`**: NON deve ignorare `data/snapshots/`. I file devono essere committati.
- **Step di commit**: deve includere `data/snapshots/` nel `git add`.

### Acceptance Criteria

- [ ] Il workflow crea il file snapshot prima di ogni run
- [ ] I file snapshot vengono committati nel repository
- [ ] Il flusso esistente non viene interrotto
- [ ] Se non esiste `opportunities.json`, lo step non fallisce

---

## QW-1: Campo Agent dall'Enrichment Transfermarkt

### Requisito

Il campo `agent` (stringa, opzionale) viene persistito nella opportunity quando disponibile dall'enrichment Transfermarkt. Il prompt Gemini dell'enricher GIA' chiede il campo `agent`, ma il valore non viene salvato nel dict di output della opportunity.

### Implementazione

- **File:** `scripts/run_enrichment.py` — aggiungere `'agent'` alla lista dei campi copiati dal risultato TM alla opportunity (riga 48)
- **File:** `src/models.py` — aggiungere `agent: Optional[str] = None` a `PlayerProfile`
- **File:** `scripts/generate_dashboard.py` — aggiungere `'agent'` al dict `dashboard_opp`
- **File:** `src/notifier.py` — mostrare agente nel messaggio HOT alert se disponibile
- **File:** `scripts/generate_weekly_report.py` — mostrare agente nella card se disponibile

### Acceptance Criteria

- [ ] Il campo `agent` appare nel JSON salvato dopo enrichment
- [ ] La dashboard include il campo nel dict delle opportunita'
- [ ] Il messaggio Telegram HOT mostra l'agente se presente
- [ ] Il report settimanale mostra l'agente se presente

---

## QW-2: Statistiche Stagionali da Transfermarkt

### Requisito

L'enricher Transfermarkt estrae, oltre ai dati anagrafici, le statistiche della stagione corrente:
- `appearances` (presenze, int, opzionale)
- `goals` (gol, int, opzionale)
- `assists` (assist, int, opzionale)
- `minutes_played` (minuti giocati, int, opzionale)

Questi campi sono opzionali (possono essere null se non trovati sulla pagina TM).

### Implementazione

- **File:** `src/enricher_tm.py` — modificare il prompt Gemini per chiedere esplicitamente le 4 stats stagionali
- **File:** `scripts/run_enrichment.py` — aggiungere i 4 campi al merge
- **File:** `scripts/generate_dashboard.py` — passare i campi al dashboard dict
- **File:** `src/notifier.py` — mostrare stats nel messaggio HOT: `📈 Stagione 25/26: {appearances} presenze, {goals} gol, {assists} assist`

### Acceptance Criteria

- [ ] Il prompt Gemini chiede esplicitamente le stats stagionali
- [ ] I 4 campi appaiono nel JSON salvato dopo enrichment
- [ ] La dashboard li include
- [ ] Il messaggio Telegram HOT li mostra se presenti

---

## QW-4: Alert "Svincolato Stale" (Free Agent Ignorato)

### Requisito

Viene calcolato un campo `days_without_contract` per ogni giocatore con `opportunity_type` in `(svincolato, rescissione)`. Il calcolo e':
```
days_without_contract = (oggi - discovered_at).days
```

Se `days_without_contract > 30` E il giocatore ha `appearances >= 10` (dalla stagione corrente o dal campo enriched), il giocatore viene flaggato come `stale_free_agent: true`.

Il report settimanale include una sezione **"CASO DELLA SETTIMANA"** che seleziona lo `stale_free_agent` con il punteggio OB1 piu' alto.

### Implementazione

- **File:** `scripts/generate_dashboard.py` — aggiungere calcolo `days_without_contract` e flag `stale_free_agent`
- **File:** `scripts/generate_weekly_report.py` — aggiungere sezione "Caso della settimana" con tutti i dati disponibili
- **Logica selezione:**
  ```python
  stale = [p for p in opportunities if p.get('stale_free_agent')]
  case_of_week = max(stale, key=lambda x: x.get('ob1_score', 0), default=None)
  ```

### Acceptance Criteria

- [ ] `days_without_contract` calcolato per svincolati/rescissioni
- [ ] Flag `stale_free_agent` impostato quando condizioni soddisfatte
- [ ] Report settimanale include sezione "Caso della settimana"
- [ ] Il caso mostra: nome, eta', ruolo, stats, giorni senza contratto, score, agente (se disponibile)

---

## Impatto sulla Narrazione Critica

| Quick Win | Dato prodotto | Esempio output |
|-----------|--------------|----------------|
| QW-3 | Delta storico | "La settimana scorsa c'erano 28 svincolati. Oggi 31. +3 in 7 giorni." |
| QW-1 | Rete agenti | "Il 40% degli svincolati di Serie C e' gestito dallo stesso gruppo di agenti." |
| QW-2 | Fatti concreti | "25 anni, 28 presenze, 9 gol. Svincolato. Zero offerte." |
| QW-4 | Anomalia | "Questo giocatore e' svincolato da 47 giorni. Nessuno lo ha chiamato." |

---

---

## MW-3: Generatore Automatico di Post Pubblici

**Status:** DONE — vedi spec completa: `.dev/DATA-003-MW3_social_output.md`

| Componente | File |
|-----------|------|
| Generatore post | `scripts/generate_social_post.py` |
| Invio canale pubblico | `scripts/send_public_report.py` |
| Alert HOT pubblici | `src/notifier.py` (metodi `send_public_hot_alert`, `format_hot_alert_public`) |
| Output X | `data/social/weekly_x_post.txt` |
| Output Telegram | `data/social/weekly_telegram_post.txt` |
| Workflow integrato | `.github/workflows/weekly-report.yml` |

---

**Last Updated:** 2026-02-18
