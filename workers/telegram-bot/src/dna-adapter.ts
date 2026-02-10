/**
 * DNA-002: DNA Adapter — Converts Wizard/Watch inputs to ClubDNA profiles
 *
 * This module bridges the Scout Wizard and Watch Profile systems
 * to the unified DNA matching engine.
 *
 * buildClubDNAFromWizard() — converts wizard answers into a virtual ClubDNA
 * buildClubDNAFromWatch()  — converts a WatchProfile into a virtual ClubDNA
 */

import { WatchProfile } from './watch/types';
import { ClubDNA, ClubNeed } from './dna';

// ── Wizard code → role mapping ──

const WIZARD_ROLE_MAP: Record<string, string[]> = {
  'dif': ['DC', 'TS', 'TD'],
  'cen': ['CC', 'MED', 'TRQ'],
  'att': ['ATT', 'PC', 'AS', 'AD'],
  'por': ['POR'],
  'any': [],
};

// ── Wizard code → age range ──

const WIZARD_EXPERIENCE_MAP: Record<string, { age_min: number; age_max: number }> = {
  'gio': { age_min: 17, age_max: 23 },
  'pro': { age_min: 23, age_max: 28 },
  'esp': { age_min: 28, age_max: 36 },
  'any': { age_min: 17, age_max: 36 },
};

// ── Wizard code → budget ──

const WIZARD_BUDGET_MAP: Record<string, { budget_type: string; max_loan_cost: number }> = {
  'zer': { budget_type: 'solo_svincolati', max_loan_cost: 0 },
  'pre': { budget_type: 'solo_prestiti', max_loan_cost: 50 },
  'any': { budget_type: 'acquisti', max_loan_cost: 200 },
};

// ── Wizard code → club id for real club DNA lookup ──

const WIZARD_CLUB_MAP: Record<string, string> = {
  'ces': 'cesena',
  'pes': 'pescara',
  'per': 'perugia',
  'rim': 'rimini',
  'tre': 'tre_penne',
  'fio': 'la_fiorita',
  'vir': 'virtus',
  'any': '',
};

// ══════════════════════════════════════════
// buildClubDNAFromWizard
// ══════════════════════════════════════════

/**
 * Converts wizard answer codes into a virtual ClubDNA.
 *
 * @param codes - Array of wizard answer codes ['cen', 'gio', 'zer', 'tal', 'ces']
 * @param realClubs - Optional map of real club DNA profiles. If the user selected
 *                    a real club (e.g., 'ces' for Cesena), use its DNA as a base
 *                    and filter/modify based on wizard answers.
 */
export function buildClubDNAFromWizard(
  codes: string[],
  realClubs?: Map<string, ClubDNA>
): ClubDNA {
  const roleCode = codes[0] || 'any';
  const expCode = codes[1] || 'any';
  const budgetCode = codes[2] || 'any';
  // codes[3] = character (lea/gre/tal/any) — not directly mapped to ClubDNA
  const clubCode = codes[4] || 'any';

  // Try to use real club DNA as base
  const realClubId = WIZARD_CLUB_MAP[clubCode] || '';
  if (realClubId && realClubs && realClubs.has(realClubId)) {
    const baseClub = realClubs.get(realClubId)!;
    return refineClubDNA(baseClub, roleCode, expCode, budgetCode);
  }

  // Build virtual ClubDNA from scratch
  const roles = WIZARD_ROLE_MAP[roleCode] || [];
  const ageRange = WIZARD_EXPERIENCE_MAP[expCode] || WIZARD_EXPERIENCE_MAP['any'];
  const budget = WIZARD_BUDGET_MAP[budgetCode] || WIZARD_BUDGET_MAP['any'];

  // Build needs from role selection
  const needs: ClubNeed[] = roles.length > 0
    ? roles.map(pos => ({
        position: pos,
        player_type: '',
        age_min: ageRange.age_min,
        age_max: ageRange.age_max,
        priority: 'alta',
      }))
    : [
        // If 'any' role, add generic needs for all positions
        { position: 'CC', player_type: '', age_min: ageRange.age_min, age_max: ageRange.age_max, priority: 'media' },
        { position: 'DC', player_type: '', age_min: ageRange.age_min, age_max: ageRange.age_max, priority: 'media' },
        { position: 'ATT', player_type: '', age_min: ageRange.age_min, age_max: ageRange.age_max, priority: 'media' },
        { position: 'ES', player_type: '', age_min: ageRange.age_min, age_max: ageRange.age_max, priority: 'bassa' },
      ];

  return {
    id: 'wizard_virtual',
    name: 'Ricerca Wizard',
    category: 'Serie C', // Default to Serie C level
    city: '',
    primary_formation: '4-3-3',
    playing_styles: ['possesso', 'transizioni'],
    needs,
    budget_type: budget.budget_type,
    max_loan_cost: budget.max_loan_cost,
  };
}

