#!/usr/bin/env python3
"""
OB1 Serie C — INTEL Engine: Minutaggio Lega Pro + Traffic Light FIGC
Trasforma normative complesse in risposte binarie per Direttori Sportivi.

Regolamento Lega Pro 2024/25:
- Coefficienti età per contributo minutaggio giovani
- Bonus vivaio (formati nel settore giovanile del club)
- Soglia minima 271 min/gara, massimo 450 min/gara
- Bonus tesseramento definitivo +30%

Regolamento Liste FIGC:
- Serie B: Lista A (Over) max 18, Lista B (Under) illimitata, Lista C (Bandiera) max 2
- Serie C: Lista Over max 23, Under illimitata (nati dopo 01/01/2002)
"""

from datetime import datetime
from typing import Dict, Any, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════════
# P0 — FINANCIAL ENGINE: Coefficienti Minutaggio Lega Pro
# ═══════════════════════════════════════════════════════════════════════════════

# Coefficienti per anno di nascita (Lega Pro 2024/25)
COEFFICIENTI_ETA = {
    2003: 0.8,
    2004: 1.0,
    2005: 1.2,
    2006: 1.4,  # 2006 e successivi
}

# Bonus vivaio (cresciuto nel settore giovanile del club)
BONUS_VIVAIO = {
    'primi_30_min': 2.0,   # 200% incremento quota primi 30 min
    'successivi': 4.0,     # 400% incremento quota dopo 30 min
}

BONUS_TESSERAMENTO_DEFINITIVO = 0.3  # +30% per tesseramento definitivo

SOGLIA_MINIMA_GARA = 271   # minuti minimi per conteggiare la gara
SOGLIA_MASSIMA_GARA = 450  # minuti massimi conteggiabili per gara (5 tempi supp.)
MAX_MINUTI_GIOCATORE = 90  # massimo per singolo giocatore per gara
MAX_2002_PER_GARA = 2      # massimo 2 giocatori classe 2002 conteggiabili a gara


def get_birth_year(age: Optional[int] = None,
                   birth_date: Optional[str] = None) -> Optional[int]:
    """Ricava anno di nascita da età o data di nascita."""
    if birth_date:
        try:
            return int(birth_date[:4])
        except (ValueError, TypeError):
            pass
    if age:
        return datetime.now().year - age
    return None


def get_coefficiente_eta(birth_year: int) -> float:
    """Restituisce il coefficiente età per l'anno di nascita.

    2006+ → 1.4 (massimo valore)
    2005  → 1.2
    2004  → 1.0
    2003  → 0.8
    ≤2002 → 0.0 (non contribuisce al minutaggio giovani)
    """
    if birth_year >= 2006:
        return COEFFICIENTI_ETA[2006]
    return COEFFICIENTI_ETA.get(birth_year, 0.0)


def calcola_minutaggio_ponderato(
    minuti_effettivi: int,
    birth_year: int,
    is_vivaio: bool = False,
    is_tesseramento_definitivo: bool = False,
) -> Dict[str, Any]:
    """Calcola il minutaggio ponderato per contributo Lega Pro.

    Formula: Mp = Me * C_età * (1 + B_vivaio + B_tesseramento)

    Args:
        minuti_effettivi: Minuti giocati nella gara (max 90 per giocatore)
        birth_year: Anno di nascita del giocatore
        is_vivaio: Se cresciuto nel vivaio del club
        is_tesseramento_definitivo: Se ha tesseramento definitivo (non prestito)

    Returns:
        Dict con dettaglio del calcolo
    """
    # Cap minuti a 90 per giocatore
    minuti_cap = min(minuti_effettivi, MAX_MINUTI_GIOCATORE)

    # Coefficiente età
    coeff_eta = get_coefficiente_eta(birth_year)

    if coeff_eta == 0.0:
        return {
            'minuti_effettivi': minuti_effettivi,
            'minuti_cap': minuti_cap,
            'birth_year': birth_year,
            'coefficiente_eta': 0.0,
            'bonus_vivaio': 0.0,
            'bonus_tesseramento': 0.0,
            'minutaggio_ponderato': 0.0,
            'contribuisce': False,
            'motivo': f'Classe {birth_year}: troppo vecchio per coefficiente giovani',
        }

    # Bonus vivaio
    bonus_vivaio = 0.0
    if is_vivaio:
        if minuti_cap <= 30:
            bonus_vivaio = BONUS_VIVAIO['primi_30_min']
        else:
            bonus_vivaio = BONUS_VIVAIO['successivi']

    # Bonus tesseramento definitivo
    bonus_tess = BONUS_TESSERAMENTO_DEFINITIVO if is_tesseramento_definitivo else 0.0

    # Formula ponderata
    moltiplicatore = coeff_eta * (1 + bonus_vivaio + bonus_tess)
    minutaggio_ponderato = round(minuti_cap * moltiplicatore, 1)

    return {
        'minuti_effettivi': minuti_effettivi,
        'minuti_cap': minuti_cap,
        'birth_year': birth_year,
        'coefficiente_eta': coeff_eta,
        'bonus_vivaio': bonus_vivaio,
        'bonus_tesseramento': bonus_tess,
        'moltiplicatore_totale': round(moltiplicatore, 2),
        'minutaggio_ponderato': minutaggio_ponderato,
        'contribuisce': True,
    }


