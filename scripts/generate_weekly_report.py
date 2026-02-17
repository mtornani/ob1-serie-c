#!/usr/bin/env python3
import sys, json
from pathlib import Path
from datetime import datetime

DATA_FILE = Path("docs/data.json")
REPORTS_DIR = Path("docs/reports")

def load_data():
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "opportunities" in data:
        return data["opportunities"]
    return data if isinstance(data, list) else []

def generate_report_html(opportunities, date_str):
    hot = [o for o in opportunities if o.get("ob1_score", 0) >= 80]
    warm = [o for o in opportunities if 60 <= o.get("ob1_score", 0) < 80]
    svincolati = [o for o in opportunities if "svincolato" in (o.get("opportunity_type", "") or "").lower()]
    top_10 = sorted(opportunities, key=lambda x: x.get("ob1_score", 0), reverse=True)[:10]
    labels = {"PO": "Portiere", "DC": "Difensore", "TD": "Terzino D.", "TS": "Terzino S.", "CC": "Centrocampista", "MED": "Mediano", "TRQ": "Trequartista", "AT": "Attaccante", "PC": "Punta", "AD": "Ala D.", "AS": "Ala S.", "ED": "Esterno D.", "ES": "Esterno S."}
    
    def rlabel(code):
        return labels.get(code, code)
    
    def tlabel(ot):
        return {"svincolato": "Svincolato", "rescissione": "Rescissione", "prestito": "Prestito"}.get(ot or "", ot or "")
    
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>OB1 - Report {date_str}</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:Georgia,serif;background:#fafafa}}.container{{max-width:860px;margin:0 auto;padding:20px}}header{{background:#1a1a2e;color:white;padding:30px;border-radius:8px;margin-bottom:20px}}.market{{background:white;border-left:4px solid #1a1a2e;padding:20px;margin-bottom:20px}}.market .numbers{{display:flex;gap:30px}}.market .num .val{{font-size:1.8em}}.market .num .val.hot{{color:#c0392b}}.market .num .val.free{{color:#27ae60}}.market .num .lbl{{font-size:0.75em;color:#888}}.card{{background:white;border-radius:8px;padding:20px;margin-bottom:15px}}.card.hot{{border-left:4px solid #c0392b}}.card.warm{{border-left:4px solid #f39c12}}.name{{font-size:1.2em}}.score{{font-weight:700;padding:4px 10px;border-radius:4px}}.score.hot{{background:#fdecea;color:#c0392b}}.score.warm{{background:#fef5e7;color:#e67e22}}.tag{{font-size:0.7em;padding:2px 8px;border-radius:3px}}.tag.svin{{background:#d5f5e3;color:#1e8449}}.tag.pre{{background:#d6eaf8;color:#1a5276}}.rep{{background:white;border-radius:8px;padding:20px;margin-bottom:15px}}table{{width:100%;border-collapse:collapse}}th{{text-align:left;padding:8px;color:#888}}td{{padding:8px;border-bottom:1px solid #eee}}footer{{text-align:center;padding:20px;color:#aaa}}</style></head><body><div class="container">
<header><h1>OB1 Scout</h1><div class="date">Report Settimanale — {date_str}</div></header>
<div class="market"><h2>Polso del Mercato</h2><p>{len(svincolati)} svincolati. {len(opportunities)} profili.</p>
<div class="numbers"><div class="num"><div class="val hot">{len(hot)}</div><div class="lbl">Priorità alta</div></div><div class="num"><div class="val">{len(warm)}</div><div class="lbl">Da monitorare</div></div><div class="num"><div class="val free">{len(svincolati)}</div><div class="lbl">A costo zero</div></div></div></div>
<h2 style="text-transform:uppercase;color:#888;font-size:0.8em;margin:20px 0 15px">Segnalazioni principali</h2>
"""
    for opp in top_10:
        score = opp.get("ob1_score", 0)
        cls = "hot" if score >= 80 else "warm" if score >= 60 else "cold"
        agent_html = f'<div style="font-size:0.75em;color:#555;">👔 {opp.get("agent")}</div>' if opp.get("agent") else ""
        html += f"""<div class="card {cls}">
