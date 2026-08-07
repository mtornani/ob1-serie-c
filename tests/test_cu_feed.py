#!/usr/bin/env python3
"""
Test offline della scoperta dei CU dal canale Telegram del comitato (ARCH-003).

Le fixture riproducono il markup reale di t.me/s/<handle> e il modo in cui i
comitati postano davvero: "Cu 11 del 05.08.26" con il link al PDF. Sullo
stesso canale finiscono anche moduli e circolari, che PDF sono ma comunicati no.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_cu_feed -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cu_feed import parse_cu_feed
from src.watch.seen import SeenStore


def _msg(date_iso: str, body_html: str) -> str:
    return (f'<div class="tgme_widget_message_wrap js-widget">'
            f'<div class="tgme_widget_message " data-post="x/1">'
            f'<div class="tgme_widget_message_text js-message_text">{body_html}</div>'
            f'<time datetime="{date_iso}"></time></div>')


def _page(*messages: str) -> str:
    return f"<html><body><section>{''.join(messages)}</section></body></html>"


PDF = "https://www.figccrer.it/files/comunicati/2026/7504/cu11.pdf"


class ParseTestCase(unittest.TestCase):
    def test_trova_il_pdf_il_numero_e_la_data(self):
        page = _page(_msg("2026-08-05T14:32:00+00:00",
                          f'Cu 11 del 05.08.26 <a href="{PDF}">scarica</a>'))
        items = parse_cu_feed(page)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], PDF)
        self.assertEqual(items[0]["cu_number"], 11)
        self.assertEqual(items[0]["posted_at"], "2026-08-05T14:32:00+00:00")

    def test_riconosce_la_forma_estesa_del_numero(self):
        page = _page(_msg("2026-04-13T09:00:00+00:00",
                          f'COMUNICATO UFFICIALE N. 146 <a href="{PDF}">pdf</a>'))
        self.assertEqual(parse_cu_feed(page)[0]["cu_number"], 146)

    def test_messaggio_senza_pdf_ignorato(self):
        page = _page(_msg("2026-08-05T14:32:00+00:00",
                          'Buone vacanze a tutte le societa'))
        self.assertEqual(parse_cu_feed(page), [])

    def test_moduli_e_circolari_non_sono_comunicati(self):
        """Sullo stesso canale passano PDF che non sono CU: vanno esclusi."""
        page = _page(
            _msg("2026-08-01T10:00:00+00:00",
                 'Modulo iscrizione campionato <a href="https://x.it/modulo.pdf">qui</a>'),
            _msg("2026-08-05T14:32:00+00:00", f'Cu 11 <a href="{PDF}">pdf</a>'))
        items = parse_cu_feed(page)
        self.assertEqual([i["url"] for i in items], [PDF])

    def test_piu_allegati_nello_stesso_messaggio(self):
        page = _page(_msg("2026-08-05T14:32:00+00:00",
                          f'Cu 11 <a href="{PDF}">pdf</a> '
                          f'<a href="https://x.it/allegato.pdf">allegato</a>'))
        self.assertEqual(len(parse_cu_feed(page)), 2)

    def test_lo_stesso_link_ripetuto_conta_una_volta(self):
        page = _page(_msg("2026-08-05T14:32:00+00:00",
                          f'Cu 11 <a href="{PDF}">testo</a> <a href="{PDF}">pdf</a>'))
        self.assertEqual(len(parse_cu_feed(page)), 1)

    def test_cu_senza_numero_dichiarato_resta_utilizzabile(self):
        """Il numero vero lo legge il parser dentro al PDF: qui può mancare."""
        page = _page(_msg("2026-08-05T14:32:00+00:00",
                          f'Pubblicato <a href="{PDF}">il comunicato</a>'))
        item = parse_cu_feed(page)[0]
        self.assertIsNone(item["cu_number"])
        self.assertEqual(item["url"], PDF)

    def test_pagina_vuota(self):
        self.assertEqual(parse_cu_feed(""), [])


class SeenIntegrationTestCase(unittest.TestCase):
    """Un CU già ingerito non si riscarica: è il risparmio di ARCH-002."""

    def test_il_secondo_giro_non_vede_nulla_di_nuovo(self):
        items = parse_cu_feed(_page(_msg("2026-08-05T14:32:00+00:00",
                                         f'Cu 11 <a href="{PDF}">pdf</a>')))
        with SeenStore(":memory:") as seen:
            self.assertTrue(seen.see(items[0]["url"], kind="cu_pdf"))
            self.assertFalse(seen.see(items[0]["url"], kind="cu_pdf"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
