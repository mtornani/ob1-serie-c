#!/usr/bin/env python3
"""
OB1 WORLD - Global Scraper v3
High-performance scouting engine using Scrapling (Anti-Bot) and Tavily (Discovery).
"""

import os
import yaml
import json
import requests
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

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

    def __init__(self, config_path: str = "config/leagues.yaml"):
        self.serper_key = os.getenv('SERPER_API_KEY')
        self.tavily_key = os.getenv('TAVILY_API_KEY')
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        self.leagues = self.config.get('leagues', {})

    def search_tavily(self, query: str, include_domains: Optional[List[str]] = None) -> List[Dict]:
        """High-quality discovery phase."""
        if not self.tavily_key: return []
        
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": 10
            # Discovery aperta: non usiamo include_domains qui per non tagliare fuori notizie nuove
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
            # StealthyFetcher with Cloudflare solver
            fetcher = StealthyFetcher(headless=True)
            page = fetcher.fetch(url, network_idle=True)
            return page.text
        except Exception as e:
            print(f"  [SCRAPLING ERROR] {url}: {e}")
            return ""

    def scrape_league(self, league_id: str) -> List[MarketOpportunity]:
        """Scrape all opportunities for a league with fresh filtering."""
        conf = self.leagues.get(league_id)
        if not conf: return []
        
        print(f"🌐 Scraping: {conf['name']}...")
        opportunities = []
        seen_urls = set()

        for query in conf.get('queries', []):
            # Discovery using Tavily
            results = self.search_tavily(query, include_domains=conf.get('trusted_sources'))
            
            for item in results:
                url = item.get('url', '')
                if url in seen_urls: continue
                seen_urls.add(url)
                
                # 1. Date Filtering (Anti-Stale)
                fresh, reason = is_article_fresh(url)
                if not fresh:
                    print(f"  [STALE] Skipping {url}: {reason}")
                    continue

                # 2. Basic Opportunity
                opp = MarketOpportunity(
                    league_id=league_id,
                    opportunity_type=self._detect_type(item.get('title', '') + item.get('content', '')),
                    player_name=self._extract_name(item.get('title', '')),
                    description=item.get('content', ''),
                    source_url=url,
                    source_name=url.split('/')[2]
                )
                opportunities.append(opp)
                
        return opportunities

    def _detect_type(self, text: str) -> OpportunityType:
        text = text.lower()
        if any(k in text for k in ['svincolato', 'free agent', 'libre']): return OpportunityType.SVINCOLATO
        if any(k in text for k in ['rescinde', 'risoluzione']): return OpportunityType.RESCISSIONE
        if any(k in text for k in ['prestito', 'loan', 'empréstimo']): return OpportunityType.PRESTITO
        return OpportunityType.TALENT

    def _extract_name(self, title: str) -> str:
        # Placeholder for AI extraction in enrichment step
        return title.split(':')[0].strip()[:50]
