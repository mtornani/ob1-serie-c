/**
 * DNA-001: DNA Matching for Telegram Bot
 * Implements realistic scoring algorithm from scorer.py v2.0:
 * - position_fit × 25% (ruolo)
 * - age_fit × 15% (età)
 * - style_fit × 15% (tattico)
 * - availability × 20% (disponibilità)
 * - budget_fit × 20% (costo)
 * - level_fit × 5% (livello categoria)
 */

import { Env, Opportunity } from './types';
import { fetchData } from './data';

// Position compatibility mapping (from scorer.py POSITION_COMPATIBILITY)
const POSITION_COMPATIBILITY: Record<string, string[]> = {
  'DC': ['MED'],
  'TS': ['ES'],
  'TD': ['ED'],
  'MED': ['CC'],
  'CC': ['MED', 'TRQ'],
  'TRQ': ['CC'],
  'ES': ['TS', 'AS'],
  'ED': ['TD', 'AD'],
  'AS': ['ES'],
  'AD': ['ED'],
  'ATT': ['PC', 'AS', 'AD'],
  'PC': ['ATT'],
  'POR': [],
};

// Category value caps (in thousands €) - from scorer.py CATEGORY_VALUE_CAPS
const CATEGORY_VALUE_CAPS: Record<string, number> = {
  'Campionato Sammarinese': 300,
  'Serie D': 500,
  'Serie C': 2000,
  'Serie B': 10000,
};

// Weight values for scoring
const WEIGHTS = {
  position: 0.25,
  age: 0.15,
  style: 0.15,
  availability: 0.20,
  budget: 0.20,
  level: 0.05,
};

export interface ClubNeed {
  position: string;
  player_type?: string;
  age_min: number;
  age_max: number;
  priority: string;
}

export interface ClubDNA {
  id: string;
  name: string;
  category: string;
  city: string;
  primary_formation: string;
  playing_styles: string[];
  needs: ClubNeed[];
  budget_type: string;
  max_loan_cost: number;
}

export interface MatchBreakdown {
  position: number;
  age: number;
  style: number;
  availability: number;
  budget: number;
  level: number;
}

interface MatchWithNeed {
  score: number;
  breakdown: MatchBreakdown;
  matchedNeed?: ClubNeed;
}

export interface PlayerMatch {
  player: Opportunity;
  club_id: string;
  club_name: string;
  score: number;
  breakdown: MatchBreakdown;
  recommendation: string;
  matched_need?: ClubNeed;
}

// Cache for club data
let clubsCache: Map<string, ClubDNA> | null = null;
let clubsCacheTime: number = 0;
const CLUBS_CACHE_TTL = 60 * 60 * 1000;

