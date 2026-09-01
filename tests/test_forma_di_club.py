#!/usr/bin/env python3
"""
Un nome di squadra ha una forma. Tutto il resto non passa.

Perché questo file esiste (1 set 2026)
--------------------------------------
Il controllo su `current_club` era una blacklist: "non è la parola 'squadra',
non è 'svincolato', è lungo più di due caratteri". Una blacklist accetta per
definizione tutto il testo che non ha ancora incontrato, e in ventiquattr'ore
la stessa riga di codice ha scritto due valori falsi di forma diversa:

    Carlo Nesti      -> "| --- | --- | --- | --- | --- | --- |"
    Antonio Parrotto -> "attualmente sconosciuta Ala sinistra Valore di
                         Mercato: - * 30/09/2004 a Cassano"

Il primo è il separatore di una tabella markdown. Il secondo sono quattro
campi diversi della pagina fusi in una riga sola e tagliati a 80 caratteri
esatti — ed è la prova che non è un'invenzione del modello ma una fetta di
testo copiata: nessun nome di squadra vero è lungo esattamente quanto il
limite di troncamento.

Nessuno dei due comincia per punteggiatura, quindi nessun filtro sul primo
carattere li avrebbe mai presi. Da qui la scelta di dire che *forma* deve
avere un nome invece di elencare le forme sbagliate viste finora.

    PYTHONIOENCODING=utf-8 python -m unittest tests.test_forma_di_club -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.enricher_tm import forma_di_club, parse_tm_text


class TestFormaDiClub(unittest.TestCase):
    def test_i_due_valori_veri_sono_respinti(self):
        self.assertFalse(forma_di_club("| --- | --- | --- | --- | --- | --- |"))
        self.assertFalse(forma_di_club(
            "attualmente sconosciuta Ala sinistra Valore di Mercato: "
            "- * 30/09/2004 a Cassano"))

    def test_altri_frammenti_di_tabella_trovati_nello_stesso_giro(self):
        # Non erano due: ripassando i 816 record ne sono usciti altri due,
        # più vecchi. Stessa riga di codice, stessa forma.
        self.assertFalse(forma_di_club("| Costo |"))
        self.assertFalse(forma_di_club(
            "e ruolo | In carica da | fino al | Partite | PPP |"))

    def test_una_riga_di_frase_non_e_un_nome(self):
        self.assertFalse(forma_di_club(
            "Il giocatore si è trasferito la scorsa estate al club"))

    def test_cifre_e_trattini_da_soli_non_bastano(self):
        for v in ("---", "1907", "- - -", "2,80"):
            self.assertFalse(forma_di_club(v), v)

    def test_valori_non_testuali_e_vuoti(self):
        for v in (None, 150000, "", "  ", "ab"):
            self.assertFalse(forma_di_club(v), repr(v))


class TestCorpusVero(unittest.TestCase):
    """
    Le squadre lette DAVVERO dai profili Transfermarkt già verificati
    (data/tm_verifiche.json, 1 set 2026). La specifica è misurata su questi:
    lunghezza massima osservata 27, parole massime 5, e nessuno contiene
    ':' '|' '*' '/' ',' o '€'. Se un giorno un nome vero non passa più, è
    questo test a doverlo dire — non la produzione.
    """

    CORPUS = (
        "1. Oberndorfer SK", "AC Prato", "ACR Messina", "AS Cittadella",
        "AS Gubbio 1910", "AS Roma U20", "ASD Cynthialbalonga", "ASD Nocerina",
        "ASD Sancataldese", "Aglianese Calcio", "Alcione Milano", "Arezzo",
        "Ascoli Calcio", "Atalanta U23", "Athletic Carpi", "Audace Cerignola",
        "Aurora Pro Patria 1919", "Avellino", "Barletta 1922", "Benevento",
        "Bologna U20", "Brescia Calcio", "CS Sedan Ardennes", "Cagliari U20",
        "Calcio Foggia 1920", "Campobasso", "Carrarese Calcio", "Casarano",
        "Casertana FC", "Catania FC", "Cavese 1919", "Cerignola", "Cesena FC",
        "Charleroi", "Chievo Verona", "Club Sportivo Villa Cubas", "Como 1907",
        "Cosenza Calcio", "Crotone", "DB Rossoblù Città Di Luzzi",
        "Delfino Pescara 1936", "Empoli FC", "FBC Gravina", "FC Differdange 03",
        "FC Lugano", "Fermana FC", "Feralpisalò", "Foggia", "Forlì FC",
        "Frosinone Calcio", "Genoa CFC", "Giana Erminio", "Giugliano",
        "Grottammare Calcio 1899", "Guidonia Montecelio 1937 FC",
        "Hellas Verona", "Hellas Verona Under 18", "Inter U20", "Juve Stabia",
        "Juventus U23", "L.R. Vicenza", "Lecco", "Livorno", "Lumezzane",
        "Mantova 1911", "Milan Futuro", "Modena FC", "Monopoli", "Monza",
        "NK Aluminij Kidricevo U19", "Napoli U20", "Novara", "Padova",
        "Palermo FC", "Parma Calcio", "Perugia", "Pescara", "Piacenza",
        "Pineto Calcio", "Pisa SC", "Polisportiva Pietralunghese", "Pontedera",
        "Potenza Calcio", "Pro Vercelli", "Reggiana", "Reggina", "Renate",
        "Rimini FC", "Salernitana", "Sambenedettese", "Sassuolo U20",
        "Sorrento", "Spezia Calcio", "SPAL", "Ternana Calcio", "Torres",
        "Trapani 1905", "Trento", "Triestina", "Turris", "US Avellino 1912",
        "US Catanzaro", "US Lecce", "US Salernitana", "US Triestina Calcio 1918",
        "Udinese U20", "Union Brescia", "Vicenza", "Virtus Entella",
        "Virtus Verona", "Vis Pesaro", "Zenit St. Petersburg",
    )

    def test_ogni_nome_vero_passa(self):
        for nome in self.CORPUS:
            self.assertTrue(forma_di_club(nome), nome)

    def test_il_corpus_su_disco_passa_ancora(self):
        """
        Il test sopra è una copia congelata. Questo legge il file vivo, se c'è:
        quando la pipeline incontra una squadra di forma nuova, lo scopriamo
        qui e non da un campo vuoto in dashboard.
        """
        import json
        f = Path(__file__).resolve().parent.parent / "data" / "tm_verifiche.json"
        if not f.exists():
            self.skipTest("data/tm_verifiche.json non presente")
        d = json.loads(f.read_text(encoding="utf-8"))
        nomi = {v.get("squadra", "").strip() for v in d.values()}
        # "---", "Unknown" e "svincolato" stanno nel file ma non sono squadre:
        # sono non-risposte, e restano fuori apposta.
        nomi -= {"", "---", "Unknown", "unknown", "svincolato", "Svincolato"}
        respinti = sorted(n for n in nomi if not forma_di_club(n))
        self.assertEqual(respinti, [], f"nomi veri respinti: {respinti}")


class TestParserNonInventaPiu(unittest.TestCase):
    """Il difetto non era la forma del filtro ma il ciclo: scorreva 300
    caratteri finché *qualcosa* passava, quindi non poteva mai rispondere
    "non lo so". Ora prende il primo contenuto utile e si ferma lì."""

    def test_tabella_di_carriera_non_diventa_una_squadra(self):
        pagina = ("Carlo Nesti - Profilo giocatore\n\n"
                  "| Stagione | Squadra |\n"
                  "| --- | --- | --- | --- | --- | --- |\n"
                  "| 25/26 | AC Prato |\n")
        self.assertIsNone(parse_tm_text(pagina).get("current_club"))

    def test_campi_fusi_su_una_riga_non_diventano_una_squadra(self):
        pagina = ("Squadra attuale:  attualmente sconosciuta   Ala sinistra   "
                  "Valore di Mercato: -   * 30/09/2004 a Cassano")
        self.assertIsNone(parse_tm_text(pagina).get("current_club"))

    def test_il_valore_vero_su_riga_successiva_passa_ancora(self):
        pagina = "Squadra attuale:\n\n\n US Avellino 1912\n\nIn rosa da:\n10/07/2023"
        self.assertEqual(parse_tm_text(pagina)["current_club"], "US Avellino 1912")

    def test_il_valore_vero_sulla_stessa_riga_passa_ancora(self):
        self.assertEqual(
            parse_tm_text("Club attuale: Avellino\nPiede: destro")["current_club"],
            "Avellino")

    def test_link_markdown_passa_ancora(self):
        md = "[Atalanta U23](/atalanta-u23/startseite/verein/54365) Nato il: 03/05/2006"
        self.assertEqual(parse_tm_text(md)["current_club"], "Atalanta U23")

    def test_label_senza_valore_resta_non_lo_so(self):
        pagina = "Squadra attuale:\n\nIn rosa da:\n10/07/2023"
        self.assertIsNone(parse_tm_text(pagina).get("current_club"))


if __name__ == "__main__":
    unittest.main()
