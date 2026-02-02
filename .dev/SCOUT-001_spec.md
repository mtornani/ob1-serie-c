# SCOUT-001: Scout Wizard (Akinator-style)

## Metadata
- **ID**: SCOUT-001
- **Priority**: High
- **Status**: ✅ COMPLETATO
- **Dependencies**: BOT-001, NLP-001
- **Last Updated**: 2026-02-02

---

## Obiettivo

Sistema conversazionale a domande che guida il DS nella ricerca del giocatore ideale, ispirato al gioco Akinator.

**Problema:** Il DS non sa sempre esattamente cosa vuole. Fa richieste vaghe come:
- "mi serve qualcuno per il centrocampo"
- "aiutami a trovare un giocatore"
- "cosa mi consigli?"

**Soluzione:** Il bot pone domande mirate e affina la ricerca step-by-step.

---

## User Flow

```
DS: "mi serve qualcuno"
        │
        ▼
┌───────────────────────────────────────┐
│  🎯 Scout Wizard (1/4)                │
│                                       │
│  Che ruolo ti serve?                  │
│                                       │
│  [🛡️ Difensore]  [⚙️ Centrocampista] │
│  [⚽ Attaccante] [🧤 Portiere]        │
│  [🔍 Vediamo tutto]                   │
│                                       │
│  [❌ Annulla]                         │
└───────────────────────────────────────┘
        │
        ▼ (click "Centrocampista")
        │
┌───────────────────────────────────────┐
│  🎯 Scout Wizard (2/4)                │
│                                       │
│  Che tipo di giocatore cerchi?        │
│                                       │
│  [🌱 Giovane da far crescere]         │
│  [💪 Già pronto per la C]             │
│  [👴 Esperto/Leader]                  │
│  [🤷 Non importa]                     │
│                                       │
│  [❌ Annulla]                         │
└───────────────────────────────────────┘
        │
        ▼ (click "Giovane")
        │
┌───────────────────────────────────────┐
│  🎯 Scout Wizard (3/4)                │
│                                       │
│  Che budget hai?                      │
│                                       │
│  [🆓 Solo parametri zero]             │
│  [🔄 Anche prestiti]                  │
│  [💰 Vediamo tutto]                   │
│                                       │
│  [❌ Annulla]                         │
└───────────────────────────────────────┘
        │
        ▼ (click "Parametri zero")
        │
┌───────────────────────────────────────┐
│  🎯 Scout Wizard (4/4)                │
│                                       │
│  Che caratteristiche umane cerchi?    │
│                                       │
│  [🎖️ Un leader/capitano]              │
│  [🤝 Un gregario affidabile]          │
│  [💎 Un talento da scoprire]          │
│  [🤷 Non importa]                     │
│                                       │
│  [❌ Annulla]                         │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  🎯 Risultati Scout Wizard            │
│                                       │
│  📋 Hai cercato: centrocampista,      │
│     giovane, a zero                   │
│                                       │
│  🏆 Top 5 match:                      │
│                                       │
│  1. 🔥 Francesco Campagna (23)        │
│     Centrocampista • svincolato • 75  │
│     📍 Ex Cesena                      │
│                                       │
│  2. ⚡ Marco Bontempi (23)            │
│     Centrocampista • mercato • 68     │
│     📍 Luparense                      │
│  ...                                  │
└───────────────────────────────────────┘
```

---

## Trigger Phrases

Il wizard si attiva automaticamente con frasi vaghe:

```typescript
const vaguePatterns = [
  /mi serve (qualcuno|qualcosa|un giocatore)/i,
  /sto cercando (ma non so|qualcosa)/i,
  /aiutami a (trovare|cercare)/i,
  /non so (cosa|chi) cercare/i,
  /cosa mi (consigli|suggerisci)/i,
  /che (giocatori|opportunità) ci sono/i,
];
```

O esplicitamente:
- `/scout`
- `/wizard`
- `/aiutami`

---

## Domande e Opzioni

### Step 1: Ruolo
```typescript
{
  question: "Che ruolo ti serve?",
  options: [
    { label: "Difensore", value: "difensore", emoji: "🛡️" },
    { label: "Centrocampista", value: "centrocampista", emoji: "⚙️" },
    { label: "Attaccante", value: "attaccante", emoji: "⚽" },
    { label: "Portiere", value: "portiere", emoji: "🧤" },
    { label: "Vediamo tutto", value: "qualsiasi", emoji: "🔍" },
  ],
}
```

### Step 2: Esperienza
```typescript
{
  question: "Che tipo di giocatore cerchi?",
  options: [
    { label: "Giovane da far crescere", value: "giovane", emoji: "🌱" },  // age <= 23
    { label: "Già pronto per la C", value: "pronto", emoji: "💪" },       // 23-28
    { label: "Esperto/Leader", value: "esperto", emoji: "👴" },           // >= 28
    { label: "Non importa", value: "qualsiasi", emoji: "🤷" },
  ],
}
```

