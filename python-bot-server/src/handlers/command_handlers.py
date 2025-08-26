import asyncio
import json
import re
from typing import Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)

class CommandHandlers:
    def __init__(self, db, transaction_service, captcha, rate_limiter):
        self.db = db
        self.transaction_service = transaction_service
        self.captcha = captcha
        self.rate_limiter = rate_limiter
        self.user_states = {}  # Store user interaction states

    async def wallet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /wallet command"""
        user_id = update.effective_user.id
        
        if not await self.rate_limiter.allow_request(user_id):
            await update.message.reply_text("⏰ Terlalu banyak permintaan. Silakan tunggu.")
            return

        user = await self.db.get_user(user_id)
        if not user:
            await update.message.reply_text("❌ Silakan mulai dengan /start terlebih dahulu.")
            return

        # Get wallet balance
        balance_result = await self.transaction_service.get_balance(user['wallet_address'])
        
        if 'error' in balance_result:
            await update.message.reply_text(f"❌ Error mengambil saldo: {balance_result['error']}")
            return

        balance = balance_result['balance']
        
        # Format balance message
        message = f"💳 *Wallet Info*\n\n"
        message += f"📍 *Address:* `{user['wallet_address']}`\n"
        message += f"💰 *SOL Balance:* {balance['sol']:.6f} SOL\n\n"
        
        if balance['tokens']:
            message += "*🪙 Token Holdings:*\n"
            for token in balance['tokens'][:10]:  # Show max 10 tokens
                message += f"• {token['amount']:.6f} ({token['mint'][:8]}...)\n"
        else:
            message += "📭 Tidak ada token"

        keyboard = [
            [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw"),
             InlineKeyboardButton("📥 Import", callback_data="import_wallet")],
            [InlineKeyboardButton("📤 Export", callback_data="export_wallet"),
             InlineKeyboardButton("🔄 Refresh", callback_data="refresh_balance")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def buy_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /buy command"""
        user_id = update.effective_user.id
        
        if not await self.rate_limiter.allow_request(user_id):
            await update.message.reply_text("⏰ Terlalu banyak permintaan. Silakan tunggu.")
            return

        user = await self.db.get_user(user_id)
        if not user:
            await update.message.reply_text("❌ Silakan mulai dengan /start terlebih dahulu.")
            return

        # Parse command arguments
        args = context.args
        if len(args) >= 2:
            token_address = args[0]
            amount = args[1]
            
            if self.is_valid_solana_address(token_address) and self.is_valid_amount(amount):
                await self.execute_buy_trade(update, user, token_address, float(amount))
                return
        
        # Show buy interface
        await self.show_buy_interface(update, context)

    async def sell_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sell command"""
        user_id = update.effective_user.id
        
        if not await self.rate_limiter.allow_request(user_id):
            await update.message.reply_text("⏰ Terlalu banyak permintaan. Silakan tunggu.")
            return

        user = await self.db.get_user(user_id)
        if not user:
            await update.message.reply_text("❌ Silakan mulai dengan /start terlebih dahulu.")
            return

        # Get user positions
        positions = await self.db.get_user_positions(user_id)
        
        if not positions:
            await update.message.reply_text("📭 Anda tidak memiliki posisi aktif untuk dijual.")
            return

        await self.show_sell_interface(update, positions)

    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command"""
        user_id = update.effective_user.id
        
        user = await self.db.get_user(user_id)
        if not user:
            await update.message.reply_text("❌ Silakan mulai dengan /start terlebih dahulu.")
            return

        positions = await self.db.get_user_positions(user_id)
        
        if not positions:
            await update.message.reply_text("📭 Tidak ada posisi aktif.")
            return

        message = "📊 *Portfolio Anda*\n\n"
        total_value = 0
        
        for i, position in enumerate(positions[:15]):  # Show max 15 positions
            pnl_emoji = "🟢" if position['pnl_percent'] > 0 else "🔴"
            message += f"{pnl_emoji} *{position['token_symbol'] or 'Unknown'}*\n"
            message += f"   💰 {position['amount']:.6f}\n"
            message += f"   📈 PnL: {position['pnl_percent']:.2f}%\n"
            message += f"   💵 Entry: ${position['entry_price']:.6f}\n\n"
            
            if position['current_price']:
                total_value += position['amount'] * position['current_price']

        message += f"💎 *Total Portfolio Value:* ${total_value:.2f}\n"

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_positions"),
             InlineKeyboardButton("💸 Sell All", callback_data="sell_all")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        user_id = update.effective_user.id
        
        user = await self.db.get_user(user_id)
        if not user:
            await update.message.reply_text("❌ Silakan mulai dengan /start terlebih dahulu.")
            return

        settings = json.loads(user.get('settings', '{}'))
        
        message = "⚙️ *Pengaturan Trading*\n\n"
        message += f"🎯 *Slippage:* {settings.get('slippage', 0.5)}%\n"
        message += f"⏰ *Auto-refresh:* {settings.get('auto_refresh', False)}\n"
        message += f"🔔 *Notifications:* {settings.get('notifications', True)}\n"
        message += f"💰 *Default Buy Amount:* {settings.get('default_buy_amount', 1.0)} SOL\n"

        keyboard = [
            [InlineKeyboardButton("🎯 Set Slippage", callback_data="set_slippage"),
             InlineKeyboardButton("💰 Default Amount", callback_data="set_default_amount")],
            [InlineKeyboardButton("🔔 Notifications", callback_data="toggle_notifications"),
             InlineKeyboardButton("⏰ Auto-refresh", callback_data="toggle_auto_refresh")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def copytrade_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /copytrade command"""
        user_id = update.effective_user.id
        
        user = await self.db.get_user(user_id)
        if not user:
            await update.message.reply_text("❌ Silakan mulai dengan /start terlebih dahulu.")
            return

        message = "📋 *Copy Trading*\n\n"
        message += "Copy trade memungkinkan Anda meniru transaksi dari wallet lain secara otomatis.\n\n"
        message += "*Fitur:*\n"
        message += "• 🎯 Set rasio copy (contoh: 0.5x)\n"
        message += "• ⏰ Delay eksekusi\n"
        message += "• 💰 Batas maksimal per trade\n"
        message += "• 📊 Monitoring real-time\n"

        keyboard = [
            [InlineKeyboardButton("➕ Add Wallet", callback_data="add_copy_wallet"),
             InlineKeyboardButton("📋 My List", callback_data="copy_wallet_list")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="copy_settings"),
             InlineKeyboardButton("📊 Stats", callback_data="copy_stats")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def snipe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /snipe command"""
        user_id = update.effective_user.id
        
        user = await self.db.get_user(user_id)
        if not user:
            await update.message.reply_text("❌ Silakan mulai dengan /start terlebih dahulu.")
            return

        message = "🎯 *Token Sniping*\n\n"
        message += "Snipe token baru yang listing dengan kriteria yang Anda tentukan.\n\n"
        message += "*Fitur:*\n"
        message += "• 💧 Min. Liquidity filter\n"
        message += "• 💎 Max. Market Cap\n"
        message += "• 🛡️ Safety score minimum\n"
        message += "• ⚡ Auto-buy dengan kecepatan tinggi\n"
        message += "• 🎯 Auto-sell setelah profit target\n"

        keyboard = [
            [InlineKeyboardButton("⚙️ Configure", callback_data="snipe_configure"),
             InlineKeyboardButton("📊 Statistics", callback_data="snipe_stats")],
            [InlineKeyboardButton("✅ Enable", callback_data="snipe_enable"),
             InlineKeyboardButton("❌ Disable", callback_data="snipe_disable")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def autosell_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /autosell command"""
        user_id = update.effective_user.id
        
        user = await self.db.get_user(user_id)
        if not user:
            await update.message.reply_text("❌ Silakan mulai dengan /start terlebih dahulu.")
            return

        message = "🤖 *Auto Sell Settings*\n\n"
        message += "Atur Take Profit dan Stop Loss otomatis untuk semua posisi Anda.\n\n"
        message += "*Fitur:*\n"
        message += "• 🎯 Take Profit (TP)\n"
        message += "• 🛑 Stop Loss (SL)\n"
        message += "• 📈 Trailing Stop\n"
        message += "• ⚡ Eksekusi otomatis 24/7\n"

        keyboard = [
            [InlineKeyboardButton("🎯 Set TP/SL", callback_data="set_tp_sl"),
             InlineKeyboardButton("📈 Trailing Stop", callback_data="set_trailing")],
            [InlineKeyboardButton("📊 Active Orders", callback_data="active_auto_orders"),
             InlineKeyboardButton("⚙️ Global Settings", callback_data="global_auto_settings")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def faq_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /faq command"""
        message = "❓ *FAQ - Roku Trade*\n\n"
        message += "*Q: Bagaimana cara mulai trading?*\n"
        message += "A: Gunakan /start untuk membuat wallet, lalu /buy untuk membeli token.\n\n"
        message += "*Q: Apakah private key saya aman?*\n"
        message += "A: Ya, semua private key dienkripsi dengan AES-256.\n\n"
        message += "*Q: Bagaimana cara copy trading?*\n"
        message += "A: Gunakan /copytrade untuk menambah wallet yang ingin di-copy.\n\n"
        message += "*Q: Apa itu token sniping?*\n"
        message += "A: Fitur untuk membeli token baru secara otomatis saat listing.\n\n"
        message += "*Q: Berapa fee trading?*\n"
        message += "A: Hanya network fee Solana, tidak ada fee tambahan dari bot.\n\n"

        keyboard = [
            [InlineKeyboardButton("💬 Support", url="https://t.me/rokutrade_support"),
             InlineKeyboardButton("📚 Guide", url="https://rokutrade.com/guide")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all button callbacks"""
        query = update.callback_query
        await query.answer()
        
        callback_data = query.data
        user_id = query.from_user.id
        
        # Route callbacks to appropriate handlers
        if callback_data == "main_menu":
            await self.show_main_menu(query, context)
        elif callback_data == "captcha_verify":
            await self.handle_captcha_verify(query, context)
        elif callback_data.startswith("wallet"):
            await self.handle_wallet_callbacks(query, context, callback_data)
        elif callback_data.startswith("buy"):
            await self.handle_buy_callbacks(query, context, callback_data)
        elif callback_data.startswith("sell"):
            await self.handle_sell_callbacks(query, context, callback_data)
        elif callback_data.startswith("copy"):
            await self.handle_copy_callbacks(query, context, callback_data)
        elif callback_data.startswith("snipe"):
            await self.handle_snipe_callbacks(query, context, callback_data)
        elif callback_data.startswith("auto"):
            await self.handle_auto_callbacks(query, context, callback_data)
        else:
            await self.handle_generic_callbacks(query, context, callback_data)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages based on user state"""
        user_id = update.effective_user.id
        message_text = update.message.text
        
        # Check if user is in a specific state
        user_state = self.user_states.get(user_id, {})
        
        if user_state.get('waiting_for') == 'captcha_answer':
            await self.verify_captcha(update, context, message_text)
        elif user_state.get('waiting_for') == 'wallet_import':
            await self.import_wallet(update, context, message_text)
        elif user_state.get('waiting_for') == 'buy_token_address':
            await self.handle_buy_token_input(update, context, message_text)
        elif user_state.get('waiting_for') == 'buy_amount':
            await self.handle_buy_amount_input(update, context, message_text)
        elif user_state.get('waiting_for') == 'copy_wallet_address':
            await self.handle_copy_wallet_input(update, context, message_text)
        else:
            # Default response for unrecognized messages
            await update.message.reply_text(
                "🤖 Saya tidak mengerti pesan ini. Gunakan /start untuk melihat menu utama."
            )

    # Helper methods
    def is_valid_solana_address(self, address: str) -> bool:
        """Validate Solana address format"""
        return bool(re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', address))

    def is_valid_amount(self, amount: str) -> bool:
        """Validate amount format"""
        try:
            value = float(amount)
            return value > 0
        except ValueError:
            return False

    async def show_buy_interface(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show buy token interface"""
        message = "🛒 *Buy Token*\n\n"
        message += "Masukkan alamat kontrak token yang ingin dibeli:\n"
        message += "Contoh: `11111111111111111111111111112`\n\n"
        message += "Atau pilih quick buy dengan jumlah SOL:"

        keyboard = [
            [InlineKeyboardButton("0.1 SOL", callback_data="quick_buy_0.1"),
             InlineKeyboardButton("0.5 SOL", callback_data="quick_buy_0.5")],
            [InlineKeyboardButton("1.0 SOL", callback_data="quick_buy_1.0"),
             InlineKeyboardButton("2.0 SOL", callback_data="quick_buy_2.0")],
            [InlineKeyboardButton("💰 Custom", callback_data="custom_buy"),
             InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)
        
        # Set user state to expect token address
        self.user_states[update.effective_user.id] = {'waiting_for': 'buy_token_address'}

    async def show_sell_interface(self, update: Update, positions):
        """Show sell positions interface"""
        message = "💸 *Sell Positions*\n\n"
        message += "Pilih posisi yang ingin dijual:\n\n"
        
        keyboard = []
        for i, position in enumerate(positions[:10]):
            pnl_emoji = "🟢" if position['pnl_percent'] > 0 else "🔴"
            button_text = f"{pnl_emoji} {position['token_symbol']} ({position['pnl_percent']:.2f}%)"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"sell_position_{position['id']}")])
        
        keyboard.extend([
            [InlineKeyboardButton("💸 Sell All", callback_data="sell_all_positions"),
             InlineKeyboardButton("🔄 Refresh", callback_data="refresh_positions")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def execute_buy_trade(self, update: Update, user: dict, token_address: str, amount: float):
        """Execute buy trade"""
        try:
            # Get user settings
            settings = json.loads(user.get('settings', '{}'))
            slippage = settings.get('slippage', 0.5)
            
            message = f"🔄 Sedang memproses pembelian...\n\n"
            message += f"📍 Token: `{token_address}`\n"
            message += f"💰 Jumlah: {amount} SOL\n"
            message += f"🎯 Slippage: {slippage}%"
            
            status_message = await update.message.reply_text(message, parse_mode='Markdown')
            
            # Execute trade via transaction service
            result = await self.transaction_service.execute_buy(
                user['wallet_address'],
                token_address,
                amount,
                slippage
            )
            
            if result.get('success'):
                success_message = f"✅ *Pembelian Berhasil!*\n\n"
                success_message += f"📍 Token: `{token_address}`\n"
                success_message += f"💰 Jumlah: {amount} SOL\n"
                success_message += f"🔗 TX: `{result['tx_hash']}`\n"
                success_message += f"⏰ Waktu: {result['timestamp']}"
                
                await status_message.edit_text(success_message, parse_mode='Markdown')
                
                # Save position to database
                await self.db.save_position(
                    user['user_id'],
                    token_address,
                    result['tokens_received'],
                    result['sol_price'],
                    result['tx_hash']
                )
            else:
                error_message = f"❌ *Pembelian Gagal*\n\n"
                error_message += f"Error: {result.get('error', 'Unknown error')}"
                await status_message.edit_text(error_message, parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"Error executing buy trade: {e}")
            await update.message.reply_text(f"❌ Terjadi kesalahan: {str(e)}")

    async def show_main_menu(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu"""
        message = "🏠 *Roku Trade - Main Menu*\n\n"
        message += "Pilih fitur yang ingin digunakan:"
        
        keyboard = [
            [InlineKeyboardButton("💳 Wallet", callback_data="wallet"),
             InlineKeyboardButton("🛒 Buy", callback_data="buy")],
            [InlineKeyboardButton("💸 Sell", callback_data="sell"),
             InlineKeyboardButton("📊 Positions", callback_data="positions")],
            [InlineKeyboardButton("📋 Copy Trade", callback_data="copytrade"),
             InlineKeyboardButton("🎯 Snipe", callback_data="snipe")],
            [InlineKeyboardButton("🤖 Auto Sell", callback_data="autosell"),
             InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_captcha_verify(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle captcha verification"""
        user_id = query.from_user.id
        
        # Generate captcha
        captcha_result = await self.captcha.generate_captcha(user_id)
        
        if captcha_result:
            self.user_states[user_id] = {
                'waiting_for': 'captcha_answer',
                'captcha_answer': captcha_result['answer']
            }
            
            message = f"🤖 *Verifikasi CAPTCHA*\n\n"
            message += f"Silakan jawab: {captcha_result['question']}"
            
            await query.edit_message_text(message, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Gagal membuat CAPTCHA. Coba lagi.")

    async def verify_captcha(self, update: Update, context: ContextTypes.DEFAULT_TYPE, answer: str):
        """Verify captcha answer"""
        user_id = update.effective_user.id
        user_state = self.user_states.get(user_id, {})
        
        if user_state.get('captcha_answer') == answer.strip():
            # Clear user state
            self.user_states.pop(user_id, None)
            
            await update.message.reply_text(
                "✅ *Verifikasi berhasil!*\n\n"
                "Selamat datang di Roku Trade. Gunakan menu di bawah untuk mulai trading:",
                parse_mode='Markdown'
            )
            
            # Show main menu
            await self.show_main_menu_message(update, context)
        else:
            await update.message.reply_text(
                "❌ Jawaban salah. Coba lagi atau gunakan /start untuk CAPTCHA baru."
            )

    async def show_main_menu_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu as message"""
        message = "🏠 *Roku Trade - Main Menu*\n\n"
        message += "Pilih fitur yang ingin digunakan:"
        
        keyboard = [
            [InlineKeyboardButton("💳 Wallet", callback_data="wallet"),
             InlineKeyboardButton("🛒 Buy", callback_data="buy")],
            [InlineKeyboardButton("💸 Sell", callback_data="sell"),
             InlineKeyboardButton("📊 Positions", callback_data="positions")],
            [InlineKeyboardButton("📋 Copy Trade", callback_data="copytrade"),
             InlineKeyboardButton("🎯 Snipe", callback_data="snipe")],
            [InlineKeyboardButton("🤖 Auto Sell", callback_data="autosell"),
             InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_wallet_callbacks(self, query, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Handle wallet-related callbacks"""
        user_id = query.from_user.id
        
        if callback_data == "wallet":
            await self.wallet_command_callback(query, context)
        elif callback_data == "withdraw":
            await self.handle_withdraw(query, context)
        elif callback_data == "import_wallet":
            await self.handle_import_wallet(query, context)
        elif callback_data == "export_wallet":
            await self.handle_export_wallet(query, context)
        elif callback_data == "refresh_balance":
            await self.handle_refresh_balance(query, context)

    async def wallet_command_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle wallet command via callback"""
        user_id = query.from_user.id
        
        user = await self.db.get_user(user_id)
        if not user:
            await query.edit_message_text("❌ Silakan mulai dengan /start terlebih dahulu.")
            return

        balance_result = await self.transaction_service.get_balance(user['wallet_address'])
        
        if 'error' in balance_result:
            await query.edit_message_text(f"❌ Error mengambil saldo: {balance_result['error']}")
            return

        balance = balance_result['balance']
        
        message = f"💳 *Wallet Info*\n\n"
        message += f"📍 *Address:* `{user['wallet_address']}`\n"
        message += f"💰 *SOL Balance:* {balance['sol']:.6f} SOL\n\n"
        
        if balance['tokens']:
            message += "*🪙 Token Holdings:*\n"
            for token in balance['tokens'][:10]:
                message += f"• {token['amount']:.6f} ({token['mint'][:8]}...)\n"
        else:
            message += "📭 Tidak ada token"

        keyboard = [
            [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw"),
             InlineKeyboardButton("📥 Import", callback_data="import_wallet")],
            [InlineKeyboardButton("📤 Export", callback_data="export_wallet"),
             InlineKeyboardButton("🔄 Refresh", callback_data="refresh_balance")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_withdraw(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle withdraw functionality"""
        message = "💸 *Withdraw SOL*\n\n"
        message += "Masukkan alamat tujuan dan jumlah SOL yang ingin ditarik.\n"
        message += "Format: `alamat_tujuan jumlah`\n\n"
        message += "Contoh: `11111111111111111111111111112 0.5`"
        
        await query.edit_message_text(message, parse_mode='Markdown')
        self.user_states[query.from_user.id] = {'waiting_for': 'withdraw_details'}

    async def handle_import_wallet(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle wallet import"""
        message = "📥 *Import Wallet*\n\n"
        message += "⚠️ **PERINGATAN:** Pastikan Anda berada di chat privat!\n\n"
        message += "Kirim private key wallet Solana Anda.\n"
        message += "Private key akan dienkripsi dan disimpan dengan aman.\n\n"
        message += "Format: Base58 string (88 karakter)"
        
        await query.edit_message_text(message, parse_mode='Markdown')
        self.user_states[query.from_user.id] = {'waiting_for': 'wallet_import'}

    async def import_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE, private_key: str):
        """Import wallet from private key"""
        user_id = update.effective_user.id
        
        try:
            # Validate private key format
            if not self.is_valid_private_key(private_key):
                await update.message.reply_text("❌ Format private key tidak valid.")
                return
            
            # Import wallet via transaction service
            result = await self.transaction_service.import_wallet(user_id, private_key)
            
            if result.get('success'):
                await self.db.update_user_wallet(user_id, result['wallet_address'], result['encrypted_key'])
                
                await update.message.reply_text(
                    f"✅ *Wallet berhasil diimport!*\n\n"
                    f"📍 Address: `{result['wallet_address']}`",
                    parse_mode='Markdown'
                )
                
                # Clear private key from memory
                private_key = None
            else:
                await update.message.reply_text(f"❌ Gagal import wallet: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Error importing wallet: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat import wallet.")
        
        # Clear user state
        self.user_states.pop(user_id, None)

    def is_valid_private_key(self, private_key: str) -> bool:
        """Validate private key format"""
        try:
            # Basic validation for base58 string
            return len(private_key) >= 80 and len(private_key) <= 90
        except:
            return False

    async def handle_export_wallet(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle wallet export"""
        user_id = query.from_user.id
        
        user = await self.db.get_user(user_id)
        if not user or not user.get('encrypted_private_key'):
            await query.edit_message_text("❌ Tidak ada wallet untuk diekspor.")
            return
        
        try:
            # Decrypt private key
            private_key = await self.transaction_service.decrypt_private_key(user['encrypted_private_key'])
            
            message = f"📤 *Export Wallet*\n\n"
            message += f"⚠️ **JANGAN BAGIKAN DENGAN SIAPAPUN!**\n\n"
            message += f"🔑 Private Key:\n`{private_key}`\n\n"
            message += f"📍 Address: `{user['wallet_address']}`"
            
            await query.edit_message_text(message, parse_mode='Markdown')
            
            # Clear private key from memory
            private_key = None
            
        except Exception as e:
            logger.error(f"Error exporting wallet: {e}")
            await query.edit_message_text("❌ Gagal mengekspor wallet.")

    async def handle_refresh_balance(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Refresh wallet balance"""
        await self.wallet_command_callback(query, context)

    async def handle_buy_callbacks(self, query, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Handle buy-related callbacks"""
        if callback_data == "buy":
            await self.show_buy_interface_callback(query, context)
        elif callback_data.startswith("quick_buy_"):
            amount = float(callback_data.split("_")[-1])
            await self.handle_quick_buy(query, context, amount)
        elif callback_data == "custom_buy":
            await self.handle_custom_buy(query, context)

    async def show_buy_interface_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Show buy interface via callback"""
        message = "🛒 *Buy Token*\n\n"
        message += "Masukkan alamat kontrak token yang ingin dibeli:\n"
        message += "Contoh: `11111111111111111111111111112`\n\n"
        message += "Atau pilih quick buy dengan jumlah SOL:"

        keyboard = [
            [InlineKeyboardButton("0.1 SOL", callback_data="quick_buy_0.1"),
             InlineKeyboardButton("0.5 SOL", callback_data="quick_buy_0.5")],
            [InlineKeyboardButton("1.0 SOL", callback_data="quick_buy_1.0"),
             InlineKeyboardButton("2.0 SOL", callback_data="quick_buy_2.0")],
            [InlineKeyboardButton("💰 Custom", callback_data="custom_buy"),
             InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
        
        self.user_states[query.from_user.id] = {'waiting_for': 'buy_token_address'}

    async def handle_quick_buy(self, query, context: ContextTypes.DEFAULT_TYPE, amount: float):
        """Handle quick buy with preset amount"""
        message = f"🛒 *Quick Buy - {amount} SOL*\n\n"
        message += "Masukkan alamat kontrak token:"
        
        await query.edit_message_text(message, parse_mode='Markdown')
        
        self.user_states[query.from_user.id] = {
            'waiting_for': 'buy_token_address',
            'buy_amount': amount
        }

    async def handle_custom_buy(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle custom buy amount"""
        message = "💰 *Custom Buy*\n\n"
        message += "Masukkan alamat token dan jumlah SOL:\n"
        message += "Format: `alamat_token jumlah_sol`\n\n"
        message += "Contoh: `11111111111111111111111111112 1.5`"
        
        await query.edit_message_text(message, parse_mode='Markdown')
        
        self.user_states[query.from_user.id] = {'waiting_for': 'custom_buy_details'}

    async def handle_buy_token_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, token_address: str):
        """Handle token address input for buy"""
        user_id = update.effective_user.id
        user_state = self.user_states.get(user_id, {})
        
        if not self.is_valid_solana_address(token_address):
            await update.message.reply_text("❌ Alamat token tidak valid.")
            return
        
        buy_amount = user_state.get('buy_amount')
        
        if buy_amount:
            # Execute trade with preset amount
            user = await self.db.get_user(user_id)
            if user:
                await self.execute_buy_trade(update, user, token_address, buy_amount)
            
            self.user_states.pop(user_id, None)
        else:
            # Ask for amount
            message = f"💰 *Jumlah Pembelian*\n\n"
            message += f"Token: `{token_address}`\n\n"
            message += "Masukkan jumlah SOL yang ingin digunakan:"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
            self.user_states[user_id] = {
                'waiting_for': 'buy_amount',
                'token_address': token_address
            }

    async def handle_buy_amount_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, amount_str: str):
        """Handle buy amount input"""
        user_id = update.effective_user.id
        user_state = self.user_states.get(user_id, {})
        
        if not self.is_valid_amount(amount_str):
            await update.message.reply_text("❌ Jumlah tidak valid.")
            return
        
        token_address = user_state.get('token_address')
        amount = float(amount_str)
        
        user = await self.db.get_user(user_id)
        if user:
            await self.execute_buy_trade(update, user, token_address, amount)
        
        self.user_states.pop(user_id, None)

    async def handle_sell_callbacks(self, query, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Handle sell-related callbacks"""
        if callback_data == "sell":
            await self.show_sell_interface_callback(query, context)
        elif callback_data.startswith("sell_position_"):
            position_id = callback_data.split("_")[-1]
            await self.handle_sell_position(query, context, position_id)
        elif callback_data == "sell_all_positions":
            await self.handle_sell_all_positions(query, context)
        elif callback_data == "refresh_positions":
            await self.handle_refresh_positions(query, context)

    async def show_sell_interface_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Show sell interface via callback"""
        user_id = query.from_user.id
        positions = await self.db.get_user_positions(user_id)
        
        if not positions:
            await query.edit_message_text("📭 Anda tidak memiliki posisi aktif untuk dijual.")
            return

        message = "💸 *Sell Positions*\n\n"
        message += "Pilih posisi yang ingin dijual:\n\n"
        
        keyboard = []
        for i, position in enumerate(positions[:10]):
            pnl_emoji = "🟢" if position['pnl_percent'] > 0 else "🔴"
            button_text = f"{pnl_emoji} {position['token_symbol']} ({position['pnl_percent']:.2f}%)"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"sell_position_{position['id']}")])
        
        keyboard.extend([
            [InlineKeyboardButton("💸 Sell All", callback_data="sell_all_positions"),
             InlineKeyboardButton("🔄 Refresh", callback_data="refresh_positions")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_sell_position(self, query, context: ContextTypes.DEFAULT_TYPE, position_id: str):
        """Handle selling specific position"""
        user_id = query.from_user.id
        
        try:
            # Get position details
            position = await self.db.get_position(position_id)
            if not position or position['user_id'] != user_id:
                await query.edit_message_text("❌ Posisi tidak ditemukan.")
                return
            
            # Execute sell
            result = await self.transaction_service.execute_sell(
                position['wallet_address'],
                position['token_address'],
                position['amount']
            )
            
            if result.get('success'):
                # Update position status
                await self.db.close_position(position_id, result['tx_hash'], result['sol_received'])
                
                message = f"✅ *Penjualan Berhasil!*\n\n"
                message += f"📍 Token: {position['token_symbol']}\n"
                message += f"💰 Jumlah: {position['amount']:.6f}\n"
                message += f"💵 SOL Diterima: {result['sol_received']:.6f}\n"
                message += f"📈 PnL: {result['pnl_percent']:.2f}%\n"
                message += f"🔗 TX: `{result['tx_hash']}`"
                
                await query.edit_message_text(message, parse_mode='Markdown')
            else:
                await query.edit_message_text(f"❌ Penjualan gagal: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Error selling position: {e}")
            await query.edit_message_text("❌ Terjadi kesalahan saat menjual posisi.")

    async def handle_sell_all_positions(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle sell all positions"""
        user_id = query.from_user.id
        
        confirmation_message = "⚠️ *Konfirmasi Sell All*\n\n"
        confirmation_message += "Anda yakin ingin menjual SEMUA posisi?\n"
        confirmation_message += "Aksi ini tidak dapat dibatalkan!"
        
        keyboard = [
            [InlineKeyboardButton("✅ Ya, Jual Semua", callback_data="confirm_sell_all"),
             InlineKeyboardButton("❌ Batal", callback_data="cancel_sell_all")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(confirmation_message, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_refresh_positions(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Refresh positions display"""
        await self.show_sell_interface_callback(query, context)

    async def handle_copy_callbacks(self, query, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Handle copy trade callbacks"""
        if callback_data == "copytrade":
            await self.copytrade_command_callback(query, context)
        elif callback_data == "add_copy_wallet":
            await self.handle_add_copy_wallet(query, context)
        elif callback_data == "copy_wallet_list":
            await self.handle_copy_wallet_list(query, context)

    async def copytrade_command_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle copytrade command via callback"""
        message = "📋 *Copy Trading*\n\n"
        message += "Copy trade memungkinkan Anda meniru transaksi dari wallet lain secara otomatis.\n\n"
        message += "*Fitur:*\n"
        message += "• 🎯 Set rasio copy (contoh: 0.5x)\n"
        message += "• ⏰ Delay eksekusi\n"
        message += "• 💰 Batas maksimal per trade\n"
        message += "• 📊 Monitoring real-time\n"

        keyboard = [
            [InlineKeyboardButton("➕ Add Wallet", callback_data="add_copy_wallet"),
             InlineKeyboardButton("📋 My List", callback_data="copy_wallet_list")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="copy_settings"),
             InlineKeyboardButton("📊 Stats", callback_data="copy_stats")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_add_copy_wallet(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle add copy wallet"""
        message = "➕ *Add Copy Wallet*\n\n"
        message += "Masukkan alamat wallet yang ingin di-copy:\n"
        message += "Pastikan alamat valid dan aktif trading.\n\n"
        message += "Contoh: `11111111111111111111111111112`"
        
        await query.edit_message_text(message, parse_mode='Markdown')
        self.user_states[query.from_user.id] = {'waiting_for': 'copy_wallet_address'}

    async def handle_copy_wallet_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, wallet_address: str):
        """Handle copy wallet address input"""
        user_id = update.effective_user.id
        
        if not self.is_valid_solana_address(wallet_address):
            await update.message.reply_text("❌ Alamat wallet tidak valid.")
            return
        
        try:
            # Add to copy list
            result = await self.db.add_copy_wallet(user_id, wallet_address)
            
            if result:
                message = f"✅ *Wallet berhasil ditambahkan!*\n\n"
                message += f"📍 Address: `{wallet_address}`\n"
                message += f"🎯 Rasio: 1.0x (default)\n"
                message += f"💰 Max per trade: 1.0 SOL (default)\n\n"
                message += "Gunakan menu Copy Settings untuk mengatur rasio dan limit."
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text("❌ Wallet sudah ada dalam daftar copy.")
                
        except Exception as e:
            logger.error(f"Error adding copy wallet: {e}")
            await update.message.reply_text("❌ Terjadi kesalahan saat menambah wallet.")
        
        self.user_states.pop(user_id, None)

    async def handle_copy_wallet_list(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Show copy wallet list"""
        user_id = query.from_user.id
        
        copy_wallets = await self.db.get_copy_wallets(user_id)
        
        if not copy_wallets:
            await query.edit_message_text("📭 Belum ada wallet dalam daftar copy.")
            return
        
        message = "📋 *Copy Wallet List*\n\n"
        
        for i, wallet in enumerate(copy_wallets[:10]):
            status_emoji = "🟢" if wallet['active'] else "🔴"
            message += f"{status_emoji} `{wallet['address'][:8]}...{wallet['address'][-8:]}`\n"
            message += f"   🎯 Rasio: {wallet['ratio']}x\n"
            message += f"   💰 Max: {wallet['max_amount']} SOL\n\n"
        
        keyboard = [
            [InlineKeyboardButton("⚙️ Manage", callback_data="manage_copy_wallets"),
             InlineKeyboardButton("➕ Add New", callback_data="add_copy_wallet")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_snipe_callbacks(self, query, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Handle snipe-related callbacks"""
        if callback_data == "snipe":
            await self.snipe_command_callback(query, context)
        elif callback_data == "snipe_configure":
            await self.handle_snipe_configure(query, context)
        elif callback_data == "snipe_enable":
            await self.handle_snipe_enable(query, context)
        elif callback_data == "snipe_disable":
            await self.handle_snipe_disable(query, context)

    async def snipe_command_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle snipe command via callback"""
        message = "🎯 *Token Sniping*\n\n"
        message += "Snipe token baru yang listing dengan kriteria yang Anda tentukan.\n\n"
        message += "*Fitur:*\n"
        message += "• 💧 Min. Liquidity filter\n"
        message += "• 💎 Max. Market Cap\n"
        message += "• 🛡️ Safety score minimum\n"
        message += "• ⚡ Auto-buy dengan kecepatan tinggi\n"
        message += "• 🎯 Auto-sell setelah profit target\n"

        keyboard = [
            [InlineKeyboardButton("⚙️ Configure", callback_data="snipe_configure"),
             InlineKeyboardButton("📊 Statistics", callback_data="snipe_stats")],
            [InlineKeyboardButton("✅ Enable", callback_data="snipe_enable"),
             InlineKeyboardButton("❌ Disable", callback_data="snipe_disable")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_snipe_configure(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle snipe configuration"""
        user_id = query.from_user.id
        
        snipe_settings = await self.db.get_snipe_settings(user_id)
        
        message = "⚙️ *Snipe Configuration*\n\n"
        message += f"💧 Min. Liquidity: ${snipe_settings.get('min_liquidity', 1000)}\n"
        message += f"💎 Max. Market Cap: ${snipe_settings.get('max_mcap', 100000)}\n"
        message += f"🛡️ Min. Safety Score: {snipe_settings.get('min_safety', 7)}/10\n"
        message += f"💰 Buy Amount: {snipe_settings.get('buy_amount', 0.1)} SOL\n"
        message += f"🎯 Profit Target: {snipe_settings.get('profit_target', 200)}%\n"
        message += f"🛑 Stop Loss: {snipe_settings.get('stop_loss', 50)}%\n"
        
        keyboard = [
            [InlineKeyboardButton("💧 Liquidity", callback_data="set_snipe_liquidity"),
             InlineKeyboardButton("💎 Market Cap", callback_data="set_snipe_mcap")],
            [InlineKeyboardButton("🛡️ Safety", callback_data="set_snipe_safety"),
             InlineKeyboardButton("💰 Amount", callback_data="set_snipe_amount")],
            [InlineKeyboardButton("🎯 Profit", callback_data="set_snipe_profit"),
             InlineKeyboardButton("🛑 Stop Loss", callback_data="set_snipe_sl")],
            [InlineKeyboardButton("💾 Save", callback_data="save_snipe_config"),
             InlineKeyboardButton("🔙 Back", callback_data="snipe")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_snipe_enable(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Enable sniping"""
        user_id = query.from_user.id
        
        result = await self.db.update_snipe_status(user_id, True)
        
        if result:
            await query.edit_message_text(
                "✅ *Sniping Enabled!*\n\n"
                "Bot akan mulai monitoring token baru sesuai kriteria Anda.\n"
                "Pastikan wallet memiliki cukup SOL untuk auto-buy."
            )
        else:
            await query.edit_message_text("❌ Gagal mengaktifkan sniping.")

    async def handle_snipe_disable(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Disable sniping"""
        user_id = query.from_user.id
        
        result = await self.db.update_snipe_status(user_id, False)
        
        if result:
            await query.edit_message_text(
                "❌ *Sniping Disabled*\n\n"
                "Bot berhenti monitoring token baru."
            )
        else:
            await query.edit_message_text("❌ Gagal menonaktifkan sniping.")

    async def handle_auto_callbacks(self, query, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Handle auto sell callbacks"""
        if callback_data == "autosell":
            await self.autosell_command_callback(query, context)
        elif callback_data == "set_tp_sl":
            await self.handle_set_tp_sl(query, context)
        elif callback_data == "active_auto_orders":
            await self.handle_active_auto_orders(query, context)

    async def autosell_command_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle autosell command via callback"""
        message = "🤖 *Auto Sell Settings*\n\n"
        message += "Atur Take Profit dan Stop Loss otomatis untuk semua posisi Anda.\n\n"
        message += "*Fitur:*\n"
        message += "• 🎯 Take Profit (TP)\n"
        message += "• 🛑 Stop Loss (SL)\n"
        message += "• 📈 Trailing Stop\n"
        message += "• ⚡ Eksekusi otomatis 24/7\n"

        keyboard = [
            [InlineKeyboardButton("🎯 Set TP/SL", callback_data="set_tp_sl"),
             InlineKeyboardButton("📈 Trailing Stop", callback_data="set_trailing")],
            [InlineKeyboardButton("📊 Active Orders", callback_data="active_auto_orders"),
             InlineKeyboardButton("⚙️ Global Settings", callback_data="global_auto_settings")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_set_tp_sl(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle set TP/SL"""
        message = "🎯 *Set Take Profit & Stop Loss*\n\n"
        message += "Masukkan nilai TP dan SL dalam persen:\n"
        message += "Format: `take_profit stop_loss`\n\n"
        message += "Contoh: `200 50` (TP 200%, SL 50%)\n"
        message += "Default: TP 100%, SL 30%"
        
        await query.edit_message_text(message, parse_mode='Markdown')
        self.user_states[query.from_user.id] = {'waiting_for': 'tp_sl_values'}

    async def handle_active_auto_orders(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Show active auto orders"""
        user_id = query.from_user.id
        
        auto_orders = await self.db.get_auto_orders(user_id)
        
        if not auto_orders:
            await query.edit_message_text("📭 Tidak ada auto order aktif.")
            return
        
        message = "📊 *Active Auto Orders*\n\n"
        
        for order in auto_orders[:10]:
            status_emoji = "🟢" if order['active'] else "🔴"
            order_type = "🎯 TP" if order['order_type'] == 'take_profit' else "🛑 SL"
            
            message += f"{status_emoji} {order_type} - {order['token_symbol']}\n"
            message += f"   💰 Amount: {order['amount']:.6f}\n"
            message += f"   📈 Target: {order['target_percent']}%\n"
            message += f"   💵 Current: ${order['current_price']:.6f}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("❌ Cancel All", callback_data="cancel_all_auto"),
             InlineKeyboardButton("🔄 Refresh", callback_data="refresh_auto_orders")],
            [InlineKeyboardButton("🔙 Back", callback_data="autosell")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_generic_callbacks(self, query, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
        """Handle other generic callbacks"""
        if callback_data == "refresh_balance":
            await self.handle_refresh_balance(query, context)
        elif callback_data == "refresh_positions":
            await self.handle_refresh_positions(query, context)
        elif callback_data == "settings":
            await self.settings_command_callback(query, context)
        elif callback_data == "positions":
            await self.positions_command_callback(query, context)
        else:
            await query.edit_message_text("❌ Fungsi belum tersedia.")

    async def settings_command_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle settings command via callback"""
        user_id = query.from_user.id
        
        user = await self.db.get_user(user_id)
        if not user:
            await query.edit_message_text("❌ Silakan mulai dengan /start terlebih dahulu.")
            return

        settings = json.loads(user.get('settings', '{}'))
        
        message = "⚙️ *Pengaturan Trading*\n\n"
        message += f"🎯 *Slippage:* {settings.get('slippage', 0.5)}%\n"
        message += f"⏰ *Auto-refresh:* {settings.get('auto_refresh', False)}\n"
        message += f"🔔 *Notifications:* {settings.get('notifications', True)}\n"
        message += f"💰 *Default Buy Amount:* {settings.get('default_buy_amount', 1.0)} SOL\n"

        keyboard = [
            [InlineKeyboardButton("🎯 Set Slippage", callback_data="set_slippage"),
             InlineKeyboardButton("💰 Default Amount", callback_data="set_default_amount")],
            [InlineKeyboardButton("🔔 Notifications", callback_data="toggle_notifications"),
             InlineKeyboardButton("⏰ Auto-refresh", callback_data="toggle_auto_refresh")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def positions_command_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle positions command via callback"""
        user_id = query.from_user.id
        
        user = await self.db.get_user(user_id)
        if not user:
            await query.edit_message_text("❌ Silakan mulai dengan /start terlebih dahulu.")
            return

        positions = await self.db.get_user_positions(user_id)
        
        if not positions:
            await query.edit_message_text("📭 Tidak ada posisi aktif.")
            return

        message = "📊 *Portfolio Anda*\n\n"
        total_value = 0
        
        for i, position in enumerate(positions[:15]):
            pnl_emoji = "🟢" if position['pnl_percent'] > 0 else "🔴"
            message += f"{pnl_emoji} *{position['token_symbol'] or 'Unknown'}*\n"
            message += f"   💰 {position['amount']:.6f}\n"
            message += f"   📈 PnL: {position['pnl_percent']:.2f}%\n"
            message += f"   💵 Entry: ${position['entry_price']:.6f}\n\n"
            
            if position['current_price']:
                total_value += position['amount'] * position['current_price']

        message += f"💎 *Total Portfolio Value:* ${total_value:.2f}\n"

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_positions"),
             InlineKeyboardButton("💸 Sell All", callback_data="sell_all")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)