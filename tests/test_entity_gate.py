#!/usr/bin/env python3
"""
Test del gate entità. È il filtro più economico della pipeline: se sbaglia in
un verso si paga per sempre su spazzatura, se sbaglia nell'altro si perdono
giocatori veri. I casi qui sotto vengono dal database reale.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_entity_gate -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.entity_gate import (JUNK, OUT_OF_SCOPE, PLAYER, classify,
                             classify_name, find_particle_duplicates,
                             is_player_name)


class TestJunkRejected(unittest.TestCase):
    """Casi osservati in data/opportunities.json che il gate vecchio lasciava passare."""

    CASI = [
        "Comunicato Ufficiale",
        "La Serie",
        "Toro News",
        "Summer Transfer Big Board",
        "Ultime Notizie",
        "Classifica Marcatori",
        "Calciomercato Live",
        "Rassegna Stampa",
    ]

    def test_editorial_titles_are_junk(self):
        for nome in self.CASI:
            with self.subTest(nome=nome):
                v = classify_name(nome)
                self.assertEqual(v.kind, JUNK, f"{nome} doveva essere junk")
                self.assertTrue(v.reason)

    def test_structural_rejects(self):
        for nome, atteso in [
            ("", "troppo corto"),
            ("Rossi", "nome singolo"),
            ("Player 2026", "cifre"),
            ("Titolo | Sito", "separatori"),
            ("Un lunghissimo titolo di articolo che non finisce mai davvero", "lungo"),
            (None, "stringa"),
            (12345, "stringa"),
        ]:
            with self.subTest(nome=nome):
                self.assertEqual(classify_name(nome).kind, JUNK)

    def test_phrase_of_five_tokens_is_not_a_name(self):
        self.assertEqual(classify_name("Ecco i migliori giovani italiani").kind, JUNK)


class TestRealNamesSurvive(unittest.TestCase):
    """
    Il rischio opposto: un filtro troppo avido cancella giocatori veri.
    I cognomi italiani con particella sono la trappola classica.
    """

    CASI = [
        "Cosimo Patierno",
        "Antonino La Gumina",
        "Jacopo Da Riva",
        "Matteo Della Morte",
        "Daniele De Rossi",
        "Marco Del Prato",
        "Virgil Van Dijk",
        "Eloge Koffi Yao Guy",          # 4 token, nome africano
        "Rioko Imar Simpson Bitata",    # 4 token
        "CHIOETTO JHONATAN DAVID",      # maiuscolo: è un nome, non un titolo
        "Sergej Levak",
    ]

    def test_real_players_pass(self):
        for nome in self.CASI:
            with self.subTest(nome=nome):
                v = classify_name(nome)
                self.assertEqual(v.kind, PLAYER, f"{nome} respinto: {v.reason}")

    def test_compat_helper(self):
        self.assertTrue(is_player_name("Cosimo Patierno"))
        self.assertFalse(is_player_name("Comunicato Ufficiale"))


class TestScope(unittest.TestCase):
    def test_high_value_player_is_out_of_scope_not_junk(self):
        v = classify({"player_name": "Dusan Vlahovic", "market_value": 35_000_000})
        self.assertEqual(v.kind, OUT_OF_SCOPE)
        self.assertFalse(v.spend_allowed)  # non ci si spende
        self.assertFalse(v.is_junk)        # ma non è spazzatura: non si butta

    def test_serie_c_value_passes(self):
        v = classify({"player_name": "Cosimo Patierno", "market_value": 150_000})
        self.assertEqual(v.kind, PLAYER)
        self.assertTrue(v.spend_allowed)
        self.assertTrue(bool(v))

    def test_value_read_from_nested_profile(self):
        v = classify({"player_name": "Tizio Caio",
                      "player_profile": {"market_value_eur": 22_000_000}})
        self.assertEqual(v.kind, OUT_OF_SCOPE)

    def test_cap_is_configurable(self):
        opp = {"player_name": "Tizio Caio", "market_value": 8_000_000}
        self.assertEqual(classify(opp, max_market_value=10_000_000).kind, PLAYER)
        self.assertEqual(classify(opp, max_market_value=1_000_000).kind, OUT_OF_SCOPE)

    def test_unparsable_value_does_not_reject(self):
        v = classify({"player_name": "Tizio Caio", "market_value": "n/d"})
        self.assertEqual(v.kind, PLAYER)

    def test_junk_name_wins_over_value_check(self):
        v = classify({"player_name": "Comunicato Ufficiale", "market_value": 50_000_000})
        self.assertEqual(v.kind, JUNK)


class TestRassegneDiMercato(unittest.TestCase):
    """
    Casi veri, trovati il 31 ago 2026 guardando chi c'era in dashboard:
    Acerbi (38) e Donnarumma pubblicati come opportunità di Serie C, e
    Jonathan David con loro. Venivano tutti e tre da calciomercato.com/liste/,
    le rassegne sui grandi nomi in scadenza. Il cap sul valore non li ferma:
    Acerbi vale 2 mln € su Transfermarkt proprio perché ha 38 anni, e per
    Donnarumma il valore non c'era affatto.
    """

    LISTA = ("https://www.calciomercato.com/liste/da-acerbi-a-vlahovic-"
             "tutti-i-giocatori-in-scadenza-di-contratto-il-30-giugno-2026/x")

    def test_rassegna_e_fuori_scopo(self):
        v = classify({"player_name": "Francesco Acerbi", "market_value": 2_000_000,
                      "source_url": self.LISTA})
        self.assertEqual(v.kind, OUT_OF_SCOPE)
        self.assertFalse(v.spend_allowed)
        self.assertFalse(v.is_junk)   # è un giocatore vero, non spazzatura
        self.assertIn("rassegna", v.reason)

    def test_rassegna_senza_valore_di_mercato(self):
        # Donnarumma: market_value assente, il cap non ha nulla da leggere
        v = classify({"player_name": "Gianluigi Donnarumma", "market_value": None,
                      "source_url": self.LISTA})
        self.assertEqual(v.kind, OUT_OF_SCOPE)

    def test_www_e_maiuscole_non_aggirano_il_controllo(self):
        v = classify({"player_name": "Luka Modric",
                      "source_url": "HTTPS://CalcioMercato.com/LISTE/top-10-svincolati/"})
        self.assertEqual(v.kind, OUT_OF_SCOPE)

    def test_articolo_normale_dello_stesso_sito_passa(self):
        # Non è il dominio a essere bandito: è lo spazio delle rassegne.
        v = classify({"player_name": "Cosimo Patierno", "market_value": 150_000,
                      "source_url": "https://www.calciomercato.com/serie-c/patierno-avellino/"})
        self.assertEqual(v.kind, PLAYER)

    def test_articolo_di_lega_pro_che_cita_la_serie_a_passa(self):
        # tuttoc.com, "mezza serie A su un diamante della Lega Pro": parla di
        # un giocatore NOSTRO che piace sopra. Vero positivo, non si tocca.
        v = classify({"player_name": "Chec Benelli Doumbia",
                      "source_url": "https://www.tuttoc.com/il-punto/mezza-serie-a-su-"
                                    "un-diamante-della-lega-pro-operazione-nostalgia/427"})
        self.assertEqual(v.kind, PLAYER)

    def test_senza_source_url_non_esplode(self):
        v = classify({"player_name": "Tizio Caio", "market_value": 150_000})
        self.assertEqual(v.kind, PLAYER)


class TestParticleDuplicates(unittest.TestCase):
    def test_preposition_artifact_is_linked_to_the_canonical_name(self):
        dupes = find_particle_duplicates(
            ["Bernardo Silva", "Da Bernardo Silva", "Cosimo Patierno"])
        self.assertEqual(dupes, {"Da Bernardo Silva": "Bernardo Silva"})

    def test_real_particle_surname_is_not_a_duplicate(self):
        """'Da Riva' esiste come cognome: senza il canonico non è un artefatto."""
        self.assertEqual(find_particle_duplicates(["Jacopo Da Riva", "Marco Rossi"]), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
