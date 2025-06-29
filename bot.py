import os
import re
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient
import threading
from flask import Flask

API_ID        = int(os.getenv("API_ID", "0"))
API_HASH      = os.getenv("API_HASH", "")
BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
MONGO_URI     = os.getenv("MONGO_URI", "")
DEFAULT_PURGE_SECONDS = int(os.getenv("PURGE_SECONDS", "600"))
LOG_CHAT_ID   = int(os.getenv("LOG_CHAT_ID", "0"))

if not all((API_ID, API_HASH, BOT_TOKEN, MONGO_URI)):
    raise RuntimeError("Missing required environment variables.")

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")

mongo = MongoClient(MONGO_URI)
db = mongo["autopurgebot"]
group_config = db["delays"]

bot = Client("auto_purge_worker", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def get_group_config(chat_id):
    config = group_config.find_one({"chat_id": chat_id}) or {}
    return {
        "delay": config.get("delay", DEFAULT_PURGE_SECONDS),
        "block_links": config.get("block_links", True),
        "block_mentions": config.get("block_mentions", True),
        "whitelist_usernames": config.get("whitelist_usernames", []),
        "whitelist_domains": config.get("whitelist_domains", [])
    }

warned_users = {}

async def warn_once(client, message: Message):
    key = f"{message.chat.id}:{message.from_user.id if message.from_user else 0}"
    if key in warned_users:
        return
    warned_users[key] = True
    await message.reply("⚠️ Links or @mentions are not allowed in this group.")

@bot.on_message(filters.group & ~filters.service)
async def auto_purge(client: Client, message: Message):
    cfg = get_group_config(message.chat.id)
    text = (message.text or message.caption or "").lower()

    is_whitelisted_user = any(u in text for u in cfg["whitelist_usernames"])
    is_whitelisted_domain = any(d in text for d in cfg["whitelist_domains"])

    has_link = bool(re.search(r"(http[s]?://|t\.me/|telegram\.me/)", text))
    has_mention = bool(re.search(r"@\w{3,}", text))

    if (
        (cfg["block_links"] and has_link and not is_whitelisted_domain) or
        (cfg["block_mentions"] and has_mention and not is_whitelisted_user)
    ):
        try:
            await message.delete()
            await warn_once(client, message)
            if LOG_CHAT_ID:
                await client.send_message(
                    LOG_CHAT_ID,
                    f"🚫 Link or mention deleted in [{message.chat.title}](https://t.me/c/{str(message.chat.id)[4:]}/{message.id})",
                    disable_web_page_preview=True
                )
            return
        except Exception as e:
            logging.warning(f"Failed to delete filtered message: {e}")
            return

    try:
        await asyncio.sleep(cfg["delay"])
        await message.delete()
        if LOG_CHAT_ID:
            await client.send_message(
                LOG_CHAT_ID,
                f"🧹 Message auto-deleted in [{message.chat.title}](https://t.me/c/{str(message.chat.id)[4:]}/{message.id})",
                disable_web_page_preview=True
            )
    except Exception as e:
        logging.warning(f"Failed to delete after delay: {e}")

# ─── Admin Commands ─────────────────────────

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
    await message.reply(f"✅ Auto-delete delay set to {delay} seconds.")

@bot.on_message(filters.command("getdelay") & filters.group)
async def get_delay(client: Client, message: Message):
    cfg = get_group_config(message.chat.id)
    await message.reply(f"🕒 Current delay: {cfg['delay']} seconds.")

@bot.on_message(filters.command(["blocklinks", "blockmentions"]) & filters.group)
async def toggle_blocking(client, message):
    if not message.from_user or not message.from_user.is_chat_admin:
        return await message.reply("Admins only.")
    cmd = message.command[0]
    value = message.text.split()[-1].lower() == "on"
    field = "block_links" if "links" in cmd else "block_mentions"
    group_config.update_one(
        {"chat_id": message.chat.id},
        {"$set": {field: value}},
        upsert=True
    )
    await message.reply(f"✅ `{field}` set to `{value}`")

@bot.on_message(filters.command("whitelistuser") & filters.group)
async def whitelist_user(client, message):
    if not message.from_user or not message.from_user.is_chat_admin:
        return
    if len(message.command) < 2:
        return await message.reply("Usage: /whitelistuser @username")
    username = message.command[1].lower()
    group_config.update_one(
        {"chat_id": message.chat.id},
        {"$addToSet": {"whitelist_usernames": username}},
        upsert=True
    )
    await message.reply(f"✅ Whitelisted username: {username}")

@bot.on_message(filters.command("whitelistdomain") & filters.group)
async def whitelist_domain(client, message):
    if not message.from_user or not message.from_user.is_chat_admin:
        return
    if len(message.command) < 2:
        return await message.reply("Usage: /whitelistdomain domain.com")
    domain = message.command[1].lower()
    group_config.update_one(
        {"chat_id": message.chat.id},
        {"$addToSet": {"whitelist_domains": domain}},
        upsert=True
    )
    await message.reply(f"✅ Whitelisted domain: {domain}")

@bot.on_message(filters.command("settings") & filters.group)
async def show_settings(client: Client, message: Message):
    cfg = get_group_config(message.chat.id)
    text = (
        f"🛠 **Group Settings**\n"
        f"- Auto-delete delay: `{cfg['delay']}s`\n"
        f"- Block Links: `{cfg['block_links']}`\n"
        f"- Block Mentions: `{cfg['block_mentions']}`\n"
        f"- Whitelisted Users: `{', '.join(cfg['whitelist_usernames']) or 'None'}`\n"
        f"- Whitelisted Domains: `{', '.join(cfg['whitelist_domains']) or 'None'}`"
    )
    await message.reply(text)

@bot.on_message(filters.command("status") & filters.private)
async def status(client: Client, message: Message):
    count = group_config.count_documents({})
    await message.reply(
        f"✅ Bot is running.\n"
        f"🧠 Groups with custom delay: {count}\n"
        f"🕒 Default delay: {DEFAULT_PURGE_SECONDS} sec"
    )

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    await message.reply(
        "**👋 Welcome to AutoDelete Bot!**\n\n"
        "I'm here to help you auto-delete messages from your groups.\n"
        "Add me to your group and promote me to admin.\n\n"
        "Use /help to see available commands and features."
    )

@bot.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    await message.reply(
        "**🛠 AutoDelete Bot Help Menu**\n\n"
        "**Main Features:**\n"
        "• 🧹 Automatically deletes group messages after a delay\n"
        "• 🔗 Deletes messages containing links\n"
        "• 👤 Deletes messages with @usernames\n"
        "• ⚙️ Fully configurable per group\n\n"
        "**Admin Commands (group only):**\n"
        "`/setdelay <seconds>` – Set auto-delete delay\n"
        "`/getdelay` – Show current delay\n"
        "`/blocklinks on/off` – Enable or disable link blocking\n"
        "`/blockmentions on/off` – Enable or disable @username blocking\n"
        "`/whitelistuser @username` – Allow specific usernames\n"
        "`/whitelistdomain domain.com` – Allow specific domains\n"
        "`/settings` – View current settings\n\n"
        "**Private Commands:**\n"
        "`/start` – Welcome message\n"
        "`/status` – Check bot status\n\n"
        "__Add me to your group and make me admin to get started!__"
    )

# === Flask App for Koyeb health check ===
app = Flask(__name__)

@app.route('/')
def home():
    return "OK", 200

def run_web():
    app.run(host="0.0.0.0", port=8000)

# Start fake server in background
threading.Thread(target=run_web).start()

bot.run()
