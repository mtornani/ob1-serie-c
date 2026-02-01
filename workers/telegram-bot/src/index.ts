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
import { setWebhook, getWebhookInfo } from './telegram';

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
};
