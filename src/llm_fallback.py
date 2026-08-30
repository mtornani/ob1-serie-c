#!/usr/bin/env python3
"""
Shim di compatibilità verso il gateway LLM.

Storicamente questo modulo era "Groq o OpenRouter, uno a caso": una sola rotta,
nessuna contabilità, nessuna cache. Ora è un adattatore su src/llm/, che fa
routing multi-provider con budget free-tier persistente.

Le firme restano identiche (resolve_fallback / chat_json) per non toccare i
call site esistenti. Il vecchio percorso diretto resta disponibile con
OB1_LLM_GATEWAY=0, come via di fuga se il gateway dà problemi in produzione.
"""

from __future__ import annotations

import os
from typing import Optional

import requests

# Groq free tier TPM stretto — tieni prompt corti
GROQ_MAX_CHARS = 2800


def _gateway_enabled() -> bool:
    return os.getenv("OB1_LLM_GATEWAY", "1") != "0"


def _real_key(name: str) -> Optional[str]:
    """Reject empty / placeholder dotenv values (your_xxx)."""
    v = (os.getenv(name) or "").strip()
    if not v:
        return None
    low = v.lower()
    if low.startswith("your_") or low in ("placeholder", "xxx", "changeme"):
        return None
    if len(v) < 16:
        return None
    return v


def resolve_fallback() -> Optional[dict]:
    """
    Descrive la rotta che verrà usata. Serve ai call site solo per decidere
    "ho un LLM di riserva sì/no" e per loggarne il nome.
    """
    if _gateway_enabled():
        try:
            from src.llm import get_gateway
            gw = get_gateway()
            routes = gw.registry.routes_for("extract", allow_paid=gw.allow_paid)
            if routes:
                return {
                    "base_url": routes[0].base_url,
                    "api_key": routes[0].api_key,
                    "model": routes[0].model,
                    "label": f"gateway[{gw.registry.describe()}]",
                    "max_chars": routes[0].max_input_chars or 24000,
                }
        except Exception as e:  # config assente/rotta: si degrada al path legacy
            print(f"  [LLM] gateway non disponibile ({e}) — fallback legacy")

    groq = _real_key("GROQ_API_KEY")
    if groq:
        return {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": groq,
            # llama-3.3-70b-versatile ritirato da Groq (19 ago 2026, HTTP 404).
            # openai/gpt-oss-120b e' il rimpiazzo verificato in produzione su
            # OB1 Global, non indovinato qui. Vedi la stessa nota in
            # config/llm_providers.yaml (la rotta che il gateway usa davvero;
            # questo default e' solo il ripiego legacy se il gateway manca).
            "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            "label": "groq",
            "max_chars": GROQ_MAX_CHARS,
        }
    ork = _real_key("OPENROUTER_API_KEY")
    if ork:
        return {
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": ork,
            "model": os.getenv(
                "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
            ),
            "label": "openrouter",
            "max_chars": 6000,
        }
    return None


def chat_json(prompt: str, system: str = "Rispondi solo con JSON valido.",
              task: str = "extract") -> str:
    """
    Una completion JSON. Solleva RuntimeError se nessuna rotta risponde.
    Ritorna testo grezzo (il chiamante fa già il proprio parsing).
    """
    if _gateway_enabled():
        try:
            from src.llm import get_gateway
            res = get_gateway().complete_json(task, prompt, system=system)
            if res.ok:
                return res.raw
            # Nessuna rotta ha risposto: prima di arrendersi, prova il legacy.
            last = res.errors[-1] if res.errors else "no route"
            print(f"  [LLM] gateway KO ({last}) — provo path legacy")
        except Exception as e:
            print(f"  [LLM] gateway errore ({e}) — provo path legacy")

    fb = _legacy_route()
    if not fb:
        raise RuntimeError("no fallback LLM configured (GROQ_API_KEY / OPENROUTER_API_KEY)")
    max_c = fb.get("max_chars", 4000)
    if len(prompt) > max_c:
        prompt = prompt[:max_c] + "\n…"
    resp = requests.post(
        fb["base_url"].rstrip("/") + "/chat/completions",
        headers={
            "Authorization": f"Bearer {fb['api_key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": fb["model"],
            "temperature": 0.0,
            "max_tokens": 2048,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=90,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"{fb['label']} HTTP {resp.status_code}: {resp.text[:180]}")
    return resp.json()["choices"][0]["message"]["content"] or ""


def _legacy_route() -> Optional[dict]:
    """Groq -> OpenRouter, chiamata diretta senza gateway."""
    groq = _real_key("GROQ_API_KEY")
    if groq:
        return {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": groq,
            # llama-3.3-70b-versatile ritirato da Groq (19 ago 2026, HTTP 404).
            # openai/gpt-oss-120b e' il rimpiazzo verificato in produzione su
            # OB1 Global, non indovinato qui. Vedi la stessa nota in
            # config/llm_providers.yaml (la rotta che il gateway usa davvero;
            # questo default e' solo il ripiego legacy se il gateway manca).
            "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            "label": "groq",
            "max_chars": GROQ_MAX_CHARS,
        }
    ork = _real_key("OPENROUTER_API_KEY")
    if ork:
        return {
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": ork,
            "model": os.getenv(
                "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
            ),
            "label": "openrouter",
            "max_chars": 6000,
        }
    return None
