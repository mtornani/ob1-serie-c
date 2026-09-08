#!/usr/bin/env python3
"""
Gli svincolati dai Comunicati Ufficiali: nomi veri, al livello giusto.

Il radar cercava svincolati sui portali di calciomercato e trovava Donnarumma.
La lista che serve a un club di Eccellenza la pubblica il comitato stesso, nel
CU che questa pipeline gia' scarica ogni giovedi', in una tabella come questa:

    Matricola Calciatore      Nascita     Matricola Societa'
    4630785   CARBONI FILIPPO 25/03/1998  70392   OSTERIA GRANDE
    6893545   TORTORA KEVIN   01/05/2004  6740    BOBBIESE

Perche' vale piu' di qualsiasi fonte trovata finora:

  - **e' un atto pubblico**: non scade, non risponde 404, si cita per numero
    e data. Il problema che ha ucciso 580 record del database non esiste qui;
  - **la matricola e' una chiave vera**: niente accoppiamenti per nome, che e'
    il modo in cui "CHIOETTO JHONATAN DAVID" aveva finito per portarsi dietro
    il profilo di Jonathan David;
  - **la data di nascita e' esatta**, quindi l'eta' non si stima;
  - **il livello e la regione sono giusti per costruzione**: sono tesserati di
    societa' del comitato, non gente di Serie A che non scendera' mai;
  - **esce tutto l'anno**, non solo nella finestra di dicembre: verificato sui
    CU 20, 24 e 25 del settembre 2026.

Due articoli producono queste liste, e li trattiamo insieme perche' per chi
cerca un giocatore la conseguenza e' la stessa — quella persona e' libera:
  - art. 117 bis: risoluzione del contratto di lavoro sportivo;
  - art. 107/109: decadenza dal tesseramento (rinuncia, inattivita').

Test: PYTHONIOENCODING=utf-8 python -m unittest tests.test_cu_svincoli -v
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

# L'intestazione della tabella. E' la sola ancora affidabile: il paragrafo che
# la precede cambia formula fra un articolo e l'altro, la tabella no.
RE_INTESTAZIONE = re.compile(
    r"Matricola\s+Calciatore\s+Nascita\s+Matricola\s+Societ", re.IGNORECASE)

# Una riga. La matricola puo' arrivare puntata ("3.937.990") o liscia; il nome
# e' in maiuscolo e puo' avere piu' parole, apostrofi tipografici e lettere
# accentate; la societa' e' tutto cio' che resta fino alla riga dopo.
RE_RIGA = re.compile(
    r"(?P<matricola>\d[\d.]{4,12})\s+"
    r"(?P<nome>[A-ZÀ-ÜÄ-Ü][A-ZÀ-ÜÄ-Ü'’.\- ]{2,48}?)\s+"
    r"(?P<nascita>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<matricola_societa>\d[\d.]{2,10})\s+"
    r"(?P<societa>[A-ZÀ-Ü0-9][^\n]{1,60}?)"
    r"(?=\s+\d[\d.]{4,12}\s+[A-ZÀ-Ü]|\s*$)", re.MULTILINE)

# Dove finisce la tabella: il comitato chiude sempre con la frase sul nuovo
# tesseramento. Senza questo confine il regex prosegue nel resto del comunicato.
RE_FINE = re.compile(
    r"(È|E')\s+possibile\s+effettuare\s+il\s+nuovo\s+tesseramento|"
    r"possono\s+tesserarsi\s+nuovamente", re.IGNORECASE)

_SPAZI = re.compile(r"\s+")


def _pulisci_matricola(raw: str) -> str:
    return raw.replace(".", "").strip()


def _nome_proprio(raw: str) -> str:
    """'CARBONI FILIPPO' -> 'Carboni Filippo'. L'apostrofo tipografico resta."""
    return " ".join(p.capitalize() for p in _SPAZI.sub(" ", raw).strip().split())


def _eta(nascita_iso: str, al: Optional[date] = None) -> Optional[int]:
    try:
        n = datetime.strptime(nascita_iso, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    al = al or date.today()
    return al.year - n.year - ((al.month, al.day) < (n.month, n.day))


# Una lettera isolata in mezzo al nome quasi sempre e' pypdf che ha spezzato
# il cognome: "CAVALLIN I EDOARDO" era "CAVALLINI EDOARDO". Quasi sempre, non
# sempre — un'iniziale puntata esiste. Quindi non si indovina: si marca, e chi
# produce una scheda decide se escluderlo o telefonare al comitato.
RE_LETTERA_SOLA = re.compile(r"(?:^|\s)[A-ZÀ-Ü](?=\s)")


def nome_incerto(nome: str) -> bool:
    """Il nome porta un segno di estrazione sporca?"""
    return bool(RE_LETTERA_SOLA.search(nome.upper()))


def parse_svincoli(testo: str, cu_number: Optional[int] = None,
                   cu_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Testo di un CU -> elenco di svincolati. Codice puro, nessuna rete.

    Se la tabella non c'e', la risposta e' una lista vuota: la maggioranza dei
    comunicati non contiene svincoli, e questo non e' un errore.
    """
    if not testo:
        return []

    fuori = []
    for intestazione in RE_INTESTAZIONE.finditer(testo):
        inizio = intestazione.end()
        fine_m = RE_FINE.search(testo, inizio)
        # Il blocco arriva fino alla frase di chiusura, o a 6.000 caratteri:
        # un tetto serve perche' se la frase manca il regex mangerebbe il resto
        # del comunicato, e la' dentro ci sono i provvedimenti disciplinari.
        fine = min(fine_m.start() if fine_m else len(testo), inizio + 6000)
        blocco = testo[inizio:fine]

        for m in RE_RIGA.finditer(blocco):
            g, n = m.group, m.group("nascita")
            iso = f"{n[6:10]}-{n[3:5]}-{n[0:2]}"
            fuori.append({
                "matricola": _pulisci_matricola(g("matricola")),
                "nome": _nome_proprio(g("nome")),
                "nascita": iso,
                "eta": _eta(iso),
                "matricola_societa": _pulisci_matricola(g("matricola_societa")),
                "societa": _SPAZI.sub(" ", g("societa")).strip(),
                "nome_incerto": nome_incerto(g("nome")),
                "cu_number": cu_number,
                "cu_date": cu_date,
                "fonte": "svincolo da Comunicato Ufficiale",
            })
    # Stessa persona in piu' blocchi dello stesso CU: la matricola decide.
    unici = {}
    for s in fuori:
        unici.setdefault(s["matricola"], s)
    return list(unici.values())


def solo_maggiorenni(svincolati: List[Dict[str, Any]],
                     al: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Filtro obbligatorio prima di qualunque uscita che esca dal club.

    I CU pubblicano anche tesserati minorenni: sono atti pubblici e leggerli e'
    legittimo, ma metterne il nome su una scheda che gira su WhatsApp non lo e'.
    Il vincolo sta qui, in una funzione, e non nella buona memoria di chi
    scrive il prossimo script.
    """
    fuori = []
    for s in svincolati:
        e = _eta(s.get("nascita", ""), al=al)
        if e is not None and e >= 18:
            fuori.append(s)
    return fuori
