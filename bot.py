# auto-purge bot  – deletes every message in every group 10 minutes after it lands
#
# works on Koyeb (Python buildpack) – set 3 env-vars:
#   API_ID   • API_HASH   • BOT_TOKEN
# optional:
#   PURGE_SECONDS   (defaults to 600  = 10 min)

import os, asyncio, logging
from pyrogram import Client, filters
from pyrogram.types import Message

# ─── credentials come from environment ────────────────────────────────
API_ID        = int(os.getenv("API_ID", "0"))
API_HASH      = os.getenv("API_HASH", "")
BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
PURGE_SECONDS = int(os.getenv("PURGE_SECONDS", "600"))   # default 10 min

if not all((API_ID, API_HASH, BOT_TOKEN)):
    raise RuntimeError("API_ID, API_HASH, BOT_TOKEN must be set as env vars")

# ─── logging (Koyeb captures stdout) ──────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s"
)

bot = Client(
    "auto_purge_worker",
    api_id     = API_ID,
    api_hash   = API_HASH,
    bot_token  = BOT_TOKEN
)

# ─── main handler: schedule deletion for EVERY message in groups ──────
@bot.on_message(filters.group)
async def schedule_delete(_, m: Message):
    async def purge():
        await asyncio.sleep(PURGE_SECONDS)
        try:
            await m.delete()
        except Exception:
            pass    # already gone or no rights

    asyncio.create_task(purge())

# ─── run ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot.run()
