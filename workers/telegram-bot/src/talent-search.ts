/**
 * DNA-001: Talent Search - Natural Language Field Search
 *
 * Permette al DS di cercare talenti con linguaggio da campo:
 * - "mi serve un terzino che spinga"
 * - "centrocampista box-to-box"
 * - "difensore bravo in impostazione"
 * - "ala veloce"
 */

import { PlayerMatch, DNAData } from './dna';

// Mapping ruoli - linguaggio naturale → posizioni
const ROLE_MAPPINGS: Record<string, string[]> = {
  // Difensori
  'terzino': ['TD', 'TS'],
  'terzino destro': ['TD'],
  'terzino sinistro': ['TS'],
  'difensore centrale': ['DC'],
  'centrale': ['DC'],
  'difensore': ['DC', 'TD', 'TS'],
  'stopper': ['DC'],

  // Centrocampisti
  'centrocampista': ['CC', 'MED', 'TRQ'],
  'mediano': ['MED', 'CC'],
  'regista': ['MED', 'CC'],
  'mezzala': ['CC'],
  'trequartista': ['TRQ'],
  'interno': ['CC'],
  'centrocampista centrale': ['CC'],

  // Esterni
  'esterno': ['ES', 'ED', 'AS', 'AD'],
  'esterno destro': ['ED', 'AD'],
  'esterno sinistro': ['ES', 'AS'],
  'ala': ['AS', 'AD'],
  'ala destra': ['AD'],
  'ala sinistra': ['AS'],
  'fascia': ['ES', 'ED', 'TS', 'TD'],

  // Attaccanti
  'attaccante': ['ATT', 'PC'],
  'punta': ['PC', 'ATT'],
  'prima punta': ['PC'],
  'seconda punta': ['ATT', 'TRQ'],
  'centravanti': ['PC'],

  // Portiere
  'portiere': ['POR'],
};

// Mapping caratteristiche - linguaggio da campo → skill requirements
interface SkillRequirement {
  skill: string;
  minValue: number;
  description: string;
}

const CHARACTERISTIC_MAPPINGS: Record<string, SkillRequirement[]> = {
  // Caratteristiche offensive
  'veloce': [{ skill: 'velocita', minValue: 75, description: 'veloce' }],
  'rapido': [{ skill: 'velocita', minValue: 75, description: 'rapido' }],
  'tecnico': [{ skill: 'tecnica', minValue: 75, description: 'tecnico' }],
  'dribblatore': [{ skill: 'dribbling', minValue: 75, description: 'bravo nel dribbling' }],
  'che dribbla': [{ skill: 'dribbling', minValue: 70, description: 'bravo nel dribbling' }],
  'goleador': [{ skill: 'tiro', minValue: 70, description: 'pericoloso sotto porta' }],
  'bomber': [{ skill: 'tiro', minValue: 75, description: 'bomber' }],
  'che segna': [{ skill: 'tiro', minValue: 68, description: 'pericoloso' }],

  // Caratteristiche difensive
  'che difende': [{ skill: 'difesa', minValue: 70, description: 'solido difensivamente' }],
  'difensivo': [{ skill: 'difesa', minValue: 70, description: 'affidabile dietro' }],
  'che pressa': [{ skill: 'pressing', minValue: 75, description: 'aggressivo nel pressing' }],
  'aggressivo': [{ skill: 'pressing', minValue: 75, description: 'aggressivo' }],
  'pressing alto': [{ skill: 'pressing', minValue: 78, description: 'ottimo nel pressing alto' }],

  // Caratteristiche fisiche
  'fisico': [{ skill: 'fisico', minValue: 75, description: 'fisicamente forte' }],
  'forte': [{ skill: 'fisico', minValue: 75, description: 'forte fisicamente' }],
  'robusto': [{ skill: 'fisico', minValue: 78, description: 'robusto' }],
  'potente': [{ skill: 'fisico', minValue: 75, description: 'potente' }],

  // Caratteristiche mentali/visione
  'che imposta': [{ skill: 'visione', minValue: 70 }, { skill: 'tecnica', minValue: 70 }],
  'impostazione': [{ skill: 'visione', minValue: 72 }, { skill: 'tecnica', minValue: 68 }],
  'che vede il gioco': [{ skill: 'visione', minValue: 75, description: 'ottima visione di gioco' }],
  'intelligente': [{ skill: 'visione', minValue: 72, description: 'intelligente tatticamente' }],

  // Tipi di giocatore specifici
  'box to box': [
    { skill: 'pressing', minValue: 70, description: 'box-to-box' },
    { skill: 'fisico', minValue: 68 },
    { skill: 'tecnica', minValue: 65 }
  ],
  'box-to-box': [
    { skill: 'pressing', minValue: 70, description: 'box-to-box' },
    { skill: 'fisico', minValue: 68 },
    { skill: 'tecnica', minValue: 65 }
  ],
  'che spinge': [
    { skill: 'velocita', minValue: 72, description: 'propositivo in fase offensiva' },
    { skill: 'fisico', minValue: 65 }
  ],
  'offensivo': [
    { skill: 'velocita', minValue: 68 },
    { skill: 'tecnica', minValue: 68, description: 'propositivo in avanti' }
  ],
  'tutta fascia': [
    { skill: 'velocita', minValue: 75, description: 'tutta fascia' },
    { skill: 'difesa', minValue: 60 },
    { skill: 'fisico', minValue: 70 }
  ],
  'incursore': [
    { skill: 'velocita', minValue: 70, description: 'incursore' },
    { skill: 'dribbling', minValue: 68 }
  ],
};

// Età target patterns
const AGE_PATTERNS: Record<string, { min?: number; max?: number }> = {
  'giovane': { max: 21 },
  'giovanissimo': { max: 19 },
  'under 21': { max: 21 },
  'under 23': { max: 23 },
  'under 25': { max: 25 },
  'esperto': { min: 26 },
  'maturo': { min: 25 },
};

