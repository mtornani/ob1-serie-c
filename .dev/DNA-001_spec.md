# DNA-001: Player-Club DNA Matching System

## Overview

Sistema di matching bidirezionale che connette automaticamente:
- **Giovani talenti** delle squadre B (Milan Futuro, Juve NG, Atalanta U23, ecc.)
- **Club di Serie C** che cercano rinforzi in prestito

**Innovazione chiave:** Nessuno fa questo match automatico. I DS perdono ore al telefono.

## Problem Statement

### Lato Club Serie C
- "Cerco un terzino sinistro under 23, chi è disponibile?"
- Deve chiamare 10 club di Serie A per sapere chi hanno
- Non sa quali giovani si adattano al SUO modulo

### Lato Club Serie A (squadre B)
- Hanno 25+ giovani da piazzare ogni anno
- Vogliono club che li facciano GIOCARE
- Vogliono contesti tattici compatibili

### La soluzione OB1
Match automatico basato su "DNA" del giocatore e del club.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    OB1 DNA MATCHING ENGINE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────┐│
│  │ PLAYER DNA   │         │   MATCHING   │         │ CLUB DNA ││
│  │              │────────▶│   ALGORITHM  │◀────────│          ││
│  │ • Età        │         │              │         │ • Modulo ││
│  │ • Ruolo      │         │  Calcola %   │         │ • Stile  ││
│  │ • Piede      │         │  compatib.   │         │ • Budget ││
│  │ • Skills     │         │              │         │ • Needs  ││
│  │ • Minutaggio │         └──────────────┘         │          ││
│  └──────────────┘                │                 └──────────┘│
│                                  ▼                              │
│                         ┌──────────────┐                        │
│                         │   OUTPUT     │                        │
│                         │              │                        │
│                         │ Top matches  │                        │
│                         │ per club     │                        │
│                         └──────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

## Data Models

### Player DNA

```python
@dataclass
class PlayerDNA:
    # Identità
    id: str
    name: str
    birth_year: int
    nationality: str

    # Posizione
    primary_position: str      # "CC", "DC", "ES", "AT", etc.
    secondary_positions: list  # Posizioni alternative
    preferred_foot: str        # "destro", "sinistro", "ambidestro"

    # Club attuale
    parent_club: str           # "Juventus", "Milan", "Inter"
    current_team: str          # "Juventus Next Gen", "Milan Futuro"
    contract_until: str        # "2027-06-30"

    # Statistiche stagione corrente
    appearances: int
    minutes_played: int
    goals: int
    assists: int

    # Caratteristiche tecniche (1-100)
    skills: dict = {
        "tecnica": 75,
        "velocita": 80,
        "fisico": 70,
        "visione": 65,
        "difesa": 60,
        "pressing": 75,
    }

    # Disponibilità
    transfer_status: str       # "disponibile_prestito", "in_uscita", "incedibile"
    estimated_loan_cost: int   # In migliaia di euro

    # Calcolato
    minutes_percentage: float  # % minuti giocati vs disponibili
    is_underused: bool         # True se < 40% minuti
```

### Club DNA

```python
@dataclass
class ClubDNA:
    # Identità
    id: str
    name: str
    category: str              # "Serie C", "Serie D"
    group: str                 # "A", "B", "C" per Serie C

    # Tattica
    primary_formation: str     # "3-5-2", "4-3-3", "4-2-3-1"
    playing_style: list        # ["pressing_alto", "possesso", "transizioni"]

    # Esigenze attuali
    needs: list[dict] = [
        {
            "position": "CC",
            "type": "box_to_box",
            "age_range": [19, 24],
            "priority": "alta",
        },
        {
            "position": "ES",
            "type": "tutta_fascia",
            "age_range": [20, 26],
            "priority": "media",
        }
    ]

    # Budget
    budget_type: str           # "solo_prestiti", "prestiti_obbligo", "acquisti"
    max_loan_cost: int         # Max costo prestito in migliaia

    # Track record con giovani
    youth_minutes_pct: float   # % minuti a under 23 nella stagione
    youth_development_score: int  # 1-5 stelle, basato su storico

    # Contatti
    ds_name: str
    ds_contact: str            # Solo per utenti premium
```

