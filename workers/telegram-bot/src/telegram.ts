import { Env } from './types';

const TELEGRAM_API = 'https://api.telegram.org/bot';

export async function sendMessage(
  env: Env,
  chatId: number,
  text: string,
  parseMode: 'HTML' | 'Markdown' = 'HTML'
): Promise<boolean> {
  const url = `${TELEGRAM_API}${env.TELEGRAM_BOT_TOKEN}/sendMessage`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        chat_id: chatId,
        text: text,
        parse_mode: parseMode,
        disable_web_page_preview: true,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      console.error('Telegram API error:', error);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Failed to send message:', error);
    return false;
  }
}

export async function sendMessageWithKeyboard(
  env: Env,
  chatId: number,
  text: string,
  keyboard: any,
  parseMode: 'HTML' | 'Markdown' = 'HTML'
): Promise<boolean> {
  const url = `${TELEGRAM_API}${env.TELEGRAM_BOT_TOKEN}/sendMessage`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        chat_id: chatId,
        text: text,
        parse_mode: parseMode,
        disable_web_page_preview: true,
        reply_markup: keyboard,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      console.error('Telegram API error:', error);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Failed to send message with keyboard:', error);
    return false;
  }
}

export async function answerCallbackQuery(
  env: Env,
  callbackQueryId: string,
  text?: string,
  showAlert: boolean = false
): Promise<boolean> {
  const url = `${TELEGRAM_API}${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        callback_query_id: callbackQueryId,
        text: text,
        show_alert: showAlert,
      }),
    });

    return response.ok;
  } catch (error) {
    console.error('Failed to answer callback query:', error);
    return false;
  }
}

export async function editMessageText(
  env: Env,
  chatId: number,
  messageId: number,
  text: string,
  parseMode: 'HTML' | 'Markdown' = 'HTML'
): Promise<boolean> {
  const url = `${TELEGRAM_API}${env.TELEGRAM_BOT_TOKEN}/editMessageText`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        chat_id: chatId,
        message_id: messageId,
        text: text,
        parse_mode: parseMode,
        disable_web_page_preview: true,
      }),
    });

    return response.ok;
  } catch (error) {
    console.error('Failed to edit message:', error);
    return false;
  }
}

export async function setWebhook(env: Env, webhookUrl: string): Promise<boolean> {
  const url = `${TELEGRAM_API}${env.TELEGRAM_BOT_TOKEN}/setWebhook`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        url: webhookUrl,
        allowed_updates: ['message', 'callback_query'],
      }),
    });

    return response.ok;
  } catch (error) {
    console.error('Failed to set webhook:', error);
    return false;
  }
}

export async function getWebhookInfo(env: Env): Promise<any> {
  const url = `${TELEGRAM_API}${env.TELEGRAM_BOT_TOKEN}/getWebhookInfo`;

  try {
    const response = await fetch(url);
    return await response.json();
  } catch (error) {
    console.error('Failed to get webhook info:', error);
    return null;
  }
}

/**
 * Set bot commands for the menu
 */
export async function setMyCommands(env: Env): Promise<boolean> {
  const url = `${TELEGRAM_API}${env.TELEGRAM_BOT_TOKEN}/setMyCommands`;

  const commands = [
    { command: 'start', description: '🎯 Avvia il bot' },
    { command: 'hot', description: '🔥 Migliori opportunità (score 80+)' },
    { command: 'warm', description: '⚡ Opportunità interessanti (60-79)' },
    { command: 'all', description: '📋 Tutte le opportunità' },
    { command: 'scout', description: '🎯 Wizard guidato (ti aiuto a cercare)' },
    { command: 'talenti', description: '🧬 Talenti dalle squadre B' },
    { command: 'dna', description: '🧬 DNA match per un club' },
    { command: 'watch', description: '🔔 Gestisci alert personalizzati' },
    { command: 'stats', description: '📊 Statistiche mercato' },
    { command: 'help', description: '❓ Come usare il bot' },
  ];

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ commands }),
    });

    if (!response.ok) {
      const error = await response.text();
      console.error('Failed to set commands:', error);
      return false;
    }

    return true;
  } catch (error) {
    console.error('Failed to set commands:', error);
    return false;
  }
}
