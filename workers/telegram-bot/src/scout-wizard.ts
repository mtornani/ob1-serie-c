/**
 * SCOUT-001: Scout Wizard ("Akinator" style)
 *
 * Sistema conversazionale a domande per aiutare i DS a trovare il giocatore giusto.
 * Il DS non sa sempre cosa vuole, ma sa rispondere a domande mirate.
 *
 * Flow:
 * 1. DS scrive qualcosa di vago: "mi serve qualcuno per il centrocampo"
 * 2. Bot inizia wizard: "Preferisci un giovane da far crescere o uno già pronto?"
 * 3. DS risponde cliccando un bottone
 * 4. Bot affina: "Budget importante o parametro zero?"
 * 5. Etc. fino a trovare i match migliori
 */

import { Env, Opportunity } from './types';
import { sendMessageWithKeyboard, editMessageText, answerCallbackQuery } from './telegram';
import { fetchData, filterOpportunities } from './data';

// ============================================================================
// TYPES
// ============================================================================

export interface WizardSession {
  chatId: number;
  messageId?: number;
  step: number;
  answers: WizardAnswers;
  startedAt: string;
}

export interface WizardAnswers {
  // Step 1: Ruolo
  role?: 'difensore' | 'centrocampista' | 'attaccante' | 'portiere' | 'qualsiasi';

  // Step 2: Età/Esperienza
  experience?: 'giovane' | 'pronto' | 'esperto' | 'qualsiasi';

  // Step 3: Budget/Tipo
  budget?: 'zero' | 'prestito' | 'qualsiasi';

  // Step 4: Carattere/Piazza
  character?: 'leader' | 'gregario' | 'talento' | 'qualsiasi';

  // Step 5: Contesto geografico (rivalità)
  excludeClubs?: string[];  // Club da cui NON prendere (rivalità)
}

// ============================================================================
// WIZARD QUESTIONS
// ============================================================================

interface WizardQuestion {
  step: number;
  question: string;
  options: Array<{
    label: string;
    value: string;
    emoji: string;
  }>;
}

const WIZARD_QUESTIONS: WizardQuestion[] = [
  {
    step: 1,
    question: "Che ruolo ti serve?",
    options: [
      { label: "Difensore", value: "difensore", emoji: "🛡️" },
      { label: "Centrocampista", value: "centrocampista", emoji: "⚙️" },
      { label: "Attaccante", value: "attaccante", emoji: "⚽" },
      { label: "Portiere", value: "portiere", emoji: "🧤" },
      { label: "Vediamo tutto", value: "qualsiasi", emoji: "🔍" },
    ],
  },
  {
    step: 2,
    question: "Che tipo di giocatore cerchi?",
    options: [
      { label: "Giovane da far crescere", value: "giovane", emoji: "🌱" },
      { label: "Già pronto per la C", value: "pronto", emoji: "💪" },
      { label: "Esperto/Leader", value: "esperto", emoji: "👴" },
      { label: "Non importa", value: "qualsiasi", emoji: "🤷" },
    ],
  },
  {
    step: 3,
    question: "Che budget hai?",
    options: [
      { label: "Solo parametri zero", value: "zero", emoji: "🆓" },
      { label: "Anche prestiti", value: "prestito", emoji: "🔄" },
      { label: "Vediamo tutto", value: "qualsiasi", emoji: "💰" },
    ],
  },
  {
    step: 4,
    question: "Che caratteristiche umane cerchi?",
    options: [
      { label: "Un leader/capitano", value: "leader", emoji: "🎖️" },
      { label: "Un gregario affidabile", value: "gregario", emoji: "🤝" },
      { label: "Un talento da scoprire", value: "talento", emoji: "💎" },
      { label: "Non importa", value: "qualsiasi", emoji: "🤷" },
    ],
  },
];

// ============================================================================
// ITALIAN FOOTBALL RIVALRIES (campanilismi)
// ============================================================================

/**
 * Mappa delle rivalità storiche del calcio italiano.
 * Un giocatore con passato in una di queste squadre difficilmente
 * andrà a giocare nella rivale.
 */
