# 🎯 OB1 Serie C Radar

Sistema automatico di scouting per opportunità di mercato in Serie C italiana.

## ⚡ Setup Veloce

### 1. Crea la repo su GitHub
- Nome: `ob1-serie-c`
- Public
- NO README, NO .gitignore

### 2. Configura Secrets
Settings → Secrets and variables → Actions → New repository secret
- Nome: `SERPER_API_KEY`
- Valore: [la tua key da serper.dev](https://serper.dev)

### 3. Abilita GitHub Pages
Settings → Pages → Source: `main` branch → Save

### 4. Abilita Actions
Actions → "I understand my workflows..." → Enable

### 5. Upload File
Scarica tutti i file da questo repo e carica su GitHub

## 🧪 Test Locale

```bash
pip install requests python-dotenv
python scanner.py
open index.html
📱 Accesso Mobile
Dopo il primo scan automatico:
https://[tuo-username].github.io/ob1-serie-c/
✨ Features
✅ Scan automatico ogni 6 ore
✅ Frontend mobile-first ottimizzato
✅ Filtri per categoria (Parametro Zero, Prestiti, etc.)
✅ Sistema priorità 1-5 stelle
✅ Estrazione automatica nomi giocatori
✅ Stats real-time aggregate
✅ Auto-refresh ogni 5 minuti
🎯 Tipologie Opportunità
🆓 Parametro Zero: Giocatori svincolati
✂️ Risoluzione: Contratti rescissi
🔄 Prestito: Disponibili in prestito
🏥 Infortunio: Stop lunghi (occasioni per sostituti)
📈 Serie D: Talenti da categorie inferiori
⭐ Performance: Doppiette/triplette recenti
🔧 Troubleshooting
Actions falliscono?
Verifica SERPER_API_KEY in Secrets
Settings → Actions → Workflow permissions → Read and write
GitHub Pages non funziona?
Aspetta 2-3 minuti dopo primo push
Verifica Settings → Pages sia su main branch
Scanner non trova nulla?
Normale se non ci sono notizie recenti
Riprova tra qualche ora (scan ogni 6h)
📊 Struttura
ob1-serie-c/
├── .github/workflows/auto-scan.yml  # Automazione GitHub
├── scanner.py                       # Scraper intelligente
├── index.html                       # UI mobile
├── data.json                        # Database risultati
└── README.md
🚀 Prossimi Step
[ ] Export PDF report settimanale
[ ] Notifiche Telegram per priorità 5
[ ] Integrazione Transfermarkt per valutazioni
[ ] Tracking storico movimenti
Made with ⚽ for Serie C scouting
