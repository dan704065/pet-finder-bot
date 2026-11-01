"""Copy to config.py and configure environment variables before starting the bot."""

import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = [int(value.strip()) for value in os.environ.get("ADMIN_IDS", "").split(",") if value.strip()]
