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


class TestVerificaAllaFonte(unittest.TestCase):
    """
    26 ago 2026: 138 link su 174 nel database portavano a un'altra persona,
    e avevano tutti superato il controllo sintattico. Bonificarli non basta —
    la pipeline ne riscriverebbe di nuovi al primo run. Il cancello deve
    stare al momento della CREAZIONE del link, in enricher_tm.

    Qui si verifica che ogni strada che produce un tm_url passi da
    _url_verificato(), non solo da clean(). Senza rete: il verificatore e'
    sostituito da un finto.
    """

    def _enricher(self, esiti):
        """Enricher con la verifica finta: esiti = {url: combacia?}."""
        import os
        from unittest import mock
        os.environ["OB1_SPORTS_SKILLS"] = "0"
        self.addCleanup(os.environ.pop, "OB1_SPORTS_SKILLS", None)
        from src import enricher_tm
        from src.tm_verify import Verifica

        class _Finto:
            def verifica(self, nome, url):
                if url not in esiti:
                    return None                      # non verificabile
                combacia = esiti[url]
                return Verifica(combacia=combacia, nome_cercato=nome,
                                nome_sul_profilo=nome if combacia else "Altra Persona",
                                motivo="ok" if combacia else "e' un altro",
                                verificato_il="2026-08-26T12:00:00+00:00")

        e = enricher_tm.TransfermarktEnricher.__new__(
            enricher_tm.TransfermarktEnricher)
        e._verificatore = _Finto()
        e._verifica_attiva = True
        return e

    def test_url_di_unaltra_persona_non_diventa_mai_un_link(self):
        url = "https://www.transfermarkt.it/andrea-rizzo-pinna/profil/spieler/538430"
        e = self._enricher({url: False})
        self.assertEqual(e._url_verificato("Rizzo Pinna", url), (None, ""))

    def test_url_confermato_passa_e_porta_il_timestamp(self):
        url = "https://www.transfermarkt.it/andrea-rizzo-pinna/profil/spieler/411465"
        e = self._enricher({url: True})
        ok, quando = e._url_verificato("Rizzo Pinna", url)
        self.assertEqual(ok, url)
        self.assertTrue(quando, "un link verificato deve portare quando lo e' stato")

    def test_non_verificabile_non_e_un_permesso(self):
        """Rete giu' non significa 'va bene': significa che non lo sappiamo."""
        url = "https://www.transfermarkt.it/tizio-caio/profil/spieler/123456"
        e = self._enricher({})        # nessun esito -> None
        self.assertEqual(e._url_verificato("Tizio Caio", url), (None, ""))

    def test_la_sintassi_resta_il_primo_filtro_e_non_costa_rete(self):
        """Un ID tondo non deve nemmeno arrivare alla verifica."""
        chiamate = []

        class _Spia:
            def verifica(self, nome, url):
                chiamate.append(url); return None

        e = self._enricher({})
        e._verificatore = _Spia()
        tondo = "https://www.transfermarkt.it/mario-rossi/profil/spieler/939000"
        self.assertEqual(e._url_verificato("Mario Rossi", tondo), (None, ""))
        self.assertEqual(chiamate, [], "l'ID tondo va scartato senza aprire nulla")


class TestRicercaInternaTMViaJina(unittest.TestCase):
    """
    Il motore di ricerca generico e' l'anello che si blocca: da CI e da questo
    ambiente DDG risponde "HTTP 202, pagina anti-bot", e senza candidati i
    link finivano per essere COSTRUITI da un modello invece che trovati.
    L'indice di Transfermarkt, letto via Jina, risponde e risponde meglio.
    """

    def _enricher(self, pagina):
        from unittest import mock
        from src import enricher_tm, tm_verify
        e = enricher_tm.TransfermarktEnricher.__new__(
            enricher_tm.TransfermarktEnricher)
        e._verifica_attiva = True
        # Si intercetta la rete al punto piu' basso (`_scarica`) e non la
        # funzione di ricerca: cosi' il test continua a far passare davvero la
        # pagina attraverso l'estrazione dei candidati, che e' la cosa che
        # deve restare corretta.
        p = mock.patch.object(tm_verify, "_scarica", return_value=pagina)
        p.start(); self.addCleanup(p.stop)
        return e

    def test_estrae_i_candidati_dalla_pagina_di_ricerca(self):
        # Forma reale: un solo risultato esatto (misurato su Alessio Cragno).
        pagina = ("Markdown Content: [Alessio Cragno]"
                  "(https://www.transfermarkt.it/alessio-cragno/profil/spieler/12907)")
        e = self._enricher(pagina)
        self.assertEqual(
            e._candidati_da_tm_via_jina("Alessio Cragno"),
            ["https://www.transfermarkt.it/alessio-cragno/profil/spieler/12907"])

    def test_piu_omonimi_restano_tutti_candidati(self):
        """Non si sceglie col nome: si aprono e decide la verifica."""
        pagina = ("[Marco Rossi](https://www.transfermarkt.it/marco-rossi/profil/spieler/111)"
                  "[Marco Rossi](https://www.transfermarkt.it/marco-rossi-ii/profil/spieler/222)")
        e = self._enricher(pagina)
        self.assertEqual(len(e._candidati_da_tm_via_jina("Marco Rossi")), 2)

    def test_lo_stesso_profilo_ripetuto_conta_una_volta(self):
        pagina = "".join(
            "[X](https://www.transfermarkt.it/x/profil/spieler/999)" for _ in range(4))
        e = self._enricher(pagina)
        self.assertEqual(len(e._candidati_da_tm_via_jina("X")), 1)

    def test_nessuna_risposta_non_produce_candidati_inventati(self):
        e = self._enricher("")
        self.assertEqual(e._candidati_da_tm_via_jina("Tizio Caio"), [])


