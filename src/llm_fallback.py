#!/usr/bin/env python3
"""
LLM fallback OpenAI-compatible (Groq / OpenRouter).
Pattern copiato da global-scout: Gemini primary, questo quando free tier morto.
No grounding Google — solo parse di testo già scaricato (es. Tavily).
"""

from __future__ import annotations

import os
from typing import Optional

import requests

# Groq free tier TPM stretto — tieni prompt corti
GROQ_MAX_CHARS = 2800


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
    """Ordine: GROQ_API_KEY → OPENROUTER_API_KEY → None."""
    groq = _real_key("GROQ_API_KEY")
    if groq:
        return {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": groq,
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
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


def chat_json(prompt: str, system: str = "Rispondi solo con JSON valido.") -> str:
    """Una completion. Solleva RuntimeError se fallback assente o HTTP fail."""
    fb = resolve_fallback()
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
