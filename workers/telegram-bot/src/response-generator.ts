import { Ai } from '@cloudflare/ai';
import { Opportunity } from './types';
import { MatchResult, DNAStats } from './dna';

/**
 * SCOUT PERSONA SYSTEM PROMPT
 * Defines the tone, style, and constraints for the AI response.
 */
const SCOUT_SYSTEM_PROMPT = `Sei OB1, uno scout professionista ed esperto per la Serie C e D italiana.
Il tuo compito è rispondere alle domande di Direttori Sportivi e Allenatori sui giocatori disponibili.

LINEE GUIDA PERSONA:
- Tono: Professionale, sintetico, tecnico, diretto. Mai servile o robotico.
- Stile: "Insider" del calcio. Usa termini come "profilo interessante", "gamba", "struttura", "minutaggio", "under".
- Lingua: Italiano perfetto calcistico.
- Obiettivo: Dare subito valore. Evita preamboli inutili come "Ecco la lista che hai chiesto".
- Data-driven: Cita 1-2 numeri chiave (età, presenze, score) per giustificare i consigli.

COSA NON FARE:
- Non dire "Sono un'intelligenza artificiale".
- Non dire "Spero che questa lista ti sia utile".
- Non inventare dati. Usa solo quelli forniti nel contesto.

FORMATO RISPOSTA:
- Breve introduzione (max 2 frasi) che riassume cosa hai trovato.
- Se ci sono giocatori interessanti, citane 1 o 2 specifici con una brevissima motivazione tecnica.
- Chiudi rimandando alla lista sottostante.
`;

/**
 * Generates a natural language response using Cloudflare AI (Llama 3.1)
 * Wraps the data results with a professional scout commentary.
 */
export async function generateScoutResponse(
  ai: Ai,
  userQuery: string,
  opportunities: Opportunity[],
  context: string = 'market' // 'market' | 'dna' | 'talent'
): Promise<string | null> {
  try {
    // 1. Prepare data summary for the LLM (minimize tokens)
    const topOpps = opportunities.slice(0, 3).map(o => ({
      name: o.player_name,
      role: o.role,
      age: o.age,
      club: o.current_club,
      type: o.opportunity_type,
      score: o.ob1_score
    }));

    const dataContext = JSON.stringify(topOpps);
    const count = opportunities.length;

    // 2. Build the specific user prompt
    let userPrompt = '';
    
    if (context === 'market') {
      userPrompt = `Domanda utente: "${userQuery}"
Dati trovati: ${count} opportunità. Top 3: ${dataContext}

Scrivi una risposta breve (max 30 parole) per introdurre questi risultati al DS.
Se la lista è vuota, dillo chiaramente ma professionalmente.
Se ci sono profili validi (score > 75), evidenzia il migliore.`;
    } else if (context === 'talent') {
      userPrompt = `Domanda utente (ricerca talento): "${userQuery}"
Talenti trovati: ${count}. Top 3: ${dataContext}

Il DS cerca caratteristiche specifiche. Scrivi una risposta tecnica (max 40 parole).
Conferma se i giocatori trovati rispecchiano le caratteristiche richieste (es. "che spinge", "strutturato").`;
    }

    // 3. Call Cloudflare AI
    const response = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        { role: 'system', content: SCOUT_SYSTEM_PROMPT },
        { role: 'user', content: userPrompt }
      ],
      max_tokens: 150, // Keep it short
      temperature: 0.3, // Low creativity, high precision
    });

    const text = (response as any).response;
    return text ? text.trim() : null;

  } catch (error) {
    console.error('AI Generation Error:', error);
    return null; // Fallback to standard static messages on error
  }
}

/**
 * Generates a response for DNA Matches (specifically for clubs)
 */
export async function generateDNAResponse(
  ai: Ai,
  clubName: string,
  matches: MatchResult[]
): Promise<string | null> {
  try {
    const topMatches = matches.slice(0, 3).map(m => ({
      name: m.player.name,
      role: m.player.primary_position,
      age: 2026 - m.player.birth_year,
      club: m.player.current_team,
      match_score: m.score,
      why: Object.entries(m.breakdown).filter(([k,v]) => (v as number) > 80).map(([k]) => k).join(', ')
    }));

    const userPrompt = `Analisi DNA per il club: ${clubName}
Matches trovati: ${matches.length}. Top 3: ${JSON.stringify(topMatches)}

Scrivi un commento tecnico (max 30-40 parole) per il DS del ${clubName}.
Evidenzia perché questi giovani sono adatti al loro modulo/stile (basandoti sul match_score e breakdown).`;

    const response = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        { role: 'system', content: SCOUT_SYSTEM_PROMPT },
        { role: 'user', content: userPrompt }
      ],
      max_tokens: 150,
      temperature: 0.3,
    });

    return (response as any).response?.trim() || null;

  } catch (error) {
    console.error('AI DNA Generation Error:', error);
    return null;
  }
}
