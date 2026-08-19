#!/usr/bin/env python3
"""
Estrae un campione REALE da data/opportunities.json per testare un altro LLM
sulla data quality.

Regole, in ordine di importanza:

1. **Non si pulisce niente.** Null, valori assurdi e incoerenze restano come
   sono nel dataset: sono l'oggetto del test, non un difetto da nascondere.
2. **Non si inventa niente.** Campo assente nel sorgente = `null`.
3. **I nomi di persone reali sono anonimizzati** (`Player_001`, …). Restano
   invece testuali le stringhe che NON sono persone ("Comunicato Ufficiale",
   "Toro News"): sono spazzatura entrata dal gate, cioè proprio l'anomalia da
   far riconoscere, e anonimizzarle distruggerebbe il caso di test. L'`id`
   originale è preservato, quindi la tracciabilità interna resta.
4. **Il timestamp è quello genuino di scoperta** (`discovered_at`, uno per
   record, 751 valori distinti al microsecondo: non è un bulk seed). Viene
   copiato così com'è, naive — l'assenza di fuso è essa stessa un segnale.

Uso: python scripts/export_qa_sample.py [--out test_qwen_dataset.json]
"""

import argparse
import json
import re
from pathlib import Path

SOURCE = Path("data/opportunities.json")

# Nomi che non sono persone: restano in chiaro, sono il caso di test.
NOT_A_PERSON = re.compile(
    r"comunicato|ufficiale|news|la serie|six under|classifica|top \d+|girone", re.I)

# Selezione fissa: id reali scelti a mano per coprire i quattro reparti e
# portarsi dentro le anomalie vere trovate nel dataset (vedi --explain).
# Le anomalie NON hanno vincolo di ruolo: nel dataset reale i record incoerenti
# sono quasi sempre anche privi di ruolo, e forzare "un difensore con i minuti
# impossibili" significherebbe fabbricare un caso che non esiste.
SELECTION = [
    # --- copertura dei reparti, record senza incoerenze note
    ("POR", "regolare"), ("POR", "regolare"), ("POR", "regolare"),
    ("DIF", "regolare"), ("DIF", "regolare"), ("DIF", "regolare"),
    ("CC", "regolare"), ("CC", "regolare"), ("CC", "regolare"),
    ("ATT", "regolare"), ("ATT", "regolare"),
    # --- anomalie vere, prese dove stanno
    (None, "minuti_impossibili"),   # minuti > presenze x 90
    (None, "eta_fuori_range"),      # radar U23, record con 40+
    (None, "eta_incoerente"),       # age non torna con birth_date
    (None, "non_e_una_persona"),    # spazzatura passata dal gate
]


def macro_role(opp: dict):
    r = (opp.get("role_name") or opp.get("role") or "").lower()
    if any(k in r for k in ("portiere", "goalkeeper", "gk")):
        return "POR"
    if any(k in r for k in ("difensore", "terzino", "centre-back", "back")):
        return "DIF"
    if any(k in r for k in ("centrocampista", "mediano", "midfield", "trequartista")):
        return "CC"
    if any(k in r for k in ("attaccante", "punta", "ala", "winger", "forward", "striker")):
        return "ATT"
    return None


def anomalies(opp: dict) -> list:
    """Etichette delle incoerenze REALI presenti nel record."""
    out = []
    name = opp.get("player_name") or ""
    if NOT_A_PERSON.search(name) or len(name.split()) < 2:
        out.append("non_e_una_persona")
    age, birth = opp.get("age"), opp.get("birth_date")
    if isinstance(age, int) and not (15 <= age <= 42):
        out.append("eta_fuori_range")
    if isinstance(age, int) and birth:
        try:
            if abs((2026 - int(str(birth)[:4])) - age) > 1:
                out.append("eta_incoerente")
        except ValueError:
            pass
    apps, mins, goals = opp.get("appearances"), opp.get("minutes_played"), opp.get("goals")
    if isinstance(apps, int) and isinstance(mins, int) and mins > apps * 90 + 30:
        out.append("minuti_impossibili")
    if isinstance(apps, int) and isinstance(goals, int) and goals > apps:
        out.append("gol_oltre_presenze")
    mv = opp.get("market_value")
    if isinstance(mv, (int, float)) and mv > 5_000_000:
        out.append("valore_sospetto")
    return out


def to_record(opp: dict, alias: str) -> dict:
    """Schema richiesto. Campo assente nel sorgente -> null, mai inventato."""
    return {
        "id": opp["id"],
        "nome": alias,
        "eta": opp.get("age") if isinstance(opp.get("age"), int) else None,
        "ruolo": opp.get("role_name") or opp.get("role") or None,
        "lega": opp.get("league_id") or None,
        "stats_grezze": {
            "presenze": opp.get("appearances"),
            "gol": opp.get("goals"),
            "assist": opp.get("assists"),
            "minuti": opp.get("minutes_played"),
        },
        "first_seen_timestamp": opp.get("discovered_at"),
    }


def pick(data: list) -> list:
    """Un record per riga di SELECTION, senza ripetere lo stesso id."""
    used, chosen = set(), []
    completeness = lambda o: sum(
        1 for k in ("appearances", "goals", "assists", "minutes_played", "age")
        if o.get(k) not in (None, ""))

    for want_role, want_kind in SELECTION:
        pool = [o for o in data if o["id"] not in used]
        if want_role:
            pool = [o for o in pool if macro_role(o) == want_role]
        if want_kind == "regolare":
            pool = [o for o in pool if not anomalies(o)]
            pool.sort(key=lambda o: (-completeness(o), o["discovered_at"]))
        else:
            pool = [o for o in pool if want_kind in anomalies(o)]
            pool.sort(key=lambda o: (-completeness(o), o["discovered_at"]))
        if not pool:
            print(f"  [ATTENZIONE] nessun record reale per ({want_role}, {want_kind}): riga saltata")
            continue
        opp = pool[0]
        used.add(opp["id"])
        chosen.append(opp)
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="test_qwen_dataset.json")
    ap.add_argument("--explain", action="store_true",
                    help="stampa le anomalie riconosciute per ogni record scelto")
    args = ap.parse_args()

    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    chosen = pick(data)

    records, n = [], 0
    for opp in chosen:
        name = opp.get("player_name") or ""
        if NOT_A_PERSON.search(name) or len(name.split()) < 2:
            alias = name          # non è una persona: resta il caso di test
        else:
            n += 1
            alias = f"Player_{n:03d}"
        records.append(to_record(opp, alias))
        if args.explain:
            print(f"  {alias:24} {macro_role(opp) or '-':4} "
                  f"anomalie={anomalies(opp) or ['-']}")

    Path(args.out).write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(records)} record -> {args.out}")
    return records


if __name__ == "__main__":
    main()
