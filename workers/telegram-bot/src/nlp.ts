/**
 * NLP-001: Natural Language Processing for Telegram Bot
 * Parses Italian natural language queries into structured intents
 */

export interface ParsedIntent {
  intent: 'search' | 'list_hot' | 'list_warm' | 'list_all' | 'stats' | 'help' | 'unknown';
  filters: {
    role?: string;
    type?: string;
    ageMin?: number;
    ageMax?: number;
    query?: string;
    limit?: number;
  };
  confidence: number;
  interpretation?: string;
}

// Role mappings (Italian variants → normalized)
const ROLE_PATTERNS: Record<string, RegExp> = {
  'centrocampista': /\b(centrocamp\w*|cc|mediano|mezzala|regista|trequartista)\b/i,
  'difensore': /\b(difensor\w*|dc|terzin\w*|central\w*|stopper|libero)\b/i,
  'attaccante': /\b(attaccant\w*|punt\w*|bomber|ala|esterno.?offensiv\w*|prima.?punta|seconda.?punta)\b/i,
  'portiere': /\b(portier\w*|gk|goalkeeper|numero.?1)\b/i,
};

// Opportunity type mappings
const TYPE_PATTERNS: Record<string, RegExp> = {
  'svincolato': /\b(svincolat\w*|liber\w*|free|senza.?contratto|a.?zero)\b/i,
  'prestito': /\b(prestit\w*|loan|in.?prestito|temporane\w*)\b/i,
  'rescissione': /\b(rescission\w*|risoluzion\w*|consensual\w*)\b/i,
  'scadenza': /\b(scadenz\w*|contratto.?in.?scadenza|fine.?contratto)\b/i,
};

