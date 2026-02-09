"""
DNA-001: Match Scoring Algorithm v2.0

Calcola la compatibilità tra un giocatore e un club
basandosi su multiple dimensioni con filtri realistici.

Cambiamenti v2:
- Giocatori incedibili bloccati completamente (score=0)
- Filtro categoria: penalizzazione market_value vs livello club
- Budget fit ribilanciato (costo sconosciuto = neutro, non favorevole)
- Pesi ribilanciati: budget e availability più pesanti
- Stile mix_sammarinese con mapping reale
- Compatibilità posizioni più stretta
- Soglia minima position fit per procedere
"""

from typing import Dict, Tuple, Optional
from .models import PlayerDNA, ClubDNA, ClubNeed, MatchResult, PlayingStyle


# --- CONFIGURAZIONE PESI ---
# Pesi ribilanciati per risultati realistici
WEIGHTS = {
    'position': 0.25,      # 25% - Fit ruolo
    'age': 0.15,           # 15% - Fit età
    'style': 0.15,         # 15% - Fit tattico
    'availability': 0.20,  # 20% - Disponibilità reale (era 15%)
    'budget': 0.20,        # 20% - Sostenibilità economica (era 10%)
    'level': 0.05,         # 5%  - NUOVO: Compatibilità livello/categoria
}


# Mapping stili di gioco -> skills richieste
STYLE_SKILL_MAP = {
    PlayingStyle.HIGH_PRESS.value: ['pressing', 'fisico', 'velocita'],
    PlayingStyle.POSSESSION.value: ['tecnica', 'visione'],
    PlayingStyle.COUNTER.value: ['velocita', 'dribbling', 'tecnica'],
    PlayingStyle.LOW_BLOCK.value: ['difesa', 'fisico'],
    PlayingStyle.DIRECT.value: ['fisico', 'tiro'],
    PlayingStyle.AERIAL.value: ['fisico'],
    PlayingStyle.WIDE_PLAY.value: ['velocita', 'dribbling', 'tecnica'],
    # NUOVO: mix_sammarinese = possesso + transizioni veloci + tecnica
    PlayingStyle.SAMMARINESE_MIX.value: ['tecnica', 'visione', 'velocita', 'dribbling'],
}

# Posizioni compatibili - PIÙ RESTRITTIVE
# Solo posizioni veramente adattabili, non "vicine in campo"
POSITION_COMPATIBILITY = {
    'DC': ['MED'],          # DC può fare il mediano (era DC->MED,TS,TD)
    'TS': ['ES'],           # Terzino sx -> Esterno sx (tolto DC)
    'TD': ['ED'],           # Terzino dx -> Esterno dx (tolto DC)
    'MED': ['CC'],          # Mediano -> Centrocampista (tolto DC)
    'CC': ['MED', 'TRQ'],   # CC può fare mediano o trequartista
    'TRQ': ['CC'],          # Trequartista -> CC (tolto AS, AD)
    'ES': ['TS', 'AS'],     # Esterno sx -> Terzino sx o Ala sx
    'ED': ['TD', 'AD'],     # Esterno dx -> Terzino dx o Ala dx
    'AS': ['ES'],           # Ala sx -> Esterno sx (tolto ATT, TRQ)
    'AD': ['ED'],           # Ala dx -> Esterno dx (tolto ATT, TRQ)
    'ATT': ['PC', 'AS', 'AD'],  # Attaccante -> Punta, Ali
    'PC': ['ATT'],          # Punta -> Attaccante
    'POR': [],              # Portiere solo portiere
}

# Fasce di market value per categoria club (in migliaia €)
# Un club sammarinese non può permettersi un giocatore da 3M€
CATEGORY_VALUE_CAPS = {
    'Campionato Sammarinese': 300,    # Max 300k€ market value realistico
    'Serie D': 500,                    # Max 500k€
    'Serie C': 2000,                   # Max 2M€
    'Serie B': 10000,                  # Max 10M€
}


