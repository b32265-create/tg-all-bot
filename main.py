import os
import asyncio
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# --- Monkey Patch Pyrogram for new Telegram Channel IDs ---
import pyrogram.utils
pyrogram.utils.MIN_CHANNEL_ID = -1009999999999
# ----------------------------------------------------------

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from config import BOT_TOKEN

# Import module handlers
from modules.ads.handlers import setup_ads_handlers
from modules.admin.handlers import setup_admin_handlers
from modules.gmail_store.handlers import setup_gmail_store_handlers

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    from config import ADMIN_USER_ID
    if ADMIN_USER_ID:
        try:
            error_message = f"⚠️ An error occurred:\n\n<pre>{context.error}</pre>"
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=error_message, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Failed to send error log to admin: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    keyboard = [
        [InlineKeyboardButton("📢 Ads Bot", callback_data='module_ads')],
        [
            InlineKeyboardButton("📥 Sell Gmails", callback_data='module_gmail_store'),
            InlineKeyboardButton("🛒 Buy Gmails", callback_data='module_gmail_buy_shop')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_message = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✨ **ALL-IN-ONE PREMIUM BOT** ✨\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Welcome to the ultimate command center.\n"
        "Select an advanced module below to get started:\n\n"
        "╰┈➤ **Available Modules:**"
    )
    
    if update.message:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
        query = update.callback_query
        try:
            # If the current message has a photo, we can't just edit the text. We must delete and send new.
            if query.message.photo or query.message.document or query.message.video:
                await query.message.delete()
                await context.bot.send_message(chat_id=query.message.chat_id, text=welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await query.edit_message_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error returning to main menu: {e}")
            await context.bot.send_message(chat_id=query.message.chat_id, text=welcome_message, reply_markup=reply_markup, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help! Select a module from /start to use specific features.")

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    server.serve_forever()

def main():
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Please set your BOT_TOKEN in config.py")
        return

    # Initialize the database and global Userbots without blocking startup
    from database import init_db
    from modules.ads.broadcaster import init_all_clients
    
    async def post_init(app: Application):
        await init_db()
        # Start Pyrogram clients in the background so it doesn't block the bot startup
        asyncio.create_task(init_all_clients())

    application = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Add a handler for "Back to Main Menu" generic callback
    application.add_handler(CallbackQueryHandler(start, pattern='^main_menu$'))

    # Setup module handlers
    setup_ads_handlers(application)
    setup_admin_handlers(application)
    setup_gmail_store_handlers(application)
    
    # Global Middleware (Maintenance & Force Sub)
    from telegram.ext import TypeHandler, ApplicationHandlerStop
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from modules.admin.handlers import load_maintenance, load_force_sub, is_admin
    from telegram.error import BadRequest
    
    async def global_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return
            
        user_id = update.effective_user.id
        is_user_admin = await is_admin(user_id)
        
        # 1. Maintenance Check
        m_data = await load_maintenance()
        if m_data.get("is_maintenance") and not is_user_admin:
            msg = m_data.get("message", "The bot is currently undergoing maintenance. Please check back later.")
            text = f"🛠 **Maintenance Break:**\n\n{msg}"
            if update.callback_query:
                await update.callback_query.answer("Maintenance Mode Active", show_alert=True)
            elif update.message:
                await update.message.reply_text(text, parse_mode='Markdown')
            raise ApplicationHandlerStop()

        # 2. Force Sub Check
        if not is_user_admin:
            channels = await load_force_sub()
            if channels:
                not_joined = []
                for cid_str, cname in channels.items():
                    try:
                        member = await context.bot.get_chat_member(chat_id=cid_str, user_id=user_id)
                        if member.status in ['left', 'kicked']:
                            not_joined.append((cid_str, cname))
                    except BadRequest:
                        # User hasn't joined or bot is not admin
                        not_joined.append((cid_str, cname))
                    except Exception as e:
                        logger.error(f"Force sub check error for {cid_str}: {e}")
                        
                if not_joined:
                    # Construct keyboard
                    keyboard = []
                    for cid_str, cname in not_joined:
                        # Attempt to create a link if possible, though usernames are easier
                        # If cid_str starts with '@', it's a public channel
                        url = f"https://t.me/{cid_str.replace('@', '')}" if cid_str.startswith("@") else None
                        
                        if not url:
                            try:
                                chat = await context.bot.get_chat(cid_str)
                                url = chat.invite_link if chat.invite_link else chat.username
                                if url and not url.startswith("http"):
                                    url = f"https://t.me/{url}"
                            except Exception:
                                pass
                                
                        if url:
                            keyboard.append([InlineKeyboardButton(f"📢 Join {cname}", url=url)])
                        else:
                            keyboard.append([InlineKeyboardButton(f"📢 Join {cname}", callback_data='ignore')])
                            
                    keyboard.append([InlineKeyboardButton("🔄 Refresh / Check", callback_data='fsub_check_joined')])
                    
                    text = "🚨 **Must Join Channels**\n\nYou must join our official channels to use this bot!"
                    
                    if update.callback_query:
                        if update.callback_query.data == 'fsub_check_joined':
                            await update.callback_query.answer("You haven't joined all channels yet!", show_alert=True)
                        else:
                            await update.callback_query.answer("Please join the required channels first.", show_alert=True)
                            try:
                                await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
                            except BadRequest:
                                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
                    elif update.message:
                        try:
                            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown', quote=False)
                        except BadRequest:
                            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
                        
                    raise ApplicationHandlerStop()

    application.add_handler(TypeHandler(Update, global_middleware), group=-1)
    
    async def fsub_check_passed(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer("Thank you for joining!", show_alert=True)
        await start(update, context)
        
    application.add_handler(CallbackQueryHandler(fsub_check_passed, pattern='^fsub_check_joined$'))
    
    # Global error handler
    application.add_error_handler(error_handler)

    # Start dummy HTTP server for Render health checks
    if os.environ.get("PORT"):
        logger.info("Starting dummy web server for Render...")
        threading.Thread(target=run_dummy_server, daemon=True).start()

    # Run the bot until the user presses Ctrl-C
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

import asyncio

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    main()
