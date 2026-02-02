# BOT-001: Telegram Bot Interattivo - Specifica Completa

## Metadata
- **ID**: BOT-001
- **Priority**: High
- **Status**: ✅ COMPLETATO (v3.0)
- **Dependencies**: UX-001 (data.json), DNA-001 (dna_matches.json)
- **Last Updated**: 2026-02-02

---

## Obiettivo

Bot Telegram intelligente che permette ai DS di Serie C di:
1. Consultare opportunità di mercato in linguaggio naturale
2. Ricevere notifiche smart basate su criteri personalizzati
3. Trovare match DNA tra talenti e club
4. Essere guidati nella ricerca con wizard interattivo (stile Akinator)

---

## Architettura

### Stack Tecnologico
```
Runtime:        Cloudflare Workers (edge computing, <50ms latency)
AI:             Cloudflare AI (LLM fallback per NLP)
Storage:        Cloudflare KV (user profiles, watch criteria)
Data Source:    GitHub Pages (data.json, dna_matches.json)
Language:       TypeScript
Webhook:        Telegram Bot API
```

### Flusso Richiesta
```
User Message → Telegram API → Webhook → Cloudflare Worker
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    │                                                   │
                    ▼                                                   ▼
            [Command?]                                          [Natural Language]
                    │                                                   │
                    ▼                                                   ▼
         handleCommand()                                      parseNaturalQuery()
                    │                                                   │
                    │                              ┌────────────────────┼────────────────────┐
                    │                              │                    │                    │
                    │                              ▼                    ▼                    ▼
                    │                      [Confidence OK]    [Low Confidence]      [Wizard Trigger]
                    │                              │                    │                    │
                    │                              │                    ▼                    ▼
                    │                              │           classifyWithLLM()    startScoutWizard()
                    │                              │                    │                    │
                    └──────────────────────────────┴────────────────────┴────────────────────┘
                                                   │
                                                   ▼
                                          Fetch data.json / dna_matches.json
                                                   │
                                                   ▼
                                          Format Response
                                                   │
                                                   ▼
                                          Telegram API ← Send Message
```

---

## File Structure

```
workers/telegram-bot/
├── wrangler.toml              # Cloudflare config
├── package.json
├── tsconfig.json
└── src/
    ├── index.ts               # Entry point, webhook handler
    ├── handlers.ts            # Message & callback handlers
    ├── telegram.ts            # Telegram API helpers
    ├── types.ts               # TypeScript interfaces
    │
    ├── data.ts                # Data fetching & filtering
    ├── dna.ts                 # DNA matching logic
    ├── formatters.ts          # Message formatting
    │
    ├── nlp.ts                 # Natural Language Processing
    ├── llm-classifier.ts      # Cloudflare AI fallback
    ├── talent-search.ts       # "Field language" queries
    │
    ├── scout-wizard.ts        # Akinator-style wizard
    │
    ├── watch/                 # Watch Criteria System
    │   ├── types.ts
    │   ├── storage.ts         # KV persistence
    │   ├── wizard.ts          # Interactive wizard
    │   └── matcher.ts         # Profile matching
    │
    ├── notifications/         # Smart Notifications
    │   ├── sender.ts
    │   └── digest.ts
    │
    └── response-generator.ts  # AI-powered responses
```

---

## Comandi Disponibili

### Base Commands

| Comando | Descrizione | Output |
|---------|-------------|--------|
| `/start` | Benvenuto + istruzioni | Messaggio intro |
| `/help` | Lista comandi | Help dettagliato |
| `/hot` | Opportunità HOT (score 80+) | Lista top 5 |
| `/warm` | Opportunità WARM (score 60-79) | Lista top 5 |
| `/all` | Tutte le opportunità | Lista top 8 |
| `/search <nome>` | Cerca giocatore | Risultati matching |
| `/stats` | Statistiche mercato | Conteggi + ultimo update |

### DNA Matching Commands

| Comando | Descrizione | Output |
|---------|-------------|--------|
| `/talenti` | Top talenti squadre B | Match score >75% |
| `/dna <club>` | DNA match per club | Top 5 match con score |

### Watch Criteria Commands

