/**
 * NLP-001: Natural Language Processing for Telegram Bot
 * Parses Italian natural language queries into structured intents
 *
 * PHILOSOPHY: Be permissive! Any reasonable query should return results.
 * When in doubt, show the list rather than asking for clarification.
 */

export interface ParsedIntent {
  intent: 'search' | 'list_hot' | 'list_warm' | 'list_all' | 'stats' | 'help' | 'dna_top' | 'dna_club' | 'create_watch' | 'unknown';
  filters: {
    role?: string;
    roles?: string[];      // For watch profiles: multiple roles
    type?: string;
    types?: string[];      // For watch profiles: multiple types
    ageMin?: number;
    ageMax?: number;
    minScore?: number;
    query?: string;
    limit?: number;
    nationality?: string;        // e.g., 'sudamericano', 'europeo'
    requiresEUPassport?: boolean; // "con passaporto comunitario"
  };
  confidence: number;
  interpretation?: string;
  warning?: string;  // Warning message for unavailable features
}

// Role mappings (Italian variants → normalized)
const ROLE_PATTERNS: Record<string, RegExp> = {
  'centrocampista': /\b(centrocamp\w*|cc|mediano|mezzala|regista|trequartista|interno)\b/i,
  'difensore': /\b(difensor\w*|dc|terzin\w*|central\w*|stopper|libero)\b/i,
  'attaccante': /\b(attaccant\w*|punt\w*|bomber|ala|esterno.?offensiv\w*|prima.?punta|seconda.?punta|goleador)\b/i,
  'portiere': /\b(portier\w*|gk|goalkeeper|numero.?1)\b/i,
};

// Nationality/region patterns for future use
const NATIONALITY_PATTERNS: Record<string, RegExp> = {
  'sudamericano': /\b(sudamerican\w*|sud.?american\w*|argentino|brasiliano|uruguaiano|colombiano|cileno|peruviano|paraguaiano|venezuelano|ecuadoriano|boliviano)\b/i,
  'europeo': /\b(europe\w*|comunitari\w*|passaporto.?(?:eu|ue|comunitari\w*|europe\w*))\b/i,
  'africano': /\b(african\w*|senegalese|nigeriano|camerunese|ivoriano|ghanese|marocchino|egiziano|algerino|tunisino)\b/i,
};

// Opportunity type mappings
const TYPE_PATTERNS: Record<string, RegExp> = {
  'svincolato': /\b(svincolat\w*|liber\w*|free|senza.?contratto|a.?zero)\b/i,
  'prestito': /\b(prestit\w*|loan|in.?prestito|temporane\w*)\b/i,
  'rescissione': /\b(rescission\w*|risoluzion\w*|consensual\w*)\b/i,
  'scadenza': /\b(scadenz\w*|contratto.?in.?scadenza|fine.?contratto)\b/i,
};

// Intent patterns - EXPANDED to be more permissive
const INTENT_PATTERNS = {
  // Asking for the best / top opportunities
  list_hot: /\b(miglior\w*|top|hot|priorit\w*|urgent\w*|imperdibil\w*|da.?prendere|consiglia|raccomand\w*|important\w*|principal\w*)\b/i,

  // Asking for interesting opportunities
  list_warm: /\b(interessant\w*|warm|tener\w*.?d.?occhio|monitorare|seguire|valutare|notevol\w*)\b/i,

  // Asking for a list / all opportunities
  list_all: /\b(tutt\w*|lista|elenco|complet\w*|mostrar?\w*|far.?vedere|veder\w*|elenca|dammi|dimmi)\b/i,

  // Asking for stats / numbers
  stats: /\b(statistic\w*|numer\w*|quant\w*|riepilog\w*|report|situazione|sommario)\b/i,

  // Asking for help
  help: /\b(aiuto|help|come.?funzion\w*|cosa.?(puoi|sai)|comand\w*|istruzioni)\b/i,

  // Explicit search
  search: /\b(cerca|trovami|chi.?[eè]|info.?su|dimmi.?di|parlami.?di|conosc\w*)\b/i,

  // GENERIC QUESTION PATTERNS - These indicate user wants to see opportunities
  generic_list: /\b(occasioni|opportunit\w*|giocator\w*|calciat\w*|disponibil\w*|mercato|news|novit\w*|aggiornament\w*|ricostruire|rifondare|rinforzare|acquist\w*|prendere)\b/i,

  // Time-related patterns (oggi, recenti, ultimi, nuovi)
  time_query: /\b(oggi|ieri|recent\w*|ultim\w*|nuov\w*|ultimo|fresc\w*|appena)\b/i,

  // Situazioni di necessità ("devo ricostruire", "fallito", "serve rinforzare")
  need_players: /\b(devo|dobbiamo|bisogna|serve|servono)\b.*\b(ricostruire|rinforzare|comprare|prendere|trovare|cercare|squadra|rosa)\b/i,

  // DNA-001: DNA matching patterns
  dna_top: /\b(talenti|prodigy|giovani.?promesse|migliori.?talenti|top.?talenti|squadre?.?b|under\s?23|next\s?gen|futuro|primavera)\b/i,
  dna_club: /\b(match\w*|fit|adatti?\s*(a|per)?|compatibil\w*|profilo|dna)\b/i,

  // SCORE-002: Watch profile creation via natural language
  create_watch: /\b(avvisami|notificami|alertami|segnalami|fammi sapere|tienimi aggiornato|monitora|segui|watch)\b.*\b(quando|se|trovi|esce|arriva|disponibile)\b/i,
  create_watch_alt: /\b(voglio|vorrei)\b.*\b(essere avvisato|ricevere notifiche|sapere quando)\b/i,
};

