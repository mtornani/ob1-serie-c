#!/usr/bin/env python3
"""
OB1 Scout — Backtest Scorer
Applica lo scorer a 8 fattori ai dati storici Serie C 2022/2023 raccolti da FBref.
Poi arricchisce i top 20 con dati attuali via enricher_tm (Tavily + Gemini).

Pipeline: LOAD → ADAPT → SCORE → RANK → ENRICH → CLASSIFY → OUTPUT

Input:  data/backtest/serie_c_2022_2023_raw.json
Output: data/backtest/backtest_results.json
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# ── Setup paths ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scoring import OB1Scorer
from enricher_tm import TransfermarktEnricher

DATA_DIR = PROJECT_ROOT / "data" / "backtest"

# ── Logging ──
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backtest_score")

# ── Configurazione ──
FREEZE_DATE = "2023-06-30"
TOP_N = 20
ENRICHMENT_DELAY = 5  # secondi tra richieste enrichment (Tavily rate limit)


def load_raw_data() -> List[Dict]:
    """Carica i dati grezzi raccolti dal collector"""
    raw_path = DATA_DIR / "serie_c_2022_2023_raw.json"

    if not raw_path.exists():
        logger.error(f"[FAIL] File non trovato: {raw_path}")
        logger.info("Esegui prima: python scripts/backtest_collector.py")
        return []

    with open(raw_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    players = data.get("players", [])
    logger.info(f"[LOAD] {len(players)} giocatori caricati da {raw_path}")
    return players


def adapt_for_scorer(player: Dict) -> Dict:
    """
    Adatta un record FBref al formato atteso dallo scorer OB1.
    Lo scorer si aspetta campi come 'player_name', 'age', 'appearances', etc.
    """
    stats = player.get("stats", {})

    # Mappa posizione FBref → ruolo OB1
    position = player.get("position", "")
    role = _map_position(position)

    # Stima valore di mercato basato su statistiche (non disponibile su FBref)
    estimated_value = _estimate_market_value(player)

    return {
        "player_name": player["name"],
        "age": player.get("age_2023"),
        "role": role,
        "role_name": position,
        "opportunity_type": "mercato",  # Per backtest, tutti sono "mercato"
        "reported_date": FREEZE_DATE,  # Data congelata
        "source_name": "FBref",
        "source_url": player.get("fbref_url", ""),
        "current_club": player.get("team_2023", ""),
        "previous_clubs": [],  # Non disponibile da FBref single-season
        "appearances": stats.get("games", 0),
        "goals": stats.get("goals", 0),
        "assists": stats.get("assists", 0),
        "summary": _build_summary(player),
        "nationality": player.get("nationality", ""),
        "market_value": estimated_value,
        # Metriche extra per il backtest
        "_raw_stats": stats,
        "_fbref_url": player.get("fbref_url", ""),
    }


def _map_position(fbref_pos: str) -> str:
    """Mappa posizioni FBref ai ruoli OB1"""
    pos_upper = fbref_pos.upper() if fbref_pos else ""

    mapping = {
        "GK": "GK",
        "DF": "CB", "DF,MF": "CB", "DF,FW": "CB",
        "MF": "CM", "MF,DF": "CDM", "MF,FW": "CAM",
        "FW": "ST", "FW,MF": "CF", "FW,DF": "ST",
    }

    return mapping.get(pos_upper, pos_upper or "CM")


def _estimate_market_value(player: Dict) -> int:
    """
    Stima il valore di mercato Serie C basato su eta e statistiche.
    Usato come proxy dato che FBref non ha valori di mercato.
    """
    stats = player.get("stats", {})
    age = player.get("age_2023") or 25
    games = stats.get("games") or 0
    goals = stats.get("goals") or 0
    assists = stats.get("assists") or 0
    minutes = stats.get("minutes") or 0

    # Valore base per Serie C: 50k-250k EUR
    base = 100000

    # Bonus per produttivita
    if goals >= 10:
        base += 100000
    elif goals >= 5:
        base += 50000

    if assists >= 5:
        base += 30000

    # Bonus per minuti giocati (titolarita)
    if minutes >= 2500:
        base += 50000
    elif minutes >= 1500:
        base += 25000

    # Moltiplicatore eta (giovani valgono di piu)
    if age <= 21:
        base = int(base * 1.5)
    elif age <= 24:
        base = int(base * 1.2)
    elif age >= 30:
        base = int(base * 0.6)

    return base


def _build_summary(player: Dict) -> str:
    """Costruisce un summary testuale per il giocatore"""
    stats = player.get("stats", {})
    parts = []

    pos = player.get("position", "")
    team = player.get("team_2023", "")
    if pos:
        parts.append(f"Ruolo: {pos}")
    if team:
        parts.append(f"Club: {team}")

    games = stats.get("games")
    goals = stats.get("goals")
    assists = stats.get("assists")

    if games:
        parts.append(f"{games} presenze")
    if goals:
        parts.append(f"{goals} gol")
    if assists:
        parts.append(f"{assists} assist")

    xg = stats.get("xg")
    if xg is not None:
        parts.append(f"xG: {xg}")

    return " | ".join(parts) if parts else "Serie C 2022-2023"


def score_all(players: List[Dict]) -> List[Dict]:
    """Applica lo scorer OB1 a 8 fattori a tutti i giocatori"""
    scorer = OB1Scorer()
    scored = []

    for player_raw in players:
        adapted = adapt_for_scorer(player_raw)

        # Override freshness = 100 per backtest (simuliamo dati freschi al 30/06/2023)
        score_result = scorer.score(adapted)
        breakdown = score_result["score_breakdown"]

        # Forza freshness a 100 per il backtest
        old_freshness = breakdown["freshness"]
        breakdown["freshness"] = 100

        # Ricalcola score totale con freshness = 100
        total = sum(
            breakdown[key] * scorer.WEIGHTS[key]
            for key in scorer.WEIGHTS
        )
        score_result["ob1_score"] = int(round(total))

        # Riclassifica
        if score_result["ob1_score"] >= 70:
            score_result["classification"] = "hot"
        elif score_result["ob1_score"] >= 57:
            score_result["classification"] = "warm"
        else:
            score_result["classification"] = "cold"

        # Merge
        result = {**adapted, **score_result}
        result["_original"] = player_raw  # Conserva dati originali FBref
        scored.append(result)

    # Ordina per score decrescente
    scored.sort(key=lambda x: x["ob1_score"], reverse=True)

    logger.info(f"[SCORE] {len(scored)} giocatori scorati")
    hot = sum(1 for s in scored if s["classification"] == "hot")
    warm = sum(1 for s in scored if s["classification"] == "warm")
    cold = sum(1 for s in scored if s["classification"] == "cold")
    logger.info(f"  HOT: {hot} | WARM: {warm} | COLD: {cold}")

    return scored


def enrich_top_n(scored: List[Dict], n: int = TOP_N) -> List[Dict]:
    """Arricchisce i top N giocatori con dati attuali via Tavily + Gemini"""
    top = scored[:n]

    try:
        enricher = TransfermarktEnricher()
    except ValueError as e:
        logger.warning(f"[WARN] Enricher non disponibile: {e}")
        logger.info("  → I risultati saranno senza dati attuali. Aggiungi TAVILY_API_KEY e GEMINI_API_KEY.")
        for p in top:
            p["club_now"] = None
            p["league_now"] = None
            p["market_value_now"] = None
        return top

    logger.info(f"\n[ENRICH] Arricchisco top {n} giocatori con dati attuali...")

    for i, player in enumerate(top):
        name = player["player_name"]
        logger.info(f"  [{i+1}/{n}] {name}...")

        try:
            time.sleep(ENRICHMENT_DELAY)
            profile = enricher.search_player_profile(name)

            if profile:
                player["club_now"] = profile.get("current_club")
                player["league_now"] = profile.get("league") or profile.get("competition")
                player["market_value_now"] = _parse_market_value(profile.get("market_value"))
                player["nationality_enriched"] = profile.get("nationality") or profile.get("citizenship")
                player["age_now"] = profile.get("age")
                logger.info(f"    → {player['club_now']} | {player['league_now']} | {player['market_value_now']}")
            else:
                logger.info(f"    → Profilo non trovato")
                player["club_now"] = None
                player["league_now"] = None
                player["market_value_now"] = None

        except Exception as e:
            logger.warning(f"    → Errore enrichment: {e}")
            player["club_now"] = None
            player["league_now"] = None
            player["market_value_now"] = None

    return top


def _parse_market_value(value_str: Optional[str]) -> Optional[int]:
    """Parsa valore di mercato da stringa (es. '€4.00m', '€500k') a int"""
    if not value_str:
        return None

    import re
    # Rimuovi simboli valuta
    clean = value_str.replace("€", "").replace("$", "").replace("£", "").strip().lower()

    match = re.match(r"([\d.]+)\s*(m|mln|mil|k|thousand)?", clean)
    if not match:
        return None

    num = float(match.group(1))
    unit = match.group(2) or ""

    if unit in ("m", "mln", "mil"):
        return int(num * 1_000_000)
    elif unit in ("k", "thousand"):
        return int(num * 1_000)
    else:
        return int(num) if num > 1000 else int(num * 1_000_000)  # FBref default assume milioni


def classify_results(top_players: List[Dict]) -> List[Dict]:
    """Classifica ogni giocatore come hit/miss/lateral"""
    for p in top_players:
        mv_2023 = p.get("market_value") or 100000  # stima 2023
        mv_now = p.get("market_value_now")
        league_now = (p.get("league_now") or "").lower()
        club_now = p.get("club_now") or ""

        # Determina se salto di categoria
        higher_league = any(kw in league_now for kw in [
            "serie a", "serie b", "primera", "la liga", "bundesliga",
            "premier", "ligue 1", "eredivisie", "liga portugal",
            "championship", "2. bundesliga",
        ])

        if mv_now and mv_now > 0:
            roi = mv_now / max(mv_2023, 50000)
        else:
            roi = 1.0

        if higher_league and roi >= 3.0:
            status = "hit"
        elif roi < 1.5 and not higher_league:
            status = "miss"
        else:
            status = "lateral"

        p["status"] = status
        p["roi_multiplier"] = round(roi, 1)
        p["market_value_2023"] = mv_2023

    return top_players


def build_output(top_players: List[Dict], total_processed: int) -> Dict:
    """Costruisce l'output finale nel formato richiesto"""
    hits = [p for p in top_players if p.get("status") == "hit"]
    misses = [p for p in top_players if p.get("status") == "miss"]
    laterals = [p for p in top_players if p.get("status") == "lateral"]

    cumulative_gain = sum(
        (p.get("market_value_now") or 0) - (p.get("market_value_2023") or 0)
        for p in hits
        if p.get("market_value_now")
    )

    results = []
    for p in top_players:
        stats = p.get("_raw_stats", p.get("_original", {}).get("stats", {}))
        key_metrics = {
            "goals": stats.get("goals"),
            "assists": stats.get("assists"),
            "appearances": stats.get("games"),
            "minutes": stats.get("minutes"),
            "xg": stats.get("xg"),
        }
        # Aggiungi metriche passing/defense se disponibili
        if "passing" in stats:
            key_metrics["progressive_passes"] = stats["passing"].get("progressive_passes")
            key_metrics["key_passes"] = stats["passing"].get("key_passes")
        if "defense" in stats:
            key_metrics["tackles"] = stats["defense"].get("tackles")
            key_metrics["interceptions"] = stats["defense"].get("interceptions")

        results.append({
            "name": p["player_name"],
            "position": p.get("role_name") or p.get("role", ""),
            "club_2023": p.get("current_club", ""),
            "league_2023": "Serie C",
            "ob1_score_2023": p["ob1_score"],
            "classification_2023": p["classification"],
            "score_breakdown": p.get("score_breakdown", {}),
            "key_metrics_2023": key_metrics,
            "market_value_2023": p.get("market_value_2023"),
            "club_now": p.get("club_now"),
            "league_now": p.get("league_now"),
            "market_value_now": p.get("market_value_now"),
            "roi_multiplier": p.get("roi_multiplier", 1.0),
            "status": p.get("status", "miss"),
            "flag_date": FREEZE_DATE,
            "verified_date": datetime.now().strftime("%Y-%m-%d"),
            "fbref_url": p.get("_fbref_url", ""),
        })

    return {
        "metadata": {
            "source": "FBref",
            "season": "2022-2023",
            "freeze_date": FREEZE_DATE,
            "scorer": "scoring.py (8 fattori — freshness forzata a 100)",
            "total_players_processed": total_processed,
            "top_n_selected": len(top_players),
            "verified_date": datetime.now().strftime("%Y-%m-%d"),
            "generated_at": datetime.now().isoformat(),
            "version": "1.0",
        },
        "results": results,
        "summary": {
            "total_flagged": len(top_players),
            "hits": len(hits),
            "misses": len(misses),
            "lateral": len(laterals),
            "cumulative_value_gain": cumulative_gain,
            "narrative": _build_narrative(len(top_players), len(hits), len(misses), len(laterals), cumulative_gain),
        },
    }


