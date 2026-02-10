/**
 * Smart Search v3 - LLM-first + Web fallback
 *
 * Flusso:
 * 1. DS chiede qualcosa (qualsiasi linguaggio naturale)
 * 2. LLM interpreta e estrae JSON strutturato
 * 3. Cerchiamo nelle opportunità locali
 * 4. Se pochi/nessun risultato → cerca sul web in tempo reale
 * 5. Rispondiamo con risultati veri
 */

import { Env, Opportunity } from './types';
import { sendMessage, sendMessageWithKeyboard } from './telegram';
import { fetchData } from './data';

// URL per squadre B (giovani talenti da Serie A)
const SQUADRE_B_URL = 'https://raw.githubusercontent.com/mtornani/ob1-serie-c/main/data/players/squadre_b.json';

interface SquadraBPlayer {
  id: string;
  name: string;
  birth_year: number;
  nationality: string;
  primary_position: string;
  secondary_positions: string[];
  parent_club: string;
  current_team: string;
  transfer_status: string;
  market_value: number;
  skills?: Record<string, number>;
}

/**
 * Converte giocatori squadre B in formato Opportunity
 */
function convertSquadraBToOpportunity(player: SquadraBPlayer): Opportunity {
  const age = new Date().getFullYear() - player.birth_year;
  const avgSkill = player.skills
    ? Math.round(Object.values(player.skills).reduce((a, b) => a + b, 0) / Object.values(player.skills).length)
    : 70;

  return {
    id: player.id,
    player_name: player.name,
    age,
    role: player.primary_position,
    role_name: getRoleName(player.primary_position),
    opportunity_type: player.transfer_status === 'disponibile_prestito' ? 'prestito' :
                     player.transfer_status === 'in_uscita' ? 'mercato' : 'sconosciuto',
    reported_date: new Date().toISOString().split('T')[0],
    source_name: 'Squadre B',
    source_url: '',
    current_club: player.current_team,
    summary: `Giovane talento del ${player.parent_club}, gioca in ${player.current_team}. ${player.transfer_status === 'disponibile_prestito' ? 'Disponibile in prestito.' : ''}`,
    nationality: player.nationality,
    second_nationality: undefined,
    ob1_score: Math.min(95, avgSkill + 5), // Bonus per talenti squadre B
    classification: avgSkill >= 75 ? 'hot' : 'warm',
  };
}

function getRoleName(code: string): string {
  const map: Record<string, string> = {
    'PO': 'Portiere', 'DC': 'Difensore Centrale', 'TD': 'Terzino Destro', 'TS': 'Terzino Sinistro',
    'CC': 'Centrocampista', 'MED': 'Mediano', 'TRQ': 'Trequartista', 'ED': 'Esterno Destro',
    'ES': 'Esterno Sinistro', 'AD': 'Ala Destra', 'AS': 'Ala Sinistra', 'ATT': 'Attaccante', 'PC': 'Punta'
  };
  return map[code] || code;
}

/**
 * Carica dati unificati (opportunità + squadre B)
 */
async function fetchAllData(env: Env): Promise<Opportunity[]> {
  const mainData = await fetchData(env);
  const opportunities = mainData?.opportunities || [];

  // Prova a caricare squadre B
  try {
    const response = await fetch(SQUADRE_B_URL);
    if (response.ok) {
      const squadreB: SquadraBPlayer[] = await response.json();
      const converted = squadreB
        .filter(p => p.transfer_status !== 'incedibile') // Escludi incedibili
        .map(convertSquadraBToOpportunity);
      console.log(`Loaded ${converted.length} players from Squadre B`);
      return [...opportunities, ...converted];
    }
  } catch (e) {
    console.log('Could not load Squadre B data:', e);
  }

  return opportunities;
}

interface SearchFilters {
  roles?: string[];        // ['DC', 'CC', 'ATT', etc.]
  types?: string[];        // ['svincolato', 'prestito', 'rescissione']
  maxAge?: number;
  minAge?: number;
  nationalities?: string[];
  characteristics?: string[];  // ['veloce', 'tecnico', 'fisico']
  maxCost?: boolean;       // true = cerca low cost
}