// Age patterns
const AGE_PATTERNS = {
  young: { pattern: /\b(giovan\w*|under.?(\d+)|u(\d+)|ragaz\w*)\b/i, extractAge: extractUnderAge },
  experienced: { pattern: /\b(espert\w*|over.?(\d+)|veteran\w*|esperto)\b/i, extractAge: extractOverAge },
  specific: { pattern: /\b(\d{2})\s*anni\b/i, extractAge: extractSpecificAge },
};

function extractUnderAge(match: RegExpMatchArray): { min?: number; max?: number } {
  const num = match[2] || match[3];
  if (num) {
    return { max: parseInt(num) };
  }
  return { max: 25 }; // Default "giovane" = under 25
}

function extractOverAge(match: RegExpMatchArray): { min?: number; max?: number } {
  const num = match[2];
  if (num) {
    return { min: parseInt(num) };
  }
  return { min: 30 }; // Default "esperto" = over 30
}

function extractSpecificAge(match: RegExpMatchArray): { min?: number; max?: number } {
  const age = parseInt(match[1]);
  return { min: age, max: age };
}

// Map role name to position codes (for watch profiles)
function mapRoleToPositions(role: string): string[] {
  const mappings: Record<string, string[]> = {
    'centrocampista': ['CC', 'MED', 'TRQ'],
    'difensore': ['DC', 'TD', 'TS'],
    'attaccante': ['ATT', 'PC'],
    'portiere': ['POR'],
    'esterno': ['ES', 'ED', 'AS', 'AD'],
    'terzino': ['TD', 'TS'],
  };
  return mappings[role.toLowerCase()] || [];
}

// Detect if text contains a proper name (capitalized words not matching keywords)
function extractPlayerName(text: string): string | null {
  // Remove common words and see if we have capitalized names
  const cleanText = text
    .replace(/\b(cerca|trovami|chi|è|e|info|su|dimmi|di|mostra|voglio|vedere|le|i|gli|la|il|lo|un|una|dei|delle|del|della)\b/gi, '')
    .trim();

  // Look for capitalized word sequences (likely names)
  const namePattern = /\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b/g;
  const matches = cleanText.match(namePattern);

  if (matches && matches.length > 0) {
    // Filter out known keywords
    const keywords = ['Migliori', 'Top', 'Tutti', 'Hot', 'Warm', 'Cold', 'Lista', 'Occasioni'];
    const names = matches.filter(m => !keywords.includes(m));
    if (names.length > 0) {
      return names.join(' ');
    }
  }

  return null;
}

/**
 * Check if the query is a greeting or small talk (not a data query)
 */
function isGreetingOrSmallTalk(text: string): boolean {
  const greetings = /^(ciao|salve|buongiorno|buonasera|hey|hi|hello|ehi)[\s!?]*$/i;
  const smallTalk = /^(come stai|tutto bene|ok|grazie|thanks)[\s!?]*$/i;
  return greetings.test(text.trim()) || smallTalk.test(text.trim());
}

/**
 * Main NLP parser - converts natural language to structured intent
 *
 * PRINCIPLE: Be generous in interpretation. If user asks anything about
 * players, opportunities, market - show them data!
 */
