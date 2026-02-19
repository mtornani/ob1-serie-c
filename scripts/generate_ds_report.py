#!/usr/bin/env python3
"""
OB1 Scout - Report DS-Ready (PDF)

Genera un PDF settimanale con i top 5 giocatori per ob1_score,
pensato per essere girato via WhatsApp ai Direttori Sportivi.

Input:  docs/data.json (con ob1_score e classification)
Output: docs/reports/ds_report_YYYY-MM-DD.pdf

Stile: professionale, austero, bianco/nero/grigio con accenti rossi.
"""

import json
import sys
from datetime import datetime, date
from pathlib import Path

from fpdf import FPDF

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "docs" / "data.json"
REPORTS_DIR = BASE_DIR / "docs" / "reports"

# --- Costanti stile ---
BLACK = (0, 0, 0)
DARK_GRAY = (51, 51, 51)
MID_GRAY = (120, 120, 120)
LIGHT_GRAY = (200, 200, 200)
BG_GRAY = (245, 245, 245)
RED = (192, 57, 43)
ORANGE = (230, 126, 34)
AMBER = (211, 172, 43)
WHITE = (255, 255, 255)

BADGE_COLORS = {
    "svincolato": RED,
    "rescissione": RED,
    "prestito": ORANGE,
    "in_scadenza": AMBER,
}
BADGE_LABELS = {
    "svincolato": "SVINCOLATO",
    "rescissione": "RESCISSIONE",
    "prestito": "PRESTITO",
    "in_scadenza": "IN SCADENZA",
}

MESI_IT = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre",
}


def data_italiana(d: date) -> str:
    return f"{d.day} {MESI_IT[d.month]} {d.year}"


def load_opportunities() -> list:
    if not DATA_FILE.exists():
        print(f"❌ File non trovato: {DATA_FILE}")
        sys.exit(1)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "opportunities" in data:
        return data["opportunities"]
    return data if isinstance(data, list) else []


def _days_since_discovery(player: dict) -> int | None:
    """Calcola giorni da discovered_at. None se non disponibile."""
    discovered_at = player.get("discovered_at", "")
    if not discovered_at:
        return None
    try:
        disc_date = datetime.fromisoformat(discovered_at.replace("Z", "+00:00"))
        return (datetime.now() - disc_date.replace(tzinfo=None)).days
    except (ValueError, TypeError):
        return None


def _is_enriched(player: dict) -> bool:
    """Un profilo e' considerato completo se ha summary >= 100 char e ruolo specificato."""
    role_name = (player.get("role_name") or "").strip().lower()
    if not role_name or role_name == "non specificato":
        return False
    summary = player.get("summary", "") or ""
    if len(summary) < 100:
        return False
    return True


def select_ds_players(opportunities: list, n: int = 5) -> tuple[list, int]:
    """Seleziona i migliori giocatori per il report DS-Ready.

    Pipeline:
    1. Escludi score < 70 (COLD)
    2. Escludi discovered_at > 14 giorni
    3. Escludi ruolo nullo / "Non Specificato"
    4. Escludi profili incompleti (summary < 100 char)
    5. Penalizza 7-14 giorni (score effettivo -10)
    6. Max 2 giocatori per club di destinazione
    7. Risultato variabile: 1-5 giocatori

    Returns:
        (selected_players, enrichment_pending_count)
    """
    enrichment_pending = 0
    candidates = []
    for p in opportunities:
        score = p.get("ob1_score", 0)
        if score < 70:
            continue

        days = _days_since_discovery(p)
        if days is not None and days > 14:
            continue

        # Escludi ruolo mancante o generico
        role_name = (p.get("role_name") or "").strip().lower()
        if not role_name or role_name == "non specificato":
            enrichment_pending += 1
            continue

        # Escludi profili con summary troppo corta
        summary = p.get("summary", "") or ""
        if len(summary) < 100:
            enrichment_pending += 1
            continue

        # Score effettivo: penalizza 7-14 giorni
        effective_score = score
        if days is not None and days > 7:
            effective_score = score - 10

        candidates.append((effective_score, score, p))

    # Sort per score effettivo desc, poi score reale desc come tiebreaker
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)

    # Diversificazione: max 2 per club
    selected = []
    club_count: dict[str, int] = {}
    for _eff, _score, player in candidates:
        club = (player.get("current_club") or "").strip().lower()
        if club and club_count.get(club, 0) >= 2:
            continue
        selected.append(player)
        if club:
            club_count[club] = club_count.get(club, 0) + 1
        if len(selected) >= n:
            break

    return selected, enrichment_pending


