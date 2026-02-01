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
 * Send daily digest
 */
export async function sendDailyDigest(
  chatId: number,
  entries: DigestEntry[],
  env: Env
): Promise<boolean> {
  if (entries.length === 0) return true;

  let message = `📬 <b>Il tuo digest giornaliero</b>

Abbiamo trovato ${entries.length} opportunità che matchano i tuoi criteri:\n\n`;

  // Sort by score
  const sorted = entries.sort((a, b) => b.opportunity.ob1_score - a.opportunity.ob1_score);

  // Show top 5
  sorted.slice(0, 5).forEach((entry, i) => {
    const opp = entry.opportunity;
    const emoji = opp.ob1_score >= 80 ? '🔥' : opp.ob1_score >= 60 ? '⚡' : '📊';

    message += `${emoji} <b>${escapeHtml(opp.player_name)}</b> (${opp.age})
   ${opp.role_name || opp.role} • ${opp.opportunity_type} • Score ${opp.ob1_score}
   Match: <i>${entry.matchedProfiles.slice(0, 2).join(', ')}</i>\n\n`;
  });

  if (entries.length > 5) {
    message += `<i>... e altre ${entries.length - 5} opportunità</i>\n\n`;
  }

  message += `━━━━━━━━━━━━━━━━━━━━
🌐 <a href="${DASHBOARD_URL}">Apri Dashboard per dettagli</a>`;

  return await sendMessage(env, chatId, message);
}

/**
 * Process queued notifications (called by cron)
 */
export async function processQueuedNotifications(env: Env): Promise<{
  immediate: number;
  digests: number;
}> {
  const notifQueue = getNotifQueue(env);
  const users = await notifQueue.getActiveUsers();

  let immediate = 0;
  let digests = 0;

  for (const chatId of users) {
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

    // Send digest
    const digestEntries = await notifQueue.getDigest(chatId);
    if (digestEntries.length > 0) {
      const success = await sendDailyDigest(chatId, digestEntries, env);
      if (success) {
        await notifQueue.clearDigest(chatId);
        digests++;
      }
    }

    // Reset hourly stats
    await notifQueue.resetHourlyStats(chatId);
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
