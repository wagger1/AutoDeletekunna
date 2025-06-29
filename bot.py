import os
import re
import asyncio
import logging
import threading
from flask import Flask, request, jsonify
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
import sys

# ── Environment ────────────────────────────────────────────────────────────
API_ID               = int(os.getenv("API_ID", "0"))
API_HASH             = os.getenv("API_HASH", "")
BOT_TOKEN            = os.getenv("BOT_TOKEN", "")
MONGO_URI            = os.getenv("MONGO_URI", "")
DEFAULT_PURGE_SECONDS = int(os.getenv("PURGE_SECONDS", "600"))   # 10 min default
LOG_CHAT_ID          = int(os.getenv("LOG_CHAT_ID", "0"))        # 0 = disable
ADMIN_KEY            = os.getenv("ADMIN_KEY", "changeme")        # for /admin

if not all((API_ID, API_HASH, BOT_TOKEN, MONGO_URI)):
    raise RuntimeError("Missing required environment variables.")

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),                     # Console output
        logging.FileHandler("bot.log", encoding="utf-8")       # Log file
    ]
)

# ── DB ─────────────────────────────────────────────────────────────────────
mongo         = MongoClient(MONGO_URI)
db            = mongo["autopurgebot"]
group_config  = db["delays"]        # one doc per group
warned_users  = {}                  # runtime cache: warned once per session

# ── Client ─────────────────────────────────────────────────────────────────
bot = Client(
    "auto_purge_worker",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# ── Helpers ────────────────────────────────────────────────────────────────
def get_group_config(chat_id: int) -> dict:
    cfg = group_config.find_one({"chat_id": chat_id}) or {}
    return {
        "delay": cfg.get("delay", DEFAULT_PURGE_SECONDS),
        "block_links": cfg.get("block_links", True),
        "block_mentions": cfg.get("block_mentions", True),
        "whitelist_usernames": cfg.get("whitelist_usernames", []),
        "whitelist_domains": cfg.get("whitelist_domains", []),
    }

async def warn_once(client: Client, message: Message):
    key = f"{message.chat.id}:{message.from_user.id if message.from_user else 0}"
    if key not in warned_users:
        warned_users[key] = True
        await message.reply("⚠️ Links or @mentions are not allowed in this group.")

# ── Auto‑purge handler ─────────────────────────────────────────────────────
@Client.on_message(filters.group & ~filters.service)
async def auto_purge(client: Client, message: Message):
    cfg  = get_group_config(message.chat.id)
    text = (message.text or message.caption or "").lower()

    is_whitelisted_user   = any(u in text for u in cfg["whitelist_usernames"])
    is_whitelisted_domain = any(d in text for d in cfg["whitelist_domains"])

    has_link    = bool(re.search(r"(https?://|t\.me/|telegram\.me/)", text))
    has_mention = bool(re.search(r"@\w{3,}", text))

    # Delete immediately if blocked
    if (
        (cfg["block_links"]    and has_link    and not is_whitelisted_domain) or
        (cfg["block_mentions"] and has_mention and not is_whitelisted_user)
    ):
        try:
            await message.delete()
            await warn_once(client, message)
            if LOG_CHAT_ID:
                await client.send_message(
                    LOG_CHAT_ID,
                    f"🚫 Link/mention deleted in "
                    f"[{message.chat.title}](https://t.me/c/{str(message.chat.id)[4:]}/{message.id})",
                    disable_web_page_preview=True,
                )
        except Exception as e:
            logging.warning("Failed immediate delete: %s", e)
        return

    # Otherwise schedule purge
    try:
        await asyncio.sleep(cfg["delay"])
        await message.delete()
        if LOG_CHAT_ID:
            await client.send_message(
                LOG_CHAT_ID,
                f"🧹 Message auto‑deleted in "
                f"[{message.chat.title}](https://t.me/c/{str(message.chat.id)[4:]}/{message.id})",
                disable_web_page_preview=True,
            )
    except Exception as e:
        logging.warning("Failed delayed delete: %s", e)

# ── Inline settings panel ──────────────────────────────────────────────────
@Client.on_message(filters.command("settings") & filters.group)
async def show_settings(client: Client, message: Message):
    cfg = get_group_config(message.chat.id)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Delay +5", callback_data="inc_delay"),
                InlineKeyboardButton("➖ Delay -5", callback_data="dec_delay"),
            ],
            [
                InlineKeyboardButton(
                    f"🔗 Links: {'✅' if cfg['block_links'] else '❌'}",
                    callback_data="toggle_links",
                )
            ],
            [
                InlineKeyboardButton(
                    f"👤 Mentions: {'✅' if cfg['block_mentions'] else '❌'}",
                    callback_data="toggle_mentions",
                )
            ],
        ]
    )
    await message.reply("**⚙️ Group Settings:**", reply_markup=keyboard)

