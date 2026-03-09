from datetime import datetime
from threading import Lock
from typing import Dict, List


class HODTracker:
    """
    Tracks all symbols' live % change relative to previous close or baseline price.
    Detects and records new High-of-Day (HOD) levels.
    """

    def __init__(self):
        # Each entry: { symbol: { "base": float, "last": float, "hod": float, "change_pct": float } }
        self.data: Dict[str, Dict[str, float]] = {}
        self.lock = Lock()

    def set_base_price(self, symbol: str, base_price: float):
        """Set baseline price (previous close or fallback)."""
        with self.lock:
            if symbol not in self.data:
                self.data[symbol] = {
                    "base": base_price,
                    "last": base_price,
                    "hod": base_price,
                    "change_pct": 0.0
                }

    def update_price(self, symbol: str, price: float):
        """Update live price and % change. Detect new HOD if exceeded."""
        with self.lock:
            if symbol not in self.data or self.data[symbol]["base"] == 0:
                return False

            entry = self.data[symbol]
            base = entry["base"]
            entry["last"] = price
            entry["change_pct"] = ((price - base) / base) * 100

            new_high = False
            if price > entry["hod"]:
                entry["hod"] = price
                new_high = True
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 {symbol} hit new HOD ${price:.2f}")

            self.data[symbol] = entry
            return new_high

    def update_hod(self, symbol: str, price: float, change_pct: float, time: str = None):
        """Alias for FastAPI endpoint — same as update_price but accepts external data."""
        with self.lock:
            if symbol not in self.data:
                self.data[symbol] = {
                    "base": price,
                    "last": price,
                    "hod": price,
                    "change_pct": change_pct
                }
                return True

            entry = self.data[symbol]
            entry["last"] = price
            entry["change_pct"] = change_pct

            if price > entry["hod"]:
                entry["hod"] = price
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 {symbol} hit new HOD ${price:.2f}")
                return True

            return False

    def get_hod_list(self) -> List[Dict[str, float]]:
        """Return symbols sorted by % change descending."""
        with self.lock:
            hods = [
                {"symbol": s, **v}
                for s, v in self.data.items()
                if v.get("change_pct") is not None
            ]
            hods.sort(key=lambda x: x["change_pct"], reverse=True)
            return hods


# Global instance
hod_tracker = HODTracker()
