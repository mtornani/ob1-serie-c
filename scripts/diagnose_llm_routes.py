#!/usr/bin/env python3
"""
OB1 Lega Pro — stato reale delle rotte LLM configurate

Perché
------
Tre volte in due giorni una rotta è stata dichiarata morta e sostituita a
naso, e due volte il nome di rimpiazzo era sbagliato quanto l'originale
(vedi le note in config/llm_providers.yaml su groq e openrouter). Il punto
non è indovinare meglio: è smettere di indovinare. Ogni provider espone
`GET /v1/models`, cioè il proprio catalogo autoritativo. Questo script lo
chiede, e poi prova davvero ogni rotta configurata.

Risponde a due domande diverse, che vanno tenute separate:

  1. il MODELLO esiste ancora nel catalogo del provider?
     -> se no, il nome in config è stantio: il catalogo dice come si chiama
        adesso, senza che nessuno debba tirare a indovinare.
  2. la CHIAVE funziona e la rotta risponde davvero?
     -> un modello può essere in catalogo ed essere comunque irraggiungibile
        col piano corrente (il classico "unavailable for free").

Un 404 sul catalogo e un 404 su una singola chiamata vogliono dire cose
opposte, e confonderli è esattamente l'errore che ha bruciato PR #48/#49.

Zero effetti collaterali: non tocca database, feed o seen-store. La prova
di ogni rotta è un prompt da poche decine di token con max_tokens basso,
per non erodere il free tier che stiamo cercando di preservare.

Uso
---
Da .github/workflows/diagnose-llm-routes.yml (dispatch manuale), con TUTTE
le chiavi in ambiente: qui il fallback silenzioso non è un rischio ma lo
scopo — vogliamo sapere di ognuna se è viva, non farne funzionare una.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.registry import Registry, Route  # noqa: E402

# Prova volutamente minima: verifica che la rotta risponda, non che ragioni.
PROBE_PROMPT = "Rispondi con la sola parola: ok"
# 8 token sembravano abbondanti per una risposta di una parola, e hanno fatto
# risultare morte due rotte che in produzione servivano decine di chiamate
# (groq/gpt-oss-120b e compare/gpt-oss:20b, run del 30 ago 2026). I modelli
# reasoning spendono token in ragionamento PRIMA del contenuto: con un tetto
# basso il budget finisce lì e `content` torna vuoto. La rotta è viva, è la
# misura a essere sbagliata — e una misura che condanna chi funziona è peggio
# che nessuna misura. Il costo di 512 token su una prova manuale è irrilevante
# rispetto al free tier che stiamo cercando di proteggere.
PROBE_MAX_TOKENS = 512
PROBE_TIMEOUT_S = 60
CATALOG_TIMEOUT_S = 30
# Gli errori utili sono lunghi: OpenRouter, quando un modello esce dal tier
# free, risponde "use this slug instead: <nome>" — cioè il rimpiazzo esatto,
# che a 120 caratteri veniva troncato via proprio mentre lo cercavamo.
ERR_SNIPPET = 400


def _mask(key: str) -> str:
    """Forma della chiave, mai il valore. Serve a distinguere 'assente' da
    'presente ma rifiutata' leggendo un log pubblico di GitHub Actions."""
    if not key:
        return "(assente)"
    if key == "local":
        return "(nessuna: endpoint keyless)"
    return f"(impostata, {len(key)} char)"


def fetch_catalog(base_url: str, api_key: str,
                  extra_headers: Dict[str, str]) -> Tuple[Optional[List[str]], str]:
    """
    Catalogo modelli del provider via GET /models (standard OpenAI).

    Ritorna (lista_id, nota). lista_id è None quando il catalogo non è
    interrogabile — che NON vuol dire che il provider sia morto: alcuni
    endpoint compatibili non espongono /models pur servendo /chat/completions.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    headers.update(extra_headers)
    try:
        r = requests.get(f"{base_url}/models", headers=headers,
                         timeout=CATALOG_TIMEOUT_S)
    except Exception as e:
        return None, f"irraggiungibile ({type(e).__name__})"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        payload = r.json()
    except ValueError:
        return None, "risposta non JSON"
    data = payload.get("data")
    if not isinstance(data, list):
        return None, "formato inatteso"
    ids = [m.get("id", "") for m in data if isinstance(m, dict) and m.get("id")]
    return sorted(ids), f"{len(ids)} modelli"


