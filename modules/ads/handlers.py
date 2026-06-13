from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import CallbackQueryHandler, ContextTypes, Application, ConversationHandler, MessageHandler, filters, CommandHandler
import logging
import html

from database import (
    get_hosted_accounts_count, get_ads_config, add_user, update_ads_config,
    get_hosted_accounts, delete_account, is_premium_user, get_excluded_groups,
    add_excluded_group, remove_excluded_group
)
from modules.ads.userbot import prompt_add_account, receive_phone, receive_otp, receive_password, ASK_PHONE, ASK_OTP, ASK_PASSWORD
from modules.ads.broadcaster import start_broadcaster, stop_broadcaster
from modules.ads.autojoin import prompt_auto_join, receive_group_link, auto_join_done, ASK_GROUP_LINK

logger = logging.getLogger(__name__)

# Conversation states
SET_MESSAGE, SET_INTERVAL, ASK_CYCLES, ASK_EXCLUDE_GROUP = range(4)

async def get_user_profile_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Helper to get user's profile photo. Returns file_id or None."""
    user_id = update.effective_user.id
    try:
        photos = await context.bot.get_user_profile_photos(user_id)
        if photos.total_count > 0:
            return photos.photos[0][-1].file_id
    except Exception as e:
        logger.error(f"Failed to get profile photo: {e}")
    return None

async def send_or_edit_menu(query, context, text, reply_markup, photo_file_id=None, parse_mode='HTML'):
    """Helper to transition between text and photo messages."""
    try:
        if photo_file_id:
            if query.message.photo:
                try:
                    await query.edit_message_media(
                        media=InputMediaPhoto(media=photo_file_id, caption=text, parse_mode=parse_mode),
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"Failed to edit media: {e}")
                    await query.message.delete()
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=photo_file_id,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
            else:
                await query.message.delete()
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=photo_file_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        else:
            if query.message.photo:
                await query.message.delete()
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Error in send_or_edit_menu: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )

async def ads_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the Ads bot menu."""
    query = update.callback_query
    await query.answer()

    photo_file_id = await get_user_profile_photo(update, context)

    keyboard = [
        [InlineKeyboardButton("Dashboard", callback_data='ads_dashboard')],
        [
            InlineKeyboardButton("Updates ↗", url='https://t.me/+9v78xzfA0bg2M2U1'),
            InlineKeyboardButton("Support ↗", url='https://t.me/SHADOW_SELLER07')
        ],
        [InlineKeyboardButton("How To Use ↗", url='https://t.me/+9v78xzfA0bg2M2U1')],
        [InlineKeyboardButton("Powered by ↗", url='https://t.me/SHADOW_SELLER07')],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    ads_message = (
        f"Welcome to <b>SHADOWS ADS</b> Free Ads bot — The Future of Telegram Automation\n\n"
        "• Premium Ad Broadcasting\n"
        "• Smart Delays\n"
        "• Multi-Account Support\n\n"
        "For support contact: @SHADOW_SELLER07"
    )
    
    await send_or_edit_menu(query, context, ads_message, reply_markup, photo_file_id)

async def ads_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the intricate Ads Dashboard."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    await add_user(user_id) # Ensure user exists in DB

    accounts_count = await get_hosted_accounts_count(user_id)
    config = await get_ads_config(user_id)

    ad_msg_preview = "Not Set ❌"
    if config and config.get('ad_message'):
        raw_msg = config['ad_message']
        ad_msg_preview = raw_msg[:20] + "..." if len(raw_msg) > 20 else raw_msg
        ad_msg_preview = html.escape(ad_msg_preview)
    
    interval = config.get('interval_minutes', 'Not Set') if config else 'Not Set'
    target = config.get('target_type', 'groups') if config else 'groups'
    cycles_current = config.get('current_cycles', 0) if config else 0
    cycles_max = config.get('max_cycles', 0) if config else 0
    cycles_text = f"{cycles_current}/∞" if cycles_max == 0 else f"{cycles_current}/{cycles_max}"
    
    status = "Active ▶️" if config and config.get('status') == 'active' else "Paused ⏸️"
    auto_reply_mode = config.get('auto_reply_mode', 'off') if config else 'off'
    
    target_emoji = "🎯 Target: Groups" if target == 'groups' else "🎯 Target: DMs (Users)"
    auto_reply_emoji = f"💬 Auto Reply: {auto_reply_mode.capitalize()}"

    photo_file_id = await get_user_profile_photo(update, context)
    bot_username = context.bot.username if context.bot.username else "bot"

    keyboard = [
        [
            InlineKeyboardButton("➕ Add Account", callback_data='ads_add_account'),
            InlineKeyboardButton("📱 My Accounts", callback_data='ads_my_accounts')
        ],
        [
            InlineKeyboardButton("📝 Set Ad Message", callback_data='ads_set_message'),
            InlineKeyboardButton("⏱️ Set Interval", callback_data='ads_set_interval')
        ],
        [
            InlineKeyboardButton(target_emoji, callback_data='ads_toggle_target'),
            InlineKeyboardButton("🔄 Set Cycles", callback_data='ads_set_cycles')
        ]
    ]

    if config and config.get('status') == 'running':
        keyboard.append([InlineKeyboardButton("⏸️ Stop Ads", callback_data='ads_stop')])
    else:
        keyboard.append([InlineKeyboardButton("▶️ Start Ads", callback_data='ads_start')])

    keyboard.extend([
        [
            InlineKeyboardButton("🚫 Exclude Groups", callback_data='ads_exclude_menu'),
            InlineKeyboardButton("📝 Set Auto Reply Msg", callback_data='ads_set_auto_reply_msg')
        ],
        [
            InlineKeyboardButton(auto_reply_emoji, callback_data='ads_toggle_auto_reply'),
            InlineKeyboardButton("📊 Analytics", callback_data='ads_analytics')
        ],
        [
            InlineKeyboardButton("⭐ Premium", callback_data='ads_premium_info'),
            InlineKeyboardButton("📥 Auto Join Groups", callback_data='ads_auto_join')
        ],
        [
            InlineKeyboardButton("🗑️ Delete Accounts", callback_data='ads_delete_accounts_menu')
        ],
        [
            InlineKeyboardButton("🔙 Back to Ads Menu", callback_data='module_ads')
        ]
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    dashboard_msg = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>@{bot_username} Control Panel</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Accounts & Content</b>\n"
        f"├ Hosted Accounts: <code>{accounts_count}</code>\n"
        f"└ Ad Message: <code>{ad_msg_preview}</code>\n\n"
        f"⚙️ <b>Engine Configuration</b>\n"
        f"├ Target Type: <code>{target.upper()}</code>\n"
        f"├ Interval: <code>{interval} mins</code>\n"
        f"├ Cycles: <code>{cycles_text}</code>\n"
        f"└ Auto Reply: <code>{auto_reply_mode.capitalize()}</code>\n\n"
        f"📊 <b>Status:</b> <code>{status}</code>\n"
    )
    
    if target == 'dms':
        dashboard_msg += "\n⚠️ <b>Warning:</b> Ads will be sent privately (DM) to the user who sent the latest message in your active groups.\n"
        
    dashboard_msg += "\n╰┈➤ <b>Select an option below to manage:</b>"
    
    await send_or_edit_menu(query, context, dashboard_msg, reply_markup, photo_file_id, parse_mode='HTML')

async def ads_coming_soon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Placeholder for dashboard buttons."""
    query = update.callback_query
    await query.answer(text="⚠️ This feature is coming soon!", show_alert=True)

async def module_coming_soon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer(text="⚠️ This module is coming soon!", show_alert=True)

async def ads_premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    from database import get_user_plan_status
    plan_status = await get_user_plan_status(user_id)
    
    if plan_status == "Premium":
        status_text = "🟢 **Premium Active**"
    elif plan_status == "Trial":
        status_text = "⏳ **2-Day Trial Active**\n╰┈➤ *(Premium Features Unlocked)*"
    else:
        status_text = "🔴 **Free Plan**"
    
    msg = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 **Premium Subscription**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Your Status:** {status_text}\n\n"
        "🆓 **Free Plan Limits:**\n"
        "├ Max Accounts: `2`\n"
        "└ Min Interval: `30 mins`\n\n"
        "👑 **Premium Limits:**\n"
        "├ Max Accounts: `Unlimited`\n"
        "└ Min Interval: `5 mins`\n\n"
        "╰┈➤ _Contact Admin to upgrade to Premium._"
    )
    keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]]
    await send_or_edit_menu(query, context, msg, InlineKeyboardMarkup(keyboard), None, parse_mode='Markdown')