export function parseNaturalQuery(text: string): ParsedIntent {
  const lower = text.toLowerCase().trim();
  const filters: ParsedIntent['filters'] = {};
  let confidence = 0;
  let intent: ParsedIntent['intent'] = 'unknown';
  const interpretationParts: string[] = [];

  // Handle greetings separately
  if (isGreetingOrSmallTalk(lower)) {
    return {
      intent: 'help',
      filters: {},
      confidence: 0.9,
      interpretation: 'benvenuto',
    };
  }

  // 1. Check for explicit help request
  if (INTENT_PATTERNS.help.test(lower)) {
    return {
      intent: 'help',
      filters: {},
      confidence: 0.95,
    };
  }

  // 2. Check for stats request
  if (INTENT_PATTERNS.stats.test(lower) && !INTENT_PATTERNS.generic_list.test(lower)) {
    return {
      intent: 'stats',
      filters: {},
      confidence: 0.9,
    };
  }

  // 3. Check for player name (high priority)
  const playerName = extractPlayerName(text);
  if (playerName && playerName.length > 2) {
    filters.query = playerName;
    intent = 'search';
    confidence += 0.7;
    interpretationParts.push(`"${playerName}"`);
  }

  // 4. Check for role filters
  for (const [role, pattern] of Object.entries(ROLE_PATTERNS)) {
    if (pattern.test(lower)) {
      filters.role = role;
      confidence += 0.25;
      interpretationParts.push(role);
      if (intent === 'unknown') intent = 'list_all';
      break;
    }
  }

  // 5. Check for opportunity type filters
  for (const [type, pattern] of Object.entries(TYPE_PATTERNS)) {
    if (pattern.test(lower)) {
      filters.type = type;
      confidence += 0.25;
      interpretationParts.push(type);
      if (intent === 'unknown') intent = 'list_all';
      break;
    }
  }

  // 6. Check for age filters
  for (const [ageType, { pattern, extractAge }] of Object.entries(AGE_PATTERNS)) {
    const match = lower.match(pattern);
    if (match) {
      const ageRange = extractAge(match);
      if (ageRange.min) filters.ageMin = ageRange.min;
      if (ageRange.max) filters.ageMax = ageRange.max;
      confidence += 0.2;

      if (ageRange.min && ageRange.max && ageRange.min === ageRange.max) {
        interpretationParts.push(`${ageRange.min} anni`);
      } else if (ageRange.max) {
        interpretationParts.push(`under ${ageRange.max}`);
      } else if (ageRange.min) {
        interpretationParts.push(`over ${ageRange.min}`);
      }

      if (intent === 'unknown') intent = 'list_all';
      break;
    }
  }

  // 6b. Check for nationality filters (DATA-001)
  let warnings: string[] = [];
  for (const [nationality, pattern] of Object.entries(NATIONALITY_PATTERNS)) {
    if (pattern.test(lower)) {
      filters.nationality = nationality;
      confidence += 0.15;
      interpretationParts.push(nationality);

      // Check for EU passport requirement
      if (NATIONALITY_PATTERNS['europeo'].test(lower) && nationality !== 'europeo') {
        filters.requiresEUPassport = true;
        interpretationParts.push('con passaporto UE');
      }

      // Add warning that nationality data is limited
      warnings.push('I dati di nazionalità sono ancora limitati nel database.');

      if (intent === 'unknown') intent = 'list_all';
      break;
    }
  }

  // 7. Check for quality intents (hot/warm)
  if (INTENT_PATTERNS.list_hot.test(lower)) {
    intent = 'list_hot';
    confidence = Math.max(confidence, 0.8);
    if (!interpretationParts.includes('migliori')) {
      interpretationParts.unshift('migliori');
    }
  } else if (INTENT_PATTERNS.list_warm.test(lower)) {
    intent = 'list_warm';
    confidence = Math.max(confidence, 0.75);
    if (!interpretationParts.includes('interessanti')) {
      interpretationParts.unshift('interessanti');
    }
  }

  // 8. Handle generic list requests and time queries
  // "le occasioni di oggi", "opportunità recenti", "giocatori disponibili", etc.
  const hasGenericListWord = INTENT_PATTERNS.generic_list.test(lower);
  const hasTimeWord = INTENT_PATTERNS.time_query.test(lower);
  const hasListIntent = INTENT_PATTERNS.list_all.test(lower);
  const hasNeedPlayers = INTENT_PATTERNS.need_players?.test(lower);

  if ((hasGenericListWord || hasTimeWord || hasListIntent || hasNeedPlayers) && intent === 'unknown') {
    intent = 'list_all';
    confidence = Math.max(confidence, 0.7);

    if (hasTimeWord) {
      interpretationParts.push('recenti');
    }
    if (hasNeedPlayers) {
      interpretationParts.push('svincolati disponibili');
      // Se cercano giocatori per ricostruire, filtra per svincolati
      filters.type = 'svincolato';
    }
  }

  // 9. Handle limit requests
  const limitMatch = lower.match(/\b(prim[oiae]|top\s*)?(\d+)\b/);
  if (limitMatch && limitMatch[2]) {
    const num = parseInt(limitMatch[2]);
    if (num >= 1 && num <= 20) {
      filters.limit = num;
    }
  }

  // 10. SCORE-002: Check for watch profile creation
  const wantsWatch = INTENT_PATTERNS.create_watch.test(lower) ||
    (INTENT_PATTERNS as any).create_watch_alt?.test(lower);

  if (wantsWatch) {
    intent = 'create_watch';
    confidence = Math.max(confidence, 0.9);

    // Extract role for watch
    if (filters.role) {
      filters.roles = mapRoleToPositions(filters.role);
    }

    // Extract type for watch
    if (filters.type) {
      filters.types = [filters.type];
    }

    interpretationParts.unshift('crea alert');
  }

  // 11. DNA-001: Check for DNA matching intents
  if (intent === 'unknown' && INTENT_PATTERNS.dna_top.test(lower)) {
    intent = 'dna_top';
    confidence = Math.max(confidence, 0.85);
    interpretationParts.unshift('talenti squadre B');
  } else if (intent === 'unknown' && INTENT_PATTERNS.dna_club.test(lower)) {
    // Try to extract club name for DNA match, skipping common verbs
    // Handles: "adatti a rifondare il rimini fc", "per il pescara", "match pescara"
    const clubPatterns = [
      /(?:rifondare|ricostruire|rinforzare|aiutare|sistemare)\s+(?:il\s+)?(\w+)(?:\s+fc)?/i,
      /(?:per|a)\s+(?:il\s+)?(\w+)(?:\s+fc)?/i,
      /(?:adatti?\s*(?:a|per)?)\s+(?:il\s+)?(\w+)(?:\s+fc)?/i,
      /(?:match|dna|profilo)\s+(?:per\s+)?(?:il\s+)?(\w+)/i,
    ];

    let clubName: string | null = null;
    for (const pattern of clubPatterns) {
      const match = lower.match(pattern);
      if (match && match[1]) {
        // Skip common verbs that might get matched
        const skipWords = ['rifondare', 'ricostruire', 'rinforzare', 'aiutare', 'sistemare', 'dei', 'giocatori', 'adatti'];
        if (!skipWords.includes(match[1].toLowerCase())) {
          clubName = match[1];
          break;
        }
      }
    }

    if (clubName) {
      filters.query = clubName;
      intent = 'dna_club';
      confidence = Math.max(confidence, 0.8);
      interpretationParts.push(`DNA match per ${clubName}`);
    }
  }

  // 12. FALLBACK: If we still don't know what to do but the message
  // looks like a question about football/market, show all opportunities
  if (intent === 'unknown') {
    const looksLikeQuestion = /[?]|\b(ci sono|c'è|cosa|quali|che)\b/i.test(lower);
    const footballRelated = /\b(gioc\w*|calc\w*|serie|mercato|trasfer\w*|acquist\w*)\b/i.test(lower);

    if (looksLikeQuestion || footballRelated || lower.length < 30) {
      // Short message or question? Just show the list!
      intent = 'list_all';
      confidence = 0.5;
    }
  }

  // Build interpretation string
  let interpretation: string | undefined;
  if (interpretationParts.length > 0) {
    interpretation = interpretationParts.join(' ');
  }

  // Build warning if any
  const warning = warnings.length > 0 ? warnings.join(' ') : undefined;

  return {
    intent,
    filters,
    confidence: Math.min(confidence, 1),
    interpretation,
    warning,
  };
}

/**
 * Generate a natural response prefix based on the parsed intent
 */
export function getInterpretationMessage(parsed: ParsedIntent): string {
  if (!parsed.interpretation) {
    return '';
  }

  switch (parsed.intent) {
    case 'search':
      return `🔍 Cerco: ${parsed.interpretation}\n\n`;
    case 'list_hot':
      return `🔥 Ecco i ${parsed.interpretation}:\n\n`;
    case 'list_warm':
      return `⚡ Opportunità ${parsed.interpretation}:\n\n`;
    default:
      return '';
  }
}
