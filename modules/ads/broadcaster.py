import asyncio
import logging
import random
from pyrogram import Client, enums, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from config import API_ID, API_HASH
from database import get_ads_config, get_hosted_accounts, update_ads_config, get_all_active_accounts, get_excluded_groups
from modules.ads.utils import flood_wait_countdown

logger = logging.getLogger(__name__)

# Keep track of running broadcast tasks: user_id -> asyncio.Task
active_broadcasts = {}

# Keep track of running Pyrogram clients for instant auto-reply: user_id -> {account_id: Client}
active_clients = {}

async def init_all_clients():
    """Starts Pyrogram clients for ALL active accounts in the DB on bot startup."""
    accounts = await get_all_active_accounts()
    logger.info(f"Initializing {len(accounts)} Userbots for 24/7 listening...")
    for acc in accounts:
        user_id = acc.get('user_id')
        await start_client_if_needed(user_id, acc)

import time

auto_reply_cooldowns = {}  # {target_chat_id: timestamp}

async def start_client_if_needed(user_id: int, account: dict):
    session_string = account.get('session_string')
    if not session_string:
        return None
    acc_id = account.get('id')
    
    if user_id not in active_clients:
        active_clients[user_id] = {}
        
    if acc_id in active_clients[user_id]:
        return active_clients[user_id][acc_id]
        
    client = Client(
        name=f"session_{acc_id}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        in_memory=True
    )
    
    @client.on_message(filters.private & ~filters.me)
    async def instant_auto_reply(c: Client, m: Message):
        # Anti-Loop Cooldown: Only reply once per 10 minutes per user
        chat_id = m.chat.id
        now = time.time()
        if chat_id in auto_reply_cooldowns and now - auto_reply_cooldowns[chat_id] < 600:
            return
            
        conf = await get_ads_config(user_id)
        if not conf: return
        mode = conf.get('auto_reply_mode', 'off')
        if mode == 'off': return
        
        reply_text = conf.get('auto_reply_message') or conf.get('ad_message')
        if not reply_text: return
        
        try:
            await m.reply_text(reply_text, parse_mode=enums.ParseMode.HTML)
            auto_reply_cooldowns[chat_id] = now
            logger.info(f"User {user_id}: INSTANT Auto Reply sent to {m.chat.id}")
        except Exception as e:
            logger.error(f"User {user_id}: Auto reply failed: {e}")
            
    try:
        await client.start()
        
        # Populate in-memory peer cache to prevent "Peer id invalid" errors
        try:
            async for _ in client.get_dialogs(limit=50):
                pass
        except Exception:
            pass
            
        active_clients[user_id][acc_id] = client
        logger.info(f"User {user_id}: Started and cached account {account.get('phone_number')} for 24/7 Auto Reply")
        return client
    except Exception as e:
        logger.error(f"User {user_id}: Failed to start account {account.get('phone_number')}: {e}")
        return None

async def _send_ads_for_account(user_id: int, account: dict, config: dict, bot):
    """Connects to Pyrogram for a single account and sends the ad message to all groups."""
    client = await start_client_if_needed(user_id, account)
    if not client:
        return 0
        
    try:
        # Target: Auto-fetch all Groups and Supergroups
        # In a production environment, you might limit the count or allow users to specify groups
        target_chats = []
        async for dialog in client.get_dialogs():
            if dialog.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
                target_chats.append(dialog.chat.id)
                
        logger.info(f"User {user_id}: Found {len(target_chats)} target groups for {account.get('phone_number')}")
        
        target_type = config.get('target_type', 'groups')
        ad_message = config.get('ad_message')
        if not ad_message:
            return 0
            
        excluded_groups = await get_excluded_groups(user_id)
            
        sent_count = 0
        # Send messages with Anti-Ban delay
        for chat_id in target_chats:
            chat_str = str(chat_id)
            chat_obj = await client.get_chat(chat_id)
            chat_username = f"@{chat_obj.username}" if chat_obj.username else ""
            chat_link = chat_obj.invite_link if chat_obj.invite_link else ""
            
            skip = False
            for excl in excluded_groups:
                if excl == chat_str or excl.lower() == chat_username.lower() or (excl and chat_link and excl in chat_link):
                    skip = True
                    break
            
            if skip:
                logger.info(f"User {user_id}: Skipping excluded group {chat_id}")
                continue
                
            try:
                if target_type == 'dms':
                    # Send to the user who sent the latest message
                    async for msg in client.get_chat_history(chat_id, limit=1):
                        if msg.from_user and not msg.from_user.is_bot:
                            await client.send_message(chat_id=msg.from_user.id, text=ad_message, parse_mode=enums.ParseMode.HTML)
                            logger.info(f"User {user_id}: Sent DM to {msg.from_user.id} from group {chat_id}")
                            sent_count += 1
                            
                    delay = random.randint(300, 600)
                    logger.info(f"User {user_id}: Waiting {delay} seconds (Safe DM Anti-Ban) before next DM...")
                    await asyncio.sleep(delay)
                else:
                    # Send to the group directly
                    await client.send_message(chat_id=chat_id, text=ad_message, parse_mode=enums.ParseMode.HTML)
                    logger.info(f"User {user_id}: Sent ad to group {chat_id}")
                    sent_count += 1
                    await asyncio.sleep(5)  # Smart delay between messages
            except FloodWait as e:
                logger.warning(f"User {user_id}: FloodWait for {e.value} seconds")
                await flood_wait_countdown(user_id, account.get('phone_number', 'Unknown'), "Broadcast Ads", e.value, bot)
            except Exception as e:
                logger.debug(f"User {user_id}: Could not send ad to {chat_id}: {e}")
                await asyncio.sleep(1)
                
        # Auto Reply logic is now fully handled instantly by the @client.on_message event!
        # So we do NOT stop the client here anymore. It stays alive in the background.
        
        return sent_count
    except Exception as e:
        logger.error(f"User {user_id}: Error running account {account.get('phone_number')}: {e}")
        return 0

