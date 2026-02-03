/**
 * OpenRouter API Client
 *
 * Usa modelli gratuiti per NLP conversazionale:
 * - deepseek/deepseek-chat-v3-0324:free (principale)
 * - meta-llama/llama-3.3-70b-instruct:free (fallback)
 */

export interface OpenRouterMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface OpenRouterResponse {
  choices: Array<{
    message: {
      content: string;
    };
  }>;
}

export interface ConversationalResponse {
  type: 'answer' | 'clarify' | 'action';
  message: string;
  action?: {
    intent: string;
    filters: Record<string, any>;
  };
  suggestions?: string[];
  confidence: number;
}

// Free models on OpenRouter (Feb 2026)
// Priority order: best for Italian conversational bot
const FREE_MODELS = [
  'google/gemma-3-27b-it:free',                 // Google 27B, multimodale (audio+vision), 131K context
  'google/gemma-3-12b-it:free',                 // Google 12B, multimodale fallback
  'meta-llama/llama-3.3-70b-instruct:free',     // Meta 70B, solido text-only fallback
];

/**
 * Chiama OpenRouter API con un modello gratuito
 */
export async function callOpenRouter(
  apiKey: string,
  messages: OpenRouterMessage[],
  options: {
    model?: string;
    maxTokens?: number;
    temperature?: number;
  } = {}
): Promise<string | null> {
  const model = options.model || FREE_MODELS[0];

  try {
    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://ob1-scout.pages.dev',
        'X-Title': 'OB1 Scout Bot',
      },
      body: JSON.stringify({
        model,
        messages,
        max_tokens: options.maxTokens || 512,
        temperature: options.temperature ?? 0.3,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      console.error(`OpenRouter error (${response.status}):`, error);

      // Se il modello principale fallisce, prova il fallback
      if (model === FREE_MODELS[0] && FREE_MODELS.length > 1) {
        console.log('Trying fallback model...');
        return callOpenRouter(apiKey, messages, { ...options, model: FREE_MODELS[1] });
      }

      return null;
    }

    const data: OpenRouterResponse = await response.json();
    return data.choices?.[0]?.message?.content || null;

  } catch (error) {
    console.error('OpenRouter fetch error:', error);
    return null;
  }
}

/**
 * System prompt per il bot conversazionale OB1 Scout
 */
export const OB1_SYSTEM_PROMPT = `Sei OB1 Scout, un assistente esperto di calciomercato italiano specializzato in Serie C e Lega Pro.

PERSONALITA:
- Sei amichevole e competente, come un vecchio osservatore di calcio
- Rispondi sempre in italiano
- Sei conciso ma utile
- Quando non capisci, fai domande per stringere il cerchio (come Akinator)

CAPACITA:
- Cercare giocatori per ruolo, eta, tipo (svincolato, prestito, etc.)
- Mostrare opportunita HOT (score 80+) o WARM (60-79)
- Trovare DNA match tra talenti squadre B e club Serie C
- Creare alert personalizzati

FORMATO RISPOSTA (JSON):
{
  "type": "answer|clarify|action",
  "message": "testo da mostrare all'utente",
  "action": {
    "intent": "list_hot|list_warm|list_all|search|dna_club|dna_top|stats|help|scout_wizard|unknown",
    "filters": {
      "role": "DC|TD|TS|CC|ED|ES|TQ|AT|PO",
      "type": "svincolato|prestito|rescissione|scadenza",
      "ageMax": 25,
      "ageMin": 20,
      "query": "testo ricerca",
      "club": "nome club per DNA"
    }
  },
  "suggestions": ["suggerimento 1", "suggerimento 2"],
  "confidence": 0.0-1.0
}

REGOLE:
1. Se l'utente saluta, rispondi cordialmente e chiedi come puoi aiutarlo
2. Se la richiesta e chiara, usa type="action" con l'intent corretto
3. Se la richiesta e vaga, usa type="clarify" e fai UNA domanda specifica per stringere il cerchio
4. Se non puoi aiutare, suggerisci cosa sai fare
5. NON inventare dati sui giocatori - usa sempre le azioni per recuperarli

ESEMPI DI CLARIFY (stringere il cerchio):
- "Un giocatore?" -> "Che ruolo ti interessa? Difensore, centrocampista, attaccante?"
- "Serve qualcuno" -> "Cosa cerchi esattamente? Un giocatore svincolato? In prestito?"
- "Per la mia squadra" -> "Per quale squadra? Posso fare un DNA match se me lo dici!"

RUOLI POSIZIONI:
- PO = Portiere
- DC = Difensore centrale
- TD = Terzino destro
- TS = Terzino sinistro
- CC = Centrocampista centrale
- ED = Esterno destro
- ES = Esterno sinistro
- TQ = Trequartista
- AT = Attaccante

IMPORTANTE: Rispondi SOLO con JSON valido, niente altro testo prima o dopo.`;

/**
 * Elabora un messaggio con il bot conversazionale
 */
export async function processConversational(
  apiKey: string,
  userMessage: string,
  conversationHistory: OpenRouterMessage[] = []
): Promise<ConversationalResponse | null> {
  const messages: OpenRouterMessage[] = [
    { role: 'system', content: OB1_SYSTEM_PROMPT },
    ...conversationHistory.slice(-6), // Mantieni solo ultimi 6 messaggi per contesto
    { role: 'user', content: userMessage },
  ];

  const response = await callOpenRouter(apiKey, messages, {
    maxTokens: 512,
    temperature: 0.3,
  });

  if (!response) {
    return null;
  }

  try {
    // Estrai JSON dalla risposta
    const jsonMatch = response.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      console.error('No JSON in response:', response);
      return null;
    }

    const parsed = JSON.parse(jsonMatch[0]) as ConversationalResponse;

    // Valida risposta
    if (!parsed.type || !parsed.message) {
      console.error('Invalid response structure:', parsed);
      return null;
    }

    return parsed;

  } catch (error) {
    console.error('JSON parse error:', error, 'Response:', response);
    return null;
  }
}