/**
 * Refine a real club's DNA based on wizard answers.
 * Keeps the club's base profile but filters needs by the wizard's role/age/budget choices.
 */
function refineClubDNA(
  base: ClubDNA,
  roleCode: string,
  expCode: string,
  budgetCode: string
): ClubDNA {
  const roles = WIZARD_ROLE_MAP[roleCode] || [];
  const ageRange = WIZARD_EXPERIENCE_MAP[expCode] || WIZARD_EXPERIENCE_MAP['any'];
  const budget = WIZARD_BUDGET_MAP[budgetCode] || WIZARD_BUDGET_MAP['any'];

  let needs = [...base.needs];

  // If a specific role was chosen, prioritize matching needs
  if (roles.length > 0) {
    // Boost priority for matching positions, lower for others
    needs = needs.map(need => {
      if (roles.includes(need.position)) {
        return { ...need, priority: 'alta', age_min: ageRange.age_min, age_max: ageRange.age_max };
      }
      return { ...need, priority: 'bassa' };
    });

    // If no existing need matches the wizard role, add it
    const hasMatchingNeed = needs.some(n => roles.includes(n.position));
    if (!hasMatchingNeed) {
      roles.forEach(pos => {
        needs.push({
          position: pos,
          player_type: '',
          age_min: ageRange.age_min,
          age_max: ageRange.age_max,
          priority: 'alta',
        });
      });
    }
  } else {
    // Apply age range to all needs
    needs = needs.map(n => ({
      ...n,
      age_min: Math.max(n.age_min, ageRange.age_min),
      age_max: Math.min(n.age_max, ageRange.age_max),
    }));
  }

  return {
    ...base,
    needs,
    budget_type: budget.budget_type,
    max_loan_cost: Math.min(base.max_loan_cost, budget.max_loan_cost) || budget.max_loan_cost,
  };
}

// ══════════════════════════════════════════
// buildClubDNAFromWatch
// ══════════════════════════════════════════

/**
 * Converts a WatchProfile into a virtual ClubDNA for DNA scoring.
 *
 * WatchProfile fields → ClubDNA mapping:
 * - roles[]        → needs[] (each role becomes a ClubNeed)
 * - opportunity_types[] → budget_type
 * - age_min/max    → need age ranges
 * - min_ob1_score  → (used as post-filter, not in DNA)
 */
export function buildClubDNAFromWatch(profile: WatchProfile): ClubDNA {
  const needs: ClubNeed[] = [];

  if (profile.roles && profile.roles.length > 0) {
    // Create a need for each watched role
    for (const role of profile.roles) {
      needs.push({
        position: role,
        player_type: '',
        age_min: profile.age_min || 17,
        age_max: profile.age_max || 36,
        priority: 'alta',
      });
    }
  } else {
    // No specific roles = generic needs
    needs.push({
      position: 'CC',
      player_type: '',
      age_min: profile.age_min || 17,
      age_max: profile.age_max || 36,
      priority: 'media',
    });
  }

  // Map opportunity types to budget type
  let budgetType = 'acquisti';
  let maxLoan = 100;

  if (profile.opportunity_types && profile.opportunity_types.length > 0) {
    const types = profile.opportunity_types;
    if (types.includes('svincolato') && types.length === 1) {
      budgetType = 'solo_svincolati';
      maxLoan = 0;
    } else if (types.includes('prestito')) {
      budgetType = 'solo_prestiti';
      maxLoan = 50;
    }
  }

  return {
    id: `watch_${profile.id}`,
    name: profile.name || 'Watch Profile',
    category: 'Serie C', // Default — could be enhanced with user's club
    city: '',
    primary_formation: '4-3-3',
    playing_styles: ['possesso', 'transizioni'],
    needs,
    budget_type: budgetType,
    max_loan_cost: maxLoan,
  };
}