| Comando | Descrizione | Output |
|---------|-------------|--------|
| `/watch` | Lista profili attivi | Inline keyboard |
| `/watch add` | Crea nuovo profilo | Wizard interattivo |
| `/watch remove` | Rimuovi profilo | Selezione |
| `/watch test` | Testa profili su dati attuali | Match trovati |
| `/digest` | Anteprima digest giornaliero | Preview |

### Scout Wizard Command

| Comando | Descrizione | Output |
|---------|-------------|--------|
| `/scout` | Avvia wizard guidato | Domande step-by-step |
| `/wizard` | Alias di /scout | |
| `/aiutami` | Alias di /scout | |

---

## Natural Language Processing (NLP-001)

### Pattern Riconosciuti

#### Ruoli
```typescript
'centrocampista': /\b(centrocamp\w*|cc|mediano|mezzala|regista|trequartista|interno)\b/i
'difensore': /\b(difensor\w*|dc|terzin\w*|central\w*|stopper|libero)\b/i
'attaccante': /\b(attaccant\w*|punt\w*|bomber|ala|esterno.?offensiv\w*|prima.?punta|seconda.?punta)\b/i
'portiere': /\b(portier\w*|gk|goalkeeper|numero.?1)\b/i
```

#### Tipi Opportunità
```typescript
'svincolato': /\b(svincolat\w*|liber\w*|free|senza.?contratto|a.?zero)\b/i
'prestito': /\b(prestit\w*|loan|in.?prestito|temporane\w*)\b/i
'rescissione': /\b(rescission\w*|risoluzion\w*|consensual\w*)\b/i
```

#### Nazionalità (DATA-001)
```typescript
'sudamericano': /\b(sudamerican\w*|argentino|brasiliano|uruguaiano|...)\b/i
'europeo': /\b(europe\w*|comunitari\w*|passaporto.?(?:eu|ue|comunitari\w*))\b/i
'africano': /\b(african\w*|senegalese|nigeriano|camerunese|...)\b/i
```

#### Età
```typescript
'giovane': /\b(giovan\w*|under.?(\d+)|u(\d+)|ragaz\w*)\b/i  → max 25
'esperto': /\b(espert\w*|over.?(\d+)|veteran\w*)\b/i       → min 30
```

### Esempi Query → Intent

| Query | Intent | Filters |
|-------|--------|---------|
| "centrocampisti svincolati" | list_all | role=centrocampista, type=svincolato |
| "attaccanti under 25" | list_all | role=attaccante, ageMax=25 |
| "migliori opportunità" | list_hot | minScore=80 |
| "talenti dalle squadre B" | dna_top | - |
| "match per pescara" | dna_club | query=pescara |
| "mi serve qualcuno" | → Scout Wizard | - |

### LLM Fallback (NLP-002)

Quando confidence < 0.5, usa Cloudflare AI:
```typescript
const llmResult = await classifyWithLLM(env.AI, text);
// Returns: { intent, filters, confidence, explanation }
```

---

## Scout Wizard (SCOUT-001)

### Filosofia "Akinator"
Il DS non sa sempre cosa vuole, ma sa rispondere a domande mirate.

### Flow
```
Step 1: "Che ruolo ti serve?"
        → Difensore / Centrocampista / Attaccante / Portiere / Vediamo tutto

Step 2: "Che tipo di giocatore cerchi?"
        → Giovane da far crescere / Già pronto / Esperto-Leader / Non importa

Step 3: "Che budget hai?"
        → Solo parametri zero / Anche prestiti / Vediamo tutto

Step 4: "Che caratteristiche umane cerchi?"
        → Leader-capitano / Gregario affidabile / Talento da scoprire / Non importa

→ Risultati filtrati + suggerimenti AI
```

### Trigger Phrases
```typescript
/\b(mi serve qualcuno|aiutami a trovare|non so cosa cercare|cosa mi consigli)\b/i
```

### Rivalità Calcistiche Italiane
Il wizard tiene conto delle incompatibilità storiche:

```typescript
const RIVALRIES = {
  'cesena': ['rimini'],
  'rimini': ['cesena'],
  'reggiana': ['modena', 'parma'],
  'pisa': ['livorno', 'fiorentina'],
  'catania': ['palermo', 'messina'],
  'bari': ['lecce', 'foggia'],
  // ... etc
};
```

