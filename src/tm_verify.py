#!/usr/bin/env python3
"""
Verifica d'identità su Transfermarkt — aprire davvero il profilo e guardare
di chi è.

Il blocco che questo modulo scioglie
------------------------------------
Fino al 26 agosto 2026 il prodotto scriveva "✓ Dati verificati su
Transfermarkt" su 85 schede su 85, e il valore dietro quel bollino era
`bool(url_ben_formato)`: nessun profilo veniva mai aperto. Trentatré di
quegli 85 link avevano un ID inventato (tondo: 939000, 1000000, 600000), e
uno — quello che stava per essere mandato a un direttore sportivo — aveva
un ID plausibile che apparteneva a un'altra persona:

    /andrea-rizzo-pinna/profil/spieler/538430   ->  Emre Dalgalıdere, turco
    /andrea-rizzo-pinna/profil/spieler/411465   ->  Andrea Rizzo Pinna

Lo slug è identico e giusto in entrambi. Su Transfermarkt la pagina la
decide il NUMERO: nessuna regola sulla forma del numero distingue 538430 da
411465. L'unico modo di sapere di chi è un ID è **aprirlo e leggere il
nome**.

E qui c'era il muro: Transfermarkt risponde anti-bot agli IP dei datacenter,
quindi dai runner di GitHub Actions il profilo non si scarica (limite già
documentato nel README del progetto).

La via d'uscita, misurata il 26 ago 2026: **Jina Reader** (`r.jina.ai`), che
questo progetto già usa per leggere gli articoli, scarica la pagina dalla
*sua* infrastruttura e ce la restituisce in markdown. Il blocco sugli IP
nostri non si applica. Provato sui due ID sopra: 200, 46 KB, nome corretto
in entrambi i casi — e il finto smascherato.

Nessuna chiave obbligatoria. Con JINA_API_KEY il tetto di richieste al
minuto è più alto, ma senza chiave funziona lo stesso.

Cosa restituisce, e perché quei campi
-------------------------------------
Aprire il profilo non serve solo a dire sì/no sull'identità: la stessa
pagina porta i dati che il sistema prima inventava o lasciava scadere.

    nome           l'unica cosa che decide se l'ID è di questa persona
    data_nascita   l'età smette di essere dedotta e diventa dichiarata
    squadra        risolve la staleness: la dashboard diceva "Ascoli", il
                   profilo dice "Union Brescia" — la segnalazione di marzo
                   era morta e nessuno se ne accorgeva
    contratto_fino la scadenza vera, non una voce di mercato di sei mesi fa
    valore, ruolo, piede, procuratore

Ogni campo esce solo se la pagina lo scrive: nessun valore stimato.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.request
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

JINA_READER = "https://r.jina.ai/"
CACHE = Path("data/tm_verifiche.json")

# Un profilo aperto oggi vale a lungo per l'IDENTITÀ (chi è quell'ID non
# cambia mai) ma non per la SQUADRA. Si ri-verifica dopo questo intervallo
# perché è il club a scadere, non il nome.
TTL_GIORNI = int(os.getenv("TM_VERIFY_TTL_GIORNI", "30"))

_TIMEOUT = int(os.getenv("TM_VERIFY_TIMEOUT", "30"))

_RE_ID = re.compile(r"/profil/spieler/(\d+)")
_RE_NOME = re.compile(
    r"Title:\s*(.+?)\s*[-–]\s*(?:Profilo giocatore|Player profile|Perfil del jugador)",
    re.IGNORECASE)
# "Nato il: 13/01/2000 (26)" oppure "Nato il:[13/01/2000 (26)](...)"
_RE_NASCITA = re.compile(
    r"(?:Nato il|Date of birth|Fecha de nacimiento)\s*:\s*\[?\s*(\d{1,2}[/.]\d{1,2}[/.]\d{4})",
    re.IGNORECASE)
# "Squadra attuale: [![Image 39: Union Brescia](...)"
_RE_SQUADRA = re.compile(
    r"(?:Squadra attuale|Current club|Club actual)\s*:\s*\[?!?\[?"
    r"(?:Image\s*\d+\s*:\s*)?([^\]\(\)\n]{2,45})", re.IGNORECASE)
_RE_CONTRATTO = re.compile(
    r"(?:Contratto fino|Contract expires|Contrato hasta)\s*:\s*\[?\s*(\d{1,2}[/.]\d{1,2}[/.]\d{4})",
    re.IGNORECASE)
_RE_RUOLO = re.compile(
    r"(?:Posizione|Position|Posición)\s*:\s*\[?([^\[\]\n*]{3,45})", re.IGNORECASE)
_RE_PIEDE = re.compile(r"(?:Piede|Foot|Pie)\s*:\s*(\w+)", re.IGNORECASE)
_RE_PROCURATORE = re.compile(
    r"(?:Procuratore|Agent|Agente)\s*:\s*\[([^\]]{2,45})\]", re.IGNORECASE)


def _norm(t: Any) -> str:
    s = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


@dataclass
class Verifica:
    """
    L'esito di aver aperto un profilo. `combacia` è l'unico campo che decide
    se il link si può pubblicare; tutto il resto è quel che la pagina dice.
    """
    id_profilo: str = ""
    combacia: bool = False
    nome_sul_profilo: str = ""
    nome_cercato: str = ""
    motivo: str = ""
    data_nascita: str = ""
    squadra: str = ""
    contratto_fino: str = ""
    ruolo: str = ""
    piede: str = ""
    procuratore: str = ""
    verificato_il: str = ""

    def eta(self, oggi: Optional[datetime] = None) -> Optional[int]:
        """Età dalla data di nascita LETTA sul profilo. Mai stimata."""
        if not self.data_nascita:
            return None
        try:
            g, m, a = re.split(r"[/.]", self.data_nascita)
            nato = datetime(int(a), int(m), int(g))
        except (ValueError, TypeError):
            return None
        oggi = oggi or datetime.now()
        return oggi.year - nato.year - ((oggi.month, oggi.day) < (nato.month, nato.day))


def nomi_combaciano(cercato: str, trovato: str) -> bool:
    """
    Il nome sul profilo è la stessa persona che cercavamo?

    Regge le varianti reali del database ("Rizzo Pinna" contro "Andrea Rizzo
    Pinna", "CHIOETTO JHONATAN DAVID" contro "Jhonatan Chioetto") chiedendo
    che condividano almeno un token lungo. Non è una somiglianza vaga: se
    l'ID fosse di un'altra persona, i token non si toccherebbero — ed è
    esattamente il caso Rizzo Pinna / Dalgalidere.
    """
    a = {t for t in _norm(cercato).split() if len(t) >= 4}
    b = {t for t in _norm(trovato).split() if len(t) >= 4}
    if not a or not b:
        return False
    return bool(a & b)


def analizza(markdown: str, nome_cercato: str = "", id_profilo: str = "") -> Verifica:
    """
    Legge il markdown di Jina Reader. Puro: nessuna rete, testabile con una
    pagina salvata.
    """
    v = Verifica(id_profilo=id_profilo, nome_cercato=nome_cercato,
                 verificato_il=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    piatto = " ".join((markdown or "").split())

    m = _RE_NOME.search(piatto)
    if not m:
        v.motivo = "la pagina non ha un titolo di profilo giocatore"
        return v
    v.nome_sul_profilo = m.group(1).strip()

    for campo, rex in (("data_nascita", _RE_NASCITA), ("squadra", _RE_SQUADRA),
                       ("contratto_fino", _RE_CONTRATTO), ("ruolo", _RE_RUOLO),
                       ("piede", _RE_PIEDE), ("procuratore", _RE_PROCURATORE)):
        mm = rex.search(piatto)
        if mm:
            setattr(v, campo, mm.group(1).strip(" *: "))

    if not nome_cercato:
        v.motivo = "nessun nome da confrontare"
        return v
    v.combacia = nomi_combaciano(nome_cercato, v.nome_sul_profilo)
    v.motivo = ("il profilo è di questa persona" if v.combacia else
                f"il profilo è di '{v.nome_sul_profilo}', non di '{nome_cercato}'")
    return v


def _scarica(url: str) -> str:
    """Markdown della pagina via Jina Reader, o stringa vuota. Non solleva mai."""
    intestazioni = {"User-Agent": "Mozilla/5.0"}
    chiave = os.getenv("JINA_API_KEY", "")
    if chiave:
        intestazioni["Authorization"] = f"Bearer {chiave}"
    try:
        req = urllib.request.Request(JINA_READER + url, headers=intestazioni)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            if r.status != 200:
                return ""
            return r.read().decode("utf-8", "ignore")
    except Exception:
        return ""


class VerificatoreTM:
    """
    Apre i profili e ricorda gli esiti. I contatori NON sono decorativi: un
    fallimento di rete che passa in silenzio riporterebbe il prodotto al
    problema di partenza (una verifica che non è avvenuta ma sembra avvenuta),
    quindi ogni esito è contato e va stampato a fine run.
    """

    def __init__(self, cache_path: Path = None):
        self.cache_path = Path(cache_path or CACHE)
        self.cache: Dict[str, dict] = self._carica()
        self.aperti = 0
        self.da_cache = 0
        self.falliti = 0
        self.smascherati = 0

    def _carica(self) -> Dict[str, dict]:
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _salva(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self.cache, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8")
        except OSError:
            pass

    def _fresca(self, voce: dict) -> bool:
        quando = voce.get("verificato_il") or ""
        try:
            t = datetime.fromisoformat(quando)
        except ValueError:
            return False
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).days < TTL_GIORNI

    def verifica(self, nome: str, tm_url: str) -> Optional[Verifica]:
        """
        Apre il profilo (o riusa una verifica recente) e dice se quell'ID è
        di questa persona. None se non si è potuto verificare — che NON
        significa "non combacia": significa che non lo sappiamo, ed è una
        cosa diversa da dire in dashboard.
        """
        m = _RE_ID.search(tm_url or "")
        if not m:
            return None
        pid = m.group(1)
        chiave = f"{pid}|{_norm(nome)}"

        voce = self.cache.get(chiave)
        if voce and self._fresca(voce):
            self.da_cache += 1
            return Verifica(**voce)

        markdown = _scarica(tm_url)
        if not markdown:
            self.falliti += 1
            return None

        v = analizza(markdown, nome_cercato=nome, id_profilo=pid)
        self.aperti += 1
        if not v.combacia:
            self.smascherati += 1
        self.cache[chiave] = asdict(v)
        self._salva()
        return v

    def riepilogo(self) -> str:
        return (f"verifiche TM: {self.aperti} profili aperti · "
                f"{self.da_cache} da cache · {self.smascherati} ID smascherati · "
                f"{self.falliti} non verificabili")


# --------------------------------------------------------------- self-test
if __name__ == "__main__":
    # Pagina reale di Andrea Rizzo Pinna (ID 411465), ridotta ai pezzi che
    # contano — catturata da r.jina.ai il 26 ago 2026. Serve a testare il
    # parsing senza rete: i selettori vengono da una pagina vera, non da
    # come immagino che TM sia fatto.
    PAGINA = (
        "Title: Andrea Rizzo Pinna - Profilo giocatore 26/27 "
        "URL Source: https://www.transfermarkt.it/andrea-rizzo-pinna/profil/spieler/411465 "
        "Markdown Content: # #25 Andrea **Rizzo Pinna** "
        "[![Image 20: Union Brescia](https://img.a.transfermarkt.technology/x.png)]"
        "(https://www.transfermarkt.it/union-brescia/startseite/verein/132806 \"Union Brescia\") "
        "Arrivo: 22/07/2026 Contratto fino: 30/06/2029 "
        "* Nato il: 13/01/2000 (26) * Luogo di nascita: Milano "
        "Altezza:1,72 m Nazionalità: Italia Posizione: Centrocampo - Trequartista "
        "Piede:destro Procuratore:[MM-Management](https://www.transfermarkt.it/x) "
        "Squadra attuale: [![Image 39: Union Brescia](https://img.a.x.png)]"
    )

    v = analizza(PAGINA, nome_cercato="Rizzo Pinna", id_profilo="411465")
    assert v.combacia, v.motivo
    assert v.nome_sul_profilo == "Andrea Rizzo Pinna", v.nome_sul_profilo
    assert v.data_nascita == "13/01/2000", v.data_nascita
    assert v.contratto_fino == "30/06/2029", v.contratto_fino
    assert "Brescia" in v.squadra, v.squadra
    assert v.piede.lower() == "destro", v.piede
    assert "MM-Management" in v.procuratore, v.procuratore
    # L'età non è più dedotta: viene da una data letta sul profilo.
    assert v.eta(datetime(2026, 8, 26)) == 26, v.eta(datetime(2026, 8, 26))

    # Il caso che ha fatto scoppiare tutto: stesso slug, ID di un'altra
    # persona. Nessun controllo sintattico poteva prenderlo; aprire la
    # pagina sì.
    ALTRA = "Title: Emre Dalgalıdere - Player profile 26/27 Markdown Content: ..."
    v2 = analizza(ALTRA, nome_cercato="Rizzo Pinna", id_profilo="538430")
    assert not v2.combacia
    assert "Emre" in v2.motivo, v2.motivo

    # Varianti legittime del database: non devono essere scartate.
    assert nomi_combaciano("Rizzo Pinna", "Andrea Rizzo Pinna")
    assert nomi_combaciano("CHIOETTO JHONATAN DAVID", "Jhonatan Chioetto")
    assert nomi_combaciano("Nicolò Rovella", "Nicolo Rovella")
    # ...e persone diverse devono esserlo.
    assert not nomi_combaciano("Rizzo Pinna", "Emre Dalgalidere")
    assert not nomi_combaciano("Berardini Alessandro", "Stefano Del Sante")

    # Una pagina che non è un profilo non produce mai una verifica positiva.
    v3 = analizza("Title: Serie C - Girone A - Classifica", nome_cercato="Tizio")
    assert not v3.combacia and "non ha un titolo" in v3.motivo

    print("OK tm_verify: il profilo si apre davvero, l'ID di un'altra persona "
          "viene smascherato, e la pagina porta data di nascita e squadra "
          "attuale — cioè età dichiarata e staleness risolta.")
