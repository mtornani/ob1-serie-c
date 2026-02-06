/**
 * DNA-001: Talent Search - Natural Language Field Search
 * REFACTORED: Now uses only data.json via Opportunity interface.
 */

import { PlayerMatch } from './dna';
import { Opportunity } from './types';

// Mapping ruoli - linguaggio naturale → posizioni
const ROLE_MAPPINGS: Record<string, string[]> = {
  'terzino destro': ['TD'],
  'terzino dx': ['TD'],
  'terzino sinistro': ['TS'],
  'terzino sx': ['TS'],
  'difensore centrale': ['DC'],
  'centrale': ['DC'],
  'stopper': ['DC'],
  'terzino': ['TD', 'TS'],
  'difensore': ['DC', 'TD', 'TS'],
  'centrocampista centrale': ['CC'],
  'mediano': ['MED', 'CC'],
  'regista': ['MED', 'CC'],
  'mezzala': ['CC'],
  'trequartista': ['TRQ'],
  'interno': ['CC'],
  'centrocampista': ['CC', 'MED', 'TRQ'],
  'esterno destro': ['ED', 'AD'],
  'esterno sinistro': ['ES', 'AS'],
  'ala destra': ['AD'],
  'ala sinistra': ['AS'],
  'esterno': ['ES', 'ED', 'AS', 'AD'],
  'ala': ['AS', 'AD'],
  'fascia': ['ES', 'ED', 'TS', 'TD'],
  'prima punta': ['PC'],
  'seconda punta': ['ATT', 'TRQ'],
  'centravanti': ['PC'],
  'attaccante': ['ATT', 'PC'],
  'punta': ['PC', 'ATT'],
  'portiere': ['POR', 'PO'],
};

export interface TalentSearchQuery {
  positions: string[];
  keywords: string[];
  ageRange?: { min?: number; max?: number };
  description: string;
}

/**
 * Parsa una query da campo in requisiti strutturati
 */
export function parseTalentQuery(text: string): TalentSearchQuery | null {
  const lower = text.toLowerCase().trim();
  const positions: string[] = [];
  const keywords: string[] = [];
  let ageRange: { min?: number; max?: number } | undefined;
  const descriptions: string[] = [];

  // 1. Trova il ruolo
  for (const [keyword, positionList] of Object.entries(ROLE_MAPPINGS)) {
    if (lower.includes(keyword)) {
      positions.push(...positionList);
      descriptions.push(keyword);
      break;
    }
  }

  // 2. Trova parole chiave (caratteristiche)
  const characteristicKeywords = [
    'veloce', 'rapido', 'tecnico', 'dribbling', 'fisico', 'forte', 
    'imposta', 'visione', 'pressa', 'aggressivo', 'box-to-box', 'spinge'
  ];
  
  for (const kw of characteristicKeywords) {
    if (lower.includes(kw)) {
      keywords.push(kw);
      descriptions.push(kw);
    }
  }

  // 3. Trova età
  if (lower.includes('giovane') || lower.includes('under 23') || lower.includes('u23')) {
    ageRange = { max: 23 };
    descriptions.push('giovane');
  } else if (lower.includes('esperto') || lower.includes('over 30')) {
    ageRange = { min: 30 };
    descriptions.push('esperto');
  }

  if (positions.length === 0 && keywords.length === 0) {
    return null;
  }

  return {
    positions: [...new Set(positions)],
    keywords,
    ageRange,
    description: descriptions.join(', '),
  };
}

/**
 * Cerca talenti che matchano la query usando le opportunità di mercato
 */
export function searchTalents(
  opportunities: Opportunity[],
  query: TalentSearchQuery,
  limit: number = 5
): PlayerMatch[] {
  const matches: Array<{ opportunity: Opportunity; score: number }> = [];

  for (const opp of opportunities) {
    let score = opp.ob1_score;
    
    // Check posizione
    if (query.positions.length > 0) {
      const playerPos = (opp.role || '').toUpperCase();
      const posMatch = query.positions.some(p => playerPos.includes(p));
      if (!posMatch) continue;
      score += 10;
    }

    // Check keywords in summary
    if (query.keywords.length > 0) {
      const summary = (opp.summary || '').toLowerCase();
      let kwMatches = 0;
      for (const kw of query.keywords) {
        if (summary.includes(kw)) {
          kwMatches++;
          score += 5;
        }
      }
      if (kwMatches === 0 && query.keywords.length > 1) {
        // Se cerchiamo caratteristiche specifiche e non ne troviamo nessuna, penalizziamo
        score -= 10;
      }
    }

    // Check età
    if (query.ageRange) {
      if (query.ageRange.max && opp.age > query.ageRange.max) continue;
      if (query.ageRange.min && opp.age < query.ageRange.min) continue;
      score += 5;
    }

    matches.push({ opportunity: opp, score });
  }

  return matches
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map(m => ({
      player: m.opportunity,
      club_id: 'talent-search',
      club_name: 'Ricerca Talenti',
      score: m.score,
      recommendation: `Match basato su caratteristiche: ${query.description}`
    }));
}

/**
 * Formatta i risultati per Telegram
 */
export function formatTalentSearchResults(
  matches: PlayerMatch[],
  query: TalentSearchQuery
): string {
  if (matches.length === 0) {
    return `🔍 <b>Nessun talento trovato</b>

Cercavi: <i>${query.description || 'caratteristiche non specificate'}</i>

Prova con query più generiche o cerca per ruolo.`;
  }

  let message = `⚽ <b>Talenti per: ${query.description}</b>

`;

  matches.forEach((match, index) => {
    const o = match.player;
    const scoreEmoji = o.ob1_score >= 80 ? '🔥' : o.ob1_score >= 60 ? '⚡' : '📊';

    message += `${scoreEmoji} <b>${escapeHtml(o.player_name)}</b>`;
    message += ` (${o.age} anni)
`;
    message += `📍 ${o.role_name || o.role} | ${escapeHtml(o.current_club || 'Svincolato')}
`;

    message += `💡 <i>${escapeHtml(match.recommendation)}</i>
`;

    if (o.source_url) {
      message += `🔗 <a href="${o.source_url}">Dettagli</a>
`;
    }

    if (index < matches.length - 1) {
      message += '\n───────────────\n\n';
    }
  });

  message += '\n\n━━━━━━━━━━━━━━━━━━━━';
  message += '\n🌐 <a href="https://mtornani.github.io/ob1-serie-c/">Dashboard completa</a>';

  return message;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}