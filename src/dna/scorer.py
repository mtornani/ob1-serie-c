"""
DNA-001: Match Scoring Algorithm

Calcola la compatibilità tra un giocatore e un club
basandosi su multiple dimensioni.
"""

from typing import Dict, Tuple, Optional
from .models import PlayerDNA, ClubDNA, ClubNeed, MatchResult, PlayingStyle


# Mapping stili di gioco -> skills richieste
STYLE_SKILL_MAP = {
    PlayingStyle.HIGH_PRESS.value: ['pressing', 'fisico', 'velocita'],
    PlayingStyle.POSSESSION.value: ['tecnica', 'visione'],
    PlayingStyle.COUNTER.value: ['velocita', 'dribbling', 'tecnica'],
    PlayingStyle.LOW_BLOCK.value: ['difesa', 'fisico'],
    PlayingStyle.DIRECT.value: ['fisico', 'tiro'],
    PlayingStyle.AERIAL.value: ['fisico'],
    PlayingStyle.WIDE_PLAY.value: ['velocita', 'dribbling', 'tecnica'],
}

# Posizioni compatibili (primaria -> secondarie accettabili)
POSITION_COMPATIBILITY = {
    'DC': ['MED', 'TS', 'TD'],
    'TS': ['ES', 'DC'],
    'TD': ['ED', 'DC'],
    'MED': ['DC', 'CC'],
    'CC': ['MED', 'TRQ'],
    'TRQ': ['CC', 'AS', 'AD'],
    'ES': ['TS', 'AS'],
    'ED': ['TD', 'AD'],
    'AS': ['ES', 'ATT', 'TRQ'],
    'AD': ['ED', 'ATT', 'TRQ'],
    'ATT': ['PC', 'AS', 'AD', 'TRQ'],
    'PC': ['ATT'],
    'POR': [],
}


def calculate_match_score(player: PlayerDNA, club: ClubDNA) -> MatchResult:
    """
    Calcola lo score di compatibilità tra giocatore e club.

    Returns:
        MatchResult con score 0-100 e breakdown componenti
    """
    breakdown = {}
    matched_need = None

    # 1. POSITION FIT (30%)
    position_score, matched_need = _calc_position_fit(player, club)
    breakdown['position'] = position_score

    # 2. AGE FIT (20%)
    age_score = _calc_age_fit(player, matched_need)
    breakdown['age'] = age_score

    # 3. STYLE FIT (25%)
    style_score = _calc_style_fit(player, club)
    breakdown['style'] = style_score

    # 4. AVAILABILITY (15%)
    availability_score = _calc_availability(player)
    breakdown['availability'] = availability_score

    # 5. BUDGET FIT (10%)
    budget_score = _calc_budget_fit(player, club)
    breakdown['budget'] = budget_score

    # Calcolo score totale con pesi
    total_score = (
        position_score * 0.30 +
        age_score * 0.20 +
        style_score * 0.25 +
        availability_score * 0.15 +
        budget_score * 0.10
    )

    # Genera raccomandazione testuale
    recommendation = _generate_recommendation(player, club, breakdown, matched_need)

    return MatchResult(
        player=player,
        club=club,
        score=round(total_score),
        breakdown=breakdown,
        recommendation=recommendation,
        matched_need=matched_need,
    )


def _calc_position_fit(player: PlayerDNA, club: ClubDNA) -> Tuple[int, Optional[ClubNeed]]:
    """Calcola fit posizione con esigenze club"""
    best_score = 0
    best_need = None

    for need in club.needs:
        score = 0

        # Match esatto posizione primaria
        if player.primary_position == need.position:
            score = 100
        # Match posizione secondaria
        elif need.position in player.secondary_positions:
            score = 75
        # Match posizione compatibile
        elif need.position in POSITION_COMPATIBILITY.get(player.primary_position, []):
            score = 50
        # Check inverso
        elif player.primary_position in POSITION_COMPATIBILITY.get(need.position, []):
            score = 50

        # Bonus se priorità alta
        if need.priority == 'alta' and score > 0:
            score = min(100, score + 10)

        if score > best_score:
            best_score = score
            best_need = need

    return best_score, best_need


