#!/usr/bin/env python3
"""
IMPATTO — "se arrivasse, sposterebbe?", che e' un'altra domanda da ECC-001.

ECC-001 pesa la prossimita' al 30% perche' risponde a *riusciamo a prenderlo*.
E' la domanda del direttore sportivo. Chi fa ricerca ne ha un'altra: **fra
quelli usciti da una categoria superiore, chi potrebbe fare la differenza qui**.
Convincerlo non e' il lavoro di chi cerca.

Tenerle separate non e' pignoleria: un punteggio unico che mescola fattibilita'
e potenziale non si sa leggere. Davanti a un 60 nessuno saprebbe dire se il
giocatore e' mediocre o se abita lontano — e sono due decisioni opposte.

## Cosa questo numero NON e'

Non e' una valutazione tecnica, e la parola "valutazione" non compare
nell'output. Dai Comunicati Ufficiali sappiamo **chi e' stato svincolato, da
quale societa', in che data e con che eta'**. Non sappiamo se ha giocato,
quanto, in che ruolo, ne' come. Quel giudizio lo danno un allenatore e un
osservatore guardando la partita.

Quello che questo modulo misura e' una cosa sola e verificabile: **da che
categoria arriva**. Un tesserato di Serie D che scende in Eccellenza parte
sopra la media della categoria per costruzione, e questo e' un fatto sul
campionato, non un'opinione sul giocatore.

Test: PYTHONIOENCODING=utf-8 python -m unittest tests.test_impatto -v
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from src.livelli import ETICHETTA, categoria_di, salto_verso

# Va su ogni scheda, identica ovunque. E' il patto con chi legge: qui trovi
# una ricerca, il giudizio lo dai tu.
DISCLAIMER = ("Ricerca su fonti ufficiali, non una valutazione tecnica. "
              "Sappiamo da dove viene e quando è stato svincolato; "
              "quanto e come abbia giocato lo dice chi lo guarda.")

PESI = {"salto": 0.55, "eta": 0.30, "freschezza": 0.15}


def _eta_punti(eta: Optional[int]) -> int:
    if eta is None:
        return 50
    if eta < 19:
        return 55      # puo' diventare, ma in Eccellenza non sposta subito
    if eta <= 21:
        return 80
    if eta <= 29:
        return 100     # gli anni in cui uno rende quanto sa rendere
    if eta <= 32:
        return 70
    if eta <= 35:
        return 45
    return 25


def _salto_punti(salto: Optional[int]) -> int:
    if salto is None:
        return 40      # categoria non riconosciuta: non si sa, non si premia
    if salto >= 1:
        return 100     # scende da sopra
    if salto == 0:
        return 65      # stesso livello: dipende tutto da come giocava
    if salto == -1:
        return 35
    return 20


def _giorni(cu_date: Optional[str], al: Optional[date] = None) -> Optional[int]:
    try:
        d = datetime.strptime(str(cu_date), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return ((al or date.today()) - d).days


def _freschezza_punti(giorni: Optional[int]) -> int:
    if giorni is None:
        return 50
    if giorni <= 14:
        return 100     # appena uscito: probabilmente ancora libero
    if giorni <= 45:
        return 75
    if giorni <= 90:
        return 45
    return 20          # due mesi da svincolato: o ha firmato, o c'e' un perche'


def valuta_impatto(svincolato: Dict[str, Any], mappa: Dict[str, str],
                   obiettivo: str = "eccellenza",
                   al: Optional[date] = None) -> Dict[str, Any]:
    """
    Un record da `cu_svincoli.parse_svincoli` -> potenziale di categoria.

    Ritorna sempre un risultato: qui non c'e' un gate come in ECC-001, perche'
    la fonte e' gia' un atto ufficiale e l'identita' e' certificata dalla
    matricola federale. Cio' che manca non e' la prova, sono i minuti — ed e'
    detto nei `limiti`, non nascosto in un punteggio basso.
    """
    cat = categoria_di(svincolato.get("societa", ""), mappa)
    salto = salto_verso(cat, obiettivo) if cat else None
    eta = svincolato.get("eta")
    giorni = _giorni(svincolato.get("cu_date"), al=al)

    b = {"salto": _salto_punti(salto),
         "eta": _eta_punti(eta),
         "freschezza": _freschezza_punti(giorni)}
    punteggio = int(round(sum(b[k] * PESI[k] for k in PESI)))

    fascia = ("da guardare per primo" if punteggio >= 78
              else "da guardare" if punteggio >= 58
              else "in coda")

    frasi: List[str] = []
    if salto is not None and salto >= 1:
        frasi.append(f"Scende dalla {ETICHETTA.get(cat, cat)}: parte sopra la "
                     f"media della categoria.")
    elif salto == 0:
        frasi.append(f"Viene dalla stessa categoria ({ETICHETTA.get(cat, cat)}): "
                     f"quanto sposti dipende da come giocava, e questo va visto.")
    elif salto is not None:
        frasi.append(f"Viene da una categoria inferiore ({ETICHETTA.get(cat, cat)}): "
                     f"sarebbe un salto per lui.")
    else:
        frasi.append("La categoria della sua ultima società non è nei calendari "
                     "regionali: da chiarire prima di tutto il resto.")

    if eta is not None:
        if eta <= 21:
            frasi.append(f"Ha {eta} anni: giovane, utile anche per le quote.")
        elif eta <= 29:
            frasi.append(f"Ha {eta} anni: età in cui uno rende quanto sa rendere.")
        elif eta <= 32:
            frasi.append(f"Ha {eta} anni: ancora dentro, ma è una scelta di esperienza.")
        else:
            frasi.append(f"Ha {eta} anni: solo per un ruolo preciso.")

    if giorni is not None:
        if giorni <= 14:
            frasi.append(f"Svincolato da {giorni} giorni: è appena uscito.")
        elif giorni <= 45:
            frasi.append(f"Svincolato da {giorni} giorni.")
        else:
            frasi.append(f"Svincolato da {giorni} giorni: può aver già firmato, "
                         f"si verifica con una telefonata.")

    limiti = ["Non sappiamo quante partite abbia giocato, né in che ruolo.",
              "Nessun dato tecnico: il giudizio sul giocatore non è nostro."]
    if svincolato.get("nome_incerto"):
        limiti.append("Il nome esce sporco dal PDF: da confermare col comitato "
                      "prima di usarlo.")

    return {"punteggio": punteggio, "fascia": fascia, "breakdown": b,
            "categoria_provenienza": cat, "salto": salto,
            "giorni_da_svincolo": giorni,
            "spiegazione": frasi, "limiti": limiti, "disclaimer": DISCLAIMER,
            "riassunto": f"{fascia.capitalize()} ({punteggio}/100). " + " ".join(frasi)}


def ordina(svincolati: List[Dict[str, Any]], mappa: Dict[str, str],
           obiettivo: str = "eccellenza",
           al: Optional[date] = None) -> List[Dict[str, Any]]:
    """Lista di svincolati -> stessa lista con l'impatto, dal più alto."""
    fuori = []
    for s in svincolati:
        r = valuta_impatto(s, mappa, obiettivo=obiettivo, al=al)
        fuori.append({**s, "impatto": r})
    fuori.sort(key=lambda x: x["impatto"]["punteggio"], reverse=True)
    return fuori
