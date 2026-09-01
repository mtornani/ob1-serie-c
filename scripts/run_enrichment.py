#!/usr/bin/env python3
"""
Enrichment Transfermarkt — batched.

One grounded Gemini call enriches BATCH_SIZE players at once (the cost
lever: N players -> ceil(N/BATCH_SIZE) calls instead of N). Players the
model can't find stay unlocked and retry on the next run.
"""
import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from src.enricher_tm import TransfermarktEnricher, BATCH_SIZE, forma_di_club
from src.entity_gate import classify
from src.quality_gate import AGE_MIN, AGE_MAX
from src.metrics import METRICS_FILE, get_metrics

DATA_FILE = Path("data/opportunities.json")
DATA_FILE_DOCS = Path("docs/data.json")
DELAY_BETWEEN_BATCHES = 5  # seconds

# Cap Gemini calls per run: backlog spikes (e.g. a big discovery day) get
# spread over multiple runs instead of burning quota in one.
# Free tier ≈20 RPD shared with discovery — keep enrichment lean.
MAX_BATCHES_PER_RUN = int(os.getenv("MAX_ENRICH_BATCHES", "4"))

_JUNK_TERMS = [
    'transfermarkt', 'calciomercato', 'svincolati', 'la casa di c',
    'rádio', 'fischio finale', 'ultime notizie', 'football club',
    'web radio', 'il portale', 'il piccolo', 'management magazine',
    'next pro wiki', 'chiamarsi bomber', 'spareggi nazionali', 'spareggi',
    'stagione sportiva', 'sport news', 'giornale', 'magazine',
    'notiziario', 'dipartimento', 'interregionale', 'associazione',
    'sky sport', 'rappresentativa', 'juniores cup', 'parametro zero',
    'football italy', 'migliori giovani', 'giovani talenti', 'occasione serie',
    'notizie calcio', 'scuola superiore', 'tutto mercato', 'calciomercato live',
    'accordo collettivo', 'guardian', 'ultimo uomo', 'mediaset',
    'jugadores libres', 'ranking', 'classifica', 'tabella',
    'reserve league', 'liga profesional', 'selección', 'seleccion',
]

_TM_KEYS = ['nationality', 'second_nationality', 'foot', 'market_value',
            'enrichment_source',
            'market_value_formatted', 'height_cm', 'birth_date', 'contract_expires',
            'tm_url', 'agent', 'appearances', 'goals', 'assists', 'minutes_played',
            'current_club']

# Campi in testo libero dove un modello debole, senza dati veri da dare,
# può restituire un frammento dello SCHEMA invece di un valore — non una
# fonte diversa che sbaglia, il modello che risponde descrivendo la domanda.
#
# Trovato dal vivo (31 ago 2026, prima run dopo il grafo delle fonti):
# Daniele Cagnazzo, current_club = ", competizione ecc." — nessuna
# occorrenza di quella frase nei nostri prompt (verificato: non è un
# template che perde), quindi non è un leak, è un'invenzione del modello
# (Mistral, via free_stack) quando non sapeva la risposta vera.
#
# Il grafo l'ha reso visibile per la prima volta: prima finiva dritto in
# `current_club` e restava lì, un fatto falso indistinguibile da uno vero.
_CAMPI_TESTO_LIBERO = ('current_club', 'agent', 'nationality', 'second_nationality')

# "Svincolato" non è un nome di squadra, ma è una risposta vera — ed è proprio
# la risposta che questo prodotto cerca. Non deve cadere col controllo di forma.
_STATI_SENZA_SQUADRA = frozenset({
    'svincolato', 'senza squadra', 'senza club', 'ritiro', 'carriera conclusa',
    'free agent', 'without club', 'retired',
})

# Il ruolo NON si presta allo stesso controllo del club: "del compagno" non
# comincia con punteggiatura, è una frase italiana grammaticalmente normale
# — è solo semanticamente un ruolo di calcio inesistente. Ma a differenza di
# club/agente, il ruolo è un vocabolario CHIUSO: poche decine di parole, in
# tre lingue viste davvero nei dati (IT/EN/DE — Transfermarkt risponde nella
# lingua del TLD interrogato). Un controllo per appartenenza, come i nomi in
# entity_gate.classify_name, invece che per esclusione.
#
# "Non Specificato" / "N/D" restano ammessi apposta: sono il modo in cui
# ALTRI punti della pipeline dichiarano "non lo sappiamo" (6 e 1 occorrenze
# reali nel corpus) — un "non lo so" onesto non è la stessa cosa di un
# frammento di schema, e non va scartato allo stesso modo.
_RUOLI_NOTI = (
    'portiere', 'goalkeeper', 'torwart',
    'difensore', 'difesa', 'centrale', 'terzino', 'libero', 'laterale',
    'defender', 'back', 'sweeper',
    'verteidiger', 'außen',
    'centrocampista', 'centrocampo', 'mediano', 'regista', 'trequartista',
    'midfield', 'midfielder',
    'mittelfeld', 'stürmer', 'sechser', 'zehner',
    'ala', 'esterno', 'winger',
    'attaccante', 'attacco', 'punta',
    'forward', 'striker', 'attack',
)
_RUOLO_IGNOTO_DICHIARATO = ('non specificato', 'n/d', 'n/a', 'unknown', '-')


