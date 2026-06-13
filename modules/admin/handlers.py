import json
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters
from config import ADMIN_USER_ID
from database import get_total_users, update_user_premium_status, get_all_users

logger = logging.getLogger(__name__)

ASK_PREMIUM_DATA, ASK_BROADCAST_MESSAGE, ASK_MAINTENANCE_MSG, ASK_FSUB_CHANNEL = range(4)

def load_maintenance():
    if os.path.exists("maintenance.json"):
        with open("maintenance.json", "r") as f:
            return json.load(f)
    return {"is_maintenance": False, "message": "The bot is currently undergoing maintenance. Please check back later."}

def save_maintenance(data):
    with open("maintenance.json", "w") as f:
        json.dump(data, f)

def load_force_sub():
    if os.path.exists("force_sub.json"):
        with open("force_sub.json", "r") as f:
            return json.load(f)
    return {}

def save_force_sub(data):
    with open("force_sub.json", "w") as f:
        json.dump(data, f)

async def is_admin(user_id: int) -> bool:
    if not ADMIN_USER_ID:
        return False
    return user_id == ADMIN_USER_ID

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin dashboard stats."""
    user_id = update.effective_user.id
    if not await is_admin(user_id):
        if update.message:
            await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    total_users = await get_total_users()
    
    stats = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👑 **Admin Command Center**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 **Total Registered Users:** `{total_users}`\n\n"
        "╰┈➤ **Select an option below:**"
    )
    
    m_data = load_maintenance()
    m_status = "🟢 ON" if m_data.get("is_maintenance") else "🔴 OFF"
    
    keyboard = [
        [InlineKeyboardButton("👥 View All Users", callback_data='admin_view_users')],
        [
            InlineKeyboardButton("💎 Manage Premium", callback_data='admin_manage_premium'),
            InlineKeyboardButton("📢 Broadcast", callback_data='admin_broadcast')
        ],
        [InlineKeyboardButton(f"🛠 Maintenance: {m_status}", callback_data='admin_toggle_maintenance')],
        [InlineKeyboardButton("📢 Force Sub Channels", callback_data='admin_fsub_menu')],
        [InlineKeyboardButton("📄 Get Logs", callback_data='admin_get_logs')],
        [InlineKeyboardButton("❌ Close Panel", callback_data='admin_close')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(stats, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(stats, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception:
            pass

async def admin_view_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not await is_admin(user_id): return
    
    users = await get_all_users()
    if not users:
        text = "No users found in database."
    else:
        text = "━━━━━━━━━━━━━━━━━━━━\n👥 **Registered Users**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        # List up to 50 users to avoid message length limits
        for i, u in enumerate(users[:50], 1):
            uid = u.get('user_id')
            prem = "💎" if u.get('is_premium') else "🆓"
            text += f"{i}. `{uid}` - {prem}\n"
        
        if len(users) > 50:
            text += f"\n_...and {len(users) - 50} more users._"
            
    keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel_back')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_get_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    if not await is_admin(user_id): return
    
    await query.answer("Fetching logs...")
    
    if os.path.exists("bot.log"):
        try:
            await context.bot.send_document(
                chat_id=user_id,
                document=open("bot.log", "rb"),
                caption="📄 **Here are the latest bot logs:**",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send logs: {e}")
    else:
        await context.bot.send_message(chat_id=user_id, text="❌ No log file found yet.")

async def prompt_manage_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='admin_panel_back')]]
    msg = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💎 **Manage Premium**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send the action and the **User ID**.\n"
        "Format: `add <user_id>` OR `remove <user_id>`\n"
        "Example: `add 123456789`"
    )
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ASK_PREMIUM_DATA

async def receive_premium_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    
    parts = text.split()
    if len(parts) != 2 or parts[0] not in ['add', 'remove']:
        await update.message.reply_text("❌ Invalid format. Please use `add <user_id>` or `remove <user_id>`.", parse_mode='Markdown')
        return ASK_PREMIUM_DATA
        
    action, target_id_str = parts[0], parts[1]
    
    try:
        target_id = int(target_id_str)
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID. Must be a number.")
        return ASK_PREMIUM_DATA
        
    if action == "add":
        success = await update_user_premium_status(target_id, True)
        msg = f"✅ Premium granted to `{target_id}`." if success else "❌ Failed to grant premium."
    else:
        success = await update_user_premium_status(target_id, False)
        msg = f"✅ Premium revoked from `{target_id}`." if success else "❌ Failed to revoke premium."
        
    keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel_back')]]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ConversationHandler.END

async def prompt_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='admin_panel_back')]]
    msg = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📢 **Broadcast Message**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send the message you want to broadcast to ALL registered users.\n\n"
        "╰┈➤ _Markdown and HTML formatting are supported._"
    )
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ASK_BROADCAST_MESSAGE

async def receive_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await get_all_users()
    
    status_msg = await update.message.reply_text(f"⏳ Broadcasting to {len(users)} users...")
    
    success_count = 0
    for u in users:
        target_id = u.get('user_id')
        try:
            # Send the broadcast header
            await context.bot.send_message(chat_id=target_id, text="📢 **Broadcast from Admin:**", parse_mode='Markdown')
            # Copy the exact message (supports photo, video, document, formatting perfectly)
            await context.bot.copy_message(chat_id=target_id, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
            success_count += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to {target_id}: {e}")

    keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel_back')]]
    await status_msg.edit_text(f"✅ Broadcast successfully sent to {success_count}/{len(users)} users.", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def admin_toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    m_data = load_maintenance()
    is_on = m_data.get("is_maintenance", False)
    
    if is_on:
        # Turn it OFF
        m_data["is_maintenance"] = False
        save_maintenance(m_data)
        await admin_panel(update, context)
        return ConversationHandler.END
    else:
        # Turn it ON -> Ask for message
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='admin_panel_back')]]
        msg = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🛠 **Turn ON Maintenance Mode**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please send the maintenance message that regular users will see when they try to use the bot.\n\n"
            "╰┈➤ _For example: 'We are updating our servers. Please wait 10 minutes.'_"
        )
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return ASK_MAINTENANCE_MSG

async def receive_maintenance_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text_html or update.message.text
    
    m_data = load_maintenance()
    m_data["is_maintenance"] = True
    m_data["message"] = text
    save_maintenance(m_data)
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel_back')]]
    await update.message.reply_text("✅ Maintenance mode is now **ON** with the new message.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ConversationHandler.END

async def admin_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.delete()
    return ConversationHandler.END

async def admin_cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await admin_panel(update, context)
    return ConversationHandler.END

async def admin_fsub_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not await is_admin(user_id): return
    
    channels = load_force_sub()
    
    text = "━━━━━━━━━━━━━━━━━━━━\n📢 **Force Sub Channels**\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if not channels:
        text += "No required channels currently set.\n\n"
    else:
        text += "Users must join these channels to use the bot:\n\n"
        for idx, (cid, cname) in enumerate(channels.items(), 1):
            text += f"{idx}. {cname} (`{cid}`)\n"
        text += "\n"
        
    text += "╰┈➤ **Select an action below:**"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Channel", callback_data='admin_fsub_add')],
    ]
    
    if channels:
        for cid, cname in channels.items():
            keyboard.append([InlineKeyboardButton(f"❌ Remove {cname}", callback_data=f'admin_fsub_rem_{cid}')])
            
    keyboard.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data='admin_panel_back')])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def prompt_fsub_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='admin_fsub_menu')]]
    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "➕ **Add Force Sub Channel**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send the Channel ID (e.g., `-100123456789`) or username (e.g., `@mychannel`).\n"
        "**NOTE:** The bot must be an ADMIN in this channel!"
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ASK_FSUB_CHANNEL

async def receive_fsub_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_id_or_username = update.message.text.strip()
    channels = load_force_sub()
    
    try:
        chat = await context.bot.get_chat(channel_id_or_username)
        # Try to fetch bot member status to ensure it can read
        await context.bot.get_chat_member(chat.id, context.bot.id)
        
        cid_str = str(chat.id)
        channels[cid_str] = chat.title or channel_id_or_username
        save_force_sub(channels)
        
        msg = f"✅ Channel **{chat.title}** successfully added to Force Sub!"
    except Exception as e:
        msg = f"❌ Error adding channel: {e}\n\nMake sure the bot is an admin in the channel and the ID is correct."
        logger.error(msg)
        
    keyboard = [[InlineKeyboardButton("🔙 Back to Force Sub Menu", callback_data='admin_fsub_menu')]]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ConversationHandler.END

async def admin_fsub_rem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if not await is_admin(user_id): return
    
    cid_to_rem = query.data.split('admin_fsub_rem_')[1]
    channels = load_force_sub()
    
    if cid_to_rem in channels:
        cname = channels.pop(cid_to_rem)
        save_force_sub(channels)
        await query.answer(f"Removed {cname} from Force Sub", show_alert=True)
    else:
        await query.answer("Channel not found.", show_alert=True)
        
    await admin_fsub_menu(update, context)

def setup_admin_handlers(application: Application):
    """Register all admin handlers."""
    # The main /admin command
    application.add_handler(CommandHandler("admin", admin_panel))
    
    # Standalone callback queries for simple actions
    application.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin_panel_back$'))
    application.add_handler(CallbackQueryHandler(admin_view_users, pattern='^admin_view_users$'))
    application.add_handler(CallbackQueryHandler(admin_get_logs, pattern='^admin_get_logs$'))
    application.add_handler(CallbackQueryHandler(admin_close, pattern='^admin_close$'))
    application.add_handler(CallbackQueryHandler(admin_fsub_menu, pattern='^admin_fsub_menu$'))
    application.add_handler(CallbackQueryHandler(admin_fsub_rem, pattern='^admin_fsub_rem_'))
    
    # Conversation handler for complex flows (Premium & Broadcast & Maintenance)
    admin_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_manage_premium, pattern='^admin_manage_premium$'),
            CallbackQueryHandler(prompt_broadcast, pattern='^admin_broadcast$'),
            CallbackQueryHandler(admin_toggle_maintenance, pattern='^admin_toggle_maintenance$'),
            CallbackQueryHandler(prompt_fsub_add, pattern='^admin_fsub_add$')
        ],
        states={
            ASK_PREMIUM_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_premium_data)],
            ASK_BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, receive_broadcast)],
            ASK_MAINTENANCE_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_maintenance_msg)],
            ASK_FSUB_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_fsub_channel)]
        },
        fallbacks=[
            CommandHandler('admin', admin_panel),
            CallbackQueryHandler(admin_cancel_conv, pattern='^admin_panel_back$')
        ],
        per_message=False
    )
    application.add_handler(admin_conv_handler)