<div class="player-header"><div><div class="name">{opp.get("player_name", "N/D")}</div>
<div style="font-size:0.85em;color:#666;">{rlabel(opp.get("role", ""))} • {opp.get("age", "-")} anni</div>{agent_html}</div>
<span class="score {cls}">{score}</span></div>
<div><span class="tag {tlabel(opp.get("opportunity_type", "") or "")}">{tlabel(opp.get("opportunity_type", "") or "")}</span></div>
</div>"""
    
    for reparto, roles in [("Difesa", ["DC", "TD", "TS", "PO"]), ("Centrocampo", ["CC", "MED", "TRQ"]), ("Attacco", ["AT", "ATT", "PC", "AD", "AS", "ED", "ES"])]:
        players = [o for o in opportunities if o.get("role", "") in roles]
        if not players: continue
        seen = set()
        deduped = [p for p in players if not (p.get("player_name", "").lower() in seen or seen.add(p.get("player_name", "").lower()))]
        html += f"""<div class="rep"><h2>{reparto} ({len(deduped)})<table><tr><th>Giocatore</th><th>Età</th><th>Score</th><th>Status</th></tr>"""
        for p in sorted(deduped, key=lambda x: x.get("ob1_score", 0), reverse=True)[:5]:
            p_score = p.get("ob1_score", 0)
            p_cls = "hot" if p_score >= 80 else "warm" if p_score >= 60 else "cold"
            p_type = p.get("opportunity_type", "") or ""
            html += f"""<tr><td><strong>{p.get("player_name", "N/D")}</strong></td><td>{p.get("age", "-")}</td>
<td><span class="score {p_cls}">{p_score}</span></td>
<td><span class="tag">{tlabel(p_type)}</span></td></tr>"""
        html += "</table></div>"
    
    html += f"""<footer><p>OB1 Scout — {date_str}</p></footer></div></body></html>"""
    return html

def main():
    print("Generazione Report Settimanale...")
    date_str = datetime.now().strftime("%d %B %Y").replace("January", "Gennaio").replace("February", "Febbraio").replace("March", "Marzo").replace("April", "Aprile").replace("May", "Maggio").replace("June", "Giugno").replace("July", "Luglio").replace("August", "Agosto").replace("September", "Settembre").replace("October", "Ottobre").replace("November", "Novembre").replace("December", "Dicembre")
    opportunities = load_data()
    if not opportunities:
        print("Nessuna opportunità!")
        return
    print(f"Caricate {len(opportunities)} opportunità")
    html = generate_report_html(opportunities, date_str)
    report_date = datetime.now().strftime("%Y-%m-%d")
    report_dir = REPORTS_DIR / report_date
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"HTML: {report_dir / 'index.html'}")
    stats = {"date": report_date, "total": len(opportunities), "hot": len([o for o in opportunities if o.get("ob1_score", 0) >= 80]), "warm": len([o for o in opportunities if 60 <= o.get("ob1_score", 0) < 80])}
    (report_dir / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"Stats: {report_dir / 'stats.json'}")
    (report_dir / "top10.json").write_text(json.dumps(sorted(opportunities, key=lambda x: x.get("ob1_score", 0), reverse=True)[:10], indent=2), encoding="utf-8")
    print(f"Top 10: {report_dir / 'top10.json'}")
    (REPORTS_DIR / "latest.json").write_text(json.dumps({"date": report_date, "url": f"https://mtornani.github.io/ob1-serie-c/reports/{report_date}/"}), encoding="utf-8")
    print(f"Latest: {REPORTS_DIR / 'latest.json'}")
    print(f"Report: docs/reports/{report_date}/")

if __name__ == "__main__":
    main()

