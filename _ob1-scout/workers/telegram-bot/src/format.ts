import { Signal, RadarData } from './types';

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function scoreEmoji(score: number): string {
  if (score >= 20) return '🔥';
  if (score >= 10) return '⚡';
  return '❄️';
}

function typeEmoji(type: string): string {
  if (type === 'PLAYER_BURST') return '⭐';
  if (type === 'TRANSFER_SIGNAL') return '🔄';
  return '📡';
}

export function formatSignal(s: Signal): string {
  const emoji = scoreEmoji(s.score);
  const te = typeEmoji(s.anomaly_type);
  const tags = s.why.map(w => `#${w.replace(/-/g, '_')}`).join(' ');
  const link = s.links[0] ? `<a href="${esc(s.links[0])}">Source</a>` : '';
  return `${emoji} <b>${esc(s.label)}</b>\n${te} ${s.anomaly_type} | Score: ${s.score}\n${tags}\n${link}`;
}

export function formatReport(data: RadarData, dashUrl: string): string {
  const b = data.region_breakdown;
  const total = data.items.length;
  const lines = [
    `🌍 <b>OB1 World Scout Report</b>`,
    ``,
    `📊 <b>${total} signals detected</b>`,
    `🌍 Africa: ${b.africa || 0} | Asia: ${b.asia || 0}`,
    `🌎 S. America: ${b['south-america'] || 0} | Int'l: ${b.international || 0}`,
    ``,
    `🕐 Updated: ${data.generated_at_utc}`,
    ``,
    `<a href="${esc(dashUrl)}">📱 Open Dashboard</a>`,
  ];
  return lines.join('\n');
}

export function formatList(signals: Signal[], title: string, max = 5): string {
  if (!signals.length) return `${title}\n\nNo signals found.`;
  const items = signals.slice(0, max).map((s, i) => `${i + 1}. ${formatSignal(s)}`);
  return `${title}\n\n${items.join('\n\n')}`;
}
