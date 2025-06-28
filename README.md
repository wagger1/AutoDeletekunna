# Auto-Purge Bot (Pyrogram)

Deletes **all** messages in any Telegram group 10 minutes after they arrive.

## Deploy on Koyeb

1.  Create a new **GitHub repo** with the four files:
    * `bot.py`
    * `requirements.txt`
    * `Procfile`
    * `README.md`
2.  Push to GitHub, then in Koyeb:
    * **Create App ▸ GitHub ▸ pick the repo**
    * Choose **Python buildpack** (detected automatically).
    * In “Environment Variables” add
      * `API_ID`
      * `API_HASH`
      * `BOT_TOKEN`
      * *(optional)* `PURGE_SECONDS` – override default 600 s.
3.  Finish.  Grant the bot **Delete messages** admin right in the groups you
    want auto-cleaned.

## Local test

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export API_ID=12345 API_HASH=abcd… BOT_TOKEN=123:abc
python bot.py