def _valore_di_ruolo_plausibile(valore) -> bool:
    """Contiene almeno una parola di un vocabolario di ruolo vero, o è un
    "non lo sappiamo" dichiarato — non un frammento di schema come "del
    compagno" (caso vero, 31 ago 2026, comparso due volte nel corpus)."""
    if not isinstance(valore, str):
        return True
    v = valore.strip().lower()
    if not v:
        return True
    if v in _RUOLO_IGNOTO_DICHIARATO:
        return True
    # Sottostringa, non \b: provato un confine di parola e rotto subito su
    # dati veri — "Mittelstürmer" e "Linksaußen" sono composti tedeschi
    # senza spazio interno, "stürmer"/"außen" non cominciano su un confine.
    # Il rischio opposto (un "ala" per sottostringa dentro "scala") resta
    # teorico: nel vocabolario di ruolo non è mai comparso.
    return any(r in v for r in _RUOLI_NOTI)


def _valore_di_testo_plausibile(valore) -> bool:
    """
    Un valore in testo libero che assomiglia a una risposta vera, non a un
    frammento di istruzioni. Non prova che sia CORRETTO — solo che non sia
    palesemente il modello che descrive lo schema invece di compilarlo.

    Regola minima, non un parser di linguaggio: un nome di club/persona vero
    non comincia con un segno di punteggiatura, e le frasi-schema quasi
    sempre sì (", competizione ecc." comincia con una virgola perché è la
    coda di un elenco). Un numero come primo carattere resta valido apposta
    — ci sono club veri con un anno nel nome (es. "1913 Seregno").
    """
    if not isinstance(valore, str):
        return True                    # non è testo: non è questo il controllo
    v = valore.strip()
    if not v:
        return True                    # stringa vuota: la gestisce chi chiama
    if v[0] in ',;:.!?)]}-–—':
        return False
    v_norm = v.lower().strip('.').strip()
    if v_norm in ('ecc', 'eccetera', 'esempio', 'placeholder', 'template',
                  'tbd', 'n/a', 'null', 'none', 'vedi sopra'):
        return False
    return True


def _is_enrichable(opp) -> bool:
    """
    Si spende su questo record? Il gate è condiviso con la discovery
    (src/entity_gate.py): una sola fonte di verità invece di tre liste
    divergenti. Accetta un dict o, per compatibilità, un nome.
    """
    if isinstance(opp, str):
        opp = {"player_name": opp}
    return classify(opp).spend_allowed


def _registra_nel_grafo(opp: dict, tm: dict) -> None:
    """
    Mette nel grafo delle fonti (src/piramide.py) cosa dice la discovery e
    cosa dice Transfermarkt, PRIMA che uno dei due cancelli l'altro.

    Il grafo vive dentro il record (`grafo_fonti`), non in un database a
    parte: qui lo stato è un JSON su file, e una tabella in più sarebbe una
    seconda verità da tenere allineata a mano.

    Non decide niente — la riga sotto continua a fare quello che faceva. Ma
    quando un conflitto c'è, adesso resta scritto insieme a chi l'ha
    causato, e `piramide.risolvi` sa già dire chi dovrebbe vincere.
    """
    from src.piramide import registra

    grafo = opp.get('grafo_fonti')
    if not isinstance(grafo, dict):
        grafo = {}
    # La data della notizia è l'unica cosa che rende "fresca" l'osservazione
    # della discovery: senza, un club trovato in giro non batte niente.
    datato = (opp.get('reported_date') or '')[:10]
    for campo, chiave_opp, chiave_tm in (
            ('club', 'current_club', 'current_club'),
            ('eta', 'age', None),
            ('contract_expires', 'contract_expires', 'contract_expires'),
            ('market_value', 'market_value', 'market_value')):
        if opp.get(chiave_opp) is not None:
            registra(grafo, 'p', campo, opp.get(chiave_opp), 'news',
                     datato_al=datato, url=opp.get('source_url') or '')
        if chiave_tm and tm.get(chiave_tm) is not None:
            registra(grafo, 'p', campo, tm.get(chiave_tm), 'transfermarkt',
                     url=tm.get('tm_url') or opp.get('tm_url') or '')
    # L'età di TM non arriva come numero ma come data di nascita: è il dato
    # più forte che abbiamo su un campo lento, e buttarlo sarebbe il difetto
    # che questo grafo esiste per rendere visibile.
    if tm.get('birth_date'):
        try:
            eta_tm = datetime.now().year - int(str(tm['birth_date'])[:4])
            if 10 <= eta_tm <= 60:
                registra(grafo, 'p', 'eta', eta_tm, 'transfermarkt',
                         url=tm.get('tm_url') or '',
                         nota=f"da data di nascita {str(tm['birth_date'])[:10]}")
        except (ValueError, TypeError):
            pass
    if grafo:
        opp['grafo_fonti'] = grafo