def _build_narrative(total: int, hits: int, misses: int, laterals: int, gain: int) -> str:
    """Genera narrativa VC-style per il summary"""
    gain_str = f"€{gain:,.0f}".replace(",", ".") if gain > 0 else "€0"

    return (
        f"{total} giocatori flaggati nella Serie C 2022-2023. "
        f"{misses} sono rimasti in Serie C o categorie inferiori (costo club: ~€0). "
        f"{hits} sono esplosi generando {gain_str} di plusvalenza cumulativa stimata. "
        f"{laterals} movimenti laterali. "
        f"Il sistema OB1 identifica pattern statistici invisibili all'analisi tradizionale."
    )


def main():
    """Entry point"""
    logger.info("=" * 60)
    logger.info("OB1 BACKTEST SCORER — Serie C 2022/2023")
    logger.info("=" * 60)

    # Step 1: Carica dati
    players = load_raw_data()
    if not players:
        return

    total_processed = len(players)

    # Step 2: Scorri tutti
    scored = score_all(players)
    if not scored:
        logger.error("[FAIL] Nessun giocatore scorato")
        return

    # Step 3: Prendi top N
    top = scored[:TOP_N]
    logger.info(f"\n[TOP {TOP_N}] Score range: {top[0]['ob1_score']} — {top[-1]['ob1_score']}")
    for i, p in enumerate(top):
        logger.info(f"  {i+1:2d}. {p['player_name']:25s} | Score: {p['ob1_score']:3d} | {p.get('current_club', 'N/A')}")

    # Step 4: Arricchisci con dati attuali
    enriched = enrich_top_n(top, TOP_N)

    # Step 5: Classifica hit/miss/lateral
    classified = classify_results(enriched)

    # Step 6: Costruisci e salva output
    output = build_output(classified, total_processed)

    output_path = DATA_DIR / "backtest_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"\n{'=' * 60}")
    logger.info(f"[DONE] Risultati salvati in {output_path}")
    logger.info(f"{'=' * 60}")

    # Stampa summary
    summary = output["summary"]
    logger.info(f"\n📊 SUMMARY:")
    logger.info(f"  Flaggati: {summary['total_flagged']}")
    logger.info(f"  ✅ Hit:     {summary['hits']}")
    logger.info(f"  ❌ Miss:    {summary['misses']}")
    logger.info(f"  ↔️ Lateral: {summary['lateral']}")
    logger.info(f"  💰 Gain:    €{summary['cumulative_value_gain']:,.0f}")
    logger.info(f"\n  {summary['narrative']}")


if __name__ == "__main__":
    main()
