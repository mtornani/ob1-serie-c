"""
OB1 Serie C - Data Models
Strutture dati per giocatori e opportunità di mercato
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List
from enum import Enum
import json


class OpportunityType(Enum):
    SVINCOLATO = "svincolato"
    RESCISSIONE = "rescissione"
    PRESTITO = "prestito"
    INFORTUNIO = "infortunio"  # Crea opportunità per sostituti
    SERIE_D_TALENT = "talento_serie_d"
    PERFORMANCE = "performance"


class PlayerRole(Enum):
    PORTIERE = "portiere"
    DIFENSORE_CENTRALE = "difensore_centrale"
    TERZINO_DESTRO = "terzino_destro"
    TERZINO_SINISTRO = "terzino_sinistro"
    MEDIANO = "mediano"
    CENTROCAMPISTA = "centrocampista"
    TREQUARTISTA = "trequartista"
    ESTERNO_DESTRO = "esterno_destro"
    ESTERNO_SINISTRO = "esterno_sinistro"
    ATTACCANTE = "attaccante"
    PUNTA = "punta"


@dataclass
class PlayerProfile:
    """Profilo giocatore strutturato per RAG"""

    # Identificazione
    name: str
    birth_year: Optional[int] = None
    nationality: Optional[str] = None

    # Ruolo e caratteristiche
    role: Optional[PlayerRole] = None
    foot: Optional[str] = None  # destro, sinistro, ambidestro
    height_cm: Optional[int] = None

    # Valore di mercato (Transfermarkt)
    market_value: Optional[int] = None  # in euro
    market_value_formatted: Optional[str] = None  # es. "€300k"

    # Situazione contrattuale
    current_club: Optional[str] = None
    contract_status: Optional[str] = None  # sotto contratto, svincolato, in scadenza
    contract_expiry: Optional[str] = None

    # Statistiche stagione corrente
    appearances: Optional[int] = None
    goals: Optional[int] = None
    assists: Optional[int] = None
    minutes_played: Optional[int] = None

    # Agente / Agenzia (DATA-003 QW-1)
    agent: Optional[str] = None

    # Storico
    previous_clubs: List[str] = field(default_factory=list)
    career_highlights: List[str] = field(default_factory=list)

    # Metadati
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())
    sources: List[str] = field(default_factory=list)

    def to_document(self) -> str:
        """Converte il profilo in documento testuale per File Search"""

        lines = [f"# PROFILO GIOCATORE: {self.name}", ""]

        # Info base
        if self.birth_year:
            age = datetime.now().year - self.birth_year
            lines.append(f"Età: {age} anni (nato nel {self.birth_year})")
        if self.market_value_formatted:
            lines.append(f"Valore Mercato: {self.market_value_formatted}")
        if self.nationality:
            lines.append(f"Nazionalità: {self.nationality}")
        if self.role:
            lines.append(f"Ruolo: {self.role.value}")
        if self.foot:
            lines.append(f"Piede: {self.foot}")
        if self.height_cm:
            lines.append(f"Altezza: {self.height_cm} cm")

        lines.append("")

        # Situazione attuale
        lines.append("## SITUAZIONE CONTRATTUALE")
        if self.current_club:
            lines.append(f"Club attuale: {self.current_club}")
        if self.contract_status:
            lines.append(f"Status: {self.contract_status}")
        if self.contract_expiry:
            lines.append(f"Scadenza contratto: {self.contract_expiry}")
        if self.agent:
            lines.append(f"Agente: {self.agent}")

        lines.append("")

        # Stats
        if any([self.appearances, self.goals, self.assists]):
            lines.append("## STATISTICHE STAGIONE 2024/25")
            if self.appearances:
                lines.append(f"Presenze: {self.appearances}")
            if self.goals:
                lines.append(f"Gol: {self.goals}")
            if self.assists:
                lines.append(f"Assist: {self.assists}")
            if self.minutes_played:
                lines.append(f"Minuti giocati: {self.minutes_played}")
            lines.append("")

        # Storico
        if self.previous_clubs:
            lines.append("## CARRIERA")
            lines.append(f"Club precedenti: {', '.join(self.previous_clubs)}")
            lines.append("")

        if self.career_highlights:
            lines.append("## NOTE")
            for highlight in self.career_highlights:
                lines.append(f"- {highlight}")
            lines.append("")

        # Metadati
        lines.append(f"---")
        lines.append(f"Ultimo aggiornamento: {self.last_updated}")
        if self.sources:
            lines.append(f"Fonti: {', '.join(self.sources)}")

        return "\n".join(lines)

    def to_json(self) -> str:
        """Serializza in JSON"""
        data = asdict(self)
        if self.role:
            data["role"] = self.role.value
        return json.dumps(data, ensure_ascii=False, indent=2)


@dataclass
class MarketOpportunity:
    """Opportunità di mercato rilevata"""

    # Tipo opportunità
    opportunity_type: OpportunityType

    # Giocatore coinvolto
    player_name: str
    player_profile: Optional[PlayerProfile] = None

    # Dettagli opportunità
    description: str = ""
    relevance_score: int = 3  # 1-5

    # Contesto
    clubs_involved: List[str] = field(default_factory=list)
    reported_date: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d")
    )

    # Fonti
    source_url: str = ""
    source_name: str = ""
    raw_snippet: str = ""

    # Metadati
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_document(self) -> str:
        """Converte in documento per File Search"""

        lines = [
            f"# OPPORTUNITÀ: {self.player_name}",
            f"Tipo: {self.opportunity_type.value.upper()}",
            f"Data segnalazione: {self.reported_date}",
            f"Rilevanza: {'⭐' * self.relevance_score}",
            "",
            "## DESCRIZIONE",
            self.description,
            "",
        ]

        if self.clubs_involved:
            lines.append(f"Club coinvolti: {', '.join(self.clubs_involved)}")
            lines.append("")

        if self.raw_snippet:
            lines.append("## FONTE ORIGINALE")
            lines.append(f"> {self.raw_snippet}")
            lines.append("")

        lines.append(f"---")
        lines.append(f"Fonte: {self.source_name} ({self.source_url})")
        lines.append(f"Registrato: {self.created_at}")

        return "\n".join(lines)


# Costanti utili
SERIE_C_CLUBS_2024_25 = {
    "girone_a": [
        "Albinoleffe",
        "Alcione",
        "Arzignano",
        "FeralpiSalò",
        "Giana Erminio",
        "Lecco",
        "Legnago",
        "Lumezzane",
        "Novara",
        "Padova",
        "Pergolettese",
        "Pro Patria",
        "Pro Vercelli",
        "Renate",
        "Trento",
        "Triestina",
        "Union Clodiense",
        "Vicenza",
        "Virtus Verona",
    ],
    "girone_b": [
        "Arezzo",
        "Ascoli",
        "Campobasso",
        "Carpi",
        "Cesena",
        "Entella",
        "Gubbio",
        "Lucchese",
        "Milan Futuro",
        "Perugia",
        "Pescara",
        "Pianese",
        "Pineto",
        "Pontedera",
        "Rimini",
        "SPAL",
        "Sestri Levante",
        "Ternana",
        "Torres",
        "Vis Pesaro",
    ],
    "girone_c": [
        "Audace Cerignola",
        "Avellino",
        "AZ Picerno",
        "Benevento",
        "Casertana",
        "Catania",
        "Cavese",
        "Crotone",
        "Foggia",
        "Giugliano",
        "Juventus Next Gen",
        "Latina",
        "Messina",
        "Monopoli",
        "Potenza",
        "Sorrento",
        "Taranto",
        "Team Altamura",
        "Trapani",
        "Turris",
    ],
}

ALL_SERIE_C_CLUBS = (
    SERIE_C_CLUBS_2024_25["girone_a"]
    + SERIE_C_CLUBS_2024_25["girone_b"]
    + SERIE_C_CLUBS_2024_25["girone_c"]
)
