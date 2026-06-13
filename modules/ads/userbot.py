import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, PasswordHashInvalid
from config import API_ID, API_HASH
from database import add_hosted_account, get_hosted_accounts_count, is_premium_user

logger = logging.getLogger(__name__)

ASK_PHONE, ASK_OTP, ASK_PASSWORD = range(2, 5)

async def prompt_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    # Check Premium Limits
    is_premium = await is_premium_user(user_id)
    accounts_count = await get_hosted_accounts_count(user_id)
    
    if not is_premium and accounts_count >= 2:
        msg = "━━━━━━━━━━━━━━━━━━━━\n⚠️ **Free Plan Limit Reached**\n━━━━━━━━━━━━━━━━━━━━\n\nYou can only add up to `2` accounts on the Free Plan.\n╰┈➤ *Please contact Admin to upgrade to Premium.*"
        keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]]
        try:
            await query.edit_message_caption(caption=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception:
            await query.edit_message_text(text=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return ConversationHandler.END

    
    # Initialize a new Pyrogram client in memory
    client = Client(
        name=f"in_memory_{update.effective_user.id}",
        api_id=API_ID,
        api_hash=API_HASH,
        in_memory=True
    )
    context.user_data['pyro_client'] = client
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='ads_cancel_conv')]]
    
    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📱 <b>Device Registration</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send your Telegram phone number with the country code.\n"
        "<i>Example: +919876543210</i>\n\n"
        "╰┈➤ <i>Send /cancel to abort at any time.</i>"
    )
    
    try:
        if query.message.photo:
            await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        else:
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error in prompt_add_account: {e}")
        
    return ASK_PHONE

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    client: Client = context.user_data.get('pyro_client')
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='ads_cancel_conv')]]
    
    if not phone.startswith('+'):
        await update.message.reply_text("❌ Please include the country code (e.g., +1, +91). Try again:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ASK_PHONE
        
    status_msg = await update.message.reply_text("🔄 <b>Connecting to Telegram Network...</b>", parse_mode='HTML')
    
    try:
        await client.connect()
        sent_code = await client.send_code(phone)
        context.user_data['phone'] = phone
        context.user_data['phone_code_hash'] = sent_code.phone_code_hash
        
        await status_msg.edit_text(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ <b>OTP Sent Successfully!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Please check your Telegram app for the login code and send it here.\n\n"
            "<i>(If your code contains letters or you want to bypass auto-format, you can send it normally).</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return ASK_OTP
    except Exception as e:
        logger.error(f"Error sending code: {e}")
        await client.disconnect()
        await status_msg.edit_text(f"❌ Failed to send OTP: {e}\n\nPlease try again or /cancel.", reply_markup=InlineKeyboardMarkup(keyboard))
        return ASK_PHONE

async def receive_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text.strip()
    client: Client = context.user_data.get('pyro_client')
    phone = context.user_data.get('phone')
    phone_code_hash = context.user_data.get('phone_code_hash')
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='ads_cancel_conv')]]
    
    status_msg = await update.message.reply_text("🔄 Verifying OTP...", parse_mode='HTML')
    
    try:
        await client.sign_in(phone, phone_code_hash, otp)
        # Success!
        await status_msg.delete()
        return await finalize_login(update, context, client)
        
    except SessionPasswordNeeded:
        await status_msg.edit_text(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔐 <b>Two-Step Verification</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "This account is secured with a 2FA password. Please send your password here to complete login.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return ASK_PASSWORD
    except PhoneCodeInvalid:
        await status_msg.edit_text("❌ Invalid OTP. Please try again:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ASK_OTP
    except PhoneCodeExpired:
        await status_msg.edit_text("❌ OTP expired. Please /cancel and start over.")
        return ASK_OTP
    except Exception as e:
        logger.error(f"Error during sign_in: {e}")
        await client.disconnect()
        await status_msg.edit_text(f"❌ Failed to login: {e}\n\nPlease /cancel and start over.")
        return ConversationHandler.END

async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text
    client: Client = context.user_data.get('pyro_client')
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='ads_cancel_conv')]]
    
    status_msg = await update.message.reply_text("🔄 Verifying password...", parse_mode='HTML')
    
    try:
        await client.check_password(password)
        # Success!
        await status_msg.delete()
        return await finalize_login(update, context, client)
    except PasswordHashInvalid:
        await status_msg.edit_text("❌ Incorrect Password. Please try again:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ASK_PASSWORD
    except Exception as e:
        logger.error(f"Error during check_password: {e}")
        await client.disconnect()
        await status_msg.edit_text(f"❌ Failed to login: {e}\n\nPlease /cancel and start over.")
        return ConversationHandler.END

async def finalize_login(update: Update, context: ContextTypes.DEFAULT_TYPE, client: Client):
    user_id = update.effective_user.id
    phone = context.user_data.get('phone')
    
    try:
        session_string = await client.export_session_string()
        await client.disconnect()
        
        # Save to database
        await add_hosted_account(user_id, phone, session_string)
        
        # Clean up
        context.user_data.pop('pyro_client', None)
        context.user_data.pop('phone', None)
        context.user_data.pop('phone_code_hash', None)
        
        dashboard_keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]]
        await update.message.reply_text(
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎉 <b>Account Setup Complete!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Your session has been securely saved to the database.\n"
            "╰┈➤ You can now use this account for broadcasting ads.",
            reply_markup=InlineKeyboardMarkup(dashboard_keyboard),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error finalizing login: {e}")
        await update.message.reply_text(f"❌ Error exporting session: {e}\nPlease /cancel and try again.")
        
    return ConversationHandler.END