interface LLMResponse {
  understood: boolean;
  filters: SearchFilters;
  searchDescription: string;  // "Attaccanti giovani e economici"
  clarificationNeeded?: string;
}

/**
 * Chiama OpenRouter per interpretare la richiesta
 */
async function interpretWithLLM(text: string, env: Env): Promise<LLMResponse | null> {
  if (!env.OPENROUTER_API_KEY) return null;

  const systemPrompt = `Sei un assistente per direttori sportivi di calcio Serie C italiana.
Interpreta la richiesta e restituisci SOLO un JSON valido con questi campi:

{
  "understood": true/false,
  "filters": {
    "roles": ["DC", "TD", "TS", "CC", "MED", "TRQ", "ED", "ES", "AD", "AS", "ATT", "PC", "PO"],
    "types": ["svincolato", "prestito", "rescissione", "scadenza"],
    "maxAge": numero o null,
    "minAge": numero o null,
    "nationalities": ["Italia", "Argentina", "Brasile", etc.] o null,
    "characteristics": ["veloce", "tecnico", "fisico", "leader", "gol"] o null,
    "maxCost": true se cerca low cost/economico/gratis
  },
  "searchDescription": "breve descrizione della ricerca in italiano",
  "clarificationNeeded": null o "domanda se serve chiarimento"
}

REGOLE:
- "minima spesa" / "economico" / "low cost" / "gratis" → maxCost: true, types: ["svincolato", "prestito"]
- "massima resa" / "rendimento" → cerca giocatori con buon score
- "giovane" / "prospetto" / "scommessa" → maxAge: 23-25
- "esperto" / "leader" / "salvezza" → minAge: 27+
- "sudamericano" → nationalities: ["Argentina", "Brasile", "Uruguay", "Colombia", ...]
- "campionato sammarinese" / "San Marino" → cerca Serie C, non c'è filtro specifico, ignora
- "attaccante" / "punta" → roles: ["ATT", "PC"]
- "difensore" → roles: ["DC", "TD", "TS"]
- "centrocampista" → roles: ["CC", "MED", "TRQ"]

Se la richiesta è un saluto (ciao, buongiorno), rispondi con understood: false e clarificationNeeded con un messaggio di benvenuto.

IMPORTANTE: Rispondi SOLO con il JSON, niente altro.`;

  try {
    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.OPENROUTER_API_KEY}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://ob1-scout.pages.dev',
        'X-Title': 'OB1 Scout Bot',
      },
      body: JSON.stringify({
        model: 'google/gemma-3-27b-it:free',
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: text }
        ],
        max_tokens: 500,
        temperature: 0.1,
      }),
    });

    if (!response.ok) {
      console.error('OpenRouter error:', await response.text());
      return null;
    }

    const data = await response.json() as any;
    const content = data.choices?.[0]?.message?.content?.trim();

    if (!content) return null;

    // Pulisci il JSON
    let jsonStr = content;
    if (jsonStr.startsWith('```json')) jsonStr = jsonStr.slice(7);
    if (jsonStr.startsWith('```')) jsonStr = jsonStr.slice(3);
    if (jsonStr.endsWith('```')) jsonStr = jsonStr.slice(0, -3);

    const parsed = JSON.parse(jsonStr.trim());
    console.log('LLM interpreted:', JSON.stringify(parsed));
    return parsed;

  } catch (error) {
    console.error('LLM interpretation error:', error);
    return null;
  }
}

/**
 * Fallback parser per keyword (quando LLM non disponibile)
 */
