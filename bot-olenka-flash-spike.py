# Стандартні бібліотеки
import os
import json
import time
import asyncio
import logging
import threading
import requests
import platform
from datetime import datetime, timedelta, timezone
from collections import deque, defaultdict
import concurrent.futures
from threading import Semaphore
from config import Config


# Сторонні бібліотеки
import pytz
import alpaca_trade_api as tradeapi
from collections import namedtuple

TradeEvent = namedtuple("TradeEvent", ["timestamp", "price", "size"])
recent_trades_window = defaultdict(lambda: deque(maxlen=100))  # symbol: [TradeEvent]



# Limit to ~5 requests per second = 300 per minute
FMP_RATE_LIMIT = 5
fmp_semaphore = Semaphore(FMP_RATE_LIMIT)


# --- Ключі доступу до API ---
API_KEY = Config.API_KEY
API_SECRET = Config.API_SECRET
BASE_URL = Config.BASE_URL
DATA_STREAM_URL = Config.DATA_STREAM_URL

# --- Ключі фінансових API ---
FMP_API_KEY = Config.FMP_API_KEY
POLYGON_API_KEY = Config.POLYGON_API_KEY

# --- Шляхи до файлів кешу ---
TICKER_FILE = Config.TICKER_FILE
CACHE_FILE = Config.CACHE_FILE
EXECUTED_FILE = Config.EXECUTED_FILE

# --- Таймінги кешів ---
EXECUTED_EXPIRY_HOURS = Config.EXECUTED_EXPIRY_HOURS
CACHE_EXPIRY_HOURS = Config.CACHE_EXPIRY_HOURS



# === Configurable Trading Parameters ===
PROFIT_TRIGGER = Config.PROFIT_TRIGGER
STOP_LOSS_ABS = Config.STOP_LOSS_ABS
COOLDOWN_MINUTES = Config.COOLDOWN_MINUTES
SCAN_START_HOUR = Config.SCAN_START_HOUR
SCAN_END_HOUR = Config.SCAN_END_HOUR
QUANTITY = Config.QUANTITY
VOLUME_THRESHOLD = Config.VOLUME_THRESHOLD 
SPREAD_THRESHOLD = Config.SPREAD_THRESHOLD 
FLASH_SPIKE_TRADE_COUNT = Config.FLASH_SPIKE_TRADE_COUNT
FLASH_SPIKE_AVG_VOLUME = Config.FLASH_SPIKE_AVG_VOLUME


# === Alpaca API Setup ===
rest = tradeapi.REST(API_KEY, API_SECRET, BASE_URL, api_version='v2')
stream = tradeapi.Stream(API_KEY, API_SECRET, base_url=DATA_STREAM_URL, data_feed='sip')

# Безпечний запит з обмеженням по FMP API
def fmp_safe_request(url):
    with fmp_semaphore:
        try:
            response = requests.get(url, timeout=5)
            time.sleep(1 / FMP_RATE_LIMIT)  # sleep after each call
            return response
        except Exception:
            return None
        