const RIVALRIES: Record<string, string[]> = {
  // Emilia-Romagna
  'cesena': ['rimini'],
  'rimini': ['cesena'],
  'reggiana': ['modena', 'parma'],
  'modena': ['reggiana', 'parma'],
  'parma': ['reggiana', 'modena'],
  'spal': ['bologna'],

  // Toscana
  'pisa': ['livorno', 'fiorentina'],
  'livorno': ['pisa'],
  'empoli': ['fiorentina'],
  'siena': ['fiorentina'],

  // Lazio
  'frosinone': ['latina'],
  'latina': ['frosinone'],

  // Campania
  'avellino': ['salernitana', 'benevento'],
  'salernitana': ['avellino', 'napoli'],
  'benevento': ['avellino'],

  // Sicilia
  'catania': ['palermo', 'messina'],
  'palermo': ['catania'],
  'messina': ['catania', 'reggina'],

  // Calabria
  'reggina': ['cosenza', 'catanzaro'],
  'cosenza': ['reggina', 'catanzaro'],
  'catanzaro': ['reggina', 'cosenza'],

  // Puglia
  'bari': ['lecce', 'foggia'],
  'lecce': ['bari', 'taranto'],
  'foggia': ['bari'],
  'taranto': ['lecce'],

  // Veneto
  'padova': ['venezia', 'vicenza', 'verona'],
  'venezia': ['padova', 'treviso'],
  'vicenza': ['padova', 'verona'],

  // Lombardia
  'brescia': ['atalanta', 'cremonese'],
  'cremonese': ['brescia'],
  'como': ['varese'],

  // Piemonte
  'novara': ['alessandria', 'pro vercelli'],
  'alessandria': ['novara'],
  'pro vercelli': ['novara'],
};

/**
 * Data le squadre precedenti di un giocatore, ritorna i club
 * dove probabilmente NON andrebbe per rivalità storiche.
 */
export function getIncompatibleClubs(previousClubs: string[]): string[] {
  const incompatible = new Set<string>();

  for (const club of previousClubs) {
    const normalized = club.toLowerCase().trim();
    const rivals = RIVALRIES[normalized];
    if (rivals) {
      rivals.forEach(r => incompatible.add(r));
    }
  }

  return Array.from(incompatible);
}

// ============================================================================
// SESSION MANAGEMENT (in-memory for now, could use KV)
// ============================================================================

const wizardSessions = new Map<number, WizardSession>();

export function getWizardSession(chatId: number): WizardSession | undefined {
  return wizardSessions.get(chatId);
}

export function createWizardSession(chatId: number): WizardSession {
  const session: WizardSession = {
    chatId,
    step: 1,
    answers: {},
    startedAt: new Date().toISOString(),
  };
  wizardSessions.set(chatId, session);
  return session;
}

export function clearWizardSession(chatId: number): void {
  wizardSessions.delete(chatId);
}

// ============================================================================
// WIZARD FLOW
// ============================================================================

/**
 * Avvia il wizard scout
 */
export async function startScoutWizard(chatId: number, env: Env): Promise<void> {
  const session = createWizardSession(chatId);
  await sendWizardQuestion(chatId, session, env);
}

/**
 * Manda la domanda corrente del wizard
 */
async function sendWizardQuestion(chatId: number, session: WizardSession, env: Env): Promise<void> {
  const question = WIZARD_QUESTIONS[session.step - 1];

  if (!question) {
    // Wizard completato, mostra risultati
    await showWizardResults(chatId, session, env);
    return;
  }

  const keyboard = {
    inline_keyboard: question.options.map(opt => [{
      text: `${opt.emoji} ${opt.label}`,
      callback_data: `scout:${session.step}:${opt.value}`,
    }]),
  };

  // Add cancel button
  keyboard.inline_keyboard.push([{
    text: "❌ Annulla",
    callback_data: "scout:cancel",
  }]);

  const message = `🎯 <b>Scout Wizard</b> (${session.step}/${WIZARD_QUESTIONS.length})

${question.question}`;

  await sendMessageWithKeyboard(env, chatId, message, keyboard);
}

/**
 * Gestisce la risposta a una domanda del wizard
 */
export async function handleWizardCallback(
  chatId: number,
  messageId: number,
  callbackId: string,
  data: string,
  env: Env
): Promise<void> {
  // Parse callback data: "scout:step:value" or "scout:cancel"
  const parts = data.split(':');

  if (parts[1] === 'cancel') {
    clearWizardSession(chatId);
    await answerCallbackQuery(env, callbackId, '❌ Wizard annullato');
    await editMessageText(env, chatId, messageId, '❌ Scout Wizard annullato.\n\nUsa /scout per ricominciare.');
    return;
  }

  const step = parseInt(parts[1]);
  const value = parts[2];

  const session = getWizardSession(chatId);
  if (!session || session.step !== step) {
    await answerCallbackQuery(env, callbackId, '⚠️ Sessione scaduta');
    return;
  }

  // Save answer based on step
  switch (step) {
    case 1:
      session.answers.role = value as any;
      break;
    case 2:
      session.answers.experience = value as any;
      break;
    case 3:
      session.answers.budget = value as any;
      break;
    case 4:
      session.answers.character = value as any;
      break;
  }

  // Move to next step
  session.step++;
  wizardSessions.set(chatId, session);

  await answerCallbackQuery(env, callbackId, '✓');

  // Update message with next question or results
  if (session.step > WIZARD_QUESTIONS.length) {
    await showWizardResults(chatId, session, env, messageId);
  } else {
    const nextQuestion = WIZARD_QUESTIONS[session.step - 1];
    const keyboard = {
      inline_keyboard: nextQuestion.options.map(opt => [{
        text: `${opt.emoji} ${opt.label}`,
        callback_data: `scout:${session.step}:${opt.value}`,
      }]),
    };
    keyboard.inline_keyboard.push([{
      text: "❌ Annulla",
      callback_data: "scout:cancel",
    }]);

    const message = `🎯 <b>Scout Wizard</b> (${session.step}/${WIZARD_QUESTIONS.length})

${nextQuestion.question}`;

    await editMessageText(env, chatId, messageId, message, keyboard);
  }
}

