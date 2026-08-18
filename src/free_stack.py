#!/usr/bin/env python3
"""
Free stack: ricerca web e LLM senza chiavi obbligatorie.

Due regole:
  - la ricerca NON deve richiedere Serper (DuckDuckGo e SearXNG non hanno chiave)
  - l'inferenza NON deve richiedere Gemini (basta GROQ_API_KEY, o qualsiasi
    altra rotta free del gateway)

Catena ricerca:   cache disco (7g) -> DuckDuckGo -> SearXNG -> Tavily* -> Serper*
Catena LLM:       gateway free (Cerebras/Groq/Mistral/OpenRouter/NVIDIA/COMPARE)
                  -> Gemini in coda
(* solo se la chiave c'è: sono opzionali, non requisiti)

Modi (env):
  OB1_SEARCH_MODE=serper       Serper per primo (legacy), free dopo
  OB1_LLM_MODE=free_first      default: free, poi Gemini
  OB1_LLM_MODE=free_only       Gemini mai
  OB1_LLM_MODE=gemini_first    Gemini per primo, free come rete
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import requests

try:  # le metriche non devono mai poter rompere una ricerca
    from src.metrics import get_metrics
except ImportError:  # layout PYTHONPATH=src
    try:
        from metrics import get_metrics
    except ImportError:
        get_metrics = None


def _metric(name: str, *args) -> None:
    """Contatore ARCH-002 (costo per fatto nuovo). Silenzioso se assente."""
    if get_metrics is None:
        return
    try:
        getattr(get_metrics(), name)(*args)
    except Exception:
        pass


SEARCH_CACHE_DIR = Path("data/search_cache")
SEARCH_CACHE_TTL_S = 7 * 24 * 3600

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_DEFAULT_SEARXNG = [
    "https://searx.be",
    "https://search.bus-hit.me",
    "https://searxng.site",
]

# Un risultato: {"title", "url", "content", "source"}
SearchResults = List[Dict[str, str]]


# ============================================================ modi / capacità
def search_mode() -> str:
    return (os.getenv("OB1_SEARCH_MODE") or "free_first").strip().lower()


def llm_mode() -> str:
    mode = (os.getenv("OB1_LLM_MODE") or "free_first").strip().lower()
    return mode if mode in ("free_first", "free_only", "gemini_first") else "free_first"


def _real_key(name: str) -> Optional[str]:
    v = (os.getenv(name) or "").strip()
    if not v or len(v) < 16:
        return None
    if v.lower().startswith(("your_", "changeme", "placeholder", "xxx", "<")):
        return None
    return v


def _gateway():
    """Gateway LLM, o None se il layer non è disponibile."""
    try:
        from src.llm import get_gateway
        return get_gateway()
    except Exception:
        try:
            from llm import get_gateway  # PYTHONPATH=src
            return get_gateway()
        except Exception:
            return None


def free_llm_routes() -> List[str]:
    """Rotte LLM gratuite disponibili adesso, Gemini escluso."""
    gw = _gateway()
    if not gw:
        return []
    routes = gw.registry.routes_for("extract", allow_paid=False)
    return [r.label for r in routes if r.provider != "gemini"]


def has_any_llm(free_only: Optional[bool] = None) -> bool:
    """
    True se esiste almeno una via per fare inferenza.
    free_only=None -> lo decide OB1_LLM_MODE.
    """
    if free_only is None:
        free_only = llm_mode() == "free_only"
    if free_llm_routes():
        return True
    return bool(not free_only and _real_key("GEMINI_API_KEY"))


def describe_stack() -> str:
    free = free_llm_routes()
    gem = "gemini" if _real_key("GEMINI_API_KEY") else "-"
    search = ["ddg", "searxng"]
    if _real_key("TAVILY_API_KEY"):
        search.append("tavily")
    if _real_key("SERPER_API_KEY"):
        search.append("serper")
    return (f"search[{'>'.join(search)}] llm_free[{len(free)}: {', '.join(free[:4]) or '-'}] "
            f"gemini[{gem}] mode[{llm_mode()}]")


# ==================================================================== cache
def _cache_path(query: str, domains: Optional[List[str]]) -> Path:
    h = hashlib.sha256(f"{query}|{','.join(sorted(domains or []))}".encode("utf-8")).hexdigest()
    return SEARCH_CACHE_DIR / h[:2] / f"{h}.json"


def _cache_get(query: str, domains: Optional[List[str]]) -> Optional[Tuple[str, SearchResults]]:
    if os.getenv("OB1_SEARCH_CACHE", "1") == "0":
        return None
    p = _cache_path(query, domains)
    try:
        entry = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - float(entry.get("stored_at", 0)) > SEARCH_CACHE_TTL_S:
        return None
    results = entry.get("results") or []
    if not results:
        return None
    return f"cache:{entry.get('source', '?')}", results


def _cache_put(query: str, domains: Optional[List[str]], source: str, results: SearchResults) -> None:
    if os.getenv("OB1_SEARCH_CACHE", "1") == "0" or not results:
        return
    p = _cache_path(query, domains)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"stored_at": time.time(), "query": query, "source": source, "results": results},
            ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# ============================================================ provider search
def _strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _unwrap_ddg(href: str) -> str:
    """DDG incapsula i link in /l/?uddg=<url encoded>."""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "/l/?" in href or "uddg=" in href:
        qs = parse_qs(urlparse(href).query)
        if qs.get("uddg"):
            return unquote(qs["uddg"][0])
    return href


def _with_domains(query: str, domains: Optional[List[str]]) -> str:
    """site: bias per i motori senza parametro dedicato."""
    if not domains:
        return query
    picked = domains[:5]
    if len(picked) == 1:
        return f"site:{picked[0]} {query}"
    return "(" + " OR ".join(f"site:{d}" for d in picked) + f") {query}"


# DDG non ha rate limit dichiarati: risponde 202 con una pagina anti-bot
# ("anomaly") quando le richieste arrivano troppo fitte. Va distinto da
# "nessun risultato", altrimenti un blocco si traveste da giocatore non trovato
# e l'entry resta silenziosamente senza dati.
_DDG_MIN_INTERVAL_S = 2.5
_DDG_BLOCK_COOLDOWN_S = 900
_ddg_state = {"last_call": 0.0, "blocked_until": 0.0}


def ddg_blocked() -> bool:
    return time.time() < _ddg_state["blocked_until"]


def _is_ddg_block(status: int, body: str) -> bool:
    if status == 202:
        return True
    low = (body or "")[:4000].lower()
    return "anomaly" in low or "unfortunately, bots" in low


def search_duckduckgo(query: str, max_results: int = 8,
                      domains: Optional[List[str]] = None) -> SearchResults:
    """DDG HTML endpoint: nessuna chiave, nessuna registrazione."""
    if ddg_blocked():
        return []
    q = _with_domains(query, domains)
    for endpoint in ("https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/"):
        # Throttle lato nostro: le richieste fitte sono ciò che fa scattare il blocco
        gap = time.time() - _ddg_state["last_call"]
        if gap < _DDG_MIN_INTERVAL_S:
            time.sleep(_DDG_MIN_INTERVAL_S - gap)
        try:
            resp = requests.post(
                endpoint, data={"q": q, "kl": "it-it"},
                headers={"User-Agent": _UA, "Accept-Language": "it-IT,it;q=0.9"},
                timeout=20,
            )
        except requests.RequestException:
            continue
        finally:
            _ddg_state["last_call"] = time.time()

        if _is_ddg_block(resp.status_code, resp.text):
            _ddg_state["blocked_until"] = time.time() + _DDG_BLOCK_COOLDOWN_S
            print(f"    [SEARCH ddg] BLOCCATO (HTTP {resp.status_code}, pagina anti-bot) "
                  f"— fuori per {_DDG_BLOCK_COOLDOWN_S // 60} min, passo al provider dopo")
            return []
        if resp.status_code != 200:
            continue
        results = _parse_ddg_html(resp.text, max_results)
        if results:
            return results
    return []


def _parse_ddg_html(body: str, max_results: int) -> SearchResults:
    out: SearchResults = []
    seen = set()
    blocks = re.findall(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        body, re.S | re.I)
    if not blocks:  # lite endpoint: tabella con link nudi
        blocks = re.findall(r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                            body, re.S | re.I)
    snippets = [_strip_tags(s) for s in re.findall(
        r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', body, re.S | re.I)]
    for i, (href, title) in enumerate(blocks):
        url = _unwrap_ddg(html.unescape(href))
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        out.append({
            "title": _strip_tags(title),
            "url": url,
            "content": snippets[i] if i < len(snippets) else "",
            "source": "duckduckgo",
        })
        if len(out) >= max_results:
            break
    return out


_searxng_dead = set()  # istanze che hanno già fallito in questa run


def search_searxng(query: str, max_results: int = 8,
                   domains: Optional[List[str]] = None) -> SearchResults:
    """
    Istanze SearXNG pubbliche. La maggior parte disabilita il format json o
    rate-limita gli anonimi: un'istanza che fallisce viene esclusa per il resto
    della run invece di essere ritentata a ogni query.
    """
    raw = (os.getenv("SEARXNG_INSTANCES") or "").strip()
    instances = [i.strip().rstrip("/") for i in raw.split(",") if i.strip()] or _DEFAULT_SEARXNG
    q = _with_domains(query, domains)
    for inst in instances[:4]:
        if inst in _searxng_dead:
            continue
        try:
            resp = requests.get(
                f"{inst}/search",
                params={"q": q, "format": "json", "language": "it", "safesearch": 0},
                headers={"User-Agent": _UA}, timeout=20,
            )
            if resp.status_code != 200 or "json" not in resp.headers.get("content-type", ""):
                _searxng_dead.add(inst)
                continue
            items = (resp.json() or {}).get("results") or []
        except (requests.RequestException, ValueError):
            _searxng_dead.add(inst)
            continue
        out = [{
            "title": str(it.get("title") or ""),
            "url": str(it.get("url") or ""),
            "content": str(it.get("content") or ""),
            "source": "searxng",
        } for it in items[:max_results] if it.get("url")]
        if out:
            return out
    return []


def search_tavily(query: str, max_results: int = 8, domains: Optional[List[str]] = None,
                  raw_content: bool = False) -> SearchResults:
    key = _real_key("TAVILY_API_KEY")
    if not key:
        return []
    payload: Dict[str, Any] = {
        "api_key": key, "query": query, "search_depth": "basic",
        "max_results": max_results, "include_raw_content": raw_content,
    }
    if domains:
        payload["include_domains"] = domains
    try:
        resp = requests.post("https://api.tavily.com/search", json=payload, timeout=30)
        if resp.status_code != 200:
            # Prima restava un return [] muto: un errore diverso da "chiave
            # assente" (scaduta, quota, API cambiata) finiva indistinguibile
            # da "nessun risultato", e il chiamante (free_web_search) non
            # vede questo ramo per loggarlo — non solleva un'eccezione.
            print(f"    [SEARCH tavily] HTTP {resp.status_code}: {resp.text[:120]}")
            return []
        items = (resp.json() or {}).get("results") or []
    except (requests.RequestException, ValueError) as e:
        print(f"    [SEARCH tavily] {type(e).__name__}: {str(e)[:120]}")
        return []
    return [{
        "title": str(it.get("title") or ""),
        "url": str(it.get("url") or ""),
        "content": str(it.get("raw_content") or it.get("content") or ""),
        "source": "tavily",
    } for it in items if it.get("url")]


def search_serper(query: str, max_results: int = 8,
                  domains: Optional[List[str]] = None) -> SearchResults:
    key = _real_key("SERPER_API_KEY")
    if not key:
        return []
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": _with_domains(query, domains), "gl": "it", "hl": "it",
                  "num": max_results},
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"    [SEARCH serper] HTTP {resp.status_code}: {resp.text[:120]}")
            return []
        items = (resp.json() or {}).get("organic") or []
    except (requests.RequestException, ValueError) as e:
        print(f"    [SEARCH serper] {type(e).__name__}: {str(e)[:120]}")
        return []
    return [{
        "title": str(it.get("title") or ""),
        "url": str(it.get("link") or ""),
        "content": str(it.get("snippet") or ""),
        "source": "serper",
    } for it in items[:max_results] if it.get("link")]


def free_web_search(
    query: str,
    max_results: int = 8,
    include_domains: Optional[List[str]] = None,
    raw_content: bool = False,
    use_cache: bool = True,
) -> Tuple[str, SearchResults]:
    """
    Ricerca free-first. Ritorna (sorgente, risultati).
    Nessuna chiave richiesta: con zero API key configurate passa da DDG.
    """
    if use_cache and not raw_content:
        hit = _cache_get(query, include_domains)
        if hit:
            _metric("search_cached")
            return hit

    chain = [("duckduckgo", search_duckduckgo), ("searxng", search_searxng)]
    keyed = [("tavily", search_tavily), ("serper", search_serper)]
    if search_mode() == "serper":
        chain = [("serper", search_serper)] + chain + [("tavily", search_tavily)]
    else:
        chain = chain + keyed

    for name, fn in chain:
        try:
            if name == "tavily":
                results = fn(query, max_results, include_domains, raw_content)
            else:
                results = fn(query, max_results, include_domains)
        except Exception as e:  # un provider rotto non ferma la catena
            print(f"    [SEARCH {name}] errore: {type(e).__name__}: {str(e)[:80]}")
            continue
        if results:
            _metric("search", name)
            if use_cache and not raw_content:
                _cache_put(query, include_domains, name, results)
            return name, results

    # "none" e "blocked" non sono la stessa cosa: il secondo dice che la ricerca
    # non è stata fatta, non che il giocatore non esiste. Chi legge i log deve
    # poterlo distinguere, e chi configura deve sapere che serve una fallback.
    if ddg_blocked():
        _metric("search_blocked")
    else:
        # I motori sono stati interrogati e non hanno risposto niente: la
        # ricerca è stata pagata comunque, va contata.
        _metric("search", "duckduckgo")
    return ("blocked" if ddg_blocked() else "none"), []


# =============================================================== LLM wrapper
def _gemini_complete(system: str, user: str, gemini_client=None) -> Optional[str]:
    """Chiamata Gemini diretta (client passato dal chiamante o creato al volo)."""
    key = _real_key("GEMINI_API_KEY")
    if not gemini_client and not key:
        return None
    model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    try:
        if gemini_client is None:
            from google import genai
            gemini_client = genai.Client(api_key=key)
        resp = gemini_client.models.generate_content(
            model=model,
            contents=f"{system}\n\n{user}" if system else user,
        )
        return resp.text or ""
    except Exception as e:
        print(f"    [LLM gemini] errore: {str(e)[:120]}")
        return None


def llm_complete_json(
    system: str,
    user: str,
    gemini_client=None,
    free_first: Optional[bool] = None,
    task: str = "extract",
    parse: bool = True,
) -> Any:
    """
    Una completion JSON dalla prima rotta che risponde.

    Ritorna il JSON già parsato (dict/list) con parse=True, il testo grezzo
    altrimenti. None se nessuna rotta ha prodotto output valido.
    L'ordine dipende da OB1_LLM_MODE, salvo override con free_first.
    """
    mode = llm_mode()
    if free_first is None:
        free_first = mode != "gemini_first"
    allow_gemini = mode != "free_only"

    def _try_free() -> Optional[Any]:
        gw = _gateway()
        if not gw:
            return None
        # Gemini è gestito a parte (client nativo): qui solo rotte free
        res = gw.complete_json(task, user, system=system, exclude_providers={"gemini"})
        if res.ok:
            return res.data if parse else res.raw
        return None

    def _try_gemini() -> Optional[Any]:
        if not allow_gemini:
            return None
        raw = _gemini_complete(system, user, gemini_client)
        if not raw:
            return None
        if not parse:
            return raw
        from src.llm.gateway import _parse_json
        return _parse_json(raw)

    order = (_try_free, _try_gemini) if free_first else (_try_gemini, _try_free)
    for fn in order:
        out = fn()
        if out is not None:
            return out
    return None


def llm_source_label() -> str:
    """Etichetta della rotta usata più di recente, per il campo sources."""
    gw = _gateway()
    if gw and gw.stats.get("by_route"):
        last = max(gw.stats["by_route"].items(), key=lambda kv: kv[1])[0]
        return f"Enrichment:{last.split('/')[0]}"
    if _real_key("GEMINI_API_KEY"):
        return "Enrichment:gemini"
    return "Enrichment:unknown"


if __name__ == "__main__":
    import sys
    print(describe_stack())
    q = sys.argv[1] if len(sys.argv) > 1 else "Patierno transfermarkt"
    src, res = free_web_search(q, max_results=5)
    print(f"source={src} results={len(res)}")
    for r in res[:5]:
        print(f"  - {r['title'][:70]} | {r['url'][:80]}")
