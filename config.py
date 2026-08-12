import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]

DATABASE_URL = os.getenv("DATABASE_URL", "")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "./sessions")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
