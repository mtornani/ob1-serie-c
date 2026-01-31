#!/usr/bin/env python3
"""
OB1 Serie C - Enhanced Telegram Notifier (NOTIF-001)
Notifiche actionable con scoring integrato
"""

import os
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()


class TelegramNotifier:
    """Gestisce notifiche Telegram arricchite per opportunita' di mercato"""

    # Chat ID di default (Mirko Tornani)
    DEFAULT_CHAT_ID = "1465485090"

    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_ids = self._parse_chat_ids()
        self.enabled = bool(self.bot_token)

        if not self.enabled:
            print("⚠️ Telegram notifier disabilitato (token mancante)")
        else:
            print(f"✅ Telegram notifier attivo - destinatari: {self.chat_ids}")

    def _parse_chat_ids(self) -> List[str]:
        """Parse TELEGRAM_CHAT_IDS o usa il canale di default"""
        raw = os.getenv('TELEGRAM_CHAT_IDS', '')
        if raw:
            return [cid.strip() for cid in raw.split(',') if cid.strip()]
        return [self.DEFAULT_CHAT_ID]

    def send_message(self, text: str, parse_mode: str = 'HTML', reply_markup: dict = None) -> bool:
        """Invia messaggio a tutti i chat configurati"""

        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        success = True

        for chat_id in self.chat_ids:
            try:
                payload = {
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': True
                }

                if reply_markup:
                    payload['reply_markup'] = json.dumps(reply_markup)

                resp = requests.post(url, json=payload, timeout=10)

                if resp.status_code != 200:
                    print(f"❌ Telegram error ({chat_id}): {resp.text}")
                    success = False

            except Exception as e:
                print(f"❌ Telegram exception ({chat_id}): {e}")
                success = False

        return success

    # =========================================================================
    # NOTIF-001: Enhanced Notification Formats
    # =========================================================================

    def format_hot_alert(self, opp: Dict[str, Any]) -> str:
        """
        Formatta alert per opportunita' HOT (score 80+)
        Massimo dettaglio per decisione rapida
        """
        player = opp.get('player_name', 'N/D')
        age = opp.get('age', '')
        role = opp.get('role_name', opp.get('role', ''))
        opp_type = opp.get('opportunity_type', 'mercato').upper()
        score = opp.get('ob1_score', 0)
        classification = opp.get('classification', 'warm')

        current_club = opp.get('current_club', '')
        previous_clubs = opp.get('previous_clubs', [])
        appearances = opp.get('appearances', 0)
        goals = opp.get('goals', 0)

        source = opp.get('source_name', 'N/D')
        source_url = opp.get('source_url', '')
        reported_date = opp.get('reported_date', '')
        summary = opp.get('summary', '')

        breakdown = opp.get('score_breakdown', {})

        # Build message
        lines = [
            "🔥 <b>ALERT PRIORITA' ALTA</b>",
            ""
        ]

        # Player header
        player_line = f"🎯 <b>{player}</b>"
        if age:
            player_line += f" ({age} anni)"
        lines.append(player_line)

        # Role
        if role:
            lines.append(f"📍 {role}")

        # Clubs
        if current_club:
            lines.append(f"🏟️ Attuale: {current_club}")
        if previous_clubs:
            clubs_str = ', '.join(previous_clubs[:3])
            if len(previous_clubs) > 3:
                clubs_str += '...'
            lines.append(f"📋 Ex: {clubs_str}")

        lines.append("")

        # Opportunity details
        lines.append(f"💼 <b>{opp_type}</b>")
        if reported_date:
            lines.append(f"📅 {reported_date}")
        lines.append(f"📊 OB1 Score: <b>{score}/100</b>")

        # Stats
        if appearances or goals:
            stats_parts = []
            if appearances:
                stats_parts.append(f"{appearances} presenze")
            if goals:
                stats_parts.append(f"{goals} gol")
            lines.append(f"📈 {' | '.join(stats_parts)}")

        lines.append("")

        # Summary (truncated)
        if summary and len(summary) > 10:
            truncated = summary[:150] + '...' if len(summary) > 150 else summary
            lines.append(f"💬 <i>{truncated}</i>")
            lines.append("")

        # Source
        lines.append(f"📰 {source}")
        if source_url:
            short_url = source_url[:60] + '...' if len(source_url) > 60 else source_url
            lines.append(f"🔗 {short_url}")

        # Score breakdown (compact)
        if breakdown:
            lines.append("")
            lines.append("━━━━━━━━━━━━━━")
            lines.append("<b>Score Breakdown:</b>")

            emoji_map = {
                'freshness': '⏰',
                'opportunity_type': '💼',
                'experience': '⭐',
                'age': '🎂',
                'source': '📰',
                'completeness': '✅'
            }

            for key, value in breakdown.items():
                emoji = emoji_map.get(key, '•')
                lines.append(f"  {emoji} {key}: {value}")

        return '\n'.join(lines)

    def format_warm_digest(self, opportunities: List[Dict[str, Any]]) -> str:
        """
        Formatta digest per opportunita' WARM (score 60-79)
        Lista compatta con info essenziali
        """
        today = datetime.now().strftime('%d/%m/%Y')

        lines = [
            "⚡ <b>DIGEST GIORNALIERO</b>",
            f"📅 {today}",
            "",
            f"<b>{len(opportunities)} opportunita' interessanti:</b>",
            ""
        ]

        for i, opp in enumerate(opportunities[:8], 1):
            player = opp.get('player_name', 'N/D')
            age = opp.get('age', '')
            role = opp.get('role_name', opp.get('role', ''))[:3].upper() if opp.get('role_name') or opp.get('role') else ''
            score = opp.get('ob1_score', 0)
            opp_type = opp.get('opportunity_type', 'mercato')
            current_club = opp.get('current_club', '')

            # Compact format
            player_info = f"<b>{player}</b>"
            if age:
                player_info += f" ({age}"
                if role:
                    player_info += f", {role}"
                player_info += ")"
            elif role:
                player_info += f" ({role})"

            lines.append(f"{i}. ⚡ {player_info} - Score {score}")

            # Second line with details
            detail = f"   {opp_type.title()}"
            if current_club:
                detail += f" | {current_club}"
            lines.append(detail)
            lines.append("")

        if len(opportunities) > 8:
            lines.append(f"<i>...e altre {len(opportunities) - 8} opportunita'</i>")
            lines.append("")

        lines.append("📋 Dettagli completi sulla dashboard")

        return '\n'.join(lines)

    def format_cold_summary(self, count: int) -> str:
        """
        Formatta riga per opportunita' COLD (score <60)
        Solo menzione, no dettagli
        """
        if count == 0:
            return ""
        return f"❄️ {count} altre segnalazioni a bassa priorita' sulla dashboard"

    def get_inline_keyboard(self, opp_id: str) -> dict:
        """
        Crea inline keyboard per alert HOT
        """
        return {
            "inline_keyboard": [
                [
                    {"text": "📋 Salva", "callback_data": f"save_{opp_id}"},
                    {"text": "❌ Ignora", "callback_data": f"ignore_{opp_id}"}
                ],
                [
                    {"text": "📊 Dettagli", "callback_data": f"details_{opp_id}"},
                    {"text": "🔍 Dashboard", "url": "https://mirkotornani.github.io/ob1-serie-c-dev/"}
                ]
            ]
        }

    # =========================================================================
    # Main Notification Methods
    # =========================================================================

    def notify_scored_opportunities(self, opportunities: List[Dict[str, Any]], dashboard_url: str = None) -> bool:
        """
        Notifica opportunita' con scoring NOTIF-001

        - HOT (80+): Alert individuale immediato
        - WARM (60-79): Digest compatto
        - COLD (<60): Solo menzione
        """
        if not opportunities:
            print("No opportunities to notify")
            return True

        # Classify by score
        hot = [o for o in opportunities if o.get('classification') == 'hot']
        warm = [o for o in opportunities if o.get('classification') == 'warm']
        cold = [o for o in opportunities if o.get('classification') == 'cold']

        print(f"📊 Classification: {len(hot)} HOT, {len(warm)} WARM, {len(cold)} COLD")

        success = True

        # 1. Send HOT alerts (individual, with keyboard)
        for opp in hot[:5]:  # Max 5 HOT alerts per run
            msg = self.format_hot_alert(opp)
            opp_id = opp.get('id', 'unknown')
            keyboard = self.get_inline_keyboard(opp_id)

            if not self.send_message(msg, reply_markup=keyboard):
                success = False

        # 2. Send WARM digest (single message)
        if warm:
            msg = self.format_warm_digest(warm)
            if not self.send_message(msg):
                success = False

        # 3. Mention COLD count (if any)
        if cold:
            cold_msg = self.format_cold_summary(len(cold))
            if cold_msg and not self.send_message(cold_msg):
                success = False

        return success

    def notify_new_opportunities(self, opportunities: List[dict], dashboard_url: Optional[str] = None) -> bool:
        """
        Legacy method - ora usa notify_scored_opportunities se disponibile scoring
        """
        # Check if opportunities have scoring data
        if opportunities and 'ob1_score' in opportunities[0]:
            return self.notify_scored_opportunities(opportunities, dashboard_url)

        # Fallback to simple notification
        return self._notify_simple(opportunities, dashboard_url)

    def _notify_simple(self, opportunities: List[dict], dashboard_url: Optional[str] = None) -> bool:
        """Notifica semplice (fallback senza scoring)"""

        if not opportunities:
            return True

        msg_lines = [
            "🔔 <b>OB1 SCOUT - Nuove Opportunita'!</b>",
            f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            f"📊 Trovate <b>{len(opportunities)}</b> nuove segnalazioni",
            ""
        ]

        for i, opp in enumerate(opportunities[:5], 1):
            player = opp.get('player_name', 'N/D')
            club = opp.get('current_club', 'N/D')
            opp_type = opp.get('opportunity_type', 'mercato')

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

        if len(opportunities) > 5:
            msg_lines.append(f"<i>...e altre {len(opportunities) - 5} opportunita'</i>")
            msg_lines.append("")

        if dashboard_url:
            msg_lines.append(f"🌐 <a href='{dashboard_url}'>Apri Dashboard</a>")

        return self.send_message('\n'.join(msg_lines))

    def notify_daily_summary(self, stats: dict, dashboard_url: Optional[str] = None) -> bool:
        """Invia riepilogo giornaliero con stats scoring"""

        msg_lines = [
            "📊 <b>OB1 SCOUT - Riepilogo Giornaliero</b>",
            f"📅 {datetime.now().strftime('%d/%m/%Y')}",
            "",
            f"🔍 Notizie analizzate: <b>{stats.get('news_analyzed', 0)}</b>",
            f"🎯 Opportunita' trovate: <b>{stats.get('total', 0)}</b>",
            ""
        ]

        # Scoring stats
        if 'hot' in stats or 'warm' in stats or 'cold' in stats:
            msg_lines.append("<b>Per priorita':</b>")
            msg_lines.append(f"  🔥 HOT: {stats.get('hot', 0)}")
            msg_lines.append(f"  ⚡ WARM: {stats.get('warm', 0)}")
            msg_lines.append(f"  ❄️ COLD: {stats.get('cold', 0)}")
            msg_lines.append("")

        # By type
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
        # Test with scored opportunity
        test_opps = [
            {
                'id': 'test_001',
                'player_name': 'Marco Rossi',
                'age': 25,
                'role_name': 'Centrocampista',
                'opportunity_type': 'svincolato',
                'current_club': 'Ex Pescara',
                'previous_clubs': ['Pescara', 'Reggiana', 'Modena'],
                'appearances': 85,
                'goals': 12,
                'ob1_score': 87,
                'classification': 'hot',
                'reported_date': '2026-01-31',
                'source_name': 'TuttoC',
                'source_url': 'https://tuttoc.com/articolo-esempio',
                'summary': 'Centrocampista esperto svincolato dopo 3 stagioni in Serie B',
                'score_breakdown': {
                    'freshness': 100,
                    'opportunity_type': 100,
                    'experience': 85,
                    'age': 100,
                    'source': 95,
                    'completeness': 80
                }
            },
            {
                'id': 'test_002',
                'player_name': 'Luca Bianchi',
                'age': 24,
                'role_name': 'Difensore',
                'opportunity_type': 'prestito',
                'ob1_score': 72,
                'classification': 'warm',
                'current_club': 'Milan Primavera'
            },
            {
                'id': 'test_003',
                'player_name': 'Giuseppe Verdi',
                'age': 22,
                'role_name': 'Attaccante',
                'opportunity_type': 'mercato',
                'ob1_score': 65,
                'classification': 'warm',
                'current_club': 'Juventus U23'
            }
        ]

        notifier.notify_scored_opportunities(test_opps)
        print("✅ Test notifications sent!")
    else:
        print("❌ Notifier not configured")
