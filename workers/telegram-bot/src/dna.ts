/**
 * DNA-001: DNA Matching for Telegram Bot
 *
 * Handles DNA matching data fetching and formatting for the bot.
 */

import { Env } from './types';

const DNA_DATA_URL = 'https://mtornani.github.io/ob1-serie-c/dna_matches.json';

// Cache for DNA data
let cachedDnaData: DNAData | null = null;
let dnaCacheTime: number = 0;
const DNA_CACHE_TTL = 10 * 60 * 1000; // 10 minutes

export interface PlayerMatch {
  player: {
    id: string;
    name: string;
    age: number;
    primary_position: string;
    parent_club: string;
    current_team: string;
    minutes_percentage: number;
    is_underused: boolean;
    market_value: number;
    transfermarkt_url: string;
  };
  club_id: string;
  club_name: string;
  score: number;
  breakdown: {
    position: number;
    age: number;
    style: number;
    availability: number;
    budget: number;
  };
  recommendation: string;
}

export interface DNAData {
  matches: PlayerMatch[];
  stats: {
    total_players: number;
    total_clubs: number;
    parent_clubs: string[];
    underused_players: number;
  };
  generated_at: string;
}

export async function fetchDNAData(): Promise<DNAData | null> {
  const now = Date.now();

  // Return cached if valid
  if (cachedDnaData && (now - dnaCacheTime) < DNA_CACHE_TTL) {
    return cachedDnaData;
  }

  try {
    const response = await fetch(DNA_DATA_URL, {
      headers: { 'Cache-Control': 'no-cache' },
    });

    if (!response.ok) {
      console.error('Failed to fetch DNA data:', response.status);
      return cachedDnaData;
    }

    const data: DNAData = await response.json();
    cachedDnaData = data;
    dnaCacheTime = now;

    return data;
  } catch (error) {
    console.error('Error fetching DNA data:', error);
    return cachedDnaData;
  }
}

export function getMatchesForClub(data: DNAData, clubId: string, limit: number = 5): PlayerMatch[] {
  return data.matches
    .filter(m => m.club_id === clubId)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}

export function getTopMatches(data: DNAData, minScore: number = 80, limit: number = 10): PlayerMatch[] {
  // Get unique matches (one per player-club combo)
  const seen = new Set<string>();
  const unique: PlayerMatch[] = [];

  for (const m of data.matches) {
    const key = `${m.player.id}_${m.club_id}`;
    if (!seen.has(key) && m.score >= minScore) {
      seen.add(key);
      unique.push(m);
    }
  }

  return unique
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}

export function getAvailableClubs(data: DNAData): string[] {
  const clubs = new Set<string>();
  for (const m of data.matches) {
    clubs.add(m.club_id);
  }
  return Array.from(clubs);
}

export function formatDNAMatch(match: PlayerMatch): string {
  const scoreEmoji = match.score >= 85 ? '🔥' : match.score >= 70 ? '⚡' : '📊';
  const player = match.player;

  let msg = `${scoreEmoji} <b>${escapeHtml(player.name)}</b> (${match.score}%)\n`;
  msg += `📍 ${player.primary_position} | ${player.age} anni\n`;
  msg += `🏟️ ${escapeHtml(player.current_team)}\n`;

  if (player.is_underused) {
    msg += `⚠️ Solo ${player.minutes_percentage.toFixed(0)}% minuti giocati\n`;
  }

  msg += `\n💡 <i>${escapeHtml(match.recommendation)}</i>`;

  if (player.transfermarkt_url) {
    msg += `\n🔗 <a href="${player.transfermarkt_url}">Transfermarkt</a>`;
  }

  return msg;
}

export function formatDNAMatchList(matches: PlayerMatch[], title: string, clubName?: string): string {
  if (matches.length === 0) {
    return `${title}\n\n😔 Nessun match trovato.`;
  }

  let message = `${title}\n`;

  if (clubName) {
    message += `🎯 Per: <b>${escapeHtml(clubName)}</b>\n`;
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

export function formatDNAStats(data: DNAData): string {
  return `🧬 <b>DNA Matching - Stats</b>

📊 Database:
• ${data.stats.total_players} giocatori monitorati
• ${data.stats.total_clubs} club con profilo
• ${data.stats.underused_players} talenti underused

🏟️ <b>Squadre B monitorate:</b>
${data.stats.parent_clubs.map(c => `• ${c}`).join('\n')}

🕐 Aggiornamento: ${formatDate(data.generated_at)}

━━━━━━━━━━━━━━━━━━━━
🌐 <a href="https://mtornani.github.io/ob1-serie-c/">Dashboard</a>`;
}

function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateString;
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
