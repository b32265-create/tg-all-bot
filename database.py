import logging
import datetime
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

supabase: Client | None = None

if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL != "YOUR_SUPABASE_URL_HERE":
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")

async def init_db():
    """Initialize or verify the database connection."""
    if not supabase:
        logger.warning("Supabase is not configured. Database will not work until credentials are provided.")
        return
    logger.info("Supabase client initialized.")

async def add_user(user_id: int):
    """Add a new user if they don't exist."""
    if not supabase: return
    try:
        res = supabase.table('users').select('*').eq('user_id', user_id).execute()
        if not res.data:
            supabase.table('users').insert({'user_id': user_id}).execute()
    except Exception as e:
        logger.error(f"Error adding user: {e}")

async def get_hosted_accounts_count(user_id: int) -> int:
    """Get the number of accounts hosted by the user."""
    if not supabase: return 0
    try:
        res = supabase.table('accounts').select('id', count='exact').eq('user_id', user_id).eq('status', 'active').execute()
        return res.count if res.count is not None else len(res.data) if res.data else 0
    except Exception as e:
        logger.error(f"Error getting hosted accounts: {e}")
        return 0

async def add_hosted_account(user_id: int, phone_number: str, session_string: str):
    """Add a new hosted account for the user."""
    if not supabase: return
    try:
        supabase.table('accounts').insert({
            'user_id': user_id,
            'phone_number': phone_number,
            'session_string': session_string
        }).execute()
    except Exception as e:
        logger.error(f"Error adding hosted account: {e}")

async def get_hosted_accounts(user_id: int):
    """Get all active hosted accounts for the user."""
    if not supabase: return []
    try:
        res = supabase.table('accounts').select('*').eq('user_id', user_id).eq('status', 'active').execute()
        return res.data if res.data else []
    except Exception as e:
        logger.error(f"Error getting hosted accounts details: {e}")
        return []

async def get_all_active_accounts():
    """Get all active hosted accounts across all users."""
    if not supabase: return []
    try:
        res = supabase.table('accounts').select('*').eq('status', 'active').execute()
        return res.data if res.data else []
    except Exception as e:
        logger.error(f"Error getting all hosted accounts: {e}")
        return []

async def delete_account(account_id: int):
    """Delete a hosted account by ID."""
    if not supabase: return False
    try:
        supabase.table('accounts').delete().eq('id', account_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error deleting account {account_id}: {e}")
        return False

async def get_ads_config(user_id: int):
    """Get the user's ads configuration, create default if not exists."""
    if not supabase: return None
    try:
        res = supabase.table('ads_config').select('*').eq('user_id', user_id).execute()
        if not res.data:
            # Create default
            supabase.table('ads_config').insert({'user_id': user_id}).execute()
            res = supabase.table('ads_config').select('*').eq('user_id', user_id).execute()
        
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"Error getting ads config: {e}")
        return None

async def update_ads_config(user_id: int, updates: dict):
    """Update ads configuration for a user."""
    if not supabase: return
    try:
        supabase.table('ads_config').update(updates).eq('user_id', user_id).execute()
    except Exception as e:
        logger.error(f"Error updating ads config: {e}")

async def get_user_plan_status(user_id: int) -> str:
    """Return the user's plan status: 'Premium', 'Trial', or 'Free'."""
    if not supabase: return "Free"
    try:
        res = supabase.table('users').select('is_premium, created_at').eq('user_id', user_id).execute()
        if res.data and len(res.data) > 0:
            user_data = res.data[0]
            if user_data.get('is_premium', False):
                return "Premium"
            
            created_at_str = user_data.get('created_at')
            if created_at_str:
                try:
                    created_at = datetime.datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    if datetime.datetime.now(datetime.timezone.utc) - created_at < datetime.timedelta(days=2):
                        return "Trial"
                except Exception as e:
                    logger.error(f"Error parsing created_at: {e}")
        return "Free"
    except Exception as e:
        logger.error(f"Error checking plan status: {e}")
        return "Free"

async def is_premium_user(user_id: int) -> bool:
    """Check if the user is a premium user or in trial."""
    status = await get_user_plan_status(user_id)
    return status in ["Premium", "Trial"]

async def update_user_premium_status(user_id: int, status: bool):
    """Update premium status of a user."""
    if not supabase: return False
    try:
        supabase.table('users').update({'is_premium': status}).eq('user_id', user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating premium status: {e}")
        return False

async def get_total_users() -> int:
    """Get the total number of registered users."""
    if not supabase: return 0
    try:
        res = supabase.table('users').select('user_id', count='exact').execute()
        return res.count if res.count is not None else len(res.data) if res.data else 0
    except Exception as e:
        logger.error(f"Error getting total users: {e}")
        return 0

async def get_all_users():
    """Get all registered users."""
    if not supabase: return []
    try:
        res = supabase.table('users').select('*').execute()
        return res.data if res.data else []
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        return []

async def add_excluded_group(user_id: int, group_id_or_link: str):
    """Add a group to the excluded list."""
    if not supabase: return
    try:
        supabase.table('excluded_groups').insert({
            'user_id': user_id,
            'group_id_or_link': group_id_or_link
        }).execute()
    except Exception as e:
        logger.error(f"Error adding excluded group: {e}")

async def remove_excluded_group(user_id: int, group_id_or_link: str):
    """Remove a group from the excluded list."""
    if not supabase: return
    try:
        supabase.table('excluded_groups').delete().eq('user_id', user_id).eq('group_id_or_link', group_id_or_link).execute()
    except Exception as e:
        logger.error(f"Error removing excluded group: {e}")

async def get_excluded_groups(user_id: int):
    """Get all excluded groups for a user."""
    if not supabase: return []
    try:
        res = supabase.table('excluded_groups').select('group_id_or_link').eq('user_id', user_id).execute()
        return [item['group_id_or_link'] for item in res.data] if res.data else []
    except Exception as e:
        logger.error(f"Error getting excluded groups: {e}")
        return []

# IMPORTANT: Run these SQL commands in your Supabase SQL editor:
'''
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    is_premium BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS accounts (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    user_id BIGINT REFERENCES users(user_id),
    phone_number TEXT,
    session_string TEXT,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS ads_config (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
    ad_message TEXT,
    interval_minutes INTEGER DEFAULT 30,
    target_type TEXT DEFAULT 'groups',
    max_cycles INTEGER DEFAULT 0,
    current_cycles INTEGER DEFAULT 0,
    status TEXT DEFAULT 'paused',
    ai_reply BOOLEAN DEFAULT FALSE,
    auto_reply_mode TEXT DEFAULT 'off',
    auto_reply_message TEXT,
    last_used_account_index INTEGER DEFAULT -1,
    total_messages_sent INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS excluded_groups (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    user_id BIGINT REFERENCES users(user_id),
    group_id_or_link TEXT NOT NULL
);
'''