def _calc_age_fit(player: PlayerDNA, matched_need: Optional[ClubNeed]) -> int:
    """Calcola fit età con requisiti"""
    if not matched_need:
        # Default: preferenza 20-25 anni
        age = player.age
        if 20 <= age <= 25:
            return 100
        elif 18 <= age < 20:
            return 80
        elif 25 < age <= 28:
            return 70
        else:
            return max(0, 100 - abs(age - 23) * 10)

    age = player.age
    min_age = matched_need.age_min
    max_age = matched_need.age_max

    if min_age <= age <= max_age:
        return 100
    elif age < min_age:
        return max(0, 100 - (min_age - age) * 20)
    else:
        return max(0, 100 - (age - max_age) * 20)


def _calc_style_fit(player: PlayerDNA, club: ClubDNA) -> int:
    """Calcola fit stile di gioco"""
    if not club.playing_styles:
        return 70  # Default neutro

    total_score = 0
    count = 0

    for style in club.playing_styles:
        required_skills = STYLE_SKILL_MAP.get(style, [])

        if required_skills:
            skills_dict = player.skills.to_dict()
            style_total = 0

            for skill_name in required_skills:
                skill_value = skills_dict.get(skill_name, 50)
                style_total += skill_value

            style_avg = style_total / len(required_skills)
            total_score += style_avg
            count += 1

    return round(total_score / count) if count > 0 else 70


def _calc_availability(player: PlayerDNA) -> int:
    """Calcola disponibilità effettiva"""
    score = 0

    # Status trasferimento
    if player.transfer_status == 'disponibile_prestito':
        score = 100
    elif player.transfer_status == 'in_uscita':
        score = 80
    elif player.transfer_status == 'sconosciuto':
        score = 50
    else:
        score = 20

    # Bonus se underused (il club proprietario vorrà farlo giocare)
    if player.is_underused:
        score = min(100, score + 15)

    return score


def _calc_budget_fit(player: PlayerDNA, club: ClubDNA) -> int:
    """Calcola fit budget"""
    if player.estimated_loan_cost == 0:
        return 90  # Gratuito o sconosciuto

    if player.estimated_loan_cost <= club.max_loan_cost:
        return 100
    elif player.estimated_loan_cost <= club.max_loan_cost * 1.5:
        return 60
    elif player.estimated_loan_cost <= club.max_loan_cost * 2:
        return 30
    else:
        return 10


def _generate_recommendation(
    player: PlayerDNA,
    club: ClubDNA,
    breakdown: Dict[str, int],
    matched_need: Optional[ClubNeed]
) -> str:
    """Genera raccomandazione testuale"""
    parts = []

    # Descrizione ruolo
    role_desc = _get_role_description(player.primary_position)
    parts.append(f"{role_desc}")

    # Punto di forza principale
    skills = player.skills.to_dict()
    top_skill = max(skills.items(), key=lambda x: x[1])
    if top_skill[1] >= 70:
        skill_desc = _get_skill_description(top_skill[0])
        parts.append(f"con {skill_desc}")

    # Fit tattico
    if breakdown['style'] >= 80:
        parts.append(f"ideale per il {club.primary_formation}")
    elif breakdown['style'] >= 60:
        parts.append(f"adattabile al {club.primary_formation}")

    # Disponibilità
    if player.is_underused:
        parts.append(f"cerca minutaggio ({player.minutes_percentage:.0f}% giocato)")

    return ", ".join(parts)


def _get_role_description(position: str) -> str:
    """Descrizione testuale del ruolo"""
    descriptions = {
        'DC': 'Difensore centrale',
        'TS': 'Terzino sinistro',
        'TD': 'Terzino destro',
        'MED': 'Mediano',
        'CC': 'Centrocampista',
        'TRQ': 'Trequartista',
        'ES': 'Esterno sinistro',
        'ED': 'Esterno destro',
        'AS': 'Ala sinistra',
        'AD': 'Ala destra',
        'ATT': 'Attaccante',
        'PC': 'Prima punta',
        'POR': 'Portiere',
    }
    return descriptions.get(position, position)


def _get_skill_description(skill: str) -> str:
    """Descrizione testuale della skill"""
    descriptions = {
        'tecnica': 'ottima tecnica',
        'velocita': 'grande velocità',
        'fisico': 'fisicità importante',
        'visione': 'visione di gioco',
        'difesa': 'solidità difensiva',
        'pressing': 'pressing intenso',
        'dribbling': 'dribbling efficace',
        'tiro': 'buon tiro',
    }
    return descriptions.get(skill, skill)
