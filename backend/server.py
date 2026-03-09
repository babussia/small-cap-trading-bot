from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from hod_tracker import hod_tracker





app = FastAPI()

# ----------------------------
# CORS (allow frontend access)
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later restrict if hosted
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# In-memory signal storage
# ----------------------------
signals = []

# Define the signal schema (what the bot sends)
class Signal(BaseModel):
    symbol: str
    price: float
    change_pct: float
    volume_intraday: int
    spread: float
    time: str

# ----------------------------
# Bot → Backend: POST signal
# ----------------------------
@app.post("/signal")
def receive_signal(sig: Signal):
    """Endpoint for the bot to push new signals directly."""
    global signals

    # Insert newest at the top
    signals.insert(0, sig.dict())
    # Keep only the latest 20
    signals = signals[:20]

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Signal received: {sig.symbol}")
    return {"status": "ok", "symbol": sig.symbol}

# ----------------------------
# Frontend → Backend: GET signals
# ----------------------------
@app.get("/flashing")
def get_flashing():
    """Frontend polls this every second."""
    return {"signals": signals}

# ----------------------------
# Mock: High of Day symbols
# ----------------------------
@app.get("/hod")
def get_hod():
    """Return live % change list (sorted descending)."""
    return {"hod": hod_tracker.get_hod_list()}




# ----------------------------
# Mock: Stock overview
# ----------------------------
@app.get("/overview/{symbol}")
def stock_overview(symbol: str):
    # In production, you’ll read real scraped data here.
    return {
        "symbol": symbol.upper(),
        "market_cap": "35.76M",
        "float": "8.55M",
        "short_percent": "10.67%",
        "sector": "Software",
        "industry": "Application Services",
        "insiders_ownership": "5.88%",
        "institutions_ownership": "38.52%",
        "country": "United States",
        "website": "https://example.com",
    }

# ----------------------------
# Mock: Stock news
# ----------------------------
@app.get("/news/{symbol}")
def stock_news(symbol: str):
    # Later, pull from your scraper CSV.
    return {
        "symbol": symbol.upper(),
        "headlines": [
            {
                "title": f"{symbol.upper()} announces strong Q3 results",
                "date": "Oct 20, 2025",
                "time": "09:30 AM",
                "summary": f"{symbol.upper()} reported a 15% revenue increase quarter over quarter.",
            },
            {
                "title": f"{symbol.upper()} expands into new markets",
                "date": "Oct 19, 2025",
                "time": "02:10 PM",
                "summary": f"The company plans to launch products in Asia and Europe in 2026.",
            },
        ],
    }

# ----------------------------
# Root check
# ----------------------------
@app.get("/")
def root():
    return {"status": "ok", "time": datetime.now().strftime("%H:%M:%S")}

@app.post("/hod/add")
async def add_hod(symbol_data: dict):
    """Simulate a stock reaching new HOD (manual test)."""
    try:
        sym = symbol_data.get("symbol")
        price = float(symbol_data.get("price", 0))
        change_pct = float(symbol_data.get("change_pct", 0))
        time = symbol_data.get("time", "")
        if not sym:
            raise HTTPException(status_code=400, detail="Symbol required")

        print(f"📈 Adding HOD symbol: {sym} @ {price} ({change_pct}%)")

        # Make sure tracker exists
        from hod_tracker import hod_tracker
        hod_tracker.update_hod(sym, price, change_pct, time)

        return {"status": "ok", "symbol": sym}

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