function parseKeywords(text: string): SearchFilters {
  const lower = text.toLowerCase();
  const filters: SearchFilters = {};

  // Ruoli
  const roleMap: Record<string, string[]> = {
    'portiere': ['PO'],
    'difensore': ['DC', 'TD', 'TS'],
    'terzino': ['TD', 'TS'],
    'centrocampista': ['CC', 'MED', 'TRQ'],
    'mediano': ['MED'],
    'trequartista': ['TRQ'],
    'esterno': ['ED', 'ES'],
    'ala': ['AD', 'AS'],
    'attaccante': ['ATT', 'PC'],
    'punta': ['PC', 'ATT'],
  };

  for (const [kw, roles] of Object.entries(roleMap)) {
    if (lower.includes(kw)) {
      filters.roles = roles;
      break;
    }
  }

  // Tipi
  if (lower.includes('svincolat') || lower.includes('gratis') || lower.includes('parametro zero')) {
    filters.types = ['svincolato'];
  } else if (lower.includes('prestito')) {
    filters.types = ['prestito'];
  }

  // Età
  if (lower.includes('giovane') || lower.includes('prospetto') || lower.includes('scommessa')) {
    filters.maxAge = 23;
  }
  if (lower.includes('esperto') || lower.includes('esperienza')) {
    filters.minAge = 28;
  }

  // Costo
  if (lower.includes('economic') || lower.includes('low cost') || lower.includes('minima spesa')) {
    filters.maxCost = true;
    if (!filters.types) filters.types = ['svincolato', 'prestito'];
  }

  return filters;
}

/**
 * Cerca nelle opportunità con i filtri
 */
function searchOpportunities(opportunities: Opportunity[], filters: SearchFilters): Opportunity[] {
  let results = [...opportunities];

  // Filtra per ruolo
  if (filters.roles?.length) {
    results = results.filter(opp =>
      filters.roles!.some(r => opp.role?.toUpperCase() === r.toUpperCase())
    );
  }

  // Filtra per tipo
  if (filters.types?.length) {
    results = results.filter(opp =>
      filters.types!.some(t => opp.opportunity_type?.toLowerCase().includes(t.toLowerCase()))
    );
  }

  // Filtra per età
  if (filters.maxAge) {
    results = results.filter(opp => !opp.age || opp.age <= filters.maxAge!);
  }
  if (filters.minAge) {
    results = results.filter(opp => !opp.age || opp.age >= filters.minAge!);
  }

  // Filtra per nazionalità (include second_nationality)
  if (filters.nationalities?.length) {
    console.log('Filtering by nationalities:', filters.nationalities);
    const filtered = results.filter(opp => {
      const nat1 = (opp.nationality || '').toLowerCase();
      const nat2 = (opp.second_nationality || '').toLowerCase();
      const combined = nat1 + ' ' + nat2;
      const match = filters.nationalities!.some(n => combined.includes(n.toLowerCase()));
      if (match) console.log(`Match: ${opp.player_name} - ${nat1}/${nat2}`);
      return match;
    });
    console.log(`Nationality filter: ${filtered.length} matches from ${results.length}`);
    if (filtered.length > 0) results = filtered;
  }

  // Cerca caratteristiche nel summary
  if (filters.characteristics?.length) {
    const filtered = results.filter(opp => {
      const summary = (opp.summary || '').toLowerCase();
      return filters.characteristics!.some(c => summary.includes(c));
    });
    if (filtered.length > 0) results = filtered;
  }

  // Ordina per score
  results.sort((a, b) => (b.ob1_score || 0) - (a.ob1_score || 0));

  return results;
}

/**
 * Formatta i risultati
 */
