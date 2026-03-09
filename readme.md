# Small Cap Trading Bot

## Overview

A personal project for scanning small-cap stocks for momentum signals in real time.

The main script is `ahk-bot-olenka-flash-spike.py`. It streams live market data, runs it through a signal filter, and writes qualifying symbols to a file. A companion script (`scraper/scraper.py`) watches that file and scrapes news and fundamentals for any new symbol that shows up, then pops it up on screen.

---

## How It Works

### Step 1 — Filter tickers at startup

Before streaming starts, the bot filters a flat list of tickers down to a watchlist. A symbol passes if it meets all three:

| Filter | Condition |
|---|---|
| Price | Between $0.50 and $6.00 |
| Float | Below 4 million shares (FMP API) |
| Pre-market volume | Below 15,000 shares since 4:00 AM ET |

Filtering runs in parallel with a thread pool and the result gets cached to disk, so the next run skips the API calls if the cache is still fresh.

### Step 2 — Stream live data

Filtered symbols are subscribed to via the Alpaca WebSocket (SIP feed). The bot receives a live stream of quotes and trades for each symbol.

Events go into async queues and get processed by a pool of workers. Symbols are distributed across workers using consistent hashing (`xxhash`) so the same symbol always lands on the same worker — no race conditions.

### Step 3 — Signal detection

Every incoming quote runs through four rules. All four must pass for a signal to fire.

**Rule 1 — Flash spike (1-second trade window)**
- At least `FLASH_SPIKE_TRADE_COUNT` trades in the last 1 second
- Those trades must show a consecutive increasing price trend of at least `MIN_CONSECUTIVE_INCREASES` steps (longest increasing subsequence via `bisect`)
- Price range across those trades ≥ `MIN_BUY_PRICE_MOVE`
- Average trade size ≥ `FLASH_SPIKE_AVG_VOLUME`

**Rule 2 — 5-minute rolling price move**
- Current ask must be at least +3% above the lowest price in the last 5 minutes

**Rule 3 — 5-minute rolling volume**
- Total volume in the last 5 minutes must exceed `VOLUME_5MIN_THRESHOLD`

**Rule 4 — Quote quality**
- Ask and bid must both be non-zero
- Bid-ask spread ≤ `SPREAD_THRESHOLD`

### Step 4 — Write the signal

When a symbol passes, two lines are written to `symbol-signals/trade-{date}.txt` — the ticker and a JSON line with metadata:

```
AAPL
{"symbol": "AAPL", "price": 2.45, "change_pct": 4.12, "volume_intraday": 8200, "spread": 0.02, "time": "09:34:21"}
```

A sound alert fires at detection.

### Step 5 — Scraper picks it up

`scraper/scraper.py` uses `watchdog` to monitor the signal file. When a new symbol appears:

1. Scrapes [stocktitan.net](https://www.stocktitan.net) for the latest news headline, article content, AI summary, and price impact
2. Pulls fundamental data: market cap, float, short percent, sector, industry, insider/institutional ownership
3. Saves everything to `results_csv/{date}/{symbol}.csv`
4. Shows a scrollable desktop pop-up with the info and a link to the full article

---

## Repository Structure

```
small-cap-trading-bot/
├── ahk-bot-olenka-flash-spike.py   # Main bot — filtering, streaming, signal detection
├── config.py                        # All thresholds and API keys
├── scraper/
│   └── scraper.py                   # File watcher, scraper, desktop popup
├── symbol-signals/
│   └── trade-{date}.txt             # Written by the bot, read by the scraper
├── results_csv/
│   └── {date}/
│       └── {symbol}.csv             # One file per symbol per day
└── trade_logs/
    └── trade_log_{date}.txt         # Full log of bot activity
```

---

## Configuration

Everything lives in `config.py`. Key parameters:

| Parameter | What it does |
|---|---|
| `API_KEY` / `API_SECRET` | Alpaca credentials |
| `FMP_API_KEY` | FMP key for float data |
| `SCAN_START_HOUR` / `SCAN_END_HOUR` | Active window (ET) |
| `PROFIT_TRIGGER` | Minimum 5-min price move (default 3%) |
| `VOLUME_5MIN_THRESHOLD` | Minimum 5-min rolling volume |
| `SPREAD_THRESHOLD` | Maximum bid-ask spread |
| `FLASH_SPIKE_TRADE_COUNT` | Minimum trades in last 1 second |
| `FLASH_SPIKE_AVG_VOLUME` | Minimum average size of those trades |
| `MIN_BUY_PRICE_MOVE` | Minimum price range across the 1-sec burst |
| `MIN_CONSECUTIVE_INCREASES` | Minimum increasing steps in the burst |
| `COOLDOWN_MINUTES` | Lockout after a signal fires for a symbol |
| `CACHE_EXPIRY_HOURS` | How long the filtered symbol cache is valid |

---

## Running It

```bash
pip install alpaca-trade-api requests beautifulsoup4 watchdog screeninfo pytz xxhash certifi
```

Set API keys in `config.py`, then:

```bash
# Terminal 1
python ahk-bot-olenka-flash-spike.py

# Terminal 2
cd scraper && python scraper.py
```

CLI commands available in the bot terminal:

| Command | Effect |
|---|---|
| `pause` | Stop processing quotes |
| `resume` | Resume |
| `exit <SYMBOL>` | Submit a manual limit sell for a position |
| `exit` | Shut down cleanly |

---

## Technologies

| | |
|---|---|
| **Language** | Python 3, asyncio |
| **Market data** | Alpaca WebSocket (SIP feed), Alpaca REST API |
| **Fundamental data** | Financial Modeling Prep (FMP) API |
| **Scraping** | requests, BeautifulSoup4 |
| **File watching** | watchdog |
| **Desktop UI** | tkinter, screeninfo, webbrowser |
| **Hashing / routing** | xxhash (consistent hashing across workers) |
| **Rolling windows** | collections.deque, bisect |
| **Storage** | csv, json, Python logging |
| **Timezone** | pytz (all times in US/Eastern) |
| **SSL** | certifi (custom context for WebSocket stability) |
| **Concurrency** | asyncio queues, ThreadPoolExecutor |

---

## Notes

- The bot writes signals to a file instead of submitting orders directly. Alpaca order execution code exists in the codebase but was only used during early testing — stopped because the broker at the time didn't support API order execution.
- A background task runs every 5 minutes and permanently blocks any symbol whose total intraday volume has crossed `VOLUME_THRESHOLD`, even if no signal fired for it.
- The executed symbols list is persisted to disk and expires after `EXECUTED_EXPIRY_HOURS`, so the same symbol can't be flagged twice across sessions.