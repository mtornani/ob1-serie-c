#!/usr/bin/env python3
"""
LLM Gateway: un solo punto di uscita verso qualsiasi provider.

Cosa fa, in ordine:
  1. cache lookup   -> se c'è, zero chiamate
  2. routing        -> prima rotta disponibile per la task class (ledger-aware)
  3. chiamata       -> OpenAI-compatible /chat/completions
  4. failover       -> 429/5xx/JSON rotto => rotta successiva, non retry cieco
  5. contabilità    -> ledger + cache + metriche di run

Il chiamante non sa quale modello ha risposto, e non deve saperlo.

Uso:
    from src.llm import get_gateway
    res = get_gateway().complete_json("extract", prompt)
    if res.ok:
        data = res.data
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from .cache import ResponseCache
from .ledger import QuotaLedger
from .registry import Registry, Route

try:  # le metriche non devono mai poter rompere il gateway
    from src.metrics import get_metrics
except ImportError:  # layout PYTHONPATH=src
    try:
        from metrics import get_metrics
    except ImportError:
        get_metrics = None

DEFAULT_SYSTEM = "Sei un estrattore di dati. Rispondi SOLO con JSON valido, nessun testo attorno."

# Firma trasporto: (url, headers, payload, timeout) -> (status_code, body)
Transport = Callable[[str, Dict[str, str], Dict[str, Any], int], "tuple[int, Any]"]

_QUOTA_DAY_MARKERS = (
    "quota exceeded", "daily", "per day", "requests per day", "rpd",
    "billing", "insufficient", "credit", "free-models-per-day",
)

# I provider dicono quanto aspettare ("Please try again in 3m59s"). Fidarsi di
# quel numero è meglio che indovinare minuto/giorno dal testo: un 429 sul budget
# giornaliero può risolversi in secondi se la finestra è scorrevole.
_RETRY_AFTER_RE = re.compile(
    r"try again in\s+(?:(\d+)\s*m)?\s*(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)
_RETRY_AFTER_CAP_S = 6 * 3600


def _parse_retry_after(body: str) -> int:
    """Secondi di attesa suggeriti dal provider, 0 se non li dichiara."""
    m = _RETRY_AFTER_RE.search(body or "")
    if not m:
        return 0
    minutes = int(m.group(1) or 0)
    seconds = float(m.group(2) or 0)
    return min(int(minutes * 60 + seconds) + 1, _RETRY_AFTER_CAP_S)


def _requests_transport(url, headers, payload, timeout):
    import requests  # import locale: i test girano senza rete
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, r.text


@dataclass
class LLMResult:
    ok: bool
    data: Any = None
    raw: str = ""
    route: str = ""
    cached: bool = False
    attempts: int = 0
    tokens: int = 0
    latency_ms: int = 0
    errors: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # `if res:` == `if res.ok:`
        return self.ok


class LLMGateway:
    def __init__(
        self,
        registry: Optional[Registry] = None,
        ledger: Optional[QuotaLedger] = None,
        cache: Optional[ResponseCache] = None,
        transport: Optional[Transport] = None,
        prompt_version: str = "v1",
        verbose: bool = True,
    ):
        self.registry = registry or Registry.load()
        self.ledger = ledger or QuotaLedger()
        self.cache = cache if cache is not None else ResponseCache(
            enabled=os.getenv("OB1_LLM_CACHE", "1") != "0"
        )
        self.transport = transport or _requests_transport
        self.prompt_version = prompt_version
        self.verbose = verbose
        self.allow_paid = os.getenv("OB1_LLM_ALLOW_PAID", "0") == "1"
        # Output cliente: niente modelli con licenza non commerciale
        self.commercial_only = os.getenv("OB1_LLM_COMMERCIAL_ONLY", "1") == "1"
        self.allow_training = os.getenv("OB1_LLM_ALLOW_TRAINING", "1") == "1"
        self.defaults = self.registry.defaults
        self.stats: Dict[str, Any] = {
            "calls": 0, "cache_hits": 0, "failures": 0,
            "by_route": {}, "tokens": 0,
        }

    # ------------------------------------------------------------------ API
    def complete_json(
        self,
        task: str,
        prompt: str,
        system: str = DEFAULT_SYSTEM,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        cache_key_extra: str = "",
        use_cache: bool = True,
        max_routes: int = 4,
        exclude_providers: Optional[Iterable[str]] = None,
        only_providers: Optional[Iterable[str]] = None,
    ) -> LLMResult:
        """Una risposta JSON per `task`, dal primo provider che ce la fa."""
        tc = self.registry.task_class(task)
        prompt = _clamp(prompt, tc.max_input_chars)
        ck = ResponseCache.key(
            task, prompt + cache_key_extra, system,
            f"{self.prompt_version}:{tc.min_tier}",
        )

        if use_cache:
            hit = self.cache.get(ck, tc.cache_ttl_h)
            if hit and hit.get("raw"):
                self.stats["cache_hits"] += 1
                data = _parse_json(hit["raw"])
                if data is not None:
                    _metric("llm_cache_hit")
                    return LLMResult(True, data, hit["raw"], hit.get("route", "cache"),
                                     cached=True)

        routes = self._pick_routes(task, exclude_providers, only_providers)
        if not routes:
            return LLMResult(False, errors=[f"nessuna rotta disponibile per task '{task}'"])

        errors: List[str] = []
        attempts = 0
        for route in routes[:max_routes]:
            attempts += 1
            est_tokens = _estimate_tokens(prompt, system, max_tokens or self._default("max_tokens", 2048))
            blocked = self.ledger.blocked_reason(route.bucket, route.limits, est_tokens)
            if blocked:
                errors.append(f"{route.label}: skip ({blocked})")
                continue
            limit = route.max_input_chars or tc.max_input_chars
            payload_prompt = _clamp(prompt, limit)

            t0 = time.time()
            status, body, err = self._call(route, payload_prompt, system, max_tokens, temperature)
            latency = int((time.time() - t0) * 1000)

            if err:
                errors.append(f"{route.label}: {err}")
                self._penalize(route, status, str(body))
                continue

            raw = _content(body)
            tokens = _usage_tokens(body) or est_tokens
            self.ledger.record_success(route.bucket, tokens)
            self._bump(route, tokens)

            data = _parse_json(raw)
            if data is None:
                errors.append(f"{route.label}: JSON non parsabile")
                self._log(f"[LLM] {route.label} JSON rotto -> rotta successiva")
                continue

            if use_cache:
                self.cache.put(ck, {"raw": raw, "route": route.label, "task": task})
            self._log(f"[LLM] {task} <- {route.label} ({latency}ms, ~{tokens}tok)")
            return LLMResult(True, data, raw, route.label, attempts=attempts,
                             tokens=tokens, latency_ms=latency, errors=errors)

        self.stats["failures"] += 1
        _metric("llm_failure")
        self._log(f"[LLM] {task} FALLITO dopo {attempts} rotte: {'; '.join(errors[-3:])}")
        return LLMResult(False, attempts=attempts, errors=errors)

    def available_routes(self, task: str) -> List[str]:
        """Diagnostica: quali rotte sono chiamabili adesso per questa task."""
        out = []
        for r in self._pick_routes(task):
            blocked = self.ledger.blocked_reason(r.bucket, r.limits)
            out.append(f"{r.label} {'BLOCCATA: ' + blocked if blocked else 'ok'}")
        return out

    def run_summary(self) -> str:
        c = self.cache.stats()
        routes = ", ".join(f"{k}={v}" for k, v in sorted(self.stats["by_route"].items())) or "-"
        return (
            f"[LLM SUMMARY] chiamate={self.stats['calls']} "
            f"cache_hit={self.stats['cache_hits']} ({c['hit_rate_pct']}%) "
            f"fallimenti={self.stats['failures']} tokens≈{self.stats['tokens']} | {routes}"
        )

    # -------------------------------------------------------------- interni
    def _pick_routes(
        self, task: str,
        exclude_providers: Optional[Iterable[str]] = None,
        only_providers: Optional[Iterable[str]] = None,
    ) -> List[Route]:
        return self.registry.routes_for(
            task,
            allow_paid=self.allow_paid,
            commercial_only=self.commercial_only,
            allow_training=self.allow_training,
            exclude_providers=exclude_providers,
            only_providers=only_providers,
        )

    def _default(self, key: str, fallback: Any) -> Any:
        v = self.defaults.get(key)
        return fallback if v is None else v

    def _call(self, route: Route, prompt: str, system: str,
              max_tokens: Optional[int], temperature: Optional[float]):
        payload: Dict[str, Any] = {
            "model": route.model,
            "temperature": self._default("temperature", 0.0) if temperature is None else temperature,
            "max_tokens": max_tokens or self._default("max_tokens", 2048),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        if route.json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {route.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(route.extra_headers)
        url = f"{route.base_url}/chat/completions"
        try:
            status, body = self.transport(url, headers, payload, int(self._default("timeout_s", 90)))
        except Exception as e:  # rete, DNS, timeout
            return 0, "", f"transport: {type(e).__name__}: {str(e)[:120]}"
        if status != 200:
            return status, body, f"HTTP {status}: {str(body)[:160]}"
        if not _content(body):
            return status, body, "risposta vuota"
        return status, body, ""

    def _penalize(self, route: Route, status: int, body: str) -> None:
        low = (body or "").lower()
        if status in (401, 403):
            # Chiave sbagliata/revocata: inutile riprovare oggi.
            self.ledger.disable(route.bucket, 86400)
            self._log(f"[LLM] {route.label} auth fallita -> bucket spento 24h")
            return
        if status == 429:
            # Prima si guarda cosa dice il provider: "try again in 24.5s" è un
            # dato, "sembra un limite giornaliero" è una congettura. Senza il
            # retry-after un 429 sul budget a finestra scorrevole spegnerebbe la
            # rotta fino a mezzanotte UTC — che su una sola rotta libera vuol
            # dire fermare la pipeline per un giorno intero.
            wait = _parse_retry_after(body)
            if wait:
                self.ledger.record_failure(route.bucket, cooldown_s=wait)
                self._log(f"[LLM] {route.label} 429, riprovabile tra {wait}s -> rotta successiva")
                return
            exhausted = "day" if any(m in low for m in _QUOTA_DAY_MARKERS) else "minute"
            self.ledger.record_failure(route.bucket, exhausted=exhausted)
            self._log(f"[LLM] {route.label} 429 ({exhausted}) -> rotta successiva")
            return
        cooldown = int(self._default("cooldown_transient_s", 60))
        self.ledger.record_failure(route.bucket, cooldown_s=cooldown)
        if self.ledger.fail_streak(route.bucket) >= int(self._default("fail_streak_limit", 3)):
            self.ledger.disable(route.bucket, 3600)
            self._log(f"[LLM] {route.label} fail streak -> bucket spento 1h")

    def _bump(self, route: Route, tokens: int) -> None:
        _metric("llm_call", route.label, tokens)
        self.stats["calls"] += 1
        self.stats["tokens"] += tokens
        self.stats["by_route"][route.label] = self.stats["by_route"].get(route.label, 0) + 1

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"  {msg}")


# ------------------------------------------------------------------ helpers
def _metric(name: str, *args) -> None:
    """Contatore ARCH-002. Silenzioso se il modulo metriche non c'è."""
    if get_metrics is None:
        return
    try:
        getattr(get_metrics(), name)(*args)
    except Exception:  # una metrica rotta non ferma un'inferenza riuscita
        pass


