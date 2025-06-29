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

# ENV Variables
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
USER_SESSION = os.environ.get("USER_SESSION", "")
DELETE_TIME = int(os.environ.get("DELETE_TIME", 60))
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", 0))
MONGO_URI = os.environ.get("MONGO_URI", "")

# Uptime tracking
START_TIME = time.time()

# MongoDB setup
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["autodelete"]
config_col = db["configs"]

# Pyrogram Clients
bot = Client("autodeletebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user = Client("userbot", api_id=API_ID, api_hash=API_HASH, session_string=USER_SESSION)

# Helpers
def get_group_config(chat_id):
    return config_col.find_one({"chat_id": chat_id}) or {}

def set_group_config(chat_id, data):
    config_col.update_one({"chat_id": chat_id}, {"$set": data}, upsert=True)

def get_delay(chat_id):
    return get_group_config(chat_id).get("delay", DELETE_TIME)

def get_whitelist(chat_id):
    return get_group_config(chat_id).get("whitelist", [])

def is_whitelisted(chat_id, user_id):
    return user_id in get_whitelist(chat_id)

def has_link_or_mention(text):
    return bool(re.search(r"(?:t\.me/|https?://|@\w+)", text or ""))

# Auto-delete user messages (bot)
@bot.on_message(filters.group & ~filters.service & ~filters.bot)
async def auto_delete_user_messages(_, message: Message):
    delay = get_delay(message.chat.id)
    if has_link_or_mention(message.text) and not is_whitelisted(message.chat.id, message.from_user.id):
        try:
            await message.delete()
        except: pass
        return
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except: pass

# Auto-delete other bots' messages (userbot)
@user.on_message(filters.group & filters.bot)
async def auto_delete_bot_messages(_, message: Message):
    delay = get_delay(message.chat.id)
    if has_link_or_mention(message.text):
        try:
            await message.delete()
        except: pass
        return
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except: pass

# Delete service messages
@bot.on_message(filters.group & filters.service)
async def delete_service(_, message: Message):
    try: await message.delete()
    except: pass

# Auto-leave if not admin
@bot.on_message(filters.new_chat_members)
async def leave_if_not_admin(_, message: Message):
    try:
        member = await bot.get_chat_member(message.chat.id, "me")
        if member.status not in ("administrator", "creator"):
            await message.reply_text("I am not an admin. Leaving...")
            await bot.leave_chat(message.chat.id)
    except: pass

# Commands (/start /help /ping)
@bot.on_message(filters.private & filters.command("start"))
async def start_cmd(_, m: Message):
    await m.reply_text(
        f"👋 Hello {m.from_user.mention}!\n\n"
        "I am an Auto Delete Bot for Telegram Groups.\n"
        f"➡️ I will delete messages after `{DELETE_TIME}` seconds.\n"
        "➡️ Add me to your group and make me admin.\n\n"
        "Use /help to see more commands."
    )

@bot.on_message(filters.private & filters.command("help"))
async def help_cmd(_, m: Message):
    await m.reply_text(
        "**🛠 Bot Help**\n\n"
        "➡️ Add me to your group.\n"
        "➡️ Promote me as Admin with 'Delete Messages' permission.\n"
        "➡️ I will delete group messages after a delay.\n\n"
        "**Available Commands:**\n"
        "`/start` - Show welcome message\n"
        "`/help` - Show help\n"
        "`/ping` - Check status\n"
        "`/restart` - Restart bot (owner)\n"
        "`/settime <sec>` - Change delete time (owner)\n"
        "`/settings` - Inline config\n"
    )

@bot.on_message(filters.private & filters.command("ping"))
async def ping_cmd(_, m: Message):
    uptime = int(time.time() - START_TIME)
    h, r = divmod(uptime, 3600)
    m_, s = divmod(r, 60)
    pong = await m.reply("Pinging...")
    await pong.edit_text(f"🏓 Pong: `{int((time.time()-START_TIME)*1000)}ms`\n⏱ Uptime: `{h}h {m_}m {s}s`")

# Restart
@bot.on_message(filters.private & filters.command("restart"))
async def restart_cmd(_, m: Message):
    if m.from_user.id != OWNER_ID:
        return await m.reply("Only owner can restart.")
    await m.reply("♻️ Restarting bot...")
    await send_startup_log()
    os.execl(sys.executable, sys.executable, *sys.argv)

# Set delay
@bot.on_message(filters.private & filters.command("settime"))
async def settime_cmd(_, m: Message):
    if m.from_user.id != OWNER_ID:
        return await m.reply("Only owner can use this.")
    if len(m.command) < 2: return await m.reply("Usage: /settime <sec>")
    try:
        val = int(m.command[1])
        if val < 5:
            return await m.reply("Minimum delay is 5 seconds.")
        set_group_config(m.chat.id, {"delay": val})
        await m.reply(f"✅ Delete time set to `{val}` seconds.")
    except: await m.reply("Invalid number.")

# Settings panel
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
async def settings_cmd(_, m: Message):
    buttons = [
        [InlineKeyboardButton("➕ +5s", callback_data="inc"), InlineKeyboardButton("➖ -5s", callback_data="dec")],
        [InlineKeyboardButton("⏱ Current", callback_data="noop")]
    ]
    await m.reply("**⚙️ AutoDelete Settings Panel**", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query()
async def cb_handler(_, cb):
    delay = get_delay(cb.message.chat.id)
    if cb.data == "inc":
        delay += 5
    elif cb.data == "dec":
        delay = max(5, delay - 5)
    set_group_config(cb.message.chat.id, {"delay": delay})
    await cb.answer(f"New Delay: {delay}s", show_alert=True)

# Log & startup
async def send_startup_log():
    if not LOG_GROUP_ID: return
    try:
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
        text = (
            "💥 **Bot Restarted**\n\n"
            f"📅 **Date** : {now.strftime('%Y-%m-%d')}\n"
            f"⏰ **Time** : {now.strftime('%I:%M:%S %p')}\n"
            f"🌐 **Timezone** : Asia/Kolkata"
        )
        await bot.send_message(LOG_GROUP_ID, text)
    except Exception as e:
        print(f"❌ Failed to send restart log: {e}")

# Flask for health check
app = Flask(__name__)
@app.route('/')
def index(): return "✅ Bot is running."
def run(): serve(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
threading.Thread(target=run).start()

# Main
async def main():
    await bot.start()
    await user.start()
    print(f"🤖 Bot: @{(await bot.get_me()).username}")
    await send_startup_log()
    await idle()

print("🔁 Starting bot...")
asyncio.run(main())
