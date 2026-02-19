#!/usr/bin/env python3
"""
OB1 Scout - Invio Report Pubblico su Canale Telegram (DATA-003-MW3)

Legge data/social/weekly_telegram_post.txt e lo invia al canale pubblico @ob1scout.
Dopo l'invio pubblico, invia il contenuto di weekly_x_post.txt al chat privato
di Mirko, pronto da copiare e incollare su X.

Viene chiamato dal workflow GitHub Actions dopo generate_social_post.py.

Variabili d'ambiente richieste:
  TELEGRAM_BOT_TOKEN          — Token del bot (stesso del privato)
  TELEGRAM_PUBLIC_CHANNEL_ID  — ID o @username del canale pubblico (es: @ob1scout)
  TELEGRAM_CHAT_ID            — Chat ID privato per il post X (default: 1465485090)
"""

import os
import sys
import requests
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
SOCIAL_FILE = BASE_DIR / "data" / "social" / "weekly_telegram_post.txt"
X_POST_FILE = BASE_DIR / "data" / "social" / "weekly_x_post.txt"

DEFAULT_PRIVATE_CHAT_ID = "1465485090"

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_to_channel(token: str, channel_id: str, text: str) -> bool:
    """Invia messaggio al canale pubblico. Niente inline keyboard, niente score breakdown."""
    url = TELEGRAM_API.format(token=token)

    # Telegram ha limite di 4096 char per messaggio
    if len(text) > 4096:
        text = text[:4090] + "\n[...]"

    payload = {
        "chat_id": channel_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print(f"✅ Messaggio inviato al canale {channel_id}")
            return True
        else:
            print(f"❌ Errore Telegram ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Eccezione invio Telegram: {e}")
        return False


def send_x_post_to_private(token: str) -> bool:
    """Invia il contenuto di weekly_x_post.txt al chat privato, pronto per copia-incolla su X."""
    private_chat_id = os.getenv("TELEGRAM_CHAT_ID", DEFAULT_PRIVATE_CHAT_ID)

    if not X_POST_FILE.exists():
        print("⚠️ weekly_x_post.txt non trovato — skip invio post X al privato")
        return False

    x_text = X_POST_FILE.read_text(encoding="utf-8").strip()
    if not x_text:
        print("⚠️ weekly_x_post.txt vuoto — skip invio post X al privato")
        return False

    message = f"\U0001f4f1 POST PER X — Copia e incolla:\n\n{x_text}"

    url = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": private_chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print(f"✅ Post X inviato al chat privato {private_chat_id}")
            return True
        else:
            print(f"❌ Errore invio post X al privato ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        print(f"❌ Eccezione invio post X al privato: {e}")
        return False


def main():
    print("📢 Send Public Telegram Report (DATA-003-MW3)")

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    channel_id = os.getenv("TELEGRAM_PUBLIC_CHANNEL_ID")

    if not token:
        print("⚠️ TELEGRAM_BOT_TOKEN non configurato — skip invio pubblico")
        sys.exit(0)

    if not channel_id:
        print("⚠️ TELEGRAM_PUBLIC_CHANNEL_ID non configurato — skip invio pubblico")
        sys.exit(0)

    if not SOCIAL_FILE.exists():
        print(f"❌ File non trovato: {SOCIAL_FILE}")
        print("   Assicurarsi che generate_social_post.py sia stato eseguito prima.")
        sys.exit(1)

    text = SOCIAL_FILE.read_text(encoding="utf-8").strip()

    if not text:
        print("⚠️ File social post vuoto — skip invio")
        sys.exit(0)

    print(f"   Canale: {channel_id}")
    print(f"   Lunghezza testo: {len(text)} char")

    success = send_to_channel(token, channel_id, text)

    # --- Invia post X al chat privato di Mirko ---
    send_x_post_to_private(token)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
