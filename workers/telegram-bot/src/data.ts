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
      ...(o.previous_clubs || []),
    ].join(' ').toLowerCase();

    return searchable.includes(lowerQuery);
  }).sort((a, b) => b.ob1_score - a.ob1_score);
}

export function getStats(opportunities: Opportunity[]): { total: number; hot: number; warm: number; cold: number } {
  return {
    total: opportunities.length,
    hot: opportunities.filter(o => o.ob1_score >= 80).length,
    warm: opportunities.filter(o => o.ob1_score >= 60 && o.ob1_score < 80).length,
    cold: opportunities.filter(o => o.ob1_score < 60).length,
  };
}