export interface TalentSearchQuery {
  positions: string[];
  characteristics: SkillRequirement[];
  ageRange?: { min?: number; max?: number };
  description: string;
}

/**
 * Parsa una query da campo in requisiti strutturati
 */
export function parseTalentQuery(text: string): TalentSearchQuery | null {
  const lower = text.toLowerCase().trim();
  const positions: string[] = [];
  const characteristics: SkillRequirement[] = [];
  let ageRange: { min?: number; max?: number } | undefined;
  const descriptions: string[] = [];

  // 1. Trova il ruolo
  for (const [keyword, positionList] of Object.entries(ROLE_MAPPINGS)) {
    if (lower.includes(keyword)) {
      positions.push(...positionList);
      descriptions.push(keyword);
      break; // Prendi solo il primo match di ruolo
    }
  }

  // 2. Trova le caratteristiche
  for (const [keyword, requirements] of Object.entries(CHARACTERISTIC_MAPPINGS)) {
    if (lower.includes(keyword)) {
      characteristics.push(...requirements);
      // Aggiungi descrizione se presente
      const withDesc = requirements.find(r => r.description);
      if (withDesc?.description && !descriptions.includes(withDesc.description)) {
        descriptions.push(withDesc.description);
      }
    }
  }

  // 3. Trova età
  for (const [keyword, range] of Object.entries(AGE_PATTERNS)) {
    if (lower.includes(keyword)) {
      ageRange = range;
      descriptions.push(keyword);
      break;
    }
  }

  // Se non abbiamo trovato niente, ritorna null
  if (positions.length === 0 && characteristics.length === 0) {
    return null;
  }

  return {
    positions: [...new Set(positions)], // Rimuovi duplicati
    characteristics,
    ageRange,
    description: descriptions.join(', '),
  };
}

/**
 * Cerca talenti che matchano la query
 */
export function searchTalents(
  data: DNAData,
  query: TalentSearchQuery,
  limit: number = 5
): PlayerMatch[] {
  const matches: Array<{ match: PlayerMatch; score: number }> = [];

  for (const match of data.matches) {
    const player = match.player;
    let score = match.score; // Partiamo dallo score DNA base
    let positionMatch = false;
    let skillsMatch = true;

    // Check posizione
    if (query.positions.length > 0) {
      positionMatch = query.positions.includes(player.primary_position);
      if (!positionMatch) {
        continue; // Skip se la posizione non matcha
      }
      score += 10; // Bonus per position match
    } else {
      positionMatch = true; // No position filter
    }

    // Check skills
    if (query.characteristics.length > 0) {
      const playerSkills = match.breakdown; // Usiamo il breakdown come proxy

      // Per ora usiamo un sistema semplificato basato sullo score
      // In futuro integreremo i dati skills dal JSON completo
      for (const req of query.characteristics) {
        // Bonus se lo score è alto (proxy per buone skills)
        if (match.score >= 80) {
          score += 5;
        }
      }
    }

    // Check età
    if (query.ageRange) {
      const age = player.age;
      if (query.ageRange.max && age > query.ageRange.max) {
        continue;
      }
      if (query.ageRange.min && age < query.ageRange.min) {
        continue;
      }
      score += 5; // Bonus per età target
    }

    // Bonus per underused (più disponibili)
    if (player.is_underused) {
      score += 10;
    }

    matches.push({ match, score });
  }

  // Ordina per score e rimuovi duplicati (stesso giocatore per club diversi)
  const seen = new Set<string>();
  return matches
    .sort((a, b) => b.score - a.score)
    .filter(m => {
      if (seen.has(m.match.player.id)) return false;
      seen.add(m.match.player.id);
      return true;
    })
    .slice(0, limit)
    .map(m => m.match);
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

Prova con query tipo:
• "terzino che spinge"
• "centrocampista box-to-box"
• "ala veloce"
• "difensore bravo in impostazione"`;
  }

  let message = `⚽ <b>Talenti per: ${query.description}</b>\n\n`;

  matches.forEach((match, index) => {
    const player = match.player;
    const scoreEmoji = match.score >= 85 ? '🔥' : match.score >= 70 ? '⚡' : '📊';

    message += `${scoreEmoji} <b>${escapeHtml(player.name)}</b>`;
    message += ` (${player.age} anni)\n`;
    message += `📍 ${player.primary_position} | ${escapeHtml(player.current_team)}\n`;

    if (player.is_underused) {
      message += `⚠️ Solo ${player.minutes_percentage.toFixed(0)}% minuti - cerca spazio!\n`;
    }

    message += `💡 <i>${escapeHtml(match.recommendation)}</i>\n`;

    if (player.transfermarkt_url) {
      message += `🔗 <a href="${player.transfermarkt_url}">Scheda</a>\n`;
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

/**
 * Check se il testo sembra una ricerca talenti
 */
export function isTalentSearchQuery(text: string): boolean {
  const lower = text.toLowerCase();

  // Pattern che indicano una ricerca talenti da campo
  const searchPatterns = [
    /\b(mi serve|cerco|voglio|ho bisogno|mi manca)\b.*\b(un|uno|una)\b/i,
    /\b(terzino|difensore|centrocampista|ala|attaccante|punta|mediano|trequartista)\b.*\b(che|veloce|tecnico|forte|bravo)\b/i,
    /\b(che spinge|box.?to.?box|tutta fascia|che imposta|che pressa)\b/i,
    /\b(giocatore|talento)\b.*\b(veloce|tecnico|fisico|giovane)\b/i,
  ];

  return searchPatterns.some(pattern => pattern.test(lower));
}
