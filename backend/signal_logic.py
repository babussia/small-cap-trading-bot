# signal_store.py
from collections import deque
from threading import Lock
from typing import Deque, Dict, List, Tuple, Any

class _SignalStore:
    """
    Thread-safe in-memory buffer for flashing signals.
    - Newest-first retrieval
    - De-dup by (symbol, time) only — Option A: allow same symbol again if time changes
    """
    def __init__(self, maxlen: int = 200):
        self._lock = Lock()
        self._seen: set[Tuple[str, str]] = set()
        self._buf: Deque[Dict[str, Any]] = deque(maxlen=maxlen)

    def add(self, ev: Dict[str, Any]) -> None:
        """
        ev must include keys: symbol (str), time (HH:MM:SS)
        Optional: price, change_pct, volume_intraday, spread
        """
        sym = (ev.get("symbol") or "").upper()
        t   = ev.get("time") or ""
        if not sym or not t:
            return

        key = (sym, t)
        with self._lock:
            if key in self._seen:
                return  # same symbol+time already in buffer → ignore
            self._seen.add(key)
            # normalize fields
            ev_norm = {
                "symbol": sym,
                "price": ev.get("price"),
                "change_pct": ev.get("change_pct"),
                "volume_intraday": ev.get("volume_intraday"),
                "spread": ev.get("spread"),
                "time": t,
            }
            # newest at left
            self._buf.appendleft(ev_norm)
            # keep seen set bounded (drop keys that fell off the deque)
            if len(self._buf) == self._buf.maxlen:
                # crude cleanup: rebuild seen from buffer (cheap at 200)
                self._seen = {(x["symbol"], x["time"]) for x in self._buf}

    def get_latest(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            # already newest-first
            return list(self._buf)[:max(0, limit)]

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()
            self._seen.clear()

SignalStore = _SignalStore(maxlen=500)  # keep more in memory if you like
