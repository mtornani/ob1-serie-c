#!/usr/bin/env python3
"""
Censimento dei canali Telegram del calcio dilettantistico (ARCH-003).

Il problema che risolve: "il canale esiste" e "il canale è vivo" sono due
affermazioni diverse, e confonderle produce registri di fonti che mentono.
Caso reale (3/8/2026): @lndlombardia risponde HTTP 200 con 20 messaggi visibili
— ma sono dell'agosto 2024, e l'ultimo annuncia la migrazione a un canale
privato a invito. Un censimento che conta solo lo status HTTP l'avrebbe
marcato attivo. Questo script no.

Per ogni handle candidato registra le PROVE, non un giudizio:
  - status HTTP dell'anteprima pubblica t.me/s/<handle>
  - data dell'ultimo messaggio visibile (la staleness si calcola, non si stima)
  - segnali di migrazione (link t.me/+... a canali privati + parole tipo
    "nuovo canale")
  - classificazione grezza del contenuto (link a PDF di comunicati, parole
    chiave di giustizia sportiva, formazioni, mercato)
  - iscritti dichiarati

Output: config/telegram_channels.json — una riga per canale, con verified_at.
Il verdetto ("attivo", "migrato", "morto", "inesistente") è DERIVATO dalle
prove con regole esplicite, e si può sempre ricalcolare.

Il parsing è codice puro (testabile offline su fixture); la rete sta solo in
fetch_preview(). Nessuna API key: si legge solo l'anteprima pubblica che
Telegram serve a chiunque.

Uso:
    python scripts/telegram_census.py                # censisce i candidati noti
    python scripts/telegram_census.py handle1 h2 ... # censisce handle specifici
"""

from __future__ import annotations

import html as html_mod
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REGISTRY = Path("config/telegram_channels.json")

# Oltre questa età dell'ultimo messaggio un canale non è "attivo". 45 giorni:
# copre la pausa estiva tra due comunicati senza assolvere un canale morto.
STALE_DAYS = 45

# Candidati noti a oggi: trovati a mano (utente) o per pattern. Il censimento
# NON inventa handle: registra solo ciò che qualcuno ha davvero indicato.
KNOWN_CANDIDATES = [
    # nazionali
    "serieDofficial",           # Dipartimento Interregionale (Serie D) — trovato dall'utente
    # comitati regionali
    "lndemiliaromagna", "lndlombardia", "lndlazio", "lndtoscana",
    # delegazioni provinciali
    "lndmilano",                # trovato dall'utente
    # club
    "renategiovanili",          # trovato dall'utente
    # aggregatori
    "tuttocampoit",
]

_MSG_RE = re.compile(
    r'<div class="tgme_widget_message_wrap.*?(?=<div class="tgme_widget_message_wrap|</section>)',
    re.S)
_INVITE_RE = re.compile(r't\.me/\+[A-Za-z0-9_-]+')
_MIGRATION_WORDS = re.compile(r'nuovo\s+canale|ci\s+siamo\s+trasferiti|sar\w+\s+disattivato', re.I)

_CONTENT_SIGNALS = {
    "comunicati_pdf": re.compile(r'href="https?://[^"]+\.pdf"'),
    "comunicato_kw": re.compile(r'comunicato\s+ufficiale|\bcu\s*\d+', re.I),
    "giustizia_kw": re.compile(r'squalific|giudice sportivo|ammonizion', re.I),
    "formazioni_kw": re.compile(r'formazion|undici titolare|starting', re.I),
    "mercato_kw": re.compile(r'svincolat|tesserament|trasferiment', re.I),
}


