import os
import re
import asyncio
import logging
import threading
from flask import Flask, request, jsonify
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URI = os.getenv("MONGO_URI", "")
DEFAULT_PURGE_SECONDS = int(os.getenv("PURGE_SECONDS", "600"))
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID", "0"))
ADMIN_KEY = os.getenv("ADMIN_KEY", "changeme")

if not all((API_ID, API_HASH, BOT_TOKEN, MONGO_URI)):
    raise RuntimeError("Missing required environment variables.")

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")

mongo = MongoClient(MONGO_URI)
db = mongo["autopurgebot"]
group_config = db["delays"]

bot = Client("auto_purge_worker", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
warned_users = {}

def get_group_config(chat_id):
    config = group_config.find_one({"chat_id": chat_id}) or {}
    return {
        "delay": config.get("delay", DEFAULT_PURGE_SECONDS),
        "block_links": config.get("block_links", True),
        "block_mentions": config.get("block_mentions", True),
        "whitelist_usernames": config.get("whitelist_usernames", []),
        "whitelist_domains": config.get("whitelist_domains", [])
    }

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

    has_link = bool(re.search(r"(https?://|t\.me/|telegram\.me/)", text))
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

@bot.on_message(filters.command("settings") & filters.group)
async def show_settings(client: Client, message: Message):
    cfg = get_group_config(message.chat.id)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Delay +5", callback_data="inc_delay"),
         InlineKeyboardButton("➖ Delay -5", callback_data="dec_delay")],
        [InlineKeyboardButton(f"🔗 Links: {'✅' if cfg['block_links'] else '❌'}", callback_data="toggle_links")],
        [InlineKeyboardButton(f"👤 Mentions: {'✅' if cfg['block_mentions'] else '❌'}", callback_data="toggle_mentions")]
    ])
    await message.reply("**⚙️ Group Settings:**", reply_markup=keyboard)

@bot.on_callback_query()
async def handle_callback(client, cb):
    if cb.message.chat.type == "private":
        return await cb.answer("Use this in a group where I'm admin.", show_alert=True)

    cid = cb.message.chat.id
    data = cb.data
    cfg = get_group_config(cid)

    if data == "toggle_links":
        group_config.update_one({"chat_id": cid}, {"$set": {"block_links": not cfg['block_links']}}, upsert=True)
    elif data == "toggle_mentions":
        group_config.update_one({"chat_id": cid}, {"$set": {"block_mentions": not cfg['block_mentions']}}, upsert=True)
    elif data == "inc_delay":
        group_config.update_one({"chat_id": cid}, {"$inc": {"delay": 5}}, upsert=True)
    elif data == "dec_delay":
        new_delay = max(5, cfg['delay'] - 5)
        group_config.update_one({"chat_id": cid}, {"$set": {"delay": new_delay}}, upsert=True)

    new_cfg = get_group_config(cid)
    new_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Delay +5", callback_data="inc_delay"),
         InlineKeyboardButton("➖ Delay -5", callback_data="dec_delay")],
        [InlineKeyboardButton(f"🔗 Links: {'✅' if new_cfg['block_links'] else '❌'}", callback_data="toggle_links")],
        [InlineKeyboardButton(f"👤 Mentions: {'✅' if new_cfg['block_mentions'] else '❌'}", callback_data="toggle_mentions")]
    ])
    await cb.edit_message_reply_markup(reply_markup=new_markup)
    await cb.answer("Updated.")

@bot.on_message(filters.command("status") & filters.private)
async def status_command(client, message):
    count = group_config.count_documents({})
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")]
    ])
    await message.reply(f"✅ Bot is online.\n🧠 Group configs: {count}\n⏱️ Default delay: {DEFAULT_PURGE_SECONDS}s", reply_markup=btn)

@bot.on_callback_query(filters.regex("refresh_status"))
async def refresh_status(client, cb):
    count = group_config.count_documents({})
    await cb.message.edit_text(f"✅ Bot is online.\n🧠 Group configs: {count}\n⏱️ Default delay: {DEFAULT_PURGE_SECONDS}s", reply_markup=cb.message.reply_markup)
    await cb.answer("Refreshed")

