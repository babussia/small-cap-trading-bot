import os
import requests
from bs4 import BeautifulSoup
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import tkinter as tk
from queue import Queue
import webbrowser
import threading
import screeninfo
import datetime
import time
from concurrent.futures import ThreadPoolExecutor
import csv

BASE_URL = "https://www.stocktitan.net/overview/"

# --- dynamic trade file ---
today = datetime.date.today().strftime("%Y-%m-%d")
TRADE_FILE = os.path.join("..", "symbol-signals", f"trade-{today}.txt")

# --- output folder by date ---
OUTPUT_DIR = os.path.join("results_csv", today)
os.makedirs(OUTPUT_DIR, exist_ok=True)

popup_queue = Queue()
executor = ThreadPoolExecutor(max_workers=5)  # scrape multiple symbols faster

def scrape(symbol: str):
    overview_url = f"{BASE_URL}{symbol}"
    r = requests.get(overview_url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        return None
    
    soup = BeautifulSoup(r.text, "html.parser")
    latest_news = soup.select_one("div.st-panel-body.news-list div.news-item")
    if not latest_news:
        return None

    news_link_tag = latest_news.select_one("h3.news-title a")
    news_url = "https://www.stocktitan.net" + news_link_tag["href"] if news_link_tag else ""
    news_title = news_link_tag.get_text(strip=True) if news_link_tag else ""
    news_date_tag = latest_news.select_one("div.news-time")
    news_date = news_date_tag["title"] if news_date_tag and news_date_tag.has_attr("title") else ""

    # --- fetch full news page ---
    news_content, news_time, summary_text = "", "", ""
    stock_data = {field.lower().replace(" ", "_"): "N/A" for field in [
        "Market Cap", "Float", "Insiders Ownership", "Institutions Ownership",
        "Short Percent", "Industry", "Sector", "Website", "Country", "City"
    ]}

    if news_url:
        news_page = requests.get(news_url, headers={"User-Agent": "Mozilla/5.0"})
        if news_page.status_code == 200:
            news_soup = BeautifulSoup(news_page.text, "html.parser")

            content_tag = news_soup.select_one("div.news-content")
            if content_tag:
                news_content = content_tag.get_text(strip=True)

            time_tag = news_soup.select_one("time[datetime]")
            if time_tag:
                news_time = time_tag.get_text(strip=True)

            summary_tag = news_soup.select_one("div.news-card-summary #summary")
            if summary_tag:
                summary_text = summary_tag.get_text(strip=True)

            for div in news_soup.select("div.news-list-item.stock-data"):
                label = div.find("label")
                if not label:
                    continue
                field_name = label.get_text(strip=True)
                key = field_name.lower().replace(" ", "_")
                if key not in stock_data:
                    continue

                if field_name == "Website":
                    a_tag = div.find("a")
                    stock_data[key] = a_tag["href"] if a_tag else "N/A"
                else:
                    span = div.find("span", class_="d-flex")
                    stock_data[key] = span.get_text(strip=True) if span else "N/A"

    data = {
        "symbol": symbol,
        "news_title": news_title,
        "news_url": news_url,
        "news_date": news_date,
        "news_time": news_time,
        "price_impact": latest_news.select_one("div.price-impact").get_text(strip=True) if latest_news.select_one("div.price-impact") else "",
        "news_content": news_content,
        "summary": summary_text
    }
    data.update(stock_data)
    return data

# --- CSV save/load ---
def save_to_csv(data, output_dir=OUTPUT_DIR):
    filename = os.path.join(output_dir, f"{data['symbol']}.csv")
    fieldnames = list(data.keys())
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(data)
    return filename

def load_from_csv(symbol, output_dir=OUTPUT_DIR):
    filename = os.path.join(output_dir, f"{symbol}.csv")
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return next(reader)

# --- popup window ---
def show_popup(symbol):
    data = load_from_csv(symbol)
    if not data:
        print(f"❌ No CSV found for {symbol}")
        return

    popup = tk.Toplevel(root)
    popup.title(f"{data['symbol']} – News")
    popup.attributes('-topmost', True)

    # place on second monitor if exists
    screens = screeninfo.get_monitors()
    if len(screens) > 1:
        second = screens[1]
        x = second.x + 50
        y = second.y + 50
    else:
        x, y = 50, 50

    popup.geometry(f"500x600+{x}+{y}")

    canvas = tk.Canvas(popup)
    scrollbar = tk.Scrollbar(popup, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    label_text = f"{data['news_title']}\nDate: {data['news_date']} {data['news_time']}\nImpact: {data['price_impact']}"
    tk.Label(scrollable_frame, text=label_text, font=("Arial", 12), justify="left", wraplength=480).pack(pady=(10,5))

    def open_link(event):
        webbrowser.open(data['news_url'])

    link = tk.Label(scrollable_frame, text="Read full article", fg="blue", cursor="hand2", font=("Arial", 12, "underline"))
    link.pack()
    link.bind("<Button-1>", open_link)

    tk.Label(scrollable_frame, text=data['summary'], font=("Arial", 11), justify="left", wraplength=480).pack(pady=(5,10))
    tk.Label(scrollable_frame, text=data['news_content'], font=("Arial", 11), justify="left", wraplength=480).pack(pady=(5,10))

    stock_text = "\n".join([f"{k.replace('_',' ').title()}: {data.get(k,'N/A')}" for k in [
        "market_cap","float","insiders_ownership","institutions_ownership","short_percent",
        "industry","sector","website","country","city"]])
    tk.Label(scrollable_frame, text=stock_text, font=("Arial", 11), justify="left", wraplength=480).pack(pady=(5,10))

# --- watchdog handler ---
class TradeFileHandler(FileSystemEventHandler):
    def __init__(self):
        self.seen = set()
        self.last_event_time = 0

    def on_modified(self, event):
        if not event.src_path.endswith(os.path.basename(TRADE_FILE)):
            return

        now = time.time()
        if now - self.last_event_time < 1:
            return
        self.last_event_time = now

        with open(TRADE_FILE, "r") as f:
            symbols = [line.strip().upper() for line in f if line.strip()]

        new_symbols = [s for s in symbols if s not in self.seen]
        for symbol in new_symbols:
            executor.submit(self.process_symbol, symbol)
            self.seen.add(symbol)

    def process_symbol(self, symbol):
        info = scrape(symbol)
        if info:
            save_to_csv(info)
            print(f"✅ Scraped & saved {symbol}")
            popup_queue.put(symbol)

# --- start watchdog ---
def start_watchdog():
    event_handler = TradeFileHandler()
    observer = Observer()
    observer.schedule(event_handler, path=os.path.dirname(TRADE_FILE) or ".", recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# --- main ---
if __name__ == "__main__":
    print(f"🚀 Watching {TRADE_FILE} for new symbols (Ctrl+C to stop)...")

    threading.Thread(target=start_watchdog, daemon=True).start()

    root = tk.Tk()
    root.withdraw()

    def check_queue():
        while not popup_queue.empty():
            symbol = popup_queue.get()
            show_popup(symbol)
        root.after(500, check_queue)

    root.after(500, check_queue)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\n👋 Exiting gracefully...")
