#!/usr/bin/env python3
"""
ARCH-003 — Test della fonte "sito del comitato" (src/cu_site.py).

Zero rete: le pagine sono fixture ricavate dall'HTML reale di figccrer.it del
5/9/2026. Il caso che conta di piu' e' l'interstiziale anti-bot: risponde 200
ma non e' l'elenco, e trattarlo come elenco vuoto ripeterebbe l'errore
@lndlombardia gia' costato una volta a questo repo.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_cu_site -v
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cu_site import (DEFAULT_SITE, ListingUnavailable, is_interstitial,
                         new_cu_links, parse_site_listing)
from src.watch.seen import SeenStore

# Forma reale: ogni allegato e' un <a> nella card dell'annuncio; il comunicato
# si distingue dagli allegati solo per il nome del file.
ELENCO = '''
<div class="card">
  <p class="mb-1"><a class='btn btn-sm btn-figc'
     href="/files/announcements/2026/7518/eccellenza_girone_b.pdf" target="_blank"></a>
     <span class="modal-attachment-text pe-1">eccellenza_girone_b.pdf</span></p>
  <p class="mb-1"><a class='btn btn-sm btn-figc'
     href="/files/announcements/2026/7518/cu14.pdf" target="_blank"></a>
     <span class="modal-attachment-text pe-1">cu14.pdf</span></p>
</div>
<div class="card">
  <p class="mb-1"><a class='btn btn-sm btn-figc'
     href="/files/announcements/2026/7599/Modulo Iscrizione-Grassroots.pdf"></a></p>
  <p class="mb-1"><a class='btn btn-sm btn-figc'
     href="/files/announcements/2026/7599/cu25.pdf"></a></p>
  <p class="mb-1"><a class='btn btn-sm btn-figc'
     href="/files/announcements/2026/7599/cu25.pdf"></a></p>
</div>
'''

INTERSTIZIALE = '''<!DOCTYPE html><html><head>
<script>(function(){ setTimeout(function(){ window.location.reload(); }, 5000); }())</script>
<title>One moment, please...</title></head><body><div class="spinner"></div></body></html>'''


class ParseTestCase(unittest.TestCase):

    def test_prende_i_comunicati_e_scarta_gli_allegati(self):
        items = parse_site_listing(ELENCO)
        self.assertEqual([it["cu_number"] for it in items], [14, 25])
        for it in items:
            self.assertTrue(it["url"].endswith(f"cu{it['cu_number']}.pdf"))

    def test_ordine_di_pubblicazione_non_numero_di_cu(self):
        # L'id dell'annuncio e' progressivo; il numero del CU riparte da 1 a
        # ogni stagione, quindi non puo' fare da ordinamento.
        items = parse_site_listing(ELENCO)
        self.assertEqual([it["announcement_id"] for it in items], [7518, 7599])

    def test_lo_stesso_pdf_due_volte_e_una_voce_sola(self):
        self.assertEqual(len(parse_site_listing(ELENCO)), 2)

    def test_url_assoluto_sulla_base_passata(self):
        it = parse_site_listing(ELENCO, base_url="https://x.test/")[0]
        self.assertEqual(it["url"], "https://x.test/files/announcements/2026/7518/cu14.pdf")

    def test_niente_data_inventata(self):
        # L'elenco non porta una data affidabile: il campo resta vuoto e la
        # data vera la dichiara il PDF (parse_cu_text la legge dall'header).
        self.assertIsNone(parse_site_listing(ELENCO)[0]["posted_at"])

    def test_pagina_vuota(self):
        self.assertEqual(parse_site_listing(""), [])

    def test_accetta_anche_il_percorso_files_comunicati(self):
        html = '<a href="/files/comunicati/2026/7504/cu11.pdf"></a>'
        self.assertEqual(parse_site_listing(html)[0]["cu_number"], 11)


class InterstizialeTestCase(unittest.TestCase):
    """'Risponde 200' non significa 'ha contenuto' — lezione @lndlombardia."""

    def test_riconosce_il_muro_anti_bot(self):
        self.assertTrue(is_interstitial(INTERSTIZIALE))
        self.assertFalse(is_interstitial(ELENCO))

    def test_l_interstiziale_non_e_un_elenco_vuoto(self):
        # parse_site_listing su quell'HTML darebbe [] — cioe' "tutto a posto,
        # niente di nuovo". Il fetch deve sollevare prima che accada.
        self.assertEqual(parse_site_listing(INTERSTIZIALE), [])
        with mock.patch("src.cu_site.fetch_listing",
                        side_effect=ListingUnavailable("interstiziale")):
            with self.assertRaises(ListingUnavailable):
                new_cu_links("https://x.test")


class SeenTestCase(unittest.TestCase):

    def test_il_filtro_non_marca_niente(self):
        """
        Il CU filtrato ma non ancora scaricato deve restare nuovo: se il PDF
        fallisce (WAF, rete), il giro dopo lo si ritenta. Marcare qui aprirebbe
        un buco permanente nella serie storica.
        """
        with mock.patch("src.cu_site.fetch_listing", return_value=ELENCO):
            with SeenStore(":memory:") as seen:
                primo = new_cu_links("https://x.test", seen=seen)
                self.assertEqual(len(primo), 2)
                # nessuno scaricamento riuscito in mezzo: sono ancora nuovi
                self.assertEqual(len(new_cu_links("https://x.test", seen=seen)), 2)
                # ora il chiamante marca, come fa brief_giovedi dopo l'ingest
                seen.see(primo[0]["url"], kind="cu_pdf")
                resta = new_cu_links("https://x.test", seen=seen)
                self.assertEqual([it["cu_number"] for it in resta], [25])


if __name__ == "__main__":
    unittest.main(verbosity=2)
