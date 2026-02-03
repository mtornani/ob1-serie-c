/**
 * NOTIF-002: Notification Sender with Rate Limiting
 */

import { Env, Opportunity } from '../types';
import { sendMessage, sendMessageWithKeyboard } from '../telegram';
import { WatchProfile } from '../watch/types';
import { matchesProfile } from '../watch/matcher';
import { createKVStorage, createMemoryStorage, WatchStorage } from '../watch/storage';
import {
  QueuedNotification,
  DigestEntry,
  RATE_LIMITS,
  isQuietHours,
  generateNotificationId,
} from './types';
import { NotificationQueue, createNotificationQueue, createMemoryQueue } from './queue';

const DASHBOARD_URL = 'https://mtornani.github.io/ob1-serie-c/';

/**
 * Process new opportunities and send notifications
 */
export async function processNewOpportunities(
  opportunities: Opportunity[],
  env: Env
): Promise<{ sent: number; queued: number; digest: number }> {
  const watchStorage = getWatchStorage(env);
  const notifQueue = getNotifQueue(env);

  // Get all users with profiles
  const activeUsers = await notifQueue.getActiveUsers();

  let sent = 0;
  let queued = 0;
  let digest = 0;

  for (const chatId of activeUsers) {
    const profiles = await watchStorage.listProfiles(chatId);
    const activeProfiles = profiles.filter(p => p.active);

    if (activeProfiles.length === 0) continue;

    for (const opp of opportunities) {
      // Find matching profiles
      const matchingProfiles = activeProfiles.filter(p => matchesProfile(opp, p));

      if (matchingProfiles.length === 0) continue;

      // Determine priority
      const isHot = opp.ob1_score >= 80;
      const shouldAlertImmediately = matchingProfiles.some(p => p.alert_immediately);

      if (isHot && shouldAlertImmediately) {
        // HOT + immediate alert → send or queue
        const result = await sendOrQueueImmediate(chatId, opp, matchingProfiles, env, notifQueue);
        if (result === 'sent') sent++;
        else if (result === 'queued') queued++;
      } else if (matchingProfiles.some(p => p.include_in_digest)) {
        // Add to digest
        await notifQueue.addToDigest(chatId, {
          opportunity: opp,
          matchedProfiles: matchingProfiles.map(p => p.name || p.id),
        });
        digest++;
      }
    }
  }

  return { sent, queued, digest };
}

/**
 * Send immediate notification or queue if rate limited / quiet hours
 */
async function sendOrQueueImmediate(
  chatId: number,
  opp: Opportunity,
  matchingProfiles: WatchProfile[],
  env: Env,
  queue: NotificationQueue
): Promise<'sent' | 'queued' | 'skipped'> {
  // Check quiet hours
  if (isQuietHours()) {
    await queueNotification(chatId, opp, matchingProfiles, 'immediate', queue);
    return 'queued';
  }

  // Check rate limits
  const stats = await queue.getStats(chatId);
  if (stats.sentThisHour >= RATE_LIMITS.maxPerHour ||
    stats.sentToday >= RATE_LIMITS.maxPerDay) {
    await queueNotification(chatId, opp, matchingProfiles, 'digest', queue);
    return 'queued';
  }

  // Send immediately
  const success = await sendImmediateAlert(chatId, opp, matchingProfiles, env);

  if (success) {
    await queue.incrementStats(chatId);
    return 'sent';
  }

  return 'skipped';
}

/**
 * Queue a notification for later
 */
async function queueNotification(
  chatId: number,
  opp: Opportunity,
  matchingProfiles: WatchProfile[],
  priority: 'immediate' | 'digest',
  queue: NotificationQueue
): Promise<void> {
  const notification: QueuedNotification = {
    id: generateNotificationId(),
    chatId,
    opportunity: opp,
    matchedProfileIds: matchingProfiles.map(p => p.id),
    matchedProfileNames: matchingProfiles.map(p => p.name || p.id),
    priority,
    createdAt: new Date().toISOString(),
  };

  await queue.enqueue(notification);
}

/**
 * Send immediate HOT alert
 */
async function sendImmediateAlert(
  chatId: number,
  opp: Opportunity,
  matchingProfiles: WatchProfile[],
  env: Env
): Promise<boolean> {
  const profileNames = matchingProfiles.map(p => p.name || 'Watch Profile').join(', ');

  const message = `🔥 <b>NUOVO MATCH!</b>

⚽ <b>${escapeHtml(opp.player_name)}</b> (${opp.age})
${opp.role_name || opp.role} • ${opp.opportunity_type} • Score <b>${opp.ob1_score}</b>
${opp.current_club ? `📍 ${escapeHtml(opp.current_club)}` : ''}

📋 Match: <i>"${escapeHtml(profileNames)}"</i>

${opp.summary ? `💬 ${escapeHtml(opp.summary.substring(0, 100))}...` : ''}`;

  const keyboard = {
    inline_keyboard: [
      [
        { text: '📊 Dettagli', callback_data: `details_${opp.id}` },
        { text: '✅ Salva', callback_data: `save_${opp.id}` },
      ],
      [
        { text: '🌐 Dashboard', url: DASHBOARD_URL },
      ],
    ],
  };

  return await sendMessageWithKeyboard(env, chatId, message, keyboard);
}

/**
 * Send daily digest - formato professionale per DS
 */
