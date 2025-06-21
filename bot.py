import asyncio
from os import environ
from pyrogram import Client, filters, idle

# === Environment variable helpers ===
def get_env_int(name):
    try:
        return int(environ[name])
    except KeyError:
        raise ValueError(f"Missing required environment variable: {name}")
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer")

def get_env_list(name):
    value = environ.get(name)
    if not value:
        raise ValueError(f"Missing or empty environment variable: {name}")
    return [int(x) for x in value.split()]

# === Load required environment variables ===
API_ID = get_env_int("API_ID")
API_HASH = environ.get("API_HASH") or exit("Missing API_HASH")
BOT_TOKEN = environ.get("BOT_TOKEN") or exit("Missing BOT_TOKEN")
SESSION = environ.get("SESSION") or exit("Missing SESSION")
TIME = get_env_int("TIME")

GROUPS = get_env_list("GROUPS")
ADMINS = get_env_list("ADMINS")

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
