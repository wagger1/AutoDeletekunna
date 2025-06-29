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

# === ENV Variables ===
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
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

# === Pyrogram Client ===
bot = Client("autodeletebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# === Helper Functions ===
def get_group_delay(chat_id):
    doc = config_col.find_one({"chat_id": chat_id})
    return doc["delay"] if doc else DELETE_TIME

def set_group_delay(chat_id, delay):
    config_col.update_one({"chat_id": chat_id}, {"$set": {"delay": delay}}, upsert=True)

# === Message Handlers ===
@bot.on_message(filters.group & ~filters.service)
async def auto_delete(_, message: Message):
    delay = get_group_delay(message.chat.id)
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception as e:
        print(f"Error deleting message: {e}")

@bot.on_message(filters.group & filters.service)
async def delete_service(_, message: Message):
    try:
        await message.delete()
    except:
        pass

@bot.on_message(filters.new_chat_members)
async def leave_if_not_admin(_, message: Message):
    try:
        member = await bot.get_chat_member(message.chat.id, "me")
        if member.status not in ("administrator", "creator"):
            await message.reply_text("I am not an admin. Leaving...")
            await bot.leave_chat(message.chat.id)
    except:
        pass

@bot.on_message(filters.private & filters.command("start"))
async def start_cmd(_, message: Message):
    await message.reply_text(
        f"👋 Hello {message.from_user.mention}!\n\n"
        f"I am an Auto Delete Bot for Telegram Groups.\n"
        f"➡️ I will delete messages after `{DELETE_TIME}` seconds.\n"
        f"➡️ Add me to your group and make me admin.\n\n"
        f"Use /help to see more commands."
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
        "`/cleanbot` - Delete all bot messages in a group\n"
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
    msg = await message.reply_text("♻️ Restarting Bot...")
    await asyncio.sleep(1)
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

@bot.on_message(filters.command("cleanbot") & filters.group)
async def clean_bot_messages(_, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("⚠️ Only the bot owner can use this command.")
    deleted = 0
    async for msg in bot.get_chat_history(message.chat.id, limit=300):
        if msg.from_user and msg.from_user.is_bot:
            try:
                await msg.delete()
                deleted += 1
            except:
                continue
    await message.reply_text(f"🧹 Deleted `{deleted}` bot messages.")

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

# === Flask for Koyeb ===
app_flask = Flask(__name__)

@app_flask.route('/')
def index():
    return "✅ Bot is healthy and running!"

def run_flask():
    serve(app_flask, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

threading.Thread(target=run_flask).start()

# === Start Bot ===
print("🔁 Starting bot...")
bot.run()
