/**
 * NLP-002: LLM-based Intent Classification (Fallback)
 *
 * Usa Cloudflare AI quando il regex-based NLP non è sicuro.
 * Modello: @cf/meta/llama-3.1-8b-instruct (gratuito)
 */

import { Ai } from '@cloudflare/ai';

export interface ClassifiedIntent {
  intent: 'talent_search' | 'list_opportunities' | 'stats' | 'help' | 'greeting' | 'unknown';
  filters: {
    role?: string;        // "terzino", "centrocampista", etc.
    position?: string;    // "TD", "CC", etc.
    characteristic?: string; // "veloce", "che imposta", etc.
    type?: string;        // "svincolato", "prestito"
    age?: string;         // "giovane", "under 25"
  };
  confidence: number;
  explanation?: string;
}

const SYSTEM_PROMPT = `Sei un assistente per classificare richieste di scouting calcistico in italiano.

INTENTI POSSIBILI:
- talent_search: L'utente cerca un giocatore con caratteristiche specifiche (ruolo, skills, età)
- list_opportunities: L'utente vuole vedere opportunità di mercato disponibili
- stats: L'utente chiede statistiche o numeri
- help: L'utente chiede come funziona il bot
- greeting: Saluto semplice
- unknown: Non riesco a classificare

RUOLI CALCISTICI:
- Difensori: terzino destro (TD), terzino sinistro (TS), difensore centrale (DC)
- Centrocampisti: centrocampista (CC), mediano (MED), trequartista (TRQ)
- Esterni: ala destra (AD), ala sinistra (AS), esterno destro (ED), esterno sinistro (ES)
- Attaccanti: attaccante (ATT), prima punta (PC)
- Portiere: portiere (POR)

CARATTERISTICHE COMUNI:
- veloce, rapido, tecnico, fisico, forte
- che imposta, che costruisce, box-to-box
- che pressa, aggressivo, che spinge

Rispondi SOLO con JSON valido, nessun altro testo.`;

const USER_PROMPT_TEMPLATE = `Classifica questa richiesta:
"{query}"

Rispondi con questo JSON:
{
  "intent": "talent_search|list_opportunities|stats|help|greeting|unknown",
  "filters": {
    "role": "ruolo in italiano se specificato",
    "position": "codice posizione (TD/TS/DC/CC/etc) se identificabile",
    "characteristic": "caratteristica principale richiesta",
    "type": "svincolato/prestito se specificato",
    "age": "fascia età se specificata"
  },
  "confidence": 0.0-1.0,
  "explanation": "breve spiegazione"
}`;

/**
 * Classifica l'intent usando Cloudflare AI
 */
export async function classifyWithLLM(
  ai: Ai,
  query: string
): Promise<ClassifiedIntent | null> {
  try {
    const userPrompt = USER_PROMPT_TEMPLATE.replace('{query}', query);

    const response = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: userPrompt }
      ],
      max_tokens: 256,
      temperature: 0.1, // Bassa per risposte consistenti
    });

    // Parse JSON dalla risposta
    const text = (response as any).response || '';

    // Estrai JSON dalla risposta (potrebbe avere testo extra)
    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      console.error('LLM response not JSON:', text);
      return null;
    }

    const parsed = JSON.parse(jsonMatch[0]) as ClassifiedIntent;

    // Valida la risposta
    if (!parsed.intent || typeof parsed.confidence !== 'number') {
      console.error('Invalid LLM response structure:', parsed);
      return null;
    }

    return parsed;

  } catch (error) {
    console.error('LLM classification error:', error);
    return null;
  }
}

/**
 * Converte ClassifiedIntent nel formato ParsedIntent usato dal bot
 */
export function convertToParseIntent(classified: ClassifiedIntent): {
  intent: string;
  filters: Record<string, any>;
  confidence: number;
} {
  // Mappa intent LLM → intent bot
  const intentMap: Record<string, string> = {
    'talent_search': 'talent_search', // Nuovo intent per talent-search.ts
    'list_opportunities': 'list_all',
    'stats': 'stats',
    'help': 'help',
    'greeting': 'help',
    'unknown': 'unknown',
  };

  const filters: Record<string, any> = {};

  if (classified.filters) {
    if (classified.filters.role) filters.role = classified.filters.role;
    if (classified.filters.position) filters.position = classified.filters.position;
    if (classified.filters.characteristic) filters.characteristic = classified.filters.characteristic;
    if (classified.filters.type) filters.type = classified.filters.type;
    if (classified.filters.age) {
      // Converti "under 25" → ageMax: 25
      const ageMatch = classified.filters.age.match(/under\s*(\d+)/i);
      if (ageMatch) {
        filters.ageMax = parseInt(ageMatch[1]);
      }
      const overMatch = classified.filters.age.match(/over\s*(\d+)/i);
      if (overMatch) {
        filters.ageMin = parseInt(overMatch[1]);
      }
    }
  }

  return {
    intent: intentMap[classified.intent] || 'unknown',
    filters,
    confidence: classified.confidence,
  };
}
