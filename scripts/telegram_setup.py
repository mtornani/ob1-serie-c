#!/usr/bin/env python3
"""
Verifica la configurazione Telegram e trova il chat id per il brief.

⚠️  NON TOCCA IL WEBHOOK. Il bot di scouting Lega Pro (workers/telegram-bot,
Cloudflare Worker) riceve i messaggi via webhook. Telegram consente UN solo
consumatore degli aggiornamenti: finché il webhook è attivo, getUpdates
risponde 409 Conflict. La "soluzione" ovvia — chiamare deleteWebhook — spegne
il bot in produzione, e nessuno se ne accorge finché un DS non scrive e non
riceve risposta. Questo script quindi rileva il webhook e si ferma, invece di
rimuoverlo.

Il brief invece convive senza problemi: mandare messaggi (sendMessage) non
confligge con il webhook, che riguarda solo la RICEZIONE. Il DS resta con un
bot solo — cerca i giocatori scrivendo, e riceve il brief senza chiedere.

Uso:
    python scripts/telegram_setup.py

Se il bot è nuovo (nessun webhook), lo script elenca le chat che gli hanno
scritto e stampa la riga da mettere in .env. Se il webhook è attivo, spiega
come recuperare il chat id senza rompere niente.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from dotenv import load_dotenv

load_dotenv()

API = "https://api.telegram.org/bot{token}/{method}"


def call(token: str, method: str) -> dict:
    try:
        return requests.get(API.format(token=token, method=method), timeout=15).json()
    except requests.RequestException as exc:
        return {"ok": False, "description": str(exc)}


def _explain_webhook(hook: dict) -> None:
    print(f"\n⚠️  Webhook ATTIVO su: {hook.get('url')}")
    print("   È il bot di scouting Lega Pro (workers/telegram-bot).")
    print("   Non lo tocco: rimuoverlo spegnerebbe il bot in produzione.\n")
    print("   Il brief funziona lo stesso — inviare non confligge con il webhook.")
    print("   Per il chat id, senza rompere niente, una di queste:\n")
    print("   a) usa quello già configurato: TELEGRAM_CHAT_ID nei secret del repo;")
    print("   b) su Telegram scrivi a @userinfobot: risponde con il tuo id;")
    print("   c) per un gruppo: aggiungi @userinfobot al gruppo, leggi l'id")
    print("      (è negativo, è normale) e poi rimuovilo.")


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN non impostato.\n")
        print("  1. Telegram -> @BotFather -> /newbot (o /token per uno esistente)")
        print("  2. copia il token nel file .env:  TELEGRAM_BOT_TOKEN=...")
        print("  3. rilancia questo comando")
        return 2

    me = call(token, "getMe")
    if not me.get("ok"):
        print(f"Token rifiutato da Telegram: {me.get('description', '?')}")
        print("Controlla di averlo copiato per intero, senza spazi.")
        return 1
    bot = me["result"]
    print(f"Bot valido: @{bot.get('username')} ({bot.get('first_name')})")

    info = call(token, "getWebhookInfo")
    hook = info.get("result") or {}
    if hook.get("url"):
        _explain_webhook(hook)
        chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_IDS")
        if chat_id:
            print(f"\n   Nel tuo ambiente c'è già: {chat_id}")
            print('   Prova:  python scripts/brief_giovedi.py --club "RIMINI" --dry-run')
        return 0

    # Nessun webhook: bot nuovo, getUpdates è sicuro.
    updates = call(token, "getUpdates")
    if not updates.get("ok"):
        print(f"getUpdates fallito: {updates.get('description', '?')}")
        return 1

    chats = {}
    for upd in updates.get("result", []):
        chat = (upd.get("message") or upd.get("channel_post") or {}).get("chat") or {}
        if chat.get("id") is not None:
            chats[chat["id"]] = chat

    if not chats:
        print("\nNessuna chat trovata.")
        print("Scrivi un messaggio qualsiasi al bot su Telegram, poi rilancia.")
        print("(Telegram conserva gli aggiornamenti 24 ore: se hai scritto ieri,")
        print(" scrivi di nuovo.)")
        return 1

    print(f"\nChat trovate ({len(chats)}):\n")
    for cid, chat in chats.items():
        name = (chat.get("title") or
                " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")])) or
                chat.get("username") or "-")
        print(f"  {cid:>16}   {chat.get('type', '?'):<10} {name}")

    print("\nIncolla in .env la riga con il destinatario del brief:\n")
    for cid in chats:
        print(f"  TELEGRAM_CHAT_ID={cid}")
    if len(chats) > 1:
        print(f"\n  (piu' destinatari: TELEGRAM_CHAT_IDS="
              f"{','.join(str(c) for c in chats)})")

    print("\nProva subito, senza inviare nulla:")
    print('  python scripts/brief_giovedi.py --club "RIMINI" --dry-run')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
