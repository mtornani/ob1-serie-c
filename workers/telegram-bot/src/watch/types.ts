/**
 * SCORE-002: Watch Criteria System - Types
 */

export interface WatchProfile {
  id: string;
  name: string;                      // "Cercasi Terzino", "Under 23 promettenti"

  // Filtri base
  roles?: string[];                  // ["TD", "TS", "DC"]
  opportunity_types?: string[];      // ["svincolato", "prestito"]

  // Età
  age_min?: number;
  age_max?: number;

  // Score minimo
  min_ob1_score?: number;            // Solo opportunità con score >= X

  // Notifiche
  alert_immediately: boolean;        // Push per match immediato (HOT)
  include_in_digest: boolean;        // Includi nel daily digest

  // Metadata
  created_at: string;
  updated_at: string;
  active: boolean;
}

export interface WizardState {
  step: 'role' | 'type' | 'age' | 'score' | 'confirm';
  profile: Partial<WatchProfile>;
}

// Role options for wizard
export const ROLE_OPTIONS = [
  { id: 'difensore', label: '🛡️ Difensore', roles: ['DC', 'TD', 'TS'] },
  { id: 'centrocampista', label: '⚙️ Centrocampista', roles: ['CC', 'MED', 'TRQ'] },
  { id: 'esterno', label: '🏃 Esterno', roles: ['ES', 'ED', 'AS', 'AD'] },
  { id: 'attaccante', label: '⚽ Attaccante', roles: ['ATT', 'PC'] },
  { id: 'portiere', label: '🧤 Portiere', roles: ['POR'] },
  { id: 'tutti', label: '📋 Tutti', roles: [] },
];

// Opportunity type options
export const TYPE_OPTIONS = [
  { id: 'svincolato', label: '🆓 Svincolato', types: ['svincolato'] },
  { id: 'prestito', label: '🔄 Prestito', types: ['prestito'] },
  { id: 'rescissione', label: '📝 Rescissione', types: ['rescissione'] },
  { id: 'tutti', label: '📋 Tutti', types: [] },
];

// Age options
export const AGE_OPTIONS = [
  { id: 'u21', label: '👶 Under 21', max: 21 },
  { id: 'u25', label: '🧑 Under 25', max: 25 },
  { id: 'u30', label: '👨 Under 30', max: 30 },
  { id: 'tutti', label: '📋 Tutti', max: undefined },
];

// Score options
export const SCORE_OPTIONS = [
  { id: 'hot', label: '🔥 Solo HOT (80+)', min: 80 },
  { id: 'warm', label: '⚡ WARM+ (60+)', min: 60 },
  { id: 'tutti', label: '📋 Tutti', min: 0 },
];

export function generateProfileId(): string {
  return `wp_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
}

export function getProfileDisplayName(profile: Partial<WatchProfile>): string {
  const parts: string[] = [];

  if (profile.roles && profile.roles.length > 0) {
    const roleOption = ROLE_OPTIONS.find(r =>
      JSON.stringify(r.roles.sort()) === JSON.stringify([...profile.roles!].sort())
    );
    if (roleOption && roleOption.id !== 'tutti') {
      parts.push(roleOption.label.split(' ')[1]); // Remove emoji
    }
  }

  if (profile.opportunity_types && profile.opportunity_types.length > 0) {
    parts.push(profile.opportunity_types[0]);
  }

  if (profile.age_max) {
    parts.push(`U${profile.age_max}`);
  }

  return parts.length > 0 ? parts.join(' ') : 'Watch Profile';
}
