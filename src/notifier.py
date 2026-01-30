#!/usr/bin/env python3
"""
OB1 Serie C - Telegram Notifier
Invia notifiche push quando trova nuove opportunita'
"""

import os
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


class TelegramNotifier:
    """Gestisce notifiche Telegram per nuove opportunita'"""

    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_ids = self._parse_chat_ids()
        self.enabled = bool(self.bot_token and self.chat_ids)

        if not self.enabled:
            print("⚠️ Telegram notifier disabilitato (token o chat_id mancanti)")

    def _parse_chat_ids(self) -> List[str]:
        """Parse TELEGRAM_CHAT_IDS (comma-separated)"""
        raw = os.getenv('TELEGRAM_CHAT_IDS', '')
        if not raw:
            # Fallback to single TELEGRAM_CHAT_ID
            single = os.getenv('TELEGRAM_CHAT_ID', '')
            return [single] if single else []
        return [cid.strip() for cid in raw.split(',') if cid.strip()]

    def send_message(self, text: str, parse_mode: str = 'HTML') -> bool:
        """Invia messaggio a tutti i chat configurati"""

        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        success = True

        for chat_id in self.chat_ids:
            try:
                resp = requests.post(url, json={
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': True
                }, timeout=10)

                if resp.status_code != 200:
                    print(f"❌ Telegram error ({chat_id}): {resp.text}")
                    success = False

            except Exception as e:
                print(f"❌ Telegram exception ({chat_id}): {e}")
                success = False

        return success

    def notify_new_opportunities(self, opportunities: List[dict], dashboard_url: Optional[str] = None) -> bool:
        """Notifica nuove opportunita' trovate"""

        if not opportunities:
            return True

        # Header
        msg_lines = [
            "🔔 <b>OB1 SCOUT - Nuove Opportunita'!</b>",
            f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            f"📊 Trovate <b>{len(opportunities)}</b> nuove segnalazioni",
            ""
        ]

        # Top 5 opportunities
        for i, opp in enumerate(opportunities[:5], 1):
            player = opp.get('player_name', 'N/D')
            club = opp.get('current_club', 'N/D')
            opp_type = opp.get('opportunity_type', 'mercato')

            # Emoji per tipo
            emoji_map = {
                'svincolato': '🟢',
                'prestito': '🔵',
                'rescissione': '🟡',
                'scadenza': '🟠',
                'mercato': '⚪'
            }
            emoji = emoji_map.get(opp_type.lower(), '⚪')

            msg_lines.append(f"{emoji} <b>{player}</b>")
            msg_lines.append(f"   📍 {club} | {opp_type}")
            msg_lines.append("")

        # More indicator
        if len(opportunities) > 5:
            msg_lines.append(f"<i>...e altre {len(opportunities) - 5} opportunita'</i>")
            msg_lines.append("")

        # Dashboard link
        if dashboard_url:
            msg_lines.append(f"🌐 <a href='{dashboard_url}'>Apri Dashboard</a>")

        return self.send_message('\n'.join(msg_lines))

    def notify_daily_summary(self, stats: dict, dashboard_url: Optional[str] = None) -> bool:
        """Invia riepilogo giornaliero"""

        msg_lines = [
            "📊 <b>OB1 SCOUT - Riepilogo Giornaliero</b>",
            f"📅 {datetime.now().strftime('%d/%m/%Y')}",
            "",
            f"🔍 Notizie analizzate: <b>{stats.get('news_analyzed', 0)}</b>",
            f"🎯 Opportunita' trovate: <b>{stats.get('opportunities_found', 0)}</b>",
            f"👤 Giocatori tracciati: <b>{stats.get('players_tracked', 0)}</b>",
            ""
        ]

        # Top per tipo
        by_type = stats.get('by_type', {})
        if by_type:
            msg_lines.append("<b>Per categoria:</b>")
            for type_name, count in by_type.items():
                msg_lines.append(f"  • {type_name}: {count}")
            msg_lines.append("")

        if dashboard_url:
            msg_lines.append(f"🌐 <a href='{dashboard_url}'>Dashboard Completa</a>")

        return self.send_message('\n'.join(msg_lines))

    def notify_error(self, error_msg: str) -> bool:
        """Notifica errori critici"""

        msg = f"⚠️ <b>OB1 SCOUT - Errore</b>\n\n{error_msg}"
        return self.send_message(msg)


# =============================================================================
# STANDALONE USAGE
# =============================================================================

if __name__ == "__main__":
    notifier = TelegramNotifier()

    if notifier.enabled:
        # Test message
        test_opps = [
            {'player_name': 'Mario Rossi', 'current_club': 'Cesena', 'opportunity_type': 'svincolato'},
            {'player_name': 'Luca Bianchi', 'current_club': 'Rimini', 'opportunity_type': 'prestito'},
        ]
        notifier.notify_new_opportunities(test_opps, "https://example.github.io/ob1-scout")
        print("✅ Test notification sent!")
    else:
        print("❌ Notifier not configured")