export async function fetchClubData(env: Env): Promise<Map<string, ClubDNA>> {
  const now = Date.now();
  
  if (clubsCache && (now - clubsCacheTime) < CLUBS_CACHE_TTL) {
    return clubsCache;
  }
  
  try {
    const dnaUrl = env.DATA_URL.replace('data.json', 'dna_matches.json');
    const response = await fetch(dnaUrl, {
      headers: { 'Cache-Control': 'no-cache' },
    });
    
    if (!response.ok) {
      console.log('DNA matches not available, using fallback');
      return new Map();
    }
    
    const dnaData = await response.json() as { matches?: any[]; clubs?: any[] };

    const clubs = new Map<string, ClubDNA>();

    // Prefer clubs[] array (v2.1+), fall back to extracting from matches[]
    if (dnaData.clubs && Array.isArray(dnaData.clubs)) {
      for (const club of dnaData.clubs) {
        if (club.id) {
          clubs.set(club.id, {
            id: club.id,
            name: club.name || club.id,
            category: club.category || 'Serie C',
            city: club.city || '',
            primary_formation: club.primary_formation || '4-3-3',
            playing_styles: club.playing_styles || ['possesso'],
            needs: club.needs || [],
            budget_type: club.budget_type || 'solo_prestiti',
            max_loan_cost: club.max_loan_cost || 50,
          });
        }
      }
    } else if (dnaData.matches) {
      dnaData.matches.forEach((match: any) => {
        if (match.club_id && !clubs.has(match.club_id)) {
          clubs.set(match.club_id, {
            id: match.club_id,
            name: match.club_name,
            category: match.category || 'Serie C',
            city: match.city || '',
            primary_formation: match.primary_formation || '4-3-3',
            playing_styles: match.playing_styles || ['possesso'],
            needs: match.needs || [],
            budget_type: match.budget_type || 'solo_prestiti',
            max_loan_cost: match.max_loan_cost || 50,
          });
        }
      });
    }
    
    clubsCache = clubs;
    clubsCacheTime = now;
    return clubs;
  } catch (error) {
    console.error('Error fetching club data:', error);
    return clubsCache || new Map();
  }
}

 function calculatePositionFit(player: Opportunity, club: ClubDNA): { score: number; matchedNeed?: ClubNeed } {
   // If no needs defined, assign neutral score based on role name
   if (!club.needs || club.needs.length === 0) {
     const role = (player.role || player.role_name || '').toUpperCase();
     // Default scores for common positions
     const defaultScores: Record<string, number> = {
       'CC': 70, 'CCM': 70, 'CCO': 70, 'CCV': 70,
       'DC': 70, 'DCM': 70, 'DCL': 70,
       'TS': 65, 'TD': 65,
       'ES': 65, 'ED': 65,
       'AS': 60, 'AD': 60,
       'ATT': 60, 'PC': 60,
       'PO': 90,
     };
     return { score: defaultScores[role] || 50, matchedNeed: undefined };
   }

   const best = { score: 0, matchedNeed: undefined as ClubNeed | undefined };

  for (const need of club.needs) {
    let score = 0;
    const needPosition = need.position.toUpperCase();
    const playerPrimary = (player.role || player.role_name || '').toUpperCase();

    if (playerPrimary === needPosition) {
      score = 100;
    } else if (POSITION_COMPATIBILITY[playerPrimary]?.includes(needPosition)) {
      score = 40;
    } else if (POSITION_COMPATIBILITY[needPosition]?.includes(playerPrimary)) {
      score = 35;
    }

    if (need.priority === 'alta' && score >= 70) {
      score = Math.min(100, score + 5);
    }

    if (score > best.score) {
      best.score = score;
      best.matchedNeed = need;
    }
  }

  return best;
}

function calculateAgeFit(player: Opportunity, matchedNeed?: ClubNeed): number {
  const age = player.age;
  
  if (age == null) {
    return 50;
  }

  if (matchedNeed) {
    const { age_min, age_max } = matchedNeed;
    
    if (age >= age_min && age <= age_max) {
      return 100;
    } else if (age < age_min) {
      return Math.max(0, 100 - (age_min - age) * 25);
    } else {
      return Math.max(0, 100 - (age - age_max) * 25);
    }
  }

  if (age >= 20 && age <= 25) return 100;
  else if (age < 20) return 80;
  else if (age > 25 && age <= 28) return 60;
  else return Math.max(0, 100 - Math.abs(age - 23) * 15);
}

function calculateStyleFit(player: Opportunity, club: ClubDNA): number {
  if (!club.playing_styles || club.playing_styles.length === 0) {
    return 50;
  }

  const styleSkills: Record<string, string[]> = {
    'pressing_alto': ['pressing', 'fisico', 'velocita'],
    'possesso': ['tecnica', 'visione'],
    'transizioni': ['velocita', 'dribbling', 'tecnica'],
    'difesa_bassa': ['difesa', 'fisico'],
    'gioco_diretto': ['fisico', 'tiro'],
    'gioco_aereo': ['fisico'],
    'gioco_sulle_fasce': ['velocita', 'dribbling', 'tecnica'],
    'mix_sammarinese': ['tecnica', 'visione', 'velocita', 'dribbling'],
  };

  let totalScore = 0;
  let count = 0;

  for (const style of club.playing_styles) {
    const requiredSkills = styleSkills[style] || [];
    
    if (requiredSkills.length > 0) {
      totalScore += 40;
      count++;
    }
  }

  if (count === 0) {
    return 50;
  }

  return Math.round(totalScore / count);
}

function calculateAvailability(player: Opportunity): number {
  const oppType = (player.opportunity_type || '').toLowerCase();
  
  if (oppType.includes('svincol')) return 100;
  else if (oppType.includes('rescis')) return 95;
  else if (oppType.includes('prestit')) return 70;
  else if (oppType.includes('scaden')) return 60;
  else return 30;
}

