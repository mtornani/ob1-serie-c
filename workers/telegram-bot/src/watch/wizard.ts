/**
 * SCORE-002: Watch Criteria System - Interactive Wizard
 */

import {
  WatchProfile,
  WizardState,
  ROLE_OPTIONS,
  TYPE_OPTIONS,
  AGE_OPTIONS,
  SCORE_OPTIONS,
  generateProfileId,
  getProfileDisplayName,
} from './types';

interface InlineKeyboardButton {
  text: string;
  callback_data: string;
}

interface InlineKeyboard {
  inline_keyboard: InlineKeyboardButton[][];
}

/**
 * Create the initial wizard state
 */
export function createInitialWizardState(): WizardState {
  return {
    step: 'role',
    profile: {
      id: generateProfileId(),
      alert_immediately: true,
      include_in_digest: true,
      active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  };
}

/**
 * Get the message and keyboard for current wizard step
 */
export function getWizardStepContent(state: WizardState): {
  message: string;
  keyboard: InlineKeyboard;
} {
  const currentSelection = getProfileDisplayName(state.profile);
  const prefix = currentSelection ? `✅ ${currentSelection}\n\n` : '';

  switch (state.step) {
    case 'role':
      return {
        message: `🎯 <b>Nuovo Watch Profile</b>\n\nChe ruolo cerchi?`,
        keyboard: createKeyboard(ROLE_OPTIONS.map(o => ({
          text: o.label,
          callback_data: `watch:role:${o.id}`,
        })), 2),
      };

    case 'type':
      return {
        message: `${prefix}Che tipo di opportunità?`,
        keyboard: createKeyboard(TYPE_OPTIONS.map(o => ({
          text: o.label,
          callback_data: `watch:type:${o.id}`,
        })), 2),
      };

    case 'age':
      return {
        message: `${prefix}Fascia d'età?`,
        keyboard: createKeyboard(AGE_OPTIONS.map(o => ({
          text: o.label,
          callback_data: `watch:age:${o.id}`,
        })), 2),
      };

    case 'score':
      return {
        message: `${prefix}Score minimo?`,
        keyboard: createKeyboard(SCORE_OPTIONS.map(o => ({
          text: o.label,
          callback_data: `watch:score:${o.id}`,
        })), 1),
      };

    case 'confirm':
      return {
        message: formatConfirmation(state.profile),
        keyboard: {
          inline_keyboard: [
            [
              { text: '✅ Salva', callback_data: 'watch:confirm:save' },
              { text: '❌ Annulla', callback_data: 'watch:confirm:cancel' },
            ],
            [
              { text: '🔄 Ricomincia', callback_data: 'watch:confirm:restart' },
            ],
          ],
        },
      };

    default:
      return {
        message: 'Errore nel wizard',
        keyboard: { inline_keyboard: [] },
      };
  }
}

/**
 * Process a wizard callback and return the updated state
 */
export function processWizardCallback(
  state: WizardState,
  action: string,
  value: string
): { newState: WizardState | null; completed: boolean; cancelled: boolean } {
  const newState: WizardState = {
    ...state,
    profile: { ...state.profile, updated_at: new Date().toISOString() },
  };

  switch (action) {
    case 'role': {
      const option = ROLE_OPTIONS.find(o => o.id === value);
      if (option) {
        newState.profile.roles = option.roles.length > 0 ? option.roles : undefined;
        newState.step = 'type';
      }
      break;
    }

    case 'type': {
      const option = TYPE_OPTIONS.find(o => o.id === value);
      if (option) {
        newState.profile.opportunity_types = option.types.length > 0 ? option.types : undefined;
        newState.step = 'age';
      }
      break;
    }

    case 'age': {
      const option = AGE_OPTIONS.find(o => o.id === value);
      if (option) {
        newState.profile.age_max = option.max;
        newState.step = 'score';
      }
      break;
    }

    case 'score': {
      const option = SCORE_OPTIONS.find(o => o.id === value);
      if (option) {
        newState.profile.min_ob1_score = option.min > 0 ? option.min : undefined;
        newState.step = 'confirm';

        // Generate name based on selections
        newState.profile.name = getProfileDisplayName(newState.profile);
      }
      break;
    }

    case 'confirm': {
      if (value === 'save') {
        return { newState, completed: true, cancelled: false };
      }
      if (value === 'cancel') {
        return { newState: null, completed: false, cancelled: true };
      }
      if (value === 'restart') {
        return {
          newState: createInitialWizardState(),
          completed: false,
          cancelled: false,
        };
      }
      break;
    }
  }

  return { newState, completed: false, cancelled: false };
}

/**
 * Format the confirmation message
 */
function formatConfirmation(profile: Partial<WatchProfile>): string {
  const lines: string[] = ['📋 <b>Riepilogo Watch Profile</b>\n'];

  // Role
  if (profile.roles && profile.roles.length > 0) {
    const roleOption = ROLE_OPTIONS.find(r =>
      JSON.stringify(r.roles.sort()) === JSON.stringify([...profile.roles!].sort())
    );
    lines.push(`• <b>Ruolo:</b> ${roleOption?.label.split(' ')[1] || profile.roles.join(', ')}`);
  } else {
    lines.push(`• <b>Ruolo:</b> Tutti`);
  }

  // Type
  if (profile.opportunity_types && profile.opportunity_types.length > 0) {
    lines.push(`• <b>Tipo:</b> ${profile.opportunity_types.join(', ')}`);
  } else {
    lines.push(`• <b>Tipo:</b> Tutti`);
  }

  // Age
  if (profile.age_max) {
    lines.push(`• <b>Età:</b> Under ${profile.age_max}`);
  } else {
    lines.push(`• <b>Età:</b> Tutte`);
  }

  // Score
  if (profile.min_ob1_score && profile.min_ob1_score > 0) {
    const scoreLabel = profile.min_ob1_score >= 80 ? 'Solo HOT' : 'WARM+';
    lines.push(`• <b>Score:</b> ${scoreLabel} (${profile.min_ob1_score}+)`);
  } else {
    lines.push(`• <b>Score:</b> Tutti`);
  }

  lines.push('');
  lines.push(`🔔 <b>Notifiche:</b> Alert immediato per match`);

  return lines.join('\n');
}

/**
 * Create an inline keyboard from buttons
 */
function createKeyboard(buttons: InlineKeyboardButton[], columns: number): InlineKeyboard {
  const rows: InlineKeyboardButton[][] = [];

  for (let i = 0; i < buttons.length; i += columns) {
    rows.push(buttons.slice(i, i + columns));
  }

  return { inline_keyboard: rows };
}

/**
 * Format the list of profiles
 */
export function formatProfileList(profiles: WatchProfile[]): string {
  if (profiles.length === 0) {
    return `📋 <b>I tuoi Watch Profile</b>

Non hai ancora creato nessun profilo.

Usa /watch add per crearne uno nuovo e ricevere notifiche personalizzate!`;
  }

  let message = `📋 <b>I tuoi Watch Profile</b> (${profiles.length})\n\n`;

  profiles.forEach((p, i) => {
    const status = p.active ? '🟢' : '🔴';
    const name = p.name || getProfileDisplayName(p);

    message += `${status} <b>${i + 1}. ${name}</b>\n`;

    const filters: string[] = [];
    if (p.roles?.length) filters.push(`Ruolo: ${p.roles.join('/')}`);
    if (p.opportunity_types?.length) filters.push(`Tipo: ${p.opportunity_types.join('/')}`);
    if (p.age_max) filters.push(`U${p.age_max}`);
    if (p.min_ob1_score) filters.push(`Score ${p.min_ob1_score}+`);

    if (filters.length > 0) {
      message += `   ${filters.join(' • ')}\n`;
    }

    message += `   <code>/watch remove ${p.id.substring(0, 8)}</code>\n\n`;
  });

  message += `\n<i>Usa /watch add per aggiungerne uno nuovo</i>`;

  return message;
}

/**
 * Format success message after saving
 */
export function formatSaveSuccess(profile: WatchProfile): string {
  const name = profile.name || getProfileDisplayName(profile);

  return `✅ <b>Watch Profile salvato!</b>

<b>${name}</b>

Riceverai notifiche quando troveremo opportunità che matchano i tuoi criteri.

📋 /watch per vedere tutti i tuoi profili`;
}
