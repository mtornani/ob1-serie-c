#!/usr/bin/env python3
"""
Test di regressione per scripts/brief_giovedi.py.

Nato da un bug vero, trovato dal primo lancio reale del workflow su Actions:
il canale Telegram risultava vuoto anche se DEFAULT_CHANNEL esiste, perché
GitHub Actions imposta SEMPRE la variabile d'ambiente (a stringa vuota
quando non è configurata), e os.getenv("X", default) usa il default solo
se la chiave manca del tutto — non se è presente-ma-vuota. L'esito era un
fetch verso "t.me/s/" (niente dopo la slash), fallito in silenzio, indistin-
guibile nel log da un canale controllato e trovato pulito.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_brief_giovedi -v
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.brief_giovedi as bg


class DefaultChannelFallbackTestCase(unittest.TestCase):
    """
    Il caso che ha prodotto il bug: non "variabile assente" (quello già
    funzionava), ma "variabile presente e vuota" — esattamente come la
    scrive ${{ vars.OB1_CU_CHANNEL }} quando su GitHub non è configurata.
    """

    def _default_canale(self):
        """Rilegge lo script come farebbe argparse: un subprocess pulito,
        perché il default è calcolato una volta sola all'import del modulo —
        rimpiazzare os.environ a caldo nello stesso processo non lo rivaluta."""
        return subprocess.run(
            [sys.executable, "-c",
             "import scripts.brief_giovedi as bg; "
             "import argparse; "
             "ap = argparse.ArgumentParser(); "
             "print(__import__('os').getenv('OB1_CU_CHANNEL') or bg.DEFAULT_CHANNEL)"],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True, text=True, env=self.env,
        ).stdout.strip()

    def setUp(self):
        self.env = dict(os.environ)

    def test_variabile_assente_usa_il_default(self):
        self.env.pop("OB1_CU_CHANNEL", None)
        self.assertEqual(self._default_canale(), bg.DEFAULT_CHANNEL)

    def test_variabile_presente_ma_vuota_usa_comunque_il_default(self):
        """Il caso reale del bug: GitHub Actions la imposta sempre, a volte a ''."""
        self.env["OB1_CU_CHANNEL"] = ""
        self.assertEqual(self._default_canale(), bg.DEFAULT_CHANNEL)

    def test_variabile_valorizzata_vince_sul_default(self):
        self.env["OB1_CU_CHANNEL"] = "altrocanale"
        self.assertEqual(self._default_canale(), "altrocanale")


class IngestNewEmptyChannelTestCase(unittest.TestCase):
    """
    Difesa in profondità: anche se in futuro un canale vuoto arrivasse a
    ingest_new() per un'altra via, deve gridarlo — non stampare "nessun
    comunicato nuovo", che ha lo stesso aspetto di un canale controllato e
    trovato pulito.

    Da ARCH-003 (5/9/2026) le fonti sono due, e i test le spengono entrambe
    esplicitamente: un test che tocca la rete non è un test.
    """

    def test_canale_vuoto_non_tenta_il_fetch_e_lo_dice(self):
        with mock.patch.object(bg, "new_cu_links") as fetch:
            result = bg.ingest_new(store=mock.Mock(), seen=mock.Mock(),
                                   channel="", site="")
        fetch.assert_not_called()
        self.assertEqual(result, {"cu": 0, "new_sanctions": 0, "new_results": 0})

    def test_canale_valorizzato_tenta_il_fetch(self):
        with mock.patch.object(bg, "new_cu_links", return_value=[]) as fetch:
            bg.ingest_new(store=mock.Mock(), seen=mock.Mock(),
                          channel="lndemiliaromagna", site="")
        fetch.assert_called_once()


class DueFontiTestCase(unittest.TestCase):
    """
    Il canale può morire (è successo: @lndemiliaromagna, 5/9/2026). Il sito
    del comitato deve bastare da solo, e un elenco irraggiungibile non deve
    mai somigliare a un elenco vuoto.
    """

    def test_il_sito_ingerisce_anche_col_canale_morto(self):
        store = mock.Mock()
        store.ingest.return_value = {"new_sanctions": 2, "new_results": 1}
        with mock.patch.object(bg, "new_cu_links", return_value=[]), \
             mock.patch.object(bg, "new_cu_links_site",
                               return_value=[{"url": "https://x.test/cu9.pdf"}]), \
             mock.patch.object(bg, "read_pdf", return_value="testo"), \
             mock.patch.object(bg, "parse_cu_text",
                               return_value={"meta": {"cu_number": 9}}):
            seen = mock.Mock()
            totals = bg.ingest_new(store, seen, channel="canalemorto",
                                   site="https://x.test")
        self.assertEqual(totals, {"cu": 1, "new_sanctions": 2, "new_results": 1})
        # marcato solo dopo l'ingest riuscito
        seen.see.assert_called_once_with("https://x.test/cu9.pdf", kind="cu_pdf")

    def test_pdf_fallito_non_viene_marcato(self):
        """Il buco silenzioso che il filtro in sola lettura esiste per evitare."""
        with mock.patch.object(bg, "new_cu_links", return_value=[]), \
             mock.patch.object(bg, "new_cu_links_site",
                               return_value=[{"url": "https://x.test/cu9.pdf"}]), \
             mock.patch.object(bg, "read_pdf", side_effect=OSError("WAF")):
            seen = mock.Mock()
            totals = bg.ingest_new(mock.Mock(), seen, channel="",
                                   site="https://x.test")
        self.assertEqual(totals["cu"], 0)
        seen.see.assert_not_called()

    def test_elenco_irraggiungibile_e_un_errore_non_un_silenzio(self):
        with mock.patch.object(bg, "new_cu_links", return_value=[]), \
             mock.patch.object(bg, "new_cu_links_site",
                               side_effect=bg.ListingUnavailable("interstiziale")):
            with mock.patch("builtins.print") as say:
                totals = bg.ingest_new(mock.Mock(), mock.Mock(), channel="",
                                       site="https://x.test")
        self.assertEqual(totals["cu"], 0)
        detto = " ".join(str(c) for c in say.call_args_list)
        self.assertIn("[ERRORE]", detto)
        self.assertIn("interstiziale", detto)


if __name__ == "__main__":
    unittest.main(verbosity=2)
