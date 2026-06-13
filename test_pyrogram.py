import asyncio
import os
from pyrogram import Client
from pyrogram.errors import ApiIdInvalid

API_ID = os.environ.get("API_ID", "37994485")
API_HASH = os.environ.get("API_HASH", "d6ba6dceeeb984b0fe6d6a633ca1673e")

async def test():
    try:
        client = Client(
            name="test_in_memory",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True
        )
        await client.connect()
        try:
            await client.send_code("+12345678900")
        except ApiIdInvalid:
            print("API_ID is invalid!")
        except Exception as e:
            print(f"send_code exception: {e}")
        await client.disconnect()
    except Exception as e:
        print(f"Error: {e}")

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(test())
