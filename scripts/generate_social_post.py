#!/usr/bin/env python3
"""
OB1 Scout - Generatore Post Social Settimanali (DATA-003-MW3)
Produce il "murales settimanale" — dati freddi che parlano da soli.

Output:
  data/social/weekly_x_post.txt      — Post per X (max 560 char, 2 tweet)
  data/social/weekly_telegram_post.txt — Report per canale Telegram pubblico
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
DATA_FILE = BASE_DIR / "docs" / "data.json"
HISTORY_FILE = BASE_DIR / "data" / "history_log.json"
SNAPSHOTS_DIR = BASE_DIR / "data" / "snapshots"
SOCIAL_DIR = BASE_DIR / "data" / "social"

DASHBOARD_URL = "https://mirkotornani.github.io/ob1-serie-c-dev/"

# Firme del murales (rotazione)
FIRME = [
    "I numeri parlano da soli.",
    "Un algoritmo li trova in 6 ore. Il mercato no.",
    "Il sistema li trova. Il mercato ancora no.",
]

# Numero settimana ISO
WEEK_NUMBER = datetime.now().isocalendar()[1]


# ---------------------------------------------------------------------------
# Caricamento dati
# ---------------------------------------------------------------------------

def load_opportunities() -> list:
    if not DATA_FILE.exists():
        fallback = BASE_DIR / "data" / "opportunities.json"
        if not fallback.exists():
            return []
        raw = json.loads(fallback.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else raw.get("opportunities", [])
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "opportunities" in data:
        return data["opportunities"]
    return data if isinstance(data, list) else []


def load_latest_snapshot() -> Optional[list]:
    """Carica lo snapshot piu' vecchio disponibile (max 7 giorni fa)."""
    if not SNAPSHOTS_DIR.exists():
        return None
    snapshots = sorted(SNAPSHOTS_DIR.glob("opportunities_*.json"))
    # Cerca snapshot tra 5 e 9 giorni fa (settimana scorsa)
    cutoff_min = datetime.now() - timedelta(days=9)
    cutoff_max = datetime.now() - timedelta(days=5)
    candidates = []
    for snap in snapshots:
        try:
            # Format: opportunities_YYYYMMDD_HHMM.json
            ts_str = snap.stem.replace("opportunities_", "")
            ts = datetime.strptime(ts_str, "%Y%m%d_%H%M")
            if cutoff_min <= ts <= cutoff_max:
                candidates.append((ts, snap))
        except ValueError:
            continue
    if not candidates:
        return None
    _, best = max(candidates, key=lambda x: x[0])
    try:
        raw = json.loads(best.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else raw.get("opportunities", [])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Calcolo statistiche aggregate
# ---------------------------------------------------------------------------

def compute_stats(opportunities: list) -> dict:
    free_agent_types = {"svincolato", "rescissione"}

    svincolati = [
        o for o in opportunities
        if (o.get("opportunity_type") or "").lower() in free_agent_types
    ]

    total_free_agents = len(svincolati)
    under_28_ignored = sum(
        1 for o in svincolati if (o.get("age") or 99) < 28
    )

    days_list = [
        o.get("days_without_contract", 0)
        for o in svincolati
        if o.get("days_without_contract") is not None
    ]
    avg_days = round(sum(days_list) / len(days_list)) if days_list else 0

    # Nuovi questa settimana (discovered_at negli ultimi 7 giorni)
    cutoff_new = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    new_this_week = sum(
        1 for o in svincolati
        if (o.get("discovered_at") or "")[:10] >= cutoff_new
    )

    stale_list = [o for o in opportunities if o.get("stale_free_agent")]
    stale_count = len(stale_list)

    return {
        "total_free_agents": total_free_agents,
        "under_28_ignored": under_28_ignored,
        "avg_days": avg_days,
        "new_this_week": new_this_week,
        "stale_count": stale_count,
        "stale_list": stale_list,
        "svincolati": svincolati,
    }


# ---------------------------------------------------------------------------
# Selezione "Caso della Settimana"
# ---------------------------------------------------------------------------

def select_case_of_week(opportunities: list) -> Optional[dict]:
    """
    Stale free agent con score piu' alto, stats disponibili e appearances >= 10.
    Fallback: giocatore con score piu' alto.
    """
    stale = [
        o for o in opportunities
        if o.get("stale_free_agent")
        and (o.get("appearances") or 0) >= 10
        and o.get("goals") is not None
    ]
    if stale:
        # Score DESC, days_without_contract DESC come tiebreaker
        return max(stale, key=lambda x: (x.get("ob1_score", 0), x.get("days_without_contract", 0)))

    # Fallback: qualsiasi stale con appearances >= 5
    stale_any = [
        o for o in opportunities
        if o.get("stale_free_agent") and (o.get("appearances") or 0) >= 5
    ]
    if stale_any:
        return max(stale_any, key=lambda x: (x.get("ob1_score", 0), x.get("days_without_contract", 0)))

    # Ultimo fallback: score piu' alto in assoluto
    if opportunities:
        return max(opportunities, key=lambda x: x.get("ob1_score", 0))

    return None


# ---------------------------------------------------------------------------
# Analisi agenti
# ---------------------------------------------------------------------------

def compute_agent_stats(svincolati: list) -> list:
    """Ritorna lista (agent_name, count) ordinata per count DESC, min 3 giocatori per agente."""
    agents = [o.get("agent") for o in svincolati if o.get("agent")]
    if len(agents) < 3:
        return []
    counts = Counter(agents)
    # Mostra solo agenti con piu' di 1 svincolato
    result = [(name, cnt) for name, cnt in counts.most_common() if cnt > 1]
    return result[:5]


# ---------------------------------------------------------------------------
# Confronto snapshot
# ---------------------------------------------------------------------------

def compute_snapshot_delta(current: list, previous: list) -> Optional[dict]:
    """Quanti erano svincolati 7 giorni fa vs oggi."""
    if not previous:
        return None
    free_types = {"svincolato", "rescissione"}
    prev_free = sum(1 for o in previous if (o.get("opportunity_type") or "").lower() in free_types)
    curr_free = sum(1 for o in current if (o.get("opportunity_type") or "").lower() in free_types)
    delta = curr_free - prev_free
    return {"prev": prev_free, "curr": curr_free, "delta": delta}


# ---------------------------------------------------------------------------
# Helpers di formattazione
# ---------------------------------------------------------------------------

ROLE_LABELS = {
    "PO": "Portiere", "DC": "Difensore", "TD": "Terzino D.", "TS": "Terzino S.",
    "CC": "Centrocampista", "MED": "Mediano", "TRQ": "Trequartista",
    "AT": "Attaccante", "PC": "Punta", "AD": "Ala D.", "AS": "Ala S.",
    "ED": "Esterno D.", "ES": "Esterno S."
}


def rl(code: str) -> str:
    return ROLE_LABELS.get(code or "", code or "")


def fmt_date_italian(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        months = ["gen", "feb", "mar", "apr", "mag", "giu",
                  "lug", "ago", "set", "ott", "nov", "dic"]
        return f"{dt.day} {months[dt.month - 1]} {dt.year}"
    except Exception:
        return date_str


def firma_settimana() -> str:
    """Rotazione firme basata sul numero di settimana."""
    return FIRME[WEEK_NUMBER % len(FIRME)]


# ---------------------------------------------------------------------------
# Generazione post X (Twitter)
# ---------------------------------------------------------------------------

def generate_x_post(stats: dict, case: Optional[dict]) -> str:
    """
    Genera post X. Se > 280 char, split in 2 parti.
    Formato: numeri aggregati + caso + firma + link.
    """
    lines_part1 = [
        f"📊 Lega Pro — Settimana {WEEK_NUMBER}",
        "",
        f"Svincolati attivi: {stats['total_free_agents']}",
        f"Under 28 ignorati: {stats['under_28_ignored']}",
        f"Media giorni senza contratto: {stats['avg_days']}",
    ]

    if case:
        name = case.get("player_name", "N/D")
        age = case.get("age", "?")
        apps = case.get("appearances") or 0
        goals = case.get("goals") or 0
        days = case.get("days_without_contract") or 0

        case_parts = [f"{name}, {age} anni"]
        if apps:
            case_parts.append(f"{apps} presenze")
        if apps and goals:
            case_parts.append(f"{goals} gol")
        if days:
            case_parts.append(f"svincolato da {days} giorni")

        lines_part1.append("")
        lines_part1.append(f"Il caso: {', '.join(case_parts)}.")

    part1 = "\n".join(lines_part1)
    firma = firma_settimana()
    link_line = "\n\n🔗 t.me/ob1scout"

    part2_text = f"\n\n{firma}{link_line}"

    # Se tutto sta in 280 char, un tweet
    full = part1 + part2_text
    if len(full) <= 280:
        return full

    # Split: tweet 1 = numeri + caso, tweet 2 = firma + link
    tweet1 = part1
    if len(tweet1) > 280:
        tweet1 = tweet1[:277] + "..."

    tweet2 = f"{firma}{link_line}"

    return f"[1/2]\n{tweet1}\n\n[2/2]\n{tweet2}"


# ---------------------------------------------------------------------------
# Generazione post Telegram pubblico
# ---------------------------------------------------------------------------

def generate_telegram_post(stats: dict, case: Optional[dict], agent_stats: list, top5: list) -> str:
    today_str = datetime.now().strftime("%d/%m/%Y")
    lines = [
        f"📊 OB1 SCOUT — Report Settimanale {today_str}",
        "",
        "━━━ I NUMERI ━━━",
        "",
        f"🔴 {stats['total_free_agents']} svincolati attivi nel sistema",
        f"🔴 {stats['under_28_ignored']} sono under 28",
        f"🔴 Media giorni senza contratto: {stats['avg_days']}",
        f"🔴 Nuovi questa settimana: {stats['new_this_week']}",
        f"🔴 Ignorati da oltre 30 giorni: {stats['stale_count']}",
    ]

    # --- Caso della settimana ---
    if case:
        lines.append("")
        lines.append("━━━ IL CASO DELLA SETTIMANA ━━━")
        lines.append("")

        name = case.get("player_name", "N/D")
        age = case.get("age")
        role_code = case.get("role", "")
        role = rl(role_code)
        foot = case.get("foot")
        height = case.get("height_cm")
        apps = case.get("appearances")
        goals = case.get("goals")
        assists = case.get("assists")
        club = case.get("current_club")
        discovered = case.get("discovered_at") or case.get("reported_date")
        days = case.get("days_without_contract")
        market_value = case.get("market_value_formatted")
        agent = case.get("agent")
        score = case.get("ob1_score", 0)
        opp_type = (case.get("opportunity_type") or "").lower()

        # Riga principale
        age_str = f", {age} anni" if age else ""
        lines.append(f"🎯 {name}{age_str}")

        # Dettagli anagrafici
        meta_parts = []
        if role:
            meta_parts.append(role)
        if foot:
            meta_parts.append(foot)
        if height:
            meta_parts.append(f"{height}cm")
        if meta_parts:
            lines.append(f"📍 {' | '.join(meta_parts)}")

        # Stats stagionali (omette campi null E zero — zero senza presenze e' dato mancante)
        stats_parts = []
        if apps:
            stats_parts.append(f"{apps} pres")
        if apps and goals is not None:
            stats_parts.append(f"{goals} gol")
        if apps and assists is not None:
            stats_parts.append(f"{assists} assist")
        if stats_parts:
            lines.append(f"📈 Stagione 25/26: {' | '.join(stats_parts)}")

        if club:
            lines.append(f"🏟️ Ex: {club} (Serie C)")

        if discovered:
            date_fmt = fmt_date_italian(discovered)
            days_str = f" ({days} giorni fa)" if days else ""
            lines.append(f"📅 Svincolato dal {date_fmt}{days_str}")

        if market_value:
            lines.append(f"💰 Valore TM: {market_value}")

        if agent:
            lines.append(f"👔 Agente: {agent}")

        lines.append(f"📊 OB1 Score: {score}/100")
        lines.append("")
        lines.append("Nessun club di Serie C risulta averlo ingaggiato.")

    # --- Top 5 ignorati ---
    if top5:
        lines.append("")
        lines.append("━━━ TOP 5 IGNORATI ━━━")
        lines.append("")
        for i, p in enumerate(top5, 1):
            p_name = p.get("player_name", "N/D")
            p_age = p.get("age", "?")
            p_goals = p.get("goals")
            p_days = p.get("days_without_contract")
            p_apps = p.get("appearances") or 0
            parts = [f"{p_name} — {p_age} anni"]
            if p_apps and p_goals is not None:
                parts.append(f"{p_goals} gol")
            if p_days:
                parts.append(f"{p_days}gg senza contratto")
            lines.append(f"{i}. {' — '.join(parts)}")

    # --- Rete agenti (solo se >= 3 giocatori con dati agent) ---
    if agent_stats:
        lines.append("")
        lines.append("━━━ RETE AGENTI ━━━")
        lines.append("")
        for ag_name, ag_count in agent_stats:
            lines.append(f"{ag_name}: {ag_count} svincolati gestiti")

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append(firma_settimana())
    lines.append("")
    lines.append(f"🔗 Dashboard: {DASHBOARD_URL}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Calcola Top 5 per il post
# ---------------------------------------------------------------------------

def compute_top5(opportunities: list) -> list:
    """
    Top 5 svincolati stale per: score DESC, poi days_without_contract DESC.
    Se meno di 5 stale, usa i migliori svincolati disponibili.
    """
    free_types = {"svincolato", "rescissione"}
    svincolati = [
        o for o in opportunities
        if (o.get("opportunity_type") or "").lower() in free_types
    ]
    stale = [o for o in svincolati if o.get("stale_free_agent")]
    pool = stale if len(stale) >= 3 else svincolati
    sorted_pool = sorted(
        pool,
        key=lambda x: (x.get("ob1_score", 0), x.get("days_without_contract", 0)),
        reverse=True
    )
    return sorted_pool[:5]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("🎨 OB1 Social Post Generator (DATA-003-MW3)")

    opportunities = load_opportunities()
    if not opportunities:
        print("❌ Nessuna opportunita' trovata. Aborting.")
        sys.exit(1)
    print(f"   Caricate {len(opportunities)} opportunita'")

    stats = compute_stats(opportunities)
    print(f"   Svincolati attivi: {stats['total_free_agents']}")
    print(f"   Under 28 ignorati: {stats['under_28_ignored']}")
    print(f"   Stale (>30gg): {stats['stale_count']}")

    # Guard: dati insufficienti per un report significativo
    if stats["total_free_agents"] < 5:
        print(f"⚠️ Solo {stats['total_free_agents']} svincolati — dati insufficienti per il post. Skip.")
        sys.exit(0)

    case = select_case_of_week(opportunities)
    if case:
        print(f"   Caso della settimana: {case.get('player_name')} (score {case.get('ob1_score')})")
    else:
        print("   Nessun caso della settimana selezionabile.")

    agent_stats = compute_agent_stats(stats["svincolati"])
    top5 = compute_top5(opportunities)

    # Snapshot delta (opzionale, solo per logging)
    prev_snapshot = load_latest_snapshot()
    if prev_snapshot:
        delta = compute_snapshot_delta(opportunities, prev_snapshot)
        if delta:
            sign = "+" if delta["delta"] >= 0 else ""
            print(f"   Delta 7gg: {delta['prev']} → {delta['curr']} ({sign}{delta['delta']})")

    # Genera post
    x_post = generate_x_post(stats, case)
    tg_post = generate_telegram_post(stats, case, agent_stats, top5)

    # Salva output
    SOCIAL_DIR.mkdir(parents=True, exist_ok=True)

    x_file = SOCIAL_DIR / "weekly_x_post.txt"
    tg_file = SOCIAL_DIR / "weekly_telegram_post.txt"

    x_file.write_text(x_post, encoding="utf-8")
    tg_file.write_text(tg_post, encoding="utf-8")

    print(f"✅ X post: {x_file} ({len(x_post)} char)")
    print(f"✅ Telegram post: {tg_file} ({len(tg_post)} char)")

    # Preview
    print("\n--- X POST PREVIEW ---")
    print(x_post)
    print("\n--- TELEGRAM POST PREVIEW (prime 300 char) ---")
    print(tg_post[:300] + "..." if len(tg_post) > 300 else tg_post)


if __name__ == "__main__":
    main()
