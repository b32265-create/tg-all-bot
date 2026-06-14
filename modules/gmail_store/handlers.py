import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ContextTypes, Application, ConversationHandler, MessageHandler, filters, CommandHandler

from database import (
    get_user_balance, update_user_balance, add_gmail_submission, 
    get_user_stats, create_payout_request, add_user, update_submission_status,
    get_available_stock_count, buy_gmail_account, add_gmail_stock, get_submission
)
from modules.admin.handlers import is_admin, load_dump_channel
from config import ADMIN_USER_ID

logger = logging.getLogger(__name__)

ASK_EMAIL, ASK_PASSWORD = range(2)
ASK_PAYOUT_METHOD = 3

# Main Keyboard
def get_buyer_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📝 SUBMIT YOUR ACCOUNT"), KeyboardButton("💰 BALANCE")],
            [KeyboardButton("📊 MY STATS"), KeyboardButton("❓ HELP")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )

async def enter_gmail_buyer_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when user clicks 'Gmail Store' from main menu."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    await add_user(user_id) # Ensure user exists

    text = (
        "🎉 Welcome 𝙎𝙃𝘼𝘿𝙊𝙒 𝙎𝙀𝙇𝙇𝙀𝙍 🐲 to Gmail Buyer Bot!\n\n"
        "How it works:\n"
        "• Submit your Gmail/Account details\n"
        "• Get approved and receive payment\n"
        "• Request payout (Minimum ₹25)\n\n"
        "Available Commands:\n"
        "📝 SUBMIT YOUR ACCOUNT - Submit new task\n"
        "💰 BALANCE - Check your earnings\n"
        "📊 MY STATS - View your statistics\n"
        "❓ HELP - Get help and support\n\n"
        "Support: @SHADOW_SELLER07"
    )
    
    # Delete the inline keyboard message and send the reply keyboard
    await query.message.delete()
    await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=get_buyer_keyboard()
    )

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 Help & Instructions\n\n"
        "How to Submit:\n"
        "1. Click \"SUBMIT YOUR ACCOUNT\"\n"
        "2. Enter Email\n"
        "3. Enter Password\n"
        "4. Wait for approval\n\n"
        "⚠️ IMPORTANT:\n"
        "After submitting, LOGOUT IMMEDIATELY\n"
        "DO NOT change password or settings\n"
        "Violation = Rejection + Ban\n\n"
        "Payout:\n"
        "Minimum: ₹25\n"
        "Click \"BALANCE\" -> Request Payout\n\n"
        "Support: @gmail_buyyyer" # Using the handle from the image
    )
    await update.message.reply_text(text, reply_markup=get_buyer_keyboard())

async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = await get_user_stats(user_id)
    
    text = (
        "📊 <b>Your Statistics</b>\n\n"
        f"📝 Total Submitted: <b>{stats.get('total', 0)}</b>\n"
        f"✅ Approved: <b>{stats.get('approved', 0)}</b>\n"
        f"❌ Rejected: <b>{stats.get('rejected', 0)}</b>\n"
        f"⏳ Pending: <b>{stats.get('pending', 0)}</b>"
    )
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=get_buyer_keyboard())

async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = await get_user_balance(user_id)
    
    text = f"💰 <b>Your Current Balance:</b> ₹{balance}"
    
    if balance >= 25:
        # Give inline button to withdraw
        keyboard = [[InlineKeyboardButton("💸 Request Payout", callback_data='request_payout')]]
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        text += "\n\n<i>Minimum payout is ₹25. Keep submitting accounts to earn more!</i>"
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=get_buyer_keyboard())

# --- PAYOUT CONVERSATION ---

async def prompt_payout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    balance = await get_user_balance(user_id)
    
    if balance < 25:
        await query.edit_message_text("❌ Minimum payout is ₹25.")
        return ConversationHandler.END
        
    await query.edit_message_text("💸 <b>Request Payout</b>\n\nPlease send your UPI ID or Payment address below:", parse_mode='HTML')
    return ASK_PAYOUT_METHOD

