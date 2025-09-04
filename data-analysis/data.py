import os
import csv
from datetime import datetime

# --- Базова директорія скрипта ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Шлях до trade_logs ---
trade_log_dir = os.path.join(BASE_DIR, "..", "trade_logs")
trade_log_dir = os.path.abspath(trade_log_dir)
print("Looking for trade_logs in:", trade_log_dir)

# --- Знайти останній trade log ---
trade_files = [f for f in os.listdir(trade_log_dir) if f.endswith(".txt")]
if not trade_files:
    raise FileNotFoundError("❌ No trade log files found in 'trade_logs/'")

trade_files.sort(key=lambda x: os.path.getmtime(os.path.join(trade_log_dir, x)), reverse=True)
TRADE_LOG_FILE = os.path.join(trade_log_dir, trade_files[0])
print("Using trade log file:", TRADE_LOG_FILE)

# --- Шлях до scraper CSV ---
today_str = datetime.today().strftime("%Y-%m-%d")
SCRAPER_DIR = os.path.join(BASE_DIR, "..", "scraper", "results_csv", today_str)
SCRAPER_DIR = os.path.abspath(SCRAPER_DIR)
COMBINED_FILE = os.path.join(BASE_DIR, "combined.csv")

# --- Поля ---
TRADE_FIELDS = [
    "price_at_detection", "low_price_5_min", "price_jump",
    "avg_vol_1sec", "num_trades_1sec", "vol_5min", "price_diff"
]

SCRAPER_FIELDS = [
    "symbol", "news_title", "news_url", "news_date", "news_time", "price_impact",
    "news_content", "summary",
    "market_cap", "float", "insiders_ownership", "institutions_ownership",
    "short_percent", "industry", "sector", "website", "country", "city"
]

ALL_FIELDS = ["timestamp", "symbol"] + TRADE_FIELDS + [f for f in SCRAPER_FIELDS if f != "symbol"]

# --- Зчитати trade log ---
trade_data = []
with open(TRADE_LOG_FILE, "r", encoding="utf-8-sig") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        # символ = перше слово у рядку
        words = line.split()
        sym = words[0]

        # дані ключ=значення після |
        tdata = {"symbol": sym}
        parts = [p.strip() for p in line.split("|") if p.strip()]
        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            try:
                if "%" in value:
                    value = float(value.replace("%", ""))
                elif "." in value:
                    value = float(value)
                else:
                    value = int(value)
            except:
                pass
            tdata[key] = value
        trade_data.append(tdata)

if not trade_data:
    print("⚠️ No trade data parsed!")

# --- Об'єднати з scraper CSV ---
combined_rows = []
for tdata in trade_data:
    sym = tdata["symbol"]
    scraper_file = os.path.join(SCRAPER_DIR, f"{sym}.csv")
    scraper_row = {}
    if os.path.isfile(scraper_file):
        with open(scraper_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            scraper_row = next(reader, {})
    else:
        print(f"⚠️ No scraper CSV for symbol: {sym}")

    row = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    row["symbol"] = sym
    for field in TRADE_FIELDS:
        row[field] = tdata.get(field, "")
    for field in SCRAPER_FIELDS:
        if field != "symbol":
            row[field] = scraper_row.get(field, "")
    combined_rows.append(row)

# --- Записати у фінальний CSV ---
file_exists = os.path.isfile(COMBINED_FILE)
with open(COMBINED_FILE, "a", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=ALL_FIELDS)
    if not file_exists:
        writer.writeheader()
    for row in combined_rows:
        writer.writerow(row)

print(f"✅ Combined CSV updated: {COMBINED_FILE}")
