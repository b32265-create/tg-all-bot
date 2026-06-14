import io
import json
from pyrogram import Client

async def upload_data_to_channel(bot: Client, channel_id: int, data: dict, filename: str = "data.json") -> int:
    """
    Uploads a dictionary/JSON data to a Telegram channel as a file.
    Returns the message ID which can be saved in your Supabase DB.
    """
    try:
        # Convert data to JSON string and then to bytes
        json_data = json.dumps(data, indent=4).encode('utf-8')
        file_obj = io.BytesIO(json_data)
        file_obj.name = filename
        
        # Send document to the dump channel
        message = await bot.send_document(
            chat_id=channel_id,
            document=file_obj,
            caption="Data Backup"
        )
        return message.id
    except Exception as e:
        print(f"Error uploading to channel: {e}")
        return 0

async def get_data_from_channel(bot: Client, channel_id: int, message_id: int) -> dict:
    """
    Downloads and reads the JSON data from the Telegram channel message ID.
    Returns the parsed dictionary.
    """
    try:
        # Fetch the message
        message = await bot.get_messages(chat_id=channel_id, message_ids=message_id)
        
        if not message or not message.document:
            return {}
            
        # Download the file into memory
        file_bytes = await bot.download_media(message.document, in_memory=True)
        
        # Parse JSON
        data = json.loads(file_bytes.getvalue().decode('utf-8'))
        return data
    except Exception as e:
        print(f"Error reading from channel: {e}")
        return {}

async def upload_text_to_channel(bot: Client, channel_id: int, text: str) -> int:
    """
    Uploads long text (like a large ad_message or config) to the channel.
    Returns the message ID.
    """
    try:
        message = await bot.send_message(chat_id=channel_id, text=text)
        return message.id
    except Exception as e:
        print(f"Error sending text: {e}")
        return 0

async def get_text_from_channel(bot: Client, channel_id: int, message_id: int) -> str:
    """
    Reads text from a specific message ID in the dump channel.
    """
    try:
        message = await bot.get_messages(chat_id=channel_id, message_ids=message_id)
        return message.text if message and message.text else ""
    except Exception as e:
        print(f"Error reading text: {e}")
        return ""
