import asyncio
from pyrogram import Client

API_ID = int("25578852")
API_HASH = "1c8e30eae03f9600dfdee4408db4811a"
SESSION = "BQG1DzwAcBDYic6Ml-7pSmXTigL26hVY8m-ZZdRjxMda9wLFc6BJy0wONQAzwgWnZ3T5OGIN_JpwDvKdourn8yRVmETzuHXow5wnh_rCaDoI4rBT2Vp5Tb3Tt48bpkae6ftDYCWlCz7eDg8akhf8XMB0MG_ckzBxEGtU11QUucWYBTxkhvIHAJMDkyn8APSCh9D8T4ekvyTY1yPEDTdlK2YO-i2hOKeRWr5gd8kTBE-19J8UAgSGoNAnHebFYFDl9pyBrBUUtFWQbSODgKitcAo-W5Znh2Lh0KSG9cJLpIqQMZfWoW-hmJpMmxTA7aPhXrj-Y48Y14mIqS6tJyD5XzT4Y26nIwAAAAFRWb3RAA"

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