function formatResults(
  results: Opportunity[],
  description: string,
  filters: SearchFilters,
  totalOpportunities: number,
  limit: number = 5
): string {
  // Messaggio se nessun risultato con i filtri specifici
  if (results.length === 0) {
    let msg = `😔 <b>Nessun risultato</b>\n\n`;
    msg += `Non ho trovato: "${description}"\n\n`;

    // Suggerisci alternative
    if (filters.nationalities?.length) {
      msg += `⚠️ <i>Al momento non ho giocatori ${filters.nationalities.includes('Argentina') ? 'sudamericani' : 'stranieri'} nel database.</i>\n\n`;
    }

    msg += `📊 Ho ${totalOpportunities} opportunità totali.\n`;
    msg += `Prova /hot per vedere le migliori o descrivi diversamente.`;
    return msg;
  }

  let message = `🎯 <b>${description}</b>\n\n`;

  const shown = results.slice(0, limit);

  for (const opp of shown) {
    const emoji = opp.ob1_score >= 80 ? '🔥' : opp.ob1_score >= 60 ? '⚡' : '📊';
    const age = opp.age ? `${opp.age} anni` : 'età n.d.';

    message += `${emoji} <b>${opp.player_name}</b> (${opp.ob1_score}/100)\n`;
    message += `📍 ${opp.role_name || opp.role} | ${age}\n`;
    message += `🏷️ ${opp.opportunity_type?.toUpperCase()}\n`;

    if (opp.current_club) {
      message += `🏟️ ${opp.current_club}\n`;
    }

    if (opp.summary) {
      const short = opp.summary.length > 100 ? opp.summary.slice(0, 100) + '...' : opp.summary;
      message += `💡 <i>${short}</i>\n`;
    }

    if (opp.source_url) {
      message += `🔗 <a href="${opp.source_url}">Fonte</a>\n`;
    }

    message += '\n';
  }

  if (results.length > limit) {
    message += `📋 <i>Mostrati ${limit} di ${results.length} risultati</i>`;
  }

  return message;
}

/**
 * Cerca sul web quando il database locale non ha risultati
 */
async function searchWebFallback(query: string, filters: SearchFilters, env: Env): Promise<string | null> {
  if (!env.OPENROUTER_API_KEY) return null;

  // Costruisci query di ricerca
  let searchQuery = 'calciomercato Serie C ';
  if (filters.roles?.length) {
    const roleNames: Record<string, string> = {
      'DC': 'difensore centrale', 'TD': 'terzino destro', 'TS': 'terzino sinistro',
      'CC': 'centrocampista', 'ATT': 'attaccante', 'PC': 'punta', 'PO': 'portiere'
    };
    searchQuery += (roleNames[filters.roles[0]] || filters.roles[0]) + ' ';
  }
  if (filters.nationalities?.length) {
    searchQuery += filters.nationalities.slice(0, 2).join(' o ') + ' ';
  }
  if (filters.maxAge) searchQuery += `under ${filters.maxAge} `;
  if (filters.types?.includes('svincolato')) searchQuery += 'svincolato ';

  searchQuery += '2026';

  console.log('Web search query:', searchQuery);

  try {
    // Usa LLM per cercare informazioni sul web
    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${env.OPENROUTER_API_KEY}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://ob1-scout.pages.dev',
        'X-Title': 'OB1 Scout Bot',
      },
      body: JSON.stringify({
        model: 'google/gemma-3-27b-it:free',
        messages: [
          {
            role: 'system',
            content: `Sei un esperto di calciomercato Serie C italiana.
L'utente cerca: "${query}"

Basandoti sulle tue conoscenze del mercato calcistico italiano (fino al 2025), suggerisci 3-5 nomi REALI di giocatori che potrebbero corrispondere a questa ricerca.

Per ogni giocatore includi:
- Nome completo
- Ruolo
- Età approssimativa
- Nazionalità
- Ultima squadra nota
- Perché potrebbe essere interessante

Se non conosci giocatori specifici per questa ricerca, dillo chiaramente.
Rispondi in italiano, formato lista.`
          },
          { role: 'user', content: query }
        ],
        max_tokens: 800,
        temperature: 0.3,
      }),
    });

    if (!response.ok) return null;

    const data = await response.json() as any;
    const content = data.choices?.[0]?.message?.content?.trim();

    if (!content || content.includes('non conosco') || content.includes('non ho informazioni')) {
      return null;
    }

    return content;

  } catch (error) {
    console.error('Web search error:', error);
    return null;
  }
}

/**
 * Handler principale
 */