# ── Callback‑query handler ────────────────────────────────────────────────
@Client.on_callback_query()
async def handle_callback(client: Client, cb):
    if cb.message.chat.type == "private":
        return await cb.answer("Use this in a group where I'm admin.", show_alert=True)

    cid  = cb.message.chat.id
    data = cb.data
    cfg  = get_group_config(cid)

    if data == "toggle_links":
        group_config.update_one(
            {"chat_id": cid}, {"$set": {"block_links": not cfg["block_links"]}}, upsert=True
        )
    elif data == "toggle_mentions":
        group_config.update_one(
            {"chat_id": cid},
            {"$set": {"block_mentions": not cfg["block_mentions"]}},
            upsert=True,
        )
    elif data == "inc_delay":
        group_config.update_one({"chat_id": cid}, {"$inc": {"delay": 5}}, upsert=True)
    elif data == "dec_delay":
        new_delay = max(5, cfg["delay"] - 5)
        group_config.update_one(
            {"chat_id": cid}, {"$set": {"delay": new_delay}}, upsert=True
        )

    # Refresh panel
    new_cfg = get_group_config(cid)
    new_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Delay +5", callback_data="inc_delay"),
                InlineKeyboardButton("➖ Delay -5", callback_data="dec_delay"),
            ],
            [
                InlineKeyboardButton(
                    f"🔗 Links: {'✅' if new_cfg['block_links'] else '❌'}",
                    callback_data="toggle_links",
                )
            ],
            [
                InlineKeyboardButton(
                    f"👤 Mentions: {'✅' if new_cfg['block_mentions'] else '❌'}",
                    callback_data="toggle_mentions",
                )
            ],
        ]
    )
    await cb.edit_message_reply_markup(reply_markup=new_markup)
    await cb.answer("Updated.")

# ── Status & utility commands ─────────────────────────────────────────────
@Client.on_message(filters.command("status") & filters.private)
async def status_command(client: Client, message: Message):
    count = group_config.count_documents({})
    btn   = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status")]])
    await message.reply(
        f"✅ Bot is online.\n🧠 Group configs: {count}\n⏱️ Default delay: {DEFAULT_PURGE_SECONDS}s",
        reply_markup=btn,
    )

@Client.on_callback_query(filters.regex("refresh_status"))
async def refresh_status(client, cb):
    count = group_config.count_documents({})
    await cb.message.edit_text(
        f"✅ Bot is online.\n🧠 Group configs: {count}\n⏱️ Default delay: {DEFAULT_PURGE_SECONDS}s",
        reply_markup=cb.message.reply_markup,
    )
    await cb.answer("Refreshed")

# ── Start / Help ──────────────────────────────────────────────────────────
@Client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    await message.reply(
        "**👋 Welcome to AutoDelete Bot!**\n\n"
        "Add me to your group and promote me to admin so I can delete messages.\n"
        "Use /help to see all commands and features.",
        disable_web_page_preview=True,
    )

