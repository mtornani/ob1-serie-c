/**
 * NOTIF-002: Priority Filtering - Types
 */

import { Opportunity } from '../types';

export interface QueuedNotification {
  id: string;
  chatId: number;
  opportunity: Opportunity;
  matchedProfileIds: string[];
  matchedProfileNames: string[];
  priority: 'immediate' | 'digest';
  createdAt: string;
  sentAt?: string;
}

export interface NotificationStats {
  sentToday: number;
  sentThisHour: number;
  lastSentAt?: string;
}

export interface DigestEntry {
  opportunity: Opportunity;
  matchedProfiles: string[];
}

// Quiet hours configuration
export const QUIET_HOURS = {
  start: 23, // 23:00
  end: 7,    // 07:00
};

// Rate limits
export const RATE_LIMITS = {
  maxPerHour: 5,
  maxPerDay: 20,
};

// Check if current time is in quiet hours
export function isQuietHours(now: Date = new Date()): boolean {
  const hour = now.getUTCHours();
  // Quiet hours: 23:00 - 07:00 UTC
  return hour >= QUIET_HOURS.start || hour < QUIET_HOURS.end;
}

// Generate notification ID
export function generateNotificationId(): string {
  return `notif_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
}