def parse_preview(page_html: str) -> dict:
    """Estrae le prove dall'HTML di t.me/s/<handle>. Codice puro."""
    msgs = _MSG_RE.findall(page_html or "")
    title = re.search(r'<meta property="og:title" content="([^"]+)"', page_html or "")
    subs = re.search(r'([\d\s.,]+)\s*(?:subscribers|iscritti)',
                     html_mod.unescape(page_html or ""))
    dates = re.findall(r'datetime="([^"]+)"', page_html or "")
    last_msg = max(dates) if dates else None

    # La migrazione si cerca negli ULTIMI messaggi: un invito vecchio in mezzo
    # allo storico non dice niente, uno nell'ultimo messaggio dice tutto.
    tail = "".join(msgs[-3:])
    migration_invites = _INVITE_RE.findall(tail)
    migrated = bool(migration_invites) and bool(_MIGRATION_WORDS.search(
        html_mod.unescape(re.sub(r'<[^>]+>', ' ', tail))))

    signals = {name: len(rx.findall(page_html or ""))
               for name, rx in _CONTENT_SIGNALS.items()}
    return {
        "title": html_mod.unescape(title.group(1)) if title else None,
        "subscribers": subs.group(1).strip() if subs else None,
        "visible_messages": len(msgs),
        "last_message_at": last_msg,
        "migrated": migrated,
        "migration_targets": sorted(set(migration_invites)),
        "content_signals": signals,
    }


def verdict(status: int, evidence: dict, now: datetime | None = None) -> str:
    """
    Regole esplicite, in ordine. Chi legge il registro può ricalcolarle:
      inesistente  l'anteprima non risponde 200 o non ha messaggi
      migrato      gli ultimi messaggi annunciano un canale sostitutivo
      morto        ultimo messaggio più vecchio di STALE_DAYS
      attivo       tutto il resto
    """
    if status != 200 or not evidence.get("visible_messages"):
        return "inesistente"
    if evidence.get("migrated"):
        return "migrato"
    last = evidence.get("last_message_at")
    if last:
        now = now or datetime.now(timezone.utc)
        try:
            dt = datetime.fromisoformat(last)
            if (now - dt).days > STALE_DAYS:
                return "morto"
        except ValueError:
            pass
    return "attivo"


def classify(evidence: dict) -> str:
    """Che tipo di dati veicola. Grezzo di proposito: si raffina a mano."""
    s = evidence.get("content_signals", {})
    if s.get("comunicati_pdf", 0) >= 3 or s.get("comunicato_kw", 0) >= 3:
        return "feed_comunicati"
    if s.get("formazioni_kw", 0) >= 3:
        return "formazioni"
    if s.get("mercato_kw", 0) >= 3:
        return "mercato"
    return "news_generiche"


def fetch_preview(handle: str, timeout: int = 20) -> tuple[int, str]:
    import urllib.request
    req = urllib.request.Request(
        f"https://t.me/s/{handle}", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except Exception:
        # urllib segue i redirect; t.me/s/ di un canale privato/inesistente
        # rimanda alla pagina t.me classica -> la trattiamo come non-anteprima
        return 0, ""


def census(handles: list[str]) -> dict:
    now = datetime.now(timezone.utc)
    rows = {}
    for h in handles:
        status, page = fetch_preview(h)
        # t.me/s/ di canali senza anteprima fa redirect a t.me/<handle>:
        # la pagina risultante non contiene widget di messaggi.
        ev = parse_preview(page)
        v = verdict(status, ev, now)
        rows[h] = {
            "handle": h,
            "verdict": v,
            "content_type": classify(ev) if v in ("attivo", "morto") else None,
            "verified_at": now.isoformat(timespec="seconds"),
            **ev,
        }
        print(f"@{h:20} {v:12} ultimo_msg={ev['last_message_at'] or '-':26}"
              f" tipo={rows[h]['content_type'] or '-'}")
    return rows


def main():
    handles = sys.argv[1:] or KNOWN_CANDIDATES
    rows = census(handles)

    existing = {}
    if REGISTRY.exists():
        try:
            existing = json.loads(REGISTRY.read_text(encoding="utf-8")).get("channels", {})
        except (ValueError, OSError):
            pass
    existing.update(rows)

    counts = {}
    for r in existing.values():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    out = {
        "_meta": {
            "purpose": ("Censimento canali Telegram del dilettantismo. Ogni riga porta "
                        "le prove (ultimo messaggio, migrazione, segnali di contenuto) "
                        "e il verdetto e' ricalcolabile con scripts/telegram_census.py. "
                        "'Risponde 200' NON significa 'vivo': vedi @lndlombardia."),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "coverage": counts,
        },
        "channels": dict(sorted(existing.items())),
    }
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"\nregistro: {REGISTRY} · verdetti: {counts}")


if __name__ == "__main__":
    main()
