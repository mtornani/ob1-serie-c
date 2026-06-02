#!/usr/bin/env python3
"""
OB1 Lega Pro — Post-pipeline sanity check.
Verifica che opportunities.json e docs/data.json esistano e siano sensati.
Exit 0 = tutto OK. Exit 1 = anomalia critica (blocca pipeline CI).
"""

import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for notifier import
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.notifier import TelegramNotifier

# ── Thresholds ────────────────────────────────────────────────────────────────
MIN_OPPS_DB        = 10    # opportunities.json must have at least this many entries
MIN_SCORED         = 5     # docs/data.json must have at least this many scored opps
MAX_COLD_RATIO     = 1.0   # if total > 20 and 100% COLD → scoring may be broken (warn only)
MAX_STALE_HOURS    = 2     # docs/data.json last_update must be within this many hours

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent.parent
OPPS_FILE = BASE_DIR / "data" / "opportunities.json"
DASH_FILE = BASE_DIR / "docs" / "data.json"

# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    notifier = TelegramNotifier()
    errors: list[str] = []
    warnings: list[str] = []
    now_utc = datetime.now(timezone.utc)

    print("=" * 55)
    print("OB1 LEGA PRO — SANITY CHECK")
    print(f"Run at: {now_utc.strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 55)

    # ── 1. File existence ──────────────────────────────────────────────────
    print("\n[1/4] File existence")
    if not OPPS_FILE.exists():
        errors.append(f"data/opportunities.json non trovato")
        print(f"  ❌ CRITICAL: {OPPS_FILE} mancante")
    else:
        print(f"  ✅ data/opportunities.json presente")

    if not DASH_FILE.exists():
        errors.append(f"docs/data.json non trovato")
        print(f"  ❌ CRITICAL: {DASH_FILE} mancante")
    else:
        print(f"  ✅ docs/data.json presente")

    if errors:
        _send_and_exit(notifier, errors, warnings)
        return 1

    # ── 2. opportunities.json content ─────────────────────────────────────
    print("\n[2/4] opportunities.json content")
    try:
        opps = json.loads(OPPS_FILE.read_text(encoding='utf-8'))
        n_opps = len(opps)
        if n_opps < MIN_OPPS_DB:
            errors.append(f"Troppo pochi entries nel DB: {n_opps} < {MIN_OPPS_DB}")
            print(f"  ❌ CRITICAL: solo {n_opps} entries (min {MIN_OPPS_DB})")
        else:
            print(f"  ✅ {n_opps} entries nel DB")

        # Spot-check first entry has minimum fields
        required_fields = ['id', 'player_name']
        if opps:
            missing = [f for f in required_fields if f not in opps[0]]
            if missing:
                errors.append(f"Campi mancanti nel primo entry: {missing}")
                print(f"  ❌ CRITICAL: campi mancanti: {missing}")
            else:
                print(f"  ✅ Struttura entries OK")
    except json.JSONDecodeError as e:
        errors.append(f"opportunities.json JSON invalido: {e}")
        print(f"  ❌ CRITICAL: JSON parse error: {e}")

    # ── 3. docs/data.json scoring sanity ──────────────────────────────────
    print("\n[3/4] docs/data.json scoring sanity")
    try:
        dash = json.loads(DASH_FILE.read_text(encoding='utf-8'))
        stats = dash.get('stats', {})
        total   = stats.get('total', 0)
        hot     = stats.get('hot', 0)
        warm    = stats.get('warm', 0)
        cold    = stats.get('cold', 0)
        last_up = dash.get('last_update', '')

        print(f"  Total: {total}  HOT: {hot}  WARM: {warm}  COLD: {cold}")

        if total < MIN_SCORED:
            errors.append(f"Troppo pochi scored in dashboard: {total} < {MIN_SCORED}")
            print(f"  ❌ CRITICAL: solo {total} scored (min {MIN_SCORED})")
        else:
            print(f"  ✅ {total} opportunità scored")

        # All-COLD warning (scoring regression risk)
        if total > 20 and hot == 0 and warm == 0:
            warnings.append(f"100% COLD su {total} entries — possibile regressione scoring")
            print(f"  ⚠️  WARNING: tutti {total} entries COLD — verificare scoring")

        # Freshness check
        if last_up:
            try:
                last_dt = datetime.fromisoformat(last_up.replace('Z', '+00:00'))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                age_hours = (now_utc - last_dt).total_seconds() / 3600
                if age_hours > MAX_STALE_HOURS:
                    warnings.append(f"docs/data.json aggiornato {age_hours:.1f}h fa (max {MAX_STALE_HOURS}h)")
                    print(f"  ⚠️  WARNING: last_update {age_hours:.1f}h fa")
                else:
                    print(f"  ✅ last_update {age_hours:.1f}h fa (fresh)")
            except (ValueError, AttributeError, TypeError):
                warnings.append(f"last_update non parsabile: {last_up!r}")
                print(f"  ⚠️  WARNING: last_update non parsabile: {last_up!r}")
        else:
            warnings.append("last_update mancante in docs/data.json")
            print(f"  ⚠️  WARNING: last_update assente")

    except json.JSONDecodeError as e:
        errors.append(f"docs/data.json JSON invalido: {e}")
        print(f"  ❌ CRITICAL: JSON parse error: {e}")

    # ── 4. Summary ────────────────────────────────────────────────────────
    print("\n[4/4] Summary")
    if not errors and not warnings:
        print("  ✅ All checks passed — pipeline output is sane")
    elif not errors:
        print(f"  ⚠️  {len(warnings)} warning(s), 0 critical errors")
    else:
        print(f"  ❌ {len(errors)} critical error(s), {len(warnings)} warning(s)")

    _send_and_exit(notifier, errors, warnings)
    return 1 if errors else 0


def _send_and_exit(notifier: TelegramNotifier, errors: list, warnings: list) -> None:
    if errors:
        msg = "CRITICAL: " + "; ".join(errors)
        if warnings:
            msg += " | WARN: " + "; ".join(warnings)
        notifier.admin_alert("ERROR", "sanity_check", msg)
    elif warnings:
        notifier.admin_alert("WARNING", "sanity_check", "; ".join(warnings))


if __name__ == "__main__":
    sys.exit(main())
