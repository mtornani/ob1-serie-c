#!/usr/bin/env python3
"""
Costruisce config/club_categorie.json dai calendari allegati ai CU.

I calendari regionali stanno fra gli allegati dell'elenco comunicati del
comitato; quello di Serie D e' nazionale, sul portale LND. Si scaricano una
volta a stagione: i gironi non cambiano.

Uso:  python scripts/costruisci_livelli.py [--dry-run]
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cu_site import DEFAULT_SITE, fetch_listing
from src.livelli import (ETICHETTA, LIVELLO, costruisci_da_elenco,
                         costruisci_mappa, salva_registro)

# I gironi di Serie D: nazionali, non regionali. Il numero del CU cambia ogni
# stagione, quindi si cerca invece di essere scritto qui.
LND = "https://comunicati.lnd.it"


def _pdf_testo(url: str, tentativi: int = 3, pausa: float = 4.0) -> str:
    from pypdf import PdfReader
    for i in range(tentativi):
        try:
            b = urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}), timeout=45).read()
        except Exception:
            time.sleep(pausa)
            continue
        if b[:4] == b"%PDF":
            return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(b)).pages)
        time.sleep(pausa)
    return ""


def calendari_regionali() -> dict:
    """{categoria: testo}, dagli allegati dell'elenco comunicati."""
    html = fetch_listing()
    trovati = {}
    for path in sorted(set(re.findall(
            r'href="(/files/announcements/\d{4}/\d+/[^"]+\.pdf)"', html))):
        nome = path.rsplit("/", 1)[-1].lower()
        if "tabellone" in nome or "coppa" in nome or "femminile" in nome:
            continue          # coppe e femminile: altre competizioni
        if nome.startswith("eccellenza_girone"):
            cat = "eccellenza"
        elif nome.startswith("promozione_girone"):
            cat = "promozione"
        elif nome.startswith("prima_categoria_girone"):
            cat = "prima_categoria"
        else:
            continue
        url = DEFAULT_SITE + urllib.parse.quote(path)
        testo = _pdf_testo(url)
        if testo:
            trovati[cat] = trovati.get(cat, "") + "\n" + testo
            print(f"  {cat:16} <- {nome}")
        else:
            print(f"  [saltato] {nome}")
        time.sleep(1.5)
    return trovati


def calendario_serie_d() -> str:
    import json
    u = LND + "/?" + urllib.parse.urlencode({"search": "Gironi", "department": 3})
    h = urllib.request.urlopen(urllib.request.Request(
        u, headers={"User-Agent": "Mozilla/5.0"}), timeout=40).read().decode("utf-8", "ignore")
    props = json.loads(re.search(
        r'data-page="app" type="application/json">(.*?)</script>', h, re.S).group(1))["props"]
    for r in props["communications"]["data"]:
        if "gironi serie d" in (r["subject"] or "").lower():
            url = LND + urllib.parse.quote(r["document_url"])
            print(f"  serie_d          <- {r['formatted_number']}")
            return _pdf_testo(url)
    print("  [saltato] gironi Serie D non trovati")
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    calendari = calendari_regionali()
    mappa = costruisci_mappa(calendari)

    # La Serie D pubblica un ELENCO di gironi, non un calendario di partite:
    # va letta con l'altra modalita'. Ha la precedenza perche' e' la categoria
    # piu' alta e non deve perderla se un nome ricapita.
    d = calendario_serie_d()
    if d:
        for nome, cat in costruisci_da_elenco(d, "serie_d").items():
            if nome not in mappa or LIVELLO["serie_d"] > LIVELLO[mappa[nome]]:
                mappa[nome] = cat
    conteggio = {}
    for cat in mappa.values():
        conteggio[cat] = conteggio.get(cat, 0) + 1
    print("\nsocieta' per categoria:")
    for cat in ("serie_d", "eccellenza", "promozione", "prima_categoria"):
        print(f"  {ETICHETTA[cat]:18} {conteggio.get(cat, 0)}")
    print(f"  {'TOTALE':18} {len(mappa)}")

    if args.dry_run:
        print("dry-run: registro non scritto")
        return 0
    salva_registro(mappa)
    print("scritto config/club_categorie.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
