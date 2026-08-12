import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

raw_api_id = os.getenv("API_ID", "0").strip()
TELEGRAM_API_ID = int(raw_api_id) if raw_api_id.isdigit() else 0

TELEGRAM_API_HASH = os.getenv("API_HASH", "").strip()

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions").strip()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip()
