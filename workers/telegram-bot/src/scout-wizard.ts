/**
 * SCOUT-001: Scout Wizard ("Akinator" style) — STATELESS VERSION
 *
 * Sistema conversazionale a domande per aiutare i DS a trovare il giocatore giusto.
 *
 * ARCHITETTURA: Zero sessioni. Tutto lo stato è codificato nel callback_data
 * di ogni bottone. Ogni click porta con sé tutte le risposte precedenti.
 *
 * Formato callback_data: "sw:<step>:<answer1>-<answer2>-..."
 * Esempio flow:
 *   Step 1 bottoni: sw:1:dif  sw:1:cen  sw:1:att  sw:1:por  sw:1:any
 *   User clicca "Centrocampista" → callback = "sw:1:cen"
 *   Step 2 bottoni: sw:2:cen-gio  sw:2:cen-pro  sw:2:cen-esp  sw:2:cen-any
 *   User clicca "Giovane" → callback = "sw:2:cen-gio"
 *   Step 3 bottoni: sw:3:cen-gio-zer  sw:3:cen-gio-pre  sw:3:cen-gio-any
 *   ...e così via fino a step 4, poi mostra risultati.
 *
 * Max callback_data = 64 bytes. Con "sw:4:xxx-xxx-xxx-xxx" = ~25 bytes. OK.
 */

import { Env, Opportunity } from './types';
import { sendMessageWithKeyboard, editMessageText, answerCallbackQuery } from './telegram';
import { fetchData, filterOpportunities } from './data';

// ============================================================================
// TYPES
// ============================================================================

interface WizardStep {
  key: string;
  question: string;
  options: Array<{
    label: string;
    code: string;   // 3-char code for callback_data
    emoji: string;
  }>;
}

interface DecodedAnswers {
  role?: string;
  experience?: string;
  budget?: string;
  character?: string;
  club?: string;
}

// ============================================================================
// WIZARD STEPS DEFINITION
// ============================================================================

const STEPS: WizardStep[] = [
  {
    key: 'role',
    question: 'Che ruolo ti serve?',
    options: [
      { label: 'Difensore', code: 'dif', emoji: '🛡️' },
      { label: 'Centrocampista', code: 'cen', emoji: '⚙️' },
      { label: 'Attaccante', code: 'att', emoji: '⚽' },
      { label: 'Portiere', code: 'por', emoji: '🧤' },
      { label: 'Vediamo tutto', code: 'any', emoji: '🔍' },
    ],
  },
  {
    key: 'experience',
    question: 'Che tipo di giocatore cerchi?',
    options: [
      { label: 'Giovane da far crescere', code: 'gio', emoji: '🌱' },
      { label: 'Già pronto per la C', code: 'pro', emoji: '💪' },
      { label: 'Esperto/Leader', code: 'esp', emoji: '👴' },
      { label: 'Non importa', code: 'any', emoji: '🤷' },
    ],
  },
  {
    key: 'budget',
    question: 'Che budget hai?',
    options: [
      { label: 'Solo parametri zero', code: 'zer', emoji: '🆓' },
      { label: 'Anche prestiti', code: 'pre', emoji: '🔄' },
      { label: 'Vediamo tutto', code: 'any', emoji: '💰' },
    ],
  },
  {
    key: 'character',
    question: 'Che caratteristiche umane cerchi?',
    options: [
      { label: 'Un leader/capitano', code: 'lea', emoji: '🎖️' },
      { label: 'Un gregario affidabile', code: 'gre', emoji: '🤝' },
      { label: 'Un talento da scoprire', code: 'tal', emoji: '💎' },
      { label: 'Non importa', code: 'any', emoji: '🤷' },
    ],
  },
  {
    key: 'club',
    question: 'Per quale piazza? (Escluderò giocatori con rivalità storiche)',
    options: [
      { label: 'Cesena', code: 'ces', emoji: '🏟️' },
      { label: 'Pescara', code: 'pes', emoji: '🏟️' },
      { label: 'Perugia', code: 'per', emoji: '🏟️' },
      { label: 'Rimini', code: 'rim', emoji: '🏟️' },
      { label: 'Tre Penne', code: 'tre', emoji: '🇸🇲' },
      { label: 'La Fiorita', code: 'fio', emoji: '🇸🇲' },
      { label: 'Virtus', code: 'vir', emoji: '🇸🇲' },
      { label: 'Non specificare', code: 'any', emoji: '🔍' },
    ],
  },
];

