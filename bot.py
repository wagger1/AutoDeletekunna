# bot.py

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
import platform
import psutil
import socket
from pyrogram.types import ChatMemberUpdated

@bot.on_chat_member_updated()
async def log_new_group(_, update: ChatMemberUpdated):
    if update.new_chat_member and update.new_chat_member.user.is_self:
        if update.old_chat_member.status in ("left", "kicked") and update.new_chat_member.status in ("member", "administrator"):
            try:
                user = update.from_user
                chat = update.chat
                ist = pytz.timezone("Asia/Kolkata")
                now = datetime.now(ist)
                date_str = now.strftime("%Y-%m-%d")
                time_str = now.strftime("%I:%M:%S %p")

                invite_link = f"https://t.me/{chat.username}" if chat.username else f"Private Group ({chat.id})"

                text = (
                    "📥 **Bot Added to New Group**\n\n"
                    f"👤 Added By: `{user.first_name}` (`{user.id}`)\n"
                    f"👥 Group   : {chat.title}\n"
                    f"🔗 Link    : {invite_link}\n\n"
                    f"📅 Date    : {date_str}\n"
                    f"⏰ Time    : {time_str}"
                )
                await bot.send_message(LOG_GROUP_ID, text)
            except Exception as e:
                print(f"❌ Error sending log: {e}")
                
# === ENV Variables ===
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DELETE_TIME = int(os.environ.get("DELETE_TIME", 60))
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", "-100"))
MONGO_URI = os.environ.get("MONGO_URI", "")
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", 100))

# === Uptime Tracking ===
START_TIME = time.time()

# === MongoDB Setup ===
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["autodelete"]
config_col = db["configs"]
groups_col = db["groups"]
whitelist_col = db["whitelist"]

# === Pyrogram Client ===
bot = Client("autodeletebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# === Helper Functions ===
def get_group_delay(chat_id):
    doc = config_col.find_one({"chat_id": chat_id})
    return doc["delay"] if doc else DELETE_TIME

def set_group_delay(chat_id, delay):
    config_col.update_one({"chat_id": chat_id}, {"$set": {"delay": delay}}, upsert=True)

def save_group(chat):
    groups_col.update_one(
        {"chat_id": chat.id},
        {"$set": {
            "chat_id": chat.id,
            "chat_title": chat.title,
            "type": chat.type,
            "updated_at": datetime.utcnow()
        }},
        upsert=True
    )

def is_whitelisted(user_id, chat_id):
    return whitelist_col.find_one({"user_id": user_id, "chat_id": chat_id}) is not None

# === Message Handlers ===
@bot.on_message(filters.group & ~filters.service)
async def auto_delete(_, message: Message):
    save_group(message.chat)

    if is_whitelisted(message.from_user.id, message.chat.id):
        return

    if message.media:
        try:
            size = getattr(message, message.media.value).file_size or 0
            if size > MAX_FILE_SIZE_MB * 1024 * 1024:
                await message.delete()
                return
        except Exception as e:
            print(f"[SizeCheckError] {e}")

    delay = get_group_delay(message.chat.id)
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception as e:
        if "message to delete not found" not in str(e).lower():
            print(f"[DeleteError] {e}")

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

@bot.on_message(filters.command("whitelist") & filters.user(OWNER_ID))
async def add_whitelist(_, message: Message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to the user's message to whitelist them.")
    user_id = message.reply_to_message.from_user.id
    chat_id = message.chat.id
    whitelist_col.update_one({"user_id": user_id, "chat_id": chat_id}, {"$set": {
        "user_id": user_id, "chat_id": chat_id
    }}, upsert=True)
    await message.reply_text("✅ User whitelisted.")

@bot.on_message(filters.command("unwhitelist") & filters.user(OWNER_ID))
async def remove_whitelist(_, message: Message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to the user's message to remove from whitelist.")
    user_id = message.reply_to_message.from_user.id
    chat_id = message.chat.id
    whitelist_col.delete_one({"user_id": user_id, "chat_id": chat_id})
    await message.reply_text("🚫 User removed from whitelist.")

@bot.on_message(filters.command("whitelisted") & filters.user(OWNER_ID))
async def list_whitelisted(_, message: Message):
    chat_id = message.chat.id
    users = whitelist_col.find({"chat_id": chat_id})
    text = "**✅ Whitelisted Users:**\n\n"
    count = 0
    for user in users:
        count += 1
        text += f"{count}. ID: `{user['user_id']}`\n"
    if count == 0:
        text += "No users whitelisted."
    await message.reply_text(text)

# ... (Keep all your previous command handlers like /start, /help, /settime, /status, /groups, etc. unchanged)

# === Flask for Koyeb ===
app_flask = Flask(__name__)

@app_flask.route('/')
def index():
    return "✅ Bot is healthy and running!"

def run_flask():
    serve(app_flask, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

threading.Thread(target=run_flask).start()

# === Startup Log ===
async def send_startup_log():
    try:
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
        text = (
            "💥 Bot Restarted\n\n"
            f"📅 Date : {now.strftime('%Y-%m-%d')}\n"
            f"⏰ Time : {now.strftime('%I:%M:%S %p')}\n"
            f"🌐 Timezone : Asia/Kolkata\n"
            f"🛠️ Build Status : v2.7.1 [Stable]"
        )
        await bot.send_message(OWNER_ID, text)
        print("✅ Restart log sent to owner.")
    except Exception as e:
        print(f"❌ Failed to send restart log: {e}")

# === Start Bot ===
bot.run()
