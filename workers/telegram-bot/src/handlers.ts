import { Env, TelegramMessage, TelegramCallbackQuery, Opportunity } from './types';
import { sendMessage, answerCallbackQuery, editMessageText, getFile, downloadFileAsBase64 } from './telegram';
import { fetchData, filterHot, filterWarm, searchOpportunities as searchByName, getStats, findOpportunityById, filterOpportunities } from './data';
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
import { handleWatchCommand, handleWatchCallback } from './watch';
import { handleSmartSearch, handleSearchCallback } from './smart-search';
import { handleVoiceMessage } from './conversational';

export async function handleMessage(message: TelegramMessage, env: Env): Promise<void> {
  const chatId = message.chat.id;

  try {
    // Handle voice messages (audio from DS)
    if (message.voice || message.audio) {
      console.log(`Received voice/audio message from chat ${chatId}`);
      await handleVoiceMessageWrapper(chatId, message, env);
      return;
    }

    const text = message.text?.trim() || '';
    if (!text) return;

    console.log(`Received message: "${text}" from chat ${chatId}`);

    // Check for explicit commands first
    if (text.startsWith('/')) {
      await handleCommand(chatId, text, env);
      return;
    }

    // SMART SEARCH: Cerca nelle opportunità REALI
    await handleSmartSearch(chatId, text, env);

  } catch (error) {
    console.error('Error handling message:', error);
    await sendMessage(env, chatId, formatError());
  }
}

/**
 * Handle voice/audio messages
 */
