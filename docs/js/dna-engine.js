/**
 * DNA Engine - Client-side DNA matching for OB1 Dashboard
 * Port of dna.ts / scorer.py v2.0
 *
 * Scores opportunities against a club DNA profile in real-time.
 * 6 dimensions: position (25%), budget (20%), availability (20%),
 *               age (15%), style (15%), level (5%)
 */

// ── Position compatibility ──
const POSITION_COMPATIBILITY = {
  'DC':  ['MED'],
  'TS':  ['ES'],
  'TD':  ['ED'],
  'MED': ['CC'],
  'CC':  ['MED', 'TRQ'],
  'TRQ': ['CC'],
  'ES':  ['TS', 'AS'],
  'ED':  ['TD', 'AD'],
  'AS':  ['ES'],
  'AD':  ['ED'],
  'ATT': ['PC', 'AS', 'AD'],
  'PC':  ['ATT'],
  'POR': [],
};

// ── Category value caps (in thousands €) ──
const CATEGORY_VALUE_CAPS = {
  'Campionato Sammarinese': 300,
  'Serie D': 500,
  'Serie C': 2000,
  'Serie B': 10000,
};

// ── Scoring weights ──
const WEIGHTS = {
  position:     0.25,
  age:          0.15,
  style:        0.15,
  availability: 0.20,
  budget:       0.20,
  level:        0.05,
};

// ── Style → required skills mapping ──
const STYLE_SKILL_MAP = {
  'pressing_alto':    ['pressing', 'fisico', 'velocita'],
  'possesso':         ['tecnica', 'visione'],
  'transizioni':      ['velocita', 'dribbling', 'tecnica'],
  'difesa_bassa':     ['difesa', 'fisico'],
  'gioco_diretto':    ['fisico', 'tiro'],
  'gioco_aereo':      ['fisico'],
  'gioco_sulle_fasce':['velocita', 'dribbling', 'tecnica'],
  'mix_sammarinese':  ['tecnica', 'visione', 'velocita', 'dribbling'],
};

// ── Helper: normalize market value ──
// data.json stores market_value in units (75000 = 75k€)
// club profiles store max_loan_cost in thousands (20 = 20k€)
function normalizeMarketValue(mv) {
  if (!mv || mv === 0) return 0;
  // If value > 1000, assume it's in units (e.g. 75000 = 75k)
  if (mv > 1000) return Math.round(mv / 1000);
  // Otherwise already in thousands
  return mv;
}

// ── Blocking filters ──
function checkBlockingFilters(opp, club) {
  const oppType = (opp.opportunity_type || '').toLowerCase();

  if (oppType.includes('incedibile')) {
    return { blocked: true, reason: 'Giocatore non disponibile (incedibile)' };
  }

  const mv = normalizeMarketValue(opp.market_value);
  const valueCap = CATEGORY_VALUE_CAPS[club.category] || 5000;
  if (mv > 0 && mv > valueCap) {
    return {
      blocked: true,
      reason: `Valore di mercato (${mv}k€) troppo alto per ${club.category} (cap ${valueCap}k€)`
    };
  }

  return { blocked: false, reason: '' };
}

// ── Position fit ──
function calculatePositionFit(opp, club) {
  if (!club.needs || club.needs.length === 0) {
    const role = (opp.role || '').toUpperCase();
    const defaults = {
      'CC': 70, 'DC': 70, 'TS': 65, 'TD': 65,
      'ES': 65, 'ED': 65, 'AS': 60, 'AD': 60,
      'ATT': 60, 'PC': 60, 'MED': 70, 'TRQ': 70, 'POR': 90,
    };
    return { score: defaults[role] || 50, matchedNeed: null };
  }

  let best = { score: 0, matchedNeed: null };

  for (const need of club.needs) {
    let score = 0;
    const needPos = need.position.toUpperCase();
    const playerPos = (opp.role || '').toUpperCase();

    if (playerPos === needPos) {
      score = 100;
    } else if ((POSITION_COMPATIBILITY[playerPos] || []).includes(needPos)) {
      score = 40;
    } else if ((POSITION_COMPATIBILITY[needPos] || []).includes(playerPos)) {
      score = 35;
    }

    // Priority bonus
    if (need.priority === 'alta' && score >= 70) {
      score = Math.min(100, score + 5);
    }

    if (score > best.score) {
      best = { score, matchedNeed: need };
    }
  }

  return best;
}

// ── Age fit ──
function calculateAgeFit(opp, matchedNeed) {
  const age = opp.age;
  if (age == null) return 50;

  if (matchedNeed) {
    const { age_min, age_max } = matchedNeed;
    if (age >= age_min && age <= age_max) return 100;
    if (age < age_min) return Math.max(0, 100 - (age_min - age) * 25);
    return Math.max(0, 100 - (age - age_max) * 25);
  }

  // Default age curve
  if (age >= 20 && age <= 25) return 100;
  if (age < 20) return 80;
  if (age > 25 && age <= 28) return 60;
  return Math.max(0, 100 - Math.abs(age - 23) * 15);
}

// ── Style fit ──
function calculateStyleFit(opp, club) {
  if (!club.playing_styles || club.playing_styles.length === 0) return 50;

  let totalScore = 0;
  let count = 0;

  for (const style of club.playing_styles) {
    const requiredSkills = STYLE_SKILL_MAP[style] || [];
    if (requiredSkills.length > 0) {
      // Without player skill data, use a neutral baseline
      totalScore += 40;
      count++;
    }
  }

  return count === 0 ? 50 : Math.round(totalScore / count);
}

