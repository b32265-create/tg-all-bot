import asyncio
import logging

logger = logging.getLogger(__name__)

async def flood_wait_countdown(user_id: int, phone: str, action: str, wait_seconds: int, bot):
    """
    Shows a live countdown message to the user for a FloodWait exception.
    Updates the message every 10 seconds.
    """
    try:
        msg = await bot.send_message(
            chat_id=user_id,
            text=f"⏳ **FloodWait Active!**\n\nAccount: `{phone}`\nAction: `{action}`\nWait time: `{wait_seconds}` seconds.\n\n_Please wait..._",
            parse_mode='Markdown'
        )
        
        remaining = wait_seconds
        while remaining > 0:
            await asyncio.sleep(min(10, remaining))
            remaining -= 10
            if remaining <= 0:
                break
                
            try:
                await msg.edit_text(
                    text=f"⏳ **FloodWait Active!**\n\nAccount: `{phone}`\nAction: `{action}`\nWait time left: `{remaining}` seconds.\n\n_Please wait..._",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.warning(f"Failed to update flood wait message: {e}")
                
        await msg.edit_text(
            text=f"✅ **FloodWait Over!**\n\nAccount: `{phone}`\nAction: `{action}` resumed.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error in flood_wait_countdown: {e}")
        # Fallback to simple sleep if message sending fails
        await asyncio.sleep(wait_seconds)