export async function handleSmartSearch(chatId: number, text: string, env: Env): Promise<boolean> {
  // 1. Prova con LLM (intelligente)
  const llmResponse = await interpretWithLLM(text, env);

  let filters: SearchFilters;
  let description: string;

  if (llmResponse) {
    // LLM ha capito
    if (!llmResponse.understood || llmResponse.clarificationNeeded) {
      // Serve chiarimento o è un saluto
      const clarification = llmResponse.clarificationNeeded ||
        `Ciao! Sono OB1 Scout, il tuo assistente per il calciomercato Serie C.\n\nCosa cerchi oggi?`;

      const keyboard = {
        inline_keyboard: [
          [{ text: '🔥 Migliori occasioni', callback_data: 'search:migliori opportunità' }],
          [{ text: '⚽ Attaccanti', callback_data: 'search:attaccanti svincolati' }],
          [{ text: '🛡️ Difensori', callback_data: 'search:difensori' }],
          [{ text: '🎯 Centrocampisti', callback_data: 'search:centrocampisti' }],
        ]
      };
      await sendMessageWithKeyboard(env, chatId, clarification, keyboard);
      return true;
    }

    filters = llmResponse.filters;
    description = llmResponse.searchDescription;

  } else {
    // Fallback a keyword parser
    console.log('LLM not available, using keyword parser');
    filters = parseKeywords(text);
    description = 'Risultati ricerca';

    // Se nessun filtro trovato, mostra help
    if (!filters.roles && !filters.types && !filters.maxAge && !filters.minAge && !filters.maxCost) {
      const keyboard = {
        inline_keyboard: [
          [{ text: '🔥 Migliori', callback_data: 'search:migliori' }],
          [{ text: '⚽ Attaccanti', callback_data: 'search:attaccanti' }],
          [{ text: '🛡️ Difensori', callback_data: 'search:difensori' }],
        ]
      };
      await sendMessageWithKeyboard(env, chatId,
        `Cosa cerchi? Scegli una categoria o descrivi il giocatore che ti serve:`,
        keyboard);
      return true;
    }
  }

  // 2. Carica dati unificati (opportunità + squadre B)
  const allOpportunities = await fetchAllData(env);
  if (!allOpportunities?.length) {
    await sendMessage(env, chatId, '❌ Dati non disponibili. Riprova tra poco.');
    return true;
  }

  // 3. Cerca nel database
  const results = searchOpportunities(allOpportunities, filters);

  // 4. Se pochi risultati E filtri specifici → prova web fallback
  const needsWebFallback = results.length < 2 &&
    (filters.nationalities?.length || filters.characteristics?.length);

  if (needsWebFallback) {
    await sendMessage(env, chatId, `🔍 <i>Cerco nel database... pochi risultati locali, consulto altre fonti...</i>`);

    const webResults = await searchWebFallback(text, filters, env);

    if (webResults) {
      let message = `🎯 <b>${description}</b>\n\n`;
      message += `📊 <i>Nel mio database ho ${results.length} risultati.</i>\n\n`;

      if (results.length > 0) {
        message += `<b>Dal database OB1:</b>\n`;
        for (const opp of results.slice(0, 2)) {
          message += `• ${opp.player_name} (${opp.role_name}, ${opp.age || '?'} anni) - ${opp.opportunity_type}\n`;
        }
        message += `\n`;
      }

      message += `<b>💡 Suggerimenti basati sul mercato:</b>\n`;
      message += webResults;
      message += `\n\n<i>⚠️ I suggerimenti sono basati su conoscenze generali. Verifica sempre le fonti ufficiali.</i>`;

      await sendMessage(env, chatId, message);
      return true;
    }
  }

  // 5. Rispondi con risultati locali
  const message = formatResults(results, description, filters, allOpportunities.length);
  await sendMessage(env, chatId, message);

  return true;
}

/**
 * Handler per callback buttons
 */
export async function handleSearchCallback(chatId: number, data: string, env: Env): Promise<void> {
  const searchText = data.replace('search:', '');
  await handleSmartSearch(chatId, searchText, env);
}
