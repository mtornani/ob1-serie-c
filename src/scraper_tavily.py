#!/usr/bin/env python3
"""
OB1 Serie C - Tavily-Powered Scraper
Advanced scraping with full content extraction and Gemini parsing
"""

import os
import json
import re
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

import requests
from dotenv import load_dotenv
from date_filter import is_article_fresh

load_dotenv()


class TavilyScraperOB1:
    """Scraper avanzato con Tavily + Gemini per opportunita Serie C"""

    # News sources whitelist
    TRUSTED_DOMAINS = [
        "tuttoc.com",
        "tuttolegapro.com",
        "calciomercato.com",
        "tuttomercatoweb.com",
        "transfermarkt.it",
        "gazzetta.it",
        "corrieredellosport.it",
        "tuttosport.com",
        "football-italia.net",
        "pianetaserieb.it",
    ]

    # Search queries optimized for Serie C market
    QUERIES = [
        # Svincolati (highest priority)
        "Serie C svincolato giocatore 2026",
        "Lega Pro parametro zero disponibile",
        "calciatore svincolato Serie C gennaio",

        # Rescissioni
        "Serie C rescissione contratto",
        "Lega Pro risoluzione consensuale giocatore",

        # Prestiti
        "Serie C prestito gennaio 2026",
        "esubero disponibile prestito Lega Pro",

        # Mercato generale
        "calciomercato Serie C ultime notizie oggi",
        "TuttoC mercato trasferimenti",

        # Talenti
        "Serie D talento interesse Serie C",
    ]

    ROLE_MAPPING = {
        'portiere': 'PO',
        'difensore centrale': 'DC',
        'difensore': 'DC',
        'terzino destro': 'TD',
        'terzino sinistro': 'TS',
        'terzino': 'TD',
        'centrocampista centrale': 'CC',
        'centrocampista': 'CC',
        'mediano': 'CC',
        'regista': 'CC',
        'mezzala': 'CC',
        'esterno destro': 'ED',
        'esterno sinistro': 'ES',
        'esterno': 'ES',
        'ala': 'ES',
        'trequartista': 'TQ',
        'attaccante': 'AT',
        'punta': 'AT',
        'centravanti': 'AT',
        'prima punta': 'AT',
        'seconda punta': 'AT',
    }

    def __init__(self):
        self.tavily_key = os.getenv('TAVILY_API_KEY')
        self.gemini_key = os.getenv('GEMINI_API_KEY')

        if not self.tavily_key:
            raise ValueError("TAVILY_API_KEY mancante")
        if not self.gemini_key:
            raise ValueError("GEMINI_API_KEY mancante")

        self.session = requests.Session()

    def search_tavily(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Esegue ricerca con Tavily API"""

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": "advanced",
            "include_domains": self.TRUSTED_DOMAINS,
            "max_results": max_results,
            "include_raw_content": True,
        }

        try:
            response = self.session.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except Exception as e:
            print(f"  [!] Tavily error: {e}")
            return []

    def parse_with_gemini(self, content: str, source_url: str) -> List[Dict[str, Any]]:
        """Usa Gemini per estrarre informazioni strutturate"""

        # Truncate content if too long
        max_chars = 8000
        if len(content) > max_chars:
            content = content[:max_chars] + "..."

        prompt = f'''Sei un esperto di calciomercato italiano. Analizza questo articolo ed estrai informazioni sui giocatori di Serie C o Serie D menzionati che potrebbero essere opportunita di mercato.

CRITERI DI INCLUSIONE:
- Giocatori svincolati o in procinto di svincolarsi
- Giocatori con contratto rescisso
- Giocatori disponibili in prestito
- Giocatori in scadenza di contratto
- Talenti di Serie D che interessano a club di Serie C

CRITERI DI ESCLUSIONE:
- Allenatori, dirigenti, presidenti
- Giocatori gia trasferiti/firmati
- Semplici rumors senza sostanza
- Giocatori di Serie A/B che non interessano la Serie C

Per ogni giocatore rilevante, estrai:
{{
  "player_name": "Nome Cognome",
  "age": numero o null,
  "role": "ruolo in italiano",
  "opportunity_type": "svincolato" | "rescissione" | "prestito" | "scadenza" | "mercato",
  "current_club": "club attuale o ultimo",
  "previous_clubs": ["lista", "club", "precedenti"],
  "summary": "breve descrizione della situazione (max 100 parole)"
}}

Rispondi SOLO con un JSON array valido. Se non ci sono giocatori rilevanti, rispondi: []

ARTICOLO:
{content}

JSON:'''

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 2000,
            }
        }

        try:
            response = self.session.post(url, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()

            # Extract text from response
            text = data['candidates'][0]['content']['parts'][0]['text']

            # Clean and parse JSON
            text = text.strip()
            if text.startswith('```json'):
                text = text[7:]
            if text.startswith('```'):
                text = text[3:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()

            players = json.loads(text)
            return players if isinstance(players, list) else []

        except json.JSONDecodeError as e:
            print(f"  [!] JSON parse error: {e}")
            return []
        except Exception as e:
            print(f"  [!] Gemini error: {e}")
            return []

    def scrape_all(self) -> List[Dict[str, Any]]:
        """Esegue scraping completo"""

        all_opportunities = []
        seen_urls = set()
        seen_players = set()

        print("=" * 60)
        print("OB1 SERIE C - TAVILY SCRAPER")
        print("=" * 60)

        for i, query in enumerate(self.QUERIES):
            print(f"\n[{i+1}/{len(self.QUERIES)}] {query[:50]}...")

            results = self.search_tavily(query, max_results=5)
            print(f"  Found {len(results)} articles")

            for result in results:
                url = result.get('url', '')

                # Skip duplicates
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Filter stale articles (old news)
                is_fresh, stale_reason = is_article_fresh(url)
                if not is_fresh:
                    print(f"  [SKIP] Stale: {stale_reason}")
                    continue

                title = result.get('title', '')
                content = result.get('raw_content') or result.get('content', '')

                if not content or len(content) < 100:
                    continue

                print(f"  Parsing: {title[:50]}...")

                # Extract players with Gemini
                players = self.parse_with_gemini(content, url)

                for player in players:
                    player_name = player.get('player_name', '')

                    # Skip if already seen
                    if player_name.lower() in seen_players:
                        continue
                    seen_players.add(player_name.lower())

                    # Build opportunity object
                    opp = self._build_opportunity(player, url, title, result)
                    if opp:
                        all_opportunities.append(opp)
                        print(f"    + {player_name} ({opp.get('opportunity_type', 'N/A')})")

        print(f"\n{'=' * 60}")
        print(f"TOTALE: {len(all_opportunities)} opportunita trovate")
        print("=" * 60)

        return all_opportunities

    def _build_opportunity(self, player: Dict, url: str, title: str, result: Dict) -> Optional[Dict[str, Any]]:
        """Costruisce oggetto opportunita strutturato"""

        player_name = player.get('player_name', '').strip()
        if not player_name or len(player_name) < 3:
            return None

        # Generate ID
        opp_id = f"opp_{hashlib.md5(f'{player_name}_{url}'.encode()).hexdigest()[:8]}"

        # Map role (handle None explicitly)
        role_raw = (player.get('role') or '').lower()
        role_code = self.ROLE_MAPPING.get(role_raw, 'CC')
        role_name = role_raw.title() if role_raw else 'N/D'

        # Opportunity type (handle None explicitly)
        opp_type = (player.get('opportunity_type') or 'mercato').lower()
        if opp_type not in ['svincolato', 'rescissione', 'prestito', 'scadenza', 'mercato']:
            opp_type = 'mercato'

        # Extract source name
        source_name = self._extract_source(url)

        return {
            'id': opp_id,
            'player_name': player_name,
            'age': player.get('age'),
            'role': role_code,
            'role_name': role_name,
            'opportunity_type': opp_type,
            'current_club': player.get('current_club', ''),
            'previous_clubs': player.get('previous_clubs', []),
            'summary': player.get('summary', ''),
            'source_url': url,
            'source_name': source_name,
            'source_title': title,
            'discovered_at': datetime.now().isoformat(),
        }

    def _extract_source(self, url: str) -> str:
        """Estrae nome fonte da URL"""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().replace('www.', '')

        sources = {
            'tuttoc.com': 'TuttoC',
            'tuttolegapro.com': 'TuttoLegaPro',
            'calciomercato.com': 'Calciomercato',
            'transfermarkt.it': 'Transfermarkt',
            'gazzetta.it': 'Gazzetta',
            'corrieredellosport.it': 'Corriere dello Sport',
            'tuttosport.com': 'Tuttosport',
            'tuttomercatoweb.com': 'TMW',
            'football-italia.net': 'Football Italia',
        }

        for key, name in sources.items():
            if key in domain:
                return name

        return domain.split('.')[0].title()


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    scraper = TavilyScraperOB1()
    opportunities = scraper.scrape_all()

    # Preview
    print("\nTOP 10 OPPORTUNITA:")
    print("-" * 40)

    for opp in opportunities[:10]:
        print(f"\n{opp['player_name']}")
        print(f"  Ruolo: {opp['role_name']} | Tipo: {opp['opportunity_type']}")
        print(f"  Club: {opp.get('current_club', 'N/A')}")
        print(f"  Fonte: {opp['source_name']}")