async def ads_set_cycles_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='ads_cancel_conv')]]
    msg = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔄 **Set Broadcast Cycles**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Enter the maximum number of cycles you want the bot to run.\n"
        "╰┈➤ _Send `0` for infinite broadcasting._"
    )
    try:
        await query.edit_message_caption(caption=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception:
        await query.edit_message_text(text=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ASK_CYCLES

async def receive_cycles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    val = update.message.text
    keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]]
    
    if not val.isdigit():
        await update.message.reply_text("❌ Please send a valid number.", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END
        
    await update_ads_config(user_id, {'max_cycles': int(val), 'current_cycles': 0})
    await update.message.reply_text(f"✅ Max cycles set to {val}.", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def ads_exclude_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    
    excluded = await get_excluded_groups(user_id)
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Excluded Group", callback_data='ads_add_exclude')],
        [InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]
    ]
    
    if not excluded:
        msg = "🚫 **Excluded Groups**\n\nYou haven't excluded any groups. Ads will be sent to all your joined groups."
    else:
        msg = "🚫 **Excluded Groups**\n\nAds will **NOT** be sent to these groups:\n\n"
        for idx, g in enumerate(excluded, 1):
            msg += f"{idx}. `{g}`\n"
        msg += "\nTo remove, please ask Admin to delete from DB currently."
        
    await send_or_edit_menu(query, context, msg, InlineKeyboardMarkup(keyboard), None, parse_mode='Markdown')

async def prompt_add_exclude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='ads_cancel_conv')]]
    msg = "🚫 **Add Excluded Group**\n\nSend me the Group ID or Link that you want to exclude."
    try:
        await query.edit_message_caption(caption=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception:
        await query.edit_message_text(text=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ASK_EXCLUDE_GROUP

async def receive_exclude_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    val = update.message.text
    await add_excluded_group(user_id, val)
    keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]]
    await update.message.reply_text(f"✅ Group `{val}` excluded successfully.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ConversationHandler.END

async def ads_my_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the user's hosted accounts."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    accounts = await get_hosted_accounts(user_id)
    
    photo_file_id = await get_user_profile_photo(update, context)
    keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]]
    
    if not accounts:
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📱 <b>Device Management</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "You currently have no active hosted accounts.\n"
            "╰┈➤ <i>Click 'Add Account' in the dashboard to connect one.</i>"
        )
    else:
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📱 <b>Device Management</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Here are your connected accounts:\n\n"
        )
        for i, acc in enumerate(accounts, 1):
            phone = acc.get('phone_number', 'Unknown')
            text += f"├ <b>{i}. {phone}</b> (🟢 Active)\n"
            
        text += "\n╰┈➤ <i>Your accounts are ready for broadcasting.</i>"
            
    await send_or_edit_menu(query, context, text, InlineKeyboardMarkup(keyboard), photo_file_id)

async def ads_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the ad broadcasting engine."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    success, message = await start_broadcaster(user_id, context.application)
    await query.answer(text=message, show_alert=True)
    
    # Reload dashboard
    if success:
        await ads_dashboard(update, context)

async def ads_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the ad broadcasting engine."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    success, message = await stop_broadcaster(user_id)
    await query.answer(text=message, show_alert=True)
    
    # Reload dashboard
    if success:
        await ads_dashboard(update, context)

async def ads_toggle_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle between targeting Groups and DMs."""
    query = update.callback_query
    user_id = update.effective_user.id
    config = await get_ads_config(user_id)
    if not config: return
    
    current = config.get('target_type', 'groups')
    new_target = 'dms' if current == 'groups' else 'groups'
    await update_ads_config(user_id, {'target_type': new_target})
    await ads_dashboard(update, context)

async def ads_toggle_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle auto reply mode: off -> offline -> everytime -> off."""
    query = update.callback_query
    user_id = update.effective_user.id
    config = await get_ads_config(user_id)
    if not config: return
    
    current = config.get('auto_reply_mode', 'off')
    if current == 'off': new_mode = 'offline'
    elif current == 'offline': new_mode = 'everytime'
    else: new_mode = 'off'
    
    await update_ads_config(user_id, {'auto_reply_mode': new_mode})
    await ads_dashboard(update, context)

