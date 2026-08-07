# ARCH-003 — Eccellenza: dal radar di mercato al supporto operativo di un club

**Stato**: spec, non implementata
**Data**: 2026-08-03
**Prerequisiti**: ARCH-001 (gateway LLM free-tier), ARCH-002 Fasi 1-2 (metrica, 304)
**Caso d'uso guida**: Rimini FC ripartito dall'Eccellenza, DS senza budget e senza
ufficio dati

---

## 1. Perché non basta aggiungere una lega

Oggi l'Eccellenza non esiste come lega in questo repo: è una parola dentro le
query di `italy_serie_c_d`, che accorpa Serie C, D ed Eccellenza sotto un unico
id con `trusted_sources` nazionali (tuttoc, calciomercato, gazzetta,
transfermarkt). Nessuna di quelle fonti copre il dilettantismo regionale.

Ma il problema vero è più a monte. `src/models.py` contiene **una sola entità**:

```python
@dataclass
class MarketOpportunity:
    league_id: str
    opportunity_type: OpportunityType
    player_name: str
    ...
```

Non esiste il concetto di partita, giornata, calendario o stato della rosa.
L'intero backend è modellato attorno a *una voce di mercato su un giocatore*.

Per un club che deve preparare la domenica, quello è il modello sbagliato. Le
due domande sono diverse:

| | OB1 Scout | OB1 Eccellenza |
|---|---|---|
| domanda | esiste un nome che nessuno guarda? | cosa deve fare **questo** club questa settimana? |
| entità centrale | giocatore che accumula prove | **partita** e stato della rosa |
| rischio principale | inventare un profilo | far perdere un sabato al DS |
| unità di valore | profilo verificato | ora risparmiata, trasferta evitata |

Sono due prodotti, non due configurazioni.

---

## 2. Verifica di accessibilità (3 agosto 2026)

**Fatta prima di scrivere il piano, perché tutto il resto ci poggia sopra.**

| fonte | esito | note |
|---|---|---|
| `emiliaromagna.lnd.it` | 302 → **`figccrer.it`** | Comitato Regionale Emilia-Romagna, CMS standard LND, HTTP 200 |
| `figccrer.it/comunicati` | raggiungibile | comunicati ufficiali: **giustizia sportiva** (squalifiche, ammonizioni), tesseramenti, svincoli |
| `figccrer.it` calendari/classifiche | pagine esistono (`submenu?id=45/48/51/...`) | **il contenuto arriva via iframe caricato in JS**: non è nell'HTML statico |
| `tuttocampo.it` (Eccellenza E-R) | **HTTP 403** | è l'aggregatore de facto dei dilettanti, con tabellini e formazioni: blocca lo scraping |
| tabellino per partita con **minuti** | **non trovato pubblicamente** | è l'assunzione più fragile dell'intero piano |

### Conseguenza, da dire chiaramente

L'idea di partenza — «i referti ufficiali danno i minuti veri» — **regge in Serie
C ma non è dimostrata in Eccellenza**. Le fonti regionali pubblicano con certezza
comunicati e calendari; i minuti per giocatore potrebbero semplicemente non
esistere in forma pubblica a questo livello.

Non si scrive un piano su un'assunzione non verificata: è lo stesso errore del
prefiltro di Fase C sull'altro repo, dove «scarterà metà del lavoro» si è
rivelato falso alla misura. Quindi la Fase 0 qui sotto **non è opzionale**.

---

## 3. Fase 0 — Il dato esiste? **RISOLTA il 3 agosto 2026**

La via d'accesso non era il sito: **è il canale Telegram del comitato**.

### `t.me/lndemiliaromagna` — canale pubblico, leggibile senza autenticazione

`https://t.me/s/lndemiliaromagna` restituisce HTML statico con gli ultimi 20
messaggi, paginabile all'indietro con `?before=<message_id>`. Storico attivo dal
2019, ultimo id ~4784. Nessuna API key, nessun bot da registrare, nessun 403.

Ogni comunicato è **un messaggio** con questa forma:

```
[2026-08-05T14:32]  Cu 11 del 05.08.26
                    https://www.figccrer.it/files/comunicati/2026/7504/cu11.pdf
```

Cioè: numero del CU, data, e **link diretto al PDF** con path prevedibile
`figccrer.it/files/comunicati/{anno}/{announcement_id}/cu{n}.pdf`.

### Le tre domande, con la risposta

**1. Endpoint dietro l'iframe?** Non serve più cercarlo. Il canale Telegram è una
fonte migliore di quella che stavamo inseguendo: è push invece che pull, ha id
di messaggio stabili (dedup immediato con `src/watch/seen.py`) e non richiede
rendering JS.

