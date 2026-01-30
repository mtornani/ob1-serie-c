# SCORE-001: OB1 Score Algorithm

## Overview

Sistema di scoring intelligente per prioritizzare le opportunita di mercato.
Ogni opportunita riceve un punteggio 1-100 basato su criteri oggettivi.

## Problem Statement

Attualmente tutte le opportunita hanno lo stesso peso:
- Un centrocampista 35enne svincolato
- Un talento 22enne in rescissione

Per un DS, la seconda e' MOLTO piu interessante della prima.
Serve un sistema che prioritizzi automaticamente.

## Solution

### Score Components

```python
OB1_SCORE = (
    freshness_score    × 20% +   # Quanto e' recente la notizia
    opportunity_type   × 20% +   # Svincolato > Prestito > Rumors
    experience_score   × 20% +   # Presenze in categoria
    age_score          × 20% +   # Eta ottimale 22-28
    source_reliability × 10% +   # Gazzetta > blog random
    completeness       × 10%     # Quanti dati abbiamo
)
```

### Freshness Score (0-100)

```python
def calc_freshness(reported_date: str) -> int:
    days_ago = (today - reported_date).days

    if days_ago == 0:
        return 100  # Oggi
    elif days_ago == 1:
        return 90   # Ieri
    elif days_ago <= 3:
        return 70   # Ultimi 3 giorni
    elif days_ago <= 7:
        return 50   # Ultima settimana
    else:
        return 30   # Piu vecchio
```

### Opportunity Type Score (0-100)

```python
TYPE_SCORES = {
    OpportunityType.SVINCOLATO: 100,     # Disponibile subito
    OpportunityType.RESCISSIONE: 95,     # Imminente disponibilita
    OpportunityType.PRESTITO: 70,        # Trattativa necessaria
    OpportunityType.SERIE_D_TALENT: 60,  # Potenziale
    OpportunityType.PERFORMANCE: 40,     # Solo segnalazione
    OpportunityType.INFORTUNIO: 30,      # Opportunita indiretta
}
```

### Experience Score (0-100)

```python
def calc_experience(appearances: int, category: str) -> int:
    if category == "Serie B":
        base = 80  # Esperienza superiore
    elif category == "Serie C":
        base = 60
    else:
        base = 40  # Serie D o inferiore

    # Bonus per presenze
    if appearances >= 100:
        return min(100, base + 30)
    elif appearances >= 50:
        return min(100, base + 20)
    elif appearances >= 20:
        return min(100, base + 10)
    else:
        return base
```

### Age Score (0-100)

```python
def calc_age_score(age: int) -> int:
    # Fascia ottimale: 22-28
    if 22 <= age <= 28:
        return 100
    elif 20 <= age < 22:
        return 85   # Giovane promettente
    elif 28 < age <= 30:
        return 75   # Ancora valido
    elif 18 <= age < 20:
        return 60   # Troppo giovane
    elif 30 < age <= 32:
        return 50   # Esperienza ma calo
    else:
        return 30   # Fuori target
```

### Source Reliability (0-100)

```python
SOURCE_SCORES = {
    "Gazzetta": 95,
    "Corriere dello Sport": 90,
    "Tuttosport": 90,
    "TuttoC": 95,        # Specializzato Serie C
    "Calciomercato": 85,
    "TMW": 80,
    "Football Italia": 75,
    "TuttoCampo": 70,
    "unknown": 50,
}
```

### Completeness Score (0-100)

```python
def calc_completeness(opportunity: MarketOpportunity) -> int:
    score = 0

    if opportunity.player_name != "Nome da verificare":
        score += 25
    if opportunity.clubs_involved:
        score += 20
    if opportunity.player_profile:
        score += 30
        if opportunity.player_profile.birth_year:
            score += 10
        if opportunity.player_profile.role:
            score += 15

    return min(100, score)
```

## Implementation

### File: `src/scoring.py`

```python
from dataclasses import dataclass
from typing import Optional
from models import MarketOpportunity, OpportunityType

@dataclass
class ScoredOpportunity:
    opportunity: MarketOpportunity
    ob1_score: int
    score_breakdown: dict
    classification: str  # HOT, WARM, COLD

    @property
    def is_hot(self) -> bool:
        return self.ob1_score >= 80

    @property
    def is_warm(self) -> bool:
        return 60 <= self.ob1_score < 80

class OB1Scorer:
    def score(self, opp: MarketOpportunity) -> ScoredOpportunity:
        # Calculate components
        breakdown = {
            "freshness": self._calc_freshness(opp.reported_date),
            "opp_type": self._calc_type_score(opp.opportunity_type),
            "experience": self._calc_experience(opp),
            "age": self._calc_age(opp),
            "source": self._calc_source(opp.source_name),
            "completeness": self._calc_completeness(opp)
        }

        # Weighted sum
        total = (
            breakdown["freshness"] * 0.20 +
            breakdown["opp_type"] * 0.20 +
            breakdown["experience"] * 0.20 +
            breakdown["age"] * 0.20 +
            breakdown["source"] * 0.10 +
            breakdown["completeness"] * 0.10
        )

        ob1_score = int(total)

        # Classification
        if ob1_score >= 80:
            classification = "HOT"
        elif ob1_score >= 60:
            classification = "WARM"
        else:
            classification = "COLD"

        return ScoredOpportunity(
            opportunity=opp,
            ob1_score=ob1_score,
            score_breakdown=breakdown,
            classification=classification
        )
```

### Integration Points

1. **scraper.py**: Dopo `scrape_all()`, passa a `OB1Scorer`
2. **notifier.py**: Usa score per filtrare/ordinare
3. **agent.py**: Include score nelle risposte
4. **dashboard**: Mostra score visivamente

## UI/UX

### Score Badge

```
🔥 87  = HOT (rosso)
⚡ 72  = WARM (arancione)
❄️ 45  = COLD (grigio)
```

### In Telegram

```
🔥 SCORE: 87/100 (HOT)
├─ Freshness: 100 (oggi)
├─ Tipo: 95 (rescissione)
├─ Esperienza: 80 (Serie B)
├─ Eta: 100 (25 anni)
├─ Fonte: 95 (TuttoC)
└─ Dati: 70
```

## Testing

```python
def test_score_svincolato_giovane():
    opp = MarketOpportunity(
        opportunity_type=OpportunityType.SVINCOLATO,
        player_name="Marco Rossi",
        reported_date="2026-01-30",  # oggi
        source_name="TuttoC",
        player_profile=PlayerProfile(birth_year=2001)  # 25 anni
    )

    scored = OB1Scorer().score(opp)

    assert scored.ob1_score >= 80  # Dovrebbe essere HOT
    assert scored.classification == "HOT"
```

## Acceptance Criteria

- [ ] Ogni opportunita ha un score 1-100
- [ ] Score breakdown disponibile
- [ ] Classificazione HOT/WARM/COLD
- [ ] Integrato in scraper pipeline
- [ ] Visualizzato in notifiche Telegram
- [ ] Test copertura >80%

## Dependencies

- models.py (MarketOpportunity, PlayerProfile)
- datetime per calcolo freshness

## Estimate

**2-3 giorni**
- Day 1: Core scoring logic + tests
- Day 2: Integration in scraper/notifier
- Day 3: Dashboard visualization + polish

---

**Status:** READY FOR IMPLEMENTATION
**Assigned:** TBD
**Created:** 2026-01-30
