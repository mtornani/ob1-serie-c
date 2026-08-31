#!/usr/bin/env python3
"""
Il redirect di grounding va risolto MENTRE è vivo (src/scraper_global.py).

Perché esiste questo file: misurato il 31 ago 2026 sul DB di produzione, 41
delle 54 schede pubbliche avevano come fonte un redirect
vertexaisearch/grounding-api-redirect. Provandone otto, otto rispondevano
404. Quelle schede hanno ancora il profilo Transfermarkt — identità, club,
contratto — ma non più l'articolo che diceva PERCHÉ quel giocatore fosse
un'occasione. Il redirect funziona solo nel momento in cui il grounding lo
restituisce, e nessuno lo seguiva lì.

Offline come tutto il resto della suite: la rete è finta.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_redirect_grounding -v
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scraper_global import GlobalScraper

REDIRECT = ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/"
            "AUZIYQHrLv5bj1wpkK5cAolSjgBvxX2id6riBmDeUG9F")
ARTICOLO = "https://www.tuttoc.com/serie-c/rossi-svincolato-dal-cesena-12345"


class _Risposta:
    def __init__(self, url):
        self.url = url


class TestRisolviRedirect(unittest.TestCase):
    def setUp(self):
        self.s = GlobalScraper.__new__(GlobalScraper)   # senza __init__/chiavi

    def test_redirect_risolto_diventa_articolo(self):
        with patch("src.scraper_global.requests.head",
                   return_value=_Risposta(ARTICOLO)) as head:
            self.assertEqual(self.s._risolvi_redirect(REDIRECT), ARTICOLO)
        self.assertTrue(head.called)

    def test_url_normale_non_viene_toccato(self):
        # nessuna richiesta di rete per un URL che è già un articolo
        with patch("src.scraper_global.requests.head") as head:
            self.assertEqual(self.s._risolvi_redirect(ARTICOLO), ARTICOLO)
        self.assertFalse(head.called)

    def test_rete_giu_tiene_il_redirect(self):
        # il caso peggiore deve essere il comportamento di oggi, non una perdita
        with patch("src.scraper_global.requests.head",
                   side_effect=OSError("boom")):
            self.assertEqual(self.s._risolvi_redirect(REDIRECT), REDIRECT)

    def test_redirect_che_rimanda_a_se_stesso_non_inganna(self):
        with patch("src.scraper_global.requests.head",
                   return_value=_Risposta(REDIRECT)):
            self.assertEqual(self.s._risolvi_redirect(REDIRECT), REDIRECT)

    def test_url_vuoto(self):
        with patch("src.scraper_global.requests.head") as head:
            self.assertEqual(self.s._risolvi_redirect(""), "")
        self.assertFalse(head.called)


if __name__ == "__main__":
    unittest.main()