function calculateBudgetFit(player: Opportunity, club: ClubDNA): number {
   const estimatedLoanCost = player.estimated_loan_cost || (player.market_value ? Math.round(player.market_value * 0.12) : 0);
   const effectiveCost = estimatedLoanCost || 0;

  if (effectiveCost === 0 && (!player.market_value || player.market_value === 0)) {
    return 50;
  }

  const maxBudget = club.max_loan_cost;

  if (maxBudget <= 0) return 30;
  else if (effectiveCost <= maxBudget) return 100;
  else if (effectiveCost <= maxBudget * 1.3) return 70;
  else if (effectiveCost <= maxBudget * 2) return 35;
  else if (effectiveCost <= maxBudget * 3) return 15;
  else return 5;
}

function calculateLevelFit(player: Opportunity, club: ClubDNA): number {
  const category = club.category;
  const mv = player.market_value || 0;

  if (category === 'Campionato Sammarinese') {
    if (mv === 0) return 60;
    else if (mv <= 100) return 100;
    else if (mv <= 300) return 70;
    else if (mv <= 500) return 40;
    else if (mv <= 1000) return 20;
    else return 5;
  } else if (category === 'Serie D') {
    if (mv === 0) return 60;
    else if (mv <= 300) return 100;
    else if (mv <= 800) return 70;
    else if (mv <= 1500) return 40;
    else return 15;
  } else if (category === 'Serie C') {
    if (mv === 0) return 60;
    else if (mv <= 500) return 90;
    else if (mv <= 1500) return 100;
    else if (mv <= 3000) return 60;
    else if (mv <= 5000) return 30;
    else return 10;
  } else {
    return 50;
  }
}

function checkBlockingFilters(player: Opportunity, club: ClubDNA): { blocked: boolean; reason: string } {
  const oppType = (player.opportunity_type || '').toLowerCase();
  
  if (oppType.includes('incedibile')) {
    return { blocked: true, reason: 'Giocatore non disponibile (incedibile)' };
  }

  const valueCap = CATEGORY_VALUE_CAPS[club.category] || 5000;
  if (player.market_value && player.market_value > valueCap) {
    return { 
      blocked: true, 
      reason: `Valore di mercato (${player.market_value}k€) troppo alto per ${club.category}` 
    };
  }

  const positionResult = calculatePositionFit(player, club);
  if (positionResult.score === 0) {
    return { blocked: true, reason: 'Nessun ruolo compatibile con le esigenze del club' };
  }

  return { blocked: false, reason: '' };
}

export function calculateDNAMatch(player: Opportunity, club: ClubDNA): MatchWithNeed {
  const blocking = checkBlockingFilters(player, club);
  
  if (blocking.blocked) {
    return {
      score: 0,
      breakdown: { position: 0, age: 0, style: 0, availability: 0, budget: 0, level: 0 },
      matchedNeed: undefined,
    };
  }

  const positionResult = calculatePositionFit(player, club);
  const ageFit = calculateAgeFit(player, positionResult.matchedNeed);
  const styleFit = calculateStyleFit(player, club);
  const availability = calculateAvailability(player);
  const budgetFit = calculateBudgetFit(player, club);
  const levelFit = calculateLevelFit(player, club);

  const breakdown: MatchBreakdown = {
    position: positionResult.score,
    age: ageFit,
    style: styleFit,
    availability: availability,
    budget: budgetFit,
    level: levelFit,
  };

  const score = Math.round(
    breakdown.position * WEIGHTS.position +
    breakdown.age * WEIGHTS.age +
    breakdown.style * WEIGHTS.style +
    breakdown.availability * WEIGHTS.availability +
    breakdown.budget * WEIGHTS.budget +
    breakdown.level * WEIGHTS.level
  );

  return { score, breakdown, matchedNeed: positionResult.matchedNeed };
}

