"""
OB1 — Data models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OpportunityType(Enum):
    SVINCOLATO = "svincolato"
    RESCISSIONE = "rescissione"
    PRESTITO = "prestito"
    INFORTUNIO = "infortunio"
    TALENT = "talento"
    PERFORMANCE = "performance"
    TRANSFER_RUMOR = "rumor_mercato"


@dataclass
class MarketOpportunity:
    league_id: str
    opportunity_type: OpportunityType
    player_name: str
    description: str = ""
    relevance_score: int = 3
    source_url: str = ""
    source_name: str = ""
    reported_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