@Client.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    await message.reply(
        "**🛠 AutoDelete Bot – Help**\n\n"
        "**Admin commands (group):**\n"
        "`/settings` – Inline panel\n"
        "`/setdelay <seconds>` – Set delete delay\n"
        "`/getdelay` – Show current delay\n"
        "`/blocklinks on|off` – Toggle link blocking\n"
        "`/blockmentions on|off` – Toggle mention blocking\n"
        "`/whitelistuser @user` – Allow that username\n"
        "`/whitelistdomain example.com` – Allow that domain\n\n"
        "**Private commands:**\n"
        "`/start` – Show welcome\n"
        "`/status` – Bot health & config count",
        disable_web_page_preview=True,
    )

# ── Delay / toggle / whitelist commands ───────────────────────────────────
@Client.on_message(filters.command("setdelay") & filters.group)
async def set_delay(client, message: Message):
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply("❗ Usage: `/setdelay <seconds>`", quote=True)
    seconds = int(message.command[1])
    group_config.update_one(
        {"chat_id": message.chat.id}, {"$set": {"delay": seconds}}, upsert=True
    )
    await message.reply(f"⏱️ Delete delay set to **{seconds} s**.", quote=True)

@Client.on_message(filters.command("getdelay") & filters.group)
async def get_delay(client, message: Message):
    cfg = get_group_config(message.chat.id)
    await message.reply(f"⏱️ Current delete delay: **{cfg['delay']} s**", quote=True)

@Client.on_message(filters.command("blocklinks") & filters.group)
async def toggle_block_links(client, message: Message):
    if len(message.command) < 2 or message.command[1].lower() not in ("on", "off"):
        return await message.reply("❗ Usage: `/blocklinks on|off`", quote=True)
    toggle = message.command[1].lower() == "on"
    group_config.update_one(
        {"chat_id": message.chat.id}, {"$set": {"block_links": toggle}}, upsert=True
    )
    await message.reply(
        f"🔗 Link blocking **{'enabled' if toggle else 'disabled'}**.", quote=True
    )

@Client.on_message(filters.command("blockmentions") & filters.group)
async def toggle_block_mentions(client, message: Message):
    if len(message.command) < 2 or message.command[1].lower() not in ("on", "off"):
        return await message.reply("❗ Usage: `/blockmentions on|off`", quote=True)
    toggle = message.command[1].lower() == "on"
    group_config.update_one(
        {"chat_id": message.chat.id}, {"$set": {"block_mentions": toggle}}, upsert=True
    )
    await message.reply(
        f"👤 Mention blocking **{'enabled' if toggle else 'disabled'}**.", quote=True
    )

@Client.on_message(filters.command("whitelistuser") & filters.group)
async def whitelist_user(client, message: Message):
    if len(message.command) < 2 or not message.command[1].startswith("@"):
        return await message.reply("❗ Usage: `/whitelistuser @username`", quote=True)
    username = message.command[1].lower()
    group_config.update_one(
        {"chat_id": message.chat.id},
        {"$addToSet": {"whitelist_usernames": username}},
        upsert=True,
    )
    await message.reply(f"✅ **{username}** whitelisted.", quote=True)

@Client.on_message(filters.command("whitelistdomain") & filters.group)
async def whitelist_domain(client, message: Message):
    if len(message.command) < 2:
        return await message.reply("❗ Usage: `/whitelistdomain example.com`", quote=True)
    domain = message.command[1].lower()
    group_config.update_one(
        {"chat_id": message.chat.id},
        {"$addToSet": {"whitelist_domains": domain}},
        upsert=True,
    )
    await message.reply(f"✅ **{domain}** whitelisted.", quote=True)

# ── Flask admin panel (optional) ───────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
def index():
    return "<h3>AutoDelete Bot is running</h3>"

@app.route("/admin")
def admin_panel():
    if request.headers.get("X-API-KEY") != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    data = list(group_config.find({}, {"_id": 0}))
    html = "<h2>Group Settings</h2>" + "<br>".join(f"<pre>{g}</pre>" for g in data)
    return html

# ── Run everything ────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False),
        daemon=True,
    ).start()
    bot.run()
