import { Env, TelegramMessage, TelegramCallbackQuery, Opportunity } from './types';
import { sendMessage, answerCallbackQuery, editMessageText } from './telegram';
import { fetchData, filterHot, filterWarm, searchOpportunities, getStats, findOpportunityById, filterOpportunities } from './data';
import {
  formatOpportunityList,
  formatStats,
  formatWelcome,
  formatHelp,
  formatError,
  formatUnknownCommand,
  formatNoResults,
  formatOpportunityDetails,
} from './formatters';
import { parseNaturalQuery, getInterpretationMessage, ParsedIntent } from './nlp';

export async function handleMessage(message: TelegramMessage, env: Env): Promise<void> {
  const chatId = message.chat.id;
  const text = message.text?.trim() || '';

  if (!text) return;

  console.log(`Received message: "${text}" from chat ${chatId}`);

  try {
    // Check for explicit commands first
    if (text.startsWith('/')) {
      await handleCommand(chatId, text, env);
      return;
    }

    // NLP-001: Parse natural language query
    await handleNaturalQuery(chatId, text, env);

  } catch (error) {
    console.error('Error handling message:', error);
    await sendMessage(env, chatId, formatError());
  }
}

// ============================================================================
// COMMAND HANDLERS (explicit /commands)
// ============================================================================

async function handleCommand(chatId: number, text: string, env: Env): Promise<void> {
  const [command, ...args] = text.split(/\s+/);
  const lowerCommand = command.toLowerCase();

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
      await sendMessage(env, chatId, formatUnknownCommand());
      break;
  }
}

async function handleStart(chatId: number, env: Env): Promise<void> {
  await sendMessage(env, chatId, formatWelcome(env));
}

async function handleHelp(chatId: number, env: Env): Promise<void> {
  await sendMessage(env, chatId, formatHelp(env));
}

