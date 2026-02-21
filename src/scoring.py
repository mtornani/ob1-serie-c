#!/usr/bin/env python3
"""
OB1 Serie C - SCORE-001: Advanced Scoring Algorithm
Prioritizza le opportunita di mercato con scoring intelligente
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional


class OB1Scorer:
    """Sistema di scoring avanzato per opportunita di mercato"""

    # Pesi per ogni componente (SCORE-002: rebalanced for differentiation)
    WEIGHTS = {
        'freshness': 0.15,
        'opportunity_type': 0.10,
        'experience': 0.20,
        'age': 0.15,
        'market_value': 0.15,
        'league_fit': 0.15,
        'source': 0.05,
        'completeness': 0.05,
    }

    # Club noti Serie C 2025/26 (subset per matching)
    SERIE_C_CLUBS = {
        'pescara', 'reggiana', 'spal', 'cesena', 'rimini', 'perugia',
        'ternana', 'arezzo', 'gubbio', 'torres', 'vis pesaro', 'pineto',
        'carpi', 'pontedera', 'lucchese', 'pianese', 'entella', 'virtus entella',
        'milan futuro', 'ascoli', 'campobasso', 'sestri levante', 'legnago',
        'avellino', 'benevento', 'catania', 'cerignola', 'audace cerignola',
        'crotone', 'foggia', 'giugliano', 'latina', 'messina', 'monopoli',
        'potenza', 'sorrento', 'taranto', 'team altamura', 'turris',
        'trapani', 'casertana', 'cavese', 'juventus next gen',
        'alcione', 'arzignano', 'caldiero', 'feralpisalò', 'giana erminio',
        'lecco', 'lumezzane', 'novara', 'padova', 'pro patria', 'pro vercelli',
        'renate', 'trento', 'triestina', 'union clodiense', 'vicenza',
        'atalanta u23', 'albinoleffe', 'l.r. vicenza',
    }

    # Score per tipo opportunita
    TYPE_SCORES = {
        'svincolato': 100,
        'rescissione': 95,
        'scadenza': 80,
        'prestito': 70,
        'mercato': 50,
        'altro': 40,
    }

    # Score per fonte
    SOURCE_SCORES = {
        'tuttoc': 95,
        'tuttolegapro': 95,
        'gazzetta': 95,
        'corriere dello sport': 90,
        'tuttosport': 90,
        'calciomercato': 85,
        'tmw': 80,
        'transfermarkt': 85,
        'football italia': 75,
        'tuttocampo': 70,
    }

    def score(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calcola score per una singola opportunita

        Returns:
            Dict con ob1_score, classification, score_breakdown
        """
        breakdown = {
            'freshness': self._calc_freshness(opportunity.get('reported_date') or opportunity.get('discovered_at', '')),
            'opportunity_type': self._calc_type_score(opportunity.get('opportunity_type', 'altro')),
            'experience': self._calc_experience(opportunity),
            'age': self._calc_age(opportunity.get('age')),
            'market_value': self._calc_market_value(opportunity.get('market_value')),
            'league_fit': self._calc_league_fit(opportunity),
            'source': self._calc_source(opportunity.get('source_name', '')),
            'completeness': self._calc_completeness(opportunity),
        }

        # Weighted sum
        total = sum(
            breakdown[key] * self.WEIGHTS[key]
            for key in self.WEIGHTS
        )

        ob1_score = int(round(total))

        # Classification (SCORE-002: calibrated for ~15% hot, ~50% warm, ~35% cold)
        if ob1_score >= 70:
            classification = 'hot'
        elif ob1_score >= 57:
            classification = 'warm'
        else:
            classification = 'cold'

        return {
            'ob1_score': ob1_score,
            'classification': classification,
            'score_breakdown': breakdown,
        }

    def _calc_freshness(self, date_str: str) -> int:
        """Score basato su quanto e' recente la notizia"""
        if not date_str:
            return 50

        try:
            # Handle ISO format
            if 'T' in date_str:
                date_str = date_str.split('T')[0]

            reported = datetime.strptime(date_str, '%Y-%m-%d').date()
            today = datetime.now().date()
            days_ago = (today - reported).days

            if days_ago <= 0:
                return 100  # Oggi
            elif days_ago == 1:
                return 95   # Ieri
            elif days_ago <= 3:
                return 85   # Ultimi 3 giorni
            elif days_ago <= 7:
                return 70   # Ultima settimana
            elif days_ago <= 14:
                return 60   # Ultime 2 settimane (ancora rilevante per mercato)
            elif days_ago <= 30:
                return 45   # Ultimo mese
            else:
                return 25   # Piu vecchio

        except (ValueError, TypeError):
            return 50

    def _calc_type_score(self, opp_type: str) -> int:
        """Score basato sul tipo di opportunita"""
        if not opp_type:
            return 50
        return self.TYPE_SCORES.get(opp_type.lower(), 50)

    def _calc_experience(self, opportunity: Dict[str, Any]) -> int:
        """Score basato sull'esperienza del giocatore"""
        appearances = opportunity.get('appearances', 0) or 0
        previous_clubs = opportunity.get('previous_clubs', []) or []
        current_club = opportunity.get('current_club', '') or ''
        summary = opportunity.get('summary', '') or ''

        score = 50  # Base

        # Bonus per presenze
        if appearances >= 100:
            score += 30
        elif appearances >= 50:
            score += 20
        elif appearances >= 20:
            score += 10

        # Bonus per club precedenti (indica esperienza)
        if len(previous_clubs) >= 3:
            score += 15
        elif len(previous_clubs) >= 1:
            score += 10

        # Bonus se ha giocato in Serie B (check nel summary o club)
        serie_b_keywords = ['serie b', 'serieb', 'cadetti']
        text_to_check = (summary + ' ' + current_club + ' ' + ' '.join(previous_clubs)).lower()
        if any(kw in text_to_check for kw in serie_b_keywords):
            score += 15

        return min(100, score)

    def _calc_age(self, age: Optional[int]) -> int:
        """Score basato sull'eta del giocatore"""
        if not age:
            return 60  # Neutro se non conosciamo l'eta

        # Fascia ottimale: 22-28
        if 22 <= age <= 28:
            return 100
        elif 20 <= age < 22:
            return 85   # Giovane promettente
        elif 28 < age <= 30:
            return 75   # Ancora valido
        elif 18 <= age < 20:
            return 65   # Molto giovane, potenziale
        elif 30 < age <= 32:
            return 55   # Esperienza ma calo
        elif age > 32:
            return 35   # Fuori target
        else:
            return 50   # Under 18

    def _calc_source(self, source_name: str) -> int:
        """Score basato sull'affidabilita della fonte"""
        if not source_name:
            return 50

        source_lower = source_name.lower()

        # Check exact match first
        if source_lower in self.SOURCE_SCORES:
            return self.SOURCE_SCORES[source_lower]

        # Check partial match
        for key, score in self.SOURCE_SCORES.items():
            if key in source_lower or source_lower in key:
                return score

        return 50  # Fonte sconosciuta

    def _calc_completeness(self, opportunity: Dict[str, Any]) -> int:
        """Score basato su quanti dati abbiamo"""
        score = 0

        # Nome giocatore valido
        player_name = opportunity.get('player_name', '')
        if player_name and player_name not in ['N/D', 'Nome da verificare', '']:
            score += 25

        # Ha info sul club
        if opportunity.get('current_club') or opportunity.get('previous_clubs'):
            score += 20

        # Ha eta
        if opportunity.get('age'):
            score += 20

        # Ha ruolo
        if opportunity.get('role') or opportunity.get('role_name'):
            score += 15

        # Ha summary/descrizione
        if opportunity.get('summary') and len(opportunity.get('summary', '')) > 20:
            score += 10

        # Ha URL fonte
        if opportunity.get('source_url'):
            score += 10

        return min(100, score)

    def _calc_market_value(self, market_value: Optional[int]) -> int:
        """Score basato sul valore di mercato (indicatore qualita giocatore)"""
        if not market_value or market_value <= 0:
            return 40  # Valore sconosciuto, penalita leggera

        if market_value >= 500000:
            return 100  # Qualita Serie B/alta Serie C
        elif market_value >= 250000:
            return 90   # Top Serie C
        elif market_value >= 150000:
            return 80   # Buon Serie C
        elif market_value >= 100000:
            return 70   # Serie C medio
        elif market_value >= 50000:
            return 55   # Basso Serie C / Serie D alto
        else:
            return 35   # Dilettanti

    def _calc_league_fit(self, opportunity: Dict[str, Any]) -> int:
        """Score basato sulla rilevanza per Serie C"""
        source_url = (opportunity.get('source_url', '') or '').lower()
        current_club = (opportunity.get('current_club', '') or '').lower()
        previous_clubs = [c.lower() for c in (opportunity.get('previous_clubs', []) or [])]
        summary = (opportunity.get('summary', '') or '').lower()
        all_text = summary + ' ' + current_club + ' ' + ' '.join(previous_clubs)

        score = 50  # Base

        # Penalita pesante: fonte da pagina Serie D generica
        if '/serie-d-' in source_url or '/wettbewerb/it4' in source_url:
            score -= 25

        # Penalita: club chiaramente dilettanti/amatoriali
        amateur_keywords = ['maia alta', 'obermais', 'eccellenza', 'promozione', 'juniores']
        if any(kw in all_text for kw in amateur_keywords):
            score -= 15

        # Bonus: club Serie C noto
        for club in self.SERIE_C_CLUBS:
            if club in current_club or any(club in pc for pc in previous_clubs):
                score += 30
                break

        # Bonus: menzioni Serie B/C nel testo
        if any(kw in all_text for kw in ['serie b', 'cadetti', 'serie a']):
            score += 25
        elif any(kw in all_text for kw in ['serie c', 'lega pro']):
            score += 15

        return max(0, min(100, score))


