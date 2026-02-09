/**
 * DNA-001: DNA Matching for Telegram Bot
 * Implements complete DNA scoring algorithm with 5 components:
 * - position_fit × 30%
 * - age_fit × 20%
 * - style_fit × 25%
 * - availability × 15%
 * - budget_fit × 10%
 */

import { Env, Opportunity } from './types';
import { fetchData } from './data';

// Club data interface
interface ClubNeed {
  position: string;
  player_type?: string;
  age_min: number;
  age_max: number;
  priority: string;
}

interface ClubDNA {
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

interface MatchBreakdown {
  position: number;
  age: number;
  style: number;
  availability: number;
  budget: number;
}

export interface PlayerMatch {
  player: Opportunity;
  club_id: string;
  club_name: string;
  score: number;
  breakdown: MatchBreakdown;
  recommendation: string;
}

// Cache for club data
let clubsCache: Map<string, ClubDNA> | null = null;
let clubsCacheTime: number = 0;
const CLUBS_CACHE_TTL = 60 * 60 * 1000; // 1 hour

/**
 * Fetch club data from GitHub Pages
 */
async function fetchClubData(env: Env): Promise<Map<string, ClubDNA>> {
  const now = Date.now();
  
  if (clubsCache && (now - clubsCacheTime) < CLUBS_CACHE_TTL) {
    return clubsCache;
  }
  
  try {
    // Try to fetch from the DNA matches endpoint
    const dnaUrl = env.DATA_URL.replace('data.json', 'dna_matches.json');
    const response = await fetch(dnaUrl, {
      headers: { 'Cache-Control': 'no-cache' },
    });
    
    if (!response.ok) {
      console.log('DNA matches not available, using fallback');
      return new Map();
    }
    
    const dnaData = await response.json();
    
    // Extract unique clubs from matches
    const clubs = new Map<string, ClubDNA>();
    if (dnaData.matches) {
      dnaData.matches.forEach((match: any) => {
        if (match.club_id && !clubs.has(match.club_id)) {
          clubs.set(match.club_id, {
            id: match.club_id,
            name: match.club_name,
            category: 'Serie C',
            city: '',
            primary_formation: '4-3-3',
            playing_styles: ['possesso'],
            needs: [],
            budget_type: 'solo_prestiti',
            max_loan_cost: 50,
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

/**
 * Calculate position fit score (30%)
 */
function calculatePositionFit(player: Opportunity, club: ClubDNA): number {
  if (!club.needs || club.needs.length === 0) {
    // Default: neutral score if no specific needs
    return 70;
  }
  
  let bestScore = 0;
  const playerRole = (player.role || player.role_name || '').toLowerCase();
  
  for (const need of club.needs) {
    const needPosition = need.position.toLowerCase();
    
    // Exact match
    if (playerRole.includes(needPosition) || needPosition.includes(playerRole)) {
      let score = 100;
      // Bonus for high priority needs
      if (need.priority === 'alta') {
        score = Math.min(100, score + 10);
      }
      bestScore = Math.max(bestScore, score);
    }
    // Partial match (e.g., "centrocampista" matches "cc")
    else if (
      (playerRole.includes('centrocamp') && needPosition.includes('cc')) ||
      (playerRole.includes('attacc') && needPosition.includes('att')) ||
      (playerRole.includes('difens') && needPosition.includes('dc')) ||
      (playerRole.includes('portier') && needPosition.includes('por'))
    ) {
      bestScore = Math.max(bestScore, 75);
    }
  }
  
  return bestScore > 0 ? bestScore : 40; // Minimum score if no match
}

/**
 * Calculate age fit score (20%)
 */
function calculateAgeFit(player: Opportunity, club: ClubDNA): number {
  const age = player.age;
  if (age == null) return 50; // Neutral if unknown
  
  // Check club needs first
  if (club.needs && club.needs.length > 0) {
    for (const need of club.needs) {
      if (age >= need.age_min && age <= need.age_max) {
        return 100; // Perfect fit
      }
      // Partial fit
      const minDiff = Math.abs(age - need.age_min);
      const maxDiff = Math.abs(age - need.age_max);
      const diff = Math.min(minDiff, maxDiff);
      
      if (diff <= 2) return 80;
      if (diff <= 4) return 60;
    }
  }
  
  // Default age scoring (optimal 22-28)
  if (age >= 22 && age <= 28) return 100;
  if (age >= 20 && age < 22) return 85;
  if (age > 28 && age <= 30) return 75;
  if (age >= 18 && age < 20) return 60;
  if (age > 30 && age <= 32) return 50;
  return Math.max(0, 100 - Math.abs(age - 25) * 10);
}

/**
 * Calculate style fit score (25%)
 */
function calculateStyleFit(player: Opportunity, club: ClubDNA): number {
  if (!club.playing_styles || club.playing_styles.length === 0) {
    return 70; // Neutral
  }
  
  // Map opportunity types to playing styles
  const styleScores: Record<string, number> = {
    'svincolato': 90, // Available immediately
    'prestito': 80,
    'rescissione': 85,
    'mercato': 70,
  };
  
  const oppType = (player.opportunity_type || '').toLowerCase();
  let baseScore = styleScores[oppType] || 70;
  
  // Bonus for youth (matches "possesso" and development style)
  if (player.age && player.age <= 23) {
    baseScore = Math.min(100, baseScore + 10);
  }
  
  return baseScore;
}

/**
 * Calculate availability score (15%)
 */
function calculateAvailability(player: Opportunity): number {
  const oppType = (player.opportunity_type || '').toLowerCase();
  
  if (oppType.includes('svincol')) return 100;
  if (oppType.includes('rescis')) return 95;
  if (oppType.includes('prestit')) return 70;
  if (oppType.includes('scaden')) return 60;
  return 40;
}

/**
 * Calculate budget fit score (10%)
 */
function calculateBudgetFit(player: Opportunity, club: ClubDNA): number {
  // Assume all players in our DB are affordable for these clubs
  // In real implementation, would check player market value vs club.max_loan_cost
  if (club.budget_type === 'solo_prestiti') {
    // Lower budget clubs get boost for loan players
    if (player.opportunity_type?.toLowerCase().includes('prestit')) {
      return 90;
    }
    if (player.opportunity_type?.toLowerCase().includes('svincol')) {
      return 100; // Free is best
    }
  }
  return 80;
}

/**
 * Calculate complete DNA match score
 */
function calculateDNAMatch(player: Opportunity, club: ClubDNA): { score: number; breakdown: MatchBreakdown } {
  const breakdown: MatchBreakdown = {
    position: calculatePositionFit(player, club),
    age: calculateAgeFit(player, club),
    style: calculateStyleFit(player, club),
    availability: calculateAvailability(player),
    budget: calculateBudgetFit(player, club),
  };
  
  // Weighted sum according to DNA-001 spec
  const score = Math.round(
    breakdown.position * 0.30 +
    breakdown.age * 0.20 +
    breakdown.style * 0.25 +
    breakdown.availability * 0.15 +
    breakdown.budget * 0.10
  );
  
  return { score, breakdown };
}

/**
 * Generate recommendation text based on match
 */
function generateRecommendation(player: Opportunity, breakdown: MatchBreakdown): string {
  const parts: string[] = [];
  
  // Role description
  const roleDesc = player.role_name || player.role || 'Giocatore';
  parts.push(`${roleDesc}`);
  
  // Strongest attribute
  const attrs = [
    { name: 'disponibilità immediata', score: breakdown.availability },
    { name: 'adattamento tattico', score: breakdown.style },
    { name: 'esperienza nella categoria', score: breakdown.position },
    { name: 'età ideale', score: breakdown.age },
  ];
  
  const topAttr = attrs.sort((a, b) => b.score - a.score)[0];
  if (topAttr.score >= 80) {
    parts.push(`con ${topAttr.name}`);
  }
  
  // Opportunity type
  if (player.opportunity_type?.toLowerCase().includes('svincol')) {
    parts.push('disponibile a parametro zero');
  } else if (player.opportunity_type?.toLowerCase().includes('prestit')) {
    parts.push('disponibile in prestito');
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
  
  // Try to find exact club match
  let club: ClubDNA | undefined;
  const query = clubQuery.toLowerCase().trim();
  
  for (const [id, c] of clubs) {
    if (id.toLowerCase() === query || c.name.toLowerCase().includes(query)) {
      club = c;
      break;
    }
  }
  
  // If no club found, create a generic one
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
  
  // Calculate DNA match for all opportunities
  const matches: PlayerMatch[] = opportunities.map(o => {
    const { score, breakdown } = calculateDNAMatch(o, club!);
    return {
      player: o,
      club_id: club!.id,
      club_name: club!.name,
      score,
      breakdown,
      recommendation: generateRecommendation(o, breakdown),
    };
  });
  
  // Sort by DNA score and return top matches
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
  // Create a generic "Serie C" club profile
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
  
  // Calculate DNA match for all opportunities
  const matches: PlayerMatch[] = opportunities
    .filter(o => o.age != null && o.age <= 23) // Focus on young players
    .map(o => {
      const { score, breakdown } = calculateDNAMatch(o, genericClub);
      return {
        player: o,
        club_id: 'serie_c',
        club_name: 'Serie C',
        score,
        breakdown,
        recommendation: generateRecommendation(o, breakdown),
      };
    });
  
  // Filter by min DNA score and return top matches
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
  
  // Show score breakdown
  if (match.breakdown) {
    msg += `\n📊 Score Breakdown:\n`;
    msg += `  • Posizione: ${match.breakdown.position}%\n`;
    msg += `  • Età: ${match.breakdown.age}%\n`;
    msg += `  • Stile: ${match.breakdown.style}%\n`;
    msg += `  • Disponibilità: ${match.breakdown.availability}%\n`;
    msg += `  • Budget: ${match.breakdown.budget}%\n`;
  }

  msg += `\n💡 <i>${escapeHtml(match.recommendation)}</i>`;

  if (o.source_url) {
    msg += `\n🔗 <a href="${o.source_url}">Fonte: ${o.source_name}</a>`;
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
  
  return `🧬 <b>OB1 Radar - Stats</b>\n\n📊 Database:\n• ${opportunities.length} giocatori monitorati\n• ${young} giovani talenti (Under 23)\n• ${hot} opportunità prioritari (Score 80+)\n\n━━━━━━━━━━━━━━━━━━━━\n🌐 <a href="https://mtornani.github.io/ob1-serie-c/">Dashboard</a>
`;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}