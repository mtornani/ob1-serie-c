/**
 * NOTIF-002: Notification Queue (KV Storage)
 */

import { QueuedNotification, NotificationStats, DigestEntry } from './types';

const QUEUE_PREFIX = 'notif:queue:';
const STATS_PREFIX = 'notif:stats:';
const DIGEST_PREFIX = 'notif:digest:';
const USERS_KEY = 'notif:users'; // List of users with notifications enabled

export interface NotificationQueue {
  // Queue operations
  enqueue(notification: QueuedNotification): Promise<void>;
  dequeue(chatId: number, notificationId: string): Promise<void>;
  getQueued(chatId: number): Promise<QueuedNotification[]>;

  // Stats for rate limiting
  getStats(chatId: number): Promise<NotificationStats>;
  incrementStats(chatId: number): Promise<void>;
  resetHourlyStats(chatId: number): Promise<void>;

  // Digest operations
  addToDigest(chatId: number, entry: DigestEntry): Promise<void>;
  getDigest(chatId: number): Promise<DigestEntry[]>;
  clearDigest(chatId: number): Promise<void>;

  // User tracking
  getActiveUsers(): Promise<number[]>;
  registerUser(chatId: number): Promise<void>;
}

export function createNotificationQueue(kv: KVNamespace): NotificationQueue {
  return {
    async enqueue(notification: QueuedNotification): Promise<void> {
      const key = `${QUEUE_PREFIX}${notification.chatId}:${notification.id}`;
      await kv.put(key, JSON.stringify(notification), {
        expirationTtl: 86400, // 24 hours
      });

      // Register user
      await this.registerUser(notification.chatId);
    },

    async dequeue(chatId: number, notificationId: string): Promise<void> {
      const key = `${QUEUE_PREFIX}${chatId}:${notificationId}`;
      await kv.delete(key);
    },

    async getQueued(chatId: number): Promise<QueuedNotification[]> {
      const prefix = `${QUEUE_PREFIX}${chatId}:`;
      const list = await kv.list({ prefix });

      const notifications: QueuedNotification[] = [];
      for (const key of list.keys) {
        const data = await kv.get(key.name);
        if (data) {
          notifications.push(JSON.parse(data));
        }
      }

      return notifications.sort((a, b) =>
        new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
      );
    },

    async getStats(chatId: number): Promise<NotificationStats> {
      const today = new Date().toISOString().split('T')[0];
      const key = `${STATS_PREFIX}${chatId}:${today}`;
      const data = await kv.get(key);

      if (!data) {
        return { sentToday: 0, sentThisHour: 0 };
      }

      return JSON.parse(data);
    },

    async incrementStats(chatId: number): Promise<void> {
      const today = new Date().toISOString().split('T')[0];
      const key = `${STATS_PREFIX}${chatId}:${today}`;

      const current = await this.getStats(chatId);
      const now = new Date().toISOString();

      const updated: NotificationStats = {
        sentToday: current.sentToday + 1,
        sentThisHour: current.sentThisHour + 1,
        lastSentAt: now,
      };

      await kv.put(key, JSON.stringify(updated), {
        expirationTtl: 86400, // 24 hours
      });
    },

    async resetHourlyStats(chatId: number): Promise<void> {
      const today = new Date().toISOString().split('T')[0];
      const key = `${STATS_PREFIX}${chatId}:${today}`;

      const current = await this.getStats(chatId);
      current.sentThisHour = 0;

      await kv.put(key, JSON.stringify(current), {
        expirationTtl: 86400,
      });
    },

    async addToDigest(chatId: number, entry: DigestEntry): Promise<void> {
      const key = `${DIGEST_PREFIX}${chatId}`;
      const existing = await this.getDigest(chatId);

      // Avoid duplicates
      const isDuplicate = existing.some(e =>
        e.opportunity.id === entry.opportunity.id
      );

      if (!isDuplicate) {
        existing.push(entry);
        await kv.put(key, JSON.stringify(existing), {
          expirationTtl: 86400,
        });
      }

      await this.registerUser(chatId);
    },

    async getDigest(chatId: number): Promise<DigestEntry[]> {
      const key = `${DIGEST_PREFIX}${chatId}`;
      const data = await kv.get(key);
      return data ? JSON.parse(data) : [];
    },

    async clearDigest(chatId: number): Promise<void> {
      const key = `${DIGEST_PREFIX}${chatId}`;
      await kv.delete(key);
    },

    async getActiveUsers(): Promise<number[]> {
      const data = await kv.get(USERS_KEY);
      return data ? JSON.parse(data) : [];
    },

    async registerUser(chatId: number): Promise<void> {
      const users = await this.getActiveUsers();
      if (!users.includes(chatId)) {
        users.push(chatId);
        await kv.put(USERS_KEY, JSON.stringify(users));
      }
    },
  };
}

// Memory-based queue for testing
export function createMemoryQueue(): NotificationQueue {
  const queued = new Map<string, QueuedNotification>();
  const stats = new Map<string, NotificationStats>();
  const digests = new Map<number, DigestEntry[]>();
  const users = new Set<number>();

  return {
    async enqueue(notification: QueuedNotification): Promise<void> {
      queued.set(`${notification.chatId}:${notification.id}`, notification);
      users.add(notification.chatId);
    },

    async dequeue(chatId: number, notificationId: string): Promise<void> {
      queued.delete(`${chatId}:${notificationId}`);
    },

    async getQueued(chatId: number): Promise<QueuedNotification[]> {
      return Array.from(queued.values())
        .filter(n => n.chatId === chatId)
        .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
    },

    async getStats(chatId: number): Promise<NotificationStats> {
      const today = new Date().toISOString().split('T')[0];
      return stats.get(`${chatId}:${today}`) || { sentToday: 0, sentThisHour: 0 };
    },

    async incrementStats(chatId: number): Promise<void> {
      const today = new Date().toISOString().split('T')[0];
      const key = `${chatId}:${today}`;
      const current = stats.get(key) || { sentToday: 0, sentThisHour: 0 };
      stats.set(key, {
        sentToday: current.sentToday + 1,
        sentThisHour: current.sentThisHour + 1,
        lastSentAt: new Date().toISOString(),
      });
    },

    async resetHourlyStats(chatId: number): Promise<void> {
      const today = new Date().toISOString().split('T')[0];
      const key = `${chatId}:${today}`;
      const current = stats.get(key);
      if (current) {
        current.sentThisHour = 0;
        stats.set(key, current);
      }
    },

    async addToDigest(chatId: number, entry: DigestEntry): Promise<void> {
      const existing = digests.get(chatId) || [];
      if (!existing.some(e => e.opportunity.id === entry.opportunity.id)) {
        existing.push(entry);
        digests.set(chatId, existing);
      }
      users.add(chatId);
    },

    async getDigest(chatId: number): Promise<DigestEntry[]> {
      return digests.get(chatId) || [];
    },

    async clearDigest(chatId: number): Promise<void> {
      digests.delete(chatId);
    },

    async getActiveUsers(): Promise<number[]> {
      return Array.from(users);
    },

    async registerUser(chatId: number): Promise<void> {
      users.add(chatId);
    },
  };
}
