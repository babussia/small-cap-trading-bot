import os
import requests
from bs4 import BeautifulSoup
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from plyer import notification
import tkinter as tk
import threading
import webbrowser
import screeninfo  # pip install screeninfo
from datetime import date
import csv

BASE_URL = "https://www.stocktitan.net/overview/"

# --- Папки ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADE_DIR = os.path.join(BASE_DIR, "symbol-signals")

# --- Дата ---
today_str = date.today().strftime("%Y-%m-%d")

# --- Trade файл ---
TRADE_FILE = os.path.join(TRADE_DIR, f"trade-{today_str}.txt")

# --- OUTPUT папки ---
OUTPUT_DIR_MD = os.path.join("results_md", today_str)
os.makedirs(OUTPUT_DIR_MD, exist_ok=True)

OUTPUT_DIR_CSV = os.path.join("results_csv", today_str)
os.makedirs(OUTPUT_DIR_CSV, exist_ok=True)

CSV_FIELDS = [
    "symbol", "news_title", "news_url", "news_date", "news_time", "price_impact",
    "news_content", "summary",
    "market_cap", "float", "insiders_ownership", "institutions_ownership",
    "short_percent", "industry", "sector", "website", "country", "city"
]

def scrape(symbol: str):
    overview_url = f"{BASE_URL}{symbol}"
    
    r = requests.get(overview_url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print(f"❌ Failed to load overview: {symbol}")
        return None
    
    soup = BeautifulSoup(r.text, "html.parser")
    latest_news = soup.select_one("div.st-panel-body.news-list div.news-item")
    if not latest_news:
        print(f"⚠️ No news found for {symbol}")
        return None

    news_link_tag = latest_news.select_one("h3.news-title a")
    news_url = "https://www.stocktitan.net" + news_link_tag["href"] if news_link_tag else ""
    news_title = news_link_tag.get_text(strip=True) if news_link_tag else ""
    news_date_tag = latest_news.select_one("div.news-time")
    news_date = news_date_tag["title"] if news_date_tag and news_date_tag.has_attr("title") else ""

    # --- fetch full news page ---
    news_content = ""
    news_time = ""
    summary_text = ""
    stock_data = {field.lower().replace(" ", "_"): "N/A" for field in [
        "Market Cap", "Float", "Insiders Ownership", "Institutions Ownership",
        "Short Percent", "Industry", "Sector", "Website", "Country", "City"
    ]}

    if news_url:
        news_page = requests.get(news_url, headers={"User-Agent": "Mozilla/5.0"})
        if news_page.status_code == 200:
            news_soup = BeautifulSoup(news_page.text, "html.parser")

            # Full news content
            content_tag = news_soup.select_one("div.news-content")
            if content_tag:
                news_content = content_tag.get_text(strip=True)

            # --- scrape <time> ---
            time_tag = news_soup.select_one("time[datetime]")
            if time_tag:
                news_time = time_tag.get_text(strip=True)

            # --- scrape Rhea-AI summary ---
            summary_tag = news_soup.select_one("div.news-card-summary #summary")
            if summary_tag:
                summary_text = summary_tag.get_text(strip=True)

            # --- scrape stock data ---
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

# --- Save MD ---
def save_to_md(data, output_dir=OUTPUT_DIR_MD):
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir, f"{data['symbol']}.md")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# {data['symbol']}\n\n")
        f.write(f"**Latest News:** [{data['news_title']}]({data['news_url']})\n\n")
        f.write(f"- **Date:** {data['news_date']}\n")
        f.write(f"- **Time:** {data['news_time']}\n")
        f.write(f"- **Price Impact:** {data['price_impact']}\n\n")

        f.write("## Summary\n")
        f.write(f"{data['summary']}\n\n")

        f.write("## Full News Content\n")
        f.write(f"{data['news_content']}\n\n")

        f.write("## Stock Data\n")
        for key in ["market_cap", "float", "insiders_ownership", "institutions_ownership",
                    "short_percent", "industry", "sector", "website", "country", "city"]:
            f.write(f"- **{key.replace('_',' ').title()}:** {data.get(key,'N/A')}\n")
    return filename

# --- Save CSV ---
def save_to_csv(data, output_dir=OUTPUT_DIR_CSV):
    os.makedirs(output_dir, exist_ok=True)
    csv_file = os.path.join(output_dir, f"{data['symbol']}.csv")
    file_exists = os.path.isfile(csv_file)
    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({field: data.get(field, "N/A") for field in CSV_FIELDS})
    return csv_file

# --- Popup ---
def show_popup_with_link(data):
    notification.notify(
        title=f"{data['symbol']} – News",
        message=f"{data['news_title']}\nDate: {data['news_date']}\nImpact: {data['price_impact']}",
        timeout=8
    )

    def popup():
        root = tk.Tk()
        root.title(f"{data['symbol']} – News")
        root.attributes('-topmost', True)

        screens = screeninfo.get_monitors()
        if len(screens) > 1:
            second = screens[1]
            x = second.x + 50
            y = second.y + 50
        else:
            x, y = 50, 50

        canvas = tk.Canvas(root)
        scrollbar = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        root.geometry(f"500x600+{x}+{y}")

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

        root.mainloop()

    threading.Thread(target=popup, daemon=True).start()

# --- Watcher ---
class TradeFileHandler(FileSystemEventHandler):
    def __init__(self, trade_file):
        self.trade_file = trade_file
        self.seen = set()

    def on_modified(self, event):
        if os.path.abspath(event.src_path) == os.path.abspath(self.trade_file):
            with open(self.trade_file, "r") as f:
                symbols = [line.strip().upper() for line in f if line.strip()]
            
            new_symbols = [s for s in symbols if s not in self.seen]
            for symbol in new_symbols:
                info = scrape(symbol)
                if info:
                    md_path = save_to_md(info)
                    csv_path = save_to_csv(info)
                    print(f"✅ Scraped & saved MD: {md_path}")
                    print(f"✅ Also saved CSV: {csv_path}")
                    show_popup_with_link(info)
                self.seen.add(symbol)

# --- Main ---
if __name__ == "__main__":
    print(f"🚀 Watching {TRADE_FILE} for new symbols (Ctrl+C to stop)...")
    event_handler = TradeFileHandler(TRADE_FILE)
    observer = Observer()
    observer.schedule(event_handler, path=os.path.dirname(TRADE_FILE) or ".", recursive=False)
    observer.start()

    try:
        while True:
            pass
    except KeyboardInterrupt:
        observer.stop()
        print("\n🛑 Stopped by user.")
    observer.join()