async def receive_payout_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    payment_method = update.message.text.strip()
    balance = await get_user_balance(user_id)
    
    if balance < 25:
        await update.message.reply_text("❌ Insufficient balance.", reply_markup=get_buyer_keyboard())
        return ConversationHandler.END
        
    success = await create_payout_request(user_id, balance, payment_method)
    if success:
        await update.message.reply_text(f"✅ <b>Payout Requested!</b>\nAmount: ₹{balance}\nMethod: {payment_method}\n\nPlease wait for admin approval.", parse_mode='HTML', reply_markup=get_buyer_keyboard())
        # Notify Admin
        d_data = await load_dump_channel()
        target_chat_id = d_data.get("channel_id") or ADMIN_USER_ID
        
        if target_chat_id:
            admin_msg = f"💸 <b>New Payout Request</b>\nUser: <code>{user_id}</code>\nAmount: ₹{balance}\nMethod: <code>{payment_method}</code>"
            try:
                await context.bot.send_message(chat_id=target_chat_id, text=admin_msg, parse_mode='HTML')
            except Exception:
                pass
    else:
        await update.message.reply_text("❌ Failed to create payout request.", reply_markup=get_buyer_keyboard())
        
    return ConversationHandler.END

# --- SUBMISSION CONVERSATION ---

async def prompt_submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_reward = await get_bot_setting("reward", 10)
            
    text = (
        "📝 SUBMIT ACCOUNT\n\n"
        "Enter your Email:\n"
        f"Reward: ₹{current_reward}\n\n"
        "Type /cancel to cancel\n"
        "Support: @gmail_buyyyer"
    )
    await update.message.reply_text(text)
    return ASK_EMAIL

async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['temp_email'] = update.message.text.strip()
    await update.message.reply_text("🔑 Now, please send the <b>Password</b>:", parse_mode='HTML')
    return ASK_PASSWORD

async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    password = update.message.text.strip()
    email = context.user_data.get('temp_email')
    
    success = await add_gmail_submission(user_id, email, password, "")
    
    if success:
        await update.message.reply_text("✅ <b>Account Submitted Successfully!</b>\nPlease wait for admin approval.", parse_mode='HTML', reply_markup=get_buyer_keyboard())
        
        # Notify Admin for Approval
        d_data = await load_dump_channel()
        target_chat_id = d_data.get("channel_id") or ADMIN_USER_ID
        
        if target_chat_id:
            admin_msg = (
                f"📝 <b>New Account Submission</b>\n\n"
                f"👤 User: <code>{user_id}</code>\n"
                f"📧 Email: <code>{email}</code>\n"
                f"🔑 Password: <code>{password}</code>\n\n"
                "Check the account and choose an action below:"
            )
            keyboard = [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_{user_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{user_id}")
                ]
            ]
            try:
                # We need to somehow store the submission ID. Since we didn't return it from add_gmail_submission,
                # we'll fetch the latest pending submission for this user.
                from database import supabase
                res = supabase.table('gmail_submissions').select('id').eq('user_id', user_id).eq('status', 'pending').order('id', desc=True).limit(1).execute()
                if res.data:
                    sub_id = res.data[0]['id']
                    keyboard = [
                        [
                            InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_{sub_id}_{user_id}"),
                            InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{sub_id}_{user_id}")
                        ]
                    ]
                await context.bot.send_message(chat_id=target_chat_id, text=admin_msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as e:
                logger.error(f"Error notifying admin: {e}")
    else:
        await update.message.reply_text("❌ Failed to submit. Please try again.", reply_markup=get_buyer_keyboard())
        
    context.user_data.pop('temp_email', None)
    return ConversationHandler.END

async def cancel_any_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # If user types something from keyboard while in conversation, just cancel and handle it
    text = update.message.text
    if text in ["📝 SUBMIT YOUR ACCOUNT", "💰 BALANCE", "📊 MY STATS", "❓ HELP"]:
        # Let the main handlers pick it up, just end conversation
        pass
    else:
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_buyer_keyboard())
    return ConversationHandler.END

