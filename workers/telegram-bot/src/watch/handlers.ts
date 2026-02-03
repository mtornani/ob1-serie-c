/**
 * SCORE-002: Watch Criteria System - Command Handlers
 */

import { Env, Opportunity } from '../types';
import { sendMessage, sendMessageWithKeyboard, editMessageText, answerCallbackQuery } from '../telegram';
import { fetchData } from '../data';
import { WatchStorage, createKVStorage, createMemoryStorage } from './storage';
import { WatchProfile } from './types';
import { createNotificationQueue, createMemoryQueue } from '../notifications/queue';
import {
  createInitialWizardState,
  getWizardStepContent,
  processWizardCallback,
  formatProfileList,
  formatSaveSuccess,
} from './wizard';
import { filterByProfiles } from './matcher';

// Global storage instance (initialized on first use)
let storage: WatchStorage | null = null;

function getStorage(env: Env): WatchStorage {
  if (!storage) {
    // Use KV if available, otherwise memory (for testing)
    if ((env as any).USER_DATA) {
      storage = createKVStorage((env as any).USER_DATA);
    } else {
      console.warn('KV not available, using memory storage');
      storage = createMemoryStorage();
    }
  }
  return storage;
}

/**
 * Handle /watch command
 */
export async function handleWatchCommand(
  chatId: number,
  args: string[],
  env: Env
): Promise<void> {
  const store = getStorage(env);
  const subcommand = args[0]?.toLowerCase();

  switch (subcommand) {
    case 'add':
      await handleWatchAdd(chatId, env, store);
      break;

    case 'remove':
    case 'delete':
      await handleWatchRemove(chatId, args.slice(1), env, store);
      break;

    case 'test':
      await handleWatchTest(chatId, args.slice(1), env, store);
      break;

    default:
      await handleWatchList(chatId, env, store);
      break;
  }
}

/**
 * List all watch profiles
 */
async function handleWatchList(
  chatId: number,
  env: Env,
  store: WatchStorage
): Promise<void> {
  const profiles = await store.listProfiles(chatId);
  const message = formatProfileList(profiles);
  await sendMessage(env, chatId, message);
}

/**
 * Start the add wizard
 */
async function handleWatchAdd(
  chatId: number,
  env: Env,
  store: WatchStorage
): Promise<void> {
  // Check max profiles (limit to 5 for free tier)
  const existing = await store.listProfiles(chatId);
  if (existing.length >= 5) {
    await sendMessage(env, chatId, `⚠️ Hai già 5 profili attivi (limite massimo).

Rimuovine uno con /watch remove <id> per crearne di nuovi.`);
    return;
  }

  // Create initial wizard state
  const state = createInitialWizardState();
  await store.saveWizardState(chatId, state);

  // Send first step
  const { message, keyboard } = getWizardStepContent(state);
  await sendMessageWithKeyboard(env, chatId, message, keyboard);
}

/**
 * Remove a watch profile
 */
async function handleWatchRemove(
  chatId: number,
  args: string[],
  env: Env,
  store: WatchStorage
): Promise<void> {
  if (args.length === 0) {
    await sendMessage(env, chatId, `❌ Specifica l'ID del profilo da rimuovere.

Usa /watch per vedere i tuoi profili con i relativi ID.`);
    return;
  }

  const profileIdPartial = args[0];
  const profiles = await store.listProfiles(chatId);

  // Find profile by partial ID match
  const profile = profiles.find(p =>
    p.id.startsWith(profileIdPartial) || p.id.includes(profileIdPartial)
  );

  if (!profile) {
    await sendMessage(env, chatId, `❌ Profilo non trovato: ${profileIdPartial}

Usa /watch per vedere i tuoi profili.`);
    return;
  }

  const deleted = await store.deleteProfile(chatId, profile.id);

  if (deleted) {
    await sendMessage(env, chatId, `✅ Profilo rimosso: <b>${profile.name || profile.id}</b>

/watch per vedere i profili rimanenti.`);
  } else {
    await sendMessage(env, chatId, `❌ Errore nella rimozione del profilo.`);
  }
}

/**
 * Test a watch profile against current opportunities
 */
