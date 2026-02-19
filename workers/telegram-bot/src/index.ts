/**
 * OB1 Radar Telegram Bot
 * Cloudflare Worker for interactive Telegram bot
 *
 * Webhook endpoint: POST /webhook
 * Health check: GET /
 * Set webhook: GET /setup?url=<webhook_url>
 */

import { Env, TelegramUpdate } from './types';
import { handleMessage, handleCallbackQuery } from './handlers';
import { setWebhook, getWebhookInfo, setMyCommands } from './telegram';
import { processQueuedNotifications } from './notifications';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Health check
    if (url.pathname === '/' && request.method === 'GET') {
      return new Response(JSON.stringify({
        status: 'ok',
        service: 'OB1 Radar Telegram Bot',
        version: '2.0.0',
        features: [
          'NOTIF-001: Enhanced alerts with inline keyboards',
          'NLP-001: Natural language query processing',
        ],
      }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Webhook info
    if (url.pathname === '/webhook-info' && request.method === 'GET') {
      const info = await getWebhookInfo(env);
      return new Response(JSON.stringify(info, null, 2), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Setup webhook (one-time setup)
    if (url.pathname === '/setup' && request.method === 'GET') {
      const webhookUrl = url.searchParams.get('url');

      if (!webhookUrl) {
        return new Response('Missing ?url parameter', { status: 400 });
      }

      const success = await setWebhook(env, webhookUrl);

      if (success) {
        return new Response(JSON.stringify({
          success: true,
          message: `Webhook set to: ${webhookUrl}`,
        }), {
          headers: { 'Content-Type': 'application/json' },
        });
      } else {
        return new Response(JSON.stringify({
          success: false,
          message: 'Failed to set webhook',
        }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        });
      }
    }

    // Manual trigger for cron/digest (for testing)
    if (url.pathname === '/trigger-cron' && request.method === 'GET') {
      try {
        console.log('Manual cron trigger via HTTP');
        const result = await processQueuedNotifications(env);
        return new Response(JSON.stringify({
          success: true,
          message: 'Cron triggered manually',
          result: {
            immediate: result.immediate,
            digests: result.digests,
          },
          timestamp: new Date().toISOString(),
        }), {
          headers: { 'Content-Type': 'application/json' },
        });
      } catch (error: any) {
        console.error('Manual cron error:', error);
        return new Response(JSON.stringify({
          success: false,
          error: error.message || 'Unknown error',
        }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        });
      }
    }

    // Setup bot commands menu
    if (url.pathname === '/setup-commands' && request.method === 'GET') {
      const success = await setMyCommands(env);

      return new Response(JSON.stringify({
        success,
        message: success ? 'Bot commands menu updated!' : 'Failed to set commands',
        commands: [
          '/report - Report mercato istantaneo',
          '/hot - Opportunità top (score 80+)',
          '/stale - Svincolati ignorati da 30+ giorni',
          '/stats - Numeri aggregati del mercato',
          '/watch - Alert personalizzati',
          '/digest - Anteprima digest giornaliero',
          '/scout - Wizard guidato (Akinator)',
          '/talenti - Talenti squadre B',
          '/help - Guida completa',
        ],
      }), {
        status: success ? 200 : 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Telegram webhook endpoint
    if (url.pathname === '/webhook' && request.method === 'POST') {
      try {
        const update: TelegramUpdate = await request.json();

        // Process message asynchronously
        if (update.message) {
          // Use waitUntil to process in background
          const ctx = (globalThis as any).ctx;
          if (ctx && ctx.waitUntil) {
            ctx.waitUntil(handleMessage(update.message, env));
          } else {
            await handleMessage(update.message, env);
          }
        }

        // Handle callback queries (NOTIF-001: inline keyboard buttons)
        if (update.callback_query) {
          const ctx = (globalThis as any).ctx;
          if (ctx && ctx.waitUntil) {
            ctx.waitUntil(handleCallbackQuery(update.callback_query, env));
          } else {
            await handleCallbackQuery(update.callback_query, env);
          }
        }

        // Always return 200 to Telegram quickly
        return new Response('OK', { status: 200 });

      } catch (error) {
        console.error('Webhook error:', error);
        // Return 200 anyway to prevent Telegram retries
        return new Response('OK', { status: 200 });
      }
    }

    // 404 for unknown routes
    return new Response('Not Found', { status: 404 });
  },

  /**
   * NOTIF-002: Cron handler for daily digest (07:00 UTC)
   */
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    console.log(`Cron triggered at ${new Date().toISOString()}`);

    try {
      const result = await processQueuedNotifications(env);
      console.log(`Cron completed: ${result.immediate} immediate, ${result.digests} digests sent`);
    } catch (error) {
      console.error('Cron error:', error);
    }
  },
};
