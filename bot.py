import os
import sys
import asyncio
import time
import re
import pytz
from datetime import datetime
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
from waitress import serve
from pymongo import MongoClient

# ENV Variables
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
STRING_SESSION = os.environ.get("STRING_SESSION", "")
DELETE_TIME = int(os.environ.get("DELETE_TIME", 60))
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", "-1002641300148"))
MONGO_URI = os.environ.get("MONGO_URI", "")
PORT = int(os.environ.get("PORT", 8000))

START_TIME = time.time()

# MongoDB Setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["autodelete"]
config_col = db["configs"]

# Pyrogram Clients
bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user = Client("user", api_id=API_ID, api_hash=API_HASH, session_string=STRING_SESSION)

# Get delay from DB
def get_group_delay(chat_id):
    doc = config_col.find_one({"chat_id": chat_id})
    return doc["delay"] if doc else DELETE_TIME

def set_group_delay(chat_id, delay):
    config_col.update_one({"chat_id": chat_id}, {"$set": {"delay": delay}}, upsert=True)

# Link and Mention Regex
link_pattern = re.compile(r"(https?://\S+|t\.me/\S+|@\w+)", re.IGNORECASE)

# Bot deletes user messages
@bot.on_message(filters.group & ~filters.service)
async def handle_user_messages(_, message: Message):
    delay = get_group_delay(message.chat.id)
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception as e:
        print(f"Bot failed to delete user message: {e}")

# User deletes messages from other bots or with links/mentions
@user.on_message(filters.group & ~filters.service)
async def handle_bot_messages(_, message: Message):
    try:
        if message.from_user and message.from_user.is_bot:
            await message.delete()
        elif link_pattern.search(message.text or ""):
            await message.delete()
    except Exception as e:
        print(f"Userbot failed to delete message: {e}")

# Delete service messages (join/leave)
@bot.on_message(filters.service)
@user.on_message(filters.service)
async def delete_services(_, message: Message):
    try:
        await message.delete()
    except:
        pass

# Auto-leave if not admin
@bot.on_message(filters.new_chat_members)
async def leave_if_not_admin(_, message: Message):
    try:
        member = await bot.get_chat_member(message.chat.id, "me")
        if member.status not in ("administrator", "creator"):
            await bot.leave_chat(message.chat.id)
    except:
        pass

# Commands
@bot.on_message(filters.private & filters.command("start"))
async def start_cmd(_, message: Message):
    await message.reply_text(
        f"👋 Hello {message.from_user.mention}!\n\n"
        "I auto-delete messages from groups including links, mentions, or bots.\n"
        f"Delay: `{DELETE_TIME}` seconds by default.\n"
        "Use /help to learn more."
    )

@bot.on_message(filters.private & filters.command("help"))
async def help_cmd(_, message: Message):
    await message.reply_text(
        "**🛠 Bot Help**\n\n"
        "`/ping` - Check bot status\n"
        "`/restart` - Restart bot (Owner only)\n"
        "`/settime <seconds>` - Set delay (Owner only)\n"
        "`/cleanbot` - Delete bot messages in group\n"
        "`/settings` - Show delay settings panel\n"
    )

@bot.on_message(filters.private & filters.command("ping"))
async def ping_cmd(_, message: Message):
    uptime = time.time() - START_TIME
    h, rem = divmod(int(uptime), 3600)
    m, s = divmod(rem, 60)
    msg = await message.reply("Pinging...")
    await msg.edit(f"🏓 Pong: `{int((time.time() - msg.date.timestamp())*1000)}ms`\n⏱ Uptime: {h}h {m}m {s}s")

@bot.on_message(filters.private & filters.command("restart"))
async def restart_cmd(_, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply("❌ Only owner can restart.")
    await message.reply("♻️ Restarting...")
    await send_startup_log()
    os.execv(sys.executable, [sys.executable] + sys.argv)

@bot.on_message(filters.private & filters.command("settime"))
async def settime_cmd(_, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply("❌ Not allowed.")
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply("⚠️ Usage: /settime <seconds>")
    sec = max(5, int(message.command[1]))
    set_group_delay(message.chat.id, sec)
    await message.reply(f"✅ Delay set to {sec} seconds.")

@bot.on_message(filters.command("cleanbot") & filters.group)
async def clean_bot_messages(_, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    count = 0
    async for msg in bot.get_chat_history(message.chat.id, limit=300):
        if msg.from_user and msg.from_user.is_bot:
            try:
                await msg.delete()
                count += 1
            except:
                continue
    await message.reply(f"🧹 Deleted {count} bot messages.")

@bot.on_message(filters.command("settings") & filters.group)
async def settings_panel(_, message: Message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ +5s", callback_data="inc"),
         InlineKeyboardButton("➖ -5s", callback_data="dec")],
        [InlineKeyboardButton("⏱ Show", callback_data="noop")]
    ])
    await message.reply("⚙️ AutoDelete Settings Panel", reply_markup=keyboard)

@bot.on_callback_query()
async def callback_handler(_, cb):
    chat_id = cb.message.chat.id
    delay = get_group_delay(chat_id)
    if cb.data == "inc":
        delay += 5
        set_group_delay(chat_id, delay)
        await cb.answer(f"⏱ New Delay: {delay}s", show_alert=True)
    elif cb.data == "dec":
        delay = max(5, delay - 5)
        set_group_delay(chat_id, delay)
        await cb.answer(f"⏱ New Delay: {delay}s", show_alert=True)
    elif cb.data == "noop":
        await cb.answer(f"⏱ Current Delay: {delay}s", show_alert=True)

# Log group check
async def send_startup_log():
    try:
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
        await bot.send_message(LOG_GROUP_ID,
            f"💥 **Bot Restarted**\n\n📅 {now.strftime('%Y-%m-%d')}\n⏰ {now.strftime('%I:%M:%S %p')}\n🛠️ v2.7.1")
    except Exception as e:
        print(f"❌ Failed to send log: {e}")

# Flask App
app_flask = Flask(__name__)
@app_flask.route('/')
def index(): return "✅ Bot running"

def run_flask(): serve(app_flask, host="0.0.0.0", port=PORT)
threading.Thread(target=run_flask).start()

# Main run loop
async def main():
    await bot.start()
    await user.start()
    print(f"🤖 Bot: @{(await bot.get_me()).username}")
    await send_startup_log()
    await idle()

print("🔁 Starting bot...")
asyncio.run(main())
