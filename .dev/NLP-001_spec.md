# NLP-001: Natural Language Processing per Telegram Bot

## Overview

Permettere agli utenti di interrogare il bot usando linguaggio naturale invece di comandi rigidi.

## Problem Statement

Situazione attuale:
```
Utente: "chi sono i centrocampisti svincolati?"
Bot: ❓ Comando non riconosciuto.
```

Obiettivo:
```
Utente: "chi sono i centrocampisti svincolati?"
Bot: 🔍 Ho trovato 3 centrocampisti svincolati...
```

## Solution

### Intent Recognition

Usare pattern matching + keywords per riconoscere l'intento:

| Intent | Keywords/Patterns | Action |
|--------|-------------------|--------|
| `search_player` | "cerca", "trovami", "chi è", nome proprio | `/search` |
| `list_hot` | "migliori", "top", "hot", "priorità alta" | `/hot` |
| `list_warm` | "interessanti", "warm", "da tenere d'occhio" | `/warm` |
| `list_all` | "tutti", "lista completa", "elenco" | `/all` |
| `get_stats` | "statistiche", "numeri", "quanti" | `/stats` |
| `filter_role` | "centrocampisti", "difensori", "attaccanti", "portieri" | search by role |
| `filter_type` | "svincolati", "prestito", "rescissione" | search by type |
| `filter_age` | "giovani", "under 25", "esperti", "over 30" | search by age |
| `help` | "aiuto", "come funziona", "cosa puoi fare" | `/help` |

### Query Examples

```
"mostrami i centrocampisti svincolati"
→ Intent: filter_role + filter_type
→ Action: search(role=centrocampista, type=svincolato)

"ci sono giovani attaccanti?"
→ Intent: filter_role + filter_age
→ Action: search(role=attaccante, age<25)

"chi è il migliore disponibile?"
→ Intent: list_hot
→ Action: /hot limit=1

"quante opportunità abbiamo oggi?"
→ Intent: get_stats
→ Action: /stats

"Alessio Rosa"
→ Intent: search_player (nome proprio rilevato)
→ Action: /search Alessio Rosa
```

## Implementation

### File: `workers/telegram-bot/src/nlp.ts`

```typescript
interface ParsedIntent {
  intent: string;
  filters: {
    role?: string;
    type?: string;
    ageMin?: number;
    ageMax?: number;
    query?: string;
  };
  confidence: number;
}

export function parseNaturalQuery(text: string): ParsedIntent {
  const lower = text.toLowerCase();

  // Intent patterns
  const intents = {
    search_player: /cerca|trovami|chi è|info su/,
    list_hot: /migliori|top|hot|priorit|urgenti/,
    list_warm: /interessant|warm|occhio|monitorare/,
    list_all: /tutti|lista|elenco|completo/,
    get_stats: /statistic|numer|quant|riepilog/,
    help: /aiuto|help|come funziona|cosa (puoi|sai)/,
  };

  // Filter patterns
  const roles = {
    centrocampista: /centrocamp|cc|mediano|mezzala/,
    difensore: /difensor|dc|terzino|centrale/,
    attaccante: /attaccant|punta|ala|esterno offensivo/,
    portiere: /portier|gk|goalkeeper/,
  };

  const types = {
    svincolato: /svincolat|libero|free/,
    prestito: /prestito|loan/,
    rescissione: /rescission|risoluzione/,
    scadenza: /scadenza|contratto in scadenza/,
  };

  // Age patterns
  const agePatterns = {
    young: /giovan|under.?2[0-5]|u2[0-5]/,
    experienced: /espert|over.?3[0-5]|veteran/,
  };

  // Parse...
}
```

## Acceptance Criteria

- [ ] Bot capisce domande in italiano naturale
- [ ] Riconosce ruoli, tipi opportunità, fasce d'età
- [ ] Fallback a comando più probabile se intent non chiaro
- [ ] Risposta contestuale che ripete la query interpretata
- [ ] Supporto per query composite (es. "centrocampisti svincolati under 28")

## Status

**Status:** IN PROGRESS
**Created:** 2026-01-31
