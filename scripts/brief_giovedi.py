#!/usr/bin/env python3
"""
ARCH-003 — Il brief del giovedì, dal canale del comitato al telefono del DS.

Una catena sola, senza pezzi manuali:

    canale Telegram del comitato
      -> nuovi PDF dei Comunicati Ufficiali (SeenStore: i vecchi si saltano)
      -> parser giustizia sportiva (regex, zero LLM)
      -> data/ob1.db
      -> messaggio Telegram al DS

Costo di un giro: zero. Nessuna API a pagamento, nessun LLM, nessun servizio
in mezzo. È la condizione perché uno strumento del genere possa esistere per
un club che non ha budget.

Uso:
    # cosa manderebbe, senza mandarlo e senza toccare il db
    python scripts/brief_giovedi.py --club "NOCETO" --dry-run

    # giro completo: scopre, ingerisce, manda
    python scripts/brief_giovedi.py --club "NOCETO" --avversario "CASTENASO CALCIO"

    # solo ingestione, senza brief (per riempire lo storico)
    python scripts/brief_giovedi.py --solo-ingest

Configurazione (.env o environment):
    OB1_CU_CHANNEL     handle del canale del comitato (default: figccrer)
    OB1_CLUB           società del DS
    OB1_AVVERSARIO     prossimo avversario (facoltativo)
    TELEGRAM_BOT_TOKEN token di BotFather
    TELEGRAM_CHAT_ID   chat del DS (o TELEGRAM_CHAT_IDS per più destinatari)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.brief import build_brief, format_telegram
from src.cu_feed import new_cu_links
from src.cu_parser import CUStore, parse_cu_text, read_pdf
from src.watch.seen import SeenStore

# Verificato vivo il 07/08/2026: 17 comunicati in anteprima, l'ultimo dello
# stesso giorno. @figccrer risponde 200 ma non pubblica PDF — l'handle
# plausibile non è quello giusto, e questa è esattamente la ragione per cui il
# registro dei canali si costruisce con scripts/telegram_census.py e non a naso.
DEFAULT_CHANNEL = "lndemiliaromagna"


def ingest_new(store: CUStore, seen: SeenStore, channel: str, limit: int = 5) -> dict:
    """
    Scarica e ingerisce i CU non ancora visti. Il limite esiste perché al
    primo giro un canale può avere venti comunicati in anteprima: scaricarli
    tutti insieme è inutile (il brief guarda le ultime settimane) e maleducato
    verso il sito del comitato.
    """
    if not channel:
        # Non dovrebbe più accadere (vedi il commento su --canale in main()),
        # ma se accade di nuovo per un'altra via va gridato, non stampato
        # come "nessun comunicato nuovo" — quello sembra un canale pulito,
        # questo è un canale che non è mai stato interrogato.
        print("[ERRORE] canale vuoto: nessun fetch tentato, controlla "
              "OB1_CU_CHANNEL o --canale")
        return {"cu": 0, "new_sanctions": 0, "new_results": 0}

    links = new_cu_links(channel, seen=seen)
    if not links:
        print(f"@{channel}: nessun comunicato nuovo")
        return {"cu": 0, "new_sanctions": 0, "new_results": 0}

    totals = {"cu": 0, "new_sanctions": 0, "new_results": 0}
    for item in links[-limit:]:
        try:
            parsed = parse_cu_text(read_pdf(item["url"]))
        except Exception as exc:                      # PDF rotto o rete giù
            print(f"  [SALTATO] {item['url']}: {exc}")
            continue
        added = store.ingest(parsed)
        totals["cu"] += 1
        totals["new_sanctions"] += added["new_sanctions"]
        totals["new_results"] += added["new_results"]
        print(f"  CU {parsed['meta']['cu_number'] or '?'} "
              f"({item['url'].rsplit('/', 1)[-1]}): "
              f"+{added['new_sanctions']} sanzioni, +{added['new_results']} risultati")
    return totals


def main() -> int:
    ap = argparse.ArgumentParser(description="Brief del giovedì per il DS")
    ap.add_argument("--club", default=os.getenv("OB1_CLUB"))
    ap.add_argument("--avversario", default=os.getenv("OB1_AVVERSARIO"))
    # `or`, non il default a due argomenti di getenv: il workflow imposta
    # SEMPRE OB1_CU_CHANNEL nell'ambiente (${{ vars.OB1_CU_CHANNEL }}), anche
    # a stringa vuota quando la variabile non è configurata su GitHub. Una
    # chiave presente-ma-vuota non fa scattare il default di getenv(k, d) —
    # solo l'assenza totale della chiave lo fa. Bug vero, trovato dal primo
    # run reale: canale="" -> fetch di "t.me/s/" -> 404 silenzioso -> "nessun
    # comunicato nuovo", indistinguibile da un canale controllato e pulito.
    ap.add_argument("--canale", default=os.getenv("OB1_CU_CHANNEL") or DEFAULT_CHANNEL)
    ap.add_argument("--data", default=date.today().isoformat(),
                    help="data del brief (default: oggi)")
    ap.add_argument("--db", default="data/ob1.db")
    ap.add_argument("--facts", default="data/cu_facts.json",
                    help="memoria versionata: si legge all'avvio, si riscrive alla fine")
    ap.add_argument("--dry-run", action="store_true",
                    help="stampa il messaggio invece di inviarlo")
    ap.add_argument("--no-fetch", action="store_true",
                    help="usa solo quello che è già nel db")
    ap.add_argument("--solo-ingest", action="store_true",
                    help="ingerisce i nuovi CU senza produrre il brief")
    args = ap.parse_args()

    store = CUStore(args.db)

    # Il .db è nel .gitignore e su CI parte vuoto a ogni run: la stagione vive
    # nel JSON versionato. Ricaricarlo per primo è ciò che rende attendibile la
    # lista dei diffidati, che per definizione guarda tutta la storia.
    restored = store.import_facts(args.facts)
    if restored["sanctions"] or restored["results"]:
        print(f"memoria: +{restored['sanctions']} sanzioni, "
              f"+{restored['results']} risultati da {args.facts}")

    if not args.no_fetch:
        with SeenStore(args.db) as seen:
            ingest_new(store, seen, args.canale)
        totals = store.export_facts(args.facts)
        print(f"memoria aggiornata: {totals['sanctions']} sanzioni, "
              f"{totals['results']} risultati in {args.facts}")

    if args.solo_ingest:
        store.close()
        return 0

    if not args.club:
        print("Serve --club (o OB1_CLUB). Società presenti nel db:")
        for c in store.clubs():
            print(f"  {c}")
        store.close()
        return 2

    known = store.clubs()
    if not known:
        # Pre-stagione (solo calendari, niente sezione disciplinare): non è
        # un errore di configurazione, è la normalità di luglio-agosto. Non
        # possiamo nemmeno provare a risolvere il nome — non c'è ancora
        # niente con cui confrontarlo.
        print(f"Nessuna società ancora nei CU ingeriti (pre-stagione): "
              f"brief non inviato per {args.club!r}.")
        store.close()
        return 0

    club, candidates = store.resolve_club(args.club)
    if club is None:
        # Qui invece i CU parlano, e OB1_CLUB no: è la configurazione
        # sbagliata che va segnalata forte, non un "nessuna squalifica" che
        # sembra tutto ok e nasconde il problema per un'intera stagione.
        print(f"'{args.club}' non corrisponde a nessuna società vista nei CU.")
        print("Occhio a sigle societarie (SSDARL, 1907, ecc.) che il "
              "comitato può aggiungere o omettere. Più vicine:")
        for c in candidates:
            print(f"  {c}")
        store.close()
        return 2
    if club != args.club:
        print(f"  [match] '{args.club}' -> '{club}'")

    opponent = None
    if args.avversario:
        opponent, opp_candidates = store.resolve_club(args.avversario)
        if opponent is None:
            print(f"Avversario '{args.avversario}' non corrisponde a "
                  f"nessuna società vista nei CU. Più vicine:")
            for c in opp_candidates:
                print(f"  {c}")
            store.close()
            return 2
        if opponent != args.avversario:
            print(f"  [match] avversario '{args.avversario}' -> '{opponent}'")

    brief = build_brief(store, args.data, club, opponent=opponent)
    message = format_telegram(brief)
    store.close()

    if not brief["has_content"]:
        # Non è un errore: a inizio stagione, o dopo una sosta, non c'è nulla.
        # Lo diciamo invece di mandare un messaggio vuoto ogni settimana.
        print(f"Nessun provvedimento per {club}: brief non inviato.")
        return 0

    if args.dry_run:
        print("\n--- messaggio (HTML Telegram) ---")
        print(message)
        return 0

    from src.notifier import TelegramNotifier
    notifier = TelegramNotifier()
    if not notifier.enabled:
        print("Telegram non configurato: manca TELEGRAM_BOT_TOKEN.")
        print(message)
        return 1
    return 0 if notifier.send_message(message, parse_mode="HTML") else 1


if __name__ == "__main__":
    raise SystemExit(main())
