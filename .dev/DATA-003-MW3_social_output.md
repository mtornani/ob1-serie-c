# DATA-003-MW3: Social Output — Il Murales Settimanale

**Priority:** HIGH | **Feature:** MW-3 (Market Watch 3)
**Status:** DONE
**Created:** 2026-02-18
**Dipende da:** DATA-003 (QW-1, QW-2, QW-3, QW-4)

---

## Scopo

OB1 Scout diventa una macchina di critica pubblica automatizzata.

Ogni lunedì pubblica prove oggettive delle inefficienze del mercato di Lega Pro.
Il parallelo è Banksy: non si spiega, si piazza. I dati parlano da soli.

Il messaggio implicito: "Il mercato di Lega Pro è inefficiente. Ecco la prova.
Un algoritmo da 5$/mese trova quello che direttori sportivi pagati decine di
migliaia di euro non trovano."

---

## Componenti

| File | Ruolo |
|------|-------|
| `scripts/generate_social_post.py` | Genera i file di testo per X e Telegram |
| `scripts/send_public_report.py` | Invia il post al canale pubblico via Bot API |
| `src/notifier.py` | Alert HOT singoli al canale pubblico (max 1/giorno) |
| `data/social/weekly_x_post.txt` | Output pronto per X (Twitter) |
| `data/social/weekly_telegram_post.txt` | Output pronto per Telegram pubblico |
| `data/social/.last_public_alert` | Lock file: data dell'ultimo alert HOT pubblico |

---

## Schedule

- **Generazione post**: ogni lunedì 08:00 UTC, workflow `weekly-report.yml`
- **Invio pubblico**: stesso workflow, step successivo alla generazione
- **Alert HOT singoli**: ogni run del workflow `ingest.yml` (ogni 6h), max 1/giorno

---

## Canale Pubblico vs Privato

| Contenuto | Privato (Mirko) | Pubblico (@ob1scout) |
|-----------|----------------|----------------------|
| Score breakdown | ✅ | ❌ |
| Inline keyboard (Salva/Ignora) | ✅ | ❌ |
| Nome agente (alert singolo) | ✅ | ❌ (solo nel report settimanale) |
| Nome agente (report settimanale) | ✅ | ✅ (sezione RETE AGENTI) |
| Stats stagionali | ✅ | ✅ |
| OB1 Score | ✅ | ✅ (solo numero finale) |
| Dashboard link | ✅ | ✅ |
| Firma "murales" | ❌ | ✅ |

---

## Formato Post X (Twitter)

**File:** `data/social/weekly_x_post.txt`

```
📊 Lega Pro — Settimana {week_number}

Svincolati attivi: {total_free_agents}
Under 28 ignorati: {under_28_ignored}
Media giorni senza contratto: {avg_days}

Il caso: {player_name}, {age} anni, {appearances} presenze, {goals} gol, svincolato da {days} giorni.

{firma}

🔗 t.me/ob1scout
```

- **Limite**: 280 char per tweet. Se supera, split in `[1/2]` / `[2/2]`
- **Split logico**: Parte 1 = numeri + caso. Parte 2 = firma + link.
- **Firma rotante** basata sul numero di settimana ISO

---

## Formato Post Telegram Pubblico

**File:** `data/social/weekly_telegram_post.txt`

```
📊 OB1 SCOUT — Report Settimanale {data}

━━━ I NUMERI ━━━

🔴 {N} svincolati attivi nel sistema
🔴 {N} sono under 28
🔴 Media giorni senza contratto: {N}
🔴 Nuovi questa settimana: {N}
🔴 Ignorati da oltre 30 giorni: {N}

━━━ IL CASO DELLA SETTIMANA ━━━

🎯 {nome}, {età} anni
📍 {ruolo} | {piede} | {altezza}cm
📈 Stagione 25/26: {presenze} pres | {gol} gol | {assist} assist
🏟️ Ex: {club} (Serie C)
📅 Svincolato dal {data} ({giorni} giorni fa)
💰 Valore TM: {valore}
👔 Agente: {agente}
📊 OB1 Score: {score}/100

Nessun club di Serie C risulta averlo ingaggiato.

━━━ TOP 5 IGNORATI ━━━

1. {nome} — {età} — {gol} gol — {giorni}gg senza contratto
...

━━━ RETE AGENTI ━━━  (solo se ≥3 giocatori con campo agent popolato)

{agente}: {N} svincolati gestiti
...

━━━━━━━━━━━━━━━━━━

{firma}

🔗 Dashboard: {url}
```

---

## Logica Selezione "Caso della Settimana"

```python
# Priorità 1: stale free agent con appearances >= 10 e goals not null
stale = [p for p in opportunities
         if p.get('stale_free_agent')
         and (p.get('appearances') or 0) >= 10
         and p.get('goals') is not None]
case = max(stale, key=lambda x: (x['ob1_score'], x['days_without_contract']))

# Fallback 1: stale con appearances >= 5
# Fallback 2: giocatore con score più alto in assoluto (con testo adattato)
```

---

## Regole di Visibilità Campi

- Campi `null`/mancanti: **omessi silenziosamente** (nessun "N/D")
- Sezione RETE AGENTI: appare **solo se** ≥3 svincolati hanno `agent` popolato
- TOP 5: ordina per `score DESC`, poi `days_without_contract DESC`
- Se meno di 5 stale, mostra quelli disponibili senza forzare il numero

---

## Guard: Dati Insufficienti

Se `total_free_agents < 5`, `generate_social_post.py` termina con exit 0
senza generare i file. Il post non viene pubblicato.
**Meglio saltare una settimana che pubblicare numeri privi di significato.**

---

## Alert HOT Pubblici (singoli)

**Trigger:** ogni run di `ingest.yml` quando viene trovato un giocatore HOT

**Condizioni di invio al canale pubblico:**
- `ob1_score >= 85`
- `appearances >= 5`
- Max 1 alert pubblico al giorno (lock file `data/social/.last_public_alert`)

**Formato:**
```
🔴 NUOVA SEGNALAZIONE

{nome}, {età} anni
— {ruolo}

{presenze} presenze | {gol} gol | {assist} assist
{tipo_opportunità} — ex {club}
💰 {valore}

OB1 Score: {score}/100

Il sistema lo ha trovato. Vediamo quanto ci mette il mercato.
```

**Note:** Il nome dell'agente NON appare negli alert singoli (solo nel report settimanale).

---

## Firme del Murales (rotazione)

```
"I numeri parlano da soli."
"Un algoritmo li trova in 6 ore. Il mercato no."
"Il sistema li trova. Il mercato ancora no."
```

Rotazione basata sul numero di settimana ISO: `FIRME[week_number % len(FIRME)]`

---

## Configurazione Necessaria

**GitHub Secrets da aggiungere:**
- `TELEGRAM_PUBLIC_CHANNEL_ID` — ID o @username del canale pubblico (es: `@ob1scout`)
  Il `TELEGRAM_BOT_TOKEN` è già presente.

**Il bot deve essere admin del canale pubblico** con permesso di postare messaggi.

---

## Retrocompatibilità

Il modulo pubblico è un **layer aggiuntivo**. Il bot privato continua a funzionare
esattamente come prima. Nessuna modifica ai flussi esistenti, solo aggiunte.

---

**Last Updated:** 2026-02-18
