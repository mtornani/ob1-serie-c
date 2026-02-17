#!/usr/bin/env python3
"""
OB1 Serie C - Quick Ingest from existing JSON
Carica dati esistenti nel File Search Store senza scraping
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from io import TextIOWrapper

# Force UTF-8 output
sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

load_dotenv()

# Gemini imports
try:
    from google import genai
    from google.genai import types

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("[WARN] google-genai non installato. Esegui: pip install google-genai")
    sys.exit(1)

DATA_FILE = Path("data/opportunities.json")
STORE_NAME = "ob1-serie-c-knowledge"


def create_document_from_opportunities():
    """Crea documento markdown da opportunities.json"""

    print(f"[INFO] Caricamento dati da {DATA_FILE}...")

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    opportunities = data if isinstance(data, list) else data.get("opportunities", [])
    print(f"[OK] Trovate {len(opportunities)} opportunità")

    lines = [
        "# OB1 SERIE C - DATABASE GIOCATORI AGGIORNATO",
        f"Data aggiornamento: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Totale giocatori: {len(opportunities)}",
        "",
        "## NUOVI CAMPI DISPONIBILI (DATA-003)",
        "- Agente/Agenzia del giocatore",
        "- Presenze stagionali 2025/26",
        "- Gol stagionali 2025/26",
        "- Assist stagionali 2025/26",
        "- Minuti giocati stagionali 2025/26",
        "",
        "---",
        "",
    ]

    for opp in opportunities:
        # Header
        player_name = opp.get("player_name", "Sconosciuto")
        lines.append(f"## {player_name}")
        lines.append("")

        # Info base
        if opp.get("age"):
            lines.append(f"Età: {opp['age']} anni")
        if opp.get("nationality"):
            lines.append(f"Nazionalità: {opp['nationality']}")
        if opp.get("second_nationality"):
            lines.append(f"Seconda nazionalità: {opp['second_nationality']}")
        if opp.get("role_name"):
            lines.append(f"Ruolo: {opp['role_name']}")
        if opp.get("foot"):
            lines.append(f"Piede: {opp['foot']}")
        if opp.get("height_cm"):
            lines.append(f"Altezza: {opp['height_cm']} cm")
        if opp.get("market_value_formatted"):
            lines.append(f"Valore di mercato: {opp['market_value_formatted']}")

        lines.append("")

        # Situazione contrattuale
        lines.append("### SITUAZIONE CONTRATTUALE")
        if opp.get("opportunity_type"):
            lines.append(f"Tipo opportunità: {opp['opportunity_type']}")
        if opp.get("current_club"):
            lines.append(f"Club attuale: {opp['current_club']}")
        if opp.get("contract_expires"):
            lines.append(f"Scadenza contratto: {opp['contract_expires']}")

        # NUOVI CAMPI - Agente
        if opp.get("agent"):
            lines.append(f"Agente: {opp['agent']}")

        lines.append("")

        # NUOVI CAMPI - Statistiche
        has_stats = any(
            [
                opp.get("appearances"),
                opp.get("goals"),
                opp.get("assists"),
                opp.get("minutes_played"),
            ]
        )

        if has_stats:
            lines.append("### STATISTICHE STAGIONE 2025/26")
            if opp.get("appearances"):
                lines.append(f"Presenze: {opp['appearances']}")
            if opp.get("goals"):
                lines.append(f"Gol: {opp['goals']}")
            if opp.get("assists"):
                lines.append(f"Assist: {opp['assists']}")
            if opp.get("minutes_played"):
                lines.append(f"Minuti giocati: {opp['minutes_played']}")
            lines.append("")

        # Storico
        if opp.get("previous_clubs"):
            lines.append(f"Club precedenti: {', '.join(opp['previous_clubs'])}")
            lines.append("")

        # Link TM
        if opp.get("tm_url"):
            lines.append(f"Profilo Transfermarkt: {opp['tm_url']}")
            lines.append("")

        # Summary
        if opp.get("summary"):
            lines.append(f"Note: {opp['summary']}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def ingest_to_gemini(content: str):
    """Carica contenuto nel File Search Store"""

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY mancante")

    client = genai.Client(api_key=api_key)

    # Trova o crea store
    print("[INFO] Connessione al File Search Store...")
    store = None
    try:
        stores = list(client.file_search_stores.list())
        for s in stores:
            if STORE_NAME in s.display_name:
                store = s
                print(f"[OK] Store esistente trovato: {s.name}")
                break
    except Exception as e:
        print(f"[WARN] Errore listing stores: {e}")

    if not store:
        print(f"[INFO] Creazione nuovo store: {STORE_NAME}")
        store = client.file_search_stores.create(config={"display_name": STORE_NAME})
        print(f"[OK] Store creato: {store.name}")

    # Salva file temporaneo
    today = datetime.now().strftime("%Y-%m-%d")
    temp_path = Path(f"/tmp/ob1_complete_{today}.md")
    temp_path.write_text(content, encoding="utf-8")

    print(f"[INFO] Uploading documento ({len(content)} caratteri)...")

    try:
        operation = client.file_search_stores.upload_to_file_search_store(
            file=str(temp_path),
            file_search_store_name=store.name,
            config={
                "display_name": f"ob1_complete_{today}",
                "mime_type": "text/markdown",
            },
        )

        print("[INFO] Indicizzazione in corso...")
        import time

        while not operation.done:
            time.sleep(3)
            operation = client.operations.get(operation)

        print("[OK] Documento indicizzato con successo!")

    except Exception as e:
        print(f"[ERROR] Errore upload: {e}")
        raise

    finally:
        if temp_path.exists():
            temp_path.unlink()


def main():
    print("=" * 60)
    print("OB1 QUICK INGEST - From JSON to Gemini")
    print("=" * 60)
    print("")

    if not DATA_FILE.exists():
        print(f"[ERROR] File {DATA_FILE} non trovato!")
        return

    try:
        # Crea documento
        print("[STEP 1/2] Creazione documento dai dati JSON...")
        doc_content = create_document_from_opportunities()
        print(f"[OK] Documento creato: {len(doc_content)} caratteri")
        print("")

        # Carica su Gemini
        print("[STEP 2/2] Caricamento su Gemini File Search...")
        ingest_to_gemini(doc_content)
        print("")

        print("=" * 60)
        print("[SUCCESS] KNOWLEDGE BASE AGGIORNATA!")
        print("=" * 60)
        print("")
        print("Ora puoi avviare il bot Telegram:")
        print("  python bot/telegram_bot.py")
        print("")

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
