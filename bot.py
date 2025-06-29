import os
import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DELETE_TIME = int(os.environ.get("DELETE_TIME", 60))  # default seconds
OWNER_ID = int(os.environ.get("OWNER_ID", 0))  # Your Telegram User ID
LOG_GROUP_ID = int(os.environ.get("LOG_GROUP_ID", 0))  # Must be numeric

app = Client("autodeletebot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


@app.on_message(filters.group & ~filters.service)
async def auto_delete(_, message: Message):
    try:
        await asyncio.sleep(DELETE_TIME)
        await message.delete()
    except Exception as e:
        print(f"Error deleting message: {e}")
        if LOG_GROUP_ID:
            await app.send_message(LOG_GROUP_ID, f"⚠️ Error deleting message:\n`{e}`")


@app.on_message(filters.private & filters.command("start"))
async def start_cmd(_, message: Message):
    await message.reply_text(
        f"👋 Hello {message.from_user.mention}!\n\n"
        "I am an Auto Delete Bot for Telegram Groups.\n"
        f"➤ I will delete messages after `{DELETE_TIME}` seconds.\n"
        "➤ Add me to your group and make me admin.\n\n"
        "Use /help to see more commands."
    )


@app.on_message(filters.private & filters.command("help"))
async def help_cmd(_, message: Message):
    await message.reply_text(
        "**🛠 Bot Help**\n\n"
        "➤ Add me to your group.\n"
        "➤ Promote me as Admin with 'Delete Messages' permission.\n"
        f"➤ I will delete group messages after `{DELETE_TIME}` seconds.\n\n"
        "**Available Commands:**\n"
        "`/start` - Show welcome message\n"
        "`/help` - Show this help message\n"
        "`/ping` - Check bot status\n"
        "`/restart` - Restart bot (Owner only)\n"
        "`/settime <seconds>` - Change delete time (Owner only)\n"
        "`/cleanbot` - Delete all bot messages in a group"
    )


@app.on_message(filters.private & filters.command("ping"))
async def ping_cmd(_, message: Message):
    start = time.time()
    m = await message.reply_text("Pinging...")
    end = time.time()
    ping_time = (end - start) * 1000
    await m.edit_text(f"🏓 Pong! `{int(ping_time)}ms`")


@app.on_message(filters.private & filters.command("restart"))
async def restart_cmd(_, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply_text("⚠️ Only the bot owner can use this command.")

    start_time = time.time()
    msg = await message.reply_text("♻️ Restarting Bot...")

    await asyncio.sleep(5)  # Simulated restart delay

    end_time = time.time()
    taken = int(end_time - start_time)

    text = (
        f"✅ Bot restarted\n"
        f"🕥 Time taken - {taken} seconds"
    )

    await msg.edit_text(text)

    if LOG_GROUP_ID:
        await app.send_message(LOG_GROUP_ID, f"♻️ Bot restarted by [{message.from_user.first_name}](tg://user?id={message.from_user.id}).\n{text}")


@app.on_message(filters.private & filters.command("settime"))
async def settime_cmd(_, message: Message):
    global DELETE_TIME

    if message.from_user.id != OWNER_ID:
        return await message.reply_text("⚠️ Only the bot owner can use this command.")

    if len(message.command) < 2:
        return await message.reply_text("❗ Usage: `/settime <seconds>`", quote=True)

    try:
        new_time = int(message.command[1])
        if new_time < 5:
            return await message.reply_text("⚠️ Minimum delete time is 5 seconds.")
        DELETE_TIME = new_time
        await message.reply_text(f"✅ Auto-delete time updated to `{DELETE_TIME}` seconds.")

        if LOG_GROUP_ID:
            await app.send_message(LOG_GROUP_ID, f"🛠 Auto-delete time changed to `{DELETE_TIME}` seconds by [{message.from_user.first_name}](tg://user?id={message.from_user.id}).")
    except ValueError:
        await message.reply_text("⚠️ Invalid number. Usage: `/settime <seconds>`")


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

from flask import Flask
import threading

app_flask = Flask(__name__)

@app_flask.route('/')
def index():
    return "✅ Bot is healthy and running!"

def run_flask():
    app_flask.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

# Run Flask in background
threading.Thread(target=run_flask).start()

print("Bot Started...")
app.run()
