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
import { fetchDNAData, getMatchesForClub, getTopMatches, formatDNAMatchList, formatDNAStats, getAvailableClubs } from './dna';
import { isTalentSearchQuery, parseTalentQuery, searchTalents, formatTalentSearchResults } from './talent-search';
import { classifyWithLLM, convertToParseIntent } from './llm-classifier';
import { handleWatchCommand, handleWatchCallback } from './watch';

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

    // DNA-001: DNA Matching commands
    case '/dna':
    case '/match':
      await handleDNAMatch(chatId, args.join(' '), env);
      break;

    case '/talenti':
    case '/talents':
      await handleDNATopMatches(chatId, env);
      break;

    // SCORE-002: Watch Criteria commands
    case '/watch':
    case '/monitora':
      await handleWatchCommand(chatId, args, env);
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
  // DNA-001: Check FIRST if this is a "field search" query
  // e.g., "mi serve un terzino che spinga", "centrocampista box-to-box"
  if (isTalentSearchQuery(text)) {
    await handleTalentSearch(chatId, text, env);
    return;
  }

  let parsed = parseNaturalQuery(text);

  console.log(`NLP parsed: intent=${parsed.intent}, confidence=${parsed.confidence}, filters=`, parsed.filters);

  // NLP-002: If regex-based NLP is unsure, try LLM fallback
  if (parsed.confidence < 0.5 && parsed.intent === 'unknown' && env.AI) {
    console.log('Low confidence, trying LLM fallback...');

    const llmResult = await classifyWithLLM(env.AI, text);

    if (llmResult && llmResult.confidence > 0.6) {
      console.log(`LLM classified: intent=${llmResult.intent}, confidence=${llmResult.confidence}`);

      const converted = convertToParseIntent(llmResult);

      // Handle LLM-specific intents
      if (converted.intent === 'talent_search') {
        // LLM detected talent search - use talent-search module
        await handleTalentSearch(chatId, text, env);
        return;
      }

      // Update parsed with LLM result
      parsed = {
        intent: converted.intent as any,
        filters: { ...parsed.filters, ...converted.filters },
        confidence: converted.confidence,
        interpretation: llmResult.explanation,
      };
    }
  }

  // If still low confidence after LLM, show help
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

    // DNA-001: Natural language DNA queries
    case 'dna_top':
      await handleDNATopMatches(chatId, env);
      break;

    case 'dna_club':
      await handleDNAMatch(chatId, parsed.filters.query || '', env);
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

🧬 <b>DNA Matching:</b>
• "talenti dalle squadre B"
• "top talenti"
• "match per Pescara"

📊 <b>Info:</b>
• "quante opportunità ci sono?"
• "come funziona?"

Oppure usa i comandi:
/hot /warm /all /search /stats /talenti /dna /help`;
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

  try {
    // SCORE-002: Handle watch wizard callbacks
    if (data.startsWith('watch:')) {
      if (chatId && messageId) {
        await handleWatchCallback(chatId, messageId, callbackId, data, env);
      }
      return;
    }

    // Parse callback data for other actions
    const [action, ...params] = data.split('_');
    const oppId = params.join('_');

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

// ============================================================================
// DNA-001: DNA MATCHING HANDLERS
// ============================================================================

async function handleDNAMatch(chatId: number, clubQuery: string, env: Env): Promise<void> {
  const dnaData = await fetchDNAData();

  if (!dnaData) {
    await sendMessage(env, chatId, '❌ Dati DNA non disponibili. Riprova più tardi.');
    return;
  }

  // If no club specified, show available clubs
  if (!clubQuery || clubQuery.trim().length === 0) {
    const clubs = getAvailableClubs(dnaData);
    const clubList = clubs.map(c => `• <code>${c}</code>`).join('\n');

    await sendMessage(env, chatId, `🧬 <b>DNA Matching</b>

Uso: /dna &lt;club&gt;

<b>Club disponibili:</b>
${clubList}

Esempio: <code>/dna pescara</code>`);
    return;
  }

  // Find club (case insensitive partial match)
  const searchTerm = clubQuery.toLowerCase().trim();
  const clubs = getAvailableClubs(dnaData);
  const matchedClub = clubs.find(c => c.toLowerCase().includes(searchTerm));

  if (!matchedClub) {
    await sendMessage(env, chatId, `❌ Club "${clubQuery}" non trovato.

<b>Club disponibili:</b>
${clubs.map(c => `• <code>${c}</code>`).join('\n')}`);
    return;
  }

  // Get matches for this club
  const matches = getMatchesForClub(dnaData, matchedClub, 5);

  // Find club name from first match
  const clubName = matches.length > 0 ? matches[0].club_name : matchedClub;

  const message = formatDNAMatchList(
    matches,
    `🧬 <b>DNA Matches</b>`,
    clubName
  );

  await sendMessage(env, chatId, message);
}

async function handleDNATopMatches(chatId: number, env: Env): Promise<void> {
  const dnaData = await fetchDNAData();

  if (!dnaData) {
    await sendMessage(env, chatId, '❌ Dati DNA non disponibili. Riprova più tardi.');
    return;
  }

  // Get top matches globally (min 75% score)
  const topMatches = getTopMatches(dnaData, 75, 8);

  if (topMatches.length === 0) {
    await sendMessage(env, chatId, `🏆 <b>Top Talenti</b>

Nessun match con score > 75% al momento.

Prova /dna &lt;club&gt; per vedere tutti i match.`);
    return;
  }

  const message = formatDNAMatchList(
    topMatches,
    `🏆 <b>TOP TALENTI - Best Matches</b>

Giocatori delle squadre B con il miglior fit per i club di Serie C:`
  );

  await sendMessage(env, chatId, message);

  // Also show stats
  const statsMessage = formatDNAStats(dnaData);
  await sendMessage(env, chatId, statsMessage);
}

// ============================================================================
// DNA-001: TALENT SEARCH ("Field Language" Queries)
// ============================================================================

async function handleTalentSearch(chatId: number, text: string, env: Env): Promise<void> {
  console.log(`Talent search query: "${text}"`);

  const query = parseTalentQuery(text);

  if (!query) {
    // Fallback: non siamo riusciti a parsare, prova con help
    await sendMessage(env, chatId, formatTalentSearchHelp());
    return;
  }

  console.log(`Parsed talent query:`, query);

  const dnaData = await fetchDNAData();

  if (!dnaData) {
    await sendMessage(env, chatId, '❌ Dati talenti non disponibili. Riprova più tardi.');
    return;
  }

  const results = searchTalents(dnaData, query, 5);
  const message = formatTalentSearchResults(results, query);

  await sendMessage(env, chatId, message);
}

function formatTalentSearchHelp(): string {
  return `⚽ <b>Cerca Talenti</b>

Dimmi che tipo di giocatore ti serve:

🏃 <b>Per ruolo + caratteristica:</b>
• "mi serve un terzino che spinga"
• "centrocampista box-to-box"
• "ala veloce"
• "difensore bravo in impostazione"

📊 <b>Caratteristiche:</b>
• veloce, tecnico, fisico, forte
• che pressa, aggressivo
• che imposta, intelligente
• box-to-box, tutta fascia

🎂 <b>Età:</b>
• giovane, under 21, under 23

<i>Es: "mi serve un centrocampista giovane che sappia pressare"</i>`;
}
