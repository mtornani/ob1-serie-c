/**
 * DNA-001: DNA Matching for Telegram Bot
 * REFACTORED: Now uses only data.json as the single source of truth.
 */

import { Env, Opportunity } from './types';
import { fetchData } from './data';

export interface PlayerMatch {
  player: Opportunity;
  club_id: string;
  club_name: string;
  score: number;
  recommendation: string;
}

/**
 * Simplified DNA Matching:
 * Since we are using only data.json, we simulate "matching" by 
 * filtering high-score opportunities that fit the club search.
 */
export async function fetchDNAData(env: Env): Promise<Opportunity[] | null> {
  const data = await fetchData(env);
  return data?.opportunities || null;
}

export function getMatchesForClub(opportunities: Opportunity[], clubQuery: string, limit: number = 5): PlayerMatch[] {
  const searchTerm = clubQuery.toLowerCase().trim();
  
  // Search for players that might fit the club
  // 1. Mention the club in summary
  // 2. Are currently in the club (to show "internal" opportunities/news)
  // 3. Just high score players if no specific match found
  
  const clubMatches = opportunities.filter(o => {
    const text = [
      o.player_name,
      o.current_club || '',
      o.summary || '',
      ...(o.previous_clubs || [])
    ].join(' ').toLowerCase();
    
    return text.includes(searchTerm);
  });

  // If we found specific mentions, prioritize them
  if (clubMatches.length > 0) {
    return clubMatches
      .sort((a, b) => b.ob1_score - a.ob1_score)
      .slice(0, limit)
      .map(o => ({
        player: o,
        club_id: searchTerm,
        club_name: clubQuery,
        score: o.ob1_score,
        recommendation: `Profilo interessante per il progetto ${clubQuery}.`
      }));
  }

  // Otherwise, suggest top players that fit the "general" DNA of a C club (young/motivated)
  return opportunities
    .filter(o => o.age <= 25 && o.ob1_score >= 70)
    .sort((a, b) => b.ob1_score - a.ob1_score)
    .slice(0, limit)
    .map(o => ({
      player: o,
      club_id: searchTerm,
      club_name: clubQuery,
      score: o.ob1_score,
      recommendation: `Talento giovane (Under 25) con alto potenziale per la categoria.`
    }));
}

export function getTopMatches(opportunities: Opportunity[], minScore: number = 75, limit: number = 10): PlayerMatch[] {
  // Top "talenti" are young players (Under 23) with high OB1 score
  return opportunities
    .filter(o => o.age <= 23 && o.ob1_score >= minScore)
    .sort((a, b) => b.ob1_score - a.ob1_score)
    .slice(0, limit)
    .map(o => ({
      player: o,
      club_id: 'general',
      club_name: 'Serie C',
      score: o.ob1_score,
      recommendation: 'Top prospect monitorato dai nostri osservatori.'
    }));
}

export function formatDNAMatch(match: PlayerMatch): string {
  const o = match.player;
  const scoreEmoji = o.ob1_score >= 85 ? '🔥' : o.ob1_score >= 70 ? '⚡' : '📊';

  let msg = `${scoreEmoji} <b>${escapeHtml(o.player_name)}</b> (${o.ob1_score}%)\n`;
  msg += `📍 ${o.role_name || o.role} | ${o.age} anni\n`;
  
  if (o.current_club) {
    msg += `🏟️ ${escapeHtml(o.current_club)}\n`;
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
  const young = opportunities.filter(o => o.age <= 23).length;
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