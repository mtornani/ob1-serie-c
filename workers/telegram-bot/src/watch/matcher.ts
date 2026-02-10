/**
 * SCORE-002: Watch Criteria System - Matching Engine
 * Enhanced with DNA scoring for personalized matching
 */

import { WatchProfile } from './types';
import { Opportunity } from '../types';
import { calculateDNAMatch } from '../dna';
import { buildClubDNAFromWatch } from '../dna-adapter';
import type { ClubDNA, MatchBreakdown } from '../dna';

/**
 * Check if an opportunity matches a watch profile
 */
export function matchesProfile(opportunity: Opportunity, profile: WatchProfile): boolean {
  // Check if profile is active
  if (!profile.active) return false;

  // Check roles
  if (profile.roles && profile.roles.length > 0) {
    if (!profile.roles.includes(opportunity.role)) {
      return false;
    }
  }

  // Check opportunity types
  if (profile.opportunity_types && profile.opportunity_types.length > 0) {
    if (!profile.opportunity_types.includes(opportunity.opportunity_type)) {
      return false;
    }
  }

  // Check age range
  if (profile.age_min !== undefined && opportunity.age < profile.age_min) {
    return false;
  }
  if (profile.age_max !== undefined && opportunity.age > profile.age_max) {
    return false;
  }

  // Check minimum score
  if (profile.min_ob1_score !== undefined && opportunity.ob1_score < profile.min_ob1_score) {
    return false;
  }

  return true;
}

/**
 * Filter opportunities that match any of the user's profiles
 */
export function filterByProfiles(
  opportunities: Opportunity[],
  profiles: WatchProfile[]
): { opportunity: Opportunity; matchedProfiles: WatchProfile[] }[] {
  const results: { opportunity: Opportunity; matchedProfiles: WatchProfile[] }[] = [];

  for (const opp of opportunities) {
    const matchedProfiles = profiles.filter(p => matchesProfile(opp, p));

    if (matchedProfiles.length > 0) {
      results.push({ opportunity: opp, matchedProfiles });
    }
  }

  // Sort by score descending
  return results.sort((a, b) => b.opportunity.ob1_score - a.opportunity.ob1_score);
}

/**
 * Get opportunities that should trigger immediate alerts
 */
export function getImmediateAlerts(
  opportunities: Opportunity[],
  profiles: WatchProfile[]
): Opportunity[] {
  const immediateProfiles = profiles.filter(p => p.alert_immediately && p.active);

  if (immediateProfiles.length === 0) return [];

  return opportunities.filter(opp =>
    immediateProfiles.some(p => matchesProfile(opp, p))
  );
}

/**
 * Get opportunities for daily digest
 */
export function getDigestOpportunities(
  opportunities: Opportunity[],
  profiles: WatchProfile[]
): Opportunity[] {
  const digestProfiles = profiles.filter(p => p.include_in_digest && p.active);

  if (digestProfiles.length === 0) return [];

  return opportunities.filter(opp =>
    digestProfiles.some(p => matchesProfile(opp, p))
  );
}

// ============================================================================
// DNA-ENHANCED MATCHING
// ============================================================================

export interface DNAScoredMatch {
  opportunity: Opportunity;
  dnaScore: number;
  breakdown: MatchBreakdown;
  matchedProfile: WatchProfile;
}

/**
 * Filter and score opportunities using DNA engine.
 * First filters with boolean matchesProfile, then scores with DNA.
 * Returns results sorted by DNA score.
 */
export function filterByProfilesDNA(
  opportunities: Opportunity[],
  profiles: WatchProfile[]
): DNAScoredMatch[] {
  const results: DNAScoredMatch[] = [];

  for (const profile of profiles) {
    if (!profile.active) continue;

    // Convert WatchProfile → ClubDNA
    const clubDNA = buildClubDNAFromWatch(profile);

    for (const opp of opportunities) {
      // Quick boolean pre-filter
      if (!matchesProfile(opp, profile)) continue;

      // DNA score
      const match = calculateDNAMatch(opp, clubDNA);
      if (match.score > 0) {
        results.push({
          opportunity: opp,
          dnaScore: match.score,
          breakdown: match.breakdown,
          matchedProfile: profile,
        });
      }
    }
  }

  // Deduplicate (same opp matched by multiple profiles → keep highest score)
  const dedupMap = new Map<string, DNAScoredMatch>();
  for (const r of results) {
    const existing = dedupMap.get(r.opportunity.id);
    if (!existing || r.dnaScore > existing.dnaScore) {
      dedupMap.set(r.opportunity.id, r);
    }
  }

  // Sort by DNA score descending
  return Array.from(dedupMap.values()).sort((a, b) => b.dnaScore - a.dnaScore);
}

/**
 * Get immediate alerts with DNA scoring
 */
export function getImmediateAlertsDNA(
  opportunities: Opportunity[],
  profiles: WatchProfile[],
  minDnaScore: number = 60
): DNAScoredMatch[] {
  const immediateProfiles = profiles.filter(p => p.alert_immediately && p.active);
  if (immediateProfiles.length === 0) return [];

  return filterByProfilesDNA(opportunities, immediateProfiles)
    .filter(r => r.dnaScore >= minDnaScore);
}

/**
 * Get digest opportunities with DNA scoring
 */
export function getDigestOpportunitiesDNA(
  opportunities: Opportunity[],
  profiles: WatchProfile[],
  minDnaScore: number = 40
): DNAScoredMatch[] {
  const digestProfiles = profiles.filter(p => p.include_in_digest && p.active);
  if (digestProfiles.length === 0) return [];

  return filterByProfilesDNA(opportunities, digestProfiles)
    .filter(r => r.dnaScore >= minDnaScore);
}
