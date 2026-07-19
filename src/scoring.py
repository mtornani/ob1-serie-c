#!/usr/bin/env python3
"""
OB1 Serie C - SCORE-001: Advanced Scoring Algorithm
Prioritizza le opportunita di mercato con scoring intelligente
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional


class OB1Scorer:
    """Sistema di scoring avanzato per opportunita di mercato"""

    # SCORE-003: after publish gate, completeness is always high → drop it.
    # Redistribute 5% to type + age (what a DS actually filters on).
    WEIGHTS = {
        'freshness': 0.15,
        'opportunity_type': 0.12,
        'experience': 0.20,
        'age': 0.18,
        'market_value': 0.15,
        'league_fit': 0.15,
        'source': 0.05,
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
        Calcola score per una singola opportunita (SCORE-003).

        Returns:
            Dict con ob1_score, classification, score_breakdown
        """
        opp_type = (opportunity.get('opportunity_type') or 'altro').lower()
        date_str = opportunity.get('reported_date') or opportunity.get('discovered_at', '')

        breakdown = {
            'freshness': self._calc_freshness(date_str, opp_type),
            'opportunity_type': self._calc_type_score(opp_type),
            'experience': self._calc_experience(opportunity),
            'age': self._calc_age(opportunity.get('age')),
            'market_value': self._calc_market_value(opportunity.get('market_value')),
            'league_fit': self._calc_league_fit(opportunity),
            'source': self._calc_source(opportunity.get('source_name', '')),
        }

        total = sum(breakdown[key] * self.WEIGHTS[key] for key in self.WEIGHTS)
        ob1_score = int(round(total))

        # HOT ≥70 / WARM ≥57 / COLD — same dials as SCORE-002
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

    def _calc_freshness(self, date_str: str, opp_type: str = '') -> int:
        """Quanto e' recente la notizia. Svincolati/rescissioni restano utili piu' a lungo."""
        if not date_str:
            return 50

        try:
            if 'T' in date_str:
                date_str = date_str.split('T')[0]

            reported = datetime.strptime(date_str, '%Y-%m-%d').date()
            days_ago = (datetime.now().date() - reported).days
            free = opp_type in ('svincolato', 'rescissione', 'scadenza')

            if days_ago <= 0:
                return 100
            if days_ago == 1:
                return 95
            if days_ago <= 3:
                return 85
            if days_ago <= 7:
                return 70
            if days_ago <= 14:
                return 60
            if days_ago <= 30:
                return 50 if free else 45
            # Old news: free agents still available → floor 55; rumors die hard
            if free:
                return 55
            return 25

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
        """Score basato sull'eta del giocatore — target U23 per FIGC minutaggio"""
        if not age:
            return 60  # Neutro se non conosciamo l'eta

        # U23 è il target principale: FIGC minutaggio rende i giovani extra-preziosi
        if 18 <= age <= 22:
            return 100  # Fascia U23 — massimo valore FIGC
        elif 23 <= age <= 26:
            return 90   # Ancora giovane, ottimo profilo
        elif 27 <= age <= 29:
            return 75   # Prime anni, esperienza senza U23 bonus
        elif age < 18:
            return 60   # Troppo giovane per continuità Serie C
        elif 30 <= age <= 32:
            return 45   # Esperienza ma nessun contributo minutaggio U23
        else:
            return 25   # Fuori target

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