async function handleVoiceMessageWrapper(chatId: number, message: TelegramMessage, env: Env): Promise<void> {
  const fileId = message.voice?.file_id || message.audio?.file_id;
  if (!fileId) {
    await sendMessage(env, chatId, '❌ Impossibile elaborare il messaggio vocale.');
    return;
  }

  // Check if OpenRouter is configured
  if (!env.OPENROUTER_API_KEY) {
    await sendMessage(env, chatId, '🎤 Ho ricevuto il tuo messaggio vocale, ma la funzione audio non è ancora attiva.\n\nPer ora, scrivimi cosa ti serve!');
    return;
  }

  // Send "processing" message
  await sendMessage(env, chatId, '🎤 Sto ascoltando...');

  // Get file path from Telegram
  const filePath = await getFile(env, fileId);
  if (!filePath) {
    await sendMessage(env, chatId, '❌ Impossibile scaricare il file audio.');
    return;
  }

  // Download file as base64
  const audioBase64 = await downloadFileAsBase64(env, filePath);
  if (!audioBase64) {
    await sendMessage(env, chatId, '❌ Impossibile elaborare il file audio.');
    return;
  }

  // Get mime type
  const mimeType = message.voice?.mime_type || message.audio?.mime_type || 'audio/ogg';

  // Process with OpenRouter/Gemma
  const handled = await handleVoiceMessage(chatId, audioBase64, mimeType, env);

  if (!handled) {
    await sendMessage(env, chatId, '❌ Non sono riuscito a capire il messaggio vocale. Prova a scrivermi!');
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

    // NOTIF-002: Notification settings
    case '/digest':
      await handleDigestPreview(chatId, env);
      break;

    // Report on-demand
    case '/report':
      await handleReport(chatId, env);
      break;

    // SCOUT-001: Interactive Scout Wizard
    case '/scout':
    case '/wizard':
    case '/aiutami':
      await startScoutWizard(chatId, env);
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
  // SCOUT-001: Check if user wants guided help (Akinator-style wizard)
  if (shouldTriggerWizard(text)) {
    await startScoutWizard(chatId, env);
    return;
  }

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

  // If still low confidence after Cloudflare AI, try OpenRouter conversational
  if (parsed.confidence < 0.3 && parsed.intent === 'unknown') {
    // Try conversational handler (OpenRouter) - more powerful and can ask clarifying questions
    if (env.OPENROUTER_API_KEY) {
      console.log('Trying OpenRouter conversational handler...');
      const handled = await handleConversationalMessage(chatId, text, env);
      if (handled) {
        return;
      }
    }

    // Final fallback: show help
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

    // SCORE-002: Create watch profile via natural language
    case 'create_watch':
      await handleNaturalWatchCreate(chatId, parsed, env);
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

  // Add warning if present (e.g., nationality data limited)
  let warningMsg = '';
  if (parsed.warning) {
    warningMsg = `\n⚠️ <i>${parsed.warning}</i>\n`;
  }

  if (results.length === 0) {
    let noResultMsg = parsed.interpretation
      ? formatNoResults(parsed.interpretation)
      : '😔 Nessun risultato trovato.\n\nProva con criteri diversi!';

    // If we have filters for nationality but no results, explain why
    if (parsed.filters.nationality || parsed.filters.requiresEUPassport) {
      noResultMsg = `😔 <b>Nessun risultato trovato</b>

Ho capito che cerchi: <i>${parsed.interpretation || 'giocatori con specifiche nazionalità'}</i>

⚠️ <b>Nota:</b> Al momento il database non ha ancora i dati di nazionalità per tutti i giocatori. Stiamo lavorando per arricchire i profili con dati da Transfermarkt.

Nel frattempo, posso mostrarti:
• /hot - migliori opportunità
• /all - lista completa
• /dna pescara - match per un club specifico`;
    }

    await sendMessage(env, chatId, noResultMsg);
    return;
  }

  let message = formatOpportunityList(results, title, limit);
  if (warningMsg) {
    message = warningMsg + message;
  }

  // NLP-003: Inject AI Scout Persona commentary if available and coming from NLP
  if (parsed.interpretation && env.AI) {
    // Generate AI comment
    const aiComment = await generateScoutResponse(env.AI, parsed.interpretation, results, 'market');
    
    if (aiComment) {
      // Prepend AI comment to the message
      const fullMessage = `🗣️ <b>OB1 Scout:</b>\n<i>"${aiComment}"</i>\n\n${message}`;
      await sendMessage(env, chatId, fullMessage);
      return;
    }
  }

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
/hot /warm /all /search /stats /talenti /dna /help

🎯 <b>Nuovo!</b> Scrivi /scout per un aiuto guidato stile Akinator!`;
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

    // SCOUT-001: Handle scout wizard callbacks
    if (data.startsWith('scout:')) {
      if (chatId && messageId) {
        await handleWizardCallback(chatId, messageId, callbackId, data, env);
      }
      return;
    }

    // Smart Search: Handle search suggestion callbacks
    if (data.startsWith('search:')) {
      if (chatId) {
        await answerCallbackQuery(env, callbackId, '');
        await handleSearchCallback(chatId, data, env);
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
  const opportunities = await fetchDNAData(env);

  if (!opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  // If no club specified, show examples
  if (!clubQuery || clubQuery.trim().length === 0) {
    await sendMessage(env, chatId, `🧬 <b>DNA Matching</b>

Uso: /dna &lt;club&gt;

Esempio: <code>/dna pescara</code>

Ti mostrerò i giocatori più adatti per il club richiesto basandomi sulle opportunità di mercato attuali.`);
    return;
  }

  // Get matches for this club
  const matches = getMatchesForClub(opportunities, clubQuery, 5);

  const message = formatDNAMatchList(
    matches,
    `🧬 <b>DNA Matches</b>`,
    clubQuery
  );

  // NLP-003: Inject AI DNA analysis if available
  if (env.AI) {
    const aiComment = await generateDNAResponse(env.AI, clubQuery, matches);

    if (aiComment) {
      const fullMessage = `🗣️ <b>OB1 Scout:</b>\n<i>"${aiComment}"</i>\n\n${message}`;
      await sendMessage(env, chatId, fullMessage);
      return;
    }
  }

  await sendMessage(env, chatId, message);
}

async function handleDNATopMatches(chatId: number, env: Env): Promise<void> {
  const opportunities = await fetchDNAData(env);

  if (!opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  // Get top matches (young players with high score)
  const topMatches = getTopMatches(opportunities, 75, 8);

  if (topMatches.length === 0) {
    await sendMessage(env, chatId, `🏆 <b>Top Talenti</b>

Nessun talento Under 23 con score > 75% al momento.`);
    return;
  }

  const message = formatDNAMatchList(
    topMatches,
    `🏆 <b>TOP TALENTI - Best Prospects</b>

Giovani talenti (Under 23) più interessanti monitorati da OB1 Radar:`
  );

  await sendMessage(env, chatId, message);

  // Also show stats
  const statsMessage = formatDNAStats(opportunities);
  await sendMessage(env, chatId, statsMessage);
}

// ============================================================================
// NOTIF-002: DIGEST PREVIEW
// ============================================================================

async function handleDigestPreview(chatId: number, env: Env): Promise<void> {
  const { createKVStorage, createMemoryStorage } = await import('./watch/storage');
  const { filterByProfiles } = await import('./watch/matcher');
  const { sendDailyDigest } = await import('./notifications/sender');

  // Get user's profiles
  const watchStorage = env.USER_DATA ? createKVStorage(env.USER_DATA) : createMemoryStorage();
  const profiles = await watchStorage.listProfiles(chatId);

  if (profiles.length === 0) {
    await sendMessage(env, chatId, `📬 <b>Anteprima Digest</b>

Non hai profili di monitoraggio attivi.

Usa /watch add per crearne uno e ricevere il digest giornaliero con le opportunità che matchano i tuoi criteri.`);
    return;
  }

  // Fetch current opportunities
  const data = await fetchData(env);
  if (!data?.opportunities) {
    await sendMessage(env, chatId, '❌ Impossibile caricare le opportunità.');
    return;
  }

  // Filter by profiles
  const matches = filterByProfiles(data.opportunities, profiles.filter(p => p.active));

  if (matches.length === 0) {
    await sendMessage(env, chatId, `📬 <b>Anteprima Digest</b>

Nessuna opportunità attuale matcha i tuoi ${profiles.length} profili.

Verrai notificato quando ne troveremo!`);
    return;
  }

  // Convert to digest format and send
  const digestEntries = matches.map(m => ({
    opportunity: m.opportunity,
    matchedProfiles: m.matchedProfiles.map(p => p.name || p.id),
  }));

  await sendDailyDigest(chatId, digestEntries, env);
}

/**
 * Genera report istantaneo del mercato
 */
async function handleReport(chatId: number, env: Env): Promise<void> {
  const data = await fetchData(env);
  if (!data?.opportunities?.length) {
    await sendMessage(env, chatId, '❌ Dati non disponibili.');
    return;
  }

  const opps = data.opportunities;
  const today = new Date();
  const dateStr = today.toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' });

  // Statistiche
  const hot = opps.filter(o => o.ob1_score >= 80);
  const warm = opps.filter(o => o.ob1_score >= 60 && o.ob1_score < 80);
  const svincolati = opps.filter(o => o.opportunity_type?.toLowerCase().includes('svincolato'));
  const prestiti = opps.filter(o => o.opportunity_type?.toLowerCase().includes('prestito'));

  // Raggruppa per ruolo
  const byRole: Record<string, typeof opps> = {};
  opps.forEach(o => {
    const role = o.role || 'Altro';
    if (!byRole[role]) byRole[role] = [];
    byRole[role].push(o);
  });

  // Top 5
  const top5 = [...opps].sort((a, b) => b.ob1_score - a.ob1_score).slice(0, 5);

  let message = `📊 <b>OB1 SCOUT - REPORT MERCATO</b>
<i>${dateStr}</i>

━━━━━━━━━━━━━━━━━━━━

📈 <b>PANORAMICA</b>
• <b>${opps.length}</b> opportunità totali
• 🔥 ${hot.length} HOT (80+)
• ⚡ ${warm.length} WARM (60-79)
• 📄 ${svincolati.length} svincolati
• 🔄 ${prestiti.length} in prestito

━━━━━━━━━━━━━━━━━━━━

🏆 <b>TOP 5 OPPORTUNITÀ</b>

`;

  top5.forEach((opp, i) => {
    const medal = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣'][i];
    message += `${medal} <b>${opp.player_name}</b> (${opp.ob1_score})
   ${opp.role_name || opp.role} • ${opp.age || '?'} anni
   ${opp.opportunity_type?.toUpperCase()} ${opp.current_club ? `• ${opp.current_club}` : ''}
\n`;
  });

  // Per ruolo
  message += `━━━━━━━━━━━━━━━━━━━━
📋 <b>PER REPARTO</b>\n`;

  const roleEmojis: Record<string, string> = {
    'DC': '🛡️', 'TD': '🛡️', 'TS': '🛡️', 'PO': '🧤',
    'CC': '🎯', 'MED': '🎯', 'TRQ': '🎯',
    'AT': '⚽', 'ATT': '⚽', 'PC': '⚽',
    'AD': '🏃', 'AS': '🏃', 'ED': '🏃', 'ES': '🏃'
  };

  const reparti = {
    'Difesa': ['DC', 'TD', 'TS', 'PO'],
    'Centrocampo': ['CC', 'MED', 'TRQ'],
    'Attacco': ['AT', 'ATT', 'PC', 'AD', 'AS', 'ED', 'ES']
  };

  Object.entries(reparti).forEach(([name, roles]) => {
    const count = roles.reduce((sum, r) => sum + (byRole[r]?.length || 0), 0);
    if (count > 0) {
      message += `• ${name}: ${count} opportunità\n`;
    }
  });

  message += `
━━━━━━━━━━━━━━━━━━━━
💬 <i>Chiedimi qualsiasi cosa sul mercato!</i>
🌐 <a href="https://mtornani.github.io/ob1-serie-c/">Dashboard</a>`;

  await sendMessage(env, chatId, message);
}

// ============================================================================
// NLP-003: NATURAL LANGUAGE WATCH PROFILE CREATION
// ============================================================================

async function handleNaturalWatchCreate(
  chatId: number,
  parsed: ParsedIntent,
  env: Env
): Promise<void> {
  const { createKVStorage, createMemoryStorage } = await import('./watch/storage');
  const { WatchProfile, generateProfileId, getProfileDisplayName } = await import('./watch/types');

  const watchStorage = env.USER_DATA ? createKVStorage(env.USER_DATA) : createMemoryStorage();

  // Check existing profiles
  const existing = await watchStorage.listProfiles(chatId);
  if (existing.length >= 5) {
    await sendMessage(env, chatId, `⚠️ Hai già 5 profili attivi (limite massimo).

Usa /watch per gestirli o rimuoverne uno.`);
    return;
  }

  // Build profile from parsed filters
  const profile: any = {
    id: generateProfileId(),
    name: '',
    roles: parsed.filters.roles || undefined,
    opportunity_types: parsed.filters.types || undefined,
    age_max: parsed.filters.ageMax || undefined,
    age_min: parsed.filters.ageMin || undefined,
    min_ob1_score: parsed.filters.minScore || undefined,
    alert_immediately: true,
    include_in_digest: true,
    active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  // Generate name
  const nameParts: string[] = [];
  if (parsed.filters.role) nameParts.push(parsed.filters.role);
  if (parsed.filters.type) nameParts.push(parsed.filters.type);
  if (parsed.filters.ageMax) nameParts.push(`U${parsed.filters.ageMax}`);
  profile.name = nameParts.length > 0 ? nameParts.join(' ') : 'Watch Profile';

  // Save profile
  await watchStorage.saveProfile(chatId, profile);

  // Register user for notifications
  const { createNotificationQueue, createMemoryQueue } = await import('./notifications/queue');
  const notifQueue = env.USER_DATA ? createNotificationQueue(env.USER_DATA) : createMemoryQueue();
  await notifQueue.registerUser(chatId);

  // Build confirmation message
  const details: string[] = [];
  if (profile.roles?.length) details.push(`📍 Ruolo: ${profile.roles.join(', ')}`);
  if (profile.opportunity_types?.length) details.push(`📋 Tipo: ${profile.opportunity_types.join(', ')}`);
  if (profile.age_max) details.push(`🎂 Età: Under ${profile.age_max}`);
  if (profile.min_ob1_score) details.push(`⭐ Score minimo: ${profile.min_ob1_score}`);

  const detailsText = details.length > 0 ? details.join('\n') : '(tutti i giocatori)';

  await sendMessage(env, chatId, `✅ <b>Alert creato!</b>

<b>${profile.name}</b>

${detailsText}

🔔 Ti avviserò quando troverò opportunità che matchano.

📋 /watch per gestire i tuoi alert`);
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

  const opportunities = await fetchDNAData(env);

  if (!opportunities) {
    await sendMessage(env, chatId, formatError());
    return;
  }

  const results = searchTalents(opportunities, query, 5);
  const message = formatTalentSearchResults(results, query);

  // NLP-003: Inject AI Scout Persona commentary
  if (env.AI) {
    const aiComment = await generateScoutResponse(
      env.AI, 
      `${query.description}`, 
      results.map(r => r.player), 
      'talent'
    );

    if (aiComment) {
      const fullMessage = `🗣️ <b>OB1 Scout:</b>\n<i>"${aiComment}"</i>\n\n${message}`;
      await sendMessage(env, chatId, fullMessage);
      return;
    }
  }

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
