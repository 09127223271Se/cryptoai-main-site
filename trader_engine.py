"""trader_engine.py — load embedded engine from sibling data file (no network)."""
from __future__ import annotations
from pathlib import Path
import base64, zlib

last_errors = {}
DEFAULT_COINS = ["BTC", "ETH", "SOL", "XRP", "TON", "DOGE"]
trader_bp = None

_data = Path(__file__).with_name("trader_engine.b64")
try:
    _SRC = zlib.decompress(base64.b64decode(_data.read_text().strip())).decode("utf-8")
    exec(compile(_SRC, "trader_engine.py", "exec"), globals())
except Exception as e:
    last_errors["load"] = str(e)[:300]
    from flask import Blueprint
    trader_bp = Blueprint("trader", __name__)
    def analyze(sym, candles=None):
        return {"last": 0, "chg24h": 0, "res": 0, "sup": 0, "week_high": 0, "week_low": 0,
                "rsi": 50, "trend": 0, "bias": 0, "tags": []}
    def simulate(a, horizon=24, paths=100, seed=7):
        p = float(a.get("last") or 0)
        return {"p05": p*0.97, "p25": p*0.99, "median": p, "p75": p*1.01, "p95": p*1.03,
                "touch": {"resistance": {"prob": 0.3}, "support": {"prob": 0.3}}}
    def fetch_rows(sym, interval="1h", limit=100):
        return [], "offline"

if "last_errors" not in globals() or not isinstance(globals().get("last_errors"), dict):
    last_errors = {}
