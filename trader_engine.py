"""trader_engine.py — offline-safe loader with structure/BOS tags."""
from __future__ import annotations

import urllib.request

_URL = (
    "https://raw.githubusercontent.com/09127223271Se/cryptoai-main-site/"
    "513e3d7bcc7cae62ee06b3b9d2b37b8ee84e5b88/trader_engine.py"
)

_src = None
_err = None
try:
    _src = urllib.request.urlopen(_URL, timeout=15).read().decode("utf-8")
except Exception as e:
    _err = e

if _src:
    _old = """    struct = 0
    if hh and hl:
        add(\"hh_hl\", \"ساختار صعودی (سقف و کف بالاتر)\", \"Bullish structure (HH+HL)\", 1); struct = 1
    elif lh and ll:
        add(\"lh_ll\", \"ساختار نزولی (سقف و کف پایین‌تر)\", \"Bearish structure (LH+LL)\", -1); struct = -1
    if bos_up:
        add(\"bos_up\", \"BOS صعودی (شکست سقف ساختار)\", \"Bullish BOS\", 1)
        struct = 1 if struct >= 0 else struct
    elif bos_dn:
        add(\"bos_dn\", \"BOS نزولی (شکست کف ساختار)\", \"Bearish BOS\", -1)
        struct = -1 if struct <= 0 else struct
    return struct
"""
    _new = """    struct = 0
    if hh and hl:
        add(\"hh_hl\", \"ساختار صعودی (سقف و کف بالاتر)\", \"Bullish structure (HH+HL)\", 1); struct = 1
    elif lh and ll:
        add(\"lh_ll\", \"ساختار نزولی (سقف و کف پایین‌تر)\", \"Bearish structure (LH+LL)\", -1); struct = -1
    elif hh or hl:
        add(\"hh_partial\", \"تمایل ساختاری صعودی\", \"Partial bullish structure\", 1); struct = 1
    elif lh or ll:
        add(\"lh_partial\", \"تمایل ساختاری نزولی\", \"Partial bearish structure\", -1); struct = -1
    else:
        add(\"struct_flat\", \"ساختار نامشخص / رنج\", \"Unclear / ranging structure\", 0)
    if bos_up:
        add(\"bos_up\", \"BOS صعودی (شکست سقف ساختار)\", \"Bullish BOS\", 1)
        struct = 1 if struct >= 0 else struct
    elif bos_dn:
        add(\"bos_dn\", \"BOS نزولی (شکست کف ساختار)\", \"Bearish BOS\", -1)
        struct = -1 if struct <= 0 else struct
    else:
        add(\"bos_none\", \"بدون BOS تازه\", \"No fresh BOS\", 0)
    return struct
"""
    if _old in _src:
        _src = _src.replace(_old, _new, 1)
    else:
        import re
        _src2 = re.sub(
            r"struct = 0\n    if hh and hl:.*?return struct\n",
            _new,
            _src,
            count=1,
            flags=re.S,
        )
        if _src2 != _src:
            _src = _src2
    _old2 = """    tags = []
    add = lambda id_, fa, en, d: tags.append({\"id\": id_, \"fa\": fa, \"en\": en, \"dir\": d})
    tight = width < med_w * 0.85
"""
    _new2 = """    tags = []
    add = lambda id_, fa, en, d: tags.append({\"id\": id_, \"fa\": fa, \"en\": en, \"dir\": d})
    struct = _structure_bias(H, L, last, n, rh, rl, add)
    tight = width < med_w * 0.85
"""
    if _old2 in _src:
        _src = _src.replace(_old2, _new2, 1)
    _old3 = "    struct = _structure_bias(H, L, last, n, rh, rl, add)\n    trend = 0\n"
    if _old3 in _src:
        _src = _src.replace(_old3, "    trend = 0\n", 1)
    exec(compile(_src, "trader_engine.py", "exec"), globals())
else:
    # Offline / network-fail fallback so gunicorn can still boot
    from flask import Blueprint

    trader_bp = Blueprint("trader", __name__)
    last_errors = {}
    DEFAULT_COINS = ["BTC", "ETH", "SOL", "XRP", "TON", "DOGE"]

    def analyze(sym, candles=None):
        return {
            "last": 0, "chg24h": 0, "res": 0, "sup": 0,
            "week_high": 0, "week_low": 0, "rsi": 50,
            "trend": 0, "bias": 0, "tags": [],
        }

    def simulate(a, horizon=24, paths=100, seed=7):
        p = float(a.get("last") or 0)
        return {
            "p05": p * 0.97, "p25": p * 0.99, "median": p,
            "p75": p * 1.01, "p95": p * 1.03,
            "touch": {
                "resistance": {"prob": 0.3},
                "support": {"prob": 0.3},
            },
        }

    def fetch_rows(sym, interval="1h", limit=100):
        return [], "offline"
