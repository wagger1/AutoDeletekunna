import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient

# ── ENVIRONMENT ─────────────────────────────
API_ID        = int(os.getenv("API_ID", "0"))
API_HASH      = os.getenv("API_HASH", "")
BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
MONGO_URI     = os.getenv("MONGO_URI", "")
DEFAULT_PURGE_SECONDS = int(os.getenv("PURGE_SECONDS", "600"))
LOG_CHAT_ID   = int(os.getenv("LOG_CHAT_ID", "0"))  # optional logging group

if not all((API_ID, API_HASH, BOT_TOKEN, MONGO_URI)):
    raise RuntimeError("Missing required environment variables.")

# ── LOGGER ──────────────────────────────────
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")

# ── DATABASE ────────────────────────────────
mongo = MongoClient(MONGO_URI)
db = mongo["autopurgebot"]
group_config = db["delays"]

# ── BOT INIT ────────────────────────────────
bot = Client("auto_purge_worker", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ── COMMAND: Set Delay ──────────────────────
@bot.on_message(filters.command("setdelay") & filters.group)
async def set_delay(client: Client, message: Message):
    if not message.from_user or not message.from_user.is_chat_admin:
        return await message.reply("Only admins can set the delay.")

    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        return await message.reply("Usage: /setdelay <seconds>")

    delay = int(args[1])
    group_config.update_one(
        {"chat_id": message.chat.id},
        {"$set": {"delay": delay}},
        upsert=True
    )
    await message.reply(f"✅ Auto-delete delay set to {delay} seconds for this group.")

# ── COMMAND: Get Current Delay ──────────────
@bot.on_message(filters.command("getdelay") & filters.group)
async def get_delay(client: Client, message: Message):
    config = group_config.find_one({"chat_id": message.chat.id})
    delay = config["delay"] if config and "delay" in config else DEFAULT_PURGE_SECONDS
    await message.reply(f"🕒 Current auto-delete delay: {delay} seconds.")

# ── COMMAND: Bot Status ─────────────────────
@bot.on_message(filters.command("status") & filters.private)
async def status(client: Client, message: Message):
    count = group_config.count_documents({})
    await message.reply(
        f"✅ Bot is running.\n"
        f"🧠 Groups with custom delay: {count}\n"
        f"🕒 Default delay: {DEFAULT_PURGE_SECONDS} sec"
    )

# ── MESSAGE HANDLER: Auto Purge ─────────────
@bot.on_message(filters.group & ~filters.service)
async def auto_purge(client: Client, message: Message):
    config = group_config.find_one({"chat_id": message.chat.id})
    delay = config["delay"] if config and "delay" in config else DEFAULT_PURGE_SECONDS

    try:
        await asyncio.sleep(delay)
        await message.delete()

        # Optional: log deletion to another group
        if LOG_CHAT_ID:
            text = (
                f"🧹 Message deleted from [{message.chat.title}](https://t.me/c/{str(message.chat.id)[4:]}/{message.id})\n"
                f"👤 User: {message.from_user.mention if message.from_user else 'Unknown'}\n"
                f"🕒 Delay: {delay} sec"
            )
            await client.send_message(LOG_CHAT_ID, text, disable_web_page_preview=True)
    except Exception as e:
        logging.warning(f"Failed to delete message in {message.chat.id}: {e}")
