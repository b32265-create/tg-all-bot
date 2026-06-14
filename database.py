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
        logger.error(f"Error checking trial usage: {e}")
        return False

# --- GMAIL BUYER/SELLER METHODS ---

async def get_available_stock_count() -> int:
    """Get the number of available Gmail accounts in stock."""
    if not supabase: return 0
    try:
        res = supabase.table('gmail_stock').select('id', count='exact').eq('status', 'available').execute()
        return res.count if res.count else 0
    except Exception as e:
        logger.error(f"Error getting stock count: {e}")
        return 0

async def add_gmail_stock(email: str, password: str, recovery: str, price: float = 10.0) -> bool:
    """Add a new Gmail to the stock."""
    if not supabase: return False
    try:
        supabase.table('gmail_stock').insert({
            'email': email,
            'password': password,
            'recovery_email': recovery,
            'price': price,
            'status': 'available'
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Error adding stock: {e}")
        return False

async def buy_gmail_account(user_id: int) -> dict:
    """Buy a Gmail account from stock if user has enough balance. Returns the account dict or None."""
    if not supabase: return None
    try:
        # Check balance
        balance = await get_user_balance(user_id)
        
        # Get one available stock
        res = supabase.table('gmail_stock').select('*').eq('status', 'available').limit(1).execute()
        if not res.data:
            return {'error': 'out_of_stock'}
            
        account = res.data[0]
        price = account.get('price', 10.0)
        
        if balance < price:
            return {'error': 'insufficient_balance', 'price': price}
            
        # Deduct balance
        new_balance = balance - float(price)
        supabase.table('user_balances').update({'balance': new_balance}).eq('user_id', user_id).execute()
        
        # Mark as sold
        supabase.table('gmail_stock').update({'status': 'sold', 'buyer_id': user_id}).eq('id', account['id']).execute()
        
        return {'success': True, 'account': account, 'price': price}
    except Exception as e:
        logger.error(f"Error buying gmail account: {e}")
        return {'error': 'system_error'}

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

# --- Gmail Store Functions ---

async def get_user_balance(user_id: int) -> float:
    """Get a user's wallet balance."""
    if not supabase: return 0.0
    try:
        res = supabase.table('user_balances').select('balance').eq('user_id', user_id).execute()
        if not res.data:
            supabase.table('user_balances').insert({'user_id': user_id, 'balance': 0.0}).execute()
            return 0.0
        return float(res.data[0]['balance'])
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        return 0.0

async def update_user_balance(user_id: int, amount_change: float) -> bool:
    """Add or subtract from a user's balance."""
    if not supabase: return False
    try:
        current_balance = await get_user_balance(user_id)
        new_balance = current_balance + amount_change
        if new_balance < 0:
            return False # Insufficient funds
        supabase.table('user_balances').update({'balance': new_balance}).eq('user_id', user_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating balance: {e}")
        return False

async def add_gmail_submission(user_id: int, email: str, password: str, recovery_email: str):
    """Add a new Gmail account submission."""
    if not supabase: return False
    try:
        supabase.table('gmail_submissions').insert({
            'user_id': user_id,
            'email': email,
            'password': password,
            'recovery_email': recovery_email,
            'status': 'pending'
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Error adding gmail submission: {e}")
        return False

async def get_user_stats(user_id: int):
    """Get the stats of a user's submissions."""
    if not supabase: return {'total': 0, 'approved': 0, 'rejected': 0, 'pending': 0}
    try:
        res = supabase.table('gmail_submissions').select('status').eq('user_id', user_id).execute()
        stats = {'total': 0, 'approved': 0, 'rejected': 0, 'pending': 0}
        if res.data:
            stats['total'] = len(res.data)
            for item in res.data:
                status = item.get('status')
                if status in stats:
                    stats[status] += 1
        return stats
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {'total': 0, 'approved': 0, 'rejected': 0, 'pending': 0}

async def get_submission(submission_id: int):
    """Get a submission by ID."""
    if not supabase: return None
    try:
        res = supabase.table('gmail_submissions').select('*').eq('id', submission_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"Error getting submission: {e}")
        return None

async def update_submission_status(submission_id: int, status: str, payout_amount: float = 0.0):
    """Update status of a submission."""
    if not supabase: return False
    try:
        updates = {'status': status}
        if payout_amount > 0:
            updates['payout_amount'] = payout_amount
        supabase.table('gmail_submissions').update(updates).eq('id', submission_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating submission: {e}")
        return False

async def create_payout_request(user_id: int, amount: float, payment_method: str):
    """Create a new payout request."""
    if not supabase: return False
    try:
        # First deduct the balance to prevent double requests
        success = await update_user_balance(user_id, -amount)
        if not success: return False
        
        supabase.table('payout_requests').insert({
            'user_id': user_id,
            'amount': amount,
            'payment_method': payment_method,
            'status': 'pending'
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Error creating payout request: {e}")
        # Could attempt to refund balance here on failure
        return False

async def update_payout_request_status(request_id: int, status: str):
    """Update a payout request."""
    if not supabase: return False
    try:
        supabase.table('payout_requests').update({'status': status}).eq('id', request_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating payout request: {e}")
        return False

# --- Bot Settings (Render Safe) ---

async def get_bot_setting(setting_key: str, default_value=None):
    """Get a generic setting from the database."""
    if not supabase: return default_value
    try:
        res = supabase.table('bot_settings').select('setting_value').eq('setting_key', setting_key).execute()
        if res.data:
            return res.data[0]['setting_value']
        return default_value
    except Exception as e:
        logger.error(f"Error getting setting {setting_key}: {e}")
        return default_value

async def update_bot_setting(setting_key: str, setting_value):
    """Update or insert a generic setting in the database."""
    if not supabase: return False
    try:
        res = supabase.table('bot_settings').select('setting_key').eq('setting_key', setting_key).execute()
        if res.data:
            supabase.table('bot_settings').update({'setting_value': setting_value}).eq('setting_key', setting_key).execute()
        else:
            supabase.table('bot_settings').insert({'setting_key': setting_key, 'setting_value': setting_value}).execute()
        return True
    except Exception as e:
        logger.error(f"Error updating setting {setting_key}: {e}")
        return False

# IMPORTANT: Run these SQL commands in your Supabase SQL editor:
'''
CREATE TABLE IF NOT EXISTS bot_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

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

CREATE TABLE IF NOT EXISTS user_balances (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
    balance NUMERIC DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS gmail_submissions (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    user_id BIGINT REFERENCES users(user_id),
    email TEXT NOT NULL,
    password TEXT NOT NULL,
    recovery_email TEXT,
    status TEXT DEFAULT 'pending',
    payout_amount NUMERIC DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payout_requests (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    user_id BIGINT REFERENCES users(user_id),
    amount NUMERIC NOT NULL,
    payment_method TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gmail_stock (
    id BIGINT PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    email TEXT NOT NULL,
    password TEXT NOT NULL,
    recovery_email TEXT,
    price NUMERIC DEFAULT 10.0,
    status TEXT DEFAULT 'available',
    buyer_id BIGINT REFERENCES users(user_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
'''
