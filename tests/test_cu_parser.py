#!/usr/bin/env python3
"""
Test offline del parser dei Comunicati Ufficiali LND (ARCH-003).

Le fixture NON sono un formato ideale: sono righe copiate dal CU 146 del CRER
(13/04/2026), spazi interni nelle date e artefatti di impaginazione compresi.
Un parser che passa su un formato pulito e cade su quello vero non serve.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_cu_parser -v
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cu_parser import CUStore, parse_cu_text

# Blocco reale (CU 146 CRER, Fasi Finali Under 19 Élite), verbatim.
CU_REALE = """COMUNICATO UFFICIALE N. 146 DEL 13/4/2026

FASI FINALI UNDER 19 ELITE

GARE DEL 11/ 4/2026

PROVVEDIMENTI DISCIPLINARI
In base alle risultanze degli atti ufficiali sono state deliberate le seguenti sanzioni disciplinari.

DIRIGENTI
I AMMONIZIONE DIFFIDA
VIGHI ALESSIO (NOCETO)    VIGHI MATTEO (NOCETO)
GIRONE A - 12 Giornata - R
SORAGNA 1921 - PONTENURESE - D

GIRONE X - 1 Giornata - A
CASTENASO CALCIO - NOCETO 5 - 6 dcr
FIORENZUOLA 1922 SSD ARL - REAL FORMIGINE 3 - 1
TERRE DI CASTELLI 1907 - SAVIGNANESE 4 - 3  dcr

 5036 5036

ALLENATORI
SQUALIFICA FINO AL 18/ 5/2026
RANIERI RICCARDO (NOCETO)
Per gravi proteste nei confronti dell'Arbitro Per aver rivolto gravi proteste e frasi offensive nei confronti
dell'arbitro.

I AMMONIZIONE DIFFIDA
CANOVA GIANMARCO (CASTENASO CALCIO)

CALCIATORI ESPULSI
SQUALIFICA PER DUE GARE EFFETTIVE
PELLEGRI FILIPPO (VIANESE CALCIO SSDARL)

I AMMONIZIONE DIFFIDA
BARATTINI LORENZO (CASTENASO CALCIO)    DASCIA TOMMASO (CASTENASO CALCIO)
SPADONI LUCA (MEDICINA FOSSATONE S.S.D.)    ALINOVI SEBASTIANO (NOCETO)
"""


def _sanction(parsed, person):
    return next(s for s in parsed["sanctions"] if s["person"] == person)


class ParseMetaTestCase(unittest.TestCase):
    def test_numero_e_data_del_comunicato(self):
        meta = parse_cu_text(CU_REALE)["meta"]
        self.assertEqual(meta["cu_number"], 146)
        self.assertEqual(meta["cu_date"], "2026-04-13")

    def test_data_gare_con_spazi_interni(self):
        """'GARE DEL 11/ 4/2026' -> 2026-04-11. Lo spazio c'e' nel PDF vero."""
        s = _sanction(parse_cu_text(CU_REALE), "VIGHI ALESSIO")
        self.assertEqual(s["match_date"], "2026-04-11")

    def test_testo_vuoto_non_esplode(self):
        parsed = parse_cu_text("")
        self.assertIsNone(parsed["meta"]["cu_number"])
        self.assertEqual(parsed["results"], [])
        self.assertEqual(parsed["sanctions"], [])


class ParseResultsTestCase(unittest.TestCase):
    def setUp(self):
        self.results = parse_cu_text(CU_REALE)["results"]

    def test_estrae_solo_le_righe_con_punteggio(self):
        """'SORAGNA 1921 - PONTENURESE - D' non ha punteggio: non e' un risultato."""
        self.assertEqual(len(self.results), 3)
        self.assertNotIn("SORAGNA 1921", [r["home"] for r in self.results])

    def test_punteggio_girone_e_giornata(self):
        r = self.results[0]
        self.assertEqual((r["home"], r["away"]), ("CASTENASO CALCIO", "NOCETO"))
        self.assertEqual((r["home_goals"], r["away_goals"]), (5, 6))
        self.assertEqual(r["note"], "dcr")
        self.assertEqual((r["girone"], r["giornata"]), ("X", 1))

    def test_nomi_societa_con_numeri_non_finiscono_nel_punteggio(self):
        r = self.results[1]
        self.assertEqual(r["home"], "FIORENZUOLA 1922 SSD ARL")
        self.assertEqual((r["home_goals"], r["away_goals"]), (3, 1))