// ── Availability ──
function calculateAvailability(opp) {
  const oppType = (opp.opportunity_type || '').toLowerCase();

  if (oppType.includes('svincol'))  return 100;
  if (oppType.includes('rescis'))   return 95;
  if (oppType.includes('prestit'))  return 70;
  if (oppType.includes('scaden'))   return 60;
  return 30;
}

// ── Budget fit ──
function calculateBudgetFit(opp, club) {
  const mv = normalizeMarketValue(opp.market_value);
  const estimatedLoan = opp.estimated_loan_cost || (mv > 0 ? Math.round(mv * 0.12) : 0);
  const cost = estimatedLoan || 0;

  if (cost === 0 && mv === 0) return 50; // Unknown

  const maxBudget = club.max_loan_cost;
  if (maxBudget <= 0) return 30;
  if (cost <= maxBudget) return 100;
  if (cost <= maxBudget * 1.3) return 70;
  if (cost <= maxBudget * 2) return 35;
  if (cost <= maxBudget * 3) return 15;
  return 5;
}

// ── Level fit ──
function calculateLevelFit(opp, club) {
  const category = club.category;
  const mv = normalizeMarketValue(opp.market_value);

  if (category === 'Campionato Sammarinese') {
    if (mv === 0) return 60;
    if (mv <= 100) return 100;
    if (mv <= 300) return 70;
    if (mv <= 500) return 40;
    if (mv <= 1000) return 20;
    return 5;
  }
  if (category === 'Serie D') {
    if (mv === 0) return 60;
    if (mv <= 300) return 100;
    if (mv <= 800) return 70;
    if (mv <= 1500) return 40;
    return 15;
  }
  if (category === 'Serie C') {
    if (mv === 0) return 60;
    if (mv <= 500) return 90;
    if (mv <= 1500) return 100;
    if (mv <= 3000) return 60;
    if (mv <= 5000) return 30;
    return 10;
  }
  return 50;
}

// ══════════════════════════════════════════
// Main API: calculateDNAMatch(opportunity, clubDNA)
// ══════════════════════════════════════════

function calculateDNAMatch(opp, club) {
  const blocking = checkBlockingFilters(opp, club);

  if (blocking.blocked) {
    return {
      score: 0,
      breakdown: { position: 0, age: 0, style: 0, availability: 0, budget: 0, level: 0 },
      matchedNeed: null,
      blocked: true,
      blockReason: blocking.reason,
    };
  }

  const posResult = calculatePositionFit(opp, club);

  // If position score is 0, skip (no relevant role)
  if (posResult.score === 0) {
    return {
      score: 0,
      breakdown: { position: 0, age: 0, style: 0, availability: 0, budget: 0, level: 0 },
      matchedNeed: null,
      blocked: true,
      blockReason: 'Nessun ruolo compatibile',
    };
  }

  const ageFit      = calculateAgeFit(opp, posResult.matchedNeed);
  const styleFit    = calculateStyleFit(opp, club);
  const availability = calculateAvailability(opp);
  const budgetFit   = calculateBudgetFit(opp, club);
  const levelFit    = calculateLevelFit(opp, club);

  const breakdown = {
    position:     posResult.score,
    age:          ageFit,
    style:        styleFit,
    availability: availability,
    budget:       budgetFit,
    level:        levelFit,
  };

  const score = Math.round(
    breakdown.position     * WEIGHTS.position +
    breakdown.age          * WEIGHTS.age +
    breakdown.style        * WEIGHTS.style +
    breakdown.availability * WEIGHTS.availability +
    breakdown.budget       * WEIGHTS.budget +
    breakdown.level        * WEIGHTS.level
  );

  return {
    score,
    breakdown,
    matchedNeed: posResult.matchedNeed,
    blocked: false,
    blockReason: '',
  };
}

// ── Score all opportunities for a club ──
function scoreOpportunitiesForClub(opportunities, club, minScore) {
  minScore = minScore || 0;

  const results = [];

  for (const opp of opportunities) {
    const match = calculateDNAMatch(opp, club);

    if (!match.blocked && match.score >= minScore) {
      results.push({
        opportunity: opp,
        score: match.score,
        breakdown: match.breakdown,
        matchedNeed: match.matchedNeed,
      });
    }
  }

  // Sort by score descending
  results.sort(function(a, b) { return b.score - a.score; });

  return results;
}

// ── Get classification label ──
function getDNAClassification(score) {
  if (score >= 80) return 'hot';
  if (score >= 60) return 'warm';
  return 'cold';
}

// ── Format breakdown as text ──
function formatBreakdownText(breakdown) {
  const labels = {
    position: 'Posizione',
    age: 'Età',
    style: 'Stile',
    availability: 'Disponibilità',
    budget: 'Budget',
    level: 'Livello',
  };

  return Object.keys(breakdown).map(function(key) {
    return labels[key] + ': ' + breakdown[key] + '%';
  }).join(' | ');
}

// Export for use in app.js
window.DNAEngine = {
  calculateDNAMatch: calculateDNAMatch,
  scoreOpportunitiesForClub: scoreOpportunitiesForClub,
  getDNAClassification: getDNAClassification,
  formatBreakdownText: formatBreakdownText,
  normalizeMarketValue: normalizeMarketValue,
  WEIGHTS: WEIGHTS,
  CATEGORY_VALUE_CAPS: CATEGORY_VALUE_CAPS,
};
