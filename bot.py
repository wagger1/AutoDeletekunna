import asyncio
from pyrogram import Client, filters, idle

# === Hardcoded Config ===
API_ID = "25578852"
API_HASH = "1c8e30eae03f9600dfdee4408db4811a"
BOT_TOKEN = "5937008191:AAHxqNWJSuS3GUBYmLePv7JTCA0Kwn2qwc4"
SESSION = "BQG1DzwAcBDYic6Ml-7pSmXTigL26hVY8m-ZZdRjxMda9wLFc6BJy0wONQAzwgWnZ3T5OGIN_JpwDvKdourn8yRVmETzuHXow5wnh_rCaDoI4rBT2Vp5Tb3Tt48bpkae6ftDYCWlCz7eDg8akhf8XMB0MG_ckzBxEGtU11QUucWYBTxkhvIHAJMDkyn8APSCh9D8T4ekvyTY1yPEDTdlK2YO-i2hOKeRWr5gd8kTBE-19J8UAgSGoNAnHebFYFDl9pyBrBUUtFWQbSODgKitcAo-W5Znh2Lh0KSG9cJLpIqQMZfWoW-hmJpMmxTA7aPhXrj-Y48Y14mIqS6tJyD5XzT4Y26nIwAAAAFRWb3RAA"
TIME = 320

GROUPS = [-1001890267303, -1002034897292, -1002182767754, -1001896199579]
ADMINS = [1739381637]
WHITE_LIST = [1739381637]

START_MSG = "<b>Hai {},\nI'm a simple bot to delete group messages after a specific time</b>"

# === Clients ===
User = Client(
    name="userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION,
    workers=300
)

Bot = Client(
    "auto-delete",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=300
)

# === Handlers ===
@Bot.on_message(filters.command("start") & filters.private)
async def start(bot, message):
    name = message.from_user.mention if message.from_user else "User"
    await message.reply(START_MSG.format(name))


@User.on_message(filters.chat(GROUPS))
async def delete(user, message):
    try:
        if message.from_user and message.from_user.id in ADMINS:
            return
        await asyncio.sleep(TIME)
        await Bot.delete_messages(message.chat.id, message.message_id)
    except Exception as e:
        print(f"[ERROR] Failed to delete message: {e}")

# === Main runner ===
async def main():
    await User.start()
    print("[✅] User Started")

    await Bot.start()
    print("[✅] Bot Started")

    await idle()

    await User.stop()
    print("[⚠️] User Stopped")

    await Bot.stop()
    print("[⚠️] Bot Stopped")


if __name__ == "__main__":
    asyncio.run(main())
