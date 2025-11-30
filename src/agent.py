#!/usr/bin/env python3
"""
OB1 Serie C - Agent
Interfaccia conversazionale per query su File Search Store
"""

import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class OB1Agent:
    """Agent conversazionale per scouting Serie C"""
    
    STORE_NAME = "ob1-serie-c-knowledge"
    MODEL = "gemini-2.5-flash"
    
    SYSTEM_PROMPT = """Sei OB1, un assistente di scouting specializzato in Serie C e Serie D italiana.

Il tuo ruolo è aiutare direttori sportivi e scout a:
- Trovare giocatori svincolati o in uscita
- Identificare opportunità di mercato
- Analizzare profili giocatori
- Suggerire target basati su criteri specifici

REGOLE:
1. Rispondi SEMPRE basandoti sui dati nel tuo database
2. Se non hai informazioni su un giocatore, dillo chiaramente
3. Cita sempre le fonti quando disponibili
4. Sii conciso e professionale
5. Quando suggerisci giocatori, spiega perché potrebbero essere interessanti

FORMATO RISPOSTA:
- Per liste di giocatori: nome, ruolo, età, situazione contrattuale
- Per analisi singole: profilo completo con pro/contro
- Per ricerche: risultati ordinati per rilevanza

Oggi è il {date}. Stagione 2024/25."""

    def __init__(self):
        if not GEMINI_AVAILABLE:
            raise ImportError("google-genai richiesto")
        
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY mancante")
        
        self.client = genai.Client(api_key=api_key)
        self.store_name = self._find_store()
        self.conversation_history: List[Dict[str, str]] = []
    
    def _find_store(self) -> Optional[str]:
        """Trova il File Search Store"""
        
        try:
            stores = list(self.client.file_search_stores.list())
            for store in stores:
                if self.STORE_NAME in store.display_name:
                    print(f"✅ Store connesso: {store.name}")
                    return store.name
        except Exception as e:
            print(f"⚠️ Errore connessione store: {e}")
        
        print("⚠️ Store non trovato. Esegui prima ingest.py")
        return None
    
    def query(self, user_message: str) -> str:
        """Esegue query sul knowledge base"""
        
        if not self.store_name:
            return "❌ Database non disponibile. Esegui prima la pipeline di ingest."
        
        # Build system prompt with current date
        system = self.SYSTEM_PROMPT.format(date=datetime.now().strftime("%d/%m/%Y"))
        
        # Build messages
        messages = [{"role": "user", "content": user_message}]
        
        # Add conversation context (last 4 exchanges)
        if self.conversation_history:
            context_messages = self.conversation_history[-8:]  # 4 exchanges = 8 messages
            messages = context_messages + messages
        
        try:
            response = self.client.models.generate_content(
                model=self.MODEL,
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    tools=[
                        types.Tool(
                            file_search=types.FileSearch(
                                file_search_store_names=[self.store_name]
                            )
                        )
                    ],
                    temperature=0.3,  # Low for factual responses
                    max_output_tokens=2048
                )
            )
            
            answer = response.text
            
            # Update conversation history
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": answer})
            
            return answer
            
        except Exception as e:
            return f"❌ Errore query: {e}"
    
    def clear_history(self):
        """Reset conversazione"""
        self.conversation_history = []
        print("🔄 Conversazione resettata")
    
    # =========================================================================
    # QUERY TEMPLATES (shortcuts per query comuni)
    # =========================================================================
    
    def find_svincolati(self, role: Optional[str] = None, max_age: Optional[int] = None) -> str:
        """Cerca giocatori svincolati"""
        
        query = "Quali giocatori svincolati sono disponibili"
        
        if role:
            query += f" nel ruolo di {role}"
        if max_age:
            query += f" con età massima {max_age} anni"
        
        query += "? Elencali con dettagli."
        return self.query(query)
    
    def analyze_player(self, player_name: str) -> str:
        """Analisi dettagliata giocatore"""
        
        return self.query(
            f"Dammi tutte le informazioni disponibili su {player_name}: "
            f"ruolo, età, situazione contrattuale, statistiche, storico e valutazione."
        )
    
    def find_by_criteria(
        self,
        role: Optional[str] = None,
        max_age: Optional[int] = None,
        contract_status: Optional[str] = None,
        min_appearances: Optional[int] = None
    ) -> str:
        """Ricerca avanzata con criteri multipli"""
        
        criteria = []
        
        if role:
            criteria.append(f"ruolo: {role}")
        if max_age:
            criteria.append(f"età massima: {max_age}")
        if contract_status:
            criteria.append(f"situazione contrattuale: {contract_status}")
        if min_appearances:
            criteria.append(f"almeno {min_appearances} presenze stagionali")
        
        if not criteria:
            return self.query("Mostrami le migliori opportunità di mercato attuali.")
        
        query = f"Cerca giocatori con questi criteri: {', '.join(criteria)}. Ordina per rilevanza."
        return self.query(query)
    
    def market_summary(self) -> str:
        """Riepilogo mercato attuale"""
        
        return self.query(
            "Fammi un riepilogo delle opportunità di mercato più interessanti: "
            "svincolati top, rescissioni recenti, prestiti disponibili. "
            "Organizza per categoria e priorità."
        )


# =============================================================================
# INTERACTIVE CLI
# =============================================================================

def interactive_mode():
    """Modalità interattiva da terminale"""
    
    print("=" * 60)
    print("🎯 OB1 SERIE C AGENT")
    print("=" * 60)
    print("\nComandi speciali:")
    print("  /svincolati [ruolo]  - Lista svincolati")
    print("  /player <nome>       - Analisi giocatore")
    print("  /summary             - Riepilogo mercato")
    print("  /clear               - Reset conversazione")
    print("  /exit                - Esci")
    print("\nOppure scrivi qualsiasi domanda in linguaggio naturale.\n")
    
    agent = OB1Agent()
    
    while True:
        try:
            user_input = input("Tu: ").strip()
            
            if not user_input:
                continue
            
            # Special commands
            if user_input.startswith('/'):
                parts = user_input.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else None
                
                if cmd == '/exit':
                    print("👋 Arrivederci!")
                    break
                elif cmd == '/clear':
                    agent.clear_history()
                    continue
                elif cmd == '/summary':
                    response = agent.market_summary()
                elif cmd == '/svincolati':
                    response = agent.find_svincolati(role=arg)
                elif cmd == '/player' and arg:
                    response = agent.analyze_player(arg)
                else:
                    print("❓ Comando non riconosciuto")
                    continue
            else:
                response = agent.query(user_input)
            
            print(f"\n🤖 OB1: {response}\n")
            
        except KeyboardInterrupt:
            print("\n👋 Arrivederci!")
            break
        except Exception as e:
            print(f"❌ Errore: {e}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    interactive_mode()