def calcola_roi_potenziale(player: Dict[str, Any]) -> Dict[str, Any]:
    """Calcola il ROI potenziale di un giocatore per il minutaggio Lega Pro.

    Proietta il valore su una stagione tipo (38 giornate, ~30 presenze medie).
    Confronta: 45 min di un vivaio 2004 valgono più di 90 min di un prestito 2001.

    Args:
        player: Dizionario con dati giocatore (age, opportunity_type, etc.)

    Returns:
        Dict con analisi ROI completa
    """
    age = player.get('age')
    birth_year = get_birth_year(
        age=age,
        birth_date=player.get('birth_date') or player.get('contract_expires'),
    )

    if not birth_year:
        return {
            'roi_class': 'unknown',
            'roi_label': 'N/D',
            'roi_color': 'gray',
            'coefficiente_eta': 0,
            'moltiplicatore_90min': 0,
            'proiezione_stagionale': 0,
            'dettaglio': 'Età non disponibile',
        }

    coeff = get_coefficiente_eta(birth_year)

    if coeff == 0.0:
        return {
            'roi_class': 'none',
            'roi_label': 'NO CONTRIB.',
            'roi_color': 'gray',
            'birth_year': birth_year,
            'coefficiente_eta': 0,
            'moltiplicatore_90min': 0,
            'proiezione_stagionale': 0,
            'dettaglio': f'Classe {birth_year} — non contribuisce al minutaggio giovani',
        }

    # Determina se vivaio/prestito
    opp_type = (player.get('opportunity_type', '') or '').lower()
    is_prestito = opp_type == 'prestito'
    is_tesseramento_def = opp_type in ('svincolato', 'rescissione', 'mercato')

    # Scenario 90 minuti (gara tipo)
    calc_90 = calcola_minutaggio_ponderato(
        minuti_effettivi=90,
        birth_year=birth_year,
        is_vivaio=False,
        is_tesseramento_definitivo=is_tesseramento_def,
    )

    # Scenario vivaio (bonus massimo)
    calc_vivaio = calcola_minutaggio_ponderato(
        minuti_effettivi=90,
        birth_year=birth_year,
        is_vivaio=True,
        is_tesseramento_definitivo=is_tesseramento_def,
    )

    # Proiezione stagionale (stima 30 presenze da ~70 min medi)
    appearances = player.get('appearances', 0) or 0
    presenze_stima = min(appearances, 30) if appearances > 0 else 25
    minuti_medi = 70

    calc_stagione = calcola_minutaggio_ponderato(
        minuti_effettivi=minuti_medi,
        birth_year=birth_year,
        is_vivaio=False,
        is_tesseramento_definitivo=is_tesseramento_def,
    )
    proiezione = round(calc_stagione['minutaggio_ponderato'] * presenze_stima, 0)

    # Classificazione ROI
    molt = calc_90['moltiplicatore_totale']
    if molt >= 5.0:
        roi_class = 'elite'
        roi_label = 'ASSET ELITE'
        roi_color = '#00ff41'
    elif molt >= 2.5:
        roi_class = 'high'
        roi_label = 'ALTO ROI'
        roi_color = '#fbbf24'
    elif molt >= 1.5:
        roi_class = 'medium'
        roi_label = 'ROI MEDIO'
        roi_color = '#3b82f6'
    elif molt >= 0.8:
        roi_class = 'low'
        roi_label = 'ROI BASSO'
        roi_color = '#94a3b8'
    else:
        roi_class = 'minimal'
        roi_label = 'MINIMO'
        roi_color = '#64748b'

    # Dettaglio testuale
    dettaglio_parts = [f'Classe {birth_year} (x{coeff})']
    if is_tesseramento_def:
        dettaglio_parts.append('tess. definitivo (+30%)')
    if is_prestito:
        dettaglio_parts.append('prestito (no bonus tess.)')
    dettaglio_parts.append(f'molt. x{molt}')
    dettaglio_parts.append(f'proiez. stagione: {int(proiezione)} min pond.')

    return {
        'roi_class': roi_class,
        'roi_label': roi_label,
        'roi_color': roi_color,
        'birth_year': birth_year,
        'coefficiente_eta': coeff,
        'moltiplicatore_90min': molt,
        'moltiplicatore_vivaio': calc_vivaio['moltiplicatore_totale'],
        'proiezione_stagionale': int(proiezione),
        'presenze_stimate': presenze_stima,
        'is_prestito': is_prestito,
        'is_tesseramento_definitivo': is_tesseramento_def,
        'dettaglio': ' | '.join(dettaglio_parts),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# P1 — TRAFFIC LIGHT: Verifica conformità liste FIGC
# ═══════════════════════════════════════════════════════════════════════════════

# Limiti liste per lega
LIMITI_LISTE = {
    'serie_b': {
        'lista_a_over': {'limit': 18, 'cutoff_year': 1999, 'label': 'Lista A (Over)'},
        'lista_b_under': {'limit': None, 'cutoff_year': 1999, 'label': 'Lista B (Under)'},
        'lista_c_bandiera': {'limit': 2, 'min_years': 4, 'label': 'Lista C (Bandiera)'},
    },
    'serie_c': {
        'lista_over': {'limit': 23, 'cutoff_year': 2002, 'label': 'Lista Over'},
        'lista_under': {'limit': None, 'cutoff_year': 2002, 'label': 'Lista Under'},
    },
}


def check_lista_figc(
    player: Dict[str, Any],
    league: str = 'serie_c',
    current_over_count: int = 0,
) -> Dict[str, Any]:
    """Verifica lo status di un giocatore rispetto alle liste FIGC.

    Restituisce un semaforo:
    - VERDE: il giocatore è Under, non occupa slot
    - GIALLO: è Over ma c'è ancora spazio nella lista
    - ROSSO: è Over e la lista è piena/quasi piena

    Args:
        player: Dati giocatore
        league: 'serie_b' o 'serie_c'
        current_over_count: Numero attuale di Over in rosa

    Returns:
        Dict con semaforo e dettaglio
    """
    limiti = LIMITI_LISTE.get(league, LIMITI_LISTE['serie_c'])

    age = player.get('age')
    birth_year = get_birth_year(
        age=age,
        birth_date=player.get('birth_date'),
    )

    if not birth_year:
        return {
            'traffic_light': 'gray',
            'traffic_label': '?',
            'traffic_icon': '⚪',
            'is_over': None,
            'slots_remaining': None,
            'dettaglio': 'Età non disponibile — impossibile classificare',
        }

    # Determina cutoff year per la lega
    if league == 'serie_b':
        cutoff = limiti['lista_a_over']['cutoff_year']
        over_limit = limiti['lista_a_over']['limit']
        lista_label = limiti['lista_a_over']['label']
    else:
        cutoff = limiti['lista_over']['cutoff_year']
        over_limit = limiti['lista_over']['limit']
        lista_label = limiti['lista_over']['label']

    is_over = birth_year < cutoff

    if not is_over:
        # VERDE — Under, non occupa slot
        return {
            'traffic_light': 'green',
            'traffic_label': 'UNDER',
            'traffic_icon': '🟢',
            'is_over': False,
            'birth_year': birth_year,
            'slots_remaining': None,
            'lista': f'Lista Under (classe {birth_year})',
            'dettaglio': f'Non occupa slot Over — classe {birth_year} (cutoff: {cutoff})',
        }

    # Over — verifica capienza
    slots_remaining = over_limit - current_over_count if over_limit else None

    if slots_remaining is not None and slots_remaining <= 0:
        # ROSSO — Lista piena
        return {
            'traffic_light': 'red',
            'traffic_label': 'LISTA PIENA',
            'traffic_icon': '🔴',
            'is_over': True,
            'birth_year': birth_year,
            'slots_remaining': 0,
            'lista': f'{lista_label} ({current_over_count}/{over_limit})',
            'dettaglio': f'ALERT: {lista_label} piena ({current_over_count}/{over_limit}). '
                        f'Acquisto classe {birth_year} richiede uscita di un Over.',
        }

    if slots_remaining is not None and slots_remaining <= 2:
        # GIALLO — Quasi piena
        return {
            'traffic_light': 'yellow',
            'traffic_label': f'{slots_remaining} SLOT',
            'traffic_icon': '🟡',
            'is_over': True,
            'birth_year': birth_year,
            'slots_remaining': slots_remaining,
            'lista': f'{lista_label} ({current_over_count}/{over_limit})',
            'dettaglio': f'Attenzione: solo {slots_remaining} slot Over rimasti '
                        f'({current_over_count}/{over_limit}). Valutare priorità.',
        }

    # VERDE — Over ma c'è spazio
    return {
        'traffic_light': 'green',
        'traffic_label': 'OK',
        'traffic_icon': '🟢',
        'is_over': True,
        'birth_year': birth_year,
        'slots_remaining': slots_remaining,
        'lista': f'{lista_label} ({current_over_count}/{over_limit})',
        'dettaglio': f'Over classe {birth_year} — {slots_remaining} slot disponibili '
                    f'({current_over_count}/{over_limit})',
    }


# ═══════════════════════════════════════════════════════════════════════════════
# INTEL BADGE — Sintesi per dashboard (combinazione P0 + P1)
# ═══════════════════════════════════════════════════════════════════════════════

# Soglia safe margin: puntare a 300 min per coprire imprevisti
SAFE_MARGIN_MINUTES = 300

# Soglie presenze per primo contratto professionistico (Art. 99-bis)
SOGLIA_APPRENDISTATO = {
    'serie_b': 12,
    'serie_c': 15,
}


def check_contract_signals(player: Dict[str, Any], league: str = 'serie_c') -> Dict[str, Any]:
    """Genera segnali contestuali su contratto e normativa.

    - Scadenza contratto (da TM data)
    - Soglia apprendistato (12 presenze Serie B, 15 Serie C)
    - Safe margin minutaggio
    """
    signals = []

    # ── Scadenza contratto ──
    contract_expires = player.get('contract_expires', '')
    if contract_expires:
        try:
            exp_date = datetime.strptime(contract_expires[:10], '%Y-%m-%d')
            days_left = (exp_date - datetime.now()).days
            if days_left < 0:
                signals.append({
                    'type': 'contract_expired',
                    'severity': 'red',
                    'label': 'SCADUTO',
                    'detail': f'Contratto scaduto ({contract_expires[:10]})',
                })
            elif days_left <= 180:
                signals.append({
                    'type': 'contract_expiry',
                    'severity': 'red',
                    'label': f'SCADE {days_left}gg',
                    'detail': f'Contratto in scadenza: {contract_expires[:10]} ({days_left} giorni)',
                })
            elif days_left <= 365:
                signals.append({
                    'type': 'contract_expiry',
                    'severity': 'yellow',
                    'label': f'SCADE {days_left}gg',
                    'detail': f'Contratto: {contract_expires[:10]} ({days_left} giorni)',
                })
        except (ValueError, TypeError):
            pass

    # ── Soglia apprendistato (primo contratto pro) ──
    appearances = player.get('appearances', 0) or 0
    soglia = SOGLIA_APPRENDISTATO.get(league, 15)
    age = player.get('age')

    if age and age <= 21 and appearances > 0:
        remaining = soglia - appearances
        if remaining <= 0:
            signals.append({
                'type': 'apprentice_reached',
                'severity': 'green',
                'label': f'ART.99bis OK',
                'detail': f'{appearances} presenze — soglia {soglia} raggiunta, blindaggio contrattuale possibile',
            })
        elif remaining <= 5:
            signals.append({
                'type': 'apprentice_near',
                'severity': 'yellow',
                'label': f'ART.99bis -{remaining}',
                'detail': f'{appearances}/{soglia} presenze — mancano {remaining} per primo contratto pro',
            })

    return {'signals': signals}


def genera_intel_badge(player: Dict[str, Any], league: str = 'serie_c') -> Dict[str, Any]:
    """Genera un badge sintetico INTEL per la dashboard.

    Combina ROI minutaggio + status lista + segnali contestuali.
    """
    roi = calcola_roi_potenziale(player)
    lista = check_lista_figc(player, league=league)
    ctx = check_contract_signals(player, league=league)

    badge = {
        # ROI Minutaggio
        'roi_class': roi['roi_class'],
        'roi_label': roi['roi_label'],
        'roi_color': roi['roi_color'],
        'coefficiente_eta': roi['coefficiente_eta'],
        'moltiplicatore': roi.get('moltiplicatore_90min', 0),
        'proiezione_stagionale': roi.get('proiezione_stagionale', 0),

        # Lista FIGC
        'traffic_light': lista['traffic_light'],
        'traffic_label': lista['traffic_label'],
        'traffic_icon': lista['traffic_icon'],
        'is_over': lista.get('is_over'),

        # Segnali contestuali (P2)
        'signals': ctx['signals'],

        # Sintesi
        'birth_year': roi.get('birth_year') or lista.get('birth_year'),
        'roi_dettaglio': roi['dettaglio'],
        'lista_dettaglio': lista['dettaglio'],
    }

    return badge
