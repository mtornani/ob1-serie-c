# 🚀 OB1 Scout - Deploy Cloud (Sempre Attivo)

Questa guida spiega come configurare OB1 Scout per funzionare **24/7 gratuitamente** usando GitHub Actions.

---

## 📋 Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                    GITHUB ACTIONS                           │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  Ogni 6h    │───▶│   Scraper   │───▶│  Notifier   │     │
│  │  (cron)     │    │   + AI      │    │  Telegram   │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                            │                                │
│                            ▼                                │
│                    ┌─────────────┐                          │
│                    │   GitHub    │                          │
│                    │   Pages     │                          │
│                    │  Dashboard  │                          │
│                    └─────────────┘                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     UTENTE FINALE                           │
│  ┌─────────────┐    ┌─────────────┐                        │
│  │  📱 Push    │    │  🌐 PWA     │                        │
│  │  Telegram   │    │  Dashboard  │                        │
│  └─────────────┘    └─────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Setup (10 minuti)

### Step 1: Push su GitHub

```bash
cd D:\AI\ob1-scout\ob1_serie_c\ob1-serie-c

# Se non hai già un repo
git init
git remote add origin https://github.com/TUO-USERNAME/ob1-scout-serie-c.git

# Push
git add .
git commit -m "Initial commit"
git push -u origin main
```

### Step 2: Configura i Secrets

Vai su **GitHub → Settings → Secrets and variables → Actions** e aggiungi:

| Secret Name | Valore | Come ottenerlo |
|-------------|--------|----------------|
| `SERPER_API_KEY` | `abc123...` | [serper.dev](https://serper.dev) (gratis) |
| `GEMINI_API_KEY` | `AIza...` | [aistudio.google.com](https://aistudio.google.com) (gratis) |
| `TELEGRAM_BOT_TOKEN` | `123456:ABC...` | [@BotFather](https://t.me/BotFather) su Telegram |
| `TELEGRAM_CHAT_IDS` | `123456789,987654321` | Vedi sotto come trovarlo |

#### Come trovare il Chat ID Telegram:
1. Avvia il tuo bot
2. Invia un messaggio al bot
3. Visita: `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Trova `"chat":{"id":123456789}`

### Step 3: Abilita GitHub Pages

1. Vai su **Settings → Pages**
2. Source: seleziona **GitHub Actions**
3. Salva

### Step 4: Lancia il Primo Run

1. Vai su **Actions**
2. Seleziona **"OB1 Scout - Auto Ingest & Notify"**
3. Clicca **"Run workflow"**
4. Aspetta 2-3 minuti

---

## ✅ Verifica

Dopo il primo run:

1. **Dashboard**: `https://TUO-USERNAME.github.io/ob1-scout-serie-c/`
2. **Telegram**: Dovresti ricevere una notifica push
3. **Actions**: Verifica che il workflow sia verde ✅

---

## 📱 Installare la PWA sul Telefono

### iPhone:
1. Apri Safari → vai alla dashboard
2. Tocca **Condividi** → **Aggiungi a Home**

### Android:
1. Apri Chrome → vai alla dashboard
2. Tocca **Menu (⋮)** → **Installa app**

---

## ⏰ Schedule

Il sistema gira automaticamente:

| Orario (UTC) | Orario (Italia) | Azione |
|--------------|-----------------|--------|
| 00:00 | 01:00 | Scraping + Notifiche |
| 06:00 | 07:00 | Scraping + Notifiche |
| 12:00 | 13:00 | Scraping + Notifiche |
| 18:00 | 19:00 | Scraping + Notifiche |
| Domenica 03:00 | 04:00 | Pulizia vecchi dati |

---

## 💰 Costi

**GRATIS!** ✨

- GitHub Actions: 2000 minuti/mese gratis
- GitHub Pages: Gratis
- Serper API: 2500 ricerche/mese gratis
- Gemini API: Gratis (con limiti generosi)
- Telegram Bot: Gratis

---

## 🔍 Troubleshooting

### Il workflow fallisce
1. Controlla i **Secrets** siano configurati
2. Verifica i log in **Actions → [workflow] → [run]**

### Non ricevo notifiche Telegram
1. Verifica che il bot sia avviato (invia `/start`)
2. Controlla che `TELEGRAM_CHAT_IDS` sia corretto
3. Verifica che `TELEGRAM_BOT_TOKEN` sia valido

### La dashboard non si aggiorna
1. Verifica che **GitHub Pages** sia abilitato
2. Controlla che il workflow **Deploy Dashboard** sia verde
3. Aspetta qualche minuto (cache)

---

## 🎯 Per Mauro & Chiellini

Una volta configurato:

1. **Riceveranno** notifiche Telegram automatiche quando trova nuovi svincolati
2. **Potranno** aprire la dashboard dal telefono come un'app
3. **Non dovranno** fare nulla - il sistema lavora da solo 24/7

---

## 📞 Supporto

Per problemi: mirko@matchanalysispro.online
