# BOT-001: Telegram Bot Interattivo

## Metadata
- **ID**: BOT-001
- **Priority**: High
- **Status**: In Progress
- **Dependencies**: UX-001 (data.json endpoint)

## Obiettivo
Creare un bot Telegram interattivo che permetta agli scout di consultare le opportunità di mercato direttamente da Telegram, senza dover aprire la dashboard.

## Architettura

### Stack Tecnologico
- **Runtime**: Cloudflare Workers (edge computing)
- **Webhook**: Telegram Bot API webhook mode
- **Data Source**: GitHub Pages `data.json`
- **Language**: JavaScript/TypeScript

### Flusso
```
User Message → Telegram API → Webhook → Cloudflare Worker
                                              ↓
                                    Fetch data.json from GitHub Pages
                                              ↓
                                    Process command
                                              ↓
                              Telegram API ← Response
```

## Comandi Bot

### `/start`
**Descrizione**: Messaggio di benvenuto e istruzioni
**Response**:
```
🎯 Benvenuto in OB1 Radar Bot!

Sono il tuo assistente per lo scouting Serie C/D.

📋 Comandi disponibili:
/hot - Giocatori HOT (score 80+)
/warm - Giocatori WARM (score 60-79)
/all - Tutte le opportunità
/search <nome> - Cerca giocatore
/stats - Statistiche attuali
/help - Mostra questo messaggio

🔗 Dashboard: https://mtornani.github.io/ob1-serie-c/
```

### `/hot`
**Descrizione**: Lista giocatori con OB1 Score >= 80
**Response**: Lista formattata con emoji 🔥

### `/warm`
**Descrizione**: Lista giocatori con OB1 Score 60-79
**Response**: Lista formattata con emoji ⚡

### `/all`
**Descrizione**: Tutte le opportunità ordinate per score
**Response**: Lista completa (max 10, con paginazione)

### `/search <query>`
**Descrizione**: Ricerca per nome giocatore o club
**Response**: Risultati matching o "Nessun risultato"

### `/stats`
**Descrizione**: Statistiche aggregate
**Response**:
```
📊 OB1 Radar Stats

Total: X opportunità
🔥 HOT: X
⚡ WARM: X
❄️ COLD: X

Ultimo aggiornamento: DD/MM/YYYY HH:mm
```

### `/help`
**Descrizione**: Elenco comandi (alias di /start)

## Formato Messaggio Giocatore

```
🔥 Nicolas Viola (87/100)
📍 Centrocampista Centrale | 28 anni
💼 SVINCOLATO
🏟️ Ex: Fiorentina, Cagliari, Benevento
📅 30/01/2026
🔗 Dettagli
```

## Implementazione

### File Structure
```
workers/
└── telegram-bot/
    ├── wrangler.toml
    ├── package.json
    ├── src/
    │   ├── index.ts        # Entry point
    │   ├── handlers.ts     # Command handlers
    │   ├── telegram.ts     # Telegram API helpers
    │   ├── data.ts         # Data fetching
    │   └── formatters.ts   # Message formatting
    └── README.md
```

### Environment Variables (Secrets)
- `TELEGRAM_BOT_TOKEN`: Token del bot
- `DATA_URL`: URL del data.json (default: GitHub Pages)

### Webhook Setup
```bash
# Set webhook
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://ob1-bot.<account>.workers.dev/webhook"}'
```

## Security

### Rate Limiting
- Max 30 requests/minuto per user
- Implementato con Cloudflare KV o in-memory

### Validation
- Verificare `X-Telegram-Bot-Api-Secret-Token` header
- Validare struttura update Telegram

## Monitoring

### Logging
- Log ogni comando ricevuto
- Log errori con stack trace
- Metriche: comandi/ora, utenti unici

### Alerts
- Errori > 5% in 5 minuti
- Latenza > 2s media

## Deploy

### Prerequisites
1. Account Cloudflare (free tier OK)
2. Wrangler CLI installato
3. Bot token da @BotFather

### Steps
```bash
cd workers/telegram-bot
npm install
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler deploy
# Set webhook to worker URL
```

## Testing

### Local Development
```bash
wrangler dev
# Use ngrok for webhook testing
ngrok http 8787
```

### Test Commands
- [ ] /start risponde correttamente
- [ ] /hot filtra score >= 80
- [ ] /warm filtra score 60-79
- [ ] /search trova giocatori
- [ ] /stats mostra conteggi corretti
- [ ] Comando sconosciuto → help message

## Future Enhancements
- [ ] Inline mode per ricerca rapida
- [ ] Callback buttons per azioni
- [ ] Notifiche push personalizzate per ruolo
- [ ] Salvataggio preferiti per utente (KV storage)
- [ ] Multi-lingua (IT/EN)

## Acceptance Criteria
- [ ] Bot risponde a tutti i comandi in < 2s
- [ ] Dati sempre aggiornati (fetch real-time)
- [ ] Formato messaggi leggibile su mobile
- [ ] Zero downtime (edge deployment)
- [ ] Costo $0 (free tier Cloudflare)