def score_opportunities(opportunities: list) -> list:
    """
    Applica scoring a lista di opportunita

    Args:
        opportunities: Lista di dict con dati opportunita

    Returns:
        Lista con ob1_score e classification aggiunti
    """
    scorer = OB1Scorer()
    scored = []

    for opp in opportunities:
        score_data = scorer.score(opp)
        scored_opp = {**opp, **score_data}
        scored.append(scored_opp)

    # Sort by score descending
    scored.sort(key=lambda x: x['ob1_score'], reverse=True)

    return scored


# =============================================================================
# CLI Test
# =============================================================================

if __name__ == "__main__":
    # Test con dati di esempio
    test_opportunities = [
        {
            'player_name': 'Marco Rossi',
            'age': 25,
            'opportunity_type': 'svincolato',
            'reported_date': datetime.now().strftime('%Y-%m-%d'),
            'source_name': 'TuttoC',
            'current_club': 'Ex Pescara',
            'previous_clubs': ['Pescara', 'Reggiana'],
            'appearances': 80,
            'summary': 'Centrocampista esperto, svincolato dopo esperienza in Serie B',
        },
        {
            'player_name': 'Luca Bianchi',
            'age': 34,
            'opportunity_type': 'mercato',
            'reported_date': '2026-01-20',
            'source_name': 'Blog Sconosciuto',
            'current_club': '',
            'previous_clubs': [],
            'appearances': 10,
            'summary': '',
        },
    ]

    print("=" * 60)
    print("OB1 SCORER - TEST")
    print("=" * 60)

    scored = score_opportunities(test_opportunities)

    for opp in scored:
        emoji = '🔥' if opp['classification'] == 'hot' else '⚡' if opp['classification'] == 'warm' else '❄️'
        print(f"\n{emoji} {opp['player_name']} - Score: {opp['ob1_score']}/100 ({opp['classification'].upper()})")
        print(f"   Breakdown:")
        for key, value in opp['score_breakdown'].items():
            print(f"   - {key}: {value}")
