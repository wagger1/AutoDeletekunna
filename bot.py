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

# ENV Variables
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DELETE_TIME = int(os.environ.get("DELETE_TIME", 60))
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", 0))

# Uptime tracking
START_TIME = time.time()

# Pyrogram Client
app = Client("autodeletebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Auto-delete normal messages
@app.on_message(filters.group & ~filters.service)
async def auto_delete(_, message: Message):
    try:
        await asyncio.sleep(DELETE_TIME)
        await message.delete()
    except Exception as e:
        print(f"Error deleting message: {e}")
        if LOG_GROUP_ID:
            await app.send_message(LOG_GROUP_ID, f"⚠️ Error deleting message:\n`{e}`")

# Delete service messages (join/leave)
@app.on_message(filters.group & filters.service)
async def delete_service(_, message: Message):
    try:
        await message.delete()
    except:
        pass

# Auto-leave if not admin
@app.on_message(filters.new_chat_members)
async def leave_if_not_admin(_, message: Message):
    try:
        member = await app.get_chat_member(message.chat.id, "me")
        if not member.status in ("administrator", "creator"):
            await message.reply_text("I am not an admin. Leaving...")
            await app.leave_chat(message.chat.id)
    except:
        pass

# /start
@app.on_message(filters.private & filters.command("start"))
async def start_cmd(_, message: Message):
    await message.reply_text(
        f"👋 Hello {message.from_user.mention}!\n\n"
        "I am an Auto Delete Bot for Telegram Groups.\n"
        f"➡️ I will delete messages after `{DELETE_TIME}` seconds.\n"
        "➡️ Add me to your group and make me admin.\n\n"
        "Use /help to see more commands."
    )

# /help
@app.on_message(filters.private & filters.command("help"))
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

# /ping
@app.on_message(filters.private & filters.command("ping"))
async def ping_cmd(_, message: Message):
    uptime = time.time() - START_TIME
    hours, rem = divmod(int(uptime), 3600)
    minutes, seconds = divmod(rem, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"

    start = time.time()
    m = await message.reply_text("Pinging...")
    end = time.time()
    ping_time = (end - start) * 1000

    await m.edit_text(f"🏓 Pong: `{int(ping_time)}ms`\n⏱ Uptime: `{uptime_str}`")

# /restart
@app.on_message(filters.private & filters.command("restart"))
async def restart_cmd(_, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("⚠️ Only the bot owner can use this command.")

    msg = await message.reply_text("♻️ Restarting Bot...")

    await asyncio.sleep(1)

    # Send restart log
    if LOG_GROUP_ID:
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
        log_text = (
            "💥 **Bᴏᴛ Rᴇsᴛᴀʀᴛᴇᴅ**\n\n"
            f"📅 **Dᴀᴛᴇ** : {now.strftime('%Y-%m-%d')}\n"
            f"⏰ **Tɪᴍᴇ** : {now.strftime('%I:%M:%S %p')}\n"
            f"🌐 **Tɪᴍᴇᴢᴏɴᴇ** : Asia/Kolkata\n"
            f"🛠️ **Bᴜɪʟᴅ Sᴛᴀᴛᴜs**: v2.7.1 [Stable]"
        )
        await app.send_message(LOG_GROUP_ID, log_text)

    os.execl(sys.executable, sys.executable, *sys.argv)

# /settime
@app.on_message(filters.private & filters.command("settime"))
async def settime_cmd(_, message: Message):
    global DELETE_TIME
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("⚠️ Only the bot owner can use this command.")
    if len(message.command) < 2:
        return await message.reply_text("❗ Usage: `/settime <seconds>`")
    try:
        sec = int(message.command[1])
        if sec < 5:
            return await message.reply_text("⚠️ Minimum delete time is 5 seconds.")
        DELETE_TIME = sec
        await message.reply_text(f"✅ Delete time updated to `{DELETE_TIME}` seconds.")
    except:
        await message.reply_text("❌ Invalid input. Use `/settime <seconds>`")

# /cleanbot
@app.on_message(filters.command("cleanbot") & filters.group)
async def clean_bot_messages(_, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("⚠️ Only the bot owner can use this command.")

    deleted = 0
    async for msg in app.get_chat_history(message.chat.id, limit=300):
        if msg.from_user and msg.from_user.is_bot:
            try:
                await msg.delete()
                deleted += 1
            except:
                continue
    await message.reply_text(f"🧹 Deleted `{deleted}` bot messages.")

# /settings panel
@app.on_message(filters.command("settings") & filters.group)
async def settings_panel(_, message: Message):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ +5s", callback_data="inc"),
            InlineKeyboardButton("➖ -5s", callback_data="dec"),
        ],
        [
            InlineKeyboardButton("⏱ Current", callback_data="noop")
        ]
    ])
    await message.reply("**⚙️ AutoDelete Settings Panel**", reply_markup=keyboard)

@app.on_callback_query()
async def callback_handler(_, cb):
    global DELETE_TIME
    if cb.data == "inc":
        DELETE_TIME += 5
        await cb.answer(f"New Delay: {DELETE_TIME}s", show_alert=True)
    elif cb.data == "dec":
        DELETE_TIME = max(5, DELETE_TIME - 5)
        await cb.answer(f"New Delay: {DELETE_TIME}s", show_alert=True)
    elif cb.data == "noop":
        await cb.answer(f"Current Delay: {DELETE_TIME}s", show_alert=True)

# Flask for Koyeb
app_flask = Flask(__name__)

@app_flask.route('/')
def index():
    return "✅ Bot is healthy and running!"

def run_flask():
    serve(app_flask, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

# Run Flask in background using Waitress (no dev server warning)
threading.Thread(target=run_flask).start()

# Send startup log when redeployed
async def send_startup_log():
    try:
        await app.get_chat(LOG_GROUP_ID)  # Bootstrap the peer
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)
        text = (
            "💥 **Bot Restarted**\n\n"
            f"📅 **Date** : {now.strftime('%Y-%m-%d')}\n"
            f"⏰ **Time** : {now.strftime('%H:%M:%S %p')}\n"
            f"🌐 **Timezone** : Asia/Kolkata\n"
            f"🛠️ **Build Status**: v2.7.1 [Stable]"
        )
        await app.send_message(LOG_GROUP_ID, text)
        print("✅ Restart log sent.")
    except Exception as e:
        print(f"❌ Failed to send restart log: {e}")

# Run bot with startup log
print("Bot Started...")

async def main():
    await app.start()
    await send_startup_log()
    await idle()

asyncio.run(main())