## Matching Algorithm

### Match Score Calculation

```python
def calculate_match_score(player: PlayerDNA, club: ClubDNA) -> MatchResult:
    score = 0
    breakdown = {}

    # 1. POSITION FIT (30%)
    # Il giocatore copre una posizione richiesta dal club?
    position_score = 0
    for need in club.needs:
        if player.primary_position == need["position"]:
            position_score = 100
            break
        elif need["position"] in player.secondary_positions:
            position_score = 70
            break

    breakdown["position"] = position_score
    score += position_score * 0.30

    # 2. AGE FIT (20%)
    # Il giocatore rientra nella fascia d'età desiderata?
    age = 2026 - player.birth_year
    age_score = 0
    for need in club.needs:
        if need["position"] == player.primary_position:
            min_age, max_age = need["age_range"]
            if min_age <= age <= max_age:
                age_score = 100
            elif age < min_age:
                age_score = max(0, 100 - (min_age - age) * 15)
            else:
                age_score = max(0, 100 - (age - max_age) * 15)
            break

    breakdown["age"] = age_score
    score += age_score * 0.20

    # 3. STYLE FIT (25%)
    # Le caratteristiche del giocatore matchano lo stile del club?
    style_score = calculate_style_match(player.skills, club.playing_style)
    breakdown["style"] = style_score
    score += style_score * 0.25

    # 4. AVAILABILITY (15%)
    # Il giocatore è effettivamente disponibile e underused?
    avail_score = 0
    if player.transfer_status == "disponibile_prestito":
        avail_score = 100
    elif player.transfer_status == "in_uscita":
        avail_score = 80

    if player.is_underused:
        avail_score = min(100, avail_score + 20)

    breakdown["availability"] = avail_score
    score += avail_score * 0.15

    # 5. BUDGET FIT (10%)
    # Il club può permettersi il prestito?
    budget_score = 0
    if player.estimated_loan_cost <= club.max_loan_cost:
        budget_score = 100
    elif player.estimated_loan_cost <= club.max_loan_cost * 1.5:
        budget_score = 50

    breakdown["budget"] = budget_score
    score += budget_score * 0.10

    return MatchResult(
        player=player,
        club=club,
        score=round(score),
        breakdown=breakdown,
        recommendation=generate_recommendation(score, breakdown)
    )

def calculate_style_match(skills: dict, styles: list) -> int:
    """Match skills del giocatore con stile di gioco del club"""

    style_requirements = {
        "pressing_alto": ["pressing", "fisico", "velocita"],
        "possesso": ["tecnica", "visione"],
        "transizioni": ["velocita", "tecnica"],
        "difesa_bassa": ["difesa", "fisico"],
        "gioco_aereo": ["fisico"],
    }

    total = 0
    count = 0

    for style in styles:
        if style in style_requirements:
            for skill in style_requirements[style]:
                if skill in skills:
                    total += skills[skill]
                    count += 1

    return round(total / count) if count > 0 else 50
```

## Data Sources

### Squadre B da monitorare

| Club | Squadra B | Categoria |
|------|-----------|-----------|
| Juventus | Juventus Next Gen | Serie C |
| Milan | Milan Futuro | Serie C |
| Atalanta | Atalanta U23 | Serie C |
| Inter | Inter Primavera* | Primavera 1 |
| Roma | Roma Primavera* | Primavera 1 |
| Napoli | Napoli Primavera* | Primavera 1 |

*Per Inter/Roma/Napoli monitoriamo i giovani che vanno in prestito

### Fonti dati

1. **Transfermarkt** - Rose, valutazioni, statistiche
2. **Sofascore/FBRef** - Statistiche avanzate
3. **News scraping** - Rumors su prestiti disponibili

## Implementation Plan

### Phase 1: Data Collection (3 giorni)

```
src/
├── dna/
│   ├── __init__.py
│   ├── models.py          # PlayerDNA, ClubDNA dataclasses
│   ├── scraper_tm.py      # Scraper Transfermarkt per rose
│   ├── scraper_stats.py   # Scraper statistiche
│   └── enricher.py        # Arricchisce dati da più fonti
```