### Step 3: Budget
```typescript
{
  question: "Che budget hai?",
  options: [
    { label: "Solo parametri zero", value: "zero", emoji: "🆓" },     // type=svincolato
    { label: "Anche prestiti", value: "prestito", emoji: "🔄" },       // include prestiti
    { label: "Vediamo tutto", value: "qualsiasi", emoji: "💰" },
  ],
}
```

### Step 4: Carattere
```typescript
{
  question: "Che caratteristiche umane cerchi?",
  options: [
    { label: "Un leader/capitano", value: "leader", emoji: "🎖️" },
    { label: "Un gregario affidabile", value: "gregario", emoji: "🤝" },
    { label: "Un talento da scoprire", value: "talento", emoji: "💎" },
    { label: "Non importa", value: "qualsiasi", emoji: "🤷" },
  ],
}
```

---

## Rivalità Calcistiche

Il sistema conosce le rivalità storiche del calcio italiano per evitare suggerimenti "impossibili":

```typescript
const RIVALRIES: Record<string, string[]> = {
  // Emilia-Romagna
  'cesena': ['rimini'],
  'rimini': ['cesena'],
  'reggiana': ['modena', 'parma'],
  'modena': ['reggiana', 'parma'],
  'parma': ['reggiana', 'modena'],
  'spal': ['bologna'],

  // Toscana
  'pisa': ['livorno', 'fiorentina'],
  'livorno': ['pisa'],
  'siena': ['fiorentina'],

  // Campania
  'avellino': ['salernitana', 'benevento'],
  'salernitana': ['avellino', 'napoli'],

  // Sicilia
  'catania': ['palermo', 'messina'],
  'palermo': ['catania'],
  'messina': ['catania', 'reggina'],

  // Calabria
  'reggina': ['cosenza', 'catanzaro'],
  'cosenza': ['reggina', 'catanzaro'],
  'catanzaro': ['reggina', 'cosenza'],

  // Puglia
  'bari': ['lecce', 'foggia'],
  'lecce': ['bari', 'taranto'],

  // Veneto
  'padova': ['venezia', 'vicenza', 'verona'],
  'venezia': ['padova', 'treviso'],
};
```

**Uso:** Se un giocatore ha giocato nel Cesena, non verrà suggerito per il Rimini.

---

## Session Management

Le sessioni wizard sono in-memory (per semplicità):

```typescript
interface WizardSession {
  chatId: number;
  messageId?: number;
  step: number;
  answers: {
    role?: string;
    experience?: string;
    budget?: string;
    character?: string;
  };
  startedAt: string;
}

const wizardSessions = new Map<number, WizardSession>();
```

**Timeout:** La sessione scade dopo 5 minuti di inattività.

---

## Callback Data Format

```
scout:{step}:{value}
```

Esempi:
- `scout:1:centrocampista` - Step 1, scelta centrocampista
- `scout:2:giovane` - Step 2, scelta giovane
- `scout:cancel` - Annulla wizard

---

## Filtering Logic

```typescript
// Applica filtri dalle risposte
if (answers.role !== 'qualsiasi') {
  filters.role = answers.role;
}

if (answers.experience !== 'qualsiasi') {
  switch (answers.experience) {
    case 'giovane': filters.ageMax = 23; break;
    case 'pronto': filters.ageMin = 23; filters.ageMax = 28; break;
    case 'esperto': filters.ageMin = 28; break;
  }
}

if (answers.budget !== 'qualsiasi') {
  if (answers.budget === 'zero') {
    filters.type = 'svincolato';
  }
}

// Filtra e ordina
const results = filterOpportunities(opportunities, filters)
  .sort((a, b) => b.ob1_score - a.ob1_score)
  .slice(0, 5);
```

---

## Testing

- [x] `/scout` avvia wizard
- [x] Ogni step mostra inline keyboard
- [x] Click su opzione avanza allo step successivo
- [x] "Annulla" termina il wizard
- [x] Risultati finali mostrano giocatori filtrati
- [x] Nessun risultato mostra messaggio appropriato
- [x] Session timeout gestito

---

## Future Enhancements

- [ ] Step 5: "Per quale piazza?" → esclude rivalità automaticamente
- [ ] Salvataggio preferenze wizard per utente
- [ ] Suggerimenti AI basati su risposte
- [ ] "Refine" per affinare ulteriormente i risultati
- [ ] Voice input support

---

**File:** `workers/telegram-bot/src/scout-wizard.ts`
**Maintainer:** Mirko Tornani