export function generateRecommendation(player: Opportunity, breakdown: MatchBreakdown, matchedNeed?: ClubNeed): string {
   const parts: string[] = [];
   
   const roleDesc = player.role_name || player.role || 'Giocatore';
   const oppType = player.opportunity_type || 'Mercato';
   const currentClub = player.current_club || 'Libero';
   const estimatedLoanCost = player.estimated_loan_cost || (player.market_value ? Math.round(player.market_value * 0.12) : 0);
   
   if (player.ob1_score >= 80) {
     parts.push(`${roleDesc} di qualità **HOT**`);
   } else if (player.ob1_score >= 60) {
     parts.push(`${roleDesc} **WARM** da valutare`);
   } else {
     parts.push(`${roleDesc} opportunità standard`);
   }
   
   if (breakdown.position >= 85) {
     parts.push(`ruolo esatto cercato (${matchedNeed?.position.toUpperCase() || 'comune'})`);
   } else if (breakdown.position >= 60) {
     parts.push(`ruolo compatibile con flessibilità`);
   }
   
   if (breakdown.age >= 80) {
     if (player.age && player.age >= 20 && player.age <= 25) {
       parts.push(`età perfetta per Serie C (${player.age} anni)`);
     } else if (player.age && player.age < 23) {
       parts.push(`giovane talento in crescita (${player.age} anni)`);
     }
   } else if (player.age && player.age > 28) {
     parts.push(`esperienza matura per squadra di vertice`);
   }
   
   if (breakdown.style >= 70) {
     parts.push(`adeguato allo stile possesso/transizioni`);
   } else if (breakdown.style < 50) {
     parts.push(`stile differente richiede adattamento`);
   }
   
   if (breakdown.availability >= 80) {
     if (oppType.toLowerCase().includes('svincol')) {
       parts.push(`disponibile immediatamente (svincolato)`);
     } else if (oppType.toLowerCase().includes('prestit')) {
       parts.push(`disponibile in prestito`);
     }
   } else if (breakdown.availability >= 60) {
     parts.push(`disponibilità parziale da verificare`);
   }
   
   if (breakdown.budget >= 80) {
     if (estimatedLoanCost > 0 && estimatedLoanCost <= 50) {
       parts.push(`costo sostenibile (${estimatedLoanCost}k€/anno)`);
     } else if (estimatedLoanCost > 0 && estimatedLoanCost <= 100) {
       parts.push(`budget medio da valutare`);
     } else if (estimatedLoanCost > 100) {
       parts.push(`investimento significativo richiesto`);
     } else {
       parts.push(`free transfer o costo minimo`);
     }
   } else if (breakdown.budget <= 35) {
     parts.push(`costo elevato per budget club`);
   }
   
   if (breakdown.level >= 80) {
     parts.push(`calibrato per categoria (Serie C/Serie D)`);
   } else if (breakdown.level < 40) {
     parts.push(`valore di mercato alto per categoria`);
   }
   
   if (parts.length <= 2) {
     parts.push(`operazione fattibile su base tecnica`);
   }
   
   return parts.join(', ');
}

export async function fetchDNAData(env: Env): Promise<Opportunity[] | null> {
  const data = await fetchData(env);
  return data?.opportunities || null;
}

export async function getMatchesForClub(
  env: Env,
  opportunities: Opportunity[],
  clubQuery: string,
  limit: number = 5
): Promise<PlayerMatch[]> {
  const clubs = await fetchClubData(env);
  
  let club: ClubDNA | undefined;
  const query = clubQuery.toLowerCase().trim();
  
  for (const [id, c] of clubs) {
    if (id.toLowerCase() === query || c.name.toLowerCase().includes(query)) {
      club = c;
      break;
    }
  }
  
  if (!club) {
    club = {
      id: query,
      name: clubQuery,
      category: 'Serie C',
      city: '',
      primary_formation: '4-3-3',
      playing_styles: ['possesso'],
      needs: [],
      budget_type: 'solo_prestiti',
      max_loan_cost: 50,
    };
  }
  
  const matches: PlayerMatch[] = opportunities.map(o => {
    const { score, breakdown, matchedNeed } = calculateDNAMatch(o, club!);
    return {
      player: o,
      club_id: club!.id,
      club_name: club!.name,
      score,
      breakdown,
      recommendation: generateRecommendation(o, breakdown, matchedNeed),
      matched_need: matchedNeed,
    };
  });
  
  return matches
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}

