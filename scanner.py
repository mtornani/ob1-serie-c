#!/usr/bin/env python3
"""
OB1 Serie C Scanner - Mobile First Edition v1.1
Trova opportunità di mercato per Serie C italiana
"""

import json
import requests
import re
from datetime import datetime, timedelta
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# Config
SERPER_API_KEY = os.getenv('SERPER_API_KEY')
OUTPUT_FILE = Path("data.json")

# Serie C Clubs per validazione
SERIE_C_CLUBS = [
    # Girone A
    'Albinoleffe', 'Alcione', 'Arzignano', 'FeralpiSalò', 'Giana Erminio',
    'Lecco', 'Legnago', 'Lumezzane', 'Novara', 'Padova', 'Pergolettese',
    'Pro Patria', 'Pro Vercelli', 'Renate', 'Trento', 'Triestina',
    'Union Clodiense', 'Vicenza', 'Virtus Verona',
    
    # Girone B  
    'Arezzo', 'Ascoli', 'Campobasso', 'Carpi', 'Cesena', 'Entella',
    'Gubbio', 'Legnago', 'Lucchese', 'Milan Futuro', 'Perugia', 'Pescara',
    'Pianese', 'Pineto', 'Pontedera', 'Rimini', 'SPAL', 'Sestri Levante',
    'Ternana', 'Torres', 'Vis Pesaro',
    
    # Girone C
    'Audace Cerignola', 'Avellino', 'AZ Picerno', 'Benevento', 'Casertana',
    'Catania', 'Cavese', 'Crotone', 'Foggia', 'Giugliano', 'Juventus Next Gen',
    'Latina', 'Messina', 'Monopoli', 'Potenza', 'Sorrento', 'Taranto',
    'Team Altamura', 'Trapani', 'Turris'
]

def extract_player_name(text):
    """Estrai nome giocatore dal testo"""
    patterns = [
        r'Il (?:calciatore|centrocampista|difensore|attaccante|portiere)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
        r'([A-Z][a-z]+\s+[A-Z][a-z]+)(?:,?\s+(?:classe|nato))',
        r'per\s+([A-Z][a-z]+\s+[A-Z][a-z]+)[,\.]',
        r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:è\s+)?(?:svincolato|parametro zero)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1)
            if name not in SERIE_C_CLUBS and 'Serie' not in name:
                return name
    
    return None

def is_valid_opportunity(item):
    """Filtra falsi positivi"""
    text_lower = (item.get('title', '') + ' ' + item.get('snippet', '')).lower()
    
    skip_words = [
        'allenatore', 'mister', 'tecnico', 'direttore sportivo', 
        'ds ', 'team manager', 'preparatore', 'massaggiatore',
        'presidente', 'patron', 'dirigente'
    ]
    
    if any(word in text_lower for word in skip_words):
        player_words = ['giocatore', 'calciatore', 'centrocampista', 'difensore', 'attaccante', 'portiere']
        if not any(word in text_lower for word in player_words):
            return False
    
    if 'wikipedia' in item.get('link', '').lower():
        return False
    
    date_str = item.get('date', '').lower()
    if 'settimane fa' in date_str or 'mesi fa' in date_str:
        return False
        
    return True

