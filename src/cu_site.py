#!/usr/bin/env python3
"""
ARCH-003 — I Comunicati Ufficiali dal sito del comitato, quando il canale muore.

Perche' esiste questo modulo, e non bastava src/cu_feed.py: il 5/9/2026 il
censimento ha dato `inesistente` su @lndemiliaromagna — il canale su cui
poggiava tutta la catena Emilia-Romagna, ancora `attivo` con 839 iscritti al
7/8/2026. Un canale Telegram e' proprieta' di chi lo apre e puo' sparire in un
giorno; il sito del comitato no, perche' e' l'organo di pubblicazione previsto
dalle NOIF. La lezione non e' "Telegram e' sbagliato" (resta la fonte con la
data di pubblicazione gratis): e' che una catena con una sola fonte non e' una
catena, e' un filo.

La superficie e' l'elenco pubblico dei comunicati (`/comunicati?page=N`), che
per ogni annuncio elenca gli allegati come link diretti a
`/files/announcements/{anno}/{announcement_id}/cu{n}.pdf`. Il nome del file
distingue il comunicato dai suoi allegati (calendari, moduli, tabelloni) senza
euristiche sul testo: se non si chiama cuNN.pdf, non e' il comunicato.

Attenzione al WAF: il sito serve a intermittenza una pagina-interstiziale
("One moment, please...") con HTTP **200**. Trattarla come elenco vuoto
ripeterebbe l'errore gia' corretto una volta in questo repo (@lndlombardia:
"risponde 200" non significa "ha contenuto"). Qui l'interstiziale si riconosce
e si ritenta; se non passa, la funzione lo dice invece di restituire [].

Il parsing e' codice puro e testabile offline; la rete sta solo in
fetch_listing(). Nessuna API key: si legge la pagina che il comitato pubblica
per chiunque, allo stesso ritmo di un lettore umano.
"""

from __future__ import annotations

import re
import time

# Comitato Regionale Emilia-Romagna: il comitato del club guida (Rimini Calcio
# SSD ARL, Eccellenza girone B 2026/2027, verificato sul calendario ufficiale).
DEFAULT_SITE = "https://www.figccrer.it"

# L'unico marcatore affidabile del comunicato dentro la cartella dell'annuncio.
# Gli allegati stanno nello stesso percorso ma hanno nomi liberi ("eccellenza_
# girone_b.pdf", "Modulo Iscrizione...pdf"): non sono comunicati e non vanno
# dati in pasto al parser della giustizia sportiva.
_CU_HREF_RE = re.compile(
    r'href="(?P<path>/files/(?:announcements|comunicati)/'
    r'(?P<year>\d{4})/(?P<aid>\d+)/cu(?P<num>\d+)\.pdf)"', re.I)

# Firme dell'interstiziale anti-bot. Due indizi indipendenti: il titolo e il
# reload automatico. Una pagina vera non li ha.
_INTERSTITIAL_RE = re.compile(
    r'One moment, please|window\.location\.reload\(\)', re.I)


class ListingUnavailable(RuntimeError):
    """Il sito ha risposto ma non con l'elenco: interstiziale, o HTTP != 200.

    Esiste come eccezione e non come lista vuota perche' "non ho potuto
    guardare" e "ho guardato e non c'era niente di nuovo" portano il chiamante
    a fare due cose diverse.
    """


def is_interstitial(page_html: str) -> bool:
    """La pagina e' il muro anti-bot invece dell'elenco?"""
    return bool(_INTERSTITIAL_RE.search(page_html or ""))


def parse_site_listing(page_html: str, base_url: str = DEFAULT_SITE) -> list:
    """
    HTML di /comunicati -> lista di CU, dal piu' vecchio al piu' recente.

    Ogni voce ha la stessa forma prodotta da src/cu_feed.parse_cu_feed, cosi'
    che scripts/brief_giovedi.py possa consumare le due fonti senza sapere da
    quale arriva il documento. `posted_at` resta None: l'elenco non porta la
    data di pubblicazione in forma affidabile, e la data vera del comunicato la
    dichiara il PDF stesso (parse_cu_text la legge dall'intestazione). Meglio
    un campo vuoto che una data inventata dall'ordine di pagina.

    L'ordinamento e' per announcement_id crescente: e' l'id progressivo del
    CMS, quindi l'ordine di pubblicazione. Non usiamo il numero del CU perche'
    a cavallo di stagione riparte da 1.
    """
    found = {}
    for m in _CU_HREF_RE.finditer(page_html or ""):
        url = base_url.rstrip("/") + m.group("path")
        # dedup: lo stesso allegato compare nella card e nella modale
        found[url] = {
            "url": url,
            "cu_number": int(m.group("num")),
            "posted_at": None,
            "text": f"CU {int(m.group('num'))} ({m.group('year')})",
            "announcement_id": int(m.group("aid")),
        }
    return sorted(found.values(), key=lambda it: it["announcement_id"])


def fetch_listing(base_url: str = DEFAULT_SITE, page: int = 1,
                  timeout: int = 30, retries: int = 3,
                  pause: float = 5.0) -> str:
    """
    HTML dell'elenco. Unica funzione che tocca la rete.

    Il WAF passa a intermittenza: si ritenta con una pausa, che e' anche il
    modo educato di insistere. Esaurititi i tentativi si solleva, perche' un
    ritorno vuoto qui diventerebbe "nessun comunicato nuovo" a valle — cioe'
    un canale rotto che si traveste da canale pulito.
    """
    import urllib.request

    url = f"{base_url.rstrip('/')}/comunicati?page={page}"
    last = "HTTP diverso da 200"
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (OB1 brief del giovedi)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status != 200:
                    last = f"HTTP {r.status}"
                else:
                    body = r.read().decode("utf-8", "ignore")
                    if not is_interstitial(body):
                        return body
                    last = "interstiziale anti-bot"
        except Exception as exc:                      # rete giu', DNS, TLS
            last = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(pause)
    raise ListingUnavailable(f"{url}: {last} dopo {retries} tentativi")


def new_cu_links(base_url: str = DEFAULT_SITE, seen=None, pages: int = 1) -> list:
    """
    I CU del sito non ancora ingeriti. Stessa firma di cu_feed.new_cu_links.

    `pages` > 1 serve al riempimento retroattivo dello storico: l'elenco e'
    paginato dal piu' recente, quindi la pagina 2 e' il mese prima.
    """
    items = []
    for p in range(1, max(1, pages) + 1):
        items.extend(parse_site_listing(fetch_listing(base_url, page=p), base_url))
    # Dedup tra pagine (un annuncio a cavallo del confine compare due volte),
    # poi ordine di pubblicazione crescente.
    items = sorted({it["url"]: it for it in items}.values(),
                   key=lambda it: it["announcement_id"])
    if seen is None:
        return items
    return [it for it in items if seen.is_new_url(it["url"])]
