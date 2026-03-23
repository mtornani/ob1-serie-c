#!/usr/bin/env python3
"""
OB1 Scout — Backtest Collector
Raccoglie statistiche giocatori Serie C 2022/2023 da Transfermarkt via Tavily Extract API.
Pipeline: SOURCE → FETCH → CACHE → CLEAN → NORMALIZE → OUTPUT

Fonte: Transfermarkt (3 gironi: IT3A, IT3B, IT3C)
Tavily Extract bypassa Cloudflare dove scrapling e requests falliscono.

Output: data/backtest/serie_c_2022_2023_raw.json
"""

import os
import sys
import json
import time
import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import requests
from dotenv import load_dotenv

# ── Setup paths ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

load_dotenv(PROJECT_ROOT / ".env")

CACHE_DIR = PROJECT_ROOT / "data" / "backtest" / "cache"
OUTPUT_DIR = PROJECT_ROOT / "data" / "backtest"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ──
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backtest_collector")

# ── Configurazione ──
TAVILY_KEY = os.getenv("TAVILY_API_KEY")
if not TAVILY_KEY:
    raise ValueError("TAVILY_API_KEY mancante in .env")

TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"

# Transfermarkt URL per Serie C 2022-2023 (3 gironi)
GIRONI = {
    "IT3A": {
        "name": "Girone A",
        "marcatori": "https://www.transfermarkt.it/serie-c-girone-a/torschuetzenliste/wettbewerb/IT3A/saison_id/2022/altersklasse/alle/detailpos//plus/1",
        "dettaglio": "https://www.transfermarkt.it/serie-c-girone-a/leistungsdaten/wettbewerb/IT3A/saison_id/2022/plus/1",
    },
    "IT3B": {
        "name": "Girone B",
        "marcatori": "https://www.transfermarkt.it/serie-c-girone-b/torschuetzenliste/wettbewerb/IT3B/saison_id/2022/altersklasse/alle/detailpos//plus/1",
        "dettaglio": "https://www.transfermarkt.it/serie-c-girone-b/leistungsdaten/wettbewerb/IT3B/saison_id/2022/plus/1",
    },
    "IT3C": {
        "name": "Girone C",
        "marcatori": "https://www.transfermarkt.it/serie-c-girone-c/torschuetzenliste/wettbewerb/IT3C/saison_id/2022/altersklasse/alle/detailpos//plus/1",
        "dettaglio": "https://www.transfermarkt.it/serie-c-girone-c/leistungsdaten/wettbewerb/IT3C/saison_id/2022/plus/1",
    },
}

# Rate limiting per Tavily
REQUEST_DELAY = 3  # secondi tra richieste

# Metadata del backtest
METADATA = {
    "source": "Transfermarkt (via Tavily Extract)",
    "season": "2022-2023",
    "league": "Serie C",
    "freeze_date": "2023-06-30",
    "collector_version": "2.0",
    "generated_at": None,
}


def get_cache_path(url: str) -> Path:
    """Genera path cache deterministico per un URL"""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"{url_hash}.txt"


def fetch_via_tavily(url: str, force_refresh: bool = False) -> Optional[str]:
    """Scarica contenuto pagina via Tavily Extract API con cache locale"""
    cache_path = get_cache_path(url)

    # Usa cache se disponibile
    if cache_path.exists() and not force_refresh:
        logger.info(f"  [CACHE HIT] {url}")
        return cache_path.read_text(encoding="utf-8")

    # Fetch via Tavily Extract
    logger.info(f"  [FETCH via Tavily] {url}")
    time.sleep(REQUEST_DELAY)

    try:
        payload = {
            "api_key": TAVILY_KEY,
            "urls": [url],
        }
        resp = requests.post(TAVILY_EXTRACT_URL, json=payload, timeout=60)

        if resp.status_code != 200:
            logger.error(f"  [HTTP {resp.status_code}] Tavily Extract error")
            return None

        data = resp.json()
        results = data.get("results", [])

        if not results:
            logger.warning(f"  [WARN] Nessun risultato da Tavily per {url}")
            # Controlla errori
            failed = data.get("failed_results", [])
            if failed:
                logger.error(f"  [FAIL] {failed}")
            return None

        raw_content = results[0].get("raw_content", "")
        if not raw_content:
            logger.warning(f"  [WARN] Contenuto vuoto per {url}")
            return None

        # Salva in cache
        cache_path.write_text(raw_content, encoding="utf-8")
        logger.info(f"  [CACHED] {cache_path.name} ({len(raw_content)} chars)")
        return raw_content

    except Exception as e:
        logger.error(f"  [ERROR] Tavily Extract fallito: {e}")
        return None


def parse_marcatori(content: str, girone_id: str) -> List[Dict[str, Any]]:
    """
    Parsa la lista marcatori Transfermarkt dal contenuto raw Tavily.
    Formato riga tipica Transfermarkt (markdown pipe):
    | # | Nome | [Nome](/profil/spieler/ID) | | Posizione | | Naz | Eta (oggi) | [Club](/verein/ID) | [Pres](/leistung) | sub_in | sub_out | minuti' | min/gol | gol/partita | [GOL](/leistung) |

    I GOL sono nell'ULTIMO link [numero] della riga.
    Le PRESENZE sono nel primo link [numero] dopo il club.
    """
    players = []
    lines = content.split("\n")

    for line in lines:
        line = line.strip()

        # Cerca solo righe numerate della tabella (iniziano con | 1, | 2, etc.)
        if not re.match(r'\|\s*\d+\s*\|', line):
            continue

        player = _parse_marcatori_row(line, girone_id)
        if player:
            players.append(player)

    logger.info(f"  [PARSED] {len(players)} marcatori dal {girone_id}")
    return players