class ParseSanctionsTestCase(unittest.TestCase):
    def setUp(self):
        self.parsed = parse_cu_text(CU_REALE)

    def test_due_tesserati_sulla_stessa_riga(self):
        noceto = [s for s in self.parsed["sanctions"]
                  if s["person"].startswith("VIGHI")]
        self.assertEqual({s["person"] for s in noceto},
                         {"VIGHI ALESSIO", "VIGHI MATTEO"})
        self.assertTrue(all(s["club"] == "NOCETO" for s in noceto))

    def test_squalifica_a_termine_porta_la_data_di_fine(self):
        s = _sanction(self.parsed, "RANIERI RICCARDO")
        self.assertEqual(s["kind"], "SQUALIFICA_FINO_AL")
        self.assertEqual(s["detail"], "2026-05-18")
        self.assertEqual(s["role"], "ALLENATORI")

    def test_squalifica_a_giornate(self):
        s = _sanction(self.parsed, "PELLEGRI FILIPPO")
        self.assertEqual(s["kind"], "SQUALIFICA_GARE")
        self.assertEqual(s["detail"], "DUE")

    def test_ammonizione_con_diffida(self):
        s = _sanction(self.parsed, "CANOVA GIANMARCO")
        self.assertEqual(s["kind"], "AMMONIZIONE")
        self.assertEqual(s["detail"], "I_DIFFIDA")

    def test_la_motivazione_si_attacca_alla_squalifica_precedente(self):
        s = _sanction(self.parsed, "RANIERI RICCARDO")
        self.assertIn("gravi proteste", s["reason"])

    def test_larbitro_della_motivazione_non_diventa_un_tesserato(self):
        """'nei confronti dell'Arbitro (art. 36)' non e' un giocatore."""
        people = {s["person"] for s in self.parsed["sanctions"]}
        self.assertFalse(any("ARBITRO" in p.upper() for p in people))

    def test_artefatti_di_impaginazione_ignorati(self):
        self.assertFalse(any("5036" in s["person"]
                             for s in self.parsed["sanctions"]))


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.store = CUStore(":memory:")
        self.parsed = parse_cu_text(CU_REALE)

    def tearDown(self):
        self.store.close()

    def test_reingerire_lo_stesso_cu_non_duplica(self):
        """Requisito: rilanciare l'ingestion deve essere sicuro."""
        first = self.store.ingest(self.parsed)
        self.assertGreater(first["new_sanctions"], 0)
        self.assertEqual(self.store.ingest(self.parsed),
                         {"new_sanctions": 0, "new_results": 0})

    def test_squalificati_alla_data_del_brief(self):
        self.store.ingest(self.parsed)
        nomi = {r["person"] for r in self.store.squalificati("2026-04-16")}
        self.assertIn("RANIERI RICCARDO", nomi)   # squalificato fino al 18/5
        self.assertIn("PELLEGRI FILIPPO", nomi)   # due giornate
        self.assertNotIn("VIGHI ALESSIO", nomi)   # solo diffidato

    def test_squalifica_scaduta_esce_dalla_lista(self):
        self.store.ingest(self.parsed)
        nomi = {r["person"] for r in self.store.squalificati("2026-06-01")}
        self.assertNotIn("RANIERI RICCARDO", nomi)

    def test_indice_di_presenza_conta_solo_i_calciatori(self):
        """Un dirigente ammonito non era in campo: fuori dall'indice."""
        self.store.ingest(self.parsed)
        nomi = {r["person"] for r in self.store.presence_index()}
        self.assertIn("PELLEGRI FILIPPO", nomi)
        self.assertNotIn("VIGHI ALESSIO", nomi)      # DIRIGENTI
        self.assertNotIn("RANIERI RICCARDO", nomi)   # ALLENATORI

    def test_indice_di_presenza_filtrato_per_societa(self):
        self.store.ingest(self.parsed)
        rows = self.store.presence_index(club="CASTENASO CALCIO")
        self.assertTrue(rows)
        self.assertTrue(all(r["club"] == "CASTENASO CALCIO" for r in rows))

    def test_due_cu_diversi_accumulano_giornate_distinte(self):
        self.store.ingest(self.parsed)
        secondo = parse_cu_text(
            CU_REALE.replace("N. 146 DEL 13/4/2026", "N. 152 DEL 20/4/2026")
                    .replace("GARE DEL 11/ 4/2026", "GARE DEL 18/ 4/2026"))
        self.assertGreater(self.store.ingest(secondo)["new_sanctions"], 0)
        row = next(r for r in self.store.presence_index()
                   if r["person"] == "PELLEGRI FILIPPO")
        self.assertEqual(row["giornate_distinte"], 2)