def apply_tm_data(opp: dict, tm: dict) -> bool:
    """
    Merge TM data into an opportunity. Returns True if locked as enriched.

    Conta anche i FATTI NUOVI (ARCH-002 Fase 1): un campo che prima era vuoto e
    ora ha un valore. Non si contano le riscritture dello stesso dato — quelle
    sono lavoro rifatto, non informazione nuova, ed è proprio la differenza che
    il costo per fatto deve rendere visibile.
    """
    metrics = get_metrics()
    if tm.get('market_value_eur') and not tm.get('market_value'):
        tm['market_value'] = tm['market_value_eur']
    if tm.get('market_value_text') and not tm.get('market_value_formatted'):
        tm['market_value_formatted'] = tm['market_value_text']

    # Un frammento di schema non è un dato: si scarta PRIMA che tocchi il
    # grafo o il record, non dopo. Vedi _valore_di_testo_plausibile.
    # Niente metrics.fact() qui: quel contatore alimenta costo_per_fatto
    # (operazioni / fatti nuovi), e uno scarto non è un fatto nuovo — chiamarlo
    # tale renderebbe la pipeline artificialmente più "efficiente" di quanto
    # sia stata davvero in questo giro.
    for campo in _CAMPI_TESTO_LIBERO:
        if campo in tm and not _valore_di_testo_plausibile(tm.get(campo)):
            print(f"  [SCARTATO] {campo}={tm[campo]!r} non è un valore, "
                  f"è un frammento di schema")
            tm[campo] = None

    # `current_club` ha una forma sua, più stretta del testo libero: è un nome
    # proprio corto. La specifica vive in src/enricher_tm.forma_di_club, misurata
    # sui 150 nomi veri del corpus TM. Qui si ri-applica al confine di scrittura
    # perché il valore arriva da DUE bocche — la regex sulla pagina e l'LLM sul
    # residuo — e finora ne era sorvegliata una sola.
    club = tm.get('current_club')
    if isinstance(club, str) and club.strip():
        if not (forma_di_club(club)
                or club.strip().lower() in _STATI_SENZA_SQUADRA):
            print(f"  [SCARTATO] current_club={club!r} non ha forma di squadra")
            tm['current_club'] = None

    # Prima di sovrascrivere: registrare chi dice cosa (src/piramide.py).
    # Questo è l'unico istante in cui i due valori coesistono — quello che la
    # discovery aveva trovato e quello che Transfermarkt porta. Subito sotto,
    # `opp[key] = tm[key]` ne cancella uno e nessuno si ricorda che esisteva.
    #
    # Oggi registra e basta: non cambia chi vince. Serve a misurare quanto le
    # due bocche litigano davvero prima di lasciar decidere il grafo — e già
    # così un disaccordo smette di sparire in silenzio.
    _registra_nel_grafo(opp, tm)

    for key in _TM_KEYS:
        if tm.get(key) is not None:
            if not opp.get(key):
                metrics.fact(key)
            opp[key] = tm[key]
    # setdefault would return an existing null value; guard for that.
    profile = opp.get('player_profile')
    if not isinstance(profile, dict):
        profile = {}
        opp['player_profile'] = profile
    for key in _TM_KEYS:
        if tm.get(key) is not None:
            profile[key] = tm[key]

    if not opp.get('age') and tm.get('birth_date'):
        try:
            age = datetime.now().year - int(str(tm['birth_date'])[:4])
            # AGE_MIN/AGE_MAX (src/quality_gate.py), non un 10-60 arbitrario:
            # sono la fascia che questo radar dichiara di coprire. Un'età
            # fuori da lì non aspetta il gate per essere scartata — il gate
            # la scarterebbe comunque, ma nel frattempo 'age' sarebbe già
            # scritto come fatto nel record grezzo (data/opportunities.json),
            # indistinguibile da un'età vera finché qualcuno non lo nota.
            # Caso reale (31 ago 2026): un birth_date inventato dava 58 anni
            # — dentro il vecchio 10-60, fuori dalla fascia vera del prodotto.
            if AGE_MIN <= age <= AGE_MAX:
                opp['age'] = age
                metrics.fact('age')
        except (ValueError, TypeError):
            pass

    # Role from TM main_position if missing. Lo stesso record che ha dato
    # ", competizione ecc." come club ha dato "del compagno" come ruolo,
    # nella stessa chiamata — non è un dominio a parte, è lo stesso modello
    # che risponde descrivendo lo schema quando non sa la risposta vera. Ma
    # "del compagno" non comincia con punteggiatura: il controllo qui è per
    # vocabolario (_valore_di_ruolo_plausibile), non per forma del testo.
    if (tm.get('main_position') and not (opp.get('role_name') or opp.get('role'))
            and _valore_di_ruolo_plausibile(tm['main_position'])):
        opp['role_name'] = tm['main_position']
        opp['role'] = tm['main_position']
        metrics.fact('role_name')

    # Lock only when substantive data arrived; otherwise retry next run.
    has_substance = any(tm.get(k) for k in [
        'market_value', 'appearances', 'contract_expires', 'goals', 'birth_date', 'current_club',
    ])
    opp['tm_enriched'] = has_substance
    return has_substance