export async function sendDailyDigest(
  chatId: number,
  entries: DigestEntry[],
  env: Env
): Promise<boolean> {
  if (entries.length === 0) return true;

  const today = new Date();
  const dateStr = today.toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' });

  // Raggruppa per ruolo
  const byRole: Record<string, DigestEntry[]> = {};
  entries.forEach(e => {
    const role = e.opportunity.role || 'Altro';
    if (!byRole[role]) byRole[role] = [];
    byRole[role].push(e);
  });

  // Sort by score
  const sorted = entries.sort((a, b) => b.opportunity.ob1_score - a.opportunity.ob1_score);
  const hotCount = sorted.filter(e => e.opportunity.ob1_score >= 80).length;

  let message = `📊 <b>OB1 SCOUT REPORT</b>
<i>${dateStr}</i>

━━━━━━━━━━━━━━━━━━━━

📈 <b>Riepilogo</b>
• ${entries.length} nuove opportunità
• ${hotCount} profili HOT (score 80+)
• ${Object.keys(byRole).length} ruoli coperti

`;

  // Top 3 opportunità
  message += `🏆 <b>TOP 3 DEL GIORNO</b>\n\n`;

  sorted.slice(0, 3).forEach((entry, i) => {
    const opp = entry.opportunity;
    const medal = i === 0 ? '🥇' : i === 1 ? '🥈' : '🥉';

    message += `${medal} <b>${escapeHtml(opp.player_name)}</b>
   ${opp.role_name || opp.role} • ${opp.age || '?'} anni • Score <b>${opp.ob1_score}</b>
   ${opp.current_club ? `📍 ${escapeHtml(opp.current_club)}` : ''}
   🏷️ ${(opp.opportunity_type || 'n.d.').toUpperCase()}
\n`;
  });

  // Breakdown per ruolo
  if (Object.keys(byRole).length > 1) {
    message += `━━━━━━━━━━━━━━━━━━━━
📋 <b>PER RUOLO</b>\n`;

    const roleEmojis: Record<string, string> = {
      'DC': '🛡️', 'TD': '🛡️', 'TS': '🛡️',
      'CC': '🎯', 'MED': '🎯', 'TRQ': '🎯',
      'AT': '⚽', 'ATT': '⚽', 'PC': '⚽',
      'PO': '🧤'
    };

    Object.entries(byRole)
      .sort((a, b) => b[1].length - a[1].length)
      .slice(0, 4)
      .forEach(([role, players]) => {
        const emoji = roleEmojis[role] || '📊';
        const topPlayer = players.sort((a, b) => b.opportunity.ob1_score - a.opportunity.ob1_score)[0];
        message += `${emoji} ${role}: ${players.length} • Top: ${topPlayer.opportunity.player_name}\n`;
      });
  }

  message += `
━━━━━━━━━━━━━━━━━━━━
💡 <i>Scrivi il nome di un giocatore per dettagli</i>
🌐 <a href="${DASHBOARD_URL}">Dashboard completa</a>`;

  return await sendMessage(env, chatId, message);
}

/**
 * Process queued notifications (called by cron)
 * Genera il digest giornaliero per tutti gli utenti registrati
 */
export async function processQueuedNotifications(env: Env): Promise<{
  immediate: number;
  digests: number;
}> {
  const notifQueue = getNotifQueue(env);
  const watchStorage = getWatchStorage(env);
  const users = await notifQueue.getActiveUsers();

  console.log(`Processing notifications for ${users.length} users`);

  let immediate = 0;
  let digests = 0;

  // Fetch current opportunities once
  const { fetchData } = await import('../data');
  const data = await fetchData(env);
  const opportunities = data?.opportunities || [];

  console.log(`Loaded ${opportunities.length} opportunities`);

  for (const chatId of users) {
    try {
      // Send queued immediate notifications
      const queued = await notifQueue.getQueued(chatId);
      for (const notif of queued.filter(n => n.priority === 'immediate')) {
        const success = await sendImmediateAlert(chatId, notif.opportunity, [], env);
        if (success) {
          await notifQueue.dequeue(chatId, notif.id);
          await notifQueue.incrementStats(chatId);
          immediate++;
        }
      }

      // Get user's watch profiles
      const profiles = await watchStorage.listProfiles(chatId);
      const activeProfiles = profiles.filter(p => p.active && p.include_in_digest);

      console.log(`User ${chatId}: ${activeProfiles.length} active profiles`);

      if (activeProfiles.length > 0 && opportunities.length > 0) {
        // Filter opportunities that match user's profiles
        const { filterByProfiles } = await import('../watch/matcher');
        const matches = filterByProfiles(opportunities, activeProfiles);

        console.log(`User ${chatId}: ${matches.length} matching opportunities`);

        if (matches.length > 0) {
          // Convert to digest entries
          const digestEntries: DigestEntry[] = matches.map(m => ({
            opportunity: m.opportunity,
            matchedProfiles: m.matchedProfiles.map(p => p.name || p.id),
          }));

          const success = await sendDailyDigest(chatId, digestEntries, env);
          if (success) {
            digests++;
            console.log(`Sent digest to user ${chatId} with ${digestEntries.length} entries`);
          }
        }
      }

      // Also check for pre-queued digest entries
      const queuedDigest = await notifQueue.getDigest(chatId);
      if (queuedDigest.length > 0) {
        const success = await sendDailyDigest(chatId, queuedDigest, env);
        if (success) {
          await notifQueue.clearDigest(chatId);
          if (digests === 0) digests++; // Don't double count
        }
      }

      // Reset hourly stats
      await notifQueue.resetHourlyStats(chatId);

    } catch (error) {
      console.error(`Error processing user ${chatId}:`, error);
    }
  }

  return { immediate, digests };
}

// Helper functions
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function getWatchStorage(env: Env): WatchStorage {
  if (env.USER_DATA) {
    return createKVStorage(env.USER_DATA);
  }
  return createMemoryStorage();
}

function getNotifQueue(env: Env): NotificationQueue {
  if (env.USER_DATA) {
    return createNotificationQueue(env.USER_DATA);
  }
  return createMemoryQueue();
}
