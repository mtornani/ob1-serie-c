#!/usr/bin/env python3
"""
OB1 Serie C - Transfermarkt Enricher
Arricchisce i profili giocatori con dati strutturati da Transfermarkt (via Tavily/Gemini)
"""

import os
import json
import time
from typing import Dict, Any, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

class TransfermarktEnricher:
    """
    Cerca e scarica dati strutturati da Transfermarkt usando Tavily per l'accesso
    e Gemini per il parsing.
    """
    
    def __init__(self):
        self.tavily_key = os.getenv('TAVILY_API_KEY')
        self.gemini_key = os.getenv('GEMINI_API_KEY')
        
        if not self.tavily_key:
            raise ValueError("TAVILY_API_KEY mancante")
        if not self.gemini_key:
            raise ValueError("GEMINI_API_KEY mancante")
            
        self.session = requests.Session()

    def search_player_profile(self, player_name: str) -> Optional[Dict[str, Any]]:
        """Cerca il profilo Transfermarkt di un giocatore"""
        
        query = f"site:transfermarkt.it {player_name} profilo giocatore"
        
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 1,
            "include_domains": ["transfermarkt.it"],
            "include_raw_content": True
        }
        
        try:
            print(f"  🔍 Cercando {player_name} su Transfermarkt...")
            response = self.session.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('results', [])
            if not results:
                print(f"  ❌ Nessun profilo trovato per {player_name}")
                return None
                
            return results[0]
            
        except Exception as e:
            print(f"  ⚠️ Errore ricerca Tavily: {e}")
            return None

    def extract_data_with_gemini(self, content: str, url: str) -> Dict[str, Any]:
        """Usa Gemini per estrarre dati strutturati dal testo grezzo della pagina"""
        
        # Truncate content to avoid token limits (TM pages can be long)
        max_chars = 12000 
        if len(content) > max_chars:
            content = content[:max_chars] + "..."

        prompt = f'''Sei un data analyst sportivo. Estrai i dati esatti da questo contenuto di pagina Transfermarkt.
URL: {url}

DATI RICHIESTI (rispondi in JSON):
{{
  "full_name": "Nome completo",
  "birth_date": "YYYY-MM-DD" o null,
  "birth_place": "Città, Nazione" o null,
  "nationality": "Nazionalità principale (es. Argentina)",
  "second_nationality": "Seconda nazionalità (es. Italia) o null",
  "height_cm": numero intero o null,
  "foot": "destro" | "sinistro" | "ambidestro" | null,
  "current_club": "Nome Club" o "Svincolato",
  "contract_expires": "YYYY-MM-DD" o null,
  "market_value_eur": numero intero (es. 150000) o null,
  "market_value_text": "stringa formattata" (es. "€150k") o null,
  "main_position": "Ruolo principale",
  "agent": "Nome Agenzia" o null,
  "player_image_url": "URL immagine profilo giocatore da Transfermarkt (cerca tag img con classe 'data-src' o 'bilderrahmen-fixed')" o null,
  "appearances": numero intero presenze stagione corrente 2025/26 (tutte le competizioni) o null,
  "goals": numero intero gol segnati stagione corrente 2025/26 o null,
  "assists": numero intero assist stagione corrente 2025/26 o null,
  "minutes_played": numero intero minuti giocati stagione corrente 2025/26 o null
}}

Se un dato non è presente, metti null.
Per il valore di mercato, cerca "Valore attuale:" o simili.
Per la cittadinanza, cerca "Nazionalità:" o "Citizenship:". Spesso sono presenti due bandiere se ha il doppio passaporto.
Per le statistiche stagionali, cerca tabelle con "Presenze", "Gol", "Assist", "Minuti" relative alla stagione 25/26 o alla stagione piu' recente disponibile.

CONTENUTO PAGINA:
{content}

JSON:'''

        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_key}"
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0, # Deterministic
                "maxOutputTokens": 1500,
                "responseMimeType": "application/json"
            }
        }
        
        try:
            response = self.session.post(gemini_url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            text = data['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text)
            
        except Exception as e:
            print(f"  ⚠️ Errore parsing Gemini: {e}")
            return {}

    def enrich_player(self, player_name: str) -> Dict[str, Any]:
        """Metodo principale: Cerca -> Scarica -> Estrae -> Ritorna"""
        
        result = self.search_player_profile(player_name)
        if not result:
            return {}
            
        raw_content = result.get('raw_content', '')
        url = result.get('url', '')
        
        if not raw_content:
            print("  ⚠️ Contenuto vuoto da Tavily")
            return {}
            
        print(f"  📝 Analizzando dati da: {url}")
        tm_data = self.extract_data_with_gemini(raw_content, url)
        tm_data['tm_url'] = url
        
        return tm_data

# Test rapido se eseguito direttamente
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        name = sys.argv[1]
    else:
        name = "Giuseppe Rossi"
        
    enricher = TransfermarktEnricher()
    print(f"Enriching: {name}")
    data = enricher.enrich_player(name)
    print(json.dumps(data, indent=2))
