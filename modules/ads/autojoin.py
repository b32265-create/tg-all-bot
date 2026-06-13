import logging
import asyncio
import re
import io
from pyrogram import Client
from pyrogram.errors import FloodWait
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from modules.ads.utils import flood_wait_countdown

from config import API_ID, API_HASH
from database import get_hosted_accounts
from modules.ads.broadcaster import start_client_if_needed

logger = logging.getLogger(__name__)

ASK_GROUP_LINK = 1

async def prompt_auto_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the auto join conversation."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("✅ Done (Skip)", callback_data='auto_join_done')]]
    
    msg_text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📥 **Auto-Join Engine**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send me a single link, or multiple links separated by spaces or newlines.\n"
        "╰┈➤ _Supported formats: `@username`, `https://t.me/...`, etc._\n\n"
        "⚠️ **Anti-Ban System Active:** I will automatically join these groups using ALL your active accounts in the background with a `10s delay` to prevent flood bans!\n\n"
        "╰┈➤ _When you are finished sending links, click **Done**._"
    )
    
    try:
        if query.message.photo:
            await query.edit_message_caption(
                caption=msg_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                text=msg_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error editing message in prompt_auto_join: {e}")
        await query.edit_message_text(
            text=msg_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    return ASK_GROUP_LINK

async def bg_auto_join(user_id: int, links: list, accounts: list, context: ContextTypes.DEFAULT_TYPE):
    """Background task to join groups with delay and detailed logging."""
    success_count = 0
    fail_count = 0
    
    joined_logs = []
    failed_logs = []
    
    for acc in accounts:
        phone = acc.get('phone_number', 'Unknown')
        
        client = await start_client_if_needed(user_id, acc)
        if not client:
            logger.error(f"Failed to get client for {phone}")
            continue
            
        for link in links:
            try:
                await client.join_chat(link)
                success_count += 1
                joined_logs.append(f"✅ {phone} Joined: {link}")
                logger.info(f"User {user_id}: Account {phone} joined {link}")
                await asyncio.sleep(10) # 10 second delay
            except FloodWait as e:
                logger.warning(f"FloodWait for {e.value}s in auto-join.")
                failed_logs.append(f"❌ {phone} Failed: {link} - FloodWait {e.value}s")
                await flood_wait_countdown(user_id, phone, "Auto Join", e.value, context.bot)
            except Exception as e:
                logger.error(f"Auto join failed for {phone} on {link}: {e}")
                fail_count += 1
                failed_logs.append(f"❌ {phone} Failed: {link} - {str(e)}")
                await asyncio.sleep(2) # Short delay on fail
            
    # Compile log file
    log_content = "=== AUTO JOIN REPORT ===\n\n"
    log_content += f"Processed {len(links)} link(s) across {len(accounts)} account(s).\n"
    log_content += f"Successful Joins: {success_count}\n"
    log_content += f"Failed Joins: {fail_count}\n\n"
    
    log_content += "--- SUCCESSFUL JOINS ---\n"
    log_content += "\n".join(joined_logs) if joined_logs else "None"
    
    log_content += "\n\n--- FAILED JOINS ---\n"
    log_content += "\n".join(failed_logs) if failed_logs else "None"
    
    log_file = io.BytesIO(log_content.encode('utf-8'))
    log_file.name = "auto_join_report.txt"
            
    # Send completion notification
    msg = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ **Auto-Join Completed!**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Processed `{len(links)}` link(s) across `{len(accounts)}` account(s).\n\n"
        f"🟢 **Successful Joins:** `{success_count}`\n"
        f"🔴 **Failed Joins:** `{fail_count}`\n\n"
        "╰┈➤ _Please check the attached detailed report._"
    )
    try:
        await context.bot.send_document(chat_id=user_id, document=log_file, caption=msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Failed to send auto join completion message: {e}")

async def receive_group_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive group links and start the background join process."""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Extract all links using regex
    # Matches t.me/..., https://t.me/..., or @username
    pattern = r"(?:https?://)?t\.me/[^\s]+|@[a-zA-Z0-9_]+"
    links = re.findall(pattern, text)
    
    if not links:
        await update.message.reply_text("❌ No valid Telegram links or usernames found. Please try again.")
        return ASK_GROUP_LINK
        
    accounts = await get_hosted_accounts(user_id)
    if not accounts:
        await update.message.reply_text("❌ You have no active accounts to join groups with!")
        return ASK_GROUP_LINK
        
    # Start background task
    asyncio.create_task(bg_auto_join(user_id, links, accounts, context))
    
    keyboard = [[InlineKeyboardButton("✅ Done (Skip)", callback_data='auto_join_done')]]
    
    await update.message.reply_text(
        text=(
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔄 **Background Engine Started**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Found `{len(links)}` link(s). I am now joining them with all your accounts.\n"
            f"╰┈➤ *(A 10-second delay is applied between each join to avoid bans)*\n\n"
            f"I will message you here when the process is complete.\n\n"
            "╰┈➤ _You can send more links or click **Done** to return to the dashboard._"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ASK_GROUP_LINK

async def auto_join_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """End the auto join conversation and return to dashboard."""
    query = update.callback_query
    await query.answer()
    
    msg_text = "━━━━━━━━━━━━━━━━━━━━\n✅ **Auto-Join Session Closed**\n━━━━━━━━━━━━━━━━━━━━\n\n╰┈➤ You can now Start Ads and it will target these new groups."
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]])
    
    try:
        if query.message.photo:
            await query.edit_message_caption(
                caption=msg_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                text=msg_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in auto_join_done: {e}")
        await query.edit_message_text(
            text=msg_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    return ConversationHandler.END
