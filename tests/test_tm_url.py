#!/usr/bin/env python3
"""
Test della validazione URL Transfermarkt.

I casi vengono dal database reale: 201 link su 728 erano da buttare. Il rischio
qui è simmetrico — troppo permissivi si manda un osservatore sul giocatore
sbagliato, troppo severi si buttano link buoni. Entrambi i lati sono coperti.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_tm_url -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tm_url import (clean, diagnose, is_profile_url, matches_player,
                        profile_id, profile_slug)

VALIDO = "https://www.transfermarkt.it/cosimo-patierno/profil/spieler/283352"


class TestFormatoValido(unittest.TestCase):
    def test_profilo_completo(self):
        self.assertTrue(is_profile_url(VALIDO))
        self.assertEqual(profile_id(VALIDO), "283352")
        self.assertEqual(profile_slug(VALIDO), "cosimo-patierno")

    def test_domini_nazionali(self):
        for host in ("transfermarkt.it", "transfermarkt.com", "transfermarkt.de",
                     "transfermarkt.co.uk"):
            with self.subTest(host=host):
                self.assertTrue(is_profile_url(
                    f"https://www.{host}/tizio-caio/profil/spieler/1"))

    def test_senza_www_e_in_http(self):
        self.assertTrue(is_profile_url("http://transfermarkt.it/x-y/profil/spieler/9"))


class TestScartiOsservatiInProduzione(unittest.TestCase):
    """Le quattro forme rotte trovate in data/opportunities.json."""

    def test_profilo_senza_id_e_costruito_non_osservato(self):
        url = "https://www.transfermarkt.it/giulio-carotenuto/profil/spieler/"
        self.assertFalse(is_profile_url(url))
        self.assertIn("senza ID", diagnose(url))

    def test_redirect_di_grounding(self):
        url = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQ"
        self.assertFalse(is_profile_url(url))
        self.assertIn("grounding", diagnose(url))

    def test_pagina_squadra(self):
        url = "https://www.transfermarkt.it/as-orceana-calcio/startseite/verein/36087"
        self.assertFalse(is_profile_url(url))
        self.assertIn("squadra", diagnose(url))

    def test_altra_pagina_del_giocatore(self):
        url = "https://www.transfermarkt.it/giuliano-fiorini/gemeinsameSpiele/spieler/33597"
        self.assertFalse(is_profile_url(url))

    def test_non_url(self):
        for cattivo in ("", None, 123, "non un url", "https://esempio.it/x"):
            with self.subTest(v=cattivo):
                self.assertFalse(is_profile_url(cattivo))
                self.assertIsNone(clean(cattivo))


class TestPersonaSbagliata(unittest.TestCase):
    def test_slug_di_un_altro_giocatore(self):
        """Il caso che l'utente ha visto: si clicca e c'è un'altra persona."""
        url = "https://www.transfermarkt.it/stefano-del-sante/profil/spieler/29608"
        self.assertTrue(is_profile_url(url))          # formato corretto
        self.assertFalse(matches_player(url, "Berardini Alessandro"))
        self.assertIsNone(clean(url, "Berardini Alessandro"))
        self.assertIn("altro giocatore", diagnose(url, "Berardini Alessandro"))

    def test_url_valido_senza_nome_passa(self):
        """Senza nome non si può giudicare la persona: decide chi chiama."""
        self.assertEqual(clean(VALIDO), VALIDO)


class TestVariantiLegittimeNonVannoPerse(unittest.TestCase):
    """Il rischio opposto: un filtro severo butta link buoni."""

    CASI = [
        (VALIDO, "Cosimo Patierno"),
        ("https://www.transfermarkt.it/andrea-rizzo-pinna/profil/spieler/456789",
         "Rizzo Pinna"),                                    # nome parziale nel DB
        ("https://www.transfermarkt.it/jhonatan-chioetto/profil/spieler/123456",
         "CHIOETTO JHONATAN DAVID"),                        # maiuscolo, ordine invertito
        ("https://www.transfermarkt.com/aimen-aroussi/profil/spieler/999",
         "Arroussi Aimen"),                                 # traslitterazione diversa
        ("https://www.transfermarkt.it/antonino-la-gumina/profil/spieler/222",
         "La Gumina"),                                      # cognome con particella
        ("https://www.transfermarkt.it/nicolo-rovella/profil/spieler/333",
         "Nicolò Rovella"),                                 # accento nel nome
    ]

    def test_passano(self):
        for url, nome in self.CASI:
            with self.subTest(nome=nome):
                self.assertEqual(clean(url, nome), url,
                                 f"{nome} scartato: {diagnose(url, nome)}")


class TestDatabaseReale(unittest.TestCase):
    def test_nessun_link_rotto_resta_nel_db(self):
        """
        Guardia di regressione: dopo la bonifica il database non deve più
        contenere link non validi. Se questo test si rompe, qualcosa è tornato
        a scriverli senza passare da clean().
        """
        db = Path(__file__).resolve().parent.parent / "data" / "opportunities.json"
        if not db.exists():
            self.skipTest("database assente")
        import json
        rotti = []
        for opp in json.loads(db.read_text(encoding="utf-8")):
            nome = opp.get("player_name") or ""
            for container in (opp, opp.get("player_profile") or {}):
                for field in ("tm_url", "transfermarkt_url"):
                    url = container.get(field)
                    if url and not clean(url, nome):
                        rotti.append(f"{nome}: {diagnose(url, nome)}")
        self.assertEqual(rotti, [], f"{len(rotti)} link rotti nel database")


if __name__ == "__main__":
    unittest.main(verbosity=2)
