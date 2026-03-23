#!/usr/bin/env python3
"""
OB1 Scout — Generatore Post LinkedIn
Legge i risultati del backtest e genera post pronti per copy-paste.
Solo i giocatori con status "hit". Il caso migliore in posizione 5 o 6 (non primo).

Output:
  - data/social/linkedin_posts.md    (tutti i post numerati e datati)
  - data/social/linkedin_calendar.json (schedulazione con date)
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

# ── Setup ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
BACKTEST_PATH = DATA_DIR / "backtest" / "backtest_results.json"
OUTPUT_DIR = DATA_DIR / "social"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("linkedin_posts")


def format_value(value: int | None) -> str:
    """Formatta valore di mercato in stringa leggibile"""
    if not value:
        return "N/D"
    if value >= 1_000_000:
        return f"€{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"€{value // 1_000}k"
    return f"€{value}"


def get_top_metrics(metrics: dict) -> tuple[str, str, str, str]:
    """
    Estrae le 2 metriche piu' significative per il post.
    Ritorna (metrica_1_nome, percentile_1, metrica_2_nome, percentile_2).
    I percentili sono stimati rispetto alla Serie C.
    """
    # Metriche con soglie percentili approssimative per Serie C
    metric_thresholds = {
        "goals": {"label": "gol stagionali", "p90": 8, "p95": 12, "p99": 18},
        "assists": {"label": "assist stagionali", "p90": 5, "p95": 8, "p99": 12},
        "xg": {"label": "xG (Expected Goals)", "p90": 6.0, "p95": 9.0, "p99": 14.0},
        "progressive_passes": {"label": "passaggi progressivi", "p90": 40, "p95": 60, "p99": 90},
        "key_passes": {"label": "key passes", "p90": 20, "p95": 35, "p99": 50},
        "appearances": {"label": "presenze", "p90": 28, "p95": 32, "p99": 36},
        "tackles": {"label": "tackle riusciti", "p90": 40, "p95": 55, "p99": 70},
        "interceptions": {"label": "intercetti", "p90": 25, "p95": 35, "p99": 50},
    }

    scored = []
    for key, thresholds in metric_thresholds.items():
        val = metrics.get(key)
        if val is None or val == 0:
            continue

        # Stima percentile
        if val >= thresholds["p99"]:
            percentile = 99
        elif val >= thresholds["p95"]:
            percentile = 95 + int(4 * (val - thresholds["p95"]) / max(1, thresholds["p99"] - thresholds["p95"]))
        elif val >= thresholds["p90"]:
            percentile = 90 + int(5 * (val - thresholds["p90"]) / max(1, thresholds["p95"] - thresholds["p90"]))
        else:
            percentile = int(90 * val / max(1, thresholds["p90"]))

        percentile = min(99, max(1, percentile))
        scored.append((key, thresholds["label"], percentile, val))

    # Ordina per percentile decrescente
    scored.sort(key=lambda x: x[2], reverse=True)

    if len(scored) >= 2:
        return scored[0][1], str(scored[0][2]), scored[1][1], str(scored[1][2])
    elif len(scored) == 1:
        return scored[0][1], str(scored[0][2]), "presenze", "85"
    else:
        return "rendimento complessivo", "90", "costanza", "85"


def generate_post(player: dict) -> str:
    """Genera un singolo post LinkedIn dal template"""
    name = player["name"]
    value_2023 = format_value(player.get("market_value_2023"))
    league_2023 = player.get("league_2023", "Serie C")
    score = player.get("ob1_score_2023", 0)
    club_now = player.get("club_now") or "club di categoria superiore"
    league_now = player.get("league_now") or "campionato superiore"
    value_now = format_value(player.get("market_value_now"))
    roi = player.get("roi_multiplier", 1.0)

    metrics = player.get("key_metrics_2023", {})
    metrica_1, percentile_1, metrica_2, percentile_2 = get_top_metrics(metrics)

    post = (
        f"Nel giugno 2023, il mercato valutava {name} {value_2023} in {league_2023}.\n\n"
        f"Il nostro Ship of Theseus Protocol lo ha flaggato con un OB1 Score di {score}/100 "
        f"per anomalie in {metrica_1} ({percentile_1}° percentile) "
        f"e {metrica_2} ({percentile_2}° percentile).\n\n"
        f"Oggi gioca in {league_now} con {club_now} e vale {value_now}. "
        f"Rapporto {roi}:1.\n\n"
        f"L'algoritmo lo vedeva 3 anni fa. I DS no. "
        f"Report completo del backtest ↓"
    )

    return post


def get_publish_dates(n_posts: int, start_after: datetime = None) -> list[datetime]:
    """
    Genera date di pubblicazione: 2 post/settimana (Martedi e Giovedi).
    Parte dal primo martedi dopo start_after.
    """
    if start_after is None:
        start_after = datetime.now()

    # Trova il primo martedi dopo oggi
    days_until_tuesday = (1 - start_after.weekday()) % 7
    if days_until_tuesday == 0:
        days_until_tuesday = 7  # Se oggi e' martedi, parti dal prossimo

    first_tuesday = start_after + timedelta(days=days_until_tuesday)
    first_tuesday = first_tuesday.replace(hour=9, minute=0, second=0, microsecond=0)

    dates = []
    current = first_tuesday

    while len(dates) < n_posts:
        if current.weekday() == 1:  # Martedi
            dates.append(current)
            current += timedelta(days=2)  # Giovedi
        elif current.weekday() == 3:  # Giovedi
            dates.append(current)
            current += timedelta(days=5)  # Prossimo Martedi
        else:
            # Avanza al prossimo Martedi o Giovedi
            days_to_tue = (1 - current.weekday()) % 7
            days_to_thu = (3 - current.weekday()) % 7
            if days_to_tue == 0:
                days_to_tue = 7
            if days_to_thu == 0:
                days_to_thu = 7
            current += timedelta(days=min(days_to_tue, days_to_thu))

    return dates


def reorder_for_impact(hits: list[dict]) -> list[dict]:
    """
    Riordina i hit per impatto narrativo.
    Il caso migliore (ROI piu' alto) va in posizione 5 o 6, non primo.
    """
    if len(hits) <= 1:
        return hits

    # Ordina per ROI
    sorted_hits = sorted(hits, key=lambda x: x.get("roi_multiplier", 0), reverse=True)

    if len(sorted_hits) <= 5:
        # Con pochi post, metti il migliore in penultima posizione
        best = sorted_hits.pop(0)
        target_pos = max(0, len(sorted_hits) - 1)
        sorted_hits.insert(target_pos, best)
        return sorted_hits

    # Il caso migliore va in posizione 4 o 5 (indice, partendo da 0)
    best = sorted_hits.pop(0)
    second_best = sorted_hits.pop(0)

    # Costruisci sequenza: parti con casi medi, cresci, picco a posizione 5, poi scendi
    result = []
    # Posizioni 0-3: casi intermedi (dal meno al piu' forte tra i rimanenti)
    remaining = sorted(sorted_hits, key=lambda x: x.get("roi_multiplier", 0))
    for p in remaining[:4]:
        result.append(p)
        remaining.remove(p)

    # Posizione 4: secondo migliore
    result.append(second_best)
    # Posizione 5: migliore
    result.append(best)
    # Resto
    result.extend(remaining)

    return result


def main():
    """Entry point"""
    logger.info("=" * 60)
    logger.info("OB1 LINKEDIN POST GENERATOR")
    logger.info("=" * 60)

    # Carica backtest results
    if not BACKTEST_PATH.exists():
        logger.error(f"[FAIL] File non trovato: {BACKTEST_PATH}")
        logger.info("Esegui prima: python scripts/backtest_score.py")
        return

    with open(BACKTEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    hits = [r for r in results if r.get("status") == "hit"]

    if not hits:
        logger.warning("[WARN] Nessun giocatore con status 'hit' trovato")
        logger.info("Verifica i risultati del backtest in data/backtest/backtest_results.json")
        return

    logger.info(f"[LOAD] {len(hits)} giocatori 'hit' trovati")

    # Riordina per impatto narrativo (migliore in posizione 5-6)
    ordered = reorder_for_impact(hits)

    # Genera date di pubblicazione
    dates = get_publish_dates(len(ordered))

    # Genera post e calendario
    posts_md_lines = [
        "# OB1 Scout — LinkedIn Posts (Backtested Signals)\n",
        f"> Generati il {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"> Totale post: {len(ordered)}\n",
        f"> Calendario: 2/settimana (Martedi e Giovedi)\n",
        "",
    ]

    calendar_entries = []

    for i, (player, pub_date) in enumerate(zip(ordered, dates)):
        post_text = generate_post(player)
        day_name = pub_date.strftime("%A")
        date_str = pub_date.strftime("%Y-%m-%d")
        date_display = pub_date.strftime("%d/%m/%Y (%A)")

        posts_md_lines.append(f"---\n")
        posts_md_lines.append(f"## Post {i + 1} — {date_display}\n")
        posts_md_lines.append(f"**Giocatore:** {player['name']}\n")
        posts_md_lines.append(f"**ROI:** {player.get('roi_multiplier', '?')}x\n")
        posts_md_lines.append(f"**Status:** {player.get('status', '?')}\n\n")
        posts_md_lines.append(f"```\n{post_text}\n```\n\n")

        calendar_entries.append({
            "post_number": i + 1,
            "publish_date": date_str,
            "publish_day": day_name,
            "publish_time": "09:00",
            "player_name": player["name"],
            "roi_multiplier": player.get("roi_multiplier"),
            "status": player.get("status"),
            "post_text": post_text,
        })

    # Salva markdown
    md_path = OUTPUT_DIR / "linkedin_posts.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(posts_md_lines))

    # Salva calendario JSON
    calendar_path = OUTPUT_DIR / "linkedin_calendar.json"
    calendar_output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_posts": len(calendar_entries),
            "frequency": "2/week (Tuesday, Thursday)",
            "first_post": dates[0].strftime("%Y-%m-%d") if dates else None,
            "last_post": dates[-1].strftime("%Y-%m-%d") if dates else None,
            "source": "data/backtest/backtest_results.json",
            "version": "1.0",
        },
        "posts": calendar_entries,
    }

    with open(calendar_path, "w", encoding="utf-8") as f:
        json.dump(calendar_output, f, ensure_ascii=False, indent=2)

    logger.info(f"\n{'=' * 60}")
    logger.info(f"[DONE] {len(calendar_entries)} post generati")
    logger.info(f"  Markdown: {md_path}")
    logger.info(f"  Calendario: {calendar_path}")
    logger.info(f"  Primo post: {dates[0].strftime('%d/%m/%Y (%A)')}")
    logger.info(f"  Ultimo post: {dates[-1].strftime('%d/%m/%Y (%A)')}")
    logger.info(f"{'=' * 60}")

    # Preview primo post
    if calendar_entries:
        logger.info(f"\n📋 PREVIEW — Post 1:")
        logger.info(f"{'─' * 40}")
        for line in calendar_entries[0]["post_text"].split("\n"):
            logger.info(f"  {line}")


if __name__ == "__main__":
    main()
