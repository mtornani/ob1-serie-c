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

from src.tm_url import (clean, diagnose, id_is_plausible, is_profile_url,
                        matches_player, profile_id, profile_slug)

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


class TestIdInventato(unittest.TestCase):
    """
    26 ago 2026, dal database reale. Lo slug e' giusto, l'ID no — e lo slug
    e' l'unica cosa che il controllo precedente guardava. Su Transfermarkt
    la pagina la decide il numero: slug corretto + ID inventato = si clicca
    e c'e' un'altra persona, con il badge 'verificato' sopra.
    """

    def test_rizzo_pinna_NON_lo_prende_nessun_controllo_di_forma(self):
        """
        Il limite, dichiarato invece che nascosto.

        538430 non e' tondo (538430 % 1000 = 430): e' un numero arbitrario
        come un ID vero, solo che appartiene a un'altra persona. Nessuna
        regola sulla FORMA del numero puo' distinguerlo da 411465, che e'
        l'ID vero di Rizzo Pinna.

        Quindi id_is_plausible() prende le invenzioni pigre (33 su 85 nel
        database reale: ID tondi) ma NON questa. L'unico modo di prendere
        questa e' RISOLVERE l'ID e guardare di chi e' — cioe' avere una
        prova di verifica registrata, non un controllo sintattico.
        Vedi `tm_verification` in scripts/generate_dashboard.py.
        """
        url = "https://www.transfermarkt.it/andrea-rizzo-pinna/profil/spieler/538430"
        self.assertTrue(is_profile_url(url))                 # forma giusta
        self.assertTrue(matches_player(url, "Rizzo Pinna"))  # slug giusto
        self.assertTrue(id_is_plausible(url))                # numero plausibile
        # ...e infatti passa. Non e' un bug del filtro: e' il filtro che non
        # puo' arrivarci. Serve la provenienza, non un'altra regex.
        self.assertEqual(clean(url, "Rizzo Pinna"), url)

    def test_id_tondi_dal_database_reale(self):
        """33 link su 85 in dashboard finivano per zeri."""
        for pid in (939000, 930000, 1000000, 600000, 119000, 49000, 1180000):
            with self.subTest(id=pid):
                url = f"https://www.transfermarkt.it/mario-rossi/profil/spieler/{pid}"
                self.assertFalse(id_is_plausible(url))
                self.assertIsNone(clean(url, "Mario Rossi"))
                self.assertIn("costruito", diagnose(url, "Mario Rossi"))

    def test_id_assurdamente_basso(self):
        url = "https://www.transfermarkt.it/giovanni-graziano/profil/spieler/95"
        self.assertIsNone(clean(url, "Giovanni Graziano"))
        self.assertIn("implausibile", diagnose(url, "Giovanni Graziano"))

    def test_id_reali_non_vengono_scartati(self):
        """Il lato opposto: gli ID veri devono passare."""
        for slug, pid, nome in (
            ("andrea-rizzo-pinna", 411465, "Rizzo Pinna"),   # quello vero
            ("cosimo-patierno", 283352, "Cosimo Patierno"),
            ("kevin-angulo", 659787, "Kevin Angulo"),
            ("yan-diomande", 1390649, "Yan Diomande"),
        ):
            with self.subTest(nome=nome):
                url = f"https://www.transfermarkt.it/{slug}/profil/spieler/{pid}"
                self.assertEqual(clean(url, nome), url, diagnose(url, nome))


class TestVariantiLegittimeNonVannoPerse(unittest.TestCase):
    """Il rischio opposto: un filtro severo butta link buoni."""

    CASI = [
        (VALIDO, "Cosimo Patierno"),
        ("https://www.transfermarkt.it/andrea-rizzo-pinna/profil/spieler/456789",
         "Rizzo Pinna"),                                    # nome parziale nel DB
        ("https://www.transfermarkt.it/jhonatan-chioetto/profil/spieler/123456",
         "CHIOETTO JHONATAN DAVID"),                        # maiuscolo, ordine invertito
        # ID finti ma PLAUSIBILI (non tondi, >= 1000). Questi casi verificano
        # il match sul NOME: con un ID sintetico sotto 1000 fallirebbero per
        # il motivo sbagliato dopo l'aggiunta di id_is_plausible().
        ("https://www.transfermarkt.com/aimen-aroussi/profil/spieler/99917",
         "Arroussi Aimen"),                                 # traslitterazione diversa
        ("https://www.transfermarkt.it/antonino-la-gumina/profil/spieler/22243",
         "La Gumina"),                                      # cognome con particella
        ("https://www.transfermarkt.it/nicolo-rovella/profil/spieler/33361",
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
