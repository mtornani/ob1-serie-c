#!/usr/bin/env python3
"""
OB1 Serie C - Telegram Bot (EDIZIONE PREMIUM / INVITE ONLY)
Interfaccia mobile per direttori sportivi
Con sistema di TRIAL e PAYWALL.
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from io import TextIOWrapper

# Force UTF-8 output
sys.stdout = TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

load_dotenv()

# Telegram imports
try:
    from telegram import Update, BotCommand
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        filters,
        ContextTypes,
    )

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("⚠️ python-telegram-bot non installato")
    print("   pip install python-telegram-bot")

# Import agent
from pathlib import Path

# Aggiungi la cartella src al path
bot_dir = Path(__file__).parent.resolve()
src_dir = bot_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from agent import OB1Agent

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# File per i dati delle trial
TRIAL_DB_FILE = bot_dir / "trial_users.json"
MAX_TRIAL_QUERIES = 20

class OB1PremiumBot:
    """Bot Telegram Elite per OB1 con sistema a Codici e Trial"""

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN mancante nel .env")

        # Configurazione degli Inviti
        # Codice invito -> Giorni di trial dal primo utilizzo
        self.valid_invite_codes = {
            "JUVENEXTGEN-7DAYS": 7,
            "LIVE-POC-7DAYS": 7,
            "TEST-DEV": 1,
            # Aggiungi qui nuovi codici per futuri club
        }

        self.agents: dict[int, OB1Agent] = {}
        self.users_db = self._load_db()
        self.super_admins = self._load_allowed_users()

    def _load_db(self):
        """Carica il database JSON delle utenze"""
        if TRIAL_DB_FILE.exists():
            with open(TRIAL_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_db(self):
        """Salva il database JSON delle utenze"""
        with open(TRIAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(self.users_db, f, indent=4)

    def _load_allowed_users(self) -> set:
        """Carica lista utenti SUPER ADMIN (sempre autorizzati, no limiti)"""
        users_str = os.getenv("ALLOWED_TELEGRAM_USERS", "")
        if users_str:
            return set(str(u.strip()) for u in users_str.split(",") if u.strip())
        return set()

    def _get_agent(self, user_id: int) -> OB1Agent:
        """Recupera o crea agent per utente"""
        if user_id not in self.agents:
            self.agents[user_id] = OB1Agent()
        return self.agents[user_id]

    def _check_access(self, user_id: int) -> tuple[bool, str]:
        """Verifica se l'utente ha accesso al bot e perché"""
        user_id_str = str(user_id)
        
        # 1. È l'admin creatore?
        if user_id_str in self.super_admins:
            return True, ""
            
        # 2. È registrato nel DB delle trial?
        if user_id_str not in self.users_db:
            return False, "⚠️ Non sei autorizzato. Ti serve un Codice di Invito per iniziare il Trial."
            
        user_data = self.users_db[user_id_str]
        
        # 3. La trial è scaduta temporalmente?
        exp_date = datetime.fromisoformat(user_data["expires_at"])
        if datetime.now() > exp_date:
            return False, "⏳ Il tuo Trial esclusivo è terminato. L'asimmetria informativa è esaurita. Contatta Mirko Tornani per una licenza ufficiale ai dati OB1."
            
        # 4. Ha superato le query del trial?
        if user_data["queries_used"] >= MAX_TRIAL_QUERIES:
            return False, "📈 Hai raggiunto il limite massimo di query per questo account di prova. Contatta Mirko Tornani per sbloccare l'accesso al radar."
            
        return True, ""

    def _increment_query(self, user_id: int):
        """Incrementa il contatore delle query, non fa nulla per i super_admins"""
        user_id_str = str(user_id)
        if user_id_str not in self.super_admins and user_id_str in self.users_db:
            self.users_db[user_id_str]["queries_used"] += 1
            self._save_db()

    # =========================================================================
    # HANDLERS
    # =========================================================================

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /start e attivazione Codice d'Invito"""
        user = update.effective_user
        user_id_str = str(user.id)
        
        args = context.args
        if args:
            # L'utente ha inserito un codice: /start JUVENEXTGEN-7DAYS
            invite_code = args[0]
            if invite_code in self.valid_invite_codes:
                if user_id_str not in self.users_db:
                    days_valid = self.valid_invite_codes[invite_code]
                    exp_date = datetime.now() + timedelta(days=days_valid)
                    self.users_db[user_id_str] = {
                        "username": user.username,
                        "code_used": invite_code,
                        "expires_at": exp_date.isoformat(),
                        "queries_used": 0
                    }
                    self._save_db()
                    await update.message.reply_text(f"✅ Codice accettato. Accesso Intelligence autorizzato per {days_valid} giorni.")
                else:
                    await update.message.reply_text("Hai già un account o un trial attivo.")
            else:
                await update.message.reply_text("❌ Codice d'invito non valido.")
                
        has_access, msg = self._check_access(user.id)
        if not has_access:
            await update.message.reply_text(msg + f"\n\nPer inserire un codice, usa: /start TUO-CODICE")
            return

        welcome = f"""
🎯 *OB1 Serie C Radar [PREMIUM]*

Accesso Concesso, {user.first_name}.

*Comandi operativi:*
/svincolati - Lista svincolati
/player <nome> - Analisi giocatore (agente, stats, lead-time)
/agent <agenzia> - Scopri portafoglio agenzia
/stats <min_presenze> - Filtra
/cerca <criteri> - Ricerca NLP

Oppure scrivi la tua query in linguaggio naturale. 
*Nota: Le tue query vengono monitorate per prevenire abusi sui pattern di intelligence.*
        """
        await update.message.reply_text(welcome)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        has_access, msg = self._check_access(update.effective_user.id)
        if not has_access:
            await update.message.reply_text(msg)
            return

        help_text = "📖 *Guida Operativa OB1*\nRicerche:/svincolati, /player, /agent, /stats, /cerca"
        await update.message.reply_text(help_text)

    async def _handle_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query_func, *args, **kwargs):
        """Metodo globale per instradare chiamate e decrementare token trial"""
        user_id = update.effective_user.id
        has_access, msg = self._check_access(user_id)
        if not has_access:
            await update.message.reply_text(msg)
            return
            
        await update.message.reply_text("🔍 Elaborazione tattica...")
        
        agent = self._get_agent(user_id)
        # Calling backend agent
        response = query_func(agent, *args, **kwargs)
        
        self._increment_query(user_id)
        
        await self._send_long_message(update, response)

    # Wrap dei comandi agenti usando _handle_query
    
    async def svincolati(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        role = " ".join(context.args) if context.args else None
        await self._handle_query(update, context, lambda agt: agt.find_svincolati(role=role))

    async def player(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❓ Specifica il giocatore. Es: /player Nicolas Viola")
            return
        player_name = " ".join(context.args)
        await self._handle_query(update, context, lambda agt: agt.analyze_player(player_name))

    async def summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._handle_query(update, context, lambda agt: agt.market_summary())

    async def cerca(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❓ Inserisci criteri: es /cerca difensore centrale under 25")
            return
        criteria = " ".join(context.args)
        await self._handle_query(update, context, lambda agt: agt.query(f"Cerca giocatori: {criteria}"))

    async def agent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❓ Specifica agenzia. Es: /agent Esse Sports")
            return
        agent_name = " ".join(context.args)
        await self._handle_query(update, context, lambda agt: agt.query(f"Trova giocatori rappresentati da '{agent_name}'. Mostra ruolo, età, valore, contratto."))

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❓ Es: /stats 15 o /stats 10 centrocampista")
            return
        try:
            min_appearances = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Prima mettici un numero (presenze min)")
            return
            
        role = " ".join(context.args[1:]) if len(context.args) > 1 else None
        
        query_text = f"Trova giocatori con almeno {min_appearances} presenze"
        if role: query_text += f" nel ruolo {role}"
        
        await self._handle_query(update, context, lambda agt: agt.query(query_text))

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_message = update.message.text
        if user_message.startswith('/'): return # Should not happen with ~filters.COMMAND but safety first
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        await self._handle_query(update, context, lambda agt: agt.query(user_message))

    async def _send_long_message(self, update: Update, text: str):
        MAX_LENGTH = 4000
        if len(text) <= MAX_LENGTH:
            await update.message.reply_text(text)
            return

        parts = []
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > MAX_LENGTH:
                parts.append(current)
                current = line
            else:
                current += "\n" + line if current else line

        if current: parts.append(current)

        for i, part in enumerate(parts):
            await update.message.reply_text(f"{part}\n\n({i + 1}/{len(parts)})")

    # =========================================================================
    # RUN
    # =========================================================================

    def run(self):
        print("[START] Avvio OB1 Telegram Bot (PREMIUM/TRIAL Version)...")
        app = Application.builder().token(self.token).build()

        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("svincolati", self.svincolati))
        app.add_handler(CommandHandler("player", self.player))
        app.add_handler(CommandHandler("agent", self.agent))
        app.add_handler(CommandHandler("stats", self.stats))
        app.add_handler(CommandHandler("summary", self.summary))
        app.add_handler(CommandHandler("cerca", self.cerca))

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler))

        async def set_commands(app):
            await app.bot.set_my_commands([
                BotCommand("start", "Inizia / Setup Codice"),
                BotCommand("svincolati", "Lista svincolati"),
                BotCommand("player", "Info giocatore"),
                BotCommand("agent", "Cerca per agenzia"),
                BotCommand("cerca", "Ricerca avanzata"),
            ])

        app.post_init = set_commands
        print("[OK] Bot Premium pronto! Attendo codici d'invito...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    if not TELEGRAM_AVAILABLE:
        print("[ERROR] Installa python-telegram-bot:")
        print("   pip install python-telegram-bot")
        exit(1)

    bot = OB1PremiumBot()
    bot.run()
