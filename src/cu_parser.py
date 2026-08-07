#!/usr/bin/env python3
"""
ARCH-003 — Parser dei Comunicati Ufficiali LND (giustizia sportiva + risultati).

Da UNA fonte (il PDF del CU, grado A) escono TRE prodotti:
  - squalificati/diffidati per il brief del giovedì (DS);
  - memoria disciplinare della rosa (settore giovanile);
  - indice di presenza: un ammonito era in campo, per forza (scouting).

Il formato è quello VERIFICATO su CU 146 del CRER (13/04/2026), non uno ideale.
Particolarità reali di cui il parser tiene conto:
  - le date hanno spazi interni: "GARE DEL 11/ 4/2026", "FINO AL 18/ 5/2026";
  - due tesserati sulla stessa riga: "VIGHI ALESSIO (NOCETO)  VIGHI MATTEO (NOCETO)";
  - artefatti di impaginazione ("5033 5033") mescolati al testo;
  - l'estrazione pypdf INTERCALA sezioni (risultati dentro la giustizia
    sportiva), quindi niente parsing gerarchico: si classifica RIGA PER RIGA
    con una macchina a stati tollerante.

Regex, zero LLM: il formato è ripetitivo e un errore qui deve essere
riproducibile, non probabilistico. Codice puro + CUStore (SQLite).

Test: PYTHONIOENCODING=utf-8 python -m unittest tests.test_cu_parser -v
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("data/ob1.db")

# Oltre questa età di una squalifica a giornate la consideriamo scontata: il CU
# dice "due gare effettive" ma non quali gare siano state giocate, e a tre
# settimane di distanza tenerla in lista produce falsi positivi. Vedi
# CUStore.squalificati().
GARE_WINDOW_DAYS = 21

# --- riconoscitori di riga (dal formato reale) -----------------------------

RE_META = re.compile(r"COMUNICATO\s+UFFICIALE\s+N\.?\s*(\d+)\s+DEL\s+([\d/\s.]+\d)", re.I)
RE_GARE_DEL = re.compile(r"GARE\s+DEL\s+([\d/\s]+\d)", re.I)
RE_GIRONE = re.compile(r"^GIRONE\s+([A-Z0-9]+)\s*-\s*(\d+)\s*Giornata", re.I)

# "CASTENASO CALCIO - NOCETO 5 - 6 dcr" / "TERRE DI CASTELLI 1907 - SAVIGNANESE 4 - 3"
RE_RESULT = re.compile(r"^(.{2,60}?)\s+-\s+(.{2,60}?)\s+(\d{1,2})\s*-\s*(\d{1,2})\s*(dcr|dts)?\s*$")

RE_ROLE = re.compile(r"^(CALCIATORI|DIRIGENTI|ALLENATORI|MASSAGGIATORI|ASSISTENTI)\b")

# Sanzioni, dalle più specifiche: l'ordine conta.
RE_SQUAL_DATE = re.compile(r"SQUALIFICA\s+FINO\s+AL\s+([\d/\s]+\d)", re.I)
RE_SQUAL_GARE = re.compile(r"SQUALIFICA\s+PER\s+(\w+)\s+GAR[AE]", re.I)
RE_AMMON = re.compile(r"^(I{1,4}|IV|V)\s+AMMONIZIONE\s*(\(?DIFFIDA\)?)?", re.I)
RE_AMMENDA = re.compile(r"^AMMENDA\b", re.I)

# "COGNOME NOME (SOCIETA')" — nomi in maiuscolo, anche due per riga.
RE_PERSON = re.compile(
    r"\b([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'’.\- ]{1,40}?)\s*\(([^)]{2,40})\)")

RE_PAGE_ARTIFACT = re.compile(r"^\s*\d{1,5}\s+\d{1,5}\s*$")

# Categorie/campionati che aprono un blocco.
RE_CATEGORY = re.compile(
    r"\b(ECCELLENZA|PROMOZIONE|PRIMA\s+CATEGORIA|SECONDA\s+CATEGORIA|"
    r"TERZA\s+CATEGORIA|UNDER\s+\d+|JUNIORES|COPPA\s+ITALIA)\b")


def _clean_date(raw: str) -> str:
    """'11/ 4/2026' -> '2026-04-11'. Le date del CU hanno spazi interni."""
    parts = re.split(r"[/.]", re.sub(r"\s+", "", raw or ""))
    if len(parts) == 3:
        d, m, y = parts
        if len(y) == 2:
            y = "20" + y
        try:
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except ValueError:
            pass
    return (raw or "").strip()


def _mostly_upper(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) > 0.8


def parse_cu_text(text: str) -> dict:
    """
    Macchina a stati riga-per-riga. Ritorna:
      {"meta": {...}, "results": [...], "sanctions": [...]}
    Ogni sanzione: category, match_date, role, kind, detail, person, club, reason.
    """
    meta = {"cu_number": None, "cu_date": None}
    m = RE_META.search(text or "")
    if m:
        meta["cu_number"] = int(m.group(1))
        meta["cu_date"] = _clean_date(m.group(2))

    results, sanctions = [], []
    category = match_date = girone = giornata = None
    role = kind = detail = None

    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or RE_PAGE_ARTIFACT.match(line):
            continue

        g = RE_GARE_DEL.search(line)
        if g:
            match_date = _clean_date(g.group(1))
            continue

        c = RE_CATEGORY.search(line)
        if c and _mostly_upper(line) and not RE_RESULT.match(line):
            category = c.group(1).upper().replace("  ", " ")

        gi = RE_GIRONE.match(line)
        if gi:
            girone, giornata = gi.group(1), int(gi.group(2))
            continue

        r = RE_RESULT.match(line)
        if r and not RE_PERSON.search(line):
            results.append({
                "category": category, "match_date": match_date,
                "girone": girone, "giornata": giornata,
                "home": r.group(1).strip(), "away": r.group(2).strip(),
                "home_goals": int(r.group(3)), "away_goals": int(r.group(4)),
                "note": (r.group(5) or "").strip() or None,
            })
            continue

        ro = RE_ROLE.match(line)
        if ro:
            role, kind, detail = ro.group(1).upper(), None, None
            continue

        sd = RE_SQUAL_DATE.search(line)
        if sd:
            kind, detail = "SQUALIFICA_FINO_AL", _clean_date(sd.group(1))
            continue
        sg = RE_SQUAL_GARE.search(line)
        if sg:
            kind, detail = "SQUALIFICA_GARE", sg.group(1).upper()
            continue
        am = RE_AMMON.match(line)
        if am:
            kind = "AMMONIZIONE"
            detail = am.group(1).upper() + ("_DIFFIDA" if am.group(2) else "")
            continue
        if RE_AMMENDA.match(line):
            kind, detail = "AMMENDA", None
            continue

        # Tesserati: solo dentro una sanzione attiva e su righe in maiuscolo —
        # così "Per gravi proteste nei confronti dell'Arbitro (art. 36)" non
        # diventa un giocatore di nome "Arbitro".
        if kind and _mostly_upper(line):
            people = RE_PERSON.findall(line)
            if people:
                for person, club in people:
                    sanctions.append({
                        "category": category, "match_date": match_date,
                        "role": role, "kind": kind, "detail": detail,
                        "person": person.strip(), "club": club.strip(),
                        "reason": None,
                    })
                continue

        # Riga di motivazione (prosa mista) dopo una squalifica: si attacca
        # all'ultima sanzione, non se ne crea una nuova.
        if (sanctions and kind and kind.startswith("SQUALIFICA")
                and not _mostly_upper(line) and len(line) > 20):
            prev = sanctions[-1]
            prev["reason"] = ((prev["reason"] + " ") if prev["reason"] else "") + line

    return {"meta": meta, "results": results, "sanctions": sanctions}


# --------------------------------------------------------------------- store

class CUStore:
    """
    Accumulo dei fatti estratti dai CU in data/ob1.db (stesso file del
    seen-store: un solo artefatto da trasportare tra le run).

    Il dedup è nel vincolo UNIQUE, non nella logica: ri-ingerire lo stesso CU
    non duplica niente — requisito per poter rilanciare l'ingestion senza paura.
    """

    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            # I campi che entrano nella chiave di dedup sono NOT NULL DEFAULT '':
            # SQLite non ammette espressioni (IFNULL) dentro UNIQUE, e due NULL
            # non collidono mai fra loro — il vincolo non dedupplicherebbe.
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS cu_sanctions (
                    cu_number INTEGER, cu_date TEXT, category TEXT,
                    match_date TEXT NOT NULL DEFAULT '', role TEXT,
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    person TEXT NOT NULL, club TEXT NOT NULL,
                    reason TEXT,
                    UNIQUE(cu_number, person, club, kind, detail, match_date)
                )""")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS cu_results (
                    cu_number INTEGER, cu_date TEXT, category TEXT,
                    match_date TEXT NOT NULL DEFAULT '',
                    girone TEXT NOT NULL DEFAULT '', giornata INTEGER,
                    home TEXT NOT NULL, away TEXT NOT NULL,
                    home_goals INTEGER, away_goals INTEGER, note TEXT,
                    UNIQUE(home, away, match_date, girone)
                )""")

    def ingest(self, parsed: dict) -> dict:
        meta = parsed["meta"]
        new_s = new_r = 0
        with self.conn:
            for s in parsed["sanctions"]:
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO cu_sanctions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (meta["cu_number"], meta["cu_date"], s["category"],
                     s["match_date"] or "", s["role"], s["kind"],
                     s["detail"] or "", s["person"], s["club"], s["reason"]))
                new_s += cur.rowcount
            for r in parsed["results"]:
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO cu_results VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (meta["cu_number"], meta["cu_date"], r["category"],
                     r["match_date"] or "", r["girone"] or "", r["giornata"],
                     r["home"], r["away"], r["home_goals"], r["away_goals"],
                     r["note"]))
                new_r += cur.rowcount
        return {"new_sanctions": new_s, "new_results": new_r}

    def squalificati(self, on_date: str, club: str = None) -> list:
        """
        Chi non può giocare alla data data: per il brief del giovedì.

        Due tipi di squalifica, con due livelli di certezza diversi, e il
        brief deve dirlo perché il DS possa fidarsi in modo calibrato:

        - SQUALIFICA_FINO_AL porta una data: sappiamo con certezza se è
          ancora in corso, basta confrontarla.
        - SQUALIFICA_GARE conta giornate, e il CU non dice quali gare siano
          state effettivamente giocate. Non possiamo saperlo con certezza,
          quindi la teniamo solo se irrogata negli ultimi GARE_WINDOW_DAYS:
          oltre quella finestra una squalifica di una o due giornate è quasi
          sempre già scontata, e mostrarla renderebbe il brief rumoroso.
          Il campo 'certezza' porta la distinzione fino al messaggio.
        """
        args = [on_date, on_date, str(GARE_WINDOW_DAYS)]
        q = ("SELECT person, club, kind, detail, reason, match_date, cu_number, role, "
             "  CASE WHEN kind='SQUALIFICA_FINO_AL' THEN 'certa' ELSE 'stimata' END "
             "  AS certezza "
             "FROM cu_sanctions WHERE ("
             "  (kind='SQUALIFICA_FINO_AL' AND detail >= ?) OR "
             "  (kind='SQUALIFICA_GARE' AND match_date != '' "
             "     AND julianday(?) - julianday(match_date) <= CAST(? AS INTEGER))) ")
        if club:
            q += "AND club = ? "
            args.append(club)
        q += "ORDER BY club, person"
        return [dict(r) for r in self.conn.execute(q, args)]

    def diffidati(self, club: str = None) -> list:
        """
        Chi salta la prossima al primo cartellino. È l'informazione che il DS
        non ha da nessun'altra parte e che cambia una scelta di formazione.

        Vale solo l'ULTIMO provvedimento di un tesserato: chi è stato diffidato
        e poi squalificato ha già scontato la diffida, e continuare a
        elencarlo sarebbe un falso positivo — quello che distrugge la fiducia
        in un alert automatico.
        """
        q = ("SELECT person, club, detail, match_date, cu_number FROM ("
             "  SELECT *, ROW_NUMBER() OVER ("
             "    PARTITION BY person, club ORDER BY match_date DESC, cu_number DESC"
             "  ) AS rn FROM cu_sanctions"
             "  WHERE role='CALCIATORI' OR role IS NULL"
             ") WHERE rn = 1 AND kind='AMMONIZIONE' AND detail LIKE '%DIFFIDA' ")
        args = []
        if club:
            q += "AND club = ? "
            args.append(club)
        q += "ORDER BY club, person"
        return [dict(r) for r in self.conn.execute(q, args)]

    def clubs(self) -> list:
        """Società viste nei CU ingeriti — per validare un nome digitato a mano."""
        return [r[0] for r in self.conn.execute(
            "SELECT DISTINCT club FROM cu_sanctions ORDER BY club")]

    def presence_index(self, club: str = None) -> list:
        """
        Provvedimenti accumulati per tesserato: un ammonito era in campo.
        Non è il tabellino — è il segnale sistematico che il tabellino
        pubblico, a questo livello, non esiste (ARCH-003 §3).
        """
        q = ("SELECT person, club, COUNT(*) AS provvedimenti, "
             "COUNT(DISTINCT match_date) AS giornate_distinte "
             "FROM cu_sanctions WHERE role IS NULL OR role='CALCIATORI' ")
        args = []
        if club:
            q += "AND club = ? "
            args.append(club)
        q += "GROUP BY person, club ORDER BY giornate_distinte DESC, provvedimenti DESC"
        return [dict(r) for r in self.conn.execute(q, args)]

    # --------------------------------------------------------- persistenza
    # Il database sta nel .gitignore, e giustamente: è un contenitore, si
    # rigenera. I FATTI estratti no — sono la memoria disciplinare di una
    # stagione, e se si perdono la lista dei diffidati torna a valere solo per
    # l'ultimo comunicato letto, cioè diventa sbagliata senza sembrarlo.
    # Quindi si versiona il JSON, non il .db: si legge in un diff, comprime
    # bene in git, e non dipende dalla versione di SQLite che lo ha scritto.

    def export_facts(self, path: Path | str) -> dict:
        import json

        data = {
            "_meta": {
                "purpose": ("Fatti estratti dai Comunicati Ufficiali LND. "
                            "Rigenerabile con scripts/brief_giovedi.py; "
                            "versionato perché e' memoria, non cache."),
                "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            "sanctions": [dict(r) for r in self.conn.execute(
                "SELECT * FROM cu_sanctions ORDER BY cu_number, club, person")],
            "results": [dict(r) for r in self.conn.execute(
                "SELECT * FROM cu_results ORDER BY cu_number, match_date, home")],
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8")
        return {"sanctions": len(data["sanctions"]), "results": len(data["results"])}

    def import_facts(self, path: Path | str) -> dict:
        """Ricostruisce il db dai fatti versionati. Idempotente come l'ingest."""
        import json

        p = Path(path)
        if not p.exists():
            return {"sanctions": 0, "results": 0}
        data = json.loads(p.read_text(encoding="utf-8"))
        cols_s = ("cu_number", "cu_date", "category", "match_date", "role",
                  "kind", "detail", "person", "club", "reason")
        cols_r = ("cu_number", "cu_date", "category", "match_date", "girone",
                  "giornata", "home", "away", "home_goals", "away_goals", "note")
        n_s = n_r = 0
        with self.conn:
            for row in data.get("sanctions", []):
                n_s += self.conn.execute(
                    f"INSERT OR IGNORE INTO cu_sanctions VALUES ({','.join('?' * 10)})",
                    tuple(row.get(c) for c in cols_s)).rowcount
            for row in data.get("results", []):
                n_r += self.conn.execute(
                    f"INSERT OR IGNORE INTO cu_results VALUES ({','.join('?' * 11)})",
                    tuple(row.get(c) for c in cols_r)).rowcount
        return {"sanctions": n_s, "results": n_r}

    def close(self):
        self.conn.close()