class ResolveClubTestCase(unittest.TestCase):
    """
    La tolleranza sta tutta qui, in un punto solo: squalificati()/diffidati()
    restano un confronto SQL esatto (vedi ResolveClubTestCase vs il resto).
    Caso guida: chi configura OB1_CLUB a mano non può sapere in anticipo se
    il comitato scriverà 'RIMINI CALCIO' o 'RIMINI CALCIO SSDARL'.
    """

    def setUp(self):
        self.store = CUStore(":memory:")
        self.store.ingest(parse_cu_text(CU_REALE))

    def tearDown(self):
        self.store.close()

    def test_match_esatto(self):
        self.assertEqual(self.store.resolve_club("NOCETO"), ("NOCETO", []))

    def test_case_e_spazi_non_contano(self):
        self.assertEqual(self.store.resolve_club("  noceto  "), ("NOCETO", []))
        self.assertEqual(self.store.resolve_club("Castenaso   Calcio"),
                         ("CASTENASO CALCIO", []))

    def test_sigla_societaria_mancante_si_risolve_comunque(self):
        """Il caso reale: 'VIANESE CALCIO' senza sigla deve trovare quella con."""
        club, candidati = self.store.resolve_club("VIANESE CALCIO")
        self.assertEqual(club, "VIANESE CALCIO SSDARL")
        self.assertEqual(candidati, [])

    def test_sigla_in_piu_rispetto_al_dato_si_risolve_comunque(self):
        """Direzione opposta: se uno mette la sigla ma il CU non ce l'ha."""
        club, _ = self.store.resolve_club("CASTENASO CALCIO SRL")
        self.assertEqual(club, "CASTENASO CALCIO")

    def test_match_ambiguo_ritorna_solo_i_candidati_che_si_avvicinano(self):
        """'CALCIO' sta sia in CASTENASO CALCIO sia in VIANESE CALCIO SSDARL:
        non è deducibile quale intendesse chi l'ha scritto, quindi niente
        scelta automatica — solo i due, non l'elenco intero."""
        club, candidati = self.store.resolve_club("CALCIO")
        self.assertIsNone(club)
        self.assertEqual(set(candidati),
                         {"CASTENASO CALCIO", "VIANESE CALCIO SSDARL"})

    def test_nome_del_tutto_estraneo_elenca_tutte_le_societa_note(self):
        """Nessuna somiglianza: meglio l'elenco intero che niente."""
        club, candidati = self.store.resolve_club("RIMINI CALCIO")
        self.assertIsNone(club)
        self.assertIn("NOCETO", candidati)
        self.assertIn("CASTENASO CALCIO", candidati)

    def test_squadra_solo_nei_risultati_e_una_squadra_nota(self):
        """
        Caso reale del 5/9/2026: RIMINI CALCIO SSD ARL gioca la 1ª di
        Eccellenza e non prende un solo provvedimento. Leggendo le sole
        sanzioni il brief rispondeva "non corrisponde a nessuna società" —
        un errore di configurazione al posto di "nessuno squalificato".
        """
        club, candidati = self.store.resolve_club("CASTENASO CALCIO")
        self.assertEqual(club, "CASTENASO CALCIO")
        # la stessa via, per una squadra che nel CU compare solo come
        # avversaria in un risultato
        self.assertIn("TERRE DI CASTELLI 1907", self.store.clubs())

    def test_nome_vuoto(self):
        self.assertEqual(self.store.resolve_club(""), (None, []))

    def test_db_senza_societa_non_esplode(self):
        vuoto = CUStore(":memory:")
        self.assertEqual(vuoto.resolve_club("RIMINI CALCIO"), (None, []))
        vuoto.close()


class PersistenceTestCase(unittest.TestCase):
    """
    Su CI il .db non sopravvive al runner: la memoria della stagione sta nel
    JSON versionato. Se questo giro non regge, la lista dei diffidati torna a
    valere solo per l'ultimo comunicato letto — sbagliata senza sembrarlo.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.facts = Path(self.tmp) / "cu_facts.json"
        self.parsed = parse_cu_text(CU_REALE)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_i_fatti_sopravvivono_alla_perdita_del_database(self):
        first = CUStore(":memory:")
        first.ingest(self.parsed)
        atteso = first.export_facts(self.facts)
        diffidati_prima = first.diffidati()
        first.close()

        rebuilt = CUStore(":memory:")          # database nuovo, vuoto
        self.assertEqual(rebuilt.import_facts(self.facts), atteso)
        self.assertEqual(rebuilt.diffidati(), diffidati_prima)
        rebuilt.close()

    def test_reimportare_non_duplica(self):
        store = CUStore(":memory:")
        store.ingest(self.parsed)
        store.export_facts(self.facts)
        store.import_facts(self.facts)
        self.assertEqual(store.import_facts(self.facts),
                         {"sanctions": 0, "results": 0})
        store.close()

    def test_memoria_assente_non_e_un_errore(self):
        """Il primo giro parte senza file: deve valere zero, non esplodere."""
        store = CUStore(":memory:")
        self.assertEqual(store.import_facts(Path(self.tmp) / "mai_scritto.json"),
                         {"sanctions": 0, "results": 0})
        store.close()

    def test_la_memoria_si_accumula_su_piu_comunicati(self):
        store = CUStore(":memory:")
        store.ingest(self.parsed)
        store.export_facts(self.facts)
        store.ingest(parse_cu_text(
            CU_REALE.replace("N. 146 DEL 13/4/2026", "N. 152 DEL 20/4/2026")))
        totale = store.export_facts(self.facts)
        store.close()

        rebuilt = CUStore(":memory:")
        self.assertEqual(rebuilt.import_facts(self.facts), totale)
        rebuilt.close()


class CU24RegressionTestCase(unittest.TestCase):
    """
    Tre difetti trovati il 5/9/2026 lanciando l'ingest sui CU veri del CRER
    (24 del 2/9 e 25 del 4/9). Il primo giro produsse 7 sanzioni: 1 vera, 6
    inventate, e una vera mancante. Per un brief al DS e' il caso peggiore —
    un nome falso costa credibilita', un nome mancante costa una squalifica in
    campo. I testi qui sotto sono ricopiati dai PDF, non semplificati.
    """

    ECCELLENZA = """CAMPIONATO ECCELLENZA