class TestAdottareUnProfiloChiedePiuProvaDiToglierlo(unittest.TestCase):
    """
    Le due domande non hanno la stessa risposta, e confonderle rimette in
    circolo lo stesso difetto dei 138 link a un'altra persona.

        togliere un link che ho gia'  -> basta il dubbio (nomi_combaciano)
        adottare un profilo trovato
        da un motore per somiglianza  -> serve la prova (nomi_combaciano_forte)
    """

    def test_un_cognome_uguale_non_e_una_persona(self):
        from src.tm_verify import nomi_combaciano, nomi_combaciano_forte
        # La regola debole dice si', ed e' giusto cosi' per NON togliere un
        # link buono. Ma come regola di adozione produrrebbe la scheda di un
        # altro essere umano.
        self.assertTrue(nomi_combaciano("Luca Rossi", "Marco Rossi"))
        self.assertFalse(nomi_combaciano_forte("Luca Rossi", "Marco Rossi"))

    def test_solo_cognome_nel_database_non_aggancia_nessuno(self):
        # Caso reale, primo giro di scripts/apri_profili_tm.py del 26 ago
        # 2026: il record "De Pieri" veniva agganciato a un Cristian De Pieri
        # brasiliano di 29 anni.
        from src.tm_verify import nomi_combaciano_forte
        self.assertFalse(nomi_combaciano_forte("De Pieri", "Cristian De Pieri"))

    def test_le_varianti_vere_del_database_passano_lo_stesso(self):
        from src.tm_verify import nomi_combaciano_forte
        for cercato, sul_profilo in [
            ("Rizzo Pinna", "Andrea Rizzo Pinna"),
            ("CHIOETTO JHONATAN DAVID", "Jhonatan Chioetto"),
            ("Nico Paz", "Nico Paz"),            # cognome corto, 3 caratteri
            ("Riccardo Sganzerla", "Riccardo Sganzerla"),
        ]:
            self.assertTrue(nomi_combaciano_forte(cercato, sul_profilo),
                            f"{cercato} / {sul_profilo}")