# ----------------------------------------------------------------------- cli

def read_pdf(source: str) -> str:
    """Testo di un CU da percorso locale o URL. I CU LND sono PDF con testo
    nativo: niente OCR, niente dipendenze pesanti."""
    import pypdf

    if source.startswith(("http://", "https://")):
        import io
        import urllib.request
        req = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            handle = io.BytesIO(r.read())
    else:
        handle = source
    return "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(handle).pages)


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Ingest di un Comunicato Ufficiale LND")
    ap.add_argument("source", help="percorso o URL del PDF")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--dry-run", action="store_true", help="stampa e basta")
    args = ap.parse_args()

    parsed = parse_cu_text(read_pdf(args.source))
    meta = parsed["meta"]
    print(f"CU {meta['cu_number']} del {meta['cu_date']}: "
          f"{len(parsed['results'])} risultati, {len(parsed['sanctions'])} sanzioni")
    for s in parsed["sanctions"]:
        print(f"  {(s['role'] or '-'):12} {s['kind']:18} {(s['detail'] or '-'):12} "
              f"{s['person']} ({s['club']})")
    if not args.dry_run:
        store = CUStore(args.db)
        print(f"\nnuovi fatti: {store.ingest(parsed)}")
        store.close()


if __name__ == "__main__":
    main()
