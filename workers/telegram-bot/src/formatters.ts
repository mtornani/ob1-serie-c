import { Opportunity, Env } from './types';

// Dashboard URL constant for companion app experience
const DASHBOARD_URL = 'https://mtornani.github.io/ob1-serie-c/';

export function formatOpportunity(opp: Opportunity): string {
  const scoreEmoji = opp.classification === 'hot' ? '🔥' : opp.classification === 'warm' ? '⚡' : '❄️';
  const typeEmoji = getTypeEmoji(opp.opportunity_type);

  let message = `${scoreEmoji} <b>${escapeHtml(opp.player_name)}</b> (${opp.ob1_score}/100)\n`;
  message += `📍 ${escapeHtml(opp.role_name || opp.role)} | ${opp.age || '?'} anni\n`;
  message += `${typeEmoji} ${opp.opportunity_type.toUpperCase()}\n`;

  if (opp.current_club) {
    message += `🏟️ ${escapeHtml(opp.current_club)}\n`;
  }

  if (opp.previous_clubs && opp.previous_clubs.length > 0) {
    message += `📋 Ex: ${opp.previous_clubs.slice(0, 2).map(escapeHtml).join(', ')}\n`;
  }

  message += `📅 ${formatDate(opp.reported_date)}`;

  if (opp.source_url) {
    message += ` | <a href="${opp.source_url}">Fonte</a>`;
  }

  return message;
}

export function formatOpportunityList(opportunities: Opportunity[], title: string, maxItems: number = 5): string {
  if (opportunities.length === 0) {
    return `${title}\n\n😔 Nessuna opportunità trovata.\n\n🌐 <a href="${DASHBOARD_URL}">Vedi Dashboard completa</a>`;
  }

  const items = opportunities.slice(0, maxItems);
  let message = `${title}\n\n`;

  items.forEach((opp, index) => {
    message += formatOpportunity(opp);
    if (index < items.length - 1) {
      message += '\n\n───────────────\n\n';
    }
  });

  // Always show dashboard link as companion app
  message += '\n\n━━━━━━━━━━━━━━━━━━━━';

  if (opportunities.length > maxItems) {
    message += `\n📊 Mostrati ${maxItems} di ${opportunities.length}`;
  }

  message += `\n🌐 <a href="${DASHBOARD_URL}">Dashboard completa</a>`;

  return message;
}

export function formatStats(stats: { total: number; hot: number; warm: number; cold: number }, lastUpdate: string): string {
  return `📊 <b>OB1 Radar - Statistiche</b>

📋 Totali: <b>${stats.total}</b> opportunità

🔥 HOT: <b>${stats.hot}</b> (score 80+)
⚡ WARM: <b>${stats.warm}</b> (score 60-79)
❄️ COLD: <b>${stats.cold}</b> (score &lt;60)

🕐 Aggiornamento: ${formatDateTime(lastUpdate)}

━━━━━━━━━━━━━━━━━━━━
🌐 <a href="${DASHBOARD_URL}">Apri Dashboard</a>`;
}

export function formatWelcome(env: Env): string {
  return `📊 <b>OB1 Scout</b>

Osservatorio sul mercato Lega Pro.
Svincolati, rescissioni, anomalie — tutto quello che il mercato non vede.

⏳ <b>Cosa non vedi altrove:</b>
/stale - Svincolati ignorati da 30+ giorni
/hot - Opportunità a priorità alta (score 80+)
/report - Snapshot completo del mercato

🔍 <b>Cerca in linguaggio naturale:</b>
• "centrocampisti svincolati under 26"
• "attaccante fisico in prestito"
• "chi è svincolato da più tempo?"

🔔 <b>Alert su misura:</b>
/watch add - Crea profilo di monitoraggio
/digest - Anteprima digest giornaliero

━━━━━━━━━━━━━━━━━━━━
🌐 <a href="${DASHBOARD_URL}">Dashboard completa</a>`;
}

