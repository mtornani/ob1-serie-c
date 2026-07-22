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
  python scripts/find_players.py --free-only --sample 3 --out out/sample_3.json

--verify controlla ogni risultato sul profilo Transfermarkt reale (via
src/tm_scraper, gratuito) e segnala i mismatch: omonimi (data di nascita
diversa), cambi di club non registrati, dati fermi. È il passo che evita di
proporre falsi.

--sample N verifica automaticamente ogni candidato e scrive in --out un JSON
pronto per outreach (solo profili con TM check "OK", scartando mismatch e
non trovati) — schema: name, club, role, year, bullets, sources. Vedi
RUNBOOK_NOMI_GIOCATORI.md per il flusso completo (comando esatto, dove
finisce l'output, come leggerlo da un'altra macchina/sessione).
"""
import argparse
import json
import re
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
    """Vista unificata: parte dall'archivio grezzo data/opportunities.json
    (tutte le segnalazioni, ~600+) e vi sovrappone punteggio/assessment/
    review_flags di docs/data.json dove disponibili (~60 già passate dal
    punteggio automatico). La maggioranza delle segnalazioni buone per
    campionati diversi dalla Serie C (Serie B, Eccellenza...) sta solo
    nel grezzo — usarlo come base invece che come arricchimento secondario
    evita di perderle di vista di default."""
    raw = json.loads((ROOT / 'data' / 'opportunities.json').read_text(encoding='utf-8'))
    opps = raw if isinstance(raw, list) else raw.get('opportunities', raw)
    if isinstance(opps, dict):
        opps = list(opps.values())

    dash = json.loads((ROOT / 'docs' / 'data.json').read_text(encoding='utf-8'))
    dash_opps = dash if isinstance(dash, list) else dash.get('opportunities', dash)
    if isinstance(dash_opps, dict):
        dash_opps = list(dash_opps.values())
    by_id = {o.get('id'): o for o in dash_opps}

    SCORE_FIELDS = ('ob1_score', 'classification', 'review_flags', 'corroborated',
                    'n_sources', 'assessment', 'publishable')
    for o in opps:
        s = by_id.get(o.get('id')) or {}
        for k in SCORE_FIELDS:
            if s.get(k) is not None:
                o[k] = s[k]
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


def _name_tokens(name):
    return {t for t in re.sub(r'[^a-zà-ÿ\s]', '', (name or '').lower()).split() if len(t) > 2}


_ACQUIRED_PATTERN = re.compile(r'\bacquistat[oi]\s+da(l|lla|ll[’\']|)\b', re.IGNORECASE)


def verify_on_tm(o):
    """Confronta il record OB1 col profilo Transfermarkt reale.
    Ritorna (esito, dettagli)."""
    import tm_scraper
    tm_url = o.get('tm_url')
    if not (isinstance(tm_url, str) and 'transfermarkt' in tm_url):
        tm_url = None
    data = tm_scraper.enrich(o.get('player_name') or '', tm_url)
    if not data:
        return 'NON TROVATO', 'nessun profilo TM raggiungibile — verifica manuale', {}

    issues = []

    # Il tm_url salvato può puntare a un omonimo (nome diverso da quello
    # cercato): senza questo controllo un profilo sbagliato ma verosimile
    # passa per "coerente" solo perché età/club non contraddicono nulla.
    profile_name = data.get('profile_name')
    if profile_name:
        wanted = _name_tokens(o.get('player_name'))
        got = _name_tokens(profile_name)
        # Un nome in comune (spesso il nome di battesimo) non basta: "Balianelli
        # Francesco" e "Francesco Ancora" condividono "francesco" ma sono due
        # persone diverse. Si richiede che la maggioranza dei token combaci.
        overlap = len(wanted & got) / len(wanted | got) if (wanted and got) else 1.0
        if wanted and got and overlap < 0.5:
            issues.append(f"NOME DIVERSO: cercato '{o.get('player_name')}', profilo TM è '{profile_name}'")

    # Una descrizione tipo "svincolato, acquistato dal Bra" non è un giocatore
    # disponibile: è un giocatore appena tesserato DA quel club. Il TM check da
    # solo non lo distingue (età e club spesso combaciano comunque).
    testo = ((o.get('summary') or '') + ' ' + (o.get('description') or ''))
    if _ACQUIRED_PATTERN.search(testo):
        issues.append("FONTE DICE 'acquistato da/dal/dalla' — probabile giocatore già tesserato, non un'opportunità aperta")

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
    contratto_attivo = False
    if exp:
        from datetime import date
        try:
            exp_date = date.fromisoformat(exp)
            giorni = (exp_date - date.today()).days
            # Una scadenza a pochi mesi (o già passata) è il normale ritardo di
            # aggiornamento di TM dopo un rescissione/fine contratto — non
            # invalida la segnalazione. Una scadenza a un anno o più nel futuro
            # vuol dire che il contratto è ancora vivo: non è uno svincolato.
            if giorni > 180 and o.get('opportunity_type') in FREE_TYPES:
                contratto_attivo = True
                issues.append(f"CONTRATTO ANCORA ATTIVO fino al {exp} — non è uno svincolato reale")
            else:
                issues.append(f"scadenza contratto TM: {exp}")
        except ValueError:
            issues.append(f"scadenza contratto TM: {exp}")

    esito = 'MISMATCH' if (contratto_attivo or any(
        marker in i for i in issues
        for marker in ('OMONIMO', 'CAMBIATO', 'NOME DIVERSO', 'FONTE DICE')
    )) else 'OK'
    return esito, '; '.join(issues) if issues else 'coerente col profilo TM', data


def _is_real_article(url):
    """Un vertexaisearch/grounding-redirect non è un articolo leggibile e
    citabile — non va spacciato per fonte giornalistica."""
    return bool(url) and 'vertexaisearch' not in url and 'grounding-api-redirect' not in url


def build_sample(found, n, verified_at):
    """Verifica i candidati uno per uno finché non ne trova n con TM check
    'OK', poi li formatta nello schema di outreach (name, club, role, year,
    bullets, sources). Niente MISMATCH o NON TROVATO in output: quelli sono
    falsi potenziali, non candidati da mandare in giro."""
    profiles = []
    scartati = []
    for o in found:
        if len(profiles) >= n:
            break

        # Una segnalazione a fonte singola può risultare "coerente" col
        # profilo TM (età, club) e comunque essere sbagliata nella sostanza —
        # è già successo (un "ufficiale l'addio" mentre TM mostra il
        # giocatore ancora in rosa lì). Per un campione pronto da inviare
        # meglio escluderle di default: chi le vuole lo fa con --verify a mano.
        if 'fonte_singola' in (o.get('review_flags') or ''):
            scartati.append({'nome': o.get('player_name'),
                              'motivo': "fonte singola (review_flags: fonte_singola) — richiede verifica manuale prima di un contatto, esclusa dal campione automatico"})
            continue

        esito, dettagli, tm_data = verify_on_tm(o)
        if esito != 'OK':
            scartati.append({'nome': o.get('player_name'), 'motivo': dettagli})
            time.sleep(1.2)
            continue

        birth = o.get('birth_date') or tm_data.get('birth_date')
        year = int(birth[:4]) if birth else None
        bullets = [
            f"{o.get('opportunity_type', 'svincolato').capitalize()} — {o.get('current_club') or tm_data.get('current_club') or 'nessun club attuale'}",
            f"Valore di mercato: {o.get('market_value_formatted') or tm_data.get('market_value_text') or 'non disponibile'}",
            f"Verificato su Transfermarkt il {verified_at} — {dettagli}",
        ]
        sources = [u for u in (o.get('tm_url'), tm_data.get('tm_url')) if u]
        if not sources:
            sources = []
        if _is_real_article(o.get('source_url')):
            sources.append(o['source_url'])
        sources = list(dict.fromkeys(sources))  # dedup, ordine stabile

        profiles.append({
            'name': o.get('player_name'),
            'club': o.get('current_club') or tm_data.get('current_club') or None,
            'role': o.get('role_name') or o.get('role') or tm_data.get('main_position'),
            'year': year,
            'bullets': bullets,
            'sources': sources,
        })
        time.sleep(1.2)
    return profiles, scartati


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
    ap.add_argument('--sample', type=int, metavar='N', help='verifica e scrive N profili pronti per outreach (schema: name, club, role, year, bullets, sources)')
    ap.add_argument('--out', help='percorso file di output per --sample (richiesto insieme a --sample)')
    args = ap.parse_args()

    opps = load_opportunities()
    found = [o for o in opps if matches(o, args)]
    found.sort(key=lambda o: -(o.get('ob1_score') or 0))

    if args.sample:
        if not args.out:
            ap.error('--sample richiede --out <path>')
        from datetime import date
        verified_at = date.today().isoformat()
        profiles, scartati = build_sample(found, args.sample, verified_at)
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'generated_at': verified_at,
            'criteria': {k: v for k, v in vars(args).items()
                         if k not in ('sample', 'out', 'json') and v not in (None, False)},
            'profiles': profiles,
            'scartati_in_verifica': scartati,
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"{len(profiles)}/{args.sample} profili verificati scritti in {out_path}")
        if len(profiles) < args.sample:
            print(f"Attenzione: solo {len(profiles)} candidati hanno superato il TM check "
                  f"su {len(found)} esaminati — {len(scartati)} scartati (vedi 'scartati_in_verifica').")
        return

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
            esito, det, _ = verify_on_tm(o)
            mark = '✓' if esito == 'OK' else '✗'
            print(f"   {mark} TM check: {esito} — {det}")
            time.sleep(1.5)


if __name__ == '__main__':
    main()