/**
 * Mostra i risultati finali del wizard
 */
async function showWizardResults(
  chatId: number,
  session: WizardSession,
  env: Env,
  messageId?: number
): Promise<void> {
  const data = await fetchData(env);

  if (!data?.opportunities) {
    const errorMsg = '❌ Errore nel caricamento dati. Riprova più tardi.';
    if (messageId) {
      await editMessageText(env, chatId, messageId, errorMsg);
    }
    clearWizardSession(chatId);
    return;
  }

  // Build filters from answers
  const filters: any = {};

  if (session.answers.role && session.answers.role !== 'qualsiasi') {
    filters.role = session.answers.role;
  }

  if (session.answers.experience && session.answers.experience !== 'qualsiasi') {
    switch (session.answers.experience) {
      case 'giovane':
        filters.ageMax = 23;
        break;
      case 'pronto':
        filters.ageMin = 23;
        filters.ageMax = 28;
        break;
      case 'esperto':
        filters.ageMin = 28;
        break;
    }
  }

  if (session.answers.budget && session.answers.budget !== 'qualsiasi') {
    switch (session.answers.budget) {
      case 'zero':
        filters.type = 'svincolato';
        break;
      case 'prestito':
        // Include both svincolato and prestito
        break;
    }
  }

  // Filter opportunities
  let results = filterOpportunities(data.opportunities, filters);

  // Sort by score
  results = results.sort((a, b) => b.ob1_score - a.ob1_score).slice(0, 5);

  // Build summary
  const summaryParts: string[] = [];
  if (session.answers.role !== 'qualsiasi') summaryParts.push(session.answers.role || '');
  if (session.answers.experience !== 'qualsiasi') {
    const expLabels: Record<string, string> = {
      'giovane': 'giovane',
      'pronto': 'pronto',
      'esperto': 'esperto',
    };
    summaryParts.push(expLabels[session.answers.experience || ''] || '');
  }
  if (session.answers.budget !== 'qualsiasi') {
    const budgetLabels: Record<string, string> = {
      'zero': 'a zero',
      'prestito': 'in prestito',
    };
    summaryParts.push(budgetLabels[session.answers.budget || ''] || '');
  }

  const summary = summaryParts.filter(Boolean).join(', ') || 'senza filtri';

  let message = `🎯 <b>Risultati Scout Wizard</b>

📋 Hai cercato: <i>${summary}</i>

`;

  if (results.length === 0) {
    message += `😔 Nessun giocatore trovato con questi criteri.

Prova a rilassare i filtri o usa /hot per vedere le migliori opportunità.`;
  } else {
    message += `🏆 <b>Top ${results.length} match:</b>\n\n`;

    results.forEach((opp, i) => {
      const emoji = opp.ob1_score >= 80 ? '🔥' : opp.ob1_score >= 60 ? '⚡' : '📊';
      message += `${i + 1}. ${emoji} <b>${opp.player_name}</b>`;
      if (opp.age) message += ` (${opp.age})`;
      message += `\n   ${opp.role_name || opp.role} • ${opp.opportunity_type} • Score ${opp.ob1_score}`;
      if (opp.current_club) message += `\n   📍 ${opp.current_club}`;
      message += '\n\n';
    });

    message += `\n💡 Usa /search <nome> per dettagli su un giocatore specifico.`;
  }

  // Clear session
  clearWizardSession(chatId);

  if (messageId) {
    await editMessageText(env, chatId, messageId, message);
  } else {
    const { sendMessage } = await import('./telegram');
    await sendMessage(env, chatId, message);
  }
}

/**
 * Check if a query should trigger the wizard
 */
export function shouldTriggerWizard(text: string): boolean {
  const lower = text.toLowerCase();

  // Explicit triggers
  if (/\/(scout|wizard|aiutami|cercami)\b/.test(lower)) {
    return true;
  }

  // Vague requests that suggest the DS doesn't know exactly what they want
  const vaguePatterns = [
    /mi serve (qualcuno|qualcosa|un giocatore)/i,
    /sto cercando (ma non so|qualcosa)/i,
    /aiutami a (trovare|cercare)/i,
    /non so (cosa|chi) cercare/i,
    /cosa mi (consigli|suggerisci)/i,
    /che (giocatori|opportunità) ci sono/i,
  ];

  return vaguePatterns.some(p => p.test(lower));
}
