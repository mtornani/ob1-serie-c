import { DashboardData, Opportunity, Env } from './types';

// Cache data for 5 minutes to reduce GitHub Pages load
let cachedData: DashboardData | null = null;
let cacheTime: number = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

export async function fetchData(env: Env): Promise<DashboardData | null> {
  const now = Date.now();

  // Return cached data if still valid
  if (cachedData && (now - cacheTime) < CACHE_TTL) {
    return cachedData;
  }

  try {
    const response = await fetch(env.DATA_URL, {
      headers: {
        'Cache-Control': 'no-cache',
      },
    });

    if (!response.ok) {
      console.error('Failed to fetch data:', response.status);
      return cachedData; // Return stale cache if available
    }

    const data: DashboardData = await response.json();
    cachedData = data;
    cacheTime = now;

    return data;
  } catch (error) {
    console.error('Error fetching data:', error);
    return cachedData; // Return stale cache if available
  }
}

export function filterHot(opportunities: Opportunity[]): Opportunity[] {
  return opportunities
    .filter(o => o.ob1_score >= 80)
    .sort((a, b) => b.ob1_score - a.ob1_score);
}

export function filterWarm(opportunities: Opportunity[]): Opportunity[] {
  return opportunities
    .filter(o => o.ob1_score >= 60 && o.ob1_score < 80)
    .sort((a, b) => b.ob1_score - a.ob1_score);
}

export function filterCold(opportunities: Opportunity[]): Opportunity[] {
  return opportunities
    .filter(o => o.ob1_score < 60)
    .sort((a, b) => b.ob1_score - a.ob1_score);
}

export function searchOpportunities(opportunities: Opportunity[], query: string): Opportunity[] {
  const lowerQuery = query.toLowerCase().trim();

  if (!lowerQuery) return [];

  return opportunities.filter(o => {
    const searchable = [
      o.player_name,
      o.role_name || o.role,
      o.opportunity_type,
      o.nationality || '',
      o.second_nationality || '',
      ...(o.previous_clubs || []),
    ].join(' ').toLowerCase();

    // Special handling for "comunitario" or "ue" keywords
    if (lowerQuery.includes('comunitario') || lowerQuery.includes('passaporto eu')) {
      const isEU = isEuropean(o.nationality) || isEuropean(o.second_nationality);
      if (!isEU) return false;
      // If query was ONLY "comunitario", return true. If it had more, continue filtering.
      if (lowerQuery.trim() === 'comunitario') return true;
    }

    return searchable.includes(lowerQuery);
  }).sort((a, b) => b.ob1_score - a.ob1_score);
}

/**
 * Basic list of EU/EEA countries for passport check
 */
function isEuropean(country?: string): boolean {
  if (!country) return false;
  const euCountries = [
    'italia', 'spagna', 'francia', 'germania', 'portogallo', 'belgio', 'olanda', 
    'austria', 'grecia', 'polonia', 'romania', 'bulgaria', 'croazia', 'danimarca',
    'finlandia', 'irlanda', 'lussemburgo', 'malta', 'svezia', 'repubblica ceca',
    'slovacchia', 'slovenia', 'ungheria', 'estonia', 'lettonia', 'lituania', 'cipro'
  ];
  return euCountries.includes(country.toLowerCase().trim());
}

export function getStats(opportunities: Opportunity[]): { total: number; hot: number; warm: number; cold: number } {
  return {
    total: opportunities.length,
    hot: opportunities.filter(o => o.ob1_score >= 80).length,
    warm: opportunities.filter(o => o.ob1_score >= 60 && o.ob1_score < 80).length,
    cold: opportunities.filter(o => o.ob1_score < 60).length,
  };
}

export function findOpportunityById(opportunities: Opportunity[], id: string): Opportunity | undefined {
  return opportunities.find(o => o.id === id);
}

// ============================================================================
// NLP-001: Advanced filtering for natural language queries
// ============================================================================

export interface FilterOptions {
  role?: string;
  type?: string;
  ageMin?: number;
  ageMax?: number;
  query?: string;
  minScore?: number;
  maxScore?: number;
}

/**
 * Filter opportunities based on multiple criteria
 */
export function filterOpportunities(opportunities: Opportunity[], filters: FilterOptions): Opportunity[] {
  return opportunities.filter(o => {
    // Role filter
    if (filters.role) {
      const roleNormalized = (o.role_name || o.role || '').toLowerCase();
      if (!roleNormalized.includes(filters.role.toLowerCase())) {
        return false;
      }
    }

    // Type filter
    if (filters.type) {
      if (o.opportunity_type.toLowerCase() !== filters.type.toLowerCase()) {
        return false;
      }
    }

    // Age filter
    if (filters.ageMin && o.age < filters.ageMin) {
      return false;
    }
    if (filters.ageMax && o.age > filters.ageMax) {
      return false;
    }

    // Score filter
    if (filters.minScore && o.ob1_score < filters.minScore) {
      return false;
    }
    if (filters.maxScore && o.ob1_score > filters.maxScore) {
      return false;
    }

    // Text query filter (name, clubs)
    if (filters.query) {
      const lowerQuery = filters.query.toLowerCase();
      const searchable = [
        o.player_name,
        o.role_name || o.role,
        o.current_club || '',
        ...(o.previous_clubs || []),
      ].join(' ').toLowerCase();

      if (!searchable.includes(lowerQuery)) {
        return false;
      }
    }

    return true;
  }).sort((a, b) => b.ob1_score - a.ob1_score);
}
