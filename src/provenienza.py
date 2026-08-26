"""
Un campo si pubblica se qualcuno l'ha letto. Non se un modello l'ha detto.

Il problema che questo file risolve
-----------------------------------
`src/enricher_tm.py` chiede a un LLM: "cerca su Transfermarkt il profilo di
Tizio e dimmi gol, presenze, procuratore, scadenza". Il modello non apre
nessuna pagina: risponde con quello che gli sembra plausibile. Il prompt dice
"Non inventare dati", che è una richiesta, non un vincolo.

Misura del 26 ago 2026 su data/opportunities.json (772 record):

    campo              da profilo aperto     senza nessuna pagina aperta
    agent                             11                            132
    appearances                        9                            113
    goals                              6                             54
    foot                              17                            198
    height_cm                         17                            301
    contract_expires                  21                            156
    birth_date                        30                            373

I 132 procuratori non letti da nessuna parte finivano sulla scheda come
"Agente: X", senza una riga di avvertenza. E finivano anche dentro
`assess_follow()`, cioè dentro il "Perché sì" che il direttore sportivo legge
come motivazione: "24 presenze e 7 gol" detto da un modello che non ha aperto
niente. È lo stesso difetto dei 138 link che portavano a un'altra persona —
stessa causa (ci fidavamo della forma invece che della fonte), volume simile.

La regola
---------
I campi che l'enricher scrive (`_TM_KEYS` in scripts/run_enrichment.py) sono
campi *di profilo*: esistono solo perché una scheda Transfermarkt li contiene.
Quindi si pubblicano solo se quella scheda è stata aperta e riconosciuta come
la persona giusta — cioè se esiste `tm_verified_at`, che scrive solo chi il
profilo lo ha letto davvero (src/tm_verify.py).

Senza verifica il valore non si cancella dal database: resta lì come *pista*,
è quello che l'enrichment andrà a controllare al giro dopo aprendo la pagina
vera. Ma non esce, non entra nello score e non entra nelle motivazioni.

Cosa NON tocca
--------------
Il nucleo della segnalazione, che non viene dall'LLM ma dall'articolo:
nome, tipo di opportunità, testo, fonte, data, regione. È lì il valore di OB1
— "questo nome si è mosso, ecco l'articolo che lo dice" — e regge da solo.
"""

from __future__ import annotations

# Gli stessi campi di `_TM_KEYS` in scripts/run_enrichment.py: sono quelli che
# l'enricher LLM scrive. Se quella lista cresce, cresce anche questa — il test
# in fondo al file lo verifica leggendo l'altro file.
CAMPI_DI_PROFILO = frozenset({
    "birth_date",
    "age",              # derivato da birth_date: eredita la sua provenienza
    "nationality",
    "second_nationality",
    "foot",
    "height_cm",
    "market_value",
    "market_value_eur",
    "market_value_formatted",
    "contract_expires",
    "agent",
    "appearances",
    "goals",
    "assists",
    "minutes_played",
    "season",
    "current_club",
})

# `current_club` esce anche quando il profilo non è stato aperto: l'articolo
# che ha generato la segnalazione parla di quel giocatore a quel club, quindi
# una fonte c'è ed è linkata sulla scheda. Resta il campo più fragile (un
# trasferimento lo invecchia in un giorno) ed è per questo che la verifica,
# quando c'è, lo riscrive con quello che dice la pagina.
TOLLERATI_SENZA_PROFILO = frozenset({"current_club"})


def profilo_letto(opp: dict) -> bool:
    """Qualcuno ha aperto la scheda di questa persona e l'ha riconosciuta?"""
    return bool((opp.get("tm_verified_at")
                 or (opp.get("player_profile") or {}).get("tm_verified_at")))


def campi_non_provati(opp: dict) -> list[str]:
    """I campi di profilo che questo record ha senza aver aperto niente."""
    if profilo_letto(opp):
        return []
    return sorted(
        c for c in CAMPI_DI_PROFILO - TOLLERATI_SENZA_PROFILO
        if opp.get(c) not in (None, "", [], {})
    )


def solo_provato(opp: dict) -> dict:
    """
    Copia del record con i campi di profilo non provati messi a None.

    None e non "0"/"": un dato ignoto deve leggersi come ignoto. Uno "0 gol"
    inventato si legge come "non ha mai segnato", ed è una bugia più precisa
    di quella che stava correggendo.
    """
    if profilo_letto(opp):
        return opp

    pulito = dict(opp)
    for campo in CAMPI_DI_PROFILO - TOLLERATI_SENZA_PROFILO:
        if campo in pulito:
            pulito[campo] = None

    profilo = pulito.get("player_profile")
    if isinstance(profilo, dict):
        p = dict(profilo)
        for campo in CAMPI_DI_PROFILO - TOLLERATI_SENZA_PROFILO:
            if campo in p:
                p[campo] = None
        pulito["player_profile"] = p

    return pulito


# ---------------------------------------------------------------- test

def _test() -> None:
    from pathlib import Path
    import re

    # 1. Un record verificato passa intero.
    ver = {"player_name": "Nicola Patierno", "agent": "SGN", "goals": 7,
           "tm_verified_at": "2026-08-26T16:00:00Z"}
    assert solo_provato(ver) == ver
    assert campi_non_provati(ver) == []

    # 2. Un record senza profilo aperto perde i campi di profilo...
    grezzo = {"player_name": "Tizio", "agent": "Agenzia Inventata",
              "goals": 12, "appearances": 30, "age": 22,
              "current_club": "Pescara",
              "opportunity_type": "svincolato",
              "source_url": "https://esempio.it/articolo",
              "description": "Il club ha comunicato la risoluzione."}
    pulito = solo_provato(grezzo)
    assert pulito["agent"] is None
    assert pulito["goals"] is None
    assert pulito["age"] is None
    # ...ma tiene tutto quello che viene dall'articolo.
    assert pulito["player_name"] == "Tizio"
    assert pulito["opportunity_type"] == "svincolato"
    assert pulito["source_url"] == "https://esempio.it/articolo"
    assert pulito["description"] == "Il club ha comunicato la risoluzione."
    assert pulito["current_club"] == "Pescara"
    assert grezzo["goals"] == 12, "l'originale non si tocca: resta la pista"
    assert set(campi_non_provati(grezzo)) == {"age", "agent", "appearances", "goals"}

    # 3. Anche player_profile viene ripulito: era la seconda strada da cui i
    #    dati non provati rientravano in dashboard (`opp.get(x) or profile.get(x)`).
    annidato = {"player_name": "Caio",
                "player_profile": {"agent": "Altra Agenzia", "foot": "destro"}}
    assert solo_provato(annidato)["player_profile"]["agent"] is None

    # 4. La lista non deve divergere da quella dell'enricher.
    run_enrich = Path(__file__).resolve().parent.parent / "scripts" / "run_enrichment.py"
    if run_enrich.exists():
        testo = run_enrich.read_text(encoding="utf-8")
        blocco = re.search(r"_TM_KEYS\s*=\s*\[(.*?)\]", testo, re.S)
        if blocco:
            chiavi = set(re.findall(r"'([a-z_]+)'", blocco.group(1)))
            chiavi -= {"tm_url", "enrichment_source"}  # non sono dati di scheda
            mancanti = chiavi - CAMPI_DI_PROFILO
            assert not mancanti, (
                f"l'enricher scrive campi che qui non sono coperti: {mancanti}")

    print("provenienza: ok")


if __name__ == "__main__":
    _test()
