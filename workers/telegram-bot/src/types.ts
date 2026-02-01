// Telegram Types
export interface TelegramUpdate {
  update_id: number;
  message?: TelegramMessage;
  callback_query?: TelegramCallbackQuery;
}

export interface TelegramCallbackQuery {
  id: string;
  from: TelegramUser;
  message?: TelegramMessage;
  chat_instance: string;
  data?: string;
}

export interface TelegramMessage {
  message_id: number;
  from?: TelegramUser;
  chat: TelegramChat;
  date: number;
  text?: string;
}

export interface TelegramUser {
  id: number;
  is_bot: boolean;
  first_name: string;
  last_name?: string;
  username?: string;
}

export interface TelegramChat {
  id: number;
  type: 'private' | 'group' | 'supergroup' | 'channel';
  title?: string;
  username?: string;
  first_name?: string;
  last_name?: string;
}

// OB1 Data Types
export interface Opportunity {
  id: string;
  player_name: string;
  age: number;
  role: string;
  role_name?: string;
  opportunity_type: string;
  reported_date: string;
  source_name: string;
  source_url?: string;
  current_club?: string;
  previous_clubs?: string[];
  appearances?: number;
  goals?: number;
  summary?: string;
  nationality?: string;
  second_nationality?: string;
  foot?: string;
  market_value?: number;
  market_value_formatted?: string;
  ob1_score: number;
  classification: 'hot' | 'warm' | 'cold';
  score_breakdown?: ScoreBreakdown;
}

export interface DashboardData {
  opportunities: Opportunity[];
  stats?: {
    total: number;
    hot: number;
    warm: number;
    cold: number;
  };
  last_update: string;
}

export interface ScoreBreakdown {
  freshness: number;
  opportunity_type: number;
  experience: number;
  age: number;
  source: number;
  completeness: number;
}

// Environment
export interface Env {
  TELEGRAM_BOT_TOKEN: string;
  DATA_URL: string;
  DASHBOARD_URL: string;
  AI?: any; // Cloudflare AI binding (optional)
  USER_DATA?: KVNamespace; // KV for user preferences (optional)
}
