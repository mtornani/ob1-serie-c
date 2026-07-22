# RUNBOOK — produrre N nomi verificati per sample/brief

Questo file esiste per far sì che **Grok** (o chiunque altro, anche senza
accesso a questa sessione) possa produrre un campione di profili giocatori
per outreach, usando solo il repo e questo comando — senza dover richiedere
di nuovo il lavoro a Claude Code da zero.

## Repo attiva

- Path in questa sessione (cloud, Linux): `/home/user/ob1-serie-c`
- Path locale su Windows (Mirko), secondo la mappa condivisa: presumibilmente
  `D:\AI\Sferico\OB1_Ecosystem\global-scout\ob1_serie_c` — verificare che sia
  la stessa repo (stesso remote GitHub `mtornani/ob1-serie-c`) prima di fidarsi
  ciecamente del path, potrebbe essere un checkout diverso o disallineato.
- Repo GitHub: `mtornani/ob1-serie-c`, branch di lavoro corrente:
  `claude/setup-daas-platform-vUaGu`

## Prerequisiti

- Python 3.12 (su Windows: `C:\Users\Mirko\AppData\Local\Programs\Python\Python312\python.exe`,
  vedi CLAUDE.md del repo)
- Nessuna dipendenza esterna da installare: lo script usa solo libreria
  standard (`urllib`, `re`, `json`) e legge Transfermarkt in chiaro via HTTP —
  niente Gemini, niente Tavily, niente API a pagamento
- Nessuna variabile d'ambiente richiesta per questo comando specifico (non
  serve `.env`)
- File dati già presenti nel repo, nessun altro setup:
  - `data/opportunities.json` — archivio grezzo di tutte le segnalazioni (~600+)
  - `docs/data.json` — punteggio OB1 dove disponibile (~60 già passate dal
    sistema di scoring)

## Comando sample (esempio: 3 profili)

```
cd ob1-serie-c
python scripts/find_players.py --free-only --sample 3 --out out/sample_3.json
```

Tempo indicativo: ~2 secondi a giocatore esaminato (fetch Transfermarkt +
pausa di cortesia tra le richieste). Per 3 profili buoni può servire
esaminarne una decina o più — lo script continua a scartare finché non ne
trova N puliti o esaurisce i candidati disponibili.

### Filtri componibili

| Flag | Effetto |
|---|---|
| `--club "<testo>"` | sottostringa del club attuale, es. `--club "san marino"` |
| `--league <testo>` | sottostringa di league/regione, es. `--league serie_c` |
| `--geo zona1,zona2` | match sul nome del club, es. `--geo romagna,marche,rimini` |
| `--max-value <euro>` | valore di mercato massimo, es. `--max-value 150000` |
| `--preset eccellenza` | esclude prospetti da club elite (Atalanta, Juventus, ecc.) e sopra i 150k — per contesti sotto la Serie C |
| `--free-only` | solo svincolati/rescissioni (quasi sempre da usare per un sample di outreach) |

Esempio combinato (candidati Romagna per un contesto sotto la Serie C):

```
python scripts/find_players.py --free-only --preset eccellenza --geo romagna,marche --sample 5 --out out/sample_romagna.json
```

## Output — schema

```json
{
  "generated_at": "YYYY-MM-DD",
  "criteria": { "...filtri usati...": true },
  "profiles": [
    {
      "name": "Nome Cognome",
      "club": "Ultimo club noto o null",
      "role": "Ruolo (da OB1 o, in mancanza, dal profilo Transfermarkt)",
      "year": 1997,
      "bullets": [
        "Stato — club",
        "Valore di mercato: ...",
        "Verificato su Transfermarkt il YYYY-MM-DD — dettaglio del controllo"
      ],
      "sources": ["https://www.transfermarkt.it/.../profil/spieler/...", "..."]
    }
  ],
  "scartati_in_verifica": [
    { "nome": "...", "motivo": "perché è stato escluso" }
  ]
}
```

**Solo i profili con verifica Transfermarkt "OK" finiscono in `profiles`.**
Tutto il resto — omonimi, contratti ancora attivi altrove, giocatori già
tesserati (la fonte diceva "acquistato da X", non "svincolato da X"), fonti
singole non confermate — finisce in `scartati_in_verifica` col motivo
esplicito. **Non aggiungere a mano un nome da `scartati_in_verifica` a una
lista da inviare senza prima controllare la fonte indicata.**

## Se il campione risulta corto o vuoto

Non è un errore dello script: è lo strumento che rifiuta di riempire il
numero richiesto con dati dubbi pur di arrivare a N. Con solo `--free-only`,
al momento della stesura di questo runbook il mercato dà pochi nomi "puliti"
(su un giro di 25 candidati esaminati, tra 1 e 3 superano il controllo a
seconda del giorno). Per aumentare la resa:

- allargare la ricerca con `--geo` o togliendo filtri troppo stretti
- accettare uno scarto: meglio 1 nome vero che 3 con un omonimo dentro

## Non serve rigenerare da zero: dati già pronti

I profili di mercato invecchiano in fretta (contratti che scadono, giocatori
che firmano altrove nel giro di giorni) — per questo l'output di `--sample`
**non è versionato nel repo** (`out/` è in `.gitignore`): va sempre
rigenerato al momento del bisogno, costa un paio di minuti.

Fanno eccezione tre dossier prodotti in una sessione precedente con lo stesso
metodo (verifica manuale profilo per profilo, non solo il comando automatico
sopra, perché richiedevano di scavare anche nell'archivio grezzo oltre le 59
segnalazioni già passate dal punteggio): candidati per **Ascoli**, **Juve
Stabia** e **Ravenna**. Sono stati consegnati direttamente a Mirko come file
scaricabili nella sessione Claude in cui sono stati generati — non sono nel
repo. Se servono a Grok senza richiederli di nuovo, vanno recuperati da lì e
copiati a mano in `D:\AI\05_Strategy\out\` (o dove preferisce Mirko).

## Se qualcosa fallisce

- **Errore di rete / timeout Transfermarkt**: lo script ritenta 1-2 volte da
  solo (vedi `src/tm_scraper.py::_get`); se persiste, Transfermarkt potrebbe
  aver bloccato l'IP della macchina che lancia lo script (già segnalato come
  rischio noto per l'esecuzione da GitHub Actions in altre parti del
  progetto) — riprovare da una rete diversa.
- **`ModuleNotFoundError`**: lo script aggiunge da solo `src/` al path, non
  serve installare nulla; se l'errore persiste, verificare di lanciarlo dalla
  radice del repo (`cd ob1-serie-c` prima del comando).
- **Il campione include un nome che sembra sbagliato**: aprire il link in
  `sources` e controllare a mano — lo script fa già molti controlli
  (omonimi, contratti attivi, giocatori già tesserati) ma non è infallibile.
  Se si trova un falso positivo non ancora coperto, è un bug da segnalare e
  correggere in `scripts/find_players.py::verify_on_tm`, non da ignorare.

## Cosa NON fare

- Non inventare giocatori: solo quelli che escono da questa pipeline,
  verificati su Transfermarkt come descritto sopra.
- Non committare `.env` o segreti: questo comando specifico non ne usa, ma
  vale come regola generale del repo (vedi `CLAUDE.md`).
- Non trattare un profilo in `scartati_in_verifica` come disponibile solo
  perché il nome è quello giusto: il motivo dello scarto è lì apposta.