class TestEUnOpportunitaDiSerieC(unittest.TestCase):
    """
    Il gate "fuori fascia Serie C" (src/entity_gate.py, cap 5 mln €) esisteva
    da sempre ed era giusto. Non scattava mai per due motivi sommati:

      1. il valore glielo passava un LLM, quindi era quasi sempre None
      2. la dashboard non chiamava classify(): leggeva un flag `out_of_scope`
         che nessun codice scriveva piu'

    In produzione il 26 ago 2026 questo metteva in dashboard, come opportunita'
    di Lega Pro, Nico Paz (Como, 80 mln), John Stones (Inter) e Simone Giordano
    (Eyupspor); piu' Alessio Rosa (41 anni) e Diego Carburi (40), che hanno
    smesso di giocare.

    Ora il valore lo legge la pagina e la domanda si fa in export.
    """

    def test_legge_il_valore_dalla_pagina(self):
        from src.tm_verify import analizza
        pagina = ("Title: Nico Paz - Profilo giocatore | Transfermarkt\n"
                  "Nome in patria: Nicolas Paz\n"
                  "Squadra attuale: [Como 1907]\n"
                  "Valore di mercato Valore attuale: [80,00 mln €](https://x)")
        v = analizza(pagina, "Nico Paz", "948294")
        self.assertEqual(v.valore_eur, 80_000_000)

    def test_ottanta_milioni_non_e_un_affare_di_lega_pro(self):
        from src.entity_gate import classify, OUT_OF_SCOPE
        fuori = classify({"player_name": "Nico Paz", "market_value": 80_000_000})
        self.assertEqual(fuori.kind, OUT_OF_SCOPE)

    def test_chi_sta_nella_fascia_resta(self):
        # Sergej Levak, 2,80 mln letti sul profilo: e' il nostro primo HOT e
        # deve restarci. Il cap toglie i fuori scala, non i giocatori buoni.
        from src.entity_gate import classify, OUT_OF_SCOPE
        dentro = classify({"player_name": "Sergej Levak", "market_value": 2_800_000})
        self.assertNotEqual(dentro.kind, OUT_OF_SCOPE)

    def test_valore_ignoto_non_scarta_nessuno(self):
        # Cosimo Patierno: il profilo non porta un valore. Non lo si butta su
        # un numero che nessuno ha letto — e' la stessa regola di provenienza.
        from src.entity_gate import classify, OUT_OF_SCOPE
        v = classify({"player_name": "Cosimo Patierno", "market_value": None})
        self.assertNotEqual(v.kind, OUT_OF_SCOPE)

    def test_chi_ha_smesso_non_e_unopportunita(self):
        from src.tm_verify import analizza
        pagina = ("Title: Alessio Rosa - Profilo giocatore | Transfermarkt\n"
                  "Squadra attuale: [![Image 28: Ritiro](x)](y) Ritiro\n"
                  "Ultima squadra: [Vis Pesaro]")
        v = analizza(pagina, "Alessio Rosa", "511164")
        self.assertTrue(v.ritirato)

    def test_chi_gioca_non_risulta_ritirato(self):
        from src.tm_verify import analizza
        pagina = ("Title: Cosimo Patierno - Profilo giocatore | Transfermarkt\n"
                  "Squadra attuale: [Casarano Calcio]")
        self.assertFalse(analizza(pagina, "Cosimo Patierno", "283352").ritirato)

    def test_una_voce_di_cache_senza_valore_va_riaperta(self):
        # Le verifiche scritte prima di questa modifica non hanno valore_eur.
        # La data direbbe "fresca" e terrebbe spento il gate per 30 giorni
        # proprio sui profili che abbiamo gia' in mano.
        from datetime import datetime, timezone
        from src.tm_verify import VerificatoreTM
        v = VerificatoreTM.__new__(VerificatoreTM)
        adesso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # Una voce completa: nome letto dal profilo E valore (che puo' essere
        # None — il profilo semplicemente non lo porta, vedi Patierno).
        piena = {"verificato_il": adesso, "valore_eur": None,
                 "nome_sul_profilo": "Cosimo Patierno"}
        self.assertTrue(v._fresca(piena))
        # Senza valore_eur: scritta prima che leggessimo il valore.
        self.assertFalse(v._fresca({k: x for k, x in piena.items()
                                    if k != "valore_eur"}))
        # Senza nome: non e' una verifica, e' una lettura fallita.
        self.assertFalse(v._fresca({k: x for k, x in piena.items()
                                    if k != "nome_sul_profilo"}))


class TestNonLoSoNonEUnVerdetto(unittest.TestCase):
    """
    Il principio vale in tutto il file ma mancava nel punto centrale.

    Se dalla pagina non si cava nemmeno un nome, `analizza` torna
    combacia=False — e a valle quel False si legge "e' un'altra persona" e fa
    RIMUOVERE il link. Ma una pagina illeggibile non dice niente su quel
    giocatore: puo' essere una schermata anti-bot, un errore temporaneo, un
    cambio di layout.

    Visto il 26 ago 2026 rileggendo i 62 profili gia' verificati: tre link
    buoni (Alessandro Cardascio, Jordan Boli, Milos Bocic) tolti con
    motivazione «il profilo e' di '', non di ...».
    """

    def _verificatore(self, pagina):
        from unittest import mock
        from src import tm_verify
        v = tm_verify.VerificatoreTM(cache_path=Path(self.tmp) / "cache.json")
        p = mock.patch.object(tm_verify, "_scarica", return_value=pagina)
        p.start(); self.addCleanup(p.stop)
        return v

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    URL = "https://www.transfermarkt.it/jordan-boli/profil/spieler/338261"

    def test_pagina_illeggibile_non_e_un_altra_persona(self):
        v = self._verificatore("Just a moment... Checking your browser")
        self.assertIsNone(v.verifica("Jordan Boli", self.URL))
        self.assertEqual(v.smascherati, 0, "non e' uno smascheramento")
        self.assertEqual(v.falliti, 1)

    def test_e_non_si_mette_in_cache_un_esito_che_non_e_un_esito(self):
        v = self._verificatore("")
        v.verifica("Jordan Boli", self.URL)
        self.assertEqual(v.cache, {})

    def test_una_persona_diversa_resta_uno_smascheramento(self):
        pagina = ("Title: Tomaso Lorenzi - Profilo giocatore | Transfermarkt\n"
                  "Squadra attuale: [Pontedera]")
        v = self._verificatore(pagina)
        r = v.verifica("Achraf El Bouchataoui", self.URL)
        self.assertIsNotNone(r)
        self.assertFalse(r.combacia)
        self.assertEqual(v.smascherati, 1)
