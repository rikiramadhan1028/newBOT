import asyncio
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import aiohttp
import json
from datetime import datetime
from utils.database import Database
from utils.security import RateLimiter, CaptchaGenerator
from services.transaction_service import TransactionService
from handlers.command_handlers import CommandHandlers

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RokuTradeBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.transaction_engine_url = os.getenv('TRANSACTION_ENGINE_URL', 'http://localhost:3000')
        self.db = Database()
        self.rate_limiter = RateLimiter()
        self.captcha = CaptchaGenerator()
        self.transaction_service = TransactionService(self.transaction_engine_url)
        self.handlers = CommandHandlers(self.db, self.transaction_service, self.captcha, self.rate_limiter)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        # Rate limiting
        if not await self.rate_limiter.allow_request(user_id):
            await update.message.reply_text("⏰ Terlalu banyak permintaan. Silakan tunggu sebentar.")
            return

        # Check if user exists
        user = await self.db.get_user(user_id)
        
        if not user:
            # New user - show captcha
            captcha_question, captcha_answer = self.captcha.generate()
            await self.db.store_captcha(user_id, captcha_answer)
            
            keyboard = [
                [InlineKeyboardButton(f"🔢 {captcha_question}", callback_data="captcha_show")],
                [InlineKeyboardButton("✅ Verifikasi", callback_data="captcha_verify")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🚀 *Selamat datang di Roku Trade!*\n\n"
                "Bot trading Solana berkecepatan tinggi dengan fitur:\n"
                "• Copy Trading\n"
                "• Token Sniping\n" 
                "• Auto TP/SL\n"
                "• Smart Wallet Analytics\n\n"
                "🔐 Silakan verifikasi terlebih dahulu:",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            await self.show_main_menu(update, context)

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("💳 Wallet", callback_data="wallet"),
             InlineKeyboardButton("💰 Buy", callback_data="buy")],
            [InlineKeyboardButton("💸 Sell", callback_data="sell"),
             InlineKeyboardButton("📊 Positions", callback_data="positions")],
            [InlineKeyboardButton("🤖 Auto Sell", callback_data="autosell"),
             InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
            [InlineKeyboardButton("📋 Copy Trade", callback_data="copytrade"),
             InlineKeyboardButton("🎯 Snipe", callback_data="snipe")],
            [InlineKeyboardButton("❓ FAQ", callback_data="faq")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = "🏠 *Roku Trade - Main Menu*\n\nPilih fitur yang ingin digunakan:"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message_text, 
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message_text,
                parse_mode='Markdown', 
                reply_markup=reply_markup
            )

    def run(self):
        app = Application.builder().token(self.token).build()
        
        # Command handlers
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("wallet", self.handlers.wallet_command))
        app.add_handler(CommandHandler("buy", self.handlers.buy_command))
        app.add_handler(CommandHandler("sell", self.handlers.sell_command))
        app.add_handler(CommandHandler("positions", self.handlers.positions_command))
        app.add_handler(CommandHandler("settings", self.handlers.settings_command))
        app.add_handler(CommandHandler("copytrade", self.handlers.copytrade_command))
        app.add_handler(CommandHandler("snipe", self.handlers.snipe_command))
        app.add_handler(CommandHandler("autosell", self.handlers.autosell_command))
        app.add_handler(CommandHandler("faq", self.handlers.faq_command))
        
        # Callback query handler
        app.add_handler(CallbackQueryHandler(self.handlers.button_callback))
        
        # Message handler for user inputs
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.handle_message))
        
        logger.info("🚀 Roku Trade Bot starting...")
        app.run_polling()

if __name__ == "__main__":
    bot = RokuTradeBot()
    bot.run()