const TOTAL_STEPS = STEPS.length;

// ============================================================================
// CALLBACK DATA ENCODING/DECODING
// ============================================================================

/**
 * Build callback_data for a button.
 * Format: "sw:<stepNum>:<prev1>-<prev2>-...-<thisAnswer>"
 *
 * For cancel: "sw:x"
 */
function buildCallbackData(stepNum: number, previousCodes: string[], thisCode: string): string {
  const allCodes = [...previousCodes, thisCode];
  return `sw:${stepNum}:${allCodes.join('-')}`;
}

/**
 * Parse callback_data back into step number and answer codes.
 * "sw:2:cen-gio" → { step: 2, codes: ['cen', 'gio'] }
 */
function parseCallbackData(data: string): { step: number; codes: string[] } | null {
  // Format: sw:<step>:<codes>
  const match = data.match(/^sw:(\d+):(.+)$/);
  if (!match) return null;
  return {
    step: parseInt(match[1]),
    codes: match[2].split('-'),
  };
}

/**
 * Decode answer codes into human-readable filters
 */
function decodeAnswers(codes: string[]): DecodedAnswers {
  const answers: DecodedAnswers = {};

  // codes[0] = role answer (from step 1)
  if (codes[0]) {
    const roleMap: Record<string, string> = {
      dif: 'difensore', cen: 'centrocampista', att: 'attaccante',
      por: 'portiere', any: 'qualsiasi',
    };
    answers.role = roleMap[codes[0]] || codes[0];
  }

  // codes[1] = experience answer (from step 2)
  if (codes[1]) {
    const expMap: Record<string, string> = {
      gio: 'giovane', pro: 'pronto', esp: 'esperto', any: 'qualsiasi',
    };
    answers.experience = expMap[codes[1]] || codes[1];
  }

  // codes[2] = budget answer (from step 3)
  if (codes[2]) {
    const budMap: Record<string, string> = {
      zer: 'zero', pre: 'prestito', any: 'qualsiasi',
    };
    answers.budget = budMap[codes[2]] || codes[2];
  }

  // codes[3] = character answer (from step 4)
  if (codes[3]) {
    const charMap: Record<string, string> = {
      lea: 'leader', gre: 'gregario', tal: 'talento', any: 'qualsiasi',
    };
    answers.character = charMap[codes[3]] || codes[3];
  }

  // codes[4] = club answer (from step 5)
  if (codes[4]) {
    const clubMap: Record<string, string> = {
      ces: 'cesena', pes: 'pescara', per: 'perugia', rim: 'rimini',
      tre: 'tre_penne', fio: 'la_fiorita', vir: 'virtus', any: 'qualsiasi',
    };
    answers.club = clubMap[codes[4]] || codes[4];
  }

  return answers;
}

// ============================================================================
// WIZARD FLOW — PUBLIC API
// ============================================================================

/**
 * Start the wizard: sends the first question with inline buttons.
 * No session created. Each button carries its own state.
 */
export async function startScoutWizard(chatId: number, env: Env): Promise<void> {
  const step = STEPS[0];
  const keyboard = buildStepKeyboard(0, []);

  const message = `🎯 <b>Scout Wizard</b> (1/${TOTAL_STEPS})

${step.question}`;

  await sendMessageWithKeyboard(env, chatId, message, keyboard);
}

/**
 * Handle a wizard callback button press.
 * Completely stateless — all info comes from callback_data.
 */
