#!/usr/bin/env python3
"""
Registry provider: YAML -> lista di rotte ordinate per priorità.

Una "rotta" è la coppia (modello, chiave API). Due chiavi sullo stesso
provider = due rotte indipendenti, ognuna con il proprio budget nel ledger:
è così che si scala orizzontalmente sul free tier senza pagare nulla.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

DEFAULT_CONFIG_PATH = Path("config/llm_providers.yaml")

TIER_ORDER = {"nano": 0, "small": 1, "mid": 2, "frontier": 3}

_PLACEHOLDER_PREFIXES = ("your_", "changeme", "placeholder", "xxx", "<")


def _real_keys(env_name: str) -> List[str]:
    """Chiavi reali da una env var (supporta 'k1,k2' per lo sharding)."""
    raw = (os.getenv(env_name) or "").strip()
    if not raw:
        return []
    out = []
    for chunk in raw.split(","):
        v = chunk.strip()
        if len(v) < 16:
            continue
        if v.lower().startswith(_PLACEHOLDER_PREFIXES):
            continue
        out.append(v)
    return out


@dataclass
class Route:
    provider: str
    base_url: str
    model: str
    api_key: str
    key_index: int
    tier: str
    context: int
    json_mode: bool
    priority: int
    limits: Dict[str, Any]
    tasks: List[str]
    max_input_chars: Optional[int]
    commercial_use: bool
    trains_on_data: bool
    paid: bool
    extra_headers: Dict[str, str] = field(default_factory=dict)

    @property
    def bucket(self) -> str:
        """Identificatore stabile nel ledger. La chiave API non ci finisce."""
        return f"{self.provider}:{self.model}:{self.key_index}"

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass
class TaskClass:
    name: str
    min_tier: str = "small"
    max_input_chars: int = 24000
    cache_ttl_h: float = 168.0


class Registry:
    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.defaults: Dict[str, Any] = self.config.get("defaults") or {}
        self.task_classes: Dict[str, TaskClass] = {}
        for name, spec in (self.config.get("task_classes") or {}).items():
            spec = spec or {}
            self.task_classes[name] = TaskClass(
                name=name,
                min_tier=spec.get("min_tier", "small"),
                max_input_chars=int(spec.get("max_input_chars", 24000)),
                cache_ttl_h=float(spec.get("cache_ttl_h", 168)),
            )
        self.routes: List[Route] = self._build_routes()

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Registry":
        p = Path(path) if path else DEFAULT_CONFIG_PATH
        with open(p, "r", encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    def _build_routes(self) -> List[Route]:
        routes: List[Route] = []
        for prov in self.config.get("providers") or []:
            # base_url può venire da env (endpoint locali tipo COMPARE_BASE_URL)
            base_url = prov.get("base_url") or ""
            if prov.get("base_url_env"):
                base_url = (os.getenv(prov["base_url_env"]) or "").strip() or base_url
            if not base_url:
                continue
            keys = _real_keys(prov.get("api_key_env", ""))
            if not keys and prov.get("requires_key", True) is False:
                keys = ["local"]  # endpoint senza autenticazione
            if not keys:
                continue  # provider non configurato: si salta in silenzio
            limits = prov.get("limits") or {}
            for model in prov.get("models") or []:
                name = model.get("name") or ""
                if model.get("name_env"):
                    name = (os.getenv(model["name_env"]) or "").strip() or name
                if not name:
                    continue
                for idx, key in enumerate(keys):
                    routes.append(Route(
                        provider=prov["id"],
                        base_url=base_url.rstrip("/"),
                        model=name,
                        api_key=key,
                        key_index=idx,
                        tier=model.get("tier", "small"),
                        context=int(model.get("context", 32000)),
                        json_mode=bool(model.get("json_mode", False)),
                        priority=int(model.get("priority", 500)),
                        limits=limits,
                        tasks=list(model.get("tasks") or []),
                        max_input_chars=model.get("max_input_chars"),
                        commercial_use=bool(prov.get("commercial_use", True)),
                        trains_on_data=bool(prov.get("trains_on_data", False)),
                        paid=bool(prov.get("paid", False)),
                        extra_headers=dict(prov.get("extra_headers") or {}),
                    ))
        routes.sort(key=lambda r: (r.priority, r.provider, r.key_index))
        return routes

    def task_class(self, name: str) -> TaskClass:
        return self.task_classes.get(name) or TaskClass(name=name)

    def routes_for(
        self, task: str, allow_paid: bool = False,
        commercial_only: bool = False, allow_training: bool = True,
        exclude_providers: Optional[Iterable[str]] = None,
        only_providers: Optional[Iterable[str]] = None,
    ) -> List[Route]:
        tc = self.task_class(task)
        floor = TIER_ORDER.get(tc.min_tier, 1)
        excluded = set(exclude_providers or ())
        included = set(only_providers or ())
        out = []
        for r in self.routes:
            if task not in r.tasks:
                continue
            if r.provider in excluded:
                continue
            if included and r.provider not in included:
                continue
            if TIER_ORDER.get(r.tier, 0) < floor:
                continue
            if r.paid and not allow_paid:
                continue
            if commercial_only and not r.commercial_use:
                continue
            if not allow_training and r.trains_on_data:
                continue
            out.append(r)
        return out

    def describe(self) -> str:
        if not self.routes:
            return "nessun provider configurato"
        by_provider: Dict[str, int] = {}
        for r in self.routes:
            by_provider[r.provider] = by_provider.get(r.provider, 0) + 1
        return ", ".join(f"{k}({v})" for k, v in sorted(by_provider.items()))
