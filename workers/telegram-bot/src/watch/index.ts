/**
 * SCORE-002: Watch Criteria System
 *
 * Allows users to create watch profiles with custom filters
 * and receive notifications when matching opportunities are found.
 */

export { WatchProfile, WizardState } from './types';
export { WatchStorage, createKVStorage, createMemoryStorage } from './storage';
export { matchesProfile, filterByProfiles, getImmediateAlerts, getDigestOpportunities } from './matcher';
export { handleWatchCommand, handleWatchCallback } from './handlers';
