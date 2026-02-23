"""
OUROBOROS - Global Data Models v3
Unified structures for Global Scouting and DNA 2.0.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum
import json


class OpportunityType(Enum):
    SVINCOLATO = "svincolato"
    RESCISSIONE = "rescissione"
    PRESTITO = "prestito"
    INFORTUNIO = "infortunio"
    TALENT = "talento"
    PERFORMANCE = "performance"
    TRANSFER_RUMOR = "rumor_mercato"


class PlayerRole(Enum):
    PORTIERE = "GK"
    DIFENSORE_CENTRALE = "CB"
    TERZINO_DESTRO = "RB"
    TERZINO_SINISTRO = "LB"
    MEDIANO = "CDM"
    CENTROCAMPISTA = "CM"
    TREQUARTISTA = "CAM"
    ESTERNO_DESTRO = "RW"
    ESTERNO_SINISTRO = "LW"
    ATTACCANTE = "ST"
    PUNTA = "CF"


@dataclass
class PlayerProfile:
    """Global Player Profile for RAG"""
    name: str
    league_id: str
    birth_year: Optional[int] = None
    nationality: Optional[str] = None
    role: Optional[PlayerRole] = None
    foot: Optional[str] = None
    height_cm: Optional[int] = None
    current_club: Optional[str] = None
    contract_status: Optional[str] = None
    contract_expiry: Optional[str] = None
    market_value: Optional[str] = None
    transfermarkt_url: Optional[str] = None
    
    # Season Stats
    appearances: Optional[int] = None
    goals: Optional[int] = None
    assists: Optional[int] = None
    
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    sources: List[str] = field(default_factory=list)
    
    def to_document(self) -> str:
        lines = [f"# PLAYER PROFILE: {self.name}", f"League: {self.league_id}", ""]
        if self.birth_year: lines.append(f"Birth Year: {self.birth_year}")
        if self.nationality: lines.append(f"Nationality: {self.nationality}")
        if self.role: lines.append(f"Role: {self.role.value}")
        if self.current_club: lines.append(f"Current Club: {self.current_club}")
        if self.market_value: lines.append(f"Market Value: {self.market_value}")
        lines.append(f"\nLast Updated: {self.last_updated}")
        return "\n".join(lines)


@dataclass
class MarketOpportunity:
    """Global Market Opportunity with DNA Support"""
    league_id: str
    opportunity_type: OpportunityType
    player_name: str
    description: str = ""
    relevance_score: int = 3
    source_url: str = ""
    source_name: str = ""
    reported_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    
    # DNA 2.0 Semantic Matching
    dna_matches: Dict[str, Dict] = field(default_factory=dict)
    
    def to_document(self) -> str:
        lines = [
            f"# OPPORTUNITY: {self.player_name}",
            f"League: {self.league_id}",
            f"Type: {self.opportunity_type.value.upper()}",
            f"Date: {self.reported_date}",
            f"Relevance: {'⭐' * self.relevance_score}",
            "",
            "## DNA STRATEGIC FIT",
        ]
        
        for arch_id, match in self.dna_matches.items():
            score = match.get('score', 0)
            verdict = match.get('verdict', 'N/A')
            lines.append(f"- {arch_id.upper()}: {score}% - {verdict}")

        lines.extend([
            "",
            "## DESCRIPTION",
            self.description,
            "",
            f"Source: {self.source_name} ({self.source_url})"
        ])
        return "\n".join(lines)
