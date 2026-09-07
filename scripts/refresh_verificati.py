#!/usr/bin/env python3
"""
Ri-controlla i record che hanno gia' una prova, invece di scoprirne altri.

Il radar scopre bene e non torna mai indietro. Misurato il 7/9/2026: 82 record
hanno un profilo Transfermarkt aperto e verificato, e **nove** hanno anche
presenze sufficienti — ma sono tutti di marzo o giugno, quindi ECC-001 li
scarta per eta' della segnalazione. Il profilo pero' e' li': dice dove gioca
quella persona *adesso*. Ri-aprirlo costa un fetch condizionale.

E' ARCH-002 al contrario: la' si evitava di ripagare per contenuto invariato,
qui il contenuto **e' cambiato** e nessuno era andato a vedere.

Cosa fa, e cosa non fa:
  - rilegge il profilo con lo stesso regex della pipeline (`parse_tm_text`),
    zero LLM: e' il percorso deterministico, non serve nessuna chiave;
  - aggiorna club attuale, valore, data di nascita, piede, ruolo, altezza;
  - scrive `refreshed_at` e rinnova `tm_verified_at` — la scheda l'abbiamo
    aperta davvero, e questa e' l'unica cosa che quel campo deve significare;
  - **non riscrive `opportunity_type`**. Se il profilo dice che oggi ha una
    squadra, lo registra in `club_attuale_verificato` e lascia decidere il
    gate: cambiare il tipo qui vorrebbe dire nascondere la contraddizione
    invece di mostrarla.

Uso:
    python scripts/refresh_verificati.py --dry-run      # non scrive
    python scripts/refresh_verificati.py --limite 10
    python scripts/refresh_verificati.py                # tutti i verificati
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from src.enricher_tm import _TM_HEADERS, parse_tm_text
from src.quality_gate import has_tm_player_profile, is_tm_verified
from src.tm_url import clean as clean_tm_url

DB = Path("data/opportunities.json")

# Come Transfermarkt scrive "non ha una squadra". Se il club attuale e' una di
# queste, il giocatore e' libero — ed e' il caso che ci interessa.
SENZA_SQUADRA = re.compile(
    r"senza\s+contratto|svincolat|vereinslos|without\s+club|ritirat|carriera\s+conclusa",
    re.IGNORECASE)

_WS = re.compile(r"\s+")


def url_profilo(opp: dict) -> str:
    """L'URL del profilo, ovunque sia finito nel record."""
    profile = opp.get("player_profile") or {}
    for fonte in (opp.get("tm_url"), opp.get("transfermarkt_url"),
                  profile.get("tm_url"), profile.get("transfermarkt_url"),
                  opp.get("source_url")):
        pulito = clean_tm_url(fonte or "", opp.get("player_name"))
        if pulito:
            return pulito
    return ""


def scarica(url: str, timeout: int = 25, tentativi: int = 3,
            pausa: float = 4.0) -> str:
    """
    Testo della pagina, o stringa vuota. Unica funzione che tocca la rete.

    Ritenta perche' il sito, da qui, sbaglia a intermittenza: nella prova su
    quattro record due sono caduti (un 502 e un timeout) per ragioni che non
    hanno niente a che vedere col giocatore. Perdere un record per un 502 e'
    lo stesso buco silenzioso che ARCH-003 ha gia' corretto sul WAF del
    comitato: un errore di rete non e' un'informazione sul dato.
    """
    for tentativo in range(1, tentativi + 1):
        try:
            res = requests.get(url, headers=_TM_HEADERS, timeout=timeout)
        except requests.RequestException as exc:
            motivo = type(exc).__name__
        else:
            if res.status_code == 200:
                corpo = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", res.text)
                return _WS.sub(" ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", corpo)))
            # 404 e 410 sono risposte sul profilo, non incidenti: non si ritenta
            if res.status_code in (404, 410):
                print(f"    [HTTP {res.status_code}] profilo non piu' esistente")
                return ""
            motivo = f"HTTP {res.status_code}"
        if tentativo < tentativi:
            time.sleep(pausa)
    print(f"    [rete] {motivo} dopo {tentativi} tentativi")
    return ""


