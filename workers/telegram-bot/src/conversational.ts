/**
 * Voice Message Handler
 *
 * Gestisce solo i messaggi vocali con Gemma 3 27B
 */

import { Env } from './types';
import { sendMessage } from './telegram';
import { handleSmartSearch } from './smart-search';

/**
 * Handler per messaggi vocali
 * Usa Gemma 3 27B per trascrivere e poi cerca nelle opportunità reali
 */
export async function handleVoiceMessage(
  chatId: number,
  audioBase64: string,
  mimeType: string,
  env: Env
): Promise<boolean> {
  if (!env.OPENROUTER_API_KEY) {
    return false;
  }

  console.log(`Processing voice message for chat ${chatId}, mime: ${mimeType}`);

  try {
    // Chiama OpenRouter per trascrivere l'audio
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
            content: `Sei un assistente che trascrive messaggi vocali.
Trascrivi ESATTAMENTE quello che dice l'utente in italiano.
Rispondi SOLO con la trascrizione, senza aggiungere commenti.
Se non capisci l'audio, rispondi "NON_CAPITO".`
          },
          {
            role: 'user',
            content: [
              {
                type: 'audio',
                audio: {
                  data: audioBase64,
                  format: mimeType.includes('ogg') ? 'ogg' :
                          mimeType.includes('mp3') ? 'mp3' :
                          mimeType.includes('wav') ? 'wav' : 'ogg'
                }
              },
              {
                type: 'text',
                text: 'Trascrivi questo messaggio vocale.'
              }
            ]
          }
        ],
        max_tokens: 256,
        temperature: 0.1,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      console.error('OpenRouter audio error:', error);
      await sendMessage(env, chatId, `🎤 Non sono riuscito a capire il messaggio vocale. Prova a scrivermi!`);
      return true;
    }

    const data = await response.json() as any;
    const transcription = data.choices?.[0]?.message?.content?.trim();

    if (!transcription || transcription === 'NON_CAPITO') {
      await sendMessage(env, chatId, `🎤 Non sono riuscito a capire il messaggio vocale. Prova a scrivermi!`);
      return true;
    }

    console.log(`Voice transcription: "${transcription}"`);

    // Mostra la trascrizione e cerca
    await sendMessage(env, chatId, `🎤 Ho capito: "<i>${transcription}</i>"\n\nCerco...`);

    // Usa smart-search per cercare nelle opportunità reali
    await handleSmartSearch(chatId, transcription, env);

    return true;

  } catch (error) {
    console.error('Voice processing error:', error);
    return false;
  }
}