**2. PDF testuali o scansioni?** **Testo nativo.** Verificato su due comunicati:
CU 11 del 05/08/2026 (3 pagine, 3.920 caratteri estratti) e CU 146 del
13/04/2026 (8 pagine, 12.576 caratteri). `pypdf` basta, niente OCR, costo zero.

**3. Formazioni e minuti per partita?** **NO.** Il comunicato porta i risultati
ufficiali e i provvedimenti disciplinari, non le distinte. Quindi il Piano B
descritto sotto non è più un'ipotesi: **è il piano.**

### Cosa contiene davvero un CU in stagione (CU 146, verificato)

```
2.2 Risultati delle Giornate di Campionato
    RISULTATI UFFICIALI GARE DEL 11/04/2026

3. GIUSTIZIA SPORTIVA DILETTANTI
   IL GIUDICE SPORTIVO ... HA ADOTTATO LE DECISIONI ...
   [CATEGORIA]
   GARE DEL 11/4/2026
   PROVVEDIMENTI DISCIPLINARI
   DIRIGENTI
   I AMMONIZIONE DIFFIDA
     VIGHI ALESSIO (NOCETO)    VIGHI MATTEO (NOCETO)
   GIRONE A - 12 Giornata - R
   SORAGNA 1921 - PONTENURESE - D
```

Nome tesserato, società fra parentesi, tipo di provvedimento, girone, giornata,
gara. Formato ripetuto e regolare: **parsabile con espressioni regolari, senza
LLM**. È la fonte di grado A del framework (§4).

### Cosa si ottiene e cosa no

| dato | disponibile | da dove |
|---|---|---|
| risultati ufficiali per giornata | sì | sezione 2.2 del CU |
| squalifiche, ammonizioni, diffide, ammende | sì, con nome e società | sezione 3, Giudice Sportivo |
| calendario e gironi | sì | comunicati di inizio stagione |
| chi ha giocato | **parziale**: un ammonito era in campo | inferenza dai provvedimenti |
| minuti per giocatore | **no** | nessuna fonte pubblica trovata |
| formazioni | **no** | `tuttocampo.it` le ha ma risponde 403 |

**Conseguenza sul prodotto**: niente statistiche per giocatore in Eccellenza. Il
valore sta nella preparazione avversario, nella memoria disciplinare e nel
tempismo — non nel minutaggio. Va scritto nel materiale commerciale, non
scoperto dal cliente.

### Piano B, se i minuti non esistono

Il prodotto non muore, si restringe: preparazione avversario (rosa, marcatori,
squalificati, modulo ricorrente), memoria disciplinare della propria rosa,
radar svincolati di zona. Tutto derivabile da comunicati e classifiche. Sparisce
solo la parte statistica per giocatore — e sparisce **detto**, non nascosto
dietro una stima.

---

## 4. Il framework: catena di custodia del dato

Non un motore di punteggi: una regola di pubblicazione, in tre livelli.

**Livello 1 — Fonte graduata.** Ogni fonte porta un grado di affidabilità
(codice Admiralty):

```
A  atto ufficiale federale (comunicato, tesseramento)
B  sito ufficiale di club o lega
C  stampa locale con cronaca diretta
D  aggregatore che ricopia
E  social, dichiarazione non verificata
F  origine ignota
```

Nel repo Scout il campo `tier` esiste già in `config/sources.json` ma è letto in
un solo punto (`sources_v2.py:119`, per escludere i secondary dalla discovery):
il gate a due fonti conta **domini distinti**, non gradi. Due aggregatori che si
copiano valgono quanto federazione + stampa. Va collegato in entrambi i repo.

**Livello 2 — Fatto con provenienza.** La provenienza sta sul **campo**, non sul
profilo: `current_club` può venire da un comunicato (A) mentre `minuti` viene da
un aggregatore (D), nello stesso giocatore.

**Livello 3 — Indice oggettivo.** Nessun numero pubblicato che chi legge non
possa ricalcolare a mano.

> **La promessa vendibile**: ogni numero che diamo si risale fino all'atto che lo
> prova. Se sbagliamo, il cliente lo dimostra in trenta secondi.

È questo che rende il prodotto scientifico — non la sofisticatezza del modello,
ma la falsificabilità.

---

## 5. L'algoritmo: IGI, Indice di Guadagno Informativo

**Cosa NON è**: un predittore di rendimento futuro. Su dati da Eccellenza
sarebbe un numero inventato appoggiato sul nulla, e non va costruito.

**Cosa risolve**: il problema vero di un DS con una macchina e due occhi —
*dove vado sabato?*

