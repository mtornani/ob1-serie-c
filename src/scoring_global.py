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
        
        # 1. Freshness (Max 100 points)
        days_old = (datetime.now() - datetime.strptime(opp.reported_date, "%Y-%m-%d")).days
        freshness_score = max(0, 100 - (days_old * 20))
        score += freshness_score * self.weights.get('freshness', 0.25)

        # 2. Source Quality (Max 100 points)
        # Check if source is in trusted_sources
        trusted = self.config.get('trusted_sources', [])
        source_score = 100 if any(ts in opp.source_url.lower() for ts in trusted) else 40
        score += source_score * self.weights.get('source_quality', 0.20)

        # 3. Type Relevance (Max 100 points)
        type_scores = {
            OpportunityType.RESCISSIONE: 100,
            OpportunityType.SVINCOLATO: 90,
            OpportunityType.PRESTITO: 70,
            OpportunityType.TALENT: 80,
            OpportunityType.TRANSFER_RUMOR: 50
        }
        type_score = type_scores.get(opp.opportunity_type, 60)
        score += type_score * self.weights.get('type_relevance', 0.20)

        # 4. Completeness (Does it have player name and description?)
        completeness = 0
        if opp.player_name and opp.player_name != "Unknown": completeness += 50
        if len(opp.description) > 50: completeness += 50
        score += completeness * self.weights.get('completeness', 0.15)

        # Map to 1-5 scale
        final_score = round(score / 20)
        return max(1, min(5, final_score))

    def enrich_description(self, opp: MarketOpportunity):
        """Adds tactical verdict based on score."""
        if opp.relevance_score >= 4:
            opp.description += "\n\n💡 OB1 VERDICT: HIGH RELEVANCE SIGNAL - Potential priority target."
        elif opp.relevance_score <= 2:
            opp.description += "\n\n⚠️ OB1 VERDICT: LOW CONFIDENCE - Monitor only."
