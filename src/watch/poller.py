#!/usr/bin/env python3
"""
Poller RSS / sitemap — ARCH-002 Fase 3.

Il motivo per cui esiste, in una riga: la discovery interrogava un motore di
ricerca 8 query × 4 run al giorno *a prescindere*, bruciando ~1900 crediti
Tavily al mese per riavere quasi sempre gli stessi articoli del giorno prima.
Un feed dice cosa è cambiato, gratis, senza chiedere permesso a nessuno.

Costo di un giro completo quando non è uscito niente: un GET condizionale per
fonte, che il server chiude con 304 senza corpo. Nessuna chiave, nessun credito.

Verificato sul campo (2026-08-03): tuttoc, tuttolegapro e lacasadic espongono
/rss, tuttomercatoweb una sitemap, sportitalia /rss. Cinque fonti su sei.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from .seen import SeenStore, watch_enabled

try:
    from src.metrics import get_metrics
except ImportError:  # layout PYTHONPATH=src
    try:
        from metrics import get_metrics
    except ImportError:
        get_metrics = None

FEEDS_CONFIG = Path("config/feeds.yaml")
FEED_ETAG_CACHE = Path("data/feed_etags.json")

DEFAULT_MAX_AGE_DAYS = 7
DEFAULT_TIMEOUT_S = 20

_UA = "Mozilla/5.0 (compatible; OB1Scout/1.0; +https://ob1-lega-pro.pages.dev)"

# Namespace che compaiono in RSS/Atom/sitemap. Si strippano invece di
# registrarli: i feed reali sbagliano i prefissi troppo spesso.
_NS_RE = re.compile(r"\{[^}]+\}")


def _metric(name: str, *args) -> None:
    if get_metrics is None:
        return
    try:
        getattr(get_metrics(), name)(*args)
    except Exception:
        pass


def _tag(el) -> str:
    return _NS_RE.sub("", el.tag).lower()


def _find_text(parent, *names) -> str:
    """Primo figlio con uno dei nomi dati, namespace ignorato."""
    wanted = {n.lower() for n in names}
    for child in parent.iter():
        if child is parent:
            continue
        if _tag(child) in wanted and (child.text or "").strip():
            return child.text.strip()
    return ""


def _parse_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    raw = raw.strip()
    try:  # RFC 822: "Mon, 03 Aug 2026 10:00:00 +0200"
        dt = parsedate_to_datetime(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:  # ISO 8601 / W3C (sitemap lastmod)
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@dataclass
class Item:
    url: str
    title: str = ""
    summary: str = ""
    published_at: Optional[datetime] = None
    source_id: str = ""

    @property
    def content(self) -> str:
        """Testo su cui calcolare l'hash: titolo + sommario, non l'URL."""
        return f"{self.title}\n{self.summary}".strip()

    def as_search_result(self) -> Dict[str, str]:
        """Stessa forma dei risultati di ricerca: i consumatori non cambiano."""
        return {
            "title": self.title,
            "url": self.url,
            "content": self.summary,
            "source": f"feed:{self.source_id}",
        }


@dataclass
class Source:
    id: str
    url: str
    kind: str = "rss"          # rss | atom | sitemap
    league_id: str = ""
    enabled: bool = True
    max_age_days: int = DEFAULT_MAX_AGE_DAYS


@dataclass
class PollResult:
    source_id: str
    items: List[Item] = field(default_factory=list)
    status: int = 0
    unchanged: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200 or self.unchanged


# ------------------------------------------------------------------ parsing
def parse_feed(body: str, source_id: str = "") -> List[Item]:
    """RSS 2.0, Atom e sitemap XML. Ritorna gli item in ordine di apparizione."""
    if not body or not body.strip():
        return []
    try:
        root = ET.fromstring(body.strip())
    except ET.ParseError:
        return []

    items: List[Item] = []
    for el in root.iter():
        tag = _tag(el)
        if tag == "item" or tag == "entry":           # RSS / Atom
            url = _find_text(el, "link", "guid", "id")
            if not url.startswith("http"):
                # Atom mette l'URL in <link href="...">
                for child in el.iter():
                    if _tag(child) == "link" and child.get("href"):
                        url = child.get("href")
                        break
            items.append(Item(
                url=url,
                title=_find_text(el, "title"),
                summary=_find_text(el, "description", "summary", "content"),
                published_at=_parse_date(
                    _find_text(el, "pubdate", "published", "updated", "date")),
                source_id=source_id,
            ))
        elif tag == "url":                             # sitemap
            loc = _find_text(el, "loc")
            if loc:
                items.append(Item(
                    url=loc,
                    title=_slug_title(loc),
                    published_at=_parse_date(_find_text(el, "lastmod")),
                    source_id=source_id,
                ))
    return [i for i in items if i.url.startswith("http")]


def _slug_title(url: str) -> str:
    """Una sitemap non porta il titolo: si ricava dallo slug, meglio di niente."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"\.\w{2,5}$", "", slug)
    slug = re.sub(r"[-_]+", " ", slug)
    return slug.strip().capitalize()