def search_serie_c_news():
    """Cerca notizie Serie C dell'ultima settimana"""
    
    queries = [
        '"Serie C" "parametro zero" OR "svincolato" 2025',
        '"Serie C" "rescinde" OR "risoluzione" contratto',
        '"Lega Pro" "ufficiale" acquisto OR cessione',
        '"Serie C" giocatore "svincolato" OR "parametro zero"',
        '"Serie C" centrocampista OR difensore OR attaccante "disponibile"',
        '"prestito" "Serie C" gennaio 2025',
        '"Primavera" "cerca spazio" Serie C',
        'Juventus OR Milan OR Inter "prestito Serie C"',
        '"Serie C" "infortunio" "stagione finita" OR "lungo stop"',
        '"Serie C" "rottura crociato" OR "lesione muscolare"',
        '"Serie D" "interesse Serie C" capocannoniere',
        '"Serie D" bomber OR talento "osservato" Serie C',
        '"Serie C" "migliore in campo" ultima giornata',
        '"Serie C" "doppietta" OR "tripletta" OR "hat-trick"'
    ]
    
    all_results = []
    
    for query in queries:
        print(f"🔍 Searching: {query[:50]}...")
        
        url = "https://google.serper.dev/search"
        headers = {
            'X-API-KEY': SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
        
        payload = {
            'q': query,
            'num': 10,
            'gl': 'it',
            'hl': 'it',
            'tbs': 'qdr:w'
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                
                for item in data.get('organic', []):
                    if not is_valid_opportunity(item):
                        continue
                    
                    snippet = item.get('snippet', '').lower()
                    title = item.get('title', '').lower()
                    full_text = title + ' ' + snippet
                    
                    mentions_club = any(club.lower() in full_text 
                                       for club in SERIE_C_CLUBS)
                    mentions_league = any(kw in full_text 
                                         for kw in ['serie c', 'lega pro', 'terza serie'])
                    
                    if mentions_club or mentions_league:
                        player_name = extract_player_name(item.get('snippet', ''))
                        
                        result = {
                            'title': item.get('title', ''),
                            'snippet': item.get('snippet', ''),
                            'link': item.get('link', ''),
                            'date': item.get('date', 'Oggi'),
                            'source': extract_source(item.get('link', '')),
                            'type': categorize_news(query, item),
                            'priority': calculate_priority(item, query),
                            'found_at': datetime.now().isoformat()
                        }
                        
                        if player_name:
                            result['player_name'] = player_name
                            if 'svincolat' in result['title'].lower() and player_name not in result['title']:
                                result['title'] = f"{player_name} - {result['title']}"
                        
                        all_results.append(result)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            continue
    
    return all_results

def extract_source(url):
    """Estrai nome fonte dal URL"""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    
    sources = {
        'tuttoc.com': 'TuttoC',
        'seriecnews.com': 'SerieC News',
        'calciomercato.com': 'Calciomercato',
        'transfermarkt': 'Transfermarkt',
        'gazzetta.it': 'Gazzetta',
        'corrieredellosport.it': 'CdS',
        'tuttosport.com': 'Tuttosport',
        'lega-pro.com': 'Lega Pro',
        'tuttomercatoweb.com': 'TMW',
        'football-italia.net': 'Football Italia',
        'notiziariocalcio.com': 'Notiziario',
        'sportcampania.it': 'Sport Campania',
        'tuttocampo.it': 'TuttoCampo'
    }
    
    for key, name in sources.items():
        if key in domain.lower():
            return name
    
    clean_domain = domain.replace('www.', '').split('.')[0]
    return clean_domain.title()

def categorize_news(query, item):
    """Categorizza tipo di opportunità"""
    text = (item.get('title', '') + ' ' + item.get('snippet', '')).lower()
    
    is_player = any(kw in text for kw in ['giocatore', 'calciatore', 'centrocampista', 
                                           'difensore', 'attaccante', 'portiere', 
                                           'esterno', 'mediano', 'trequartista'])
    
    if any(kw in text for kw in ['parametro zero', 'svincolato', 'svincolati']) and is_player:
        return '🆓 Parametro Zero'
    elif any(kw in text for kw in ['rescinde', 'rescissione', 'risoluzione', 'risolto']):
        return '✂️ Risoluzione'
    elif any(kw in text for kw in ['prestito', 'loan']):
        return '🔄 Prestito'
    elif any(kw in text for kw in ['infortunio', 'stop', 'rottura', 'lesione', 'operazione']):
        return '🏥 Infortunio'
    elif any(kw in text for kw in ['serie d', 'eccellenza', 'promozione']):
        return '📈 Serie D'
    elif any(kw in text for kw in ['doppietta', 'tripletta', 'hat-trick', 'migliore in campo']):
        return '⭐ Performance'
    elif any(kw in text for kw in ['ufficiale', 'acquisto', 'firma', 'tesserato']):
        return '✅ Ufficiale'
    else:
        return '📰 News'

def calculate_priority(item, query):
    """Calcola priorità opportunità (1-5)"""
    text = (item.get('title', '') + ' ' + item.get('snippet', '')).lower()
    score = 3
    
    is_player = any(kw in text for kw in ['giocatore', 'calciatore', 'centrocampista', 
                                           'difensore', 'attaccante', 'portiere'])
    
    if ('parametro zero' in text or 'svincolato' in text) and is_player:
        score = 5
    elif 'rescinde' in text or 'risoluzione' in text:
        score = 4
    elif 'prestito gratuito' in text:
        score = 4
    elif 'infortunio' in text and ('lungo' in text or 'mesi' in text or 'stagione' in text):
        score = 4
    elif any(kw in text for kw in ['doppietta', 'tripletta', 'hat-trick']):
        score = 4
    
    if any(kw in text for kw in ['urgente', 'immediato', 'subito']):
        score = min(5, score + 1)
    
    if 'rumors' in text or 'indiscrezione' in text or 'potrebbe' in text:
        score -= 1
    
    return min(5, max(1, score))

def save_results(results):
    """Salva risultati in JSON per frontend"""
    
    seen = set()
    unique = []
    for r in results:
        if r['link'] not in seen:
            seen.add(r['link'])
            unique.append(r)
    
    unique.sort(key=lambda x: (x['priority'], x['found_at']), reverse=True)
    unique = unique[:25]
    
    output = {
        'last_update': datetime.now().isoformat(),
        'total_found': len(unique),
        'opportunities': unique,
        'stats': {
            'parametro_zero': len([r for r in unique if 'Parametro Zero' in r['type']]),
            'prestiti': len([r for r in unique if 'Prestito' in r['type']]),
            'infortuni': len([r for r in unique if 'Infortunio' in r['type']]),
            'serie_d': len([r for r in unique if 'Serie D' in r['type']]),
            'risoluzioni': len([r for r in unique if 'Risoluzione' in r['type']])
        }
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Salvate {len(unique)} opportunità in {OUTPUT_FILE}")
    print(f"   - Parametri zero: {output['stats']['parametro_zero']}")
    print(f"   - Risoluzioni: {output['stats']['risoluzioni']}")
    print(f"   - Prestiti: {output['stats']['prestiti']}")
    print(f"   - Infortuni: {output['stats']['infortuni']}")
    print(f"   - Serie D: {output['stats']['serie_d']}")

def main():
    print("=" * 60)
    print("🎯 OB1 SERIE C SCANNER v1.1")
    print("=" * 60)
    
    if not SERPER_API_KEY:
        print("❌ SERPER_API_KEY mancante nel file .env")
        print("   1. Copia .env.example in .env")
        print("   2. Aggiungi la tua API key da serper.dev")
        return
    
    results = search_serie_c_news()
    
    if results:
        save_results(results)
        print(f"\n👁️ Visita index.html dal telefono per vedere i risultati")
    else:
        print("❌ Nessuna opportunità trovata")
        save_results([])

if __name__ == "__main__":
    main()