**Deliverable:** Database di ~100 giocatori dalle squadre B

### Phase 2: Matching Engine (2 giorni)

```
src/
├── dna/
│   ├── matcher.py         # Algoritmo di matching
│   ├── scorer.py          # Calcolo score componenti
│   └── recommender.py     # Generazione raccomandazioni
```

**Deliverable:** API che dato un ClubDNA ritorna top matches

### Phase 3: Club Profiles (2 giorni)

```
data/
├── clubs/
│   ├── pescara.json
│   ├── cesena.json
│   └── ...
```

**Deliverable:** 10 profili club di Serie C pilota

### Phase 4: Integration (2 giorni)

- Dashboard: Sezione "DNA Matches"
- Bot Telegram: Comando /match
- Notifiche: "Nuovo match 90%+ per il tuo profilo"

## Output Examples

### Bot Telegram

```
👤: /match Pescara

🧬 DNA MATCHES per PESCARA

Cercate: CC box-to-box, ES tutta fascia

🔥 TOP MATCH (92%)
━━━━━━━━━━━━━━━━━━━
🎯 Marco Rossi (20, CC)
🏟️ Juventus Next Gen
📊 Solo 890' su 2700 disponibili (33%)
💡 "Box-to-box con ottimo pressing,
    perfetto per il 3-5-2 aggressivo"

⚡ BUON MATCH (84%)
━━━━━━━━━━━━━━━━━━━
🎯 Luca Verdi (21, ES)
🏟️ Milan Futuro
📊 1200' su 2700 (44%)
💡 "Esterno rapido, può coprire
    tutta la fascia"

━━━━━━━━━━━━━━━━━━━
🌐 Dettagli su Dashboard
```

### Dashboard

```
┌─────────────────────────────────────────┐
│  🧬 DNA MATCHING                        │
│                                         │
│  Il tuo profilo: PESCARA                │
│  Modulo: 3-5-2 | Stile: Pressing alto   │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ ESIGENZE ATTUALI                │    │
│  │ • CC Box-to-box (ALTA)          │    │
│  │ • ES Tutta fascia (MEDIA)       │    │
│  │ • DC Impostatore (BASSA)        │    │
│  └─────────────────────────────────┘    │
│                                         │
│  🔥 TOP 5 MATCHES                       │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│  1. M. Rossi (Juve NG) - 92% 🔥        │
│  2. L. Verdi (Milan F) - 84% ⚡        │
│  3. A. Bianchi (Atalanta) - 81% ⚡     │
│  4. ...                                 │
│                                         │
│  [Modifica Profilo] [Vedi Tutti]        │
└─────────────────────────────────────────┘
```

## Business Model Implication

### Free Tier
- Vedi top 3 matches
- Aggiornamento settimanale

### Pro Tier (per club)
- Tutti i matches
- Aggiornamento giornaliero
- Contatti DS squadre B
- Alert su nuovi match 85%+
- Export PDF per presentazioni

## Success Metrics

| Metric | Target |
|--------|--------|
| Giocatori nel database | 150+ |
| Club con profilo | 20+ |
| Match score medio | >70% |
| Prestiti facilitati | 5+ primo anno |

## Acceptance Criteria

- [ ] Scraper Transfermarkt funzionante per rose squadre B
- [ ] Modello PlayerDNA con tutti i campi
- [ ] Modello ClubDNA configurabile
- [ ] Algoritmo matching con score breakdown
- [ ] Integrazione bot: /match [club]
- [ ] Sezione dashboard DNA Matches
- [ ] Almeno 3 club pilota configurati

## Timeline

**Estimate:** 7-10 giorni

```
Giorni 1-3: Data collection + scraping
Giorni 4-5: Matching engine
Giorni 6-7: Club profiles + integration
Giorni 8-10: Testing + refinement
```

---

**Status:** 🚀 READY TO START
**Priority:** HIGH (Game changer feature)
**Created:** 2026-02-01