async def ads_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show analytics for the user in graph format."""
    import urllib.parse
    import json
    
    query = update.callback_query
    user_id = update.effective_user.id
    
    config = await get_ads_config(user_id)
    accounts_count = await get_hosted_accounts_count(user_id)
    
    if not config:
        return await query.answer("Config not found.", show_alert=True)
        
    total_messages = config.get('total_messages_sent', 0)
    cycles = config.get('current_cycles', 0)
    target = config.get('target_type', 'groups').upper()
    status = "Active" if config.get('status') == 'active' else "Paused"
    
    # Generate QuickChart Image URL
    chart_config = {
        "type": "bar",
        "data": {
            "labels": ["Total Sent", "Cycles Run", "Accounts"],
            "datasets": [{
                "label": "Bot Analytics",
                "data": [total_messages, cycles, accounts_count],
                "backgroundColor": ["rgba(54, 162, 235, 0.8)", "rgba(255, 206, 86, 0.8)", "rgba(75, 192, 192, 0.8)"]
            }]
        },
        "options": {
            "plugins": {
                "title": {"display": True, "text": "Ads Performance Graph", "color": "white"}
            },
            "legend": {"labels": {"fontColor": "white"}},
            "scales": {
                "yAxes": [{"ticks": {"beginAtZero": True, "fontColor": "white"}}],
                "xAxes": [{"ticks": {"fontColor": "white"}}]
            }
        }
    }
    encoded_config = urllib.parse.quote(json.dumps(chart_config))
    chart_url = f"https://quickchart.io/chart.png?c={encoded_config}&bkg=transparent"
    
    # Download the image to memory to prevent Telegram API URL rejection
    import urllib.request
    import io
    try:
        req = urllib.request.Request(chart_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            image_data = response.read()
            photo_obj = io.BytesIO(image_data)
            photo_obj.name = "chart.png"
    except Exception as e:
        logger.error(f"Failed to download chart image: {e}")
        photo_obj = None
    
    analytics_msg = (
        f"📊 <b>Ads Engine Analytics</b>\n\n"
        f"📱 Active Accounts: <code>{accounts_count}</code>\n"
        f"🔄 Cycles Completed: <code>{cycles}</code>\n"
        f"📨 Total Messages Sent: <code>{total_messages}</code>\n"
        f"🎯 Current Target: <code>{target}</code>\n"
        f"⚙️ Broadcast Status: <code>{status}</code>\n\n"
        "<i>(Messages sent count updates automatically after each cycle completes)</i>"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]]
    await send_or_edit_menu(query, context, analytics_msg, InlineKeyboardMarkup(keyboard), photo_file_id=photo_obj)

async def ads_delete_accounts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show a menu with buttons to delete specific accounts."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    accounts = await get_hosted_accounts(user_id)
    if not accounts:
        return await query.answer("You don't have any accounts to delete!", show_alert=True)
        
    keyboard = []
    for acc in accounts:
        phone = acc.get('phone_number', 'Unknown')
        acc_id = acc.get('id')
        keyboard.append([InlineKeyboardButton(f"❌ Delete {phone}", callback_data=f'ads_del_acc_{acc_id}')])
        
    keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')])
    
    await query.edit_message_caption(
        caption="🗑️ **Delete Accounts**\n\nClick an account below to permanently delete it from the bot.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def ads_do_delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the actual deletion of an account."""
    query = update.callback_query
    acc_id = int(query.data.split('_')[-1])
    
    success = await delete_account(acc_id)
    if success:
        await query.answer("Account deleted successfully!", show_alert=True)
        await ads_delete_accounts_menu(update, context) # Refresh menu
    else:
        await query.answer("Failed to delete account. Try again.", show_alert=True)

# --- Conversation Handlers Logic ---
ASK_MESSAGE, ASK_AUTO_REPLY, ASK_INTERVAL = range(4, 7)


