# SCORE-002: Watch Criteria System

## Overview

Sistema di filtri personalizzabili che permette a ogni utente/club di definire
i propri criteri di monitoraggio. Il sistema filtra le opportunità mostrando
solo quelle rilevanti per le esigenze specifiche.

## User Stories

1. **Come DS**, voglio salvare i miei criteri di ricerca per non doverli ripetere ogni volta
2. **Come DS**, voglio ricevere alert solo per giocatori che matchano il mio profilo ideale
3. **Come DS**, voglio poter avere più "watch list" (es. una per ruolo carente)

## Architettura

### Watch Profile (Profilo Monitoraggio)

```typescript
interface WatchProfile {
  id: string;
  name: string;                    // "Cercasi Terzino", "Under 23 promettenti"

  // Filtri base
  roles?: string[];                // ["TD", "TS", "DC"]
  opportunity_types?: string[];    // ["svincolato", "prestito"]

  // Età
  age_min?: number;
  age_max?: number;

  // Score minimo
  min_ob1_score?: number;          // Solo opportunità con score >= X

  // Caratteristiche (per DNA matching)
  required_skills?: {
    skill: string;
    min_value: number;
  }[];

  // Categorie
  categories?: string[];           // ["Serie C", "Serie B"]

  // Notifiche
  alert_immediately: boolean;      // Push per match immediato
  include_in_digest: boolean;      // Includi nel daily digest

  // Metadata
  created_at: string;
  updated_at: string;
  active: boolean;
}
```

### Storage

Per la fase Alpha, usiamo Cloudflare KV per persistere i profili:

```
KEY: watch:{chat_id}:{profile_id}
VALUE: JSON WatchProfile
```

### Bot Commands

```
/watch                    - Lista i tuoi profili di monitoraggio
/watch add               - Crea nuovo profilo (wizard interattivo)
/watch remove <id>       - Rimuovi profilo
/watch edit <id>         - Modifica profilo
/watch test <id>         - Mostra opportunità che matchano ora
```

### Wizard Interattivo

Invece di comandi complessi, usiamo inline keyboard:

```
🎯 Nuovo Watch Profile

Che ruolo cerchi?
[Difensore] [Centrocampista] [Attaccante] [Tutti]

Che tipo di opportunità?
[Svincolato] [Prestito] [Tutti]

Fascia d'età?
[Under 21] [Under 25] [Under 30] [Tutti]

Score minimo?
[Solo HOT (80+)] [WARM+ (60+)] [Tutti]
```

## Integrazione con Notifiche (NOTIF-002)

Quando arriva una nuova opportunità:

1. Per ogni utente con watch profiles attivi
2. Controlla se l'opportunità matcha almeno un profilo
3. Se `alert_immediately: true` → push notification
4. Se `include_in_digest: true` → aggiungi al digest giornaliero

## Implementazione

### Fase 1: Storage & CRUD (questo sprint)
- [x] Definire schema WatchProfile
- [ ] Setup KV binding in Cloudflare Worker
- [ ] Implementare /watch list
- [ ] Implementare /watch add (wizard)
- [ ] Implementare /watch remove
- [ ] Implementare /watch test

### Fase 2: Matching Engine
- [ ] Funzione `matchesProfile(opportunity, profile): boolean`
- [ ] Integrazione nel flow di notifica

### Fase 3: Natural Language
- [ ] "avvisami quando trovi un terzino svincolato under 25"
- [ ] "monitora i centrocampisti box-to-box"

## Files

```
workers/telegram-bot/src/
  watch/
    types.ts          # WatchProfile interface
    storage.ts        # KV operations
    matcher.ts        # Matching logic
    wizard.ts         # Inline keyboard wizard
    handlers.ts       # /watch command handlers
```

## Esempio Uso

```
User: /watch add
Bot: 🎯 Nuovo Watch Profile
     Che ruolo cerchi?
     [Difensore] [Centrocampista] [Attaccante] [Portiere] [Tutti]

User: [clicks Difensore]
Bot: ✅ Difensore
     Che tipo di opportunità?
     [Svincolato] [Prestito] [Rescissione] [Tutti]

User: [clicks Svincolato]
Bot: ✅ Difensore svincolato
     Fascia d'età?
     [Under 21] [Under 25] [Under 30] [Tutti]

User: [clicks Under 25]
Bot: ✅ Difensore svincolato under 25

     📋 Riepilogo Watch Profile:
     • Ruolo: Difensore
     • Tipo: Svincolato
     • Età: Under 25
     • Alert: Immediato per HOT, Digest per WARM

     [✅ Salva] [❌ Annulla] [✏️ Modifica]

User: [clicks Salva]
Bot: ✅ Watch Profile salvato!

     Riceverai notifiche quando troveremo difensori
     svincolati under 25.

     /watch per gestire i tuoi profili
```

## Timeline

- **Day 1**: Storage + CRUD base + /watch list
- **Day 2**: Wizard interattivo + /watch test
