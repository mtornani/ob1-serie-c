#!/usr/bin/env python3
"""
OB1 Serie C - Scraper v2
Raccolta dati strutturati per alimentare File Search Store
"""

import requests
import re
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

from models import (
    PlayerProfile, MarketOpportunity, OpportunityType, PlayerRole,
    ALL_SERIE_C_CLUBS
)
from date_filter import is_article_fresh

load_dotenv()


class OB1Scraper:
    """Scraper per opportunità di mercato Serie C"""
    
    def __init__(self):
        self.serper_key = os.getenv('SERPER_API_KEY')
        if not self.serper_key:
            raise ValueError("SERPER_API_KEY mancante")
        
        self.session = requests.Session()
        self.session.headers.update({
            'X-API-KEY': self.serper_key,
            'Content-Type': 'application/json'
        })
    
    # =========================================================================
    # SEARCH QUERIES
    # =========================================================================
    
    QUERIES = {
        OpportunityType.SVINCOLATO: [
            '"Serie C" "parametro zero" giocatore 2025',
            '"Serie C" "svincolato" calciatore',
            '"Lega Pro" svincolato centrocampista OR difensore OR attaccante',
        ],
        OpportunityType.RESCISSIONE: [
            '"Serie C" "rescinde" contratto',
            '"Serie C" "risoluzione consensuale"',
            '"Lega Pro" rescissione giocatore',
        ],
        OpportunityType.PRESTITO: [
            '"Serie C" "prestito" disponibile',
            '"Serie C" "in prestito" gennaio',
            'Juventus OR Milan OR Inter "prestito Serie C"',
        ],
        OpportunityType.INFORTUNIO: [
            '"Serie C" "infortunio" "lungo stop"',
            '"Serie C" "rottura crociato" OR "lesione"',
            '"Lega Pro" "stagione finita" infortunio',
        ],
        OpportunityType.SERIE_D_TALENT: [
            '"Serie D" talento "interesse Serie C"',
            '"Serie D" capocannoniere promozione',
            '"Eccellenza" giovane "piace a" Serie C',
        ],
        OpportunityType.PERFORMANCE: [
            '"Serie C" "doppietta" ultima giornata',
            '"Serie C" "tripletta" OR "hat-trick"',
            '"Serie C" "migliore in campo"',
        ],
    }
    
    # =========================================================================
    # CORE METHODS
    # =========================================================================
    
    def search(self, query: str, num_results: int = 10) -> List[Dict[str, Any]]:
        """Esegue ricerca su Serper"""
        
        url = "https://google.serper.dev/search"
        payload = {
            'q': query,
            'num': num_results,
            'gl': 'it',
            'hl': 'it',
            'tbs': 'qdr:w'  # ultima settimana
        }
        
        try:
            response = self.session.post(url, json=payload, timeout=30)
            response.raise_for_status()
            return response.json().get('organic', [])
        except Exception as e:
            print(f"❌ Search error: {e}")
            return []
    
    def scrape_all(self) -> List[MarketOpportunity]:
        """Esegue tutte le query e restituisce opportunità"""
        
        all_opportunities = []
        seen_urls = set()
        
        for opp_type, queries in self.QUERIES.items():
            print(f"\n🔍 Scanning: {opp_type.value}")
            
            for query in queries:
                print(f"   → {query[:50]}...")
                results = self.search(query)
                
                for item in results:
                    url = item.get('link', '')
                    
                    # Dedup
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    
                    # Validate
                    if not self._is_valid_result(item):
                        continue

                    # Check article freshness (filter old news)
                    is_fresh, stale_reason = is_article_fresh(url)
                    if not is_fresh:
                        print(f"      [SKIP] Stale article: {stale_reason}")
                        continue

                    # Parse
                    opportunity = self._parse_result(item, opp_type)
                    if opportunity:
                        all_opportunities.append(opportunity)
        
        # Sort by relevance
        all_opportunities.sort(key=lambda x: x.relevance_score, reverse=True)
        
        print(f"\n✅ Trovate {len(all_opportunities)} opportunità")
        return all_opportunities
    
    # =========================================================================
    # PARSING
    # =========================================================================
    
    def _is_valid_result(self, item: Dict[str, Any]) -> bool:
        """Filtra risultati non rilevanti"""
        
        text = (item.get('title', '') + ' ' + item.get('snippet', '')).lower()
        url = item.get('link', '').lower()
        
        # Skip non-player content
        skip_keywords = [
            'allenatore', 'mister', 'tecnico', 'direttore',
            'presidente', 'patron', 'dirigente', 'wikipedia'
        ]
        
        player_keywords = [
            'giocatore', 'calciatore', 'centrocampista', 'difensore',
            'attaccante', 'portiere', 'esterno', 'mediano', 'terzino'
        ]
        
        if any(kw in text for kw in skip_keywords):
            if not any(kw in text for kw in player_keywords):
                return False
        
        if 'wikipedia' in url:
            return False
        
        # Must mention Serie C or a club
        mentions_league = any(kw in text for kw in ['serie c', 'lega pro'])
        mentions_club = any(club.lower() in text for club in ALL_SERIE_C_CLUBS)
        
        return mentions_league or mentions_club
    
    def _parse_result(self, item: Dict[str, Any], opp_type: OpportunityType) -> Optional[MarketOpportunity]:
        """Converte risultato raw in MarketOpportunity"""
        
        title = item.get('title', '')
        snippet = item.get('snippet', '')
        full_text = title + ' ' + snippet
        
        # Extract player name
        player_name = self._extract_player_name(full_text)
        if not player_name:
            player_name = "Nome da verificare"
        
        # Extract clubs
        clubs = self._extract_clubs(full_text)
        
        # Calculate relevance
        relevance = self._calculate_relevance(item, opp_type)
        
        # Build description
        description = self._build_description(title, snippet, opp_type)
        
        return MarketOpportunity(
            opportunity_type=opp_type,
            player_name=player_name,
            description=description,
            relevance_score=relevance,
            clubs_involved=clubs,
            reported_date=self._parse_date(item.get('date', 'Oggi')),
            source_url=item.get('link', ''),
            source_name=self._extract_source(item.get('link', '')),
            raw_snippet=snippet
        )
    
    def _extract_player_name(self, text: str) -> Optional[str]:
        """Estrae nome giocatore dal testo"""
        
        patterns = [
            r'(?:calciatore|centrocampista|difensore|attaccante|portiere|esterno|mediano)\s+([A-Z][a-zàèéìòù]+\s+[A-Z][a-zàèéìòù]+)',
            r'([A-Z][a-zàèéìòù]+\s+[A-Z][a-zàèéìòù]+)(?:,?\s+(?:classe|nato))',
            r'tesseramento\s+(?:del\s+)?(?:calciatore\s+)?([A-Z][a-zàèéìòù]+\s+[A-Z][a-zàèéìòù]+)',
            r'([A-Z][a-zàèéìòù]+\s+[A-Z][a-zàèéìòù]+)\s+(?:è\s+)?(?:svincolato|parametro zero)',
            r'(?:l\'ex|ex)\s+(?:\w+\s+)?([A-Z][a-zàèéìòù]+\s+[A-Z][a-zàèéìòù]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Validate not a club name
                if name not in ALL_SERIE_C_CLUBS and 'Serie' not in name:
                    return name
        
        return None
    
    def _extract_clubs(self, text: str) -> List[str]:
        """Estrae club menzionati"""
        
        found = []
        text_lower = text.lower()
        
        for club in ALL_SERIE_C_CLUBS:
            if club.lower() in text_lower:
                found.append(club)
        
        return found[:3]  # Max 3 clubs
    
    def _calculate_relevance(self, item: Dict[str, Any], opp_type: OpportunityType) -> int:
        """Calcola punteggio rilevanza 1-5"""
        
        text = (item.get('title', '') + ' ' + item.get('snippet', '')).lower()
        score = 3
        
        # High value opportunities
        if opp_type == OpportunityType.SVINCOLATO:
            if 'ufficiale' in text or 'tesserato' in text:
                score = 5
            elif 'parametro zero' in text:
                score = 5
        
        elif opp_type == OpportunityType.RESCISSIONE:
            if 'ufficiale' in text:
                score = 5
            else:
                score = 4
        
        elif opp_type == OpportunityType.INFORTUNIO:
            if 'lungo stop' in text or 'stagione finita' in text:
                score = 4
        
        # Negative signals
        if any(kw in text for kw in ['rumors', 'potrebbe', 'forse', 'indiscrezione']):
            score -= 1
        
        # Recency boost
        date_str = item.get('date', '').lower()
        if 'oggi' in date_str or 'ore fa' in date_str:
            score = min(5, score + 1)
        
        return max(1, min(5, score))
    
    def _build_description(self, title: str, snippet: str, opp_type: OpportunityType) -> str:
        """Costruisce descrizione human-readable"""
        
        # Clean snippet
        desc = snippet.replace('...', '').strip()
        
        # Add context based on type
        type_context = {
            OpportunityType.SVINCOLATO: "Giocatore attualmente senza contratto, disponibile a parametro zero.",
            OpportunityType.RESCISSIONE: "Contratto rescisso, giocatore libero di firmare.",
            OpportunityType.PRESTITO: "Disponibile per operazione in prestito.",
            OpportunityType.INFORTUNIO: "Infortunio che potrebbe creare opportunità per sostituti.",
            OpportunityType.SERIE_D_TALENT: "Talento emergente dalle categorie inferiori.",
            OpportunityType.PERFORMANCE: "Prestazione di rilievo recente.",
        }
        
        return f"{desc}\n\n{type_context.get(opp_type, '')}"
    
    def _parse_date(self, date_str: str) -> str:
        """Normalizza data"""
        
        date_str = date_str.lower()
        today = datetime.now()
        
        if 'oggi' in date_str or 'ore fa' in date_str:
            return today.strftime("%Y-%m-%d")
        elif 'ieri' in date_str:
            return (today - timedelta(days=1)).strftime("%Y-%m-%d")
        elif 'giorni fa' in date_str:
            try:
                days = int(re.search(r'(\d+)', date_str).group(1))
                return (today - timedelta(days=days)).strftime("%Y-%m-%d")
            except:
                pass
        
        return today.strftime("%Y-%m-%d")
    
    def _extract_source(self, url: str) -> str:
        """Estrae nome fonte da URL"""
        
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        
        sources = {
            'tuttoc.com': 'TuttoC',
            'calciomercato.com': 'Calciomercato',
            'transfermarkt': 'Transfermarkt',
            'gazzetta.it': 'Gazzetta',
            'corrieredellosport.it': 'Corriere dello Sport',
            'tuttosport.com': 'Tuttosport',
            'tuttomercatoweb.com': 'TMW',
            'tuttocampo.it': 'TuttoCampo',
            'football-italia.net': 'Football Italia',
        }
        
        for key, name in sources.items():
            if key in domain:
                return name
        
        return domain.replace('www.', '').split('.')[0].title()


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🎯 OB1 SERIE C SCRAPER v2")
    print("=" * 60)
    
    scraper = OB1Scraper()
    opportunities = scraper.scrape_all()
    
    # Preview
    print("\n📋 TOP 5 OPPORTUNITÀ:")
    print("-" * 40)
    
    for opp in opportunities[:5]:
        print(f"\n{'⭐' * opp.relevance_score} {opp.player_name}")
        print(f"   Tipo: {opp.opportunity_type.value}")
        print(f"   Club: {', '.join(opp.clubs_involved) or 'N/A'}")
        print(f"   Fonte: {opp.source_name}")