async def prompt_set_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user for the ad message."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='ads_cancel_conv')]]
    try:
        await query.edit_message_caption(
            caption="📝 <b>Please send me your Ad Message.</b>\n\nYou can use Markdown or HTML formatting.\nSend /cancel or click the button below to abort.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    except Exception:
        await query.edit_message_text(
            text="📝 <b>Please send me your Ad Message.</b>\n\nYou can use Markdown or HTML formatting.\nSend /cancel or click the button below to abort.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    return ASK_MESSAGE

async def prompt_set_auto_reply_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask user for the auto reply message."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='ads_cancel_conv')]]
    try:
        await query.edit_message_caption(
            caption="📝 <b>Please send me your Auto Reply Message.</b>\n\nThis will be sent instantly to anyone who DMs your userbots.\nSend /cancel or click the button below to abort.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    except Exception:
        await query.edit_message_text(
            text="📝 <b>Please send me your Auto Reply Message.</b>\n\nThis will be sent instantly to anyone who DMs your userbots.\nSend /cancel or click the button below to abort.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    return ASK_AUTO_REPLY

async def receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ad_msg = update.message.text_html or update.message.caption_html or update.message.text
    
    await update_ads_config(user_id, {'ad_message': ad_msg})
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]]
    await update.message.reply_text(
        "✅ <b>Ad Message saved successfully!</b>\n\n(Formatting preserved)", 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    return ConversationHandler.END

async def receive_auto_reply_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message.text_html or update.message.caption_html or update.message.text
    
    await update_ads_config(user_id, {'auto_reply_message': msg})
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]]
    await update.message.reply_text(
        "✅ <b>Auto Reply Message saved successfully!</b>", 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    return ConversationHandler.END

async def prompt_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data='ads_cancel_conv')]]
    
    try:
        await query.edit_message_caption(
            caption="⏱️ <b>Set Cycle Interval</b>\n\nSend me the interval time in minutes (e.g., 30).",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    except Exception:
        pass
    return ASK_INTERVAL

async def receive_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    interval_str = update.message.text
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]]
    
    if not interval_str.isdigit():
        await update.message.reply_text("❌ Please send a valid number for minutes.", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END
        
    interval_mins = int(interval_str)
    is_premium = await is_premium_user(user_id)
    min_interval = 5 if is_premium else 30
    
    if interval_mins < min_interval:
        await update.message.reply_text(f"⚠️ Minimum interval is {min_interval} minutes for your account plan.", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END
        
    await update_ads_config(user_id, {'interval_minutes': interval_mins})
    
    await update.message.reply_text(
        f"✅ <b>Interval set to {interval_mins} minutes!</b>", 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data='ads_dashboard')]]
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        try:
            if query.message.photo:
                await query.edit_message_caption(
                    caption="❌ Operation cancelled.", 
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await query.edit_message_text(
                    text="❌ Operation cancelled.", 
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        except Exception:
            await query.edit_message_text(
                text="❌ Operation cancelled.", 
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    elif update.message:
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

def setup_ads_handlers(application: Application):
    """Register all handlers for the Ads module."""
    
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(prompt_set_message, pattern='^ads_set_message$'),
            CallbackQueryHandler(prompt_set_auto_reply_msg, pattern='^ads_set_auto_reply_msg$'),
            CallbackQueryHandler(prompt_set_interval, pattern='^ads_set_interval$'),
            CallbackQueryHandler(ads_set_cycles_prompt, pattern='^ads_set_cycles$'),
            CallbackQueryHandler(prompt_add_exclude, pattern='^ads_add_exclude$')
        ],
        states={
            ASK_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_message)],
            ASK_AUTO_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_auto_reply_msg)],
            ASK_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_interval)],
            ASK_CYCLES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_cycles)],
            ASK_EXCLUDE_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_exclude_group)]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern='^ads_cancel_conv$')
        ]
    )
    
    userbot_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_add_account, pattern='^ads_add_account$')],
        states={
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            ASK_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_otp)],
            ASK_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern='^ads_cancel_conv$')
        ],
        per_message=False
    )
    
    autojoin_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_auto_join, pattern='^ads_auto_join$')],
        states={
            ASK_GROUP_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_group_link),
                CallbackQueryHandler(auto_join_done, pattern='^auto_join_done$')
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern='^ads_cancel_conv$')
        ],
        per_message=False
    )
    
    application.add_handler(conv_handler)
    application.add_handler(userbot_conv_handler)
    application.add_handler(autojoin_conv_handler)
    application.add_handler(CallbackQueryHandler(ads_menu, pattern='^module_ads$'))
    application.add_handler(CallbackQueryHandler(ads_dashboard, pattern='^ads_dashboard$'))
    application.add_handler(CallbackQueryHandler(ads_my_accounts, pattern='^ads_my_accounts$'))
    application.add_handler(CallbackQueryHandler(ads_start, pattern='^ads_start$'))
    application.add_handler(CallbackQueryHandler(ads_stop, pattern='^ads_stop$'))
    application.add_handler(CallbackQueryHandler(ads_toggle_target, pattern='^ads_toggle_target$'))
    application.add_handler(CallbackQueryHandler(ads_toggle_auto_reply, pattern='^ads_toggle_auto_reply$'))
    application.add_handler(CallbackQueryHandler(ads_analytics, pattern='^ads_analytics$'))
    application.add_handler(CallbackQueryHandler(ads_delete_accounts_menu, pattern='^ads_delete_accounts_menu$'))
    application.add_handler(CallbackQueryHandler(ads_do_delete_account, pattern='^ads_del_acc_'))
    application.add_handler(CallbackQueryHandler(ads_coming_soon, pattern='^ads_coming_soon$'))
    application.add_handler(CallbackQueryHandler(module_coming_soon, pattern='^module_coming_soon$'))
    application.add_handler(CallbackQueryHandler(ads_premium_info, pattern='^ads_premium_info$'))
    application.add_handler(CallbackQueryHandler(ads_exclude_menu, pattern='^ads_exclude_menu$'))
