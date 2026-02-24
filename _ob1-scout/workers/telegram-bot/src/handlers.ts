import { Env, TelegramUpdate } from './types';
import { fetchData, topSignals, filterByRegion, filterByType, searchSignals } from './data';
import { formatReport, formatList, formatSignal } from './format';

async function send(env: Env, chatId: number, text: string) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: 'HTML', disable_web_page_preview: true }),
  });
}

export async function handleUpdate(update: TelegramUpdate, env: Env) {
  const msg = update.message;
  if (!msg?.text) return;

  const chatId = msg.chat.id;
  const txt = msg.text.trim();
  const cmd = txt.split(' ')[0].toLowerCase().split('@')[0];
  const arg = txt.slice(cmd.length).trim();

  const data = await fetchData(env);
  if (!data) {
    await send(env, chatId, '⚠️ Could not load data. Try again later.');
    return;
  }

  const items = data.items || [];

  switch (cmd) {
    case '/start':
      await send(env, chatId, [
        '🌍 <b>OB1 World Scout</b>',
        '',
        'Global U20 football talent radar. I scan 50+ sources across Africa, Asia, and South America.',
        '',
        '<b>Commands:</b>',
        '/report — Full snapshot',
        '/top — Top 5 signals',
        '/debuts — Player debuts',
        '/transfers — Transfer signals',
        '/africa — Africa signals',
        '/asia — Asia signals',
        '/southamerica — S. America signals',
        '/search <query> — Search signals',
        '/help — This message',
        '',
        `<a href="${env.DASHBOARD_URL}">📱 Open Dashboard</a>`,
      ].join('\n'));
      break;

    case '/help':
      await send(env, chatId, [
        '📖 <b>OB1 World Scout Help</b>',
        '',
        '/report — Market overview + stats',
        '/top — Top 5 scoring signals',
        '/debuts — Player debut signals',
        '/transfers — Transfer & loan signals',
        '/africa — Signals from Africa',
        '/asia — Signals from Asia',
        '/southamerica — Signals from S. America',
        '/search <text> — Free text search',
        '',
        'Or just type naturally: "any debuts in Asia?"',
      ].join('\n'));
      break;

    case '/report':
      await send(env, chatId, formatReport(data, env.DASHBOARD_URL));
      if (items.length) {
        await send(env, chatId, formatList(topSignals(items, 3), '🔥 <b>Top Signals</b>', 3));
      }
      break;

    case '/top':
      await send(env, chatId, formatList(topSignals(items, 5), '🔥 <b>Top 5 Signals</b>'));
      break;

    case '/debuts':
      await send(env, chatId, formatList(filterByType(items, 'PLAYER_BURST'), '⭐ <b>Player Debuts</b>'));
      break;

    case '/transfers':
      await send(env, chatId, formatList(filterByType(items, 'TRANSFER_SIGNAL'), '🔄 <b>Transfer Signals</b>'));
      break;

    case '/africa':
      await send(env, chatId, formatList(filterByRegion(items, 'africa'), '🌍 <b>Africa Signals</b>'));
      break;

    case '/asia':
      await send(env, chatId, formatList(filterByRegion(items, 'asia'), '🌏 <b>Asia Signals</b>'));
      break;

    case '/southamerica':
      await send(env, chatId, formatList(filterByRegion(items, 'south-america'), '🌎 <b>South America Signals</b>'));
      break;

    case '/search':
      if (!arg) {
        await send(env, chatId, '🔍 Usage: /search <query>\nExample: /search debut Japan');
        break;
      }
      await send(env, chatId, formatList(searchSignals(items, arg), `🔍 <b>Search: ${arg}</b>`));
      break;

    default:
      // Natural language fallback — try search
      if (txt.length > 2 && !txt.startsWith('/')) {
        const results = searchSignals(items, txt);
        if (results.length) {
          await send(env, chatId, formatList(results, `🔍 <b>Results for "${txt}"</b>`));
        } else {
          await send(env, chatId, `No signals matching "${txt}". Try /top or /report.`);
        }
      }
      break;
  }
}
