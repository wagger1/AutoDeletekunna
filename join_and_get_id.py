import asyncio
from pyrogram import Client

API_ID = int("your_api_id")
API_HASH = "your_api_hash"
SESSION = "your_userbot_string_session"

GROUP_USERNAME = "yourgroupusername"  # e.g., "mygroupchannel"

async def main():
    async with Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION) as app:
        try:
            # Join the group
            await app.join_chat(GROUP_USERNAME)
            print(f"✅ Joined {GROUP_USERNAME}")
        except Exception as e:
            print(f"⚠️ Already joined or failed to join: {e}")

        # Get chat info
        chat = await app.get_chat(GROUP_USERNAME)
        print(f"Group Name : {chat.title}")
        print(f"Group ID   : {chat.id}")

asyncio.run(main())
