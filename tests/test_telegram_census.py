#!/usr/bin/env python3
"""
Test offline del censimento canali Telegram (ARCH-003).

Il caso che ha motivato tutto: un canale che risponde 200 con messaggi
visibili ma vecchi di due anni e con l'annuncio di migrazione in coda NON è
attivo. Il verdetto deve uscire dalle prove, con regole ricalcolabili.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_telegram_census -v
"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.telegram_census import classify, parse_preview, verdict

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


def _page(messages: str, title="LND Test", subs="1 234 subscribers"):
    return f'''<html><head>
<meta property="og:title" content="{title}">
</head><body>{subs}<section>{messages}</section></body></html>'''


def _msg(date_iso: str, body_html: str) -> str:
    return (f'<div class="tgme_widget_message_wrap js-widget">'
            f'<div class="tgme_widget_message " data-post="x/1">'
            f'<div class="tgme_widget_message_text js-message_text">{body_html}</div>'
            f'<time datetime="{date_iso}"></time></div>')


CU_LINK = ('Cu 11 del 05.08.26 <a href="https://www.figccrer.it/files/'
           'comunicati/2026/7504/cu11.pdf">pdf</a>')


class ParseTestCase(unittest.TestCase):
    def test_extracts_last_message_date_and_signals(self):
        page = _page(_msg("2026-07-30T10:00:00+00:00", CU_LINK)
                     + _msg("2026-08-05T14:32:00+00:00", CU_LINK))
        ev = parse_preview(page)
        self.assertEqual(ev["visible_messages"], 2)
        self.assertEqual(ev["last_message_at"], "2026-08-05T14:32:00+00:00")
        self.assertEqual(ev["content_signals"]["comunicati_pdf"], 2)
        self.assertFalse(ev["migrated"])

    def test_migration_notice_in_tail_is_detected(self):
        page = _page(_msg("2024-08-03T11:15:00+00:00",
                          'Nuovo canale della Delegazione '
                          '<a href="https://t.me/+Xk1fYZo7s5swOTNk">qui</a> '
                          'a breve il presente sara disattivato'))
        ev = parse_preview(page)
        self.assertTrue(ev["migrated"])
        self.assertEqual(ev["migration_targets"], ["t.me/+Xk1fYZo7s5swOTNk"])

    def test_old_invite_link_alone_is_not_a_migration(self):
        """Un invito citato di passaggio, senza parole di migrazione, non basta."""
        page = _page(_msg("2026-08-01T10:00:00+00:00",
                          'iscrivetevi anche a t.me/+abc123 per il torneo estivo'))
        self.assertFalse(parse_preview(page)["migrated"])

    def test_empty_page_yields_no_messages(self):
        ev = parse_preview("")
        self.assertEqual(ev["visible_messages"], 0)
        self.assertIsNone(ev["last_message_at"])


class VerdictTestCase(unittest.TestCase):
    """Il caso @lndlombardia: 200 + messaggi visibili NON implica attivo."""

    def test_http_200_with_2024_messages_and_migration_is_migrated_not_active(self):
        page = _page(_msg("2024-09-10T06:20:00+00:00",
                          'Nuovo canale Telegram <a href="https://t.me/+bRy">qui</a> '
                          'per restare aggiornati'))
        self.assertEqual(verdict(200, parse_preview(page), NOW), "migrato")

    def test_recent_messages_mean_active(self):
        page = _page(_msg("2026-08-05T14:32:00+00:00", CU_LINK))
        self.assertEqual(verdict(200, parse_preview(page), NOW), "attivo")

    def test_stale_channel_without_migration_is_dead(self):
        page = _page(_msg("2023-07-26T14:32:00+00:00", "clip del contest"))
        self.assertEqual(verdict(200, parse_preview(page), NOW), "morto")

    def test_non_200_or_no_preview_is_nonexistent(self):
        self.assertEqual(verdict(302, parse_preview(""), NOW), "inesistente")
        self.assertEqual(verdict(200, parse_preview(_page("")), NOW), "inesistente")

    def test_summer_pause_within_45_days_is_still_active(self):
        """Un comitato fermo 5 settimane d'estate non va dichiarato morto."""
        page = _page(_msg("2026-07-01T10:00:00+00:00", CU_LINK))
        self.assertEqual(verdict(200, parse_preview(page), NOW), "attivo")


class ClassifyTestCase(unittest.TestCase):
    def test_cu_feed_is_recognised(self):
        page = _page("".join(_msg(f"2026-08-0{i}T10:00:00+00:00", CU_LINK)
                             for i in range(1, 4)))
        self.assertEqual(classify(parse_preview(page)), "feed_comunicati")

    def test_generic_news_is_the_fallback(self):
        page = _page(_msg("2026-08-05T10:00:00+00:00", "gol spettacolare ieri"))
        self.assertEqual(classify(parse_preview(page)), "news_generiche")


if __name__ == "__main__":
    unittest.main(verbosity=2)