async function handleHot(chatId: number, env: Env, limit: number = 5): Promise<void> {
  const data = await fetchData(env);

  if (!data || !data.opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  const hotOpportunities = filterHot(data.opportunities);
  const message = formatOpportunityList(hotOpportunities, '🔥 <b>Giocatori HOT</b> (Score 80+)', limit);

  await sendMessage(env, chatId, message);
}

async function handleWarm(chatId: number, env: Env, limit: number = 5): Promise<void> {
  const data = await fetchData(env);

  if (!data || !data.opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  const warmOpportunities = filterWarm(data.opportunities);
  const message = formatOpportunityList(warmOpportunities, '⚡ <b>Giocatori WARM</b> (Score 60-79)', limit);

  await sendMessage(env, chatId, message);
}

async function handleAll(chatId: number, env: Env, limit: number = 8): Promise<void> {
  const data = await fetchData(env);

  if (!data || !data.opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  const sorted = [...data.opportunities].sort((a, b) => b.ob1_score - a.ob1_score);
  const message = formatOpportunityList(sorted, '📋 <b>Tutte le Opportunita</b>', limit);

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

// ============================================================================
// NLP-001: NATURAL LANGUAGE HANDLER
// ============================================================================

async function handleNaturalQuery(chatId: number, text: string, env: Env): Promise<void> {
  const parsed = parseNaturalQuery(text);

  console.log(`NLP parsed: intent=${parsed.intent}, confidence=${parsed.confidence}, filters=`, parsed.filters);

  // If confidence is too low, ask for clarification
  if (parsed.confidence < 0.3 && parsed.intent === 'unknown') {
    await sendMessage(env, chatId, formatNLPHelp());
    return;
  }

  const data = await fetchData(env);

  if (!data || !data.opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  const limit = parsed.filters.limit || 5;

  switch (parsed.intent) {
    case 'help':
      await handleHelp(chatId, env);
      break;

    case 'stats':
      await handleStats(chatId, env);
      break;

    case 'list_hot':
      await handleFilteredQuery(chatId, data.opportunities, parsed, '🔥 <b>Migliori opportunità</b>', { ...parsed.filters, minScore: 80 }, limit, env);
      break;

    case 'list_warm':
      await handleFilteredQuery(chatId, data.opportunities, parsed, '⚡ <b>Opportunità interessanti</b>', { ...parsed.filters, minScore: 60, maxScore: 79 }, limit, env);
      break;

    case 'list_all':
      await handleFilteredQuery(chatId, data.opportunities, parsed, '📋 <b>Tutte le opportunità</b>', parsed.filters, Math.min(limit, 10), env);
      break;

    case 'search':
      await handleFilteredQuery(chatId, data.opportunities, parsed, null, parsed.filters, limit, env);
      break;

    default:
      await sendMessage(env, chatId, formatNLPHelp());
      break;
  }
}

async function handleFilteredQuery(
  chatId: number,
  opportunities: Opportunity[],
  parsed: ParsedIntent,
  defaultTitle: string | null,
  filters: any,
  limit: number,
  env: Env
): Promise<void> {
  const results = filterOpportunities(opportunities, filters);

  // Build title based on interpretation
  let title = defaultTitle;
  if (parsed.interpretation && !defaultTitle) {
    title = `🔍 <b>Risultati per: ${parsed.interpretation}</b>`;
  } else if (parsed.interpretation && defaultTitle) {
    title = `${defaultTitle}\n<i>${parsed.interpretation}</i>`;
  }

  if (!title) {
    title = '🔍 <b>Risultati ricerca</b>';
  }

  if (results.length === 0) {
    const noResultMsg = parsed.interpretation
      ? formatNoResults(parsed.interpretation)
      : '😔 Nessun risultato trovato.\n\nProva con criteri diversi!';
    await sendMessage(env, chatId, noResultMsg);
    return;
  }

  const message = formatOpportunityList(results, title, limit);
  await sendMessage(env, chatId, message);
}

function formatNLPHelp(): string {
  return `🤖 <b>Non ho capito bene...</b>

Puoi chiedermi cose come:

📋 <b>Liste:</b>
• "mostrami i migliori"
• "chi sono i più interessanti?"
• "dammi la lista completa"

🔍 <b>Ricerche:</b>
• "centrocampisti svincolati"
• "attaccanti under 25"
• "difensori in prestito"
• "cerca Rossi"

📊 <b>Info:</b>
• "quante opportunità ci sono?"
• "come funziona?"

Oppure usa i comandi:
/hot /warm /all /search /stats /help`;
}

// ============================================================================
// CALLBACK QUERY HANDLER (NOTIF-001)
// ============================================================================

export async function handleCallbackQuery(callback: TelegramCallbackQuery, env: Env): Promise<void> {
  const callbackId = callback.id;
  const data = callback.data || '';
  const chatId = callback.message?.chat.id;
  const messageId = callback.message?.message_id;

  console.log(`Callback query: ${data} from chat ${chatId}`);

  // Parse callback data
  const [action, ...params] = data.split('_');
  const oppId = params.join('_');

  try {
    switch (action) {
      case 'save':
        // For now, just acknowledge - watchlist feature coming soon
        await answerCallbackQuery(env, callbackId, '✅ Salvato! (Watchlist in arrivo)');
        break;

      case 'ignore':
        // For now, just acknowledge - ignore list feature coming soon
        await answerCallbackQuery(env, callbackId, '❌ Ignorato! (Non vedrai piu questo alert)');
        break;

      case 'details':
        // Show full score breakdown
        await handleDetailsCallback(env, callbackId, chatId!, oppId);
        break;

      default:
        await answerCallbackQuery(env, callbackId, '❓ Azione non riconosciuta');
    }
  } catch (error) {
    console.error('Callback error:', error);
    await answerCallbackQuery(env, callbackId, '⚠️ Errore, riprova');
  }
}

async function handleDetailsCallback(env: Env, callbackId: string, chatId: number, oppId: string): Promise<void> {
  // Acknowledge callback
  await answerCallbackQuery(env, callbackId, '📊 Caricamento dettagli...');

  // Fetch data and find opportunity
  const dashboardData = await fetchData(env);

  if (!dashboardData || !dashboardData.opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  const opp = findOpportunityById(dashboardData.opportunities, oppId);

  if (!opp) {
    await sendMessage(env, chatId, '❌ Opportunita non trovata');
    return;
  }

  // Send detailed message
  const message = formatOpportunityDetails(opp);
  await sendMessage(env, chatId, message);
}