# --- Start & Help ---
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
    text = (
        "**🛠 AutoDelete Bot Help Menu**\n\n"
        "**Main Features:**\n"
        "• 🧹 Auto-deletes messages after a delay\n"
        "• 🔗 Removes messages with links\n"
        "• 👤 Removes messages with @mentions\n"
        "• ⚙️ Fully customizable per group\n\n"
        "**Admin Commands (in groups):**\n"
        "`/setdelay <seconds>` – Set delete delay\n"
        "`/getdelay` – Show current delay\n"
        "`/blocklinks on/off` – Toggle link blocking\n"
        "`/blockmentions on/off` – Toggle mention blocking\n"
        "`/whitelistuser @username` – Allow usernames\n"
        "`/whitelistdomain domain.com` – Allow domains\n"
        "`/settings` – Inline button panel\n\n"
        "**Private Commands:**\n"
        "`/start` – Show welcome\n"
        "`/status` – Bot and config count\n\n"
        "__Add me to your group and promote me to admin!__"
    )
@bot.on_message(filters.command("setdelay") & filters.group)
async def set_delay(client, message: Message):
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply("❗ Usage: `/setdelay <seconds>`", quote=True)
    seconds = int(message.command[1])
    group_config.update_one({"chat_id": message.chat.id}, {"$set": {"delay": seconds}}, upsert=True)
    await message.reply(f"⏱️ Message auto-delete delay set to **{seconds} seconds**.", quote=True)

@bot.on_message(filters.command("getdelay") & filters.group)
async def get_delay(client, message: Message):
    cfg = get_group_config(message.chat.id)
    await message.reply(f"⏱️ Current delete delay: **{cfg['delay']} seconds**", quote=True)

@bot.on_message(filters.command("blocklinks") & filters.group)
async def toggle_block_links(client, message: Message):
    if len(message.command) < 2 or message.command[1].lower() not in ("on", "off"):
        return await message.reply("❗ Usage: `/blocklinks on|off`", quote=True)
    toggle = message.command[1].lower() == "on"
    group_config.update_one({"chat_id": message.chat.id}, {"$set": {"block_links": toggle}}, upsert=True)
    await message.reply(f"🔗 Link blocking is now **{'enabled' if toggle else 'disabled'}**.", quote=True)

@bot.on_message(filters.command("blockmentions") & filters.group)
async def toggle_block_mentions(client, message: Message):
    if len(message.command) < 2 or message.command[1].lower() not in ("on", "off"):
        return await message.reply("❗ Usage: `/blockmentions on|off`", quote=True)
    toggle = message.command[1].lower() == "on"
    group_config.update_one({"chat_id": message.chat.id}, {"$set": {"block_mentions": toggle}}, upsert=True)
    await message.reply(f"👤 Mention blocking is now **{'enabled' if toggle else 'disabled'}**.", quote=True)

@bot.on_message(filters.command("whitelistuser") & filters.group)
async def whitelist_user(client, message: Message):
    if len(message.command) < 2 or not message.command[1].startswith("@"):
        return await message.reply("❗ Usage: `/whitelistuser @username`", quote=True)
    username = message.command[1].lower()
    group_config.update_one({"chat_id": message.chat.id}, {"$addToSet": {"whitelist_usernames": username}}, upsert=True)
    await message.reply(f"✅ User **{username}** whitelisted from mention blocking.", quote=True)

@bot.on_message(filters.command("whitelistdomain") & filters.group)
async def whitelist_domain(client, message: Message):
    if len(message.command) < 2:
        return await message.reply("❗ Usage: `/whitelistdomain example.com`", quote=True)
    domain = message.command[1].lower()
    group_config.update_one({"chat_id": message.chat.id}, {"$addToSet": {"whitelist_domains": domain}}, upsert=True)
    await message.reply(f"✅ Domain **{domain}** whitelisted from link blocking.", quote=True)

# Flask admin panel
app = Flask(__name__)

@app.route('/')
def index():
    return "<h3>AutoDelete Bot is running</h3>"

@app.route('/admin')
def admin_panel():
    if request.headers.get("X-API-KEY") != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    data = list(group_config.find({}, {"_id": 0}))
    html = "<h2>Group Settings</h2>" + "<br>".join(f"<pre>{g}</pre>" for g in data)
    return html

port = int(os.getenv("PORT", 8000))
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port)).start()

bot.run()
