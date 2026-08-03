#!/usr/bin/env python3
"""
ARCH-002 Fase 2 — "l'ho già visto?"

La domanda più economica del sistema: se la risposta è sì, tutto quello che
verrebbe dopo (fetch, parsing, inferenza) non va fatto. Vale per un articolo
ripubblicato uguale, per una pagina che non è cambiata, per un URL già in coda.

La chiave è `sha256(url + contenuto_normalizzato)`, non l'URL da solo:

  - stesso URL, contenuto diverso  → è un evento (la pagina è cambiata)
  - stesso URL, contenuto uguale   → non è un evento, anche se il sito ha
    cambiato la data di pubblicazione o l'ordine dei banner
  - URL diverso, contenuto uguale  → è comunque un evento per quell'URL, ma
    `seen_content()` permette di riconoscere il ricircolo tra aggregatori

Storage: SQLite in `data/ob1.db` (ARCH-002 §5.5), gitignorato e trasportato
tra le run dall'artifact di Actions. `SeenStore(":memory:")` per i test.

Test: PYTHONIOENCODING=utf-8 python -m unittest tests.test_watch -v
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_DB = Path("data/ob1.db")

# Quanto tiene la memoria. Oltre, un contenuto è talmente vecchio che rivederlo
# è di fatto un evento nuovo — e le righe non devono crescere all'infinito.
DEFAULT_RETENTION_DAYS = 60

_WS = re.compile(r"\s+")
_VOLATILE = re.compile(
    r"(?:\?|&)(?:utm_[a-z]+|fbclid|gclid|ref|ref_src|_ga)=[^&\s]*", re.IGNORECASE)


def watch_enabled() -> bool:
    """OB1_WATCH=0 riporta al comportamento pre-ARCH-002 (vincolo §7)."""
    return os.getenv("OB1_WATCH", "1") != "0"


def normalize_content(text: str) -> str:
    """
    Testo confrontabile: spazi collassati, minuscolo, niente code di tracking.
    Serve a non far passare per "nuovo" un articolo identico ripubblicato.
    """
    if not text:
        return ""
    return _WS.sub(" ", text.strip().lower())


def normalize_url(url: str) -> str:
    """URL senza parametri di tracking: ?utm_source= non è contenuto."""
    if not url:
        return ""
    return _VOLATILE.sub("", url.strip()).rstrip("?&")


def content_key(url: str, content: str = "") -> str:
    """L'identità di un contenuto per questo sistema."""
    payload = f"{normalize_url(url)}\n{normalize_content(content)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_only_key(content: str) -> str:
    """Solo il contenuto: riconosce lo stesso pezzo su URL diversi."""
    return hashlib.sha256(normalize_content(content).encode("utf-8")).hexdigest()


class SeenStore:
    """
    Memoria di cosa è già passato. Nessuna dipendenza esterna: sqlite3 è nella
    standard library, e un file solo si trasporta come artifact.
    """

    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS seen (
                    key          TEXT PRIMARY KEY,
                    kind         TEXT NOT NULL DEFAULT 'item',
                    url          TEXT,
                    content_hash TEXT,
                    first_seen   TEXT NOT NULL,
                    last_seen    TEXT NOT NULL,
                    times_seen   INTEGER NOT NULL DEFAULT 1
                )
            """)
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_seen_content ON seen(content_hash)")
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_seen_last ON seen(last_seen)")

    # ------------------------------------------------------------------ letture
    def is_new(self, key: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM seen WHERE key = ?", (key,)).fetchone()
        return row is None

    def seen_content(self, content: str) -> bool:
        """Questo testo è già passato, anche se da un altro URL?"""
        h = content_only_key(content)
        row = self.conn.execute(
            "SELECT 1 FROM seen WHERE content_hash = ? LIMIT 1", (h,)).fetchone()
        return row is not None

    def info(self, key: str) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM seen WHERE key = ?", (key,)).fetchone()
        return dict(row) if row else None

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0]

    # ---------------------------------------------------------------- scritture
    def mark(self, key: str, url: str = "", content: str = "",
             kind: str = "item") -> bool:
        """
        Registra un passaggio. Ritorna True se era NUOVO (quindi c'è lavoro da
        fare), False se era già visto (e allora il lavoro si salta).
        """
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        existing = self.conn.execute(
            "SELECT times_seen FROM seen WHERE key = ?", (key,)).fetchone()
        with self.conn:
            if existing:
                self.conn.execute(
                    "UPDATE seen SET last_seen = ?, times_seen = times_seen + 1 "
                    "WHERE key = ?", (now, key))
                return False
            self.conn.execute(
                "INSERT INTO seen (key, kind, url, content_hash, first_seen, "
                "last_seen, times_seen) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (key, kind, normalize_url(url), content_only_key(content), now, now))
        return True

    def see(self, url: str, content: str = "", kind: str = "item") -> bool:
        """
        Scorciatoia: calcola la chiave e registra. True = evento nuovo.

        Con OB1_WATCH=0 risponde sempre True: tutto sembra nuovo e la pipeline
        si comporta come prima di ARCH-002, senza rami di codice separati.
        """
        if not watch_enabled():
            return True
        return self.mark(content_key(url, content), url=url, content=content, kind=kind)

    def see_many(self, items: Iterable[tuple], kind: str = "item") -> list:
        """(url, content) → solo quelli nuovi, nell'ordine di arrivo."""
        out = []
        for url, content in items:
            if self.see(url, content, kind=kind):
                out.append(url)
        return out

    # ---------------------------------------------------------------- manutenzione
    def prune(self, days: int = DEFAULT_RETENTION_DAYS) -> int:
        """Righe più vecchie di `days` (per ultima visione). Ritorna quante."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
            timespec="seconds")
        with self.conn:
            cur = self.conn.execute("DELETE FROM seen WHERE last_seen < ?", (cutoff,))
        return cur.rowcount or 0

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self) -> "SeenStore":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


if __name__ == "__main__":
    store = SeenStore(":memory:")
    art = "https://www.tuttoc.com/news/il-giovane-attaccante-firma?utm_source=twitter"
    testo = "Il giovane attaccante ha firmato il primo contratto professionistico."
    print("prima volta :", store.see(art, testo))          # True
    print("ripubblicato:", store.see(art.split("?")[0], testo))  # False: stesso contenuto
    print("aggiornato  :", store.see(art, testo + " Esordio in Coppa."))  # True
    print("righe       :", store.count())
    print("prune 60g   :", store.prune(60))