def calculate_match_score(player: PlayerDNA, club: ClubDNA) -> MatchResult:
    """
    Calcola lo score di compatibilità tra giocatore e club.

    FILTRI BLOCCANTI (score=0):
    - Giocatore incedibile
    - Market value troppo alto per la categoria del club
    - Nessuna posizione compatibile con le esigenze del club

    Returns:
        MatchResult con score 0-100 e breakdown componenti
    """
    breakdown = {}
    matched_need = None

    # ═══════════════════════════════════════════
    # FILTRI BLOCCANTI - se falliscono, score = 0
    # ═══════════════════════════════════════════

    # BLOCCO 1: Giocatore incedibile = NON matchabile
    if player.transfer_status == 'incedibile':
        return _zero_result(player, club, "Giocatore non disponibile (incedibile)")

    # BLOCCO 2: Market value troppo alto per categoria club
    value_cap = CATEGORY_VALUE_CAPS.get(club.category, 5000)
    if player.market_value > 0 and player.market_value > value_cap:
        return _zero_result(
            player, club,
            f"Valore di mercato ({player.market_value}k€) troppo alto per {club.category}"
        )

    # ═══════════════════════════════════════════
    # CALCOLO COMPONENTI
    # ═══════════════════════════════════════════

    # 1. POSITION FIT (25%)
    position_score, matched_need = _calc_position_fit(player, club)
    breakdown['position'] = position_score

    # BLOCCO 3: Nessuna posizione compatibile
    if position_score == 0:
        return _zero_result(player, club, "Nessun ruolo compatibile con le esigenze del club")

    # 2. AGE FIT (15%)
    age_score = _calc_age_fit(player, matched_need)
    breakdown['age'] = age_score

    # 3. STYLE FIT (15%)
    style_score = _calc_style_fit(player, club)
    breakdown['style'] = style_score

    # 4. AVAILABILITY (20%)
    availability_score = _calc_availability(player)
    breakdown['availability'] = availability_score

    # 5. BUDGET FIT (20%)
    budget_score = _calc_budget_fit(player, club)
    breakdown['budget'] = budget_score

    # 6. LEVEL FIT (5%) - NUOVO
    level_score = _calc_level_fit(player, club)
    breakdown['level'] = level_score

    # ═══════════════════════════════════════════
    # CALCOLO SCORE TOTALE
    # ═══════════════════════════════════════════
    total_score = (
        position_score * WEIGHTS['position'] +
        age_score * WEIGHTS['age'] +
        style_score * WEIGHTS['style'] +
        availability_score * WEIGHTS['availability'] +
        budget_score * WEIGHTS['budget'] +
        level_score * WEIGHTS['level']
    )

    # Penalità aggiuntive per situazioni irrealistiche
    total_score = _apply_reality_penalties(total_score, player, club, breakdown)

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


def _zero_result(player: PlayerDNA, club: ClubDNA, reason: str) -> MatchResult:
    """Crea un MatchResult con score 0 (bloccato dai filtri)"""
    return MatchResult(
        player=player,
        club=club,
        score=0,
        breakdown={
            'position': 0, 'age': 0, 'style': 0,
            'availability': 0, 'budget': 0, 'level': 0,
        },
        recommendation=reason,
        matched_need=None,
    )


def _calc_position_fit(player: PlayerDNA, club: ClubDNA) -> Tuple[int, Optional[ClubNeed]]:
    """Calcola fit posizione con esigenze club - versione più restrittiva"""
    best_score = 0
    best_need = None

    for need in club.needs:
        score = 0

        # Match esatto posizione primaria
        if player.primary_position == need.position:
            score = 100
        # Match posizione secondaria del giocatore
        elif need.position in player.secondary_positions:
            score = 70  # era 75, leggermente ridotto
        # Match posizione compatibile (solo forward)
        elif need.position in POSITION_COMPATIBILITY.get(player.primary_position, []):
            score = 40  # era 50
        # Check inverso (la posizione del giocatore è compatibile con ciò che serve)
        elif player.primary_position in POSITION_COMPATIBILITY.get(need.position, []):
            score = 35  # era 50

        # Bonus ridotto per priorità alta
        if need.priority == 'alta' and score >= 70:  # Solo se buon match
            score = min(100, score + 5)  # era +10

        if score > best_score:
            best_score = score
            best_need = need

    return best_score, best_need


def _calc_age_fit(player: PlayerDNA, matched_need: Optional[ClubNeed]) -> int:
    """Calcola fit età con requisiti - penalità più severa fuori range"""
    if not matched_need:
        age = player.age
        if 20 <= age <= 25:
            return 100
        elif 18 <= age < 20:
            return 80
        elif 25 < age <= 28:
            return 60  # era 70
        else:
            return max(0, 100 - abs(age - 23) * 15)  # era *10, più severo

    age = player.age
    min_age = matched_need.age_min
    max_age = matched_need.age_max

    if min_age <= age <= max_age:
        return 100
    elif age < min_age:
        return max(0, 100 - (min_age - age) * 25)  # era *20
    else:
        return max(0, 100 - (age - max_age) * 25)  # era *20


def _calc_style_fit(player: PlayerDNA, club: ClubDNA) -> int:
    """Calcola fit stile di gioco - con mapping per tutti gli stili"""
    if not club.playing_styles:
        return 50  # Neutro basso (era 70)

    total_score = 0
    count = 0

    for style in club.playing_styles:
        required_skills = STYLE_SKILL_MAP.get(style, [])

        if required_skills:
            skills_dict = player.skills.to_dict()
            style_total = 0

            for skill_name in required_skills:
                skill_value = skills_dict.get(skill_name, 40)  # Default 40 (era 50)
                style_total += skill_value

            style_avg = style_total / len(required_skills)
            total_score += style_avg
            count += 1

    if count == 0:
        return 50  # Nessuno stile mappato

    return round(total_score / count)


