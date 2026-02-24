export interface Env {
  TELEGRAM_BOT_TOKEN: string;
  DATA_URL: string;
  DASHBOARD_URL: string;
}

export interface Signal {
  entity: string;
  label: string;
  anomaly_type: string;
  score: number;
  why: string[];
  links: string[];
}

export interface RadarData {
  generated_at_utc: string;
  source: string;
  mode: string;
  region_breakdown: Record<string, number>;
  items: Signal[];
}

export interface TelegramUpdate {
  update_id: number;
  message?: {
    message_id: number;
    from: { id: number; first_name: string };
    chat: { id: number; type: string };
    text?: string;
  };
}
