import { Env } from './types';

const TELEGRAM_API = 'https://api.telegram.org/bot';

// Footer fisso con social proof — appeso a ogni messaggio in uscita
const OB1_FOOTER =
  "\n──────────────────\n" +
  "🔎 OB1 Scout v3.2\n" +
  "📈 Villarreal: €1.8M → Clausola €51M\n" +
  "🔗 t.me/ob1scout";

const TELEGRAM_MAX_LENGTH = 4096;

/**
 * Invia messaggio Telegram con footer OB1.
 * Se il testo + footer supera 4096 char, splitta e mette il footer solo sull'ultimo chunk.
 */
export async function sendMessage(
  env: Env,
  chatId: number,
  text: string,
  parseMode: 'HTML' | 'Markdown' = 'HTML'
): Promise<boolean> {
  const textWithFooter = text + OB1_FOOTER;

  // Caso semplice: entra in un messaggio
  if (textWithFooter.length <= TELEGRAM_MAX_LENGTH) {
    return sendRawMessage(env, chatId, textWithFooter, parseMode);
  }

  // Split per paragrafi, footer solo sull'ultimo chunk
  const maxChunkLen = TELEGRAM_MAX_LENGTH - 20; // margine per contatore (x/y)
  const lines = text.split('\n');
  const parts: string[] = [];
  let current = '';

  for (const line of lines) {
    if (current.length + line.length + 1 > maxChunkLen) {
      parts.push(current);
      current = line;
    } else {
      current += (current ? '\n' : '') + line;
    }
  }
  if (current) parts.push(current);

  let success = true;
  for (let i = 0; i < parts.length; i++) {
    const isLast = i === parts.length - 1;
    const suffix = isLast ? OB1_FOOTER : '';
    let chunk = `${parts[i]}${suffix}\n\n(${i + 1}/${parts.length})`;

    // Se l'ultimo chunk con footer sfora, manda separatamente
    if (chunk.length > TELEGRAM_MAX_LENGTH && isLast) {
      if (!await sendRawMessage(env, chatId, `${parts[i]}\n\n(${i + 1}/${parts.length})`, parseMode)) success = false;
      if (!await sendRawMessage(env, chatId, OB1_FOOTER, parseMode)) success = false;
    } else {
      if (!await sendRawMessage(env, chatId, chunk, parseMode)) success = false;
    }
  }

  return success;
}

/**
 * Invio diretto senza footer (uso interno).
 */
async function sendRawMessage(
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
  replyMarkup?: any,
  parseMode: 'HTML' | 'Markdown' = 'HTML'
): Promise<boolean> {
  const url = `${TELEGRAM_API}${env.TELEGRAM_BOT_TOKEN}/editMessageText`;

  try {
    const payload: any = {
      chat_id: chatId,
      message_id: messageId,
      text: text,
      parse_mode: parseMode,
      disable_web_page_preview: true,
    };
    if (replyMarkup) {
      payload.reply_markup = replyMarkup;
    }
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
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
/**
 * Get file path from Telegram servers
 */
export async function getFile(env: Env, fileId: string): Promise<string | null> {
  const url = `${TELEGRAM_API}${env.TELEGRAM_BOT_TOKEN}/getFile`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ file_id: fileId }),
    });

    if (!response.ok) {
      console.error('Failed to get file:', await response.text());
      return null;
    }

    const data = await response.json() as any;
    if (data.ok && data.result?.file_path) {
      return data.result.file_path;
    }
    return null;
  } catch (error) {
    console.error('Failed to get file:', error);
    return null;
  }
}

/**
 * Download file from Telegram servers and return as base64
 */
export async function downloadFileAsBase64(env: Env, filePath: string): Promise<string | null> {
  const url = `https://api.telegram.org/file/bot${env.TELEGRAM_BOT_TOKEN}/${filePath}`;

  try {
    const response = await fetch(url);
    if (!response.ok) {
      console.error('Failed to download file:', response.status);
      return null;
    }

    const arrayBuffer = await response.arrayBuffer();
    const base64 = btoa(String.fromCharCode(...new Uint8Array(arrayBuffer)));
    return base64;
  } catch (error) {
    console.error('Failed to download file:', error);
    return null;
  }
}

/**
 * Set bot commands for the menu
 */
export async function setMyCommands(env: Env): Promise<boolean> {
  const url = `${TELEGRAM_API}${env.TELEGRAM_BOT_TOKEN}/setMyCommands`;

  const commands = [
    { command: 'start', description: '🚀 Inizia e seleziona lega' },
    { command: 'league', description: '🌍 Cambia focus globale' },
    { command: 'summary', description: '📊 Riepilogo opportunità top' },
    { command: 'hot', description: '🔥 Segnali High-Relevance (DNA 80+)' },
    { command: 'search', description: '🔍 Analisi tecnica giocatore' },
    { command: 'help', description: '❓ Guida completa' },
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
