import os

SCAN_URL = os.environ.get(
    "HULL_SCAN_URL", "https://chartink.com/screener/hull-scan-28"
)

DB_PATH = os.environ.get(
    "HULL_SCAN_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "scan_history.db")
)

SCAN_INTERVAL_MINUTES = float(os.environ.get("HULL_SCAN_INTERVAL", "5"))

MARKET_TZ = os.environ.get("MARKET_TZ", "Asia/Kolkata")
MARKET_OPEN = os.environ.get("MARKET_OPEN", "09:30")
MARKET_CLOSE = os.environ.get("MARKET_CLOSE", "15:30")
MARKET_DAYS = {0, 1, 2, 3, 4}  # Monday(0) to Friday(4)

REQUEST_TIMEOUT = 30
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 10

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8853706072:AAF5qqbVY3fro-F6Yexfx_JvrCUYHrdAOXk")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "382068320")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
