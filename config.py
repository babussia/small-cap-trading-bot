import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

class Config:
    # ✅ Alpaca API
    API_KEY = os.getenv("API_KEY")
    API_SECRET = os.getenv("API_SECRET")
    BASE_URL = os.getenv("BASE_URL")
    DATA_STREAM_URL = os.getenv("DATA_STREAM_URL")

    # ✅ Financial APIs
    FMP_API_KEY = os.getenv("FMP_API_KEY")
    POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

    # ✅ Files
    TICKER_FILE = os.getenv("TICKER_FILE")
    CACHE_FILE = os.getenv("CACHE_FILE")
    EXECUTED_FILE = os.getenv("EXECUTED_FILE")

    # ✅ Expiry Settings
    EXECUTED_EXPIRY_HOURS = int(os.getenv("EXECUTED_EXPIRY_HOURS", 10))
    CACHE_EXPIRY_HOURS = int(os.getenv("CACHE_EXPIRY_HOURS", 10))

    # ✅ Trading Thresholds
    VOLUME_THRESHOLD = int(os.getenv("VOLUME_THRESHOLD", 29000))
    VOLUME_5MIN_THRESHOLD = int(os.getenv("VOLUME_5MIN_THRESHOLD", 1200))
    SPREAD_THRESHOLD = float(os.getenv("SPREAD_THRESHOLD", 0.20))
    PROFIT_TRIGGER = float(os.getenv("PROFIT_TRIGGER", 0.03))
    STOP_LOSS_ABS = float(os.getenv("STOP_LOSS_ABS", 0.15))
    COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", 10))
    SCAN_START_HOUR = int(os.getenv("SCAN_START_HOUR", 4))
    SCAN_END_HOUR = int(os.getenv("SCAN_END_HOUR", 20))
    FLASH_SPIKE_TRADE_COUNT = int(os.getenv("FLASH_SPIKE_TRADE_COUNT", 6))
    FLASH_SPIKE_AVG_VOLUME = int(os.getenv("FLASH_SPIKE_AVG_VOLUME", 80))
    MIN_BUY_PRICE_MOVE = float(os.getenv("MIN_BUY_PRICE_MOVE", 0.03))
    MIN_CONSECUTIVE_INCREASES = int(os.getenv("MIN_CONSECUTIVE_INCREASES", 10))


    # ✅ Position Sizing
    QUANTITY = int(os.getenv("QUANTITY", 50))
