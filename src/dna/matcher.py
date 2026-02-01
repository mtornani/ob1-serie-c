"""
DNA-001: DNA Matcher Engine

Motore principale per il matching player-club.
Carica dati, calcola match, genera raccomandazioni.
"""

import json
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

from .models import PlayerDNA, ClubDNA, MatchResult
from .scorer import calculate_match_score


class DNAMatcher:
    """
    Motore di matching Player-Club DNA.

    Carica database giocatori e club, calcola compatibilità
    e genera liste di match ordinate per score.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Inizializza il matcher.

        Args:
            data_dir: Directory contenente players/ e clubs/
        """
        if data_dir is None:
            data_dir = Path(__file__).parent.parent.parent / 'data'

        self.data_dir = data_dir
        self.players_dir = data_dir / 'players'
        self.clubs_dir = data_dir / 'clubs'

        self.players: Dict[str, PlayerDNA] = {}
        self.clubs: Dict[str, ClubDNA] = {}

        self._load_data()

    def _load_data(self):
        """Carica tutti i dati da file JSON"""
        # Carica giocatori
        if self.players_dir.exists():
            for file in self.players_dir.glob('*.json'):
                try:
                    data = json.loads(file.read_text(encoding='utf-8'))
                    if isinstance(data, list):
                        for p in data:
                            player = PlayerDNA.from_dict(p)
                            self.players[player.id] = player
                    else:
                        player = PlayerDNA.from_dict(data)
                        self.players[player.id] = player
                except Exception as e:
                    print(f"Error loading {file}: {e}")

        # Carica club
        if self.clubs_dir.exists():
            for file in self.clubs_dir.glob('*.json'):
                try:
                    data = json.loads(file.read_text(encoding='utf-8'))
                    club = ClubDNA.from_dict(data)
                    self.clubs[club.id] = club
                except Exception as e:
                    print(f"Error loading {file}: {e}")

        print(f"📊 DNAMatcher loaded: {len(self.players)} players, {len(self.clubs)} clubs")

    def reload(self):
        """Ricarica tutti i dati"""
        self.players.clear()
        self.clubs.clear()
        self._load_data()

    def get_matches_for_club(
        self,
        club_id: str,
        min_score: int = 50,
        limit: int = 10,
        position_filter: Optional[str] = None,
    ) -> List[MatchResult]:
        """
        Trova i migliori match per un club.

        Args:
            club_id: ID del club
            min_score: Score minimo per includere (default 50)
            limit: Numero massimo risultati
            position_filter: Filtra solo per questa posizione

        Returns:
            Lista MatchResult ordinata per score decrescente
        """
        club = self.clubs.get(club_id)
        if not club:
            print(f"Club {club_id} not found")
            return []

        matches = []

        for player in self.players.values():
            # Filtro posizione se specificato
            if position_filter:
                if player.primary_position != position_filter and \
                   position_filter not in player.secondary_positions:
                    continue

            # Calcola match
            result = calculate_match_score(player, club)

            if result.score >= min_score:
                matches.append(result)

        # Ordina per score decrescente
        matches.sort(key=lambda x: x.score, reverse=True)

        return matches[:limit]

    def get_matches_for_player(
        self,
        player_id: str,
        min_score: int = 50,
        limit: int = 10,
    ) -> List[MatchResult]:
        """
        Trova i migliori club per un giocatore.

        Args:
            player_id: ID del giocatore
            min_score: Score minimo
            limit: Numero massimo risultati

        Returns:
            Lista MatchResult ordinata per score
        """
        player = self.players.get(player_id)
        if not player:
            print(f"Player {player_id} not found")
            return []

        matches = []

        for club in self.clubs.values():
            result = calculate_match_score(player, club)

            if result.score >= min_score:
                matches.append(result)

        matches.sort(key=lambda x: x.score, reverse=True)

        return matches[:limit]

    def get_top_matches(
        self,
        min_score: int = 75,
        limit: int = 20,
    ) -> List[MatchResult]:
        """
        Trova tutti i top match globali.

        Utile per la dashboard: "migliori opportunità di matching"

        Returns:
            Lista dei migliori match globali
        """
        all_matches = []

        for club in self.clubs.values():
            club_matches = self.get_matches_for_club(
                club.id,
                min_score=min_score,
                limit=5  # Top 5 per club
            )
            all_matches.extend(club_matches)

        # Rimuovi duplicati (stesso player-club) e ordina
        seen = set()
        unique_matches = []

        for m in all_matches:
            key = f"{m.player.id}_{m.club.id}"
            if key not in seen:
                seen.add(key)
                unique_matches.append(m)

        unique_matches.sort(key=lambda x: x.score, reverse=True)

        return unique_matches[:limit]

    def get_underused_talents(
        self,
        parent_club: Optional[str] = None,
        limit: int = 20,
    ) -> List[PlayerDNA]:
        """
        Trova giocatori underused (poco utilizzati).

        Questi sono i principali candidati al prestito.

        Args:
            parent_club: Filtra per club proprietario (es. "Juventus")
            limit: Numero massimo risultati

        Returns:
            Lista PlayerDNA ordinata per minutes_percentage
        """
        underused = []

        for player in self.players.values():
            if not player.is_underused:
                continue

            if parent_club and player.parent_club != parent_club:
                continue

            underused.append(player)

        # Ordina per meno minuti giocati
        underused.sort(key=lambda x: x.minutes_percentage)

        return underused[:limit]

    def get_players_by_team(self, team_name: str) -> List[PlayerDNA]:
        """Ottieni tutti i giocatori di una squadra"""
        return [
            p for p in self.players.values()
            if p.current_team.lower() == team_name.lower() or
               p.parent_club.lower() == team_name.lower()
        ]

    def get_club(self, club_id: str) -> Optional[ClubDNA]:
        """Ottieni un club per ID"""
        return self.clubs.get(club_id)

    def get_player(self, player_id: str) -> Optional[PlayerDNA]:
        """Ottieni un giocatore per ID"""
        return self.players.get(player_id)

    def search_players(self, query: str, limit: int = 10) -> List[PlayerDNA]:
        """Cerca giocatori per nome o club"""
        query_lower = query.lower()
        results = []

        for player in self.players.values():
            searchable = f"{player.name} {player.current_team} {player.parent_club}".lower()
            if query_lower in searchable:
                results.append(player)

        return results[:limit]

    def get_stats(self) -> dict:
        """Statistiche del database"""
        parent_clubs = set(p.parent_club for p in self.players.values() if p.parent_club)
        underused = sum(1 for p in self.players.values() if p.is_underused)

        return {
            'total_players': len(self.players),
            'total_clubs': len(self.clubs),
            'parent_clubs': list(parent_clubs),
            'underused_players': underused,
            'last_updated': datetime.now().isoformat(),
        }


# Singleton instance
_matcher_instance: Optional[DNAMatcher] = None


def get_matcher() -> DNAMatcher:
    """Ottieni istanza singleton del matcher"""
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = DNAMatcher()
    return _matcher_instance
