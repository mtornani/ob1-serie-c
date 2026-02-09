"""
DNA-001: Data Models for Player-Club DNA Matching

Definisce le strutture dati per il matching intelligente
tra giovani talenti e club di Serie C.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import date
from enum import Enum


class Position(Enum):
    """Posizioni calcistiche standardizzate"""

    GK = "POR"  # Portiere
    CB = "DC"  # Difensore Centrale
    LB = "TS"  # Terzino Sinistro
    RB = "TD"  # Terzino Destro
    CDM = "MED"  # Mediano
    CM = "CC"  # Centrocampista Centrale
    CAM = "TRQ"  # Trequartista
    LM = "ES"  # Esterno Sinistro
    RM = "ED"  # Esterno Destro
    LW = "AS"  # Ala Sinistra
    RW = "AD"  # Ala Destra
    CF = "ATT"  # Attaccante
    ST = "PC"  # Prima Punta


class TransferStatus(Enum):
    """Stato disponibilità giocatore"""

    AVAILABLE_LOAN = "disponibile_prestito"
    OUTGOING = "in_uscita"
    NOT_AVAILABLE = "incedibile"
    UNKNOWN = "sconosciuto"


class PlayingStyle(Enum):
    """Stili di gioco del club"""

    HIGH_PRESS = "pressing_alto"
    POSSESSION = "possesso"
    COUNTER = "transizioni"
    LOW_BLOCK = "difesa_bassa"
    DIRECT = "gioco_diretto"
    AERIAL = "gioco_aereo"
    WIDE_PLAY = "gioco_sulle_fasce"
    SAMMARINESE_MIX = "mix_sammarinese"  # Mix possesso + transizioni veloci


class Priority(Enum):
    """Priorità esigenza"""

    HIGH = "alta"
    MEDIUM = "media"
    LOW = "bassa"


@dataclass
class PlayerSkills:
    """Caratteristiche tecniche del giocatore (0-100)"""

    tecnica: int = 50
    velocita: int = 50
    fisico: int = 50
    visione: int = 50
    difesa: int = 50
    pressing: int = 50
    dribbling: int = 50
    tiro: int = 50

    def to_dict(self) -> Dict[str, int]:
        return {
            "tecnica": self.tecnica,
            "velocita": self.velocita,
            "fisico": self.fisico,
            "visione": self.visione,
            "difesa": self.difesa,
            "pressing": self.pressing,
            "dribbling": self.dribbling,
            "tiro": self.tiro,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlayerSkills":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PlayerDNA:
    """
    DNA del giocatore - profilo completo per il matching

    Contiene tutte le informazioni necessarie per matchare
    un giovane talento con il club giusto.
    """

    # Identità
    id: str
    name: str
    birth_year: int
    nationality: str = "Italia"

    # Posizione
    primary_position: str = "CC"
    secondary_positions: List[str] = field(default_factory=list)
    preferred_foot: str = "destro"  # destro, sinistro, ambidestro

    # Club
    parent_club: str = ""  # Juventus, Milan, Inter, etc.
    current_team: str = ""  # Juventus Next Gen, Milan Futuro
    contract_until: str = ""  # "2027-06-30"

    # Statistiche stagione corrente
    appearances: int = 0
    minutes_played: int = 0
    goals: int = 0
    assists: int = 0

    # Caratteristiche
    skills: PlayerSkills = field(default_factory=PlayerSkills)

    # Disponibilità
    transfer_status: str = TransferStatus.UNKNOWN.value
    estimated_loan_cost: int = 0  # In migliaia di euro

    # Fonte dati
    transfermarkt_id: str = ""
    transfermarkt_url: str = ""
    market_value: int = 0  # In migliaia di euro

    # Metadata
    last_updated: str = ""

    @property
    def age(self) -> int:
        """Calcola età attuale"""
        return date.today().year - self.birth_year

    @property
    def minutes_percentage(self) -> float:
        """Percentuale minuti giocati vs disponibili (stima 90 min * 30 partite)"""
        max_minutes = 90 * 30  # Circa una stagione
        return (
            round((self.minutes_played / max_minutes) * 100, 1)
            if max_minutes > 0
            else 0
        )

    @property
    def is_underused(self) -> bool:
        """True se il giocatore sta giocando poco (<40% minuti)"""
        return self.minutes_percentage < 40

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "birth_year": self.birth_year,
            "age": self.age,
            "nationality": self.nationality,
            "primary_position": self.primary_position,
            "secondary_positions": self.secondary_positions,
            "preferred_foot": self.preferred_foot,
            "parent_club": self.parent_club,
            "current_team": self.current_team,
            "contract_until": self.contract_until,
            "appearances": self.appearances,
            "minutes_played": self.minutes_played,
            "minutes_percentage": self.minutes_percentage,
            "is_underused": self.is_underused,
            "goals": self.goals,
            "assists": self.assists,
            "skills": self.skills.to_dict(),
            "transfer_status": self.transfer_status,
            "estimated_loan_cost": self.estimated_loan_cost,
            "market_value": self.market_value,
            "transfermarkt_url": self.transfermarkt_url,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlayerDNA":
        skills_data = data.pop("skills", {})
        skills = PlayerSkills.from_dict(skills_data) if skills_data else PlayerSkills()

        # Remove computed properties
        data.pop("age", None)
        data.pop("minutes_percentage", None)
        data.pop("is_underused", None)

        return cls(
            skills=skills,
            **{k: v for k, v in data.items() if k in cls.__dataclass_fields__},
        )


@dataclass
class ClubNeed:
    """Singola esigenza di mercato del club"""

    position: str  # "CC", "DC", "ES"
    player_type: str = ""  # "box_to_box", "regista", "tutta_fascia"
    age_min: int = 18
    age_max: int = 28
    priority: str = Priority.MEDIUM.value

    def to_dict(self) -> dict:
        return {
            "position": self.position,
            "player_type": self.player_type,
            "age_min": self.age_min,
            "age_max": self.age_max,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClubNeed":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ClubDNA:
    """
    DNA del Club - profilo per il matching

    Definisce tattica, esigenze e capacità del club
    per trovare i giovani più adatti.
    """

    # Identità
    id: str
    name: str
    category: str = "Serie C"  # Serie C, Serie D
    group: str = ""  # A, B, C per Serie C

    # Tattica
    primary_formation: str = "4-3-3"
    playing_styles: List[str] = field(default_factory=list)

    # Esigenze
    needs: List[ClubNeed] = field(default_factory=list)

    # Budget
    budget_type: str = "solo_prestiti"  # solo_prestiti, prestiti_obbligo, acquisti
    max_loan_cost: int = 50  # Max in migliaia di euro

    # Track record giovani
    youth_minutes_pct: float = 0  # % minuti a under 23
    youth_development_score: int = 3  # 1-5 stelle

    # Contatti (per premium)
    ds_name: str = ""
    city: str = ""

    # Metadata
    last_updated: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "group": self.group,
            "primary_formation": self.primary_formation,
            "playing_styles": self.playing_styles,
            "needs": [n.to_dict() for n in self.needs],
            "budget_type": self.budget_type,
            "max_loan_cost": self.max_loan_cost,
            "youth_minutes_pct": self.youth_minutes_pct,
            "youth_development_score": self.youth_development_score,
            "ds_name": self.ds_name,
            "city": self.city,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClubDNA":
        needs_data = data.pop("needs", [])
        needs = [ClubNeed.from_dict(n) for n in needs_data]
        return cls(
            needs=needs,
            **{k: v for k, v in data.items() if k in cls.__dataclass_fields__},
        )


@dataclass
class MatchResult:
    """Risultato del matching player-club"""

    player: PlayerDNA
    club: ClubDNA
    score: int  # 0-100
    breakdown: Dict[str, int]  # Score per componente
    recommendation: str = ""  # Testo raccomandazione
    matched_need: Optional[ClubNeed] = None

    def to_dict(self) -> dict:
        return {
            "player": self.player.to_dict(),
            "club_id": self.club.id,
            "club_name": self.club.name,
            "score": self.score,
            "breakdown": self.breakdown,
            "recommendation": self.recommendation,
            "matched_need": self.matched_need.to_dict() if self.matched_need else None,
        }