def eta_da_nascita(nato: str) -> int | None:
    try:
        d = datetime.strptime(nato, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    oggi = datetime.now(timezone.utc).date()
    return oggi.year - d.year - ((oggi.month, oggi.day) < (d.month, d.day))


def aggiorna(opp: dict, dati: dict, adesso: str) -> list:
    """Scrive i campi freschi sul record. Ritorna cosa e' cambiato."""
    cambiati = []
    for campo in ("current_club", "market_value", "birth_date", "foot",
                  "height_cm", "market_value_text"):
        nuovo = dati.get(campo)
        if nuovo in (None, "", 0):
            continue
        if opp.get(campo) != nuovo:
            cambiati.append(f"{campo}: {opp.get(campo)!r} -> {nuovo!r}")
        opp[campo] = nuovo

    if dati.get("main_position") and not opp.get("role_name"):
        opp["role_name"] = opp["role"] = dati["main_position"]

    eta = eta_da_nascita(dati.get("birth_date") or opp.get("birth_date") or "")
    if eta and opp.get("age") != eta:
        cambiati.append(f"age: {opp.get('age')} -> {eta}")
        opp["age"] = eta

    club = (dati.get("current_club") or "").strip()
    opp["club_attuale_verificato"] = "" if (not club or SENZA_SQUADRA.search(club)) else club
    opp["refreshed_at"] = adesso
    # La scheda l'abbiamo aperta adesso: e' l'unica cosa che questo campo dice.
    opp["tm_verified_at"] = adesso
    return cambiati


def main() -> int:
    ap = argparse.ArgumentParser(description="Ri-verifica i record gia' provati")
    ap.add_argument("--dry-run", action="store_true", help="non scrive il database")
    ap.add_argument("--limite", type=int, default=0, help="quanti record al massimo")
    ap.add_argument("--pausa", type=float, default=1.5,
                    help="secondi fra due richieste (educazione verso il sito)")
    args = ap.parse_args()

    tutti = json.loads(DB.read_text(encoding="utf-8"))
    if isinstance(tutti, dict):
        tutti = tutti.get("opportunities", [])

    da_fare = [o for o in tutti if is_tm_verified(o) and url_profilo(o)]
    senza_url = sum(1 for o in tutti if is_tm_verified(o) and not url_profilo(o))
    if args.limite:
        da_fare = da_fare[:args.limite]
    print(f"record con prova: {len(da_fare)}"
          + (f" (+{senza_url} verificati ma senza URL utilizzabile)" if senza_url else ""))

    adesso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conta = {"letti": 0, "aggiornati": 0, "liberi": 0, "tesserati": 0, "falliti": 0}

    for i, opp in enumerate(da_fare, 1):
        nome = opp.get("player_name") or "?"
        url = url_profilo(opp)
        print(f"[{i}/{len(da_fare)}] {nome}")
        testo = scarica(url)
        conta["letti"] += 1
        if not testo:
            conta["falliti"] += 1
            time.sleep(args.pausa)
            continue
        dati = parse_tm_text(testo, url)
        if not dati:
            conta["falliti"] += 1
            time.sleep(args.pausa)
            continue
        cambiati = aggiorna(opp, dati, adesso)
        conta["aggiornati"] += 1
        club = opp.get("club_attuale_verificato")
        if club:
            conta["tesserati"] += 1
            print(f"    oggi gioca in: {club}")
        else:
            conta["liberi"] += 1
            print("    risulta SENZA SQUADRA")
        for c in cambiati[:4]:
            print(f"    {c}")
        time.sleep(args.pausa)

    print("\n" + " | ".join(f"{k}: {v}" for k, v in conta.items()))
    if args.dry_run:
        print("dry-run: database non toccato")
        return 0

    DB.write_text(json.dumps(tutti, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"scritto {DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