def assess_follow(opportunity: Dict[str, Any], score_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perché sì / perché no — solo CODICE dagli stessi segnali dello score.
    Zero LLM, zero costi, non può contraddire ob1_score.
    """
    yes, no = [], []
    bd = score_result.get("score_breakdown") or {}
    t = (opportunity.get("opportunity_type") or "").lower()
    age = opportunity.get("age")
    apps = opportunity.get("appearances") or 0
    goals = opportunity.get("goals") or 0
    assists = opportunity.get("assists") or 0
    mv = opportunity.get("market_value") or 0
    club = (opportunity.get("current_club") or "").strip()
    flags = {
        f for f in (opportunity.get("review_flags") or "").split(",") if f
    }
    n_src = opportunity.get("n_sources") or 1
    dwc = opportunity.get("days_without_contract") or 0
    score = score_result.get("ob1_score") or 0

    # --- Perché sì ---
    if t == "svincolato":
        yes.append("Libero a zero — nessun costo di cartellino")
    elif t == "rescissione":
        yes.append("Ha rescisso — in uscita, trattativa possibile")
    elif t == "prestito":
        yes.append("Disponibile in prestito — investimento contenuto")
    elif t == "scadenza":
        yes.append("Contratto in scadenza — finestra per muoversi")

    if age is not None and age <= 22:
        yes.append(f"Giovane ({age} anni) — non occupa posto Over in lista")
    elif age is not None and 23 <= age <= 26:
        yes.append(f"{age} anni — nel pieno della carriera")

    if apps >= 20:
        bit = f"{apps} presenze"
        if goals:
            bit += f", {goals} gol"
        if assists:
            bit += f", {assists} assist"
        yes.append(bit)
    elif goals or assists:
        parts = []
        if goals:
            parts.append(f"{goals} gol")
        if assists:
            parts.append(f"{assists} assist")
        yes.append(" · ".join(parts))

    if mv and mv >= 150_000:
        fmt = opportunity.get("market_value_formatted")
        yes.append(f"Valore di mercato interessante{f' ({fmt})' if fmt else ''}")

    if (bd.get("league_fit") or 0) >= 80:
        yes.append("Profilo in fascia Lega Pro")
    if (bd.get("freshness") or 0) >= 70:
        yes.append("Segnalazione fresca")
    if (bd.get("source") or 0) >= 85:
        yes.append("Fonte specializzata")
    if opportunity.get("corroborated") or n_src >= 2:
        yes.append("Confermato da più fonti / profilo TM")

    # --- Perché no / cautele ---
    if not apps:
        no.append("Presenze non verificate — controllare Transfermarkt")
    if age is not None and age >= 30:
        no.append(f"{age} anni — poco margine, nessun bonus lista giovani")
    if age is not None and age < 18:
        no.append("Molto giovane — continuità in C da verificare")
    if t == "mercato" and (bd.get("opportunity_type") or 0) <= 50:
        no.append("Solo voce di mercato — non è libero")
    if (bd.get("freshness") or 50) <= 30 and t not in (
        "svincolato",
        "rescissione",
        "scadenza",
    ):
        no.append("Notizia datata — disponibilità da ricontrollare")
    if t in ("svincolato", "rescissione") and dwc > 60:
        no.append(f"{dwc} giorni senza club — perché non è stato preso?")
    if opportunity.get("stale_free_agent"):
        no.append("Svincolato da tempo con esperienza — attenzione al profilo")
    if (bd.get("league_fit") or 50) < 45:
        no.append("Fascia categoria dubbia (forse sotto/sopra la C)")
    if (bd.get("market_value") or 50) <= 40 and not mv:
        no.append("Valore di mercato assente o molto basso")
    if "fonte_singola" in flags and not opportunity.get("corroborated"):
        no.append("Una sola fonte — da corroborare")
    if (bd.get("source") or 50) < 55:
        no.append("Fonte debole o generica")
    if club.lower() in ("", "n/d", "senza club") and t not in (
        "svincolato",
        "rescissione",
    ):
        no.append("Club attuale non chiaro")

    # Action from score (same dials as scorer)
    if score >= 70:
        action = "Da chiamare ora"
    elif score >= 57:
        action = "Da tenere d'occhio"
    else:
        action = "Bassa priorità"

    # Dedupe while preserving order
    def _uniq(xs):
        seen = set()
        out = []
        for x in xs:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return {
        "yes": _uniq(yes)[:4],
        "no": _uniq(no)[:4],
        "action": action,
    }


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
