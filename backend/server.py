from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os, json
from datetime import datetime

app = FastAPI()

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all, lock later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/flashing")
def get_flashing():
    today = datetime.now().strftime("%Y-%m-%d")
    # Absolute path to your bot's signal folder
    file_path = f"C:/Users/DELL/Desktop/bot-smallcapgirl/symbol-signals/trade-{today}.txt"

    if os.path.exists(file_path):
        with open(file_path) as f:
            return {"symbols": [line.strip() for line in f]}
    return {"symbols": []}


@app.get("/hod")
def get_hod():
    # TODO: hook into your scraper logic
    return {"hod": ["AAPL", "TSLA", "NVDA"]}

@app.get("/overview/{symbol}")
def stock_overview(symbol: str):
    # TODO: connect with your scraper/bot data
    return {
        "symbol": symbol,
        "float": "5M",
        "volume": "120K",
        "price": "2.45"
    }

@app.get("/news/{symbol}")
def stock_news(symbol: str):
    # TODO: connect with your scraper
    return {
        "symbol": symbol,
        "headlines": [
            "Company X releases earnings",
            "Analyst upgrades outlook"
        ]
    }