# --- ADMIN APPROVAL HANDLERS ---
# Note: In a larger app, these might go in admin/handlers.py, but keeping them here for cohesion.

ASK_PAYOUT_AMOUNT = range(10, 11)

async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    sub_id = int(parts[2])
    user_id = int(parts[3])
    
    await update_submission_status(sub_id, 'rejected')
    
    await query.edit_message_text(f"{query.message.text}\n\n<b>Status:</b> ❌ REJECTED", parse_mode='HTML')
    
    # Notify user
    try:
        await context.bot.send_message(chat_id=user_id, text=f"❌ <b>Your submitted account was rejected.</b>", parse_mode='HTML')
    except Exception:
        pass

async def admin_approve_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    sub_id = int(parts[2])
    user_id = int(parts[3])
    
    context.user_data['approve_sub_id'] = sub_id
    context.user_data['approve_user_id'] = user_id
    
    await query.edit_message_text(f"{query.message.text}\n\n<b>Status:</b> ⏳ Approving... Please reply with the payout amount for this account (e.g., 5).", parse_mode='HTML')
    return ASK_PAYOUT_AMOUNT

async def admin_receive_payout_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Try again.")
        return ASK_PAYOUT_AMOUNT
        
    sub_id = context.user_data.get('approve_sub_id')
    user_id = context.user_data.get('approve_user_id')
    
    await update_submission_status(sub_id, 'approved', amount)
    await update_user_balance(user_id, amount)
    
    # Auto-add to stock for selling
    submission = await get_submission(sub_id)
    if submission:
        await add_gmail_stock(
            email=submission['email'],
            password=submission['password'],
            recovery=submission.get('recovery_email', ''),
            price=10.0  # Default selling price
        )
    
    await update.message.reply_text(f"✅ Account Approved! ₹{amount} added to user's balance. Account has been added to Shop Stock.")
    
    # Notify user
    try:
        await context.bot.send_message(chat_id=user_id, text=f"✅ <b>Account Approved!</b>\n₹{amount} has been added to your balance.", parse_mode='HTML')
    except Exception:
        pass
        
    context.user_data.pop('approve_sub_id', None)
    context.user_data.pop('approve_user_id', None)
    return ConversationHandler.END

def setup_gmail_store_handlers(application: Application):
    """Register handlers for Gmail Buyer Bot module."""
    
    # Entry point from main menu inline keyboard
    application.add_handler(CallbackQueryHandler(enter_gmail_buyer_bot, pattern='^module_gmail_store$'))
    
    # Main Keyboard Handlers
    application.add_handler(MessageHandler(filters.Regex("^❓ HELP$"), handle_help))
    application.add_handler(MessageHandler(filters.Regex("^📊 MY STATS$"), handle_stats))
    application.add_handler(MessageHandler(filters.Regex("^💰 BALANCE$"), handle_balance))
    
    # Submission Conversation
    submit_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📝 SUBMIT YOUR ACCOUNT$"), prompt_submit)],
        states={
            ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email)],
            ASK_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)]
        },
        fallbacks=[MessageHandler(filters.Regex("^(📝 SUBMIT YOUR ACCOUNT|💰 BALANCE|📊 MY STATS|❓ HELP)$"), cancel_any_conv)]
    )
    application.add_handler(submit_conv)
    
    # Payout Conversation
    payout_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(prompt_payout, pattern='^request_payout$')],
        states={
            ASK_PAYOUT_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_payout_method)]
        },
        fallbacks=[MessageHandler(filters.Regex("^(📝 SUBMIT YOUR ACCOUNT|💰 BALANCE|📊 MY STATS|❓ HELP)$"), cancel_any_conv)]
    )
    application.add_handler(payout_conv)
    
    # Admin Approval Conversation
    admin_approve_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_approve_prompt, pattern='^admin_approve_')],
        states={
            ASK_PAYOUT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_payout_amount)]
        },
        fallbacks=[CommandHandler('cancel', cancel_any_conv)]
    )
    application.add_handler(admin_approve_conv)
    
    # Admin Reject Handler
    application.add_handler(CallbackQueryHandler(admin_reject, pattern='^admin_reject_'))
    
    # --- BUY GMAIL SHOP HANDLERS ---
    application.add_handler(CallbackQueryHandler(enter_gmail_buy_shop, pattern='^module_gmail_buy_shop$'))
    application.add_handler(CallbackQueryHandler(handle_buy_gmail, pattern='^buy_gmail_account$'))
    
    # Admin Add Stock Command
    application.add_handler(CommandHandler("addstock", admin_add_stock))

