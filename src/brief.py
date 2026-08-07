#!/usr/bin/env python3
"""
ARCH-003 — Il brief del giovedì: cosa il DS deve sapere prima di scegliere.

Il giovedì è il giorno in cui si decide la formazione. Le informazioni che
servono in quel momento sono tre, e a questo livello nessuna arriva da sola:

  - chi NON puoi schierare (squalificati);
  - chi salta la prossima al primo cartellino (diffidati) — l'informazione
    che cambia una scelta e che oggi il DS ricostruisce a mano leggendo i
    comunicati settimana per settimana;
  - la stessa cosa per l'avversario, che è vantaggio competitivo puro.

Tutto esce dai Comunicati Ufficiali già ingeriti (src/cu_parser.py): nessuna
chiamata di rete qui dentro, nessun LLM, nessun costo.

Due scelte di prodotto che stanno nel codice, non nella documentazione:

1. **La certezza è visibile.** Una squalifica a data certa e una a giornate
   non valgono uguale (vedi CUStore.squalificati). Il messaggio le distingue
   con un segno, invece di appiattirle in un elenco che sembra tutto certo.
2. **Il silenzio è un messaggio.** Se non c'è nulla da segnalare il brief lo
   dice in una riga invece di non partire: "nessuna squalifica" è
   un'informazione che il DS altrimenti va a cercarsi.

Test: PYTHONIOENCODING=utf-8 python -m unittest tests.test_brief -v
"""

from __future__ import annotations

import html
from datetime import datetime

# Telegram tronca a 4096; il notifier splitta, ma un brief che va in due
# messaggi ha già fallito il suo scopo (si legge in piedi, sul telefono).
DIFFIDATI_INLINE = 12


def _nice(name: str) -> str:
    """'PELLEGRI FILIPPO' -> 'Pellegri Filippo'. I CU sono tutti maiuscoli."""
    return " ".join(w.capitalize() if w.isupper() else w
                    for w in (name or "").split())


def _nice_club(club: str) -> str:
    """Come _nice, ma le sigle societarie restano maiuscole: SSD, ARL, FC."""
    keep = {"SSD", "ARL", "FC", "AC", "US", "ASD", "SSDARL", "SRL", "S.S.D.", "A.S.D."}
    return " ".join(w if w in keep else _nice(w) for w in (club or "").split())


def _it_date(iso: str) -> str:
    """'2026-05-18' -> '18/05'. Il DS ragiona in giorno/mese."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return d.strftime("%d/%m")
    except (ValueError, TypeError):
        return iso or "?"


# Chi non è un calciatore va marcato: "Ranieri squalificato" in un elenco di
# giocatori fa perdere un allenatore in panchina senza che nessuno se ne accorga.
ROLE_TAGS = {"ALLENATORI": " (all.)", "DIRIGENTI": " (dir.)",
             "MASSAGGIATORI": " (mass.)", "ASSISTENTI": " (assist.)"}


def _role_tag(row: dict) -> str:
    return ROLE_TAGS.get(row.get("role") or "", "")


def _sanction_label(row: dict) -> str:
    if row["kind"] == "SQUALIFICA_FINO_AL":
        return f"fino al {_it_date(row['detail'])}"
    gare = (row.get("detail") or "").lower()
    return f"{gare} giornata" if gare == "una" else f"{gare} giornate"


def squad_status(store, club: str, on_date: str) -> dict:
    """Stato disciplinare di una rosa alla data del brief."""
    return {
        "club": club,
        "out": store.squalificati(on_date, club=club),
        "at_risk": store.diffidati(club=club),
    }


def build_brief(store, on_date: str, club: str, opponent: str = None) -> dict:
    """
    Dati del brief. Separato dal formato di proposito: lo stesso brief deve
    poter uscire su Telegram oggi e in PDF domani senza riscrivere le regole.
    """
    brief = {
        "on_date": on_date,
        "squad": squad_status(store, club, on_date),
        "opponent": squad_status(store, opponent, on_date) if opponent else None,
        "source": None,
    }
    rows = store.conn.execute(
        "SELECT cu_number, cu_date FROM cu_sanctions "
        "WHERE cu_number IS NOT NULL ORDER BY cu_date DESC, cu_number DESC LIMIT 1"
    ).fetchone()
    if rows:
        brief["source"] = {"cu_number": rows[0], "cu_date": rows[1]}
    s = brief["squad"]
    brief["has_content"] = bool(s["out"] or s["at_risk"])
    return brief


def _section(title: str, status: dict, is_opponent: bool = False) -> list:
    lines = [title]
    out, risk = status["out"], status["at_risk"]

    if out:
        lines.append(f"\n⛔ <b>Non disponibili</b> ({len(out)})")
        for r in out:
            mark = "" if r["certezza"] == "certa" else " ·"
            lines.append(f"• {html.escape(_nice(r['person']))}{_role_tag(r)} — "
                         f"{_sanction_label(r)}{mark}")
    else:
        lines.append("\n✅ <b>Nessuna squalifica</b>")

    if risk and not is_opponent:
        names = [_nice(r["person"]) for r in risk]
        shown = names[:DIFFIDATI_INLINE]
        more = len(names) - len(shown)
        lines.append(f"\n⚠️ <b>In diffida</b> ({len(names)}) — "
                     f"saltano la prossima al primo cartellino")
        lines.append(html.escape(", ".join(shown)) + (f" +{more} altri" if more else ""))
    elif risk and is_opponent:
        lines.append(f"\n⚠️ In diffida: {len(risk)}")

    return lines


def format_telegram(brief: dict) -> str:
    """Messaggio HTML per TelegramNotifier.send_message(parse_mode='HTML')."""
    squad = brief["squad"]
    lines = [f"📋 <b>Brief del giovedì</b> · {_it_date(brief['on_date'])}",
             f"<b>{html.escape(_nice_club(squad['club']))}</b>"]

    lines += _section("", squad)

    if brief.get("opponent"):
        opp = brief["opponent"]
        lines.append(f"\n───────\n🆚 <b>{html.escape(_nice_club(opp['club']))}</b>")
        lines += _section("", opp, is_opponent=True)

    src = brief.get("source")
    if src:
        lines.append(f"\n<i>Fonte: Comunicato Ufficiale n.{src['cu_number']} "
                     f"del {_it_date(src['cu_date'])}</i>")

    # La legenda deve seguire il marcatore ovunque compaia, avversario incluso:
    # un simbolo senza spiegazione è peggio che non metterlo.
    shown = list(squad["out"]) + list((brief.get("opponent") or {}).get("out", []))
    if any(r["certezza"] != "certa" for r in shown):
        lines.append("<i>· squalifica a giornate: verifica se già scontata</i>")

    return "\n".join(l for l in lines if l != "")