export async function handleWizardCallback(
  chatId: number,
  messageId: number,
  callbackId: string,
  data: string,
  env: Env
): Promise<void> {
  console.log(`[Wizard] Stateless callback: data="${data}" chat=${chatId}`);

  // Handle cancel
  if (data === 'sw:x') {
    await answerCallbackQuery(env, callbackId, '❌ Wizard annullato');
    await editMessageText(
      env, chatId, messageId,
      '❌ Scout Wizard annullato.\n\nUsa /scout per ricominciare.'
    );
    return;
  }

  // Parse callback data
  const parsed = parseCallbackData(data);
  if (!parsed) {
    console.error(`[Wizard] Invalid callback data: "${data}"`);
    await answerCallbackQuery(env, callbackId, '⚠️ Errore, usa /scout');
    return;
  }

  const { step, codes } = parsed;
  console.log(`[Wizard] Step ${step} completed, codes=[${codes.join(',')}]`);

  await answerCallbackQuery(env, callbackId, '✓');

  // Check if wizard is complete (all 4 steps answered)
  if (codes.length >= TOTAL_STEPS) {
    // All answers collected — show results
    await showWizardResults(chatId, messageId, codes, env);
    return;
  }

  // Show next step
  const nextStepIdx = codes.length; // 0-indexed
  const nextStep = STEPS[nextStepIdx];
  if (!nextStep) {
    // Shouldn't happen, but safety net
    await showWizardResults(chatId, messageId, codes, env);
    return;
  }

  const keyboard = buildStepKeyboard(nextStepIdx, codes);

  // Build progress summary
  const progress = buildProgressSummary(codes);

  const message = `🎯 <b>Scout Wizard</b> (${nextStepIdx + 1}/${TOTAL_STEPS})

${progress}
${nextStep.question}`;

  await editMessageText(env, chatId, messageId, message, keyboard);
}

/**
 * Check if a message text should trigger the wizard
 */
