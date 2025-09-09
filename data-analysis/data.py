import os
import re
import csv
from datetime import date

# === CONFIG ===
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))  # this script is inside data-analysis/
TRADE_LOG_DIR = os.path.join(ROOT_DIR, "..", "trade_logs")
SCRAPER_DIR = os.path.join(ROOT_DIR, "..", "scraper", "results_csv")

OUTPUT_FILE = os.path.join(ROOT_DIR, "data_analysis.csv")

# === Today’s date string ===
today_str = date.today().strftime("%Y-%m-%d")

trade_log_file = os.path.join(TRADE_LOG_DIR, f"trade_log_{today_str}.txt")
scraper_day_dir = os.path.join(SCRAPER_DIR, today_str)

# === Regex to capture trade log line ===
line_re = re.compile(
    r"^(?P<timestamp>[\d\- :,]+) - (?P<symbol>\w+) written to .*? \| "
    r"price_at_detection=(?P<price_at_detection>[\d.]+), "
    r"low_price_5min=(?P<low_price_5min>[\d.]+), "
    r"price_jump=(?P<price_jump>[\d.]+)%, "
    r"vol_5min=(?P<vol_5min>\d+), "
    r"number_of_trades_1sec=(?P<number_of_trades_1sec>\d+), "
    r"avg_vol_1sec=(?P<avg_vol_1sec>\d+), "
    r"price_diff_1sec=(?P<price_diff_1sec>[\d.]+)"
)

# === Desired output column order ===
trade_fields = [
    "timestamp",
    "symbol",
    "price_at_detection",
    "low_price_5min",
    "price_jump",
    "vol_5min",
    "number_of_trades_1sec",
    "avg_vol_1sec",
    "price_diff_1sec"
]

scraper_fields = [
    "news_title",
    "news_url",
    "news_date",
    "news_time",
    "price_impact",
    "news_content",
    "summary",
    "market_cap",
    "float",
    "insiders_ownership",
    "institutions_ownership",
    "short_percent",
    "industry",
    "sector",
    "website",
    "country",
    "city"
]

fieldnames = trade_fields + scraper_fields

# === Collect rows ===
rows = []
seen_symbols = set()  # Track symbols we've already processed

with open(trade_log_file, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        m = line_re.search(line.strip())
        if not m:
            continue
        trade_data = m.groupdict()
        symbol = trade_data["symbol"]

        if symbol in seen_symbols:
            # Skip duplicates (only first occurrence per symbol)
            continue
        seen_symbols.add(symbol)

        # Path to scraper CSV for this symbol
        scraper_file = os.path.join(scraper_day_dir, f"{symbol}.csv")
        scraper_data = {}
        if os.path.exists(scraper_file):
            with open(scraper_file, "r", encoding="utf-8-sig") as sf:
                reader = csv.DictReader(sf)
                scraper_data = next(reader, {})  # take first row

        combined = {**trade_data, **scraper_data}
        rows.append(combined)

# === Append to data_analysis.csv ===
if rows:
    file_exists = os.path.exists(OUTPUT_FILE)

    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8-sig") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames)

        # Write header only if file is new
        if not file_exists:
            writer.writeheader()

        for row in rows:
            # Fill missing fields with empty strings
            full_row = {field: row.get(field, "") for field in fieldnames}
            writer.writerow(full_row)

    print(f"✅ Appended {len(rows)} rows to {OUTPUT_FILE}")
else:
    print("⚠️ No matching trade log entries found.")