```
Per ogni partita in calendario nei prossimi 14 giorni:

  IGI = Σ (gap_copertura × priorità_ruolo × decadimento) / costo_trasferta
        su tutti i giocatori "aperti" schierati in quella partita

  gap_copertura   = campi essenziali mancanti / 7
                    (identità, età, ruolo, club, minutaggio, contratto, referenze)
  priorità_ruolo  = 0..1, impostato dal DS in base a cosa gli serve adesso
  decadimento     = 1 - exp(-giorni_dall_ultima_osservazione / 60)
  costo_trasferta = km_andata_e_ritorno + 30 x ore_stimate
```

Non è previsione: è **ottimizzazione della copertura**, la stessa matematica con
cui si decide dove puntare un sensore quando ne hai uno solo. È oggettiva perché
è aritmetica su lacune misurabili. È verificabile a posteriori: a fine mese si
contano i profili chiusi per trasferta fatta.

**L'output non è un punteggio, è una frase:**

> Sabato 14, Riccione–Sant'Ermete. In campo tre dei tuoi sette nomi aperti: il
> '06 in porta (di lui sai solo il nome), il terzino sinistro (mancano contratto
> e minutaggio), il centrale del Sant'Ermete visto una volta a marzo. 22 km.
> La seconda opzione migliore è a 78 km per un nome solo.

Il sistema non ha espresso alcun giudizio su alcun giocatore: ha detto dove c'è
più da imparare per meno strada. **Decide l'uomo, il sistema alloca l'attenzione.**

---

## 6. Fasi

| Fase | Contenuto | Criterio di uscita |
|---|---|---|
| **0** | Verifica accessibilità (§3) | ✅ **fatta il 3/8/2026**: canale Telegram, PDF testuali, niente minuti |
| **1** | Grading fonti nel gate (vale anche per Scout) | il gate distingue A/B da D; si misura quanti profili oggi "corroborati" reggono la regola severa |
| **2** | `italy_eccellenza_emilia` come lega separata, fonti CRER + stampa locale | una run raccoglie ≥20 fatti verificati dalle sole fonti regionali |
| **3** | Poller Telegram + parser CU | dal canale si scaricano i CU nuovi (dedup per message id) e se ne estraggono risultati e provvedimenti senza intervento umano |
| **4** | `Fixture` + `SquadState` nel modello dati | il calendario della propria squadra è in DB e si aggiorna da solo |
| **5** | Brief del giovedì su Telegram | il DS riceve il messaggio e non deve aprire nient'altro |
| **6** | IGI | il piano settimanale propone 3 partite ordinate, con la motivazione in chiaro |

Le Fasi 5 e 6 hanno senso solo dopo la 4; la 4 solo se la 0 dà esito positivo.

---

## 7. Vincoli

- **Zero budget è un vincolo assoluto**, non un obiettivo: niente servizi a
  pagamento, niente chiavi obbligatorie. Vale `OB1_LLM_ALLOW_PAID=0` come sugli
  altri repo.
- **Il DS non apre dashboard.** Se l'output non arriva su Telegram, non esiste.
- **Minorenni**: in Eccellenza ci sono tesserati under 18. Nessuna profilazione
  social, nessuna geolocalizzazione, nessun dato familiare. Si trattano solo
  fatti sportivi da atti pubblici. Non è prudenza: è GDPR, e un club non compra
  un rischio legale.
- **Rispetto delle fonti**: `tuttocampo.it` risponde 403 allo scraping. Un 403 è
  una risposta, non un ostacolo da aggirare: o si trova un accordo, o quella
  fonte non si usa. Il canale Telegram del comitato è invece pubblico e pensato
  per essere letto: si rispettano ritmo e attribuzione.
- **I CU contengono nomi di tesserati minorenni** (categorie giovanili). Si
  trattano solo i fatti sportivi dell'atto pubblico — provvedimento, società,
  gara — e nulla di più. Nessun arricchimento social su quei nomi.
- **Non si inventano minutaggi.** Se il dato non è pubblico, il campo resta
  vuoto e il prodotto lo dichiara.

---

## 8. Cosa resta condiviso tra i due repo

Solo l'infrastruttura, mai il dominio:

- catena LLM gratuita (`src/llm/`, `free_stack`) e ledger di quota
- `src/watch/seen.py` — memoria di cosa è già stato visto
- `src/metrics.py` — costo per fatto nuovo verificato
- il grading delle fonti (Fase 1), che nasce qui e va portato anche su Scout

Il modello dati, le fonti e l'output restano separati. È questa separazione che
rende i due repo due prodotti invece che due rami dello stesso.