---

## DNA Matching (DNA-001)

### Algoritmo
```
DNA_SCORE = (
    position_fit  × 30% +   # Ruolo richiesto dal club
    age_fit       × 20% +   # Fascia età target
    style_fit     × 25% +   # Stile di gioco compatibile
    availability  × 15% +   # Underused = più disponibile
    budget_fit    × 10%     # Costo prestito vs budget
)
```

### Club con Profilo DNA
- Pescara
- Cesena
- Perugia
- (Rimini - in arrivo)

### Squadre B Monitorate
- Juventus Next Gen
- Milan Futuro
- Atalanta U23

---

## Watch Criteria (SCORE-002)

### Profile Schema
```typescript
interface WatchProfile {
  id: string;
  name: string;
  roles?: string[];           // ['DC', 'TD']
  opportunity_types?: string[]; // ['svincolato', 'prestito']
  age_min?: number;
  age_max?: number;
  min_ob1_score?: number;
  alert_immediately: boolean;
  include_in_digest: boolean;
  active: boolean;
}
```

### Storage
- Cloudflare KV Namespace: `USER_DATA`
- Key format: `profiles:{chatId}`
- Max 5 profili per utente

---

## Smart Notifications (NOTIF-002)

### Tipi Notifica

| Tipo | Trigger | Timing |
|------|---------|--------|
| HOT Alert | score >= 80 + watch match | Immediato |
| Daily Digest | score >= 60 + watch match | 08:00 Italia |

### Rate Limiting
- Max 5 notifiche/ora
- Max 20 notifiche/giorno
- Quiet hours: 23:00-07:00

### Cron Job
```yaml
schedule: 0 7 * * *  # 07:00 UTC = 08:00 Italia
```

---

## Environment Variables

### Wrangler Secrets
```bash
wrangler secret put TELEGRAM_BOT_TOKEN
```

### Wrangler Vars (wrangler.toml)
```toml
[vars]
DATA_URL = "https://mtornani.github.io/ob1-serie-c/data.json"
DASHBOARD_URL = "https://mtornani.github.io/ob1-serie-c/"
```

### Bindings
```toml
[[kv_namespaces]]
binding = "USER_DATA"
id = "8fa1cfab5c5542afa3d2a683411e283c"

[ai]
binding = "AI"
```

---

## Deploy

### Commands
```bash
cd workers/telegram-bot
npm install
npx wrangler deploy
```

### Webhook Setup (automatico)
Il bot imposta il webhook automaticamente al primo `/start`.

### URL Produzione
```
https://ob1-telegram-bot.mirkotornani.workers.dev
```

---

## Testing Checklist

### Comandi Base
- [x] `/start` risponde con benvenuto
- [x] `/hot` filtra score >= 80
- [x] `/warm` filtra score 60-79
- [x] `/all` mostra lista completa
- [x] `/search` trova giocatori
- [x] `/stats` mostra conteggi

### NLP
- [x] "centrocampisti svincolati" → filtra correttamente
- [x] "attaccanti under 25" → età max 25
- [x] "migliori opportunità" → intent list_hot
- [x] Frasi vaghe → Scout Wizard

### DNA
- [x] `/talenti` mostra top match
- [x] `/dna pescara` mostra match per Pescara
- [x] Club non trovato → messaggio chiaro

### Watch
- [x] `/watch` mostra profili
- [x] `/watch add` avvia wizard
- [x] Matching funziona

### Scout Wizard
- [x] `/scout` avvia wizard
- [x] Inline keyboard funziona
- [x] Risultati filtrati corretti

---

## Performance

| Metrica | Target | Attuale |
|---------|--------|---------|
| Response time | <2s | <1s |
| Uptime | 99.9% | 99.9% |
| Error rate | <1% | <0.5% |
| Cold start | <100ms | ~50ms |

---

## Future Enhancements

- [ ] Inline mode per ricerca rapida
- [ ] Voice messages (speech-to-text)
- [ ] Integrazione calendario (remind me)
- [ ] Export PDF da bot
- [ ] Multi-lingua (IT/EN)

---

**Maintainer**: Mirko Tornani
**Bot**: @Ob1LegaPro_bot
