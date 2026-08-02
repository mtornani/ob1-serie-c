#!/usr/bin/env python3
"""
Quota ledger: contabilità free-tier persistente tra le run.

La CI è stateless — senza questo file ogni run riparte da zero, sbatte contro
i 429 e brucia tempo. Il ledger vive in data/llm_ledger.json (committato dalla
pipeline con il resto di data/) e tiene un contatore per ogni bucket
(provider:model:key_index).

Regola: si controlla PRIMA di chiamare, non dopo il 429.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_LEDGER_PATH = Path("data/llm_ledger.json")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _day_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _minute_key(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M")


class QuotaLedger:
    """Contatori RPM/RPD/TPM/TPD + cooldown per bucket, persistiti su disco."""

    def __init__(self, path: Optional[Path] = None, autosave: bool = True):
        self.path = Path(path) if path else DEFAULT_LEDGER_PATH
        self.autosave = autosave
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {"version": 1, "buckets": {}}
        self._load()

    # ------------------------------------------------------------------ io
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("buckets"), dict):
                self._state = raw
        except (OSError, ValueError):
            pass  # ledger assente o corrotto: si riparte pulito, non è fatale

    def save(self) -> None:
        """Scrittura atomica: una run interrotta non lascia un JSON monco."""
        with self._lock:
            self._state["updated_at"] = _utc_now().isoformat()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._state, f, ensure_ascii=False, indent=2, sort_keys=True)
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    # -------------------------------------------------------------- buckets
    def _bucket(self, key: str, now: datetime) -> Dict[str, Any]:
        b = self._state["buckets"].get(key)
        if not isinstance(b, dict):
            b = {}
            self._state["buckets"][key] = b
        day, minute = _day_key(now), _minute_key(now)
        if b.get("day") != day:
            b.update({"day": day, "rpd": 0, "tpd": 0})
        if b.get("minute") != minute:
            b.update({"minute": minute, "rpm": 0, "tpm": 0})
        b.setdefault("rpd", 0)
        b.setdefault("tpd", 0)
        b.setdefault("rpm", 0)
        b.setdefault("tpm", 0)
        b.setdefault("fail_streak", 0)
        b.setdefault("cooldown_until", None)
        return b

    def blocked_reason(
        self, key: str, limits: Dict[str, Any], est_tokens: int = 0,
        now: Optional[datetime] = None,
    ) -> Optional[str]:
        """None se il bucket è chiamabile, altrimenti il motivo dello stop."""
        now = now or _utc_now()
        with self._lock:
            b = self._bucket(key, now)
            cd = b.get("cooldown_until")
            if cd:
                try:
                    if datetime.fromisoformat(cd) > now:
                        return f"cooldown fino a {cd}"
                except ValueError:
                    b["cooldown_until"] = None
            for field, counter in (("rpm", "rpm"), ("rpd", "rpd")):
                cap = limits.get(field)
                if cap and b[counter] >= cap:
                    return f"{field} esaurito ({b[counter]}/{cap})"
            for field, counter in (("tpm", "tpm"), ("tpd", "tpd")):
                cap = limits.get(field)
                if cap and b[counter] + est_tokens > cap:
                    return f"{field} esaurito ({b[counter]}/{cap})"
        return None

    def record_success(self, key: str, tokens: int = 0, now: Optional[datetime] = None) -> None:
        now = now or _utc_now()
        with self._lock:
            b = self._bucket(key, now)
            b["rpm"] += 1
            b["rpd"] += 1
            b["tpm"] += max(0, tokens)
            b["tpd"] += max(0, tokens)
            b["fail_streak"] = 0
            b["cooldown_until"] = None
            b["last_ok"] = now.isoformat()
        if self.autosave:
            self.save()

    def record_failure(
        self, key: str, cooldown_s: int = 0, exhausted: str = "",
        now: Optional[datetime] = None,
    ) -> None:
        """
        exhausted: "" | "minute" | "day" — se la quota è finita, il bucket va
        in cooldown fino al confine temporale invece che per N secondi.
        """
        now = now or _utc_now()
        with self._lock:
            b = self._bucket(key, now)
            b["rpm"] += 1
            b["rpd"] += 1
            b["fail_streak"] = int(b.get("fail_streak", 0)) + 1
            b["last_error_at"] = now.isoformat()
            if exhausted == "day":
                # Spento fino al rollover UTC: il _bucket() lo azzera da solo.
                b["rpd"] = max(b["rpd"], 10 ** 9)
            elif exhausted == "minute":
                b["rpm"] = max(b["rpm"], 10 ** 9)
            elif cooldown_s > 0:
                b["cooldown_until"] = _iso_plus(now, cooldown_s)
        if self.autosave:
            self.save()

    def disable(self, key: str, seconds: int, now: Optional[datetime] = None) -> None:
        """Spegne un bucket (auth fallita, modello sparito, fail streak)."""
        now = now or _utc_now()
        with self._lock:
            self._bucket(key, now)["cooldown_until"] = _iso_plus(now, seconds)
        if self.autosave:
            self.save()

    def fail_streak(self, key: str, now: Optional[datetime] = None) -> int:
        now = now or _utc_now()
        with self._lock:
            return int(self._bucket(key, now).get("fail_streak", 0))

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))


def _iso_plus(now: datetime, seconds: int) -> str:
    return datetime.fromtimestamp(now.timestamp() + seconds, tz=timezone.utc).isoformat()
