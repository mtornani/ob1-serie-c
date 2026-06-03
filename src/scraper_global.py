#!/usr/bin/env python3
"""
OB1 WORLD - Global Scraper v3
High-performance scouting engine using Scrapling (Anti-Bot) and Tavily (Discovery).
"""

import os
import re
import yaml
import json
import requests
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv
from google import genai

# Scrapling Integration
try:
    from scrapling import StealthyFetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False

from src.models import MarketOpportunity, OpportunityType
from src.date_filter import is_article_fresh

load_dotenv()

class GlobalScraper:
    """Multi-league scouting with advanced anti-bot bypass."""

    # URLs that are index/listing pages, not player articles
    BLACKLIST_URL_PATTERNS = [
        '/transfers/wettbewerb/',
        '/startseite/wettbewerb/',
        '/spieltagtabelle/',
        '/serie-c-girone',
        '/serie-d-girone',
        '/marktwerte/',
        '/statistik/',
        '/forum/',
        '/jugadores-libres/',
        '/transferencias/',
    ]

    # Title fragments that indicate a listing page, not a player article
    JUNK_TITLE_TERMS = [
        'jugadores libres', 'ranking', 'classifica', 'tabella',
        'gli svincolati', 'sul mercato', 'quanti svincolati',
        'transferencias', 'calendario', 'risultati',
        'ultime notizie', 'tutto mercato', 'calciomercato live',
        'notiziario', 'fischio finale',
    ]

    def __init__(self, config_path: str = "config/leagues.yaml"):
        self.serper_key = os.getenv('SERPER_API_KEY')
        self.tavily_key = os.getenv('TAVILY_API_KEY')
        self.gemini_key = os.getenv('GEMINI_API_KEY')
        self.gemini_client = genai.Client(api_key=self.gemini_key) if self.gemini_key else None

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        self.leagues = self.config.get('leagues', {})

    def search_grounded(self, query: str) -> List[Dict]:
        """Gemini Search Grounding — one call: searches Google + extracts player names."""
        if not self.gemini_client:
            return []

        prompt = (
            f"Cerca su Google notizie recenti (2026) su: {query}\n\n"
            "Identifica SOLO nomi di calciatori INDIVIDUALI (persone fisiche) menzionati nelle notizie.\n\n"
            "ESCLUDI assolutamente:\n"
            "- Giornalisti o opinionisti (es. Gianluca Di Marzio, Fabrizio Romano)\n"
            "- Nomi di siti web, media, radio (es. Sky Sport, Calciomercato.com, Web Radio)\n"
            "- Organizzazioni, federazioni (es. Dipartimento Interregionale, Associazione Italiana Calciatori)\n"
            "- Squadre, rappresentative, campionati (es. Rappresentativa Serie D, Juniores Cup)\n"
            "- Concetti generici (es. Parametro Zero, Giovani Talenti, Stagione Sportiva)\n"
            "- Qualsiasi nome che non sia 'Nome Cognome' di un calciatore reale\n\n"
            "Rispondi ESCLUSIVAMENTE con un JSON array, nessun testo aggiuntivo:\n"
            '[{"player_name": "Nome Cognome", "source_url": "url articolo", '
            '"opportunity_type": "svincolato|prestito|rescissione|mercato", '
            '"description": "max 80 caratteri sul motivo"}]\n\n'
            "Se non trovi calciatori individuali reali, rispondi esattamente: []"
        )

        try:
            response = self.gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    tools=[genai.types.Tool(google_search=genai.types.GoogleSearch())],
                    temperature=0.0,
                ),
            )
            text = response.text or ""
            m = re.search(r'\[.*\]', text, re.DOTALL)
            if not m:
                return []
            items = json.loads(m.group(0))
            if not isinstance(items, list):
                return []
            print(f"    [GROUNDED] {len(items)} giocatori trovati per: {query[:40]}...")
            return items
        except Exception as e:
            print(f"    [GROUNDED ERROR] {e}")
            return []

    def search_tavily(self, query: str) -> List[Dict]:
        """High-quality discovery phase. Open search intentionally — no domain filter."""
        if not self.tavily_key: return []

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": 10,
        }
        
        try:
            res = requests.post(url, json=payload, timeout=20)
            res.raise_for_status()
            results = res.json().get('results', [])
            print(f"    [TAVILY] Found {len(results)} raw results for query: {query[:40]}...")
            return results
        except Exception:
            return []

    def deep_scrape(self, url: str) -> str:
        """Deep scraping with Scrapling's StealthyFetcher to bypass Cloudflare."""
        if not SCRAPLING_AVAILABLE: return ""
        
        try:
            fetcher = StealthyFetcher(headless=True)
            page = fetcher.fetch(url, network_idle=True)
            return page.get_all_text()
        except Exception as e:
            print(f"  [SCRAPLING ERROR] {url}: {e}")
            return ""

    def _is_junk_url(self, url: str) -> bool:
        """Detect index/listing pages that are not player-specific articles."""
        url_lower = url.lower()
        return any(p in url_lower for p in self.BLACKLIST_URL_PATTERNS)

    def _is_junk_title(self, title: str) -> bool:
        """Detect generic listing titles that aren't about a specific player."""
        title_lower = title.lower()
        return any(term in title_lower for term in self.JUNK_TITLE_TERMS)

    def scrape_league(self, league_id: str) -> List[MarketOpportunity]:
        """Scrape all opportunities for a league with fresh filtering."""
        conf = self.leagues.get(league_id)
        if not conf: return []

        print(f"🌐 Scraping: {conf['name']}...")
        opportunities = []
        seen_urls = set()

        for query in conf.get('queries', []):
            # Primary: Gemini Search Grounding (understands football context, no regex needed)
            grounded = self.search_grounded(query)
            if grounded:
                for item in grounded:
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get('source_url') or '').strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    player_name = str(item.get('player_name') or '').strip()[:50]
                    if not player_name:
                        continue

                    fresh, reason = is_article_fresh(url)
                    if not fresh:
                        print(f"  [STALE] Skipping {url}: {reason}")
                        continue

                    opp = MarketOpportunity(
                        league_id=league_id,
                        opportunity_type=self._detect_type(
                            str(item.get('opportunity_type') or '') + ' ' + str(item.get('description') or '')
                        ),
                        player_name=player_name,
                        description=str(item.get('description') or ''),
                        source_url=url,
                        source_name=url.lstrip('/').split('://')[-1].split('/')[0],
                    )
                    opportunities.append(opp)
                continue  # grounding succeeded — skip Tavily for this query

            # Fallback: Tavily + regex extraction
            results = self.search_tavily(query)

            for item in results:
                url = item.get('url', '')
                if url in seen_urls: continue
                seen_urls.add(url)

                if self._is_junk_url(url):
                    print(f"  [JUNK URL] Skipping: {url[:60]}...")
                    continue

                title = item.get('title', '')
                if self._is_junk_title(title):
                    print(f"  [JUNK TITLE] Skipping: {title[:60]}...")
                    continue

                fresh, reason = is_article_fresh(url)
                if not fresh:
                    print(f"  [STALE] Skipping {url}: {reason}")
                    continue

                player_name = self._extract_name(title)
                if not player_name:
                    print(f"  [NO NAME] Skipping: {title[:60]}...")
                    continue

                opp = MarketOpportunity(
                    league_id=league_id,
                    opportunity_type=self._detect_type(title + (item.get('content', '') or '')),
                    player_name=player_name,
                    description=item.get('content', ''),
                    source_url=url,
                    source_name=url.lstrip('/').split('://')[-1].split('/')[0],
                )
                opportunities.append(opp)

        return opportunities

    def _detect_type(self, text: str) -> OpportunityType:
        text = text.lower()
        if any(k in text for k in ['svincolato', 'parametro zero', 'free agent']): return OpportunityType.SVINCOLATO
        if any(k in text for k in ['rescinde', 'risoluzione', 'rescissione']): return OpportunityType.RESCISSIONE
        if any(k in text for k in ['prestito', 'loan']): return OpportunityType.PRESTITO
        return OpportunityType.TALENT

    def _extract_name(self, title: str) -> str:
        """Extract a plausible player name (Capitalized Firstname Lastname) from a title.

        Returns empty string if no real name is found, which signals the caller to skip.
        """
        if not title:
            return ''

        # Strip common separators used by news sites
        # "Club, ufficiale: Mario Rossi firma" → try after the separator
        for sep in [':', '–', '-', '|', ',']:
            if sep in title:
                parts = title.split(sep)
                # Try each part for a name
                for part in parts:
                    name = self._find_person_name(part.strip())
                    if name:
                        return name
                # If no part had a name, fall through to whole-title search

        return self._find_person_name(title)

    def _find_person_name(self, text: str) -> str:
        """Find a 'Firstname Lastname' pattern (two+ consecutive capitalized words) in text.

        Filters out club names and common non-person capitalized words.
        """
        # Match sequences of 2-3 capitalized words (covers "De Rossi", "Van Basten", etc.)
        matches = re.findall(
            r'\b([A-ZÀÈÉÌÒÙÁÉÍÓÚ][a-zàèéìòùáéíóú]+(?:\s+(?:De|Di|Del|Della|Van|Von|Dos|Da|El|La|Le|Lo|Al)?[A-ZÀÈÉÌÒÙÁÉÍÓÚ][a-zàèéìòùáéíóú]+)+)\b',
            text
        )

        # Filter out non-person names (clubs, leagues, media brands, institutions)
        skip_words = {
            # Leagues / competitions
            'Serie', 'Lega', 'Coppa', 'Girone', 'Champions', 'League', 'Europa',
            'Conference', 'Copa', 'Premier', 'Bundesliga',
            # Clubs
            'Juventus', 'Milan', 'Inter', 'Roma', 'Napoli',
            # Countries / regions
            'Italia', 'Brazil', 'Argentina',
            # Media / platforms
            'Transfermarkt', 'Calciomercato', 'Mercato', 'Sky', 'Sport',
            'Football', 'Italy', 'Tuttoc', 'Mister',
            # Institutions / generic
            'Associazione', 'Italiana', 'Dipartimento', 'Interregionale',
            'Scuola', 'Superiore', 'Portale', 'Notizie', 'Calcio',
        }

        for match in matches:
            first_word = match.split()[0]
            if first_word in skip_words:
                continue
            # Must be at least 2 words to be a real name
            if len(match.split()) >= 2:
                return match[:50]

        return ''