# Завантаження та фільтрація символів
def load_symbols():
    def is_cache_fresh(path):
        return os.path.exists(path) and (time.time() - os.path.getmtime(path)) < CACHE_EXPIRY_HOURS * 3600

    if is_cache_fresh(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cached = json.load(f)
            if cached:
                print("Loaded symbols from cache.")
                return cached

    print("Filtering tickers from file...", flush=True)
    start_time = time.time()  # Start timer here

    with open(TICKER_FILE, "r") as f:
        raw_symbols = [line.strip().upper() for line in f if line.strip()]

    filtered = []
    skipped_due_to_suffix = 0
    skipped_due_to_price = 0
    errors = 0
    lock = threading.Lock()

    def check_symbol(sym):
        nonlocal skipped_due_to_suffix, skipped_due_to_price, errors
        if sym.endswith((".WS", ".U", ".R", ".B", ".C", ".D", ".E", ".F", ".G", ".H", ".I", ".J", ".K", ".L", ".M", ".N", ".O", ".P")):
            with lock:
                skipped_due_to_suffix += 1
            return None
        try:
            bar = rest.get_latest_trade(sym)
            price = bar.price
            if 0.70 <= price <= 9:
                # Перевірка float < 10 млн
                try:
                    url = f"https://financialmodelingprep.com/api/v4/shares_float?symbol={sym}&apikey={FMP_API_KEY}"
                    resp = fmp_safe_request(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, list) and data:
                            float_val = data[0].get("floatShares")
                            if float_val is not None and float_val > 8_900_000:
                                return None
                    else:
                        return None
                except Exception:
                    return None
                
                # НОВА ФІЛЬТРАЦІЯ ЗА ОБСЯГОМ З 4:00
                try:
                    tz = pytz.timezone('America/New_York')
                    now = datetime.now(tz)
                    start = now.replace(hour=4, minute=0, second=0, microsecond=0)
                    end_minute = (now.minute // 5) * 5
                    end = now.replace(minute=end_minute, second=0, microsecond=0)
                    
                    bars = rest.get_bars(sym, tradeapi.TimeFrame.Minute, start.isoformat(), end.isoformat())
                    total_volume = sum(bar.v for bar in bars)
                    if total_volume > 8500:
                        return None
                except Exception:
                    return None
                
                return sym
            else:
                with lock:
                    skipped_due_to_price += 1
        except Exception:
            with lock:
                errors += 1
        return None


    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(check_symbol, raw_symbols))

    filtered = [r for r in results if r]

    with open(CACHE_FILE, "w") as f:
        json.dump(filtered, f)

    elapsed = time.time() - start_time  # Calculate elapsed time
    print(f"Cached {len(filtered)} symbols. (Took {elapsed:.2f} seconds)", flush=True)

    return filtered

# Логгер для консолі та файлу
logger = logging.getLogger()
logger.setLevel(logging.INFO)
fmt = logging.Formatter('%(asctime)s - %(message)s')
console = logging.StreamHandler()
console.setFormatter(fmt)
logger.addHandler(console)
fileh = logging.FileHandler("trade_log.txt")
fileh.setFormatter(fmt)
logger.addHandler(fileh)

# Завантаження списку вже виконаних операцій
def load_executed():
    if os.path.exists(EXECUTED_FILE):
        with open(EXECUTED_FILE, "r") as f:
            data = json.load(f)
            timestamp = data.get("timestamp")
            symbols = set(data.get("symbols", []))
            if timestamp:
                try:
                    # Парсимо з таймзоною, якщо вона є
                    ts_dt = datetime.fromisoformat(timestamp)
                    # Якщо timestamp без таймзони (naive), робимо його aware з UTC
                    if ts_dt.tzinfo is None:
                        ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                    now_utc = datetime.now(timezone.utc)
                    if now_utc - ts_dt < timedelta(hours=EXECUTED_EXPIRY_HOURS):
                        logger.info(f"Loaded {len(symbols)} executed symbols from cache.")
                        return symbols
                except Exception as e:
                    logger.warning(f"Error parsing executed timestamp: {e}")
    logger.info("Executed list expired or missing — starting fresh.")
    return set()

# Збереження виконаних символів
def save_executed():
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols": list(executed)
    }
    with open(EXECUTED_FILE, "w") as f:
        json.dump(data, f)


symbols = load_symbols()
# Стан для кожного символу
in_position = {s: False for s in symbols}
entry_price = {}
executed = load_executed()
cooldowns = {}
last_seen_price = {}
price_record = {}
volume_window = defaultdict(lambda: deque(maxlen=5))
last_minute = defaultdict(lambda: None)
price_history = defaultdict(lambda: deque(maxlen=6))
trade_history = defaultdict(lambda: deque(maxlen=300))

tz = pytz.timezone('America/New_York')
paused = False

# НОВЕ: загальний обсяг від 4:00
total_volume_since_4am = defaultdict(int)


def now_et():
    return datetime.now(tz)


def get_recent_trades(symbol, within_ms=1000):
    cutoff = now_et() - timedelta(milliseconds=within_ms)
    return [t for t in recent_trades_window[symbol] if t.timestamp > cutoff]


# Сигнал звуку при вході
def play_sound():
    try:
        if platform.system() == "Windows":
            import winsound
            winsound.Beep(1000, 700)
        elif platform.system() == "Darwin":  # macOS
            os.system("afplay /System/Library/Sounds/Pop.aiff")
        else:
            os.system("play -nq -t alsa synth 0.2 sine 1000")
    except Exception as e:
        logger.warning(f"Sound failed: {e}")

news_cache = {}  # {symbol: (timestamp, headline)}

# async def has_today_news_async(symbol):
#     # Перевіряємо кеш (оновлення кешу кожні 10 хв)
#     now = datetime.now(timezone.utc)
#     cache_entry = news_cache.get(symbol)
#     if cache_entry:
#         cached_time, cached_headline = cache_entry
#         if (now - cached_time).total_seconds() < 600:  # 10 хв
#             return True, cached_headline

