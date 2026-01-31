// Telegram Types
export interface TelegramUpdate {
  update_id: number;
  message?: TelegramMessage;
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
  previous_clubs?: string[];
  appearances?: number;
  goals?: number;
  ob1_score: number;
  classification: 'hot' | 'warm' | 'cold';
}

export interface DashboardData {
  opportunities: Opportunity[];
  stats?: {
    total: number;
    hot: number;
    warm: number;
  };
  last_update: string;
}

// Environment
export interface Env {
  TELEGRAM_BOT_TOKEN: string;
  DATA_URL: string;
  DASHBOARD_URL: string;
}