# --- BUY GMAIL SHOP LOGIC ---

async def enter_gmail_buy_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when user clicks 'Buy Gmails' from main menu."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    await add_user(user_id) # Ensure user exists

    stock_count = await get_available_stock_count()
    price_per_account = 10.0 # Default price, could be made dynamic
    
    text = (
        "🛒 <b>GMAIL BUYER SHOP</b>\n\n"
        "Buy premium, verified Gmail accounts instantly using your wallet balance!\n\n"
        f"📦 <b>Available Stock:</b> {stock_count} Accounts\n"
        f"💵 <b>Price:</b> ₹{price_per_account} per account\n\n"
        "<i>Accounts are delivered automatically after purchase.</i>"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"🛒 Buy 1 Gmail (₹{price_per_account})", callback_data='buy_gmail_account')],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]
    ]
    
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_buy_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the purchase of a Gmail account."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    result = await buy_gmail_account(user_id)
    
    if not result:
        await query.edit_message_text("❌ System error. Please try again later.")
        return
        
    if 'error' in result:
        if result['error'] == 'out_of_stock':
            await query.edit_message_text("❌ <b>Out of Stock!</b>\n\nPlease check back later when admin adds more accounts.", parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='module_gmail_buy_shop')]]))
        elif result['error'] == 'insufficient_balance':
            price = result['price']
            await query.edit_message_text(f"❌ <b>Insufficient Balance!</b>\n\nYou need ₹{price} to buy an account. Keep submitting accounts to earn balance, or contact Admin to add funds.", parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='module_gmail_buy_shop')]]))
        else:
            await query.edit_message_text("❌ Failed to process purchase.")
        return
        
    # Success
    account = result['account']
    price = result['price']
    
    text = (
        "✅ <b>Purchase Successful!</b>\n\n"
        "Here are your account details:\n\n"
        f"📧 <b>Email:</b> <code>{account['email']}</code>\n"
        f"🔑 <b>Password:</b> <code>{account['password']}</code>\n"
        f"🛡️ <b>Recovery:</b> <code>{account['recovery_email'] or 'None'}</code>\n\n"
        f"<i>₹{price} has been deducted from your balance.</i>\n\n"
        "⚠️ <i>Please login and secure your account immediately.</i>"
    )
    
    # Send as new message to keep it safely in chat history
    await context.bot.send_message(chat_id=user_id, text=text, parse_mode='HTML')
    
    # Refresh shop message
    await enter_gmail_buy_shop(update, context)

async def admin_add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to quickly add stock: /addstock email:pass:recovery price"""
    user_id = update.effective_user.id
    if str(user_id) != str(ADMIN_USER_ID):
        return
        
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /addstock email:password:recovery_email [price]\nExample: /addstock test@gmail.com:pass123:rec@gmail.com 10")
        return
        
    account_str = args[0]
    parts = account_str.split(':')
    if len(parts) < 2:
        await update.message.reply_text("Invalid format. Use email:password or email:password:recovery")
        return
        
    email = parts[0]
    password = parts[1]
    recovery = parts[2] if len(parts) > 2 else ""
    
    price = 10.0
    if len(args) > 1:
        try:
            price = float(args[1])
        except ValueError:
            await update.message.reply_text("Invalid price.")
            return
            
    success = await add_gmail_stock(email, password, recovery, price)
    if success:
        await update.message.reply_text(f"✅ Stock added successfully!\nEmail: {email}\nPrice: ₹{price}")
    else:
        await update.message.reply_text("❌ Failed to add stock.")