def probe_model(base_url: str, api_key: str, model: str, json_mode: bool,
                extra_headers: Dict[str, str]) -> Tuple[bool, str, float]:
    """
    Una chiamata vera. Ritorna (ok, dettaglio, secondi).

    `json_mode` replica quello che il gateway fa in produzione: un modello che
    non supporta response_format va saputo QUI, non al primo run del cron.
    """
    payload: Dict[str, object] = {
        "model": model,
        "temperature": 0.0,
        "max_tokens": PROBE_MAX_TOKENS,
        "messages": [{"role": "user", "content": PROBE_PROMPT}],
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
        payload["messages"] = [{"role": "user",
                                "content": PROBE_PROMPT + ' (formato: {"esito":"ok"})'}]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers)
    t0 = time.time()
    try:
        r = requests.post(f"{base_url}/chat/completions", headers=headers,
                          json=payload, timeout=PROBE_TIMEOUT_S)
    except Exception as e:
        return False, f"trasporto: {type(e).__name__}", time.time() - t0
    dt = time.time() - t0
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text[:ERR_SNIPPET]}", dt
    try:
        msg = r.json()["choices"][0]["message"]
    except Exception:
        return False, f"risposta illeggibile: {r.text[:ERR_SNIPPET]}", dt
    content = (msg.get("content") or "").strip()
    if content:
        return True, content[:60].replace("\n", " "), dt
    # Contenuto vuoto ma ragionamento presente: il modello ha risposto, il
    # tetto di token è finito prima del testo finale. È un limite della prova,
    # non della rotta — distinguerlo evita di condannare un modello che in
    # produzione (con max_tokens veri) funziona benissimo.
    reasoning = (msg.get("reasoning_content") or msg.get("reasoning") or "")
    if str(reasoning).strip():
        return True, "(solo reasoning: rotta viva, tetto token della prova)", dt
    return False, "risposta vuota (200 ma nessun contenuto)", dt


def probe_route(route: Route) -> Tuple[bool, str, float]:
    return probe_model(route.base_url, route.api_key, route.model,
                       route.json_mode, route.extra_headers)


def main() -> int:
    reg = Registry.load()
    if not reg.routes:
        print("Nessuna rotta configurata — controllare config/llm_providers.yaml")
        return 1

    print("=== Rotte LLM configurate: stato reale ===\n")

    # Le rotte sono (modello x chiave): per il catalogo basta un giro per provider.
    per_provider: Dict[str, List[Route]] = {}
    for r in reg.routes:
        per_provider.setdefault(r.provider, []).append(r)

    vivi: List[str] = []
    morti: List[str] = []

    for provider, routes in per_provider.items():
        first = routes[0]
        print(f"--- {provider} · {first.base_url} · chiave {_mask(first.api_key)}")

        catalog, nota = fetch_catalog(first.base_url, first.api_key,
                                      first.extra_headers)
        print(f"    catalogo /models: {nota}")

        for route in routes:
            in_catalogo = ""
            if catalog is not None:
                in_catalogo = ("in catalogo" if route.model in catalog
                               else "NON in catalogo")
            ok, dettaglio, dt = probe_route(route)
            esito = "OK  " if ok else "KO  "
            riga = f"    {esito} {route.model} ({dt:.1f}s)"
            if in_catalogo:
                riga += f" [{in_catalogo}]"
            print(riga)
            if not ok:
                print(f"         -> {dettaglio}")
            (vivi if ok else morti).append(f"{provider}/{route.model}")

        # Il catalogo serve a chi dovrà scegliere un rimpiazzo: senza questa
        # lista si torna a indovinare. Mostrato solo se qualcosa non torna,
        # per non seppellire il log quando va tutto bene.
        if catalog and any(r.model not in catalog for r in routes):
            print(f"    catalogo reale di {provider} ({len(catalog)} modelli):")
            for mid in catalog:
                print(f"      · {mid}")
        print()

    print("=== riepilogo ===")
    print(f"rotte vive: {len(vivi)}")
    for v in vivi:
        print(f"  OK  {v}")
    print(f"rotte morte: {len(morti)}")
    for m in morti:
        print(f"  KO  {m}")

    # Quali task restano scoperti: è la domanda che conta davvero per la
    # pipeline, più del conteggio totale delle rotte.
    print("\n=== copertura per task ===")
    for task in ("triage", "extract", "reason"):
        candidate = reg.routes_for(task)
        vive = [r for r in candidate if f"{r.provider}/{r.model}" in vivi]
        stato = "OK" if vive else "SCOPERTO"
        print(f"  {task}: {len(vive)}/{len(candidate)} rotte vive [{stato}]")
        for r in vive:
            print(f"      · {r.provider}/{r.model} (priority {r.priority})")

    probe_candidates(per_provider)
    return 0


def probe_candidates(per_provider: Dict[str, List[Route]]) -> None:
    """
    Prova modelli NON ancora in config, riusando la chiave del loro provider.

    Serve a scegliere un rimpiazzo avendolo visto rispondere, invece di
    metterlo in config e scoprire al prossimo cron che era sbagliato — che è
    esattamente come sono nati i 404 di groq, openrouter e nvidia.

    Formato: OB1_PROBE_EXTRA="provider=modello,provider=modello"
    """
    raw = (os.getenv("OB1_PROBE_EXTRA") or "").strip()
    if not raw:
        return
    print("\n=== candidati (non in config) ===")
    for chunk in raw.split(","):
        if "=" not in chunk:
            continue
        provider, _, model = chunk.strip().partition("=")
        provider, model = provider.strip(), model.strip()
        routes = per_provider.get(provider)
        if not routes:
            print(f"  ??  {provider}: provider sconosciuto o senza chiave")
            continue
        ref = routes[0]
        # json_mode acceso: è come lo userebbe la pipeline, e un modello che
        # non lo supporta va scartato adesso, non in produzione.
        ok, dettaglio, dt = probe_model(ref.base_url, ref.api_key, model,
                                        json_mode=True,
                                        extra_headers=ref.extra_headers)
        print(f"  {'OK ' if ok else 'KO '} {provider}/{model} ({dt:.1f}s)")
        print(f"       -> {dettaglio}")


if __name__ == "__main__":
    raise SystemExit(main())
