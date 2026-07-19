#!/usr/bin/env python3
"""
Query interna sul database OB1 — ricerca per squadra, campionato e criteri di
mercato, con fact-check Transfermarkt opzionale.

Strumento CLI locale, NON collegato alla dashboard pubblica. Serve per
interrogazioni ad-hoc ("chi c'è di libero in zona X?", "chi risulta al club Y?")
senza toccare la pipeline.

Esempi:
  python scripts/find_players.py --club "san marino"
  python scripts/find_players.py --league serie_c --free-only
  python scripts/find_players.py --preset eccellenza --geo romagna,marche
  python scripts/find_players.py --club forli --verify

--verify controlla ogni risultato sul profilo Transfermarkt reale (via
src/tm_scraper, gratuito) e segnala i mismatch: omonimi (data di nascita
diversa), cambi di club non registrati, dati fermi. È il passo che evita di
proporre falsi.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

FREE_TYPES = ('svincolato', 'rescissione')

# Preset Eccellenza: i punteggi OB1 sono calibrati sulla Serie C — per un
# contesto dilettantistico contano criteri diversi (libertà contrattuale,
# valore contenuto, niente prospetti di club elite).
ELITE_CLUBS = ('atalanta', 'juventus', 'inter', 'milan', 'roma', 'lazio',
               'napoli', 'fiorentina', 'torino', 'bologna', 'sassuolo',
               'u23', 'next gen', 'primavera')
ECCELLENZA_MAX_VALUE = 150_000


def load_opportunities():
    """Vista unificata: docs/data.json (scored, con assessment) arricchita con
    i tm_url del database raw."""
    dash = json.loads((ROOT / 'docs' / 'data.json').read_text(encoding='utf-8'))
    opps = dash if isinstance(dash, list) else dash.get('opportunities', dash)
    if isinstance(opps, dict):
        opps = list(opps.values())

    raw = json.loads((ROOT / 'data' / 'opportunities.json').read_text(encoding='utf-8'))
    raw_opps = raw if isinstance(raw, list) else raw.get('opportunities', raw)
    if isinstance(raw_opps, dict):
        raw_opps = list(raw_opps.values())
    by_id = {o.get('id'): o for o in raw_opps}

    for o in opps:
        r = by_id.get(o.get('id')) or {}
        for k in ('tm_url', 'birth_date'):
            if not o.get(k) and r.get(k):
                o[k] = r[k]
    return opps


def matches(o, args):
    club = (o.get('current_club') or '').lower()
    if args.club and args.club.lower() not in club:
        return False
    if args.league:
        league = ((o.get('league_id') or '') + ' ' + (o.get('region') or '')).lower()
        if args.league.lower() not in league:
            return False
    if args.free_only and o.get('opportunity_type') not in FREE_TYPES:
        return False
    if args.max_value is not None and (o.get('market_value') or 0) > args.max_value:
        return False
    if args.geo:
        zones = [z.strip().lower() for z in args.geo.split(',') if z.strip()]
        if not any(z in club for z in zones):
            return False
    if args.preset == 'eccellenza':
        if any(e in club for e in ELITE_CLUBS):
            return False
        if (o.get('market_value') or 0) > ECCELLENZA_MAX_VALUE:
            return False
    return True


def verify_on_tm(o):
    """Confronta il record OB1 col profilo Transfermarkt reale.
    Ritorna (esito, dettagli)."""
    import tm_scraper
    tm_url = o.get('tm_url')
    if not (isinstance(tm_url, str) and 'transfermarkt' in tm_url):
        tm_url = None
    data = tm_scraper.enrich(o.get('player_name') or '', tm_url)
    if not data:
        return 'NON TROVATO', 'nessun profilo TM raggiungibile — verifica manuale'

    issues = []
    db_birth = o.get('birth_date')
    tm_birth = data.get('birth_date')
    if db_birth and tm_birth and db_birth[:4] != tm_birth[:4]:
        issues.append(f"OMONIMO? nascita DB {db_birth} vs TM {tm_birth}")
    elif not db_birth and tm_birth and o.get('age'):
        # senza data nel DB, controllo grossolano sull'età dichiarata
        from datetime import date
        tm_age = date.today().year - int(tm_birth[:4])
        if abs(tm_age - int(o['age'])) > 1:
            issues.append(f"OMONIMO? età DB {o['age']} vs TM ~{tm_age}")

    db_club = (o.get('current_club') or '').lower()
    tm_club = (data.get('current_club') or '').lower()
    if tm_club and db_club and db_club not in tm_club and tm_club not in db_club:
        if 'svincolato' in tm_club:
            issues.append("TM lo dà svincolato (DB indica un club)")
        else:
            issues.append(f"CLUB CAMBIATO: DB '{o.get('current_club')}' vs TM '{data.get('current_club')}'")

    exp = data.get('contract_expires')
    if exp:
        issues.append(f"scadenza contratto TM: {exp}")

    esito = 'MISMATCH' if any('OMONIMO' in i or 'CAMBIATO' in i for i in issues) else 'OK'
    return esito, '; '.join(issues) if issues else 'coerente col profilo TM'


def main():
    ap = argparse.ArgumentParser(description='Query interna database OB1')
    ap.add_argument('--club', help='sottostringa del club attuale')
    ap.add_argument('--league', help='sottostringa di league_id/region (es. serie_c)')
    ap.add_argument('--geo', help='zone separate da virgola, match sul nome club (es. romagna,marche,rimini)')
    ap.add_argument('--free-only', action='store_true', help='solo svincolati/rescissioni')
    ap.add_argument('--max-value', type=int, help='valore di mercato massimo in €')
    ap.add_argument('--preset', choices=['eccellenza'], help='filtri predefiniti per contesto')
    ap.add_argument('--verify', action='store_true', help='fact-check su Transfermarkt (lento: ~2s a giocatore)')
    ap.add_argument('--json', action='store_true', help='output JSON invece che tabellare')
    args = ap.parse_args()

    opps = load_opportunities()
    found = [o for o in opps if matches(o, args)]
    found.sort(key=lambda o: -(o.get('ob1_score') or 0))

    if args.json and not args.verify:
        print(json.dumps(found, indent=2, ensure_ascii=False))
        return

    print(f"{len(found)} risultati su {len(opps)} opportunità\n")
    for o in found:
        flags = o.get('review_flags') or ''
        print(f"{o.get('player_name')}  |  {o.get('age')} anni  |  {o.get('role_name')}  |  "
              f"{o.get('current_club') or '—'}  |  {o.get('opportunity_type')}  |  "
              f"{o.get('market_value_formatted') or 'mv n/d'}  |  score {o.get('ob1_score')}"
              + (f"  |  ⚠ {flags}" if flags else ""))
        if args.verify:
            esito, det = verify_on_tm(o)
            mark = '✓' if esito == 'OK' else '✗'
            print(f"   {mark} TM check: {esito} — {det}")
            time.sleep(1.5)


if __name__ == '__main__':
    main()