#     try:
#         today = now.strftime("%Y-%m-%d")
#         url = (
#             f"https://api.polygon.io/benzinga/v1/news?"
#             f"tickers={symbol}&published_utc.gte={today}T00:00:00Z&published_utc.lte={today}T23:59:59Z&apiKey={POLYGON_API_KEY}"
#         )
#         async with aiohttp.ClientSession() as session:
#             async with session.get(url, timeout=10) as resp:
#                 if resp.status == 200:
#                     data = await resp.json()
#                     results = data.get("results", [])
#                     if results:
#                         headline = results[0].get("title", "No title")
#                         ts = results[0].get("published_utc", "")[:19].replace("T", " ")
#                         logger.info(f"{symbol} Benzinga News {ts}: {headline}")
#                         news_cache[symbol] = (now, headline)
#                         return True, headline
#                     else:
#                         return False, None
#                 else:
#                     logger.warning(f"Benzinga news error {resp.status} for {symbol}")
#                     return False, None
#     except Exception as e:
#         logger.warning(f"Benzinga news exception for {symbol}: {e}")
#         return False, None

    
def get_price_5min_ago(sym, current_time, minutes_ago=5):
    cutoff = current_time - timedelta(minutes=minutes_ago)
    closest_price = None
    min_diff = timedelta.max

    for ts, price in price_history.get(sym, []):
        if ts <= cutoff:
            diff = cutoff - ts
            if diff < min_diff:
                min_diff = diff
                closest_price = price

    if closest_price is None:
        if price_history.get(sym):
            return price_history[sym][0][1]
        else:
            return None  # <-- Return None here, not a coroutine

    return closest_price


async def get_previous_day_close(sym):
    try:
        bars = await asyncio.to_thread(
            rest.get_bars, 
            sym, 
            tradeapi.TimeFrame.Day, 
            limit=2
        )
        if not bars or len(bars) < 2:
            return None
        return bars[-2].c  # close price of previous day
    except Exception as e:
        logger.error(f"Error getting previous close for {sym}: {e}")
        return None


async def get_last_known_price(sym):
    try:
        quote = await asyncio.to_thread(rest.get_latest_quote, sym)
        if quote.ask_price > 0:
            return quote.ask_price
        elif quote.bid_price > 0:
            return quote.bid_price
    except Exception as e:
        logger.warning(f"{sym}: Failed quote: {e}")

    try:
        trade = await asyncio.to_thread(rest.get_latest_trade, sym)
        logger.info(f"{sym}: Using last trade price = {trade.price}")
        return trade.price
    except Exception as e:
        logger.warning(f"{sym}: Failed trade: {e}")

    return None


def in_window():
    n = now_et()
    start = n.replace(hour=SCAN_START_HOUR, minute=0, second=0, microsecond=0)
    end = n.replace(hour=SCAN_END_HOUR, minute=0, second=0, microsecond=0)
    return start <= n <= end