GARE DEL 30/ 8/2026
PROVVEDIMENTI DISCIPLINARI
DIRIGENTI
INIBIZIONE A TEMPO OPPURE SQUALIFICA A GARE: FINO AL 9/ 9/2026
BALDUCCI CLAUDIO (PIETRACUTA A.S.D.)
Per proteste nei confronti del direttore di gara.
CALCIATORI ESPULSI
SQUALIFICA PER UNA GARA EFFETTIVA
YENER EMIN (CAMPAGNOLA)
1351 1351
CAMPIONATO UNDER 18 REGIONALE
Il Giudice Sportivo,
ha letto la documentazione inviata a mezzo pec in data 24 agosto 2026 dalla Soc.
Bellaria Igea Marina con la quale quest'ultima ha formalmente manifestato la
propria volonta' di rinunciare definitivamente a partecipare al Campionato.
"""

    def test_inibizione_a_gare_fino_al_non_si_perde(self):
        """Falso negativo: il CU non scrive 'SQUALIFICA FINO AL' ma
        'SQUALIFICA A GARE: FINO AL'. Con la vecchia regex il dirigente
        inibito spariva dal brief, ed e' l'errore che manda in panchina uno
        squalificato."""
        s = parse_cu_text(self.ECCELLENZA)["sanctions"]
        balducci = [x for x in s if x["person"] == "BALDUCCI CLAUDIO"]
        self.assertEqual(len(balducci), 1)
        self.assertEqual(balducci[0]["kind"], "SQUALIFICA_FINO_AL")
        self.assertEqual(balducci[0]["detail"], "2026-09-09")
        self.assertEqual(balducci[0]["role"], "DIRIGENTI")

    def test_la_motivazione_non_sconfina_nella_sezione_dopo(self):
        """L'intestazione del campionato successivo chiude il blocco: prima
        la sanzione di Balducci si portava dietro pagine di regolamento
        Under 18 come 'motivazione'."""
        s = parse_cu_text(self.ECCELLENZA)["sanctions"]
        motivo = [x for x in s if x["person"] == "BALDUCCI CLAUDIO"][0]["reason"]
        self.assertIn("proteste", motivo)
        self.assertNotIn("Bellaria", motivo)
        self.assertLess(len(motivo), 200)

    def test_solo_le_due_sanzioni_che_ci_sono(self):
        s = parse_cu_text(self.ECCELLENZA)["sanctions"]
        self.assertEqual(sorted(x["person"] for x in s),
                         ["BALDUCCI CLAUDIO", "YENER EMIN"])

    def test_squalifica_per_LA_gara_non_e_una_squalifica(self):
        """Prosa di regolamento, non giustizia sportiva: 'SQUALIFICA PER LA
        GARA' dava una squalifica di 'LA' giornate e da li' ogni riga
        maiuscola diventava un tesserato (CESENA (FC), S.R.L. (U21)...)."""
        prosa = """COPPA EMILIA ROMAGNA
SQUALIFICA PER LA GARA successiva si applica quanto previsto dalle N.O.I.F.
CESENA FC S.R.L. (U21)
"""
        self.assertEqual(parse_cu_text(prosa)["sanctions"], [])

    def test_gare_del_senza_data_non_e_una_data(self):
        """'gare del 31' dentro un regolamento diventava match_date='31'."""
        prosa = "CAMPIONATO PROMOZIONE\nle gare del 31 si disputeranno in gara unica\n"
        self.assertEqual(parse_cu_text(prosa)["sanctions"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