// Intent patterns
const INTENT_PATTERNS = {
  list_hot: /\b(miglior\w*|top|hot|priorit\w*\s*alt\w*|urgent\w*|imperdibil\w*|da.?prendere|consiglia|raccomand)\b/i,
  list_warm: /\b(interessant\w*|warm|tener\w*.?d.?occhio|monitorare|seguire|valutare)\b/i,
  list_all: /\b(tutt\w*|lista|elenco|complet\w*|mostrar\w*\s*tutt)\b/i,
  stats: /\b(statistic\w*|numer\w*|quant\w*|riepilog\w*|report|situazione)\b/i,
  help: /\b(aiuto|help|come.?funzion\w*|cosa.?(puoi|sai)|comand\w*|istruzioni)\b/i,
  search: /\b(cerca|trovami|chi.?[eè]|info.?su|dimmi.?di|parlami.?di|conosc\w*)\b/i,
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

// Detect if text contains a proper name (capitalized words not matching keywords)
function extractPlayerName(text: string): string | null {
  // Remove common words and see if we have capitalized names
  const cleanText = text
    .replace(/\b(cerca|trovami|chi|è|info|su|dimmi|di|mostra|voglio|vedere)\b/gi, '')
    .trim();

  // Look for capitalized word sequences (likely names)
  const namePattern = /\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b/g;
  const matches = cleanText.match(namePattern);

  if (matches && matches.length > 0) {
    // Filter out known keywords
    const keywords = ['Migliori', 'Top', 'Tutti', 'Hot', 'Warm', 'Cold'];
    const names = matches.filter(m => !keywords.includes(m));
    if (names.length > 0) {
      return names.join(' ');
    }
  }

  // Also check for all-lowercase potential names (common in chat)
  // If query is short and doesn't match any intent, treat as name search
  const words = cleanText.split(/\s+/).filter(w => w.length > 2);
  if (words.length <= 3 && words.length > 0) {
    const noIntentMatch = !Object.values(INTENT_PATTERNS).some(p => p.test(cleanText));
    const noRoleMatch = !Object.values(ROLE_PATTERNS).some(p => p.test(cleanText));
    const noTypeMatch = !Object.values(TYPE_PATTERNS).some(p => p.test(cleanText));

    if (noIntentMatch && noRoleMatch && noTypeMatch) {
      return cleanText;
    }
  }

  return null;
}

/**
 * Main NLP parser - converts natural language to structured intent
 */
export function parseNaturalQuery(text: string): ParsedIntent {
  const lower = text.toLowerCase().trim();
  const filters: ParsedIntent['filters'] = {};
  let confidence = 0;
  let intent: ParsedIntent['intent'] = 'unknown';
  const interpretationParts: string[] = [];

  // 1. Check for player name first (highest priority if detected)
  const playerName = extractPlayerName(text);
  if (playerName && playerName.length > 2) {
    filters.query = playerName;
    intent = 'search';
    confidence += 0.7;
    interpretationParts.push(`cercando "${playerName}"`);
  }

  // 2. Check for role filters
  for (const [role, pattern] of Object.entries(ROLE_PATTERNS)) {
    if (pattern.test(lower)) {
      filters.role = role;
      confidence += 0.2;
      interpretationParts.push(role);
      if (intent === 'unknown') intent = 'search';
      break;
    }
  }

  // 3. Check for opportunity type filters
  for (const [type, pattern] of Object.entries(TYPE_PATTERNS)) {
    if (pattern.test(lower)) {
      filters.type = type;
      confidence += 0.2;
      interpretationParts.push(type);
      if (intent === 'unknown') intent = 'search';
      break;
    }
  }

  // 4. Check for age filters
  for (const [ageType, { pattern, extractAge }] of Object.entries(AGE_PATTERNS)) {
    const match = lower.match(pattern);
    if (match) {
      const ageRange = extractAge(match);
      if (ageRange.min) filters.ageMin = ageRange.min;
      if (ageRange.max) filters.ageMax = ageRange.max;
      confidence += 0.15;

      if (ageRange.min && ageRange.max && ageRange.min === ageRange.max) {
        interpretationParts.push(`${ageRange.min} anni`);
      } else if (ageRange.max) {
        interpretationParts.push(`under ${ageRange.max}`);
      } else if (ageRange.min) {
        interpretationParts.push(`over ${ageRange.min}`);
      }

      if (intent === 'unknown') intent = 'search';
      break;
    }
  }

  // 5. Check for explicit intents (can override 'search')
  if (INTENT_PATTERNS.help.test(lower)) {
    intent = 'help';
    confidence = 0.9;
  } else if (INTENT_PATTERNS.stats.test(lower)) {
    intent = 'stats';
    confidence = Math.max(confidence, 0.8);
  } else if (INTENT_PATTERNS.list_hot.test(lower)) {
    intent = 'list_hot';
    confidence = Math.max(confidence, 0.8);
    interpretationParts.unshift('migliori');
  } else if (INTENT_PATTERNS.list_warm.test(lower)) {
    intent = 'list_warm';
    confidence = Math.max(confidence, 0.8);
    interpretationParts.unshift('interessanti');
  } else if (INTENT_PATTERNS.list_all.test(lower)) {
    intent = 'list_all';
    confidence = Math.max(confidence, 0.7);
  }

  // 6. Handle limit requests
  const limitMatch = lower.match(/\b(primo|prima|top\s*)?(\d+)\b/);
  if (limitMatch && limitMatch[2]) {
    const num = parseInt(limitMatch[2]);
    if (num >= 1 && num <= 20) {
      filters.limit = num;
    }
  }

  // 7. Fallback: if we have filters but no clear intent, default to search
  if (intent === 'unknown' && (filters.role || filters.type || filters.ageMin || filters.ageMax)) {
    intent = 'search';
    confidence = Math.max(confidence, 0.5);
  }

  // Build interpretation string
  let interpretation: string | undefined;
  if (interpretationParts.length > 0) {
    interpretation = interpretationParts.join(' ');
  }

  return {
    intent,
    filters,
    confidence: Math.min(confidence, 1),
    interpretation,
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