def initialize_total_volume(symbol):
    try:
        now = now_et()
        start = now.replace(hour=4, minute=0, second=0, microsecond=0)
        # Рахуємо до початку поточного 5-хв інтервалу
        end_minute = (now.minute // 5) * 5
        end = now.replace(minute=end_minute, second=0, microsecond=0)
        bars = rest.get_bars(symbol, tradeapi.TimeFrame.Minute, start.isoformat(), end.isoformat())
        total = sum(bar.v for bar in bars)
        total_volume_since_4am[symbol] = total
        # logger.info(f"{symbol} total vol since 4am: {total:,}")
    except Exception as e:
        logger.warning(f"Failed to fetch volume for {symbol}: {e}")


async def manual_exit(symbol):
    try:
        quote = await asyncio.to_thread(rest.get_latest_quote, symbol)
        bid_price = quote.bid_price
        limit_price = round(bid_price - 0.05, 2)
        position = await asyncio.to_thread(rest.get_position, symbol)
        qty = int(position.qty)
        await asyncio.to_thread(
            rest.submit_order,
            symbol=symbol,
            qty=qty,
            side='sell',
            type='limit',
            time_in_force='day',
            limit_price=limit_price,
            extended_hours=True
        )
        ep = float(position.avg_entry_price)
        pnl_pct = (limit_price - ep) / ep * 100
        pnl_dol = (limit_price - ep) * qty
        logger.info(f"Manual exit {symbol} @ {limit_price} | P&L: {pnl_pct:.2f}% | ${pnl_dol:.2f}")
    except Exception as e:
        logger.error(f"Failed manual exit for {symbol}: {e}")
    finally:
        in_position[symbol] = False
        cooldowns[symbol] = now_et() + timedelta(minutes=COOLDOWN_MINUTES)

        # Volume rejection early
    # vol_total = total_volume_since_4am[sym]
    # if vol_total >= 29000:
    #     logger.info(f"{sym}: Total volume too high ({vol_total:,}) — skipping before flash spike check.")
    #     executed.add(sym)
    #     save_executed()
    #     return

# Обробка надходження нової котировки
async def handle_quote(q):
    global paused
    if paused:
        return

    sym = q.symbol
    price = q.ask_price
    ts = now_et()

    # Skip if cooldown, not in window, already in position, or already executed
    if sym in cooldowns and ts < cooldowns[sym]:
        return
    if not in_window() or in_position.get(sym) or sym in executed:
        return

    # === Rule 1: Rolling 5-min window price increase by at least 3%
    price_record.setdefault(sym, []).append((ts, price))
    cutoff = ts - timedelta(minutes=5)
    price_record[sym] = [(t, p) for t, p in price_record[sym] if t >= cutoff]

    prices = [p for t, p in price_record[sym] if t >= cutoff]

    if not prices:
        fallback_price = await get_last_known_price(sym)
        if not fallback_price or fallback_price == 0:
            fallback_price = await get_previous_day_close(sym)
            if not fallback_price or fallback_price == 0:
                logger.info(f"{sym}: No valid fallback price available — skipping.")
                return
        lowest_price = fallback_price
    else:
        lowest_price = min(prices)

    change_5min = (price - lowest_price) / lowest_price
    PROFIT_TRIGGER = 0.03  # 3% threshold

    if change_5min < PROFIT_TRIGGER:
        logger.info(f"{sym}: Price hasn't moved +3% from 5-min low — skipping.")

    # Check volume AFTER price rule regardless of price move
    vol_total = total_volume_since_4am[sym]
    if vol_total >= VOLUME_THRESHOLD:
        logger.info(f"{sym}: Volume exceeded {VOLUME_THRESHOLD:,} AFTER price rule — blocking permanently.")
        executed.add(sym)
        save_executed()
        return

    if change_5min < PROFIT_TRIGGER:
        return

    # === Rule 2: Flash spike detection based on recent trades volume only
    recent_trades = get_recent_trades(sym, within_ms=1000)
    if len(recent_trades) >= FLASH_SPIKE_TRADE_COUNT:
        avg_volume = sum(t.size for t in recent_trades) / len(recent_trades)

        if avg_volume >= FLASH_SPIKE_AVG_VOLUME:
            logger.info(f"{sym}: Flash spike detected — {len(recent_trades)} trades, avg vol {avg_volume:.0f}.")
            # continue to order
        else:
            logger.info(f"{sym}: No flash spike — trades: {len(recent_trades)}, avg vol: {avg_volume:.0f}.")
            return
    else:
        logger.info(f"{sym}: Not enough recent trades ({len(recent_trades)}) for flash spike detection.")
        return

    # === Additional Quote Validations and Order Submission (Rule 3)
    if q.ask_price == 0 or q.bid_price == 0:
        logger.info(f"{sym}: Incomplete quote (ask/bid = 0) — skipping.")
        return

    spread = q.ask_price - q.bid_price
    if spread > SPREAD_THRESHOLD:
        logger.info(f"{sym}: Spread too wide (${spread:.2f}) — skipping.")
        return

    try:
        asset = await asyncio.to_thread(rest.get_asset, sym)
        if not asset.tradable:
            logger.warning(f"{sym} not tradable. Skipping.")
            executed.add(sym)
            save_executed()
            return
    except Exception as e:
        logger.error(f"Error fetching asset info for {sym}: {e}")
        executed.add(sym)
        save_executed()
        return

    qty = QUANTITY
    limit_px = round(price + 0.1, 2)
    logger.info(f"Entry Signal {sym} | Price jump: {change_5min*100:.2f}% | BUY {qty} at {limit_px}")

    try:
        await asyncio.to_thread(
            rest.submit_order,
            symbol=sym,
            qty=qty,
            side='buy',
            type='limit',
            time_in_force='day',
            limit_price=limit_px,
            extended_hours=True
        )
        play_sound()
    except Exception as e:
        logger.error(f"Failed to submit order for {sym}: {e}")
        in_position[sym] = False
        executed.add(sym)
        save_executed()
        return

    # Confirm fill or fail
    for _ in range(4):
        try:
            position = await asyncio.to_thread(rest.get_position, sym)
            ep = float(position.avg_entry_price)
            logger.info(f"Filled {sym} @ {ep}")
            entry_price[sym] = ep
            in_position[sym] = True
            cooldowns[sym] = now_et() + timedelta(minutes=COOLDOWN_MINUTES)
            return
        except:
            await asyncio.sleep(1)

    logger.warning(f"{sym} not filled.")
    in_position[sym] = False
    executed.add(sym)
    save_executed()

# Обробка нового трейду (запис об'єму, ціни)
async def handle_trade(t):
    global paused
    if paused:
        return

    sym = t.symbol
    current_min = now_et().minute
    if last_minute[sym] != current_min:
        volume_window[sym].append(0)
        price_history[sym].append((now_et(), t.price))
        last_minute[sym] = current_min
    if not volume_window[sym]:
        volume_window[sym].append(0)
    volume_window[sym][-1] += t.size

    total_volume_since_4am[sym] += t.size
    recent_trades_window[sym].append(TradeEvent(
            timestamp=now_et(),
            price=t.price,
            size=t.size
        ))

    try:
        quote = await asyncio.to_thread(rest.get_latest_quote, sym)
        is_buy = t.price >= quote.ask_price
        trade_history[sym].append((now_et(), is_buy))
    except Exception as e:
        logger.warning(f"{sym}: Failed quote for trade side check: {e}")
        trade_history[sym].append((now_et(), False))

    if not in_position.get(sym):
        return
    ep = entry_price.get(sym)
    if not ep:
        return


# Періодичне очищення кешу виконаних угод
async def periodic_executed_cleanup():
    while True:
        await asyncio.sleep(3600)  # Перевіряти кожну годину
        try:
            if os.path.exists(EXECUTED_FILE):
                with open(EXECUTED_FILE, "r") as f:
                    data = json.load(f)
                    timestamp = data.get("timestamp")
                    if timestamp:
                        ts_dt = datetime.fromisoformat(timestamp)
                        now_utc = datetime.now(timezone.utc)
                        if now_utc - ts_dt >= timedelta(hours=EXECUTED_EXPIRY_HOURS):
                            logger.info("Executed list expired — clearing.")
                            os.remove(EXECUTED_FILE)
                            executed.clear()
        except Exception as e:
            logger.warning(f"Failed to cleanup executed cache: {e}")

 # Слухач команд у CLI (pause/resume/exit SYMBOL)   
async def listen_for_pause():
    global paused
    while True:
        cmd = await asyncio.to_thread(input, "Enter command (pause/resume/exit <symbol>): ")
        cmd = cmd.strip().lower()
        if cmd == 'pause' and not paused:
            paused = True
            logger.info("Bot paused.")
        elif cmd == 'resume' and paused:
            paused = False
            logger.info("Bot resumed.")
        elif cmd.startswith("exit "):
            parts = cmd.split()
            if len(parts) == 2:
                symbol = parts[1].upper()
                if symbol in in_position:
                    await manual_exit(symbol)
                else:
                    logger.warning(f"Symbol {symbol} not tracked.")
            else:
                logger.warning("Invalid exit command. Usage: exit <SYMBOL>")
        elif cmd == "exit":
            logger.info("Bot manually stopped.")
            await stream.stop_ws()  # properly close websocket
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    task.cancel()
            break
        else:
            logger.info(f"Unknown or redundant command: {cmd}")

import contextlib  # add this at the top if not already

async def main():
    logger.info("Bot initialized.")
    for sym in symbols:
        initialize_total_volume(sym)
    for sym in symbols:
        stream.subscribe_quotes(handle_quote, sym)
        stream.subscribe_trades(handle_trade, sym)

    try:
        await asyncio.gather(
            stream._run_forever(),
            listen_for_pause(),
        )
    except asyncio.CancelledError:
        logger.info("Async tasks cancelled cleanly.")
    finally:
        logger.info("Shutting down WebSocket connection...")
        try:
            await stream.stop_ws()
        except Exception as e:
            logger.warning(f"WebSocket shutdown failed: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot manually stopped by user.")
    except Exception as e:
        logger.error(f"Unexpected shutdown error: {e}")