export function shouldTriggerWizard(text: string): boolean {
  const lower = text.toLowerCase();

  // Explicit triggers
  if (/\/(scout|wizard|aiutami|cercami)\b/.test(lower)) {
    return true;
  }

  // Vague requests
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

// ============================================================================
// INTERNAL HELPERS
// ============================================================================

/**
 * Build the inline keyboard for a given step index.
 * Each button's callback_data contains all previous answers + this answer.
 */
function buildStepKeyboard(stepIdx: number, previousCodes: string[]): any {
  const step = STEPS[stepIdx];
  const stepNum = stepIdx + 1;

  const keyboard = {
    inline_keyboard: step.options.map(opt => [{
      text: `${opt.emoji} ${opt.label}`,
      callback_data: buildCallbackData(stepNum, previousCodes, opt.code),
    }]),
  };

  // Add cancel button
  keyboard.inline_keyboard.push([{
    text: '❌ Annulla',
    callback_data: 'sw:x',
  }]);

  return keyboard;
}

/**
 * Build a visual summary of answers given so far
 */
function buildProgressSummary(codes: string[]): string {
  const parts: string[] = [];

  const labels: Array<{ key: string; map: Record<string, string> }> = [
    { key: '📌 Ruolo', map: { dif: 'Difensore', cen: 'Centrocampista', att: 'Attaccante', por: 'Portiere', any: 'Tutti' } },
    { key: '🎯 Tipo', map: { gio: 'Giovane', pro: 'Pronto', esp: 'Esperto', any: 'Tutti' } },
    { key: '💰 Budget', map: { zer: 'Param. zero', pre: 'Anche prestiti', any: 'Tutti' } },
    { key: '👤 Carattere', map: { lea: 'Leader', gre: 'Gregario', tal: 'Talento', any: 'Tutti' } },
    { key: '🏟️ Piazza', map: { ces: 'Cesena', pes: 'Pescara', per: 'Perugia', rim: 'Rimini', tre: 'Tre Penne', fio: 'La Fiorita', vir: 'Virtus', any: 'Tutte' } },
  ];

  for (let i = 0; i < codes.length && i < labels.length; i++) {
    const label = labels[i];
    const value = label.map[codes[i]] || codes[i];
    parts.push(`${label.key}: <b>${value}</b>`);
  }

  if (parts.length === 0) return '';
  return parts.join(' • ') + '\n\n';
}

/**
 * Show wizard results — final step
 * Filtri dal wizard, ordinati per ob1_score.
 */
async function showWizardResults(
  chatId: number,
  messageId: number,
  codes: string[],
  env: Env
): Promise<void> {
  const answers = decodeAnswers(codes);
  const data = await fetchData(env);

  if (!data?.opportunities) {
    await editMessageText(
      env, chatId, messageId,
      '❌ Errore nel caricamento dati. Riprova con /scout.'
    );
    return;
  }

  const filters: any = {};
  if (answers.role && answers.role !== 'qualsiasi') {
    filters.role = answers.role;
  }
  if (answers.experience && answers.experience !== 'qualsiasi') {
    switch (answers.experience) {
      case 'giovane': filters.ageMax = 23; break;
      case 'pronto': filters.ageMin = 23; filters.ageMax = 28; break;
      case 'esperto': filters.ageMin = 28; break;
    }
  }
  if (answers.budget && answers.budget !== 'qualsiasi') {
    if (answers.budget === 'zero') filters.type = 'svincolato';
  }

  let candidates = filterOpportunities(data.opportunities, filters);

  if (answers.club && answers.club !== 'qualsiasi') {
    const incompatibleClubs = RIVALRIES[answers.club] || [];
    candidates = candidates.filter(opp => {
      if (opp.previous_clubs && opp.previous_clubs.length > 0) {
        return !opp.previous_clubs.some(prevClub => {
          const normalized = prevClub.toLowerCase().trim();
          return incompatibleClubs.includes(normalized);
        });
      }
      return true;
    });
  }

  const results = [...candidates]
    .sort((a, b) => (b.ob1_score || 0) - (a.ob1_score || 0))
    .slice(0, 5);

  const progressSummary = buildProgressSummary(codes);
  const clubLabel = answers.club && answers.club !== 'qualsiasi'
    ? ` per <b>${escapeHtml(answers.club.replace(/_/g, ' '))}</b>`
    : '';

  let message = `🎯 <b>Risultati Scout Wizard</b>${clubLabel}

${progressSummary}`;

  if (results.length === 0) {
    message += `😔 Nessun giocatore trovato con questi criteri.

Prova a rilassare i filtri o usa /hot per le migliori opportunità.`;
  } else {
    message += `📋 <b>Top ${results.length} per priorità:</b>\n\n`;

    results.forEach((opp, i) => {
      const emoji = (opp.ob1_score || 0) >= 70 ? '🔥' : (opp.ob1_score || 0) >= 57 ? '⚡' : '📊';
      message += `${i + 1}. ${emoji} <b>${escapeHtml(opp.player_name)}</b>`;
      if (opp.age) message += ` (${opp.age})`;
      message += ` — <b>${opp.ob1_score}</b>/100\n`;
      message += `   ${opp.role_name || opp.role} • ${opp.opportunity_type}`;
      if (opp.current_club) message += `\n   📍 ${escapeHtml(opp.current_club)}`;
      message += '\n\n';
    });

    message += `💡 Usa /search &lt;nome&gt; per dettagli su un giocatore.`;
  }

  // Restart button
  const keyboard = {
    inline_keyboard: [[{
      text: '🔄 Cerca di nuovo',
      callback_data: 'sw:restart',
    }]],
  };

  await editMessageText(env, chatId, messageId, message, keyboard);
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ============================================================================
// RIVALRIES (kept for future use)
// ============================================================================

const RIVALRIES: Record<string, string[]> = {
  'cesena': ['rimini'], 'rimini': ['cesena'],
  'reggiana': ['modena', 'parma'], 'modena': ['reggiana', 'parma'],
  'parma': ['reggiana', 'modena'], 'spal': ['bologna'],
  'pisa': ['livorno', 'fiorentina'], 'livorno': ['pisa'],
  'empoli': ['fiorentina'], 'siena': ['fiorentina'],
  'frosinone': ['latina'], 'latina': ['frosinone'],
  'avellino': ['salernitana', 'benevento'], 'salernitana': ['avellino', 'napoli'],
  'benevento': ['avellino'],
  'catania': ['palermo', 'messina'], 'palermo': ['catania'],
  'messina': ['catania', 'reggina'],
  'reggina': ['cosenza', 'catanzaro'], 'cosenza': ['reggina', 'catanzaro'],
  'catanzaro': ['reggina', 'cosenza'],
  'bari': ['lecce', 'foggia'], 'lecce': ['bari', 'taranto'],
  'foggia': ['bari'], 'taranto': ['lecce'],
  'padova': ['venezia', 'vicenza', 'verona'], 'venezia': ['padova', 'treviso'],
  'vicenza': ['padova', 'verona'],
  'brescia': ['atalanta', 'cremonese'], 'cremonese': ['brescia'],
  'como': ['varese'],
  'novara': ['alessandria', 'pro vercelli'], 'alessandria': ['novara'],
  'pro vercelli': ['novara'],
  // Rivalità Sammarinesi
  'tre_penne': ['tre_fiori', 'virtus'], 'tre_fiori': ['tre_penne', 'virtus'],
  'virtus': ['tre_penne', 'tre_fiori', 'la_fiorita'],
  'la_fiorita': ['virtus', 'folgore_falciano'],
  'folgore_falciano': ['la_fiorita'],
  'cosmos': ['juvenes_dogana'], 'juvenes_dogana': ['cosmos'],
};

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