def _clamp(text: str, max_chars: Optional[int]) -> str:
    if max_chars and len(text) > max_chars:
        return text[:max_chars] + "\n…[troncato]"
    return text


def _estimate_tokens(prompt: str, system: str, max_out: int) -> int:
    """~4 caratteri per token: basta per non sfondare i tetti TPM/TPD."""
    return (len(prompt) + len(system)) // 4 + int(max_out)


def _content(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    try:
        return body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def _usage_tokens(body: Any) -> int:
    if not isinstance(body, dict):
        return 0
    usage = body.get("usage") or {}
    try:
        return int(usage.get("total_tokens") or 0)
    except (TypeError, ValueError):
        return 0


def _parse_json(text: str) -> Any:
    """JSON da testo LLM: toglie i fence, poi prende il primo oggetto/array."""
    if not text:
        return None
    t = re.sub(r"^```(?:json)?\s*", "", text.strip())
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        pass
    m = re.search(r"[\{\[].*[\}\]]", t, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


_GATEWAY: Optional[LLMGateway] = None


def get_gateway(config_path: Optional[Path] = None) -> LLMGateway:
    """Singleton di processo: una sola istanza condivide ledger e cache."""
    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = LLMGateway(registry=Registry.load(config_path))
    return _GATEWAY


def reset_gateway() -> None:
    global _GATEWAY
    _GATEWAY = None