async def broadcast_loop(user_id: int, bot_app):
    """The infinite background loop that sends ads."""
    logger.info(f"User {user_id}: Broadcast loop started.")
    try:
        while True:
            # Re-fetch config to get latest interval or message updates
            config = await get_ads_config(user_id)
            if not config or config.get('status') != 'running':
                break
                
            accounts = await get_hosted_accounts(user_id)
            if not accounts:
                logger.warning(f"User {user_id}: No active accounts found. Stopping broadcast.")
                break
                
            current_cycles = config.get('current_cycles', 0)
            max_cycles = config.get('max_cycles', 0)
            if max_cycles > 0 and current_cycles >= max_cycles:
                logger.info(f"User {user_id}: Max cycles reached. Stopping broadcast.")
                break
                
            logger.info(f"User {user_id}: Starting broadcast cycle.")
            
            # Round-robin account selection: "har cycle ke baad another account se run karna"
            last_index = config.get('last_used_account_index', -1)
            next_index = (last_index + 1) % len(accounts)
            selected_account = accounts[next_index]
            
            # Send ads from the single selected account for this cycle
            sent_in_cycle = await _send_ads_for_account(user_id, selected_account, config, bot_app.bot)
                
            # Update cycles, total sent messages, and last used account
            current_cycles = config.get('current_cycles', 0)
            total_sent = config.get('total_messages_sent', 0)
            
            await update_ads_config(user_id, {
                'current_cycles': current_cycles + 1,
                'total_messages_sent': total_sent + sent_in_cycle,
                'last_used_account_index': next_index
            })
            
            # Fetch config again just in case it was paused during execution
            config = await get_ads_config(user_id)
            if not config: break
            
            interval_minutes = config.get('interval_minutes', 30)
            logger.info(f"User {user_id}: Cycle completed. Waiting for {interval_minutes} minutes.")
            
            # Sleep for the interval
            await asyncio.sleep(interval_minutes * 60)
            
    except asyncio.CancelledError:
        logger.info(f"User {user_id}: Broadcast loop cancelled.")
    except Exception as e:
        logger.error(f"User {user_id}: Broadcast loop crashed: {e}")
    finally:
        # Cleanup tasks ONLY, clients stay alive 24/7
        if user_id in active_broadcasts:
            del active_broadcasts[user_id]
            
        await update_ads_config(user_id, {'status': 'paused'})

async def start_broadcaster(user_id: int, bot_app):
    """Start the background task for the user."""
    if user_id in active_broadcasts:
        return False, "Ads are already running!"
        
    config = await get_ads_config(user_id)
    if not config or not config.get('ad_message'):
        return False, "You must set an Ad Message first!"
        
    accounts = await get_hosted_accounts(user_id)
    if not accounts:
        return False, "You need to add at least one account before starting ads!"
        
    # Update status to running
    await update_ads_config(user_id, {'status': 'running'})
    
    # Create background task
    task = asyncio.create_task(broadcast_loop(user_id, bot_app))
    active_broadcasts[user_id] = task
    return True, "Broadcasting started successfully!"

async def stop_broadcaster(user_id: int):
    """Stop the background task for the user."""
    if user_id in active_broadcasts:
        active_broadcasts[user_id].cancel()
        del active_broadcasts[user_id]
        
    await update_ads_config(user_id, {'status': 'paused'})
    return True, "Broadcasting stopped successfully! Userbots are still listening for auto-replies."