def _parse_marcatori_row(line: str, girone_id: str) -> Optional[Dict]:
    """
    Parsa una riga marcatori Transfermarkt.
    Strategia: estrai tutti i link [testo](url) e numeri separatamente.
    """
    try:
        # Estrai tutti i link markdown dalla riga
        links = re.findall(r'\[([^\]]+)\]\((/[^\)]+)\)', line)

        name = None
        tm_url = None
        position = None
        team = None
        appearances = None
        goals = None
        age = None
        minutes = None

        # Classifica i link
        stat_links = []  # Link con numeri (presenze, gol)
        for text, url in links:
            text = text.strip()

            # Profilo giocatore
            if "/profil/spieler/" in url and not name:
                name = text
                tm_url = f"https://www.transfermarkt.it{url}"
            # Club
            elif "/startseite/verein/" in url or "/verein/" in url:
                team = text
            # Link statistici (presenze o gol) — sono [numero](/leistungsdaten/...)
            elif "/leistungsdaten/" in url and text.isdigit():
                stat_links.append(int(text))

        if not name:
            return None

        # stat_links: primo = presenze, ultimo = gol
        if len(stat_links) >= 2:
            appearances = stat_links[0]
            goals = stat_links[-1]
        elif len(stat_links) == 1:
            goals = stat_links[0]

        # Cerca posizione
        pos_keywords = ["Punta centrale", "Ala sinistra", "Ala destra", "Seconda punta",
                       "Centrocampista", "Trequartista", "Mediano", "Esterno",
                       "Difensore centrale", "Terzino sinistro", "Terzino destro",
                       "Portiere", "Libero", "Jolly"]
        for pos in pos_keywords:
            if pos in line:
                position = pos
                break

        # Cerca eta: pattern "N (M)" dove N e' eta nel 2023 e M e' eta oggi
        age_match = re.search(r'\b(\d{2})\s*\(\d{2}\)', line)
        if age_match:
            age = int(age_match.group(1))

        # Cerca minuti: pattern "N.NNN'" o "NNN'"
        min_match = re.search(r'([\d.]+)\'\s*\|', line)
        if min_match:
            min_str = min_match.group(1).replace(".", "")
            try:
                minutes = int(min_str)
            except ValueError:
                pass

        return {
            "name": name,
            "tm_url": tm_url or "",
            "position": position or "",
            "team_2023": team or "",
            "age_2023": age,
            "girone": girone_id,
            "stats": {
                "games": appearances,
                "goals": goals,
                "assists": None,
                "minutes": minutes,
            },
        }

    except Exception:
        return None


def collect() -> List[Dict[str, Any]]:
    """Pipeline principale di raccolta dati da Transfermarkt via Tavily"""
    logger.info("=" * 60)
    logger.info("OB1 BACKTEST COLLECTOR — Serie C 2022/2023")
    logger.info("Fonte: Transfermarkt via Tavily Extract API")
    logger.info("=" * 60)

    all_players = []

    for girone_id, urls in GIRONI.items():
        logger.info(f"\n{'─' * 40}")
        logger.info(f"[{girone_id}] {urls['name']}")
        logger.info(f"{'─' * 40}")

        # Scarica marcatori (con retry in caso di timeout)
        logger.info(f"  Scarico marcatori {girone_id}...")
        marcatori_content = fetch_via_tavily(urls["marcatori"])

        # Retry se fallisce (timeout Tavily)
        if not marcatori_content:
            logger.info(f"  [RETRY] Riprovo marcatori {girone_id} dopo 10s...")
            time.sleep(10)
            marcatori_content = fetch_via_tavily(urls["marcatori"], force_refresh=True)

        marcatori = []
        if marcatori_content:
            marcatori = parse_marcatori(marcatori_content, girone_id)

        logger.info(f"  → {len(marcatori)} marcatori per {girone_id}")
        all_players.extend(marcatori)

    # Dedup per nome (giocatori che cambiano girone a meta' stagione)
    seen = set()
    unique_players = []
    for p in all_players:
        if p["name"] not in seen:
            seen.add(p["name"])
            unique_players.append(p)

    # Filtra giocatori con dati minimi
    valid = [p for p in unique_players if p.get("name") and len(p["name"]) > 2]
    logger.info(f"\n[TOTAL] {len(valid)} giocatori unici raccolti dai 3 gironi")

    return valid


def main():
    """Entry point"""
    players = collect()

    if not players:
        logger.error("\n[FAIL] Nessun dato raccolto.")
        return

    # Compila metadata
    METADATA["generated_at"] = datetime.now().isoformat()
    METADATA["total_players"] = len(players)

    output = {
        "metadata": METADATA,
        "players": players,
    }

    # Salva output
    output_path = OUTPUT_DIR / "serie_c_2022_2023_raw.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"\n{'=' * 60}")
    logger.info(f"[DONE] {len(players)} giocatori salvati in {output_path}")
    logger.info(f"{'=' * 60}")

    # Statistiche rapide
    with_goals = [p for p in players if p["stats"].get("goals") and p["stats"]["goals"] > 0]
    with_games = [p for p in players if p["stats"].get("games") and p["stats"]["games"] > 0]
    logger.info(f"  Con gol: {len(with_goals)}")
    logger.info(f"  Con presenze: {len(with_games)}")
    logger.info(f"  Gironi: {len(set(p.get('girone', '') for p in players))}")


if __name__ == "__main__":
    main()