# ------------------------------------------------------------------- polling
class FeedPoller:
    """
    Interroga le fonti con richieste condizionali. Lo stato dei validatori sta
    in un JSON accanto al database: senza, ogni giro riscarica tutto.
    """

    def __init__(self, etag_path: Optional[Path] = None,
                 session: Optional[requests.Session] = None):
        self.etag_path = Path(etag_path) if etag_path else FEED_ETAG_CACHE
        self.session = session or requests.Session()
        self._validators: Dict[str, Dict[str, str]] = self._load()

    def _load(self) -> Dict[str, Dict[str, str]]:
        try:
            data = json.loads(self.etag_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save(self) -> None:
        try:
            self.etag_path.parent.mkdir(parents=True, exist_ok=True)
            self.etag_path.write_text(
                json.dumps(self._validators, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8")
        except OSError:
            pass

    def poll(self, source: Source, now: Optional[datetime] = None) -> PollResult:
        now = now or datetime.now(timezone.utc)
        headers = {"User-Agent": _UA, "Accept": "application/rss+xml, application/xml, text/xml"}
        known = self._validators.get(source.url) or {}
        if known.get("etag"):
            headers["If-None-Match"] = known["etag"]
        if known.get("last_modified"):
            headers["If-Modified-Since"] = known["last_modified"]

        try:
            resp = self.session.get(source.url, headers=headers, timeout=DEFAULT_TIMEOUT_S)
        except requests.RequestException as e:
            return PollResult(source.id, error=f"{type(e).__name__}: {str(e)[:80]}")

        _metric("fetch", resp.status_code)

        if resp.status_code == 304:
            return PollResult(source.id, status=304, unchanged=True)
        if resp.status_code != 200:
            return PollResult(source.id, status=resp.status_code,
                              error=f"HTTP {resp.status_code}")

        validators = {}
        if resp.headers.get("ETag"):
            validators["etag"] = resp.headers["ETag"]
        if resp.headers.get("Last-Modified"):
            validators["last_modified"] = resp.headers["Last-Modified"]
        if validators:
            self._validators[source.url] = validators

        items = parse_feed(resp.text, source.id)
        cutoff = now - timedelta(days=source.max_age_days)
        fresh = [i for i in items
                 if i.published_at is None or i.published_at >= cutoff]
        return PollResult(source.id, items=fresh, status=200)


# ------------------------------------------------------------------- config
def load_sources(path: Optional[Path] = None,
                 league_id: str = "") -> List[Source]:
    """Legge config/feeds.yaml. Assente o illeggibile => nessuna fonte, mai un errore."""
    p = Path(path) if path else FEEDS_CONFIG
    if yaml is None or not p.exists():
        return []
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return []

    out: List[Source] = []
    for lid, conf in (raw.get("leagues") or {}).items():
        if league_id and lid != league_id:
            continue
        default_age = int((conf or {}).get("max_age_days", DEFAULT_MAX_AGE_DAYS))
        for entry in (conf or {}).get("feeds") or []:
            if not isinstance(entry, dict) or not entry.get("url"):
                continue
            out.append(Source(
                id=entry.get("id") or entry["url"],
                url=entry["url"],
                kind=(entry.get("kind") or "rss").lower(),
                league_id=lid,
                enabled=entry.get("enabled", True),
                max_age_days=int(entry.get("max_age_days", default_age)),
            ))
    return [s for s in out if s.enabled]


def poll_new_items(
    sources: Iterable[Source],
    seen: Optional[SeenStore] = None,
    poller: Optional[FeedPoller] = None,
    verbose: bool = True,
) -> List[Item]:
    """
    Gli articoli **nuovi** di questo giro. Un articolo già visto, o ripubblicato
    identico, non è un evento e non torna: è ciò che rende il costo
    proporzionale alle notizie invece che al numero di run.
    """
    sources = list(sources)
    if not sources:
        return []
    poller = poller or FeedPoller()
    owns_seen = seen is None
    seen = seen or SeenStore()

    new_items: List[Item] = []
    stats = {"304": 0, "ok": 0, "errore": 0, "nuovi": 0, "già visti": 0}
    try:
        for source in sources:
            result = poller.poll(source)
            if result.unchanged:
                stats["304"] += 1
                continue
            if result.error:
                stats["errore"] += 1
                if verbose:
                    print(f"    [FEED {source.id}] {result.error}")
                continue
            stats["ok"] += 1
            for item in result.items:
                if seen.see(item.url, item.content, kind="article"):
                    new_items.append(item)
                    stats["nuovi"] += 1
                else:
                    stats["già visti"] += 1
        poller.save()
    finally:
        if owns_seen:
            seen.close()

    if verbose:
        print(f"    [FEEDS] {len(sources)} fonti: {stats['ok']} aggiornate, "
              f"{stats['304']} invariate, {stats['errore']} in errore | "
              f"{stats['nuovi']} articoli nuovi, {stats['già visti']} già visti")
    return new_items


def feeds_enabled() -> bool:
    """`OB1_FEEDS=0` riporta la discovery al comportamento a ricerca."""
    return os.getenv("OB1_FEEDS", "1") != "0" and watch_enabled()
