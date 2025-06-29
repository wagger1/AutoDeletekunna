import os
import sys
import asyncio
import time
import pytz
from datetime import datetime
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
from waitress import serve
from pymongo import MongoClient
import re

# === ENV Variables ===
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
USER_SESSION = os.environ.get("USER_SESSION", "")
DELETE_TIME = int(os.environ.get("DELETE_TIME", 60))
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", "-1002641300148"))
MONGO_URI = os.environ.get("MONGO_URI", "")

# === Uptime Tracking ===
START_TIME = time.time()

# === MongoDB Setup ===
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["autodelete"]
config_col = db["configs"]

# === Pyrogram Clients ===
bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user = Client("user", api_id=API_ID, api_hash=API_HASH, session_string=USER_SESSION)

# === Flask for Koyeb ===
app_flask = Flask(__name__)

@app_flask.route('/')
def index():
    return "✅ Bot is healthy and running!"

def run_flask():
    serve(app_flask, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

threading.Thread(target=run_flask).start()

# === Helpers ===
def get_group_config(chat_id):
    config = config_col.find_one({"chat_id": chat_id})
    return config or {}

def get_group_delay(chat_id):
    config = get_group_config(chat_id)
    return config.get("delay", DELETE_TIME)

def set_group_delay(chat_id, delay):
    config_col.update_one({"chat_id": chat_id}, {"$set": {"delay": delay}}, upsert=True)

def get_whitelist(chat_id):
    config = get_group_config(chat_id)
    return config.get("whitelist", [])

def is_whitelisted(chat_id, user_id):
    return user_id in get_whitelist(chat_id)

def is_blocking_links(chat_id):
    return get_group_config(chat_id).get("block_links", False)

def is_blocking_mentions(chat_id):
    return get_group_config(chat_id).get("block_mentions", False)

# === Bot Client Handlers ===
@bot.on_message(filters.group & ~filters.service)
async def handle_user_messages(_, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else None

    if not user_id or is_whitelisted(chat_id, user_id):
        return

    if is_blocking_links(chat_id):
        if re.search(r"https?://|t\.me/|telegram\.me/", message.text or message.caption or ""):
            await message.delete()
            return

    if is_blocking_mentions(chat_id):
        if re.search(r"@\w+", message.text or message.caption or ""):
            await message.delete()
            return

    try:
        await asyncio.sleep(get_group_delay(chat_id))
        await message.delete()
    except Exception as e:
        print(f"Error deleting user message: {e}")

@user.on_message(filters.group & ~filters.service)
async def handle_bot_messages(_, message: Message):
    if message.from_user and message.from_user.is_bot:
        try:
            await asyncio.sleep(get_group_delay(message.chat.id))
            await message.delete()
        except Exception as e:
            print(f"Error deleting bot message: {e}")

@bot.on_message(filters.group & filters.service)
async def delete_service(_, message: Message):
    try:
        await message.delete()
    except:
        pass

@bot.on_message(filters.private & filters.command("start"))
async def start_cmd(_, message: Message):
    await message.reply_text(
        f"👋 Hello {message.from_user.mention}!
\nI am an Auto Delete Bot for Telegram Groups.\n"
        f"➡️ I will delete messages after `{DELETE_TIME}` seconds.\n"
        "➡️ Add me to your group and make me admin.\n\nUse /help to see more commands."
    )

@bot.on_message(filters.private & filters.command("help"))
async def help_cmd(_, message: Message):
    await message.reply_text(
        "**🛠 Bot Help**\n\n"
        "➡️ Add me to your group.\n"
        "➡️ Promote me as Admin with 'Delete Messages' permission.\n"
        f"➡️ I will delete group messages after `{DELETE_TIME}` seconds.\n\n"
        "**Available Commands:**\n"
        "`/start` - Show welcome message\n"
        "`/help` - Show this help message\n"
        "`/ping` - Check bot status and uptime\n"
        "`/restart` - Restart bot (Owner only)\n"
        "`/settime <seconds>` - Change delete time (Owner only)\n"
        "`/settings` - Inline panel for delay settings"
    )

@bot.on_message(filters.private & filters.command("ping"))
async def ping_cmd(_, message: Message):
    uptime = time.time() - START_TIME
    hours, rem = divmod(int(uptime), 3600)
    minutes, seconds = divmod(rem, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"

    start = time.time()
    m = await message.reply_text("Pinging...")
    ping_time = (time.time() - start) * 1000

    await m.edit_text(f"🏓 Pong: `{int(ping_time)}ms`\n⏱ Uptime: `{uptime_str}`")

@bot.on_message(filters.private & filters.command("restart"))
async def restart_cmd(_, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("⚠️ Only the bot owner can use this command.")

    await message.reply_text("♻️ Restarting Bot...")
    await send_startup_log()
    os.execl(sys.executable, sys.executable, *sys.argv)

@bot.on_message(filters.private & filters.command("settime"))
async def settime_cmd(_, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("⚠️ Only the bot owner can use this command.")
    if len(message.command) < 2:
        return await message.reply_text("❗ Usage: `/settime <seconds>`")
    try:
        sec = int(message.command[1])
        if sec < 5:
            return await message.reply_text("⚠️ Minimum delete time is 5 seconds.")
        set_group_delay(message.chat.id, sec)
        await message.reply_text(f"✅ Delete time updated to `{sec}` seconds.")
    except:
        await message.reply_text("❌ Invalid input. Use `/settime <seconds>`")

@bot.on_message(filters.command("settings") & filters.group)
async def settings_panel(_, message: Message):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ +5s", callback_data="inc"),
            InlineKeyboardButton("➖ -5s", callback_data="dec"),
        ],
        [InlineKeyboardButton("⏱ Current", callback_data="noop")]
    ])
    await message.reply("**⚙️ AutoDelete Settings Panel**", reply_markup=keyboard)

@bot.on_callback_query()
async def callback_handler(_, cb):
    chat_id = cb.message.chat.id
    delay = get_group_delay(chat_id)
    if cb.data == "inc":
        delay += 5
        set_group_delay(chat_id, delay)
        await cb.answer(f"New Delay: {delay}s", show_alert=True)
    elif cb.data == "dec":
        delay = max(5, delay - 5)
        set_group_delay(chat_id, delay)
        await cb.answer(f"New Delay: {delay}s", show_alert=True)
    elif cb.data == "noop":
        await cb.answer(f"Current Delay: {delay}s", show_alert=True)

async def send_startup_log():
    try:
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
        text = (
            "💥 **Bot Restarted**\n\n"
            f"📅 **Date** : {now.strftime('%Y-%m-%d')}\n"
            f"⏰ **Time** : {now.strftime('%I:%M:%S %p')}\n"
            f"🌐 **Timezone** : Asia/Kolkata\n"
            f"🛠️ **Build Status**: v2.7.1 [Stable]"
        )
        await bot.send_message(LOG_GROUP_ID, text)
    except Exception as e:
        print(f"❌ Failed to send restart log: {e}")

# === Startup ===
print("🔁 Starting bot...")

async def main():
    await bot.start()
    await user.start()
    print(f"🤖 Bot: @{(await bot.get_me()).username}")
    await send_startup_log()
    await idle()

asyncio.run(main())
