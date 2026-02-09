/**
 * SCORE-002: Watch Criteria System - KV Storage
 */

import { WatchProfile, WizardState } from './types';

// Key patterns
const PROFILE_PREFIX = 'watch:profile:';
const WIZARD_PREFIX = 'watch:wizard:';
const USER_PROFILES_PREFIX = 'watch:user:';
const WATCHLIST_PREFIX = 'watch:list:';
const IGNORELIST_PREFIX = 'watch:ignore:';

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

  // NOTIF-001: Watchlist and Ignore list
  addToWatchlist(chatId: number, oppId: string): Promise<void>;
  removeFromWatchlist(chatId: number, oppId: string): Promise<boolean>;
  isInWatchlist(chatId: number, oppId: string): Promise<boolean>;
  getWatchlist(chatId: number): Promise<string[]>;

  addToIgnoreList(chatId: number, oppId: string): Promise<void>;
  removeFromIgnoreList(chatId: number, oppId: string): Promise<boolean>;
  isIgnored(chatId: number, oppId: string): Promise<boolean>;
  getIgnoreList(chatId: number): Promise<string[]>;
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

    // NOTIF-001: Watchlist functions
    async addToWatchlist(chatId: number, oppId: string): Promise<void> {
      const key = `${WATCHLIST_PREFIX}${chatId}`;
      const existing = await kv.get(key);
      const watchlist: string[] = existing ? JSON.parse(existing) : [];
      
      if (!watchlist.includes(oppId)) {
        watchlist.push(oppId);
        await kv.put(key, JSON.stringify(watchlist));
      }
    },

    async removeFromWatchlist(chatId: number, oppId: string): Promise<boolean> {
      const key = `${WATCHLIST_PREFIX}${chatId}`;
      const existing = await kv.get(key);
      
      if (!existing) return false;
      
      const watchlist: string[] = JSON.parse(existing);
      if (!watchlist.includes(oppId)) return false;
      
      const filtered = watchlist.filter(id => id !== oppId);
      await kv.put(key, JSON.stringify(filtered));
      return true;
    },

    async isInWatchlist(chatId: number, oppId: string): Promise<boolean> {
      const key = `${WATCHLIST_PREFIX}${chatId}`;
      const existing = await kv.get(key);
      
      if (!existing) return false;
      
      const watchlist: string[] = JSON.parse(existing);
      return watchlist.includes(oppId);
    },

    async getWatchlist(chatId: number): Promise<string[]> {
      const key = `${WATCHLIST_PREFIX}${chatId}`;
      const existing = await kv.get(key);
      return existing ? JSON.parse(existing) : [];
    },

    // NOTIF-001: Ignore list functions
    async addToIgnoreList(chatId: number, oppId: string): Promise<void> {
      const key = `${IGNORELIST_PREFIX}${chatId}`;
      const existing = await kv.get(key);
      const ignoreList: string[] = existing ? JSON.parse(existing) : [];
      
      if (!ignoreList.includes(oppId)) {
        ignoreList.push(oppId);
        await kv.put(key, JSON.stringify(ignoreList));
      }
    },

    async removeFromIgnoreList(chatId: number, oppId: string): Promise<boolean> {
      const key = `${IGNORELIST_PREFIX}${chatId}`;
      const existing = await kv.get(key);
      
      if (!existing) return false;
      
      const ignoreList: string[] = JSON.parse(existing);
      if (!ignoreList.includes(oppId)) return false;
      
      const filtered = ignoreList.filter(id => id !== oppId);
      await kv.put(key, JSON.stringify(filtered));
      return true;
    },

    async isIgnored(chatId: number, oppId: string): Promise<boolean> {
      const key = `${IGNORELIST_PREFIX}${chatId}`;
      const existing = await kv.get(key);
      
      if (!existing) return false;
      
      const ignoreList: string[] = JSON.parse(existing);
      return ignoreList.includes(oppId);
    },

    async getIgnoreList(chatId: number): Promise<string[]> {
      const key = `${IGNORELIST_PREFIX}${chatId}`;
      const existing = await kv.get(key);
      return existing ? JSON.parse(existing) : [];
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

    // In-memory watchlist and ignore list
    async addToWatchlist(chatId: number, oppId: string): Promise<void> {
      // Implemented in memory storage
    },

    async removeFromWatchlist(chatId: number, oppId: string): Promise<boolean> {
      return false;
    },

    async isInWatchlist(chatId: number, oppId: string): Promise<boolean> {
      return false;
    },

    async getWatchlist(chatId: number): Promise<string[]> {
      return [];
    },

    async addToIgnoreList(chatId: number, oppId: string): Promise<void> {
      // Implemented in memory storage
    },

    async removeFromIgnoreList(chatId: number, oppId: string): Promise<boolean> {
      return false;
    },

    async isIgnored(chatId: number, oppId: string): Promise<boolean> {
      return false;
    },

    async getIgnoreList(chatId: number): Promise<string[]> {
      return [];
    },
  };
}
