# NOTIF-002: Priority Filtering & Smart Notifications

## Overview

Sistema di notifiche intelligenti che usa i Watch Profiles (SCORE-002) per
inviare alert personalizzati. Evita spam, rispetta quiet hours, e raggruppa
le notifiche in modo sensato.

## Regole Notifiche

### Priorità Alert

| Condizione | Azione |
|------------|--------|
| HOT (80+) + matcha watch profile | Push immediato |
| WARM (60-79) + matcha watch profile | Daily digest (ore 9:00) |
| COLD (<60) o no match | Nessuna notifica |

### Quiet Hours

- **Default:** 23:00 - 07:00 (no notifiche)
- Le notifiche HOT vengono accumulare e inviate alle 07:00
- Configurabile per utente (futuro)

### Rate Limiting

- Max 5 notifiche/ora per utente
- Max 20 notifiche/giorno per utente
- Se superato: raggruppa in digest

## Architettura

### Notification Queue (KV)

```typescript
interface QueuedNotification {
  id: string;
  chatId: number;
  opportunity: Opportunity;
  matchedProfiles: string[];  // Profile IDs
  priority: 'immediate' | 'digest';
  createdAt: string;
  sentAt?: string;
}

// KV Keys:
// notif:queue:{chatId}:{notifId} → QueuedNotification
// notif:sent:{chatId}:{date} → count (rate limiting)
// notif:digest:{chatId} → QueuedNotification[] (pending digest)
```

### Cron Trigger

```toml
# wrangler.toml
[triggers]
crons = ["0 7 * * *"]  # Daily digest at 07:00 UTC
```

### Flow

```
[New Opportunity]
    ↓
[Get all users with watch profiles]
    ↓
[For each user: check if matches any profile]
    ↓
[If HOT + match + not quiet hours → Send immediately]
[If HOT + match + quiet hours → Queue for 07:00]
[If WARM + match → Add to digest]
    ↓
[Cron at 07:00: Send queued + digests]
```

## Implementation

### Files

```
workers/telegram-bot/src/
  notifications/
    types.ts        # Notification interfaces
    queue.ts        # KV queue operations
    sender.ts       # Send logic with rate limiting
    digest.ts       # Digest formatting
    cron.ts         # Cron handler
```

### Integration Points

1. **Scraper output** → Trigger notification check
2. **Watch profiles** → Filter opportunities
3. **Telegram API** → Send messages
4. **Cron** → Daily digest

## Bot Messages

### Immediate HOT Alert
```
🔥 NUOVO MATCH!

⚽ Marco Rossi (24)
Centrocampista • Svincolato • Score 85

📋 Match: "Cercasi CC under 25"

[📊 Dettagli] [✅ Salva] [❌ Ignora]
```

### Daily Digest
```
📬 Il tuo digest giornaliero

Abbiamo trovato 3 opportunità che matchano i tuoi criteri:

⚡ Luigi Bianchi (22) - Difensore - Score 72
   Match: "Difensori giovani"

⚡ Paolo Verdi (26) - Attaccante - Score 68
   Match: "Attaccanti svincolati"

⚡ Mario Neri (23) - Centrocampista - Score 65
   Match: "Cercasi CC under 25"

🌐 Dashboard per dettagli
```

## Timeline

- Fase 1: Notification sender con rate limiting
- Fase 2: Daily digest cron
- Fase 3: Quiet hours
