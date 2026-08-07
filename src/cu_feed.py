#!/usr/bin/env python3
"""
ARCH-003 — Scoperta dei Comunicati Ufficiali dal canale Telegram del comitato.

Il censimento (scripts/telegram_census.py) ha stabilito che i comitati vivi
pubblicano i CU come link a PDF sul proprio canale pubblico. Questo modulo
chiude il cerchio: dall'anteprima pubblica del canale ricava la lista dei PDF,
e il SeenStore evita di riscaricare e riparsare quelli già ingeriti.

Perché passare dal canale invece che dal sito del comitato: il canale è
l'unica superficie che dice QUANDO un comunicato è stato pubblicato. Un
listing HTML va confrontato per differenza a ogni giro; qui il messaggio
nuovo è il segnale, ed è quello che ARCH-002 chiede — lavorare sul cambiamento,
non sull'orologio.

Il parsing è codice puro e testabile offline; la rete sta solo in fetch_channel().
Nessuna API key: si legge l'anteprima che Telegram serve a chiunque.
"""

from __future__ import annotations

import html as html_mod
import re

# Un messaggio dell'anteprima. Stesso confine usato dal censimento: il wrapper
# si ripete, e l'ultimo si chiude sulla fine della sezione.
_MSG_RE = re.compile(
    r'<div class="tgme_widget_message_wrap.*?'
    r'(?=<div class="tgme_widget_message_wrap|</section>)', re.S)

_HREF_PDF = re.compile(r'href="(https?://[^"]+?\.pdf)"', re.I)
_TIME_RE = re.compile(r'datetime="([^"]+)"')

# "Cu 11 del 05.08.26", "COMUNICATO UFFICIALE N. 146", "C.U. n.3"
_CU_NUM_RE = re.compile(
    r'(?:comunicato\s+ufficiale|c\.?\s*u\.?)\s*n?[.\s]*(\d{1,4})\b', re.I)

# Falsi positivi ricorrenti: i comitati postano sullo stesso canale anche
# moduli, circolari e calendari. Sono PDF, ma non sono comunicati.
_NOT_A_CU = re.compile(
    r'modulo|circolare|calendario|iscrizion|convocazion|corso|tessera', re.I)


def _strip_tags(fragment: str) -> str:
    return html_mod.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))


def parse_cu_feed(page_html: str) -> list:
    """
    Anteprima di t.me/s/<handle> -> lista di CU trovati, dal più vecchio al
    più recente. Ogni voce: url, cu_number (se dichiarato), posted_at, text.

    Un messaggio può portare più PDF (comunicato + allegati): li teniamo
    tutti, perché scartare a priori significherebbe decidere qui quale sia il
    documento buono, e il parser a valle lo sa meglio di noi — un PDF che non
    contiene una sezione di giustizia sportiva produce semplicemente zero fatti.
    """
    found = []
    for msg in _MSG_RE.findall(page_html or ""):
        pdfs = _HREF_PDF.findall(msg)
        if not pdfs:
            continue
        text = " ".join(_strip_tags(msg).split())
        if _NOT_A_CU.search(text):
            continue
        num = _CU_NUM_RE.search(text)
        when = _TIME_RE.search(msg)
        for url in dict.fromkeys(pdfs):        # dedup preservando l'ordine
            found.append({
                "url": html_mod.unescape(url),
                "cu_number": int(num.group(1)) if num else None,
                "posted_at": when.group(1) if when else None,
                "text": text[:200],
            })
    return found


def fetch_channel(handle: str, timeout: int = 20) -> tuple:
    """(status, html) dell'anteprima pubblica. Unica funzione che tocca la rete."""
    import urllib.request

    req = urllib.request.Request(
        f"https://t.me/s/{handle}", headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except Exception:
        return 0, ""


def new_cu_links(handle: str, seen=None) -> list:
    """
    I CU del canale non ancora ingeriti. Con seen=None ritorna tutto quello
    che vede: comodo per il primo giro e per l'ispezione manuale.
    """
    status, page = fetch_channel(handle)
    if status != 200:
        return []
    items = parse_cu_feed(page)
    if seen is None:
        return items
    # La chiave è l'URL: un CU è immutabile una volta pubblicato, e usare il
    # contenuto costringerebbe a scaricare il PDF prima di sapere se serve.
    return [it for it in items if seen.see(it["url"], kind="cu_pdf")]