export async function getTopMatches(
  env: Env,
  opportunities: Opportunity[],
  minScore: number = 75,
  limit: number = 10
): Promise<PlayerMatch[]> {
  const genericClub: ClubDNA = {
    id: 'serie_c',
    name: 'Serie C',
    category: 'Serie C',
    city: '',
    primary_formation: '4-3-3',
    playing_styles: ['possesso', 'transizioni'],
    needs: [
      { position: 'cc', age_min: 20, age_max: 28, priority: 'media' },
      { position: 'att', age_min: 20, age_max: 28, priority: 'media' },
      { position: 'dc', age_min: 21, age_max: 30, priority: 'media' },
    ],
    budget_type: 'solo_prestiti',
    max_loan_cost: 50,
  };
  
  const matches: PlayerMatch[] = opportunities
    .filter(o => o.age != null && o.age <= 23)
    .map(o => {
      const { score, breakdown, matchedNeed } = calculateDNAMatch(o, genericClub);
      return {
        player: o,
        club_id: 'serie_c',
        club_name: 'Serie C',
        score,
        breakdown,
        recommendation: generateRecommendation(o, breakdown, matchedNeed),
        matched_need: matchedNeed,
      };
    });
  
  return matches
    .filter(m => m.score >= minScore)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}

export function formatDNAMatch(match: PlayerMatch): string {
  const o = match.player;
  const score = match.score;
  const scoreEmoji = score >= 85 ? '🔥' : score >= 70 ? '⚡' : '📊';

  let msg = `${scoreEmoji} <b>${escapeHtml(o.player_name)}</b> - DNA Match: ${score}%\n`;
  msg += `📍 ${o.role_name || o.role} | ${o.age} anni\n`;
  
  if (o.current_club) {
    msg += `🏟️ ${escapeHtml(o.current_club)}\n`;
  }

  msg += `\n📊 Score Breakdown:\n`;
  msg += `  • Posizione: ${match.breakdown.position}%\n`;
  msg += `  • Età: ${match.breakdown.age}%\n`;
  msg += `  • Stile: ${match.breakdown.style}%\n`;
  msg += `  • Disponibilità: ${match.breakdown.availability}%\n`;
  msg += `  • Budget: ${match.breakdown.budget}%\n`;
  msg += `  • Livello: ${match.breakdown.level}%\n`;

   msg += `\n💡 <i>${escapeHtml(match.recommendation)}</i>`;

   // Try to show Transfermarkt link if available
   const tmUrl = (o as any).transfermarkt_url;
   if (tmUrl) {
     msg += `\n⚽ <a href="${tmUrl}">👤 Profilo Transfermarkt</a>`;
   } else if (o.source_url) {
     msg += `\n🔗 <a href="${o.source_url}">📊 ${o.source_name}</a>`;
   }

   return msg;
}

export function formatDNAMatchList(matches: PlayerMatch[], title: string, clubName?: string): string {
  if (matches.length === 0) {
    return `${title}\n\n😔 Nessun match trovato.`;
  }

  let message = `${title}\n`;

  if (clubName && clubName !== 'Serie C') {
    message += `🎯 Focus: <b>${escapeHtml(clubName)}</b>\n`;
  }

  message += '\n';

  matches.forEach((match, index) => {
    message += formatDNAMatch(match);
    if (index < matches.length - 1) {
      message += '\n\n───────────────\n\n';
    }
  });

  message += '\n\n━━━━━━━━━━━━━━━━━━━━';
  message += '\n🌐 <a href="https://mtornani.github.io/ob1-serie-c/">Dashboard completa</a>';

  return message;
}

export function formatDNAStats(opportunities: Opportunity[]): string {
  const young = opportunities.filter(o => o.age != null && o.age <= 23).length;
  const hot = opportunities.filter(o => o.ob1_score >= 80).length;
  
  return `🧬 <b>OB1 Radar - Stats</b>\n\n📊 Database:\n• ${opportunities.length} giocatori monitorati\n• ${young} giovani talenti (Under 23)\n• ${hot} opportunità prioritari (Score 80+)\n\n━━━━━━━━━━━━━━━━━━━━\n🌐 <a href="https://mtornani.github.io/ob1-serie-c/">Dashboard</a>\n`;
}

function escapeHtml(text: string): string {
   return text
     .replace(/&/g, '&amp;')
     .replace(/</g, '&lt;')
     .replace(/>/g, '&gt;')
     .replace(/"/g, '&quot;')
     .replace(/'/g, '&#039;');
}
