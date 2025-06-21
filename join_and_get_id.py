import asyncio
from pyrogram import Client

API_ID = int("your_api_id")
API_HASH = "your_api_hash"
SESSION = "your_userbot_string_session"

GROUP_ID = -1001896199579  # 🔁 Replace with your actual group ID

async def main():
    async with Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION) as app:
        try:
            chat = await app.get_chat(GROUP_ID)
            print(f"✅ Group found!")
            print(f"Group Title : {chat.title}")
            print(f"Group ID    : {chat.id}")
        except Exception as e:
            print(f"❌ Cannot access group ID {GROUP_ID}: {e}")

asyncio.run(main())
