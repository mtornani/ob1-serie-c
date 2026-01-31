import { Env, TelegramMessage } from './types';
import { sendMessage } from './telegram';
import { fetchData, filterHot, filterWarm, searchOpportunities, getStats } from './data';
import {
  formatOpportunityList,
  formatStats,
  formatWelcome,
  formatHelp,
  formatError,
  formatUnknownCommand,
  formatNoResults,
} from './formatters';

export async function handleMessage(message: TelegramMessage, env: Env): Promise<void> {
  const chatId = message.chat.id;
  const text = message.text?.trim() || '';

  // Parse command
  const [command, ...args] = text.split(/\s+/);
  const lowerCommand = command.toLowerCase();

  console.log(`Received command: ${command} from chat ${chatId}`);

  try {
    switch (lowerCommand) {
      case '/start':
        await handleStart(chatId, env);
        break;

      case '/help':
        await handleHelp(chatId, env);
        break;

      case '/hot':
        await handleHot(chatId, env);
        break;

      case '/warm':
        await handleWarm(chatId, env);
        break;

      case '/all':
        await handleAll(chatId, env);
        break;

      case '/search':
        await handleSearch(chatId, args.join(' '), env);
        break;

      case '/stats':
        await handleStats(chatId, env);
        break;

      default:
        // Check if it looks like a command
        if (text.startsWith('/')) {
          await sendMessage(env, chatId, formatUnknownCommand());
        }
        // Ignore non-command messages
        break;
    }
  } catch (error) {
    console.error('Error handling message:', error);
    await sendMessage(env, chatId, formatError());
  }
}

async function handleStart(chatId: number, env: Env): Promise<void> {
  await sendMessage(env, chatId, formatWelcome(env));
}

async function handleHelp(chatId: number, env: Env): Promise<void> {
  await sendMessage(env, chatId, formatHelp(env));
}

async function handleHot(chatId: number, env: Env): Promise<void> {
  const data = await fetchData(env);

  if (!data || !data.opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  const hotOpportunities = filterHot(data.opportunities);
  const message = formatOpportunityList(hotOpportunities, '🔥 <b>Giocatori HOT</b> (Score 80+)', 5);

  await sendMessage(env, chatId, message);
}

async function handleWarm(chatId: number, env: Env): Promise<void> {
  const data = await fetchData(env);

  if (!data || !data.opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  const warmOpportunities = filterWarm(data.opportunities);
  const message = formatOpportunityList(warmOpportunities, '⚡ <b>Giocatori WARM</b> (Score 60-79)', 5);

  await sendMessage(env, chatId, message);
}

async function handleAll(chatId: number, env: Env): Promise<void> {
  const data = await fetchData(env);

  if (!data || !data.opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  const sorted = [...data.opportunities].sort((a, b) => b.ob1_score - a.ob1_score);
  const message = formatOpportunityList(sorted, '📋 <b>Tutte le Opportunita</b>', 8);

  await sendMessage(env, chatId, message);
}

async function handleSearch(chatId: number, query: string, env: Env): Promise<void> {
  if (!query || query.trim().length < 2) {
    await sendMessage(env, chatId, `🔍 <b>Ricerca giocatore</b>\n\nUso: /search &lt;nome&gt;\n\nEsempio: /search Viola`);
    return;
  }

  const data = await fetchData(env);

  if (!data || !data.opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  const results = searchOpportunities(data.opportunities, query);

  if (results.length === 0) {
    await sendMessage(env, chatId, formatNoResults(query));
    return;
  }

  const message = formatOpportunityList(results, `🔍 <b>Risultati per "${query}"</b>`, 5);
  await sendMessage(env, chatId, message);
}

async function handleStats(chatId: number, env: Env): Promise<void> {
  const data = await fetchData(env);

  if (!data || !data.opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  const stats = getStats(data.opportunities);
  const message = formatStats(stats, data.last_update);

  await sendMessage(env, chatId, message);
}