def _report_metrics() -> None:
    """
    Riga di metriche di fine run (ARCH-002 Fase 1). Va emessa anche quando non
    c'è stato niente da fare: una run a vuoto è essa stessa un'informazione
    (coda vuota), e i buchi nella serie storica non si possono ricostruire.
    """
    try:
        from src.llm import get_gateway
        print(get_gateway().run_summary())
    except Exception:
        pass
    metrics = get_metrics()
    print(metrics.summary())
    if metrics.write(METRICS_FILE):
        print(f"  [METRICS] riga aggiunta a {METRICS_FILE}")


def main():
    if not DATA_FILE.exists():
        print(f"File {DATA_FILE} non trovato!")
        _report_metrics()
        return
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    opportunities = data if isinstance(data, list) else data.get('opportunities', [])
    print(f"Trovate {len(opportunities)} opportunità.")

    pending = [o for o in opportunities
               if _is_enrichable(o) and o.get('tm_enriched') is not True]
    skipped = len(opportunities) - len(pending) - sum(
        1 for o in opportunities if o.get('tm_enriched') is True)
    if skipped > 0:
        print(f"Scartati dal gate (nessuna spesa): {skipped}")
    # Priority: missing age first (blocks publish gate), then missing club
    pending.sort(key=lambda o: (
        0 if o.get('age') in (None, '') else 1,
        0 if not (o.get('current_club') or '').strip() else 1,
        o.get('player_name') or '',
    ))
    no_age = sum(1 for o in pending if o.get('age') in (None, ''))
    print(f"Da arricchire: {len(pending)} (senza età: {no_age})")
    if not pending:
        print("Niente da fare.")
        _report_metrics()
        return

    enricher = TransfermarktEnricher()
    enriched = 0
    batches = [pending[i:i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
    if len(batches) > MAX_BATCHES_PER_RUN:
        skipped = len(batches) - MAX_BATCHES_PER_RUN
        print(f"Backlog alto: {skipped} batch rinviati alla prossima run.")
        batches = batches[:MAX_BATCHES_PER_RUN]

    for bi, batch in enumerate(batches, 1):
        if enricher.stalled:
            print(f"  [STOP] nessuna rotta LLM — batch {bi}–{len(batches)} rinviati")
            break
        names = [o['player_name'] for o in batch]
        get_metrics().player_touched(len(names))
        print(f"\n[batch {bi}/{len(batches)}] {', '.join(names)}")
        results = enricher.enrich_players_batch(names)
        for opp in batch:
            tm = results.get(opp['player_name']) or {}
            if tm and apply_tm_data(opp, tm):
                enriched += 1
                print(f"  ✅ {opp['player_name']}: "
                      f"{tm.get('market_value_text') or '?'} | age={opp.get('age')} "
                      f"| apps={tm.get('appearances', '?')}")
        DATA_FILE.write_text(json.dumps(opportunities, ensure_ascii=False, indent=2), encoding='utf-8')
        if bi < len(batches) and not enricher.stalled:
            time.sleep(DELAY_BETWEEN_BATCHES)

    # NB: docs/data.json ha il formato dashboard (dict con opportunities/stats),
    # non la lista grezza. Scriverci la lista lo corrompe finché
    # generate_dashboard.py non gira. Lo rigenera lui, subito dopo in ingest.yml.
    print(f"\nTotale: {len(pending)} candidati | Arricchiti: {enriched} | "
          f"Batch elaborati: {len(batches)}")
    # ARCH-002 Fase 1: il numero che dice se le ottimizzazioni funzionano.
    _report_metrics()


if __name__ == "__main__":
    main()
