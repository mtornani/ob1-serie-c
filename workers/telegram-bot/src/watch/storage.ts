/**
 * SCORE-002: Watch Criteria System - KV Storage
 */

import { WatchProfile, WizardState } from './types';

// Key patterns
const PROFILE_PREFIX = 'watch:profile:';
const WIZARD_PREFIX = 'watch:wizard:';
const USER_PROFILES_PREFIX = 'watch:user:';

export interface WatchStorage {
  // Profile CRUD
  saveProfile(chatId: number, profile: WatchProfile): Promise<void>;
  getProfile(chatId: number, profileId: string): Promise<WatchProfile | null>;
  listProfiles(chatId: number): Promise<WatchProfile[]>;
  deleteProfile(chatId: number, profileId: string): Promise<boolean>;

  // Wizard state (temporary)
  saveWizardState(chatId: number, state: WizardState): Promise<void>;
  getWizardState(chatId: number): Promise<WizardState | null>;
  clearWizardState(chatId: number): Promise<void>;
}

/**
 * KV-based storage implementation
 */
export function createKVStorage(kv: KVNamespace): WatchStorage {
  return {
    async saveProfile(chatId: number, profile: WatchProfile): Promise<void> {
      // Save profile
      const profileKey = `${PROFILE_PREFIX}${chatId}:${profile.id}`;
      await kv.put(profileKey, JSON.stringify(profile));

      // Update user's profile list
      const userKey = `${USER_PROFILES_PREFIX}${chatId}`;
      const existingList = await kv.get(userKey);
      const profileIds: string[] = existingList ? JSON.parse(existingList) : [];

      if (!profileIds.includes(profile.id)) {
        profileIds.push(profile.id);
        await kv.put(userKey, JSON.stringify(profileIds));
      }
    },

    async getProfile(chatId: number, profileId: string): Promise<WatchProfile | null> {
      const key = `${PROFILE_PREFIX}${chatId}:${profileId}`;
      const data = await kv.get(key);
      return data ? JSON.parse(data) : null;
    },

    async listProfiles(chatId: number): Promise<WatchProfile[]> {
      const userKey = `${USER_PROFILES_PREFIX}${chatId}`;
      const profileIdsJson = await kv.get(userKey);

      if (!profileIdsJson) return [];

      const profileIds: string[] = JSON.parse(profileIdsJson);
      const profiles: WatchProfile[] = [];

      for (const id of profileIds) {
        const profile = await this.getProfile(chatId, id);
        if (profile) {
          profiles.push(profile);
        }
      }

      return profiles;
    },

    async deleteProfile(chatId: number, profileId: string): Promise<boolean> {
      const profileKey = `${PROFILE_PREFIX}${chatId}:${profileId}`;
      const profile = await kv.get(profileKey);

      if (!profile) return false;

      // Delete profile
      await kv.delete(profileKey);

      // Update user's profile list
      const userKey = `${USER_PROFILES_PREFIX}${chatId}`;
      const existingList = await kv.get(userKey);

      if (existingList) {
        const profileIds: string[] = JSON.parse(existingList);
        const filtered = profileIds.filter(id => id !== profileId);
        await kv.put(userKey, JSON.stringify(filtered));
      }

      return true;
    },

    async saveWizardState(chatId: number, state: WizardState): Promise<void> {
      const key = `${WIZARD_PREFIX}${chatId}`;
      // Wizard state expires after 10 minutes
      await kv.put(key, JSON.stringify(state), { expirationTtl: 600 });
    },

    async getWizardState(chatId: number): Promise<WizardState | null> {
      const key = `${WIZARD_PREFIX}${chatId}`;
      const data = await kv.get(key);
      return data ? JSON.parse(data) : null;
    },

    async clearWizardState(chatId: number): Promise<void> {
      const key = `${WIZARD_PREFIX}${chatId}`;
      await kv.delete(key);
    },
  };
}

/**
 * In-memory storage for testing/fallback (when KV not available)
 */
export function createMemoryStorage(): WatchStorage {
  const profiles = new Map<string, WatchProfile>();
  const userProfiles = new Map<number, string[]>();
  const wizardStates = new Map<number, WizardState>();

  return {
    async saveProfile(chatId: number, profile: WatchProfile): Promise<void> {
      profiles.set(`${chatId}:${profile.id}`, profile);

      const existing = userProfiles.get(chatId) || [];
      if (!existing.includes(profile.id)) {
        existing.push(profile.id);
        userProfiles.set(chatId, existing);
      }
    },

    async getProfile(chatId: number, profileId: string): Promise<WatchProfile | null> {
      return profiles.get(`${chatId}:${profileId}`) || null;
    },

    async listProfiles(chatId: number): Promise<WatchProfile[]> {
      const ids = userProfiles.get(chatId) || [];
      return ids
        .map(id => profiles.get(`${chatId}:${id}`))
        .filter((p): p is WatchProfile => p !== undefined);
    },

    async deleteProfile(chatId: number, profileId: string): Promise<boolean> {
      const key = `${chatId}:${profileId}`;
      if (!profiles.has(key)) return false;

      profiles.delete(key);

      const existing = userProfiles.get(chatId) || [];
      userProfiles.set(chatId, existing.filter(id => id !== profileId));

      return true;
    },

    async saveWizardState(chatId: number, state: WizardState): Promise<void> {
      wizardStates.set(chatId, state);
    },

    async getWizardState(chatId: number): Promise<WizardState | null> {
      return wizardStates.get(chatId) || null;
    },

    async clearWizardState(chatId: number): Promise<void> {
      wizardStates.delete(chatId);
    },
  };
}
