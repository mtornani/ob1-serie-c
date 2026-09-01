#!/usr/bin/env python3
"""
Toglie dai dati i `current_club` che non sono nomi di squadra.

Il parser che li ha scritti è stato sistemato (src/enricher_tm.forma_di_club),
ma un fix impedisce di scrivere altri valori falsi: non tocca quelli già
scritti, che restano in dashboard identici a un dato vero. Questo script fa la
seconda metà del lavoro.

Cosa toglie, e solo questo:
  - frammenti di tabella markdown copiati dalla pagina TM
    ("| --- | --- |", "| Costo |", "e ruolo | In carica da | ...")
  - righe con più campi fusi insieme
    ("attualmente sconosciuta Ala sinistra Valore di Mercato: - * 30/09/2004 ...")
  - frammenti di schema inventati dal modello (", competizione ecc.")

Cosa NON tocca:
  - "Svincolato" e gli altri stati senza squadra: non sono nomi di club ma sono
    risposte vere, ed è la risposta che questo prodotto cerca.

Toglie il valore anche dal grafo delle fonti (`grafo_fonti`), altrimenti la
riga di riconciliazione sulla card continuerebbe a mostrarlo come "quello che
diceva Transfermarkt".

    python scripts/pulisci_club_corrotti.py --prova     # mostra e basta
    python scripts/pulisci_club_corrotti.py             # scrive
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.enricher_tm import forma_di_club

DATA_FILE = Path("data/opportunities.json")

# Stessa lista di scripts/run_enrichment.py: uno stato non è un nome, ma è vero.
STATI_SENZA_SQUADRA = {
    'svincolato', 'senza squadra', 'senza club', 'ritiro', 'carriera conclusa',
    'free agent', 'without club', 'retired',
}


def da_togliere(valore) -> bool:
    if not isinstance(valore, str) or not valore.strip():
        return False
    if valore.strip().lower() in STATI_SENZA_SQUADRA:
        return False
    return not forma_di_club(valore)


def main() -> int:
    prova = "--prova" in sys.argv
    if not DATA_FILE.exists():
        print(f"manca {DATA_FILE}")
        return 1

    contenuto = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    opps = contenuto if isinstance(contenuto, list) else contenuto.get(
        "opportunities", contenuto.get("items", []))

    puliti = 0
    for o in opps:
        # Il valore sta in due posti: il campo del record e la copia dentro
        # `player_profile`. Pulirne uno solo lascia il falso visibile ovunque
        # legga l'altro — trovato leggendo il diff, non a mente.
        nidi = [o] + ([o["player_profile"]]
                      if isinstance(o.get("player_profile"), dict) else [])
        sporchi = [n for n in nidi if da_togliere(n.get("current_club"))]
        if not sporchi:
            continue
        print(f"  {o.get('player_name')}: {sporchi[0]['current_club']!r} -> None"
              f"{'  (+player_profile)' if len(sporchi) > 1 else ''}")
        for n in sporchi:
            n["current_club"] = None
        puliti += 1

        # `grafo_fonti` si tocca solo se c'è: assegnarlo comunque aggiungeva
        # una chiave a record che non l'avevano mai avuta.
        grafo = o.get("grafo_fonti")
        if not isinstance(grafo, dict):
            continue
        p = grafo.get("p") or {}
        rimasti = [oss for oss in (p.get("club") or [])
                   if not da_togliere(oss.get("valore"))]
        if rimasti:
            p["club"] = rimasti
        else:
            p.pop("club", None)
        if not p:
            o["grafo_fonti"] = None

    print(f"\n{puliti} valori tolti su {len(opps)} record")
    if prova:
        print("(--prova: niente scritto)")
        return 0
    if puliti:
        DATA_FILE.write_text(
            json.dumps(contenuto, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"scritto {DATA_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
