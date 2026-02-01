"""
OB1 DNA Matching System

Player-Club DNA matching per connettere giovani talenti delle squadre B
con club di Serie C compatibili.
"""

from .models import PlayerDNA, ClubDNA, ClubNeed, MatchResult
from .matcher import DNAMatcher
from .scorer import calculate_match_score

__all__ = [
    'PlayerDNA',
    'ClubDNA',
    'ClubNeed',
    'MatchResult',
    'DNAMatcher',
    'calculate_match_score',
]
