import { Env, TelegramUpdate } from './types';
import { handleUpdate } from './handlers';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Health check
    if (url.pathname === '/' && request.method === 'GET') {
      return new Response(JSON.stringify({
        bot: 'OB1 World Scout',
        status: 'running',
        commands: ['/start', '/report', '/top', '/debuts', '/transfers', '/africa', '/asia', '/southamerica', '/search'],
      }), { headers: { 'Content-Type': 'application/json' } });
    }

    // Webhook
    if (url.pathname === '/webhook' && request.method === 'POST') {
      try {
        const update: TelegramUpdate = await request.json();
        await handleUpdate(update, env);
      } catch (e) {
        console.error('Webhook error:', e);
      }
      return new Response('OK');
    }

    // Setup webhook
    if (url.pathname === '/setup') {
      const webhookUrl = url.searchParams.get('url');
      if (!webhookUrl) return new Response('Pass ?url=https://your-worker.dev/webhook', { status: 400 });
      const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/setWebhook`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: webhookUrl }),
      });
      return new Response(await r.text(), { headers: { 'Content-Type': 'application/json' } });
    }

    // Setup commands menu
    if (url.pathname === '/setup-commands') {
      const commands = [
        { command: 'start', description: 'Welcome & info' },
        { command: 'report', description: 'Full market snapshot' },
        { command: 'top', description: 'Top 5 signals' },
        { command: 'debuts', description: 'Player debut signals' },
        { command: 'transfers', description: 'Transfer signals' },
        { command: 'africa', description: 'Africa signals' },
        { command: 'asia', description: 'Asia signals' },
        { command: 'southamerica', description: 'South America signals' },
        { command: 'search', description: 'Search signals' },
        { command: 'help', description: 'Command help' },
      ];
      const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/setMyCommands`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ commands }),
      });
      return new Response(await r.text(), { headers: { 'Content-Type': 'application/json' } });
    }

    return new Response('Not Found', { status: 404 });
  },
};