def _calc_availability(player: PlayerDNA) -> int:
    """Calcola disponibilità effettiva - più severa"""
    score = 0

    if player.transfer_status == 'disponibile_prestito':
        score = 100
    elif player.transfer_status == 'in_uscita':
        score = 75  # era 80
    elif player.transfer_status == 'sconosciuto':
        score = 30  # era 40/50 — sconosciuto = bassa probabilità
    else:
        score = 15  # Default per status non riconosciuti

    # Bonus underused ridotto
    if player.is_underused:
        score = min(100, score + 10)  # era +15

    return score


def _calc_budget_fit(player: PlayerDNA, club: ClubDNA) -> int:
    """
    Calcola fit budget - completamente riscritta.

    Usa sia estimated_loan_cost che market_value per stima realistica.
    """
    # Stima costo reale del prestito
    loan_cost = player.estimated_loan_cost

    # Se loan_cost sconosciuto, stima da market_value
    if loan_cost == 0 and player.market_value > 0:
        # Regola: prestito costa circa 10-15% del market value
        loan_cost = round(player.market_value * 0.12)

    # Costo veramente sconosciuto (nessun dato)
    if loan_cost == 0 and player.market_value == 0:
        return 50  # Neutro — era 90, assurdamente favorevole

    # Confronto con budget club
    max_budget = club.max_loan_cost

    if max_budget <= 0:
        return 30  # Club senza budget

    if loan_cost <= max_budget:
        return 100  # Perfettamente sostenibile
    elif loan_cost <= max_budget * 1.3:
        return 70  # Leggermente sopra, fattibile con trattativa
    elif loan_cost <= max_budget * 2:
        return 35  # Difficile ma non impossibile
    elif loan_cost <= max_budget * 3:
        return 15  # Molto improbabile
    else:
        return 5   # Irrealistico


def _calc_level_fit(player: PlayerDNA, club: ClubDNA) -> int:
    """
    NUOVO: Calcola compatibilità livello giocatore vs categoria club.

    Un giocatore con market value da Serie A non va in Campionato Sammarinese.
    Un giocatore dalla Primavera è più adatto a categorie inferiori.
    """
    category = club.category
    mv = player.market_value  # in migliaia €

    if category == 'Campionato Sammarinese':
        # Livello amatoriale/semi-pro: ideale per giocatori con mv basso
        if mv == 0:
            return 60  # Sconosciuto, possibile
        elif mv <= 100:
            return 100  # Perfetto
        elif mv <= 300:
            return 70  # Buono, giocatore giovane
        elif mv <= 500:
            return 40  # Probabilmente troppo per questo livello
        elif mv <= 1000:
            return 20  # Molto improbabile
        else:
            return 5   # Irrealistico

    elif category == 'Serie D':
        if mv == 0:
            return 60
        elif mv <= 300:
            return 100
        elif mv <= 800:
            return 70
        elif mv <= 1500:
            return 40
        else:
            return 15

    elif category == 'Serie C':
        if mv == 0:
            return 60
        elif mv <= 500:
            return 90
        elif mv <= 1500:
            return 100  # Sweet spot per Serie C
        elif mv <= 3000:
            return 60   # Alto ma fattibile in prestito
        elif mv <= 5000:
            return 30
        else:
            return 10

    else:
        # Default per categorie non mappate
        return 50


def _apply_reality_penalties(
    score: float,
    player: PlayerDNA,
    club: ClubDNA,
    breakdown: Dict[str, int]
) -> float:
    """
    Penalità aggiuntive per situazioni che non hanno senso nel mondo reale.
    """
    # Penalità se budget fit è molto basso (match economicamente impraticabile)
    if breakdown['budget'] <= 15:
        score *= 0.7  # -30% se budget irrealistico

    # Penalità se disponibilità bassa (perché proporre chi non è disponibile?)
    if breakdown['availability'] <= 30:
        score *= 0.75  # -25% se difficilmente disponibile

    # Penalità cumulativa: se sia budget che availability sono bassi
    if breakdown['budget'] <= 35 and breakdown['availability'] <= 30:
        score *= 0.8  # Ulteriore -20%

    # Bonus: giocatore perfettamente disponibile E sostenibile
    if breakdown['availability'] >= 90 and breakdown['budget'] >= 80:
        score *= 1.05  # +5% per match realistici

    return min(100, max(0, score))


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

    # Indicatore realisticità
    if breakdown.get('budget', 0) >= 80 and breakdown.get('availability', 0) >= 80:
        parts.append("operazione fattibile")
    elif breakdown.get('budget', 0) <= 35:
        parts.append("costo elevato per il club")

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
