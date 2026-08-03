#!/usr/bin/env python3
"""
Cache risposte LLM su disco.

È la leva di costo più grande della pipeline: lo stesso giocatore viene
rivalutato a ogni run (4/giorno) e il contenuto della pagina TM cambia una
volta a settimana, non ogni sei ore. Cache hit = zero token, zero latenza,
zero quota consumata.

Chiave = sha256(task | prompt_version | modello logico | prompt | system).
Il modello FISICO non entra nella chiave: se domani lo stesso prompt esce da
Cerebras invece che da Groq, la risposta cachata resta valida.

I file stanno in data/llm_cache/ (gitignorata): sopravvivono tra le run via
artifact GitHub Actions, non gonfiano il repo.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CACHE_DIR = Path("data/llm_cache")


class ResponseCache:
    def __init__(self, directory: Optional[Path] = None, enabled: bool = True):
        self.dir = Path(directory) if directory else DEFAULT_CACHE_DIR
        self.enabled = enabled
        self.hits = 0
        self.misses = 0
        self.writes = 0

    @staticmethod
    def key(task: str, prompt: str, system: str = "", prompt_version: str = "v1") -> str:
        h = hashlib.sha256()
        for part in (task, prompt_version, system, prompt):
            h.update(part.encode("utf-8", "replace"))
            h.update(b"\x00")
        return h.hexdigest()

    def _path(self, key: str) -> Path:
        return self.dir / key[:2] / f"{key}.json"

    def get(self, key: str, ttl_h: float) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        p = self._path(key)
        try:
            entry = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.misses += 1
            return None
        if ttl_h and (time.time() - float(entry.get("stored_at", 0))) > ttl_h * 3600:
            self.misses += 1
            return None
        self.hits += 1
        return entry

    def put(self, key: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        entry = dict(payload)
        entry["stored_at"] = time.time()
        fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False)
            os.replace(tmp, p)
            self.writes += 1
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def prune(self, max_age_h: float = 720) -> int:
        """Elimina le entry oltre max_age_h. Da chiamare a fine pipeline."""
        if not self.dir.exists():
            return 0
        cutoff = time.time() - max_age_h * 3600
        removed = 0
        for p in self.dir.rglob("*.json"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    def stats(self) -> Dict[str, int]:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "hit_rate_pct": round(100 * self.hits / total) if total else 0,
        }
