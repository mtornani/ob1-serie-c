# OB1 Radar Telegram Bot

Bot Telegram interattivo per consultare le opportunita di mercato Serie C/D.

## Comandi

| Comando | Descrizione |
|---------|-------------|
| `/start` | Messaggio di benvenuto |
| `/hot` | Giocatori HOT (score 80+) |
| `/warm` | Giocatori WARM (score 60-79) |
| `/all` | Tutte le opportunita |
| `/search <nome>` | Cerca giocatore |
| `/stats` | Statistiche attuali |
| `/help` | Lista comandi |

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

2. Aggiungi il token del bot come secret:
```bash
npx wrangler secret put TELEGRAM_BOT_TOKEN
# Inserisci il token quando richiesto
```

### Deploy

```bash
npm run deploy
```

Dopo il deploy, otterrai un URL tipo:
```
https://ob1-telegram-bot.<account>.workers.dev
```

### Setup Webhook

Visita questo URL nel browser per configurare il webhook:
```
https://ob1-telegram-bot.<account>.workers.dev/setup?url=https://ob1-telegram-bot.<account>.workers.dev/webhook
```

Oppure via curl:
```bash
curl "https://ob1-telegram-bot.<account>.workers.dev/setup?url=https://ob1-telegram-bot.<account>.workers.dev/webhook"
```

### Verifica

Controlla lo stato del webhook:
```
https://ob1-telegram-bot.<account>.workers.dev/webhook-info
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

## Architettura

```
User Message
    |
    v
Telegram API
    |
    v
Cloudflare Worker (webhook)
    |
    v
Fetch data.json from GitHub Pages
    |
    v
Process command
    |
    v
Send response via Telegram API
```

## Environment Variables

| Variable | Descrizione | Dove |
|----------|-------------|------|
| `TELEGRAM_BOT_TOKEN` | Token del bot | Secret |
| `DATA_URL` | URL del data.json | wrangler.toml |
| `DASHBOARD_URL` | URL della dashboard | wrangler.toml |