class DSReport(FPDF):
    """PDF report DS-Ready. Una cover + una pagina per giocatore."""

    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=False)
        # fpdf2 ha Helvetica built-in (alias di Arial)
        self.report_date = date.today()

    # -- Nessun header/footer automatico, gestiamo tutto a mano --
    def header(self):
        pass

    def footer(self):
        pass

    def _footer_line(self, page_num: int, total: int):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 5, f"Pagina {page_num}/{total}", align="C")

    # ================================================================
    # COVER PAGE
    # ================================================================
    def cover_page(self, players: list, all_opps: list, enrichment_pending: int = 0):
        self.add_page()

        # Top bar
        self.set_fill_color(*DARK_GRAY)
        self.rect(0, 0, 210, 60, "F")

        self.set_y(18)
        self.set_font("Helvetica", "B", 28)
        self.set_text_color(*WHITE)
        self.cell(0, 12, "OB1 Scout", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 13)
        self.cell(0, 8, "Report Settimanale", align="C", new_x="LMARGIN", new_y="NEXT")

        # Data
        self.set_y(68)
        self.set_font("Helvetica", "", 12)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 8, data_italiana(self.report_date), align="C", new_x="LMARGIN", new_y="NEXT")

        # Linea separatrice
        self.set_y(82)
        self.set_draw_color(*LIGHT_GRAY)
        self.line(30, 82, 180, 82)

        # Box: opportunita' segnalate
        self.set_y(92)
        self.set_font("Helvetica", "B", 48)
        self.set_text_color(*RED)
        self.cell(0, 20, str(len(players)), align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 12)
        self.set_text_color(*DARK_GRAY)
        self.cell(0, 8, "opportunita' segnalate", align="C", new_x="LMARGIN", new_y="NEXT")

        # Classificazione HOT/WARM/COLD (soglie DS-Ready)
        hot = len([o for o in all_opps if o.get("ob1_score", 0) >= 85])
        warm = len([o for o in all_opps if 70 <= o.get("ob1_score", 0) < 85])
        cold = len([o for o in all_opps if o.get("ob1_score", 0) < 70])

        self.set_y(135)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 6, "DATABASE COMPLETO", align="C", new_x="LMARGIN", new_y="NEXT")

        box_y = 146
        box_w = 40
        box_h = 30
        gap = 8
        start_x = (210 - 3 * box_w - 2 * gap) / 2

        for i, (label, count, color) in enumerate([
            ("HOT", hot, RED),
            ("WARM", warm, ORANGE),
            ("COLD", cold, MID_GRAY),
        ]):
            x = start_x + i * (box_w + gap)
            self.set_fill_color(*BG_GRAY)
            self.rect(x, box_y, box_w, box_h, "F")
            self.set_xy(x, box_y + 4)
            self.set_font("Helvetica", "B", 20)
            self.set_text_color(*color)
            self.cell(box_w, 10, str(count), align="C", new_x="LMARGIN", new_y="NEXT")
            self.set_xy(x, box_y + 17)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*MID_GRAY)
            self.cell(box_w, 6, label, align="C")

        # Footer note
        self.set_y(195)
        self.set_draw_color(*LIGHT_GRAY)
        self.line(30, 195, 180, 195)
        self.set_y(200)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*MID_GRAY)
        self.multi_cell(
            0, 4,
            "Questo report contiene le migliori opportunita' identificate "
            "nella settimana corrente, ordinate per priorita'.",
            align="C",
        )

        if enrichment_pending > 0:
            self.set_y(self.get_y() + 4)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*MID_GRAY)
            self.cell(
                0, 5,
                f"{enrichment_pending} profili aggiuntivi in fase di approfondimento",
                align="C",
            )

    # ================================================================
    # PLAYER PAGE
    # ================================================================
    def player_page(self, player: dict):
        self.add_page()

        name = player.get("player_name", "N/D")
        role_name = player.get("role_name", player.get("role", ""))
        age = player.get("age", "-")
        nationality = player.get("nationality", "")
        second_nat = player.get("second_nationality")
        opp_type = (player.get("opportunity_type") or "").lower()
        score = player.get("ob1_score", 0)
        classification = player.get("classification", "").upper()

        # ---- HEADER: nome, ruolo, eta', nazionalita' ----
        y = 15
        self.set_xy(15, y)
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(*BLACK)
        self.cell(0, 10, self._safe(name))

        y += 13
        self.set_xy(15, y)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*MID_GRAY)
        nat_str = nationality
        if second_nat:
            nat_str += f" / {second_nat}"
        self.cell(0, 6, self._safe(f"{role_name}  |  {age} anni  |  {nat_str}"))

        # ---- BADGE opportunity_type ----
        badge_color = BADGE_COLORS.get(opp_type, MID_GRAY)
        badge_label = BADGE_LABELS.get(opp_type, opp_type.upper() if opp_type else "")
        if badge_label:
            y += 10
            self.set_xy(15, y)
            self.set_fill_color(*badge_color)
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*WHITE)
            tw = self.get_string_width(badge_label) + 8
            self.cell(tw, 7, badge_label, fill=True)

            # Score label accanto
            self.set_x(15 + tw + 4)
            if score >= 85:
                score_color = RED
                score_text = "PRIORITA' ALTA - AZIONE IMMEDIATA"
            else:
                score_color = ORANGE
                score_text = "OPPORTUNITA' ATTIVA - FINESTRA APERTA"
            self.set_fill_color(*BG_GRAY)
            self.set_text_color(*score_color)
            self.set_font("Helvetica", "B", 9)
            sw = self.get_string_width(score_text) + 8
            self.cell(sw, 7, score_text, fill=True)

        # Linea
        y += 12
        self.set_draw_color(*LIGHT_GRAY)
        self.line(15, y, 195, y)

        # ---- SEZIONE 1: Vantaggio Temporale ----
        y += 5
        y = self._section_title(y, "VANTAGGIO TEMPORALE")

        discovered_at = player.get("discovered_at", "")
        if discovered_at:
            try:
                disc_date = datetime.fromisoformat(discovered_at.replace("Z", "+00:00"))
                days_ago = (datetime.now() - disc_date.replace(tzinfo=None)).days
            except (ValueError, TypeError):
                days_ago = None
        else:
            days_ago = None

        self.set_xy(15, y)
        self.set_font("Helvetica", "", 10)
        if days_ago is not None:
            if days_ago < 1:
                self.set_text_color(*RED)
                self.set_font("Helvetica", "B", 11)
                self.cell(0, 6, "ALERT: PRIMO CONTATTO POSSIBILE", new_x="LMARGIN", new_y="NEXT")
            elif days_ago < 7:
                self.set_text_color(*RED)
                self.set_font("Helvetica", "B", 11)
                self.cell(0, 6, f"SEGNALATO {days_ago} GIORNI FA - FINESTRA APERTA", new_x="LMARGIN", new_y="NEXT")
            else:
                self.set_text_color(*DARK_GRAY)
                self.cell(0, 6, f"Segnalato {days_ago} giorni fa", new_x="LMARGIN", new_y="NEXT")
        else:
            self.set_text_color(*MID_GRAY)
            self.cell(0, 6, "Data segnalazione non disponibile", new_x="LMARGIN", new_y="NEXT")

        y = self.get_y() + 4

        # ---- SEZIONE 2: Profilo ----
        y = self._section_title(y, "PROFILO")

        fields = []
        current_club = player.get("current_club", "")
        if current_club:
            fields.append(("Club attuale", current_club))

        prev = player.get("previous_clubs")
        if prev and isinstance(prev, list):
            non_svin = [c for c in prev if c.lower() != "svincolato"]
            if non_svin:
                fields.append(("Club precedenti", ", ".join(non_svin)))

        mv = player.get("market_value_formatted", "")
        if mv:
            fields.append(("Valore di mercato", mv))

        contract = player.get("contract_expires") or player.get("reported_date", "")
        if contract and opp_type not in ("svincolato", "rescissione"):
            fields.append(("Scadenza contratto", contract))

        foot = player.get("foot", "")
        if foot:
            fields.append(("Piede", foot.capitalize()))

        height = player.get("height_cm")
        if height:
            fields.append(("Altezza", f"{height} cm"))

        minutes = player.get("minutes_played", 0)
        apps = player.get("appearances", 0)
        goals = player.get("goals", 0)
        assists = player.get("assists", 0)
        stats_parts = []
        if apps:
            stats_parts.append(f"{apps} presenze")
        if minutes:
            stats_parts.append(f"{minutes} min")
        if goals:
            stats_parts.append(f"{goals} gol")
        if assists:
            stats_parts.append(f"{assists} assist")
        if stats_parts:
            fields.append(("Stagione 25/26", " | ".join(stats_parts)))

        for label, value in fields:
            self.set_xy(15, y)
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*MID_GRAY)
            self.cell(48, 6, label.upper())
            self.set_font("Helvetica", "", 10)
            self.set_text_color(*DARK_GRAY)
            self.cell(0, 6, self._safe(str(value)))
            y += 7

        # Highlight: svincolato + valore > €50k
        market_value = player.get("market_value", 0) or 0
        if opp_type in ("svincolato", "rescissione") and market_value > 50000:
            y += 3
            self.set_xy(15, y)
            self.set_fill_color(255, 235, 235)
            self.set_font("Helvetica", "B", 10)
            self.set_text_color(*RED)
            highlight = self._safe(f"VALORE RESIDUO ALTO ({mv}) - COSTO ZERO")
            hw = self.get_string_width(highlight) + 10
            self.cell(hw, 8, highlight, fill=True)
            y += 12
        else:
            y += 4

        # ---- SEZIONE 3: Summary ----
        y = self._section_title(y, "ANALISI")

        summary = player.get("summary", "")
        self.set_xy(15, y)
        if summary and len(summary) >= 100:
            self.set_font("Helvetica", "", 10)
            self.set_text_color(*DARK_GRAY)
            self.multi_cell(180, 5, self._safe(summary))
        else:
            self.set_font("Helvetica", "I", 10)
            self.set_text_color(*MID_GRAY)
            self.cell(0, 6, "Profilo in fase di approfondimento")
        y = self.get_y() + 4

        # ---- FOOTER: Agente ----
        self.set_draw_color(*LIGHT_GRAY)
        footer_y = 265
        self.line(15, footer_y, 195, footer_y)
        self.set_xy(15, footer_y + 3)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*MID_GRAY)
        self.cell(20, 5, "AGENTE")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK_GRAY)
        agent = player.get("agent")
        if agent:
            self.cell(0, 5, self._safe(str(agent)))
        else:
            self.set_text_color(*MID_GRAY)
            self.set_font("Helvetica", "I", 10)
            self.cell(0, 5, "In fase di reperimento")

    # ---- Helpers ----
    def _section_title(self, y: float, title: str) -> float:
        self.set_xy(15, y)
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*MID_GRAY)
        self.cell(0, 5, title)
        self.set_draw_color(*LIGHT_GRAY)
        y += 5
        self.line(15, y, 80, y)
        return y + 4

    def _safe(self, text: str) -> str:
        """Gestisce caratteri problematici per il font built-in."""
        if not text:
            return ""
        replacements = {
            "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
            "\u2013": "-", "\u2014": "-", "\u2026": "...",
            "\u20ac": "EUR ",
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        # Fallback: rimuovi caratteri non-latin-1
        return text.encode("latin-1", "replace").decode("latin-1")


def main():
    print("📄 Generate DS Report (PDF)")

    report_date = date.today()
    date_str = report_date.strftime("%Y-%m-%d")

    opportunities = load_opportunities()
    if not opportunities:
        print("⚠️ Nessuna opportunita' trovata — skip")
        sys.exit(0)

    players, enrichment_pending = select_ds_players(opportunities, 5)
    print(f"   Totale opportunita': {len(opportunities)}")
    if not players:
        print("⚠️ Nessun giocatore supera i filtri DS-Ready (score>=70, freshness<=14gg, profilo completo) — skip")
        sys.exit(0)
    print(f"   Selezionati {len(players)} (score range: {players[-1].get('ob1_score', 0)}-{players[0].get('ob1_score', 0)})")
    if enrichment_pending:
        print(f"   {enrichment_pending} profili in attesa di approfondimento")

    pdf = DSReport()
    pdf.report_date = report_date
    pdf.cover_page(players, opportunities, enrichment_pending)

    for p in players:
        pdf.player_page(p)
        print(f"   + {p.get('player_name', 'N/D')} (score: {p.get('ob1_score', 0)})")

    # Aggiungi numeri di pagina
    total_pages = pdf.pages_count
    for i in range(1, total_pages + 1):
        pdf.page = i
        pdf._footer_line(i, total_pages)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORTS_DIR / f"ds_report_{date_str}.pdf"
    pdf.output(str(output_path))
    print(f"✅ PDF salvato: {output_path}")
    print(f"   Pagine: {total_pages} (1 cover + {total_pages - 1} giocatori)")


if __name__ == "__main__":
    main()