async function handleWatchTest(
  chatId: number,
  args: string[],
  env: Env,
  store: WatchStorage
): Promise<void> {
  const profiles = await store.listProfiles(chatId);

  if (profiles.length === 0) {
    await sendMessage(env, chatId, `📋 Non hai profili da testare.

Usa /watch add per crearne uno.`);
    return;
  }

  // If profile ID specified, test only that one
  let profilesToTest = profiles;
  if (args.length > 0) {
    const profile = profiles.find(p =>
      p.id.startsWith(args[0]) || p.id.includes(args[0])
    );
    if (profile) {
      profilesToTest = [profile];
    }
  }

  // Fetch current opportunities
  const data = await fetchData(env);
  if (!data?.opportunities) {
    await sendMessage(env, chatId, `❌ Impossibile caricare le opportunità.`);
    return;
  }

  // Filter by profiles
  const matches = filterByProfiles(data.opportunities, profilesToTest);

  if (matches.length === 0) {
    await sendMessage(env, chatId, `🔍 <b>Test Watch Profile</b>

Nessuna opportunità attuale matcha i tuoi criteri.

Verrai notificato quando ne troveremo!`);
    return;
  }

  // Format results
  let message = `🔍 <b>Test Watch Profile</b>

${matches.length} opportunità matchano i tuoi criteri:\n\n`;

  const top5 = matches.slice(0, 5);
  top5.forEach(({ opportunity: opp, matchedProfiles }) => {
    const emoji = opp.classification === 'hot' ? '🔥' :
      opp.classification === 'warm' ? '⚡' : '📊';

    message += `${emoji} <b>${opp.player_name}</b> (${opp.age})\n`;
    message += `   ${opp.role} • ${opp.opportunity_type} • Score ${opp.ob1_score}\n`;
    message += `   Match: ${matchedProfiles.map(p => p.name || p.id.substring(0, 6)).join(', ')}\n\n`;
  });

  if (matches.length > 5) {
    message += `<i>... e altre ${matches.length - 5} opportunità</i>`;
  }

  await sendMessage(env, chatId, message);
}

/**
 * Handle wizard callback (inline keyboard clicks)
 */
export async function handleWatchCallback(
  chatId: number,
  messageId: number,
  callbackId: string,
  data: string,
  env: Env
): Promise<void> {
  const store = getStorage(env);

  // Parse callback data: watch:action:value
  const parts = data.split(':');
  if (parts.length < 3) {
    await answerCallbackQuery(env, callbackId, '❌ Errore');
    return;
  }

  const [, action, value] = parts;

  // Get current wizard state
  const state = await store.getWizardState(chatId);
  if (!state) {
    await answerCallbackQuery(env, callbackId, '⚠️ Sessione scaduta');
    await sendMessage(env, chatId, `⚠️ La sessione è scaduta. Usa /watch add per ricominciare.`);
    return;
  }

  // Process callback
  const { newState, completed, cancelled } = processWizardCallback(state, action, value);

  if (cancelled) {
    await store.clearWizardState(chatId);
    await answerCallbackQuery(env, callbackId, '❌ Annullato');
    await editMessageText(env, chatId, messageId, '❌ Creazione profilo annullata.\n\n/watch per vedere i profili esistenti.');
    return;
  }

  if (completed && newState) {
    // Save the profile
    const profile: WatchProfile = {
      id: newState.profile.id!,
      name: newState.profile.name || 'Watch Profile',
      roles: newState.profile.roles,
      opportunity_types: newState.profile.opportunity_types,
      age_max: newState.profile.age_max,
      min_ob1_score: newState.profile.min_ob1_score,
      alert_immediately: true,
      include_in_digest: true,
      active: true,
      created_at: newState.profile.created_at!,
      updated_at: new Date().toISOString(),
    };

    await store.saveProfile(chatId, profile);
    await store.clearWizardState(chatId);

    // Registra l'utente per ricevere notifiche
    await registerUserForNotifications(chatId, env);

    await answerCallbackQuery(env, callbackId, '✅ Salvato!');
    await editMessageText(env, chatId, messageId, formatSaveSuccess(profile));
    return;
  }

  if (newState) {
    // Save updated state and show next step
    await store.saveWizardState(chatId, newState);

    const { message, keyboard } = getWizardStepContent(newState);
    await answerCallbackQuery(env, callbackId, '✅');

    // Edit message with new content
    await editMessageWithKeyboard(env, chatId, messageId, message, keyboard);
  }
}

/**
 * Edit message with inline keyboard
 */
async function editMessageWithKeyboard(
  env: Env,
  chatId: number,
  messageId: number,
  text: string,
  keyboard: any
): Promise<void> {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/editMessageText`;

  await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: chatId,
      message_id: messageId,
      text,
      parse_mode: 'HTML',
      reply_markup: keyboard,
    }),
  });
}

/**
 * Register user for notifications when they create a watch profile
 */
async function registerUserForNotifications(chatId: number, env: Env): Promise<void> {
  const queue = env.USER_DATA
    ? createNotificationQueue(env.USER_DATA)
    : createMemoryQueue();
  await queue.registerUser(chatId);
  console.log(`Registered user ${chatId} for notifications`);
}
