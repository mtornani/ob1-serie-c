import { Opportunity, Env } from './types';

export function formatOpportunity(opp: Opportunity): string {
  const scoreEmoji = opp.classification === 'hot' ? '🔥' : opp.classification === 'warm' ? '⚡' : '❄️';
  const typeEmoji = getTypeEmoji(opp.opportunity_type);

  let message = `${scoreEmoji} <b>${escapeHtml(opp.player_name)}</b> (${opp.ob1_score}/100)\n`;
  message += `📍 ${escapeHtml(opp.role_name || opp.role)} | ${opp.age} anni\n`;
  message += `${typeEmoji} ${opp.opportunity_type.toUpperCase()}\n`;

  if (opp.previous_clubs && opp.previous_clubs.length > 0) {
    message += `🏟️ Ex: ${opp.previous_clubs.slice(0, 3).map(escapeHtml).join(', ')}\n`;
  }

  message += `📅 ${formatDate(opp.reported_date)}`;

  if (opp.source_url) {
    message += `\n🔗 <a href="${opp.source_url}">Fonte</a>`;
  }

  return message;
}

export function formatOpportunityList(opportunities: Opportunity[], title: string, maxItems: number = 5): string {
  if (opportunities.length === 0) {
    return `${title}\n\n😔 Nessuna opportunita trovata.`;
  }

  const items = opportunities.slice(0, maxItems);
  let message = `${title}\n\n`;

  items.forEach((opp, index) => {
    message += formatOpportunity(opp);
    if (index < items.length - 1) {
      message += '\n\n───────────────\n\n';
    }
  });

  if (opportunities.length > maxItems) {
    message += `\n\n📊 Mostrati ${maxItems} di ${opportunities.length} risultati.`;
    message += `\n🔗 Vedi tutti sulla dashboard`;
  }

  return message;
}

export function formatStats(stats: { total: number; hot: number; warm: number; cold: number }, lastUpdate: string): string {
  return `📊 <b>OB1 Radar Stats</b>

📋 Totali: <b>${stats.total}</b> opportunita

🔥 HOT: <b>${stats.hot}</b>
⚡ WARM: <b>${stats.warm}</b>
❄️ COLD: <b>${stats.cold}</b>

🕐 Ultimo aggiornamento: ${formatDateTime(lastUpdate)}`;
}

export function formatWelcome(env: Env): string {
  return `🎯 <b>Benvenuto in OB1 Radar Bot!</b>

Sono il tuo assistente per lo scouting Serie C/D.

📋 <b>Comandi disponibili:</b>
/hot - Giocatori HOT (score 80+)
/warm - Giocatori WARM (score 60-79)
/all - Tutte le opportunita
/search &lt;nome&gt; - Cerca giocatore
/stats - Statistiche attuali
/help - Mostra questo messaggio

🔗 <a href="${env.DASHBOARD_URL}">Apri Dashboard</a>`;
}

export function formatHelp(env: Env): string {
  return formatWelcome(env);
}

export function formatError(): string {
  return `❌ Si e verificato un errore. Riprova tra qualche secondo.

Se il problema persiste, visita la dashboard:
🔗 https://mtornani.github.io/ob1-serie-c/`;
}

export function formatUnknownCommand(): string {
  return `❓ Comando non riconosciuto.

Usa /help per vedere i comandi disponibili.`;
}

export function formatNoResults(query: string): string {
  return `🔍 Nessun risultato per "<b>${escapeHtml(query)}</b>"

Prova con:
• Nome del giocatore
• Ruolo (es. "centrocampista")
• Club precedente`;
}

// Helper functions
function getTypeEmoji(type: string): string {
  const emojis: Record<string, string> = {
    svincolato: '🟢',
    rescissione: '🟡',
    prestito: '🔵',
    scadenza: '🟠',
  };
  return emojis[type.toLowerCase()] || '💼';
}

function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  } catch {
    return dateString;
  }
}

function formatDateTime(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateString;
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