export function formatHelp(env: Env): string {
  return `❓ <b>OB1 Scout - Guida Completa</b>

⏳ <b>ANOMALIE DI MERCATO</b>
/stale - Svincolati con 10+ presenze ignorati da 30+ giorni
/hot - Opportunità a priorità alta (score 80+)
/warm - Buone opportunità (score 60-79)

📊 <b>REPORT E STATISTICHE</b>
/report - Snapshot completo del mercato
/stats - Numeri aggregati (svincolati, stale, trend)
/all - Lista completa ordinata per score

🔍 <b>RICERCA NATURALE</b>
Scrivimi come parleresti:
• "svincolati under 26"
• "chi è svincolato da più tempo?"
• "centrocampisti con più presenze"
• "attaccante fisico in prestito"

🎤 <b>MESSAGGI VOCALI</b>
Registra un vocale e ti rispondo!

⚽ <b>SCOUTING</b>
/talenti - Under 23 in lista
/scout - Wizard guidato
/search &lt;nome&gt; - Cerca per nome

🔔 <b>ALERT PERSONALIZZATI</b>
/watch add - Crea profilo di monitoraggio
/watch - Gestisci alert attivi
/digest - Anteprima digest (ogni mattina 08:00)

━━━━━━━━━━━━━━━━━━━━
📡 <b>Canale pubblico:</b> @ob1scout
🌐 <a href="${DASHBOARD_URL}">Dashboard completa</a>`;
}

export function formatError(): string {
  return `❌ Si è verificato un errore.

Riprova tra qualche secondo, oppure:
🌐 <a href="${DASHBOARD_URL}">Vai alla Dashboard</a>`;
}

export function formatUnknownCommand(): string {
  return `❓ Comando non riconosciuto.

Prova a scrivermi in modo naturale, tipo:
• "chi sono i migliori?"
• "svincolati disponibili"

Oppure /help per i comandi`;
}

export function formatNoResults(query: string): string {
  return `🔍 Nessun risultato per "<b>${escapeHtml(query)}</b>"

Prova con:
• Nome del giocatore
• Ruolo (es. "centrocampista")
• Tipo (es. "svincolato")

🌐 <a href="${DASHBOARD_URL}">Cerca sulla Dashboard</a>`;
}

/**
 * NOTIF-001: Detailed opportunity view with score breakdown
 */
export function formatOpportunityDetails(opp: Opportunity): string {
  const scoreEmoji = opp.classification === 'hot' ? '🔥' : opp.classification === 'warm' ? '⚡' : '❄️';

  let message = `${scoreEmoji} <b>DETTAGLI GIOCATORE</b>\n\n`;

  // Player info
  message += `🎯 <b>${escapeHtml(opp.player_name)}</b>`;
  if (opp.age) {
    message += ` (${opp.age} anni)`;
  }
  message += '\n';

  if (opp.role_name || opp.role) {
    message += `📍 ${escapeHtml(opp.role_name || opp.role)}\n`;
  }

  if (opp.current_club) {
    message += `🏟️ Attuale: ${escapeHtml(opp.current_club)}\n`;
  }

  if (opp.previous_clubs && opp.previous_clubs.length > 0) {
    message += `📋 Ex: ${opp.previous_clubs.map(escapeHtml).join(', ')}\n`;
  }

  message += '\n';

  // Opportunity details
  message += `💼 <b>${opp.opportunity_type.toUpperCase()}</b>\n`;
  message += `📅 ${formatDate(opp.reported_date)}\n`;
  message += `📊 OB1 Score: <b>${opp.ob1_score}/100</b>\n`;

  // Stats
  if (opp.appearances || opp.goals) {
    message += '\n📈 <b>Statistiche:</b>\n';
    if (opp.appearances) {
      message += `   • Presenze: ${opp.appearances}\n`;
    }
    if (opp.goals) {
      message += `   • Gol: ${opp.goals}\n`;
    }
  }

  // Summary
  if (opp.summary && opp.summary.length > 10) {
    message += '\n💬 <i>' + escapeHtml(opp.summary.slice(0, 200));
    if (opp.summary.length > 200) {
      message += '...';
    }
    message += '</i>\n';
  }

  // Score breakdown
  if (opp.score_breakdown) {
    message += '\n━━━━━━━━━━━━━━\n';
    message += '<b>📊 Score Breakdown:</b>\n';

    const breakdown = opp.score_breakdown;
    message += `   ⏰ Freshness: ${breakdown.freshness}\n`;
    message += `   💼 Tipo: ${breakdown.opportunity_type}\n`;
    message += `   ⭐ Esperienza: ${breakdown.experience}\n`;
    message += `   🎂 Età: ${breakdown.age}\n`;
    message += `   📰 Fonte: ${breakdown.source}\n`;
    message += `   ✅ Completezza: ${breakdown.completeness}\n`;
  }

  // Source + Dashboard
  message += '\n━━━━━━━━━━━━━━━━━━━━\n';
  message += `📰 ${escapeHtml(opp.source_name)}`;
  if (opp.source_url) {
    message += ` | <a href="${opp.source_url}">Articolo</a>`;
  }
  message += `\n🌐 <a href="${DASHBOARD_URL}">Dashboard</a>`;

  return message;
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
