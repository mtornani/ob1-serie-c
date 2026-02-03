# OB1 Scout - Telegram Bot

Bot Telegram intelligente per DS e scout Serie C. Capisce il linguaggio del campo e supporta anche messaggi vocali.

## Funzionalità

### 🔍 Ricerca Naturale
Scrivi come parleresti al tuo collaboratore:
- "mi serve un terzino che spinga"
- "centrocampista box-to-box under 23"
- "attaccante svincolato fisico"

### 🎤 Messaggi Vocali
Invia un vocale e il bot trascrive e cerca automaticamente.

### 🔔 Alert Personalizzati
Crea profili di monitoraggio e ricevi digest giornaliero alle 8:00.

### 🧬 Squadre B
Accesso ai dati di Juventus Next Gen, Milan Futuro, Atalanta U23.

## Comandi

| Comando | Descrizione |
|---------|-------------|
| `/start` | Avvia il bot |
| `/report` | Report mercato completo |
| `/hot` | Opportunità top (score 80+) |
| `/watch` | Gestisci alert personalizzati |
| `/watch add` | Crea nuovo alert |
| `/digest` | Anteprima digest giornaliero |
| `/talenti` | Talenti dalle squadre B |
| `/scout` | Wizard guidato |
| `/stats` | Statistiche database |
| `/help` | Guida completa |

## Setup

### Prerequisiti

1. [Node.js](https://nodejs.org/) >= 18
2. Account [Cloudflare](https://cloudflare.com/) (free tier OK)
3. Bot Telegram creato con [@BotFather](https://t.me/BotFather)

### Installazione

```bash
cd workers/telegram-bot
npm install
```

### Configurazione

1. Login a Cloudflare:
```bash
npx wrangler login
```

2. Crea il KV namespace per i dati utente:
```bash
npx wrangler kv:namespace create USER_DATA
# Copia l'ID nel wrangler.toml
```

3. Aggiungi i secrets:
```bash
npx wrangler secret put TELEGRAM_BOT_TOKEN
# Token da @BotFather

npx wrangler secret put OPENROUTER_API_KEY
# (Opzionale) Per messaggi vocali e LLM avanzato
```

### Deploy

```bash
npm run deploy
```

### Setup Webhook

Dopo il deploy, configura il webhook:
```bash
curl "https://ob1-telegram-bot.<account>.workers.dev/setup?url=https://ob1-telegram-bot.<account>.workers.dev/webhook"
```

### Setup Menu Comandi

```bash
curl "https://ob1-telegram-bot.<account>.workers.dev/setup-commands"
```

### Verifica

Controlla lo stato del webhook:
```
https://ob1-telegram-bot.<account>.workers.dev/webhook-info
```

## Endpoints

| Endpoint | Descrizione |
|----------|-------------|
| `GET /` | Health check |
| `POST /webhook` | Telegram webhook |
| `GET /webhook-info` | Info webhook |
| `GET /setup?url=...` | Configura webhook |
| `GET /setup-commands` | Aggiorna menu comandi |
| `GET /trigger-cron` | Test manuale digest |

## Cron Jobs

Il bot ha un cron trigger configurato alle 07:00 UTC (08:00 Italia) che:
- Invia il digest giornaliero agli utenti con alert attivi
- Processa le notifiche in coda

## Environment Variables

| Variable | Descrizione | Tipo |
|----------|-------------|------|
| `TELEGRAM_BOT_TOKEN` | Token del bot | Secret |
| `OPENROUTER_API_KEY` | API key OpenRouter | Secret (opzionale) |
| `DATA_URL` | URL del data.json | wrangler.toml |
| `DASHBOARD_URL` | URL della dashboard | wrangler.toml |

## KV Namespaces

| Binding | Utilizzo |
|---------|----------|
| `USER_DATA` | Profili watch, notifiche, preferenze utente |

## Architettura

```
User Message/Voice
    |
    v
Telegram API
    |
    v
Cloudflare Worker (webhook)
    |
    ├── Text Message → Smart Search (LLM + filters)
    |
    ├── Voice Message → OpenRouter transcription → Smart Search
    |
    └── Command → Handler specifico
    |
    v
Fetch data.json + squadre_b.json
    |
    v
Process & Filter
    |
    v
Send response via Telegram API
```

## Development

### Local Development

```bash
npm run dev
```

Per testare il webhook localmente, usa ngrok:
```bash
ngrok http 8787
# Poi imposta il webhook all'URL ngrok
```

### Logs

```bash
npm run tail
```
