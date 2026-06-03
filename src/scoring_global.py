"""
OB1 WORLD - Universal Scoring Engine
Weighted analysis for global football opportunities.
"""

from typing import Dict, Any
from models import MarketOpportunity, OpportunityType
from datetime import datetime

class OB1Scorer:
    """Universal scoring for multi-league opportunities."""

    def __init__(self, league_config: Dict[str, Any]):
        self.config = league_config
        # Pesi di default (possono essere sovrascritti nella config della lega)
        self.weights = league_config.get('scoring_weights', {
            'freshness': 0.25,
            'source_quality': 0.20,
            'type_relevance': 0.20,
            'completeness': 0.15,
            'market_value': 0.10,
            'league_fit': 0.10
        })

    def calculate_score(self, opp: MarketOpportunity) -> int:
        """Calculates relevance score (1-5) based on weighted factors."""
        score = 0.0

        # 1. Freshness (Max 100 points) — gradual decay, not cliff at 5 days
        try:
            days_old = (datetime.now() - datetime.strptime(opp.reported_date, "%Y-%m-%d")).days
        except (ValueError, TypeError):
            days_old = 7  # assume week-old if date missing
        if days_old <= 0:
            freshness_score = 100
        elif days_old <= 3:
            freshness_score = 85
        elif days_old <= 7:
            freshness_score = 70
        elif days_old <= 14:
            freshness_score = 55
        elif days_old <= 30:
            freshness_score = 40
        else:
            freshness_score = 20
        score += freshness_score * self.weights.get('freshness', 0.25)

        # 2. Source Quality (Max 100 points)
        trusted = self.config.get('trusted_sources', [])
        source_score = 100 if any(ts in opp.source_url.lower() for ts in trusted) else 40
        score += source_score * self.weights.get('source_quality', 0.20)

        # 3. Type Relevance (Max 100 points)
        type_scores = {
            OpportunityType.RESCISSIONE: 100,
            OpportunityType.SVINCOLATO: 90,
            OpportunityType.TALENT: 80,
            OpportunityType.PRESTITO: 70,
            OpportunityType.TRANSFER_RUMOR: 50,
        }
        type_score = type_scores.get(opp.opportunity_type, 60)
        score += type_score * self.weights.get('type_relevance', 0.20)

        # 4. Completeness (Does it have player name and description?)
        completeness = 0
        if opp.player_name and opp.player_name != "Unknown":
            completeness += 50
        if len(opp.description) > 50:
            completeness += 50
        score += completeness * self.weights.get('completeness', 0.15)

        # 5. Market Value (Max 100 points) — proxy for player quality at scrape time
        mv = opp.market_value or 0
        if mv >= 500000:
            mv_score = 100
        elif mv >= 250000:
            mv_score = 85
        elif mv >= 100000:
            mv_score = 70
        elif mv > 0:
            mv_score = 50
        else:
            mv_score = 55  # unknown ≠ bad — most raw scrapes lack this
        score += mv_score * self.weights.get('market_value', 0.10)

        # 6. League Fit (Max 100 points) — is the article Italy-focused?
        url_lower = opp.source_url.lower()
        desc_lower = opp.description.lower()
        if any(d in url_lower for d in ['tuttoc', 'lacasadic', 'mister-x', 'legapro', 'calciodilettanti']):
            league_score = 100
        elif any(kw in desc_lower for kw in ['serie c', 'lega pro', 'serie d', 'eccellenza']):
            league_score = 80
        elif any(kw in desc_lower for kw in ['serie b', 'serie a']):
            league_score = 60
        else:
            league_score = 40
        score += league_score * self.weights.get('league_fit', 0.10)

        # Map to 1-5 scale
        final_score = round(score / 20)
        return max(1, min(5, final_score))

    def enrich_description(self, opp: MarketOpportunity):
        """Adds tactical verdict based on score."""
        if opp.relevance_score >= 4:
            opp.description += "\n\n💡 OB1 VERDICT: HIGH RELEVANCE SIGNAL - Potential priority target."
        elif opp.relevance_score <= 2:
            opp.description += "\n\n⚠️ OB1 VERDICT: LOW CONFIDENCE - Monitor only."
