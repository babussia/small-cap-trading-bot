import os
import requests
from bs4 import BeautifulSoup
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import tkinter as tk
from queue import Queue
import webbrowser
import threading
import screeninfo  # pip install screeninfo

BASE_URL = "https://www.stocktitan.net/overview/"
TRADE_FILE = "../trade.txt"
OUTPUT_DIR = "results_md"

popup_queue = Queue()  # для передачі даних від watchdog до головного потоку


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


def save_to_md(data, output_dir=OUTPUT_DIR):
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


def show_popup(data):
    popup = tk.Toplevel(root)
    popup.title(f"{data['symbol']} – News")
    popup.attributes('-topmost', True)

    # визначаємо другий монітор
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

    # Текст новини
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


class TradeFileHandler(FileSystemEventHandler):
    def __init__(self):
        self.seen = set()

    def on_modified(self, event):
        if event.src_path.endswith("trade.txt"):
            with open(TRADE_FILE, "r") as f:
                symbols = [line.strip().upper() for line in f if line.strip()]
            
            new_symbols = [s for s in symbols if s not in self.seen]
            for symbol in new_symbols:
                info = scrape(symbol)
                if info:
                    save_to_md(info)
                    print(f"✅ Scraped & saved {symbol}")
                    popup_queue.put(info)  # додаємо в чергу для головного потоку
                self.seen.add(symbol)


def start_watchdog():
    event_handler = TradeFileHandler()
    observer = Observer()
    observer.schedule(event_handler, path=os.path.dirname(TRADE_FILE) or ".", recursive=False)
    observer.start()
    try:
        while True:
            pass
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    print("🚀 Watching trade.txt for new symbols (Ctrl+C to stop)...")

    # Стартуємо watchdog у фоновому потоці
    threading.Thread(target=start_watchdog, daemon=True).start()

    # Головний цикл Tkinter (в головному потоці)
    def check_queue():
        while not popup_queue.empty():
            data = popup_queue.get()
            show_popup(data)  # створює попап на другому моніторі
        root.after(1000, check_queue)  # перевірка черги кожну секунду

    root = tk.Tk()
    root.withdraw()  # сховати основне вікно
    root.after(1000, check_queue)
    root.mainloop()
