import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8802315206:AAGZT0wtXxLTrzxBz6JWjovRjn5NQbfyPFQ")

# Telegram API credentials for userbots (Pyrogram)
# Get these from https://my.telegram.org
API_ID = os.environ.get("API_ID", "37994485")
API_HASH = os.environ.get("API_HASH", "d6ba6dceeeb984b0fe6d6a633ca1673e")

# Supabase Credentials
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lgycsdzqjugxsmuimbmq.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxneWNzZHpxanVneHNtdWltYm1xIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEyMjQwMDUsImV4cCI6MjA5NjgwMDAwNX0.MLywf-w8uzKAJn2GXmp7oWHscuxGZGXlevTicbV3K_I")

# Admin configuration
ADMIN_USER_ID = os.environ.get("ADMIN_USER_ID", "6799525497")
if ADMIN_USER_ID:
    ADMIN_USER_ID = int(ADMIN_USER_ID)
