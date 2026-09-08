#!/usr/bin/env python3
"""
Fact check degli svincolati: il Comunicato dice chi, Transfermarkt dice quanto.

Il CU e' una prova di identita' e di stato — chi e' stato svincolato, da quale
societa', in che data. Non dice se quella persona ha giocato. Questo script
prova a chiudere il buco, e soprattutto a **smentire**: se TM lo da' gia' in
un'altra squadra, quel nome non e' piu' un'opportunita' e va tolto dalle schede.

## L'identita' si verifica sulla data di nascita, non sul nome

E' il punto di tutto. Il database vecchio conteneva "CHIOETTO JHONATAN DAVID"
accoppiato al profilo di Jonathan David (30 milioni, Juventus) perche' il
collegamento era stato fatto per somiglianza di nome. Dai CU la data di nascita
arriva esatta: se non combacia, non e' lui, e il profilo si scarta anche quando
il nome e' identico.

Tre esiti, tutti dichiarati:
  - `confermato`  — profilo trovato, data di nascita coincidente;
  - `scartato`    — profilo trovato ma data diversa: omonimo;
  - `assente`     — nessun profilo. Normale per i dilettanti, non e' un difetto
                    del giocatore ne' un errore nostro.

Uso:  python scripts/incrocia_svincoli_tm.py svincoli.json [--out out.json]
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from src.enricher_tm import _TM_HEADERS, parse_tm_text

RICERCA = "https://www.transfermarkt.it/schnellsuche/ergebnis/schnellsuche?query="
BASE = "https://www.transfermarkt.it"
_SPAZI = re.compile(r"[ \t\r\f\v]+")   # gli a-capo servono al parser: non si toccano


def _get(url: str, tentativi: int = 3, pausa: float = 5.0):
    for i in range(tentativi):
        try:
            r = requests.get(url, headers=_TM_HEADERS, timeout=30)
        except requests.RequestException as e:
            motivo = type(e).__name__
        else:
            if r.status_code == 200:
                return r
            if r.status_code in (404, 410):
                return None
            motivo = f"HTTP {r.status_code}"
        if i < tentativi - 1:
            time.sleep(pausa)
    print(f"    [rete] {motivo}")
    return None


def _testo(r) -> str:
    corpo = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", r.text)
    return _SPAZI.sub(" ", html_mod.unescape(re.sub(r"(?s)<[^>]+>", " ", corpo)))


def cerca_profili(nome: str) -> list:
    """Nome -> URL di profilo candidati, nell'ordine in cui TM li propone."""
    r = _get(RICERCA + urllib.parse.quote(nome))
    if not r:
        return []
    trovati = re.findall(r'href="(/[^"]+/profil/spieler/\d+)"', r.text)
    return [BASE + p for p in dict.fromkeys(trovati)]


def _nome_invertito(nome: str) -> str:
    """'Varoli Fabio' -> 'Fabio Varoli': i CU scrivono cognome per primo."""
    p = nome.split()
    return " ".join(p[1:] + p[:1]) if len(p) == 2 else nome


def verifica(svincolato: dict, pausa: float = 2.0) -> dict:
    """
    Un record da cu_svincoli -> stesso record con l'esito del fact check.

    Si prova prima "Nome Cognome" (come cerca TM) e poi la forma del CU.
    """
    atteso = svincolato.get("nascita")
    esito = {"stato": "assente", "tm_url": None, "motivo": None}

    for query in (_nome_invertito(svincolato["nome"]), svincolato["nome"]):
        for url in cerca_profili(query)[:5]:
            time.sleep(pausa)
            r = _get(url)
            if not r:
                continue
            dati = parse_tm_text(_testo(r), url)
            nato = dati.get("birth_date")
            if not nato:
                continue
            if nato == atteso:
                esito = {"stato": "confermato", "tm_url": url, "motivo": None,
                         "tm": {k: v for k, v in dati.items() if k != "tm_url"}}
                return {**svincolato, "fact_check": esito}
            # Nome uguale, nato in un altro giorno: e' un'altra persona.
            esito = {"stato": "scartato", "tm_url": url,
                     "motivo": f"profilo trovato ma nato il {nato}, non il {atteso}"}
        if esito["stato"] == "confermato":
            break
        time.sleep(pausa)
    return {**svincolato, "fact_check": esito}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sorgente", help="json con gli svincolati")
    ap.add_argument("--out", default="")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--pausa", type=float, default=2.0)
    args = ap.parse_args()

    lista = json.loads(Path(args.sorgente).read_text(encoding="utf-8"))
    if args.limite:
        lista = lista[:args.limite]

    fuori, conta = [], {"confermato": 0, "scartato": 0, "assente": 0}
    for i, s in enumerate(lista, 1):
        print(f"[{i}/{len(lista)}] {s['nome']} (nato {s['nascita']})")
        r = verifica(s, pausa=args.pausa)
        fc = r["fact_check"]
        conta[fc["stato"]] += 1
        if fc["stato"] == "confermato":
            tm = fc.get("tm", {})
            print(f"    CONFERMATO · club su TM: {tm.get('current_club') or '—'}"
                  f" · presenze: {tm.get('appearances') or '—'}"
                  f" · valore: {tm.get('market_value_text') or '—'}")
        elif fc["stato"] == "scartato":
            print(f"    SCARTATO · {fc['motivo']}")
        else:
            print("    nessun profilo (normale nei dilettanti)")
        fuori.append(r)
        time.sleep(args.pausa)

    print("\n" + " | ".join(f"{k}: {v}" for k, v in conta.items()))
    if args.out:
        Path(args.out).write_text(json.dumps(fuori, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        print(f"scritto {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
