"""
markets.py — macro + market-structure numbers for the market bar.

  Gold   : spot ounce via tokenised gold PAXG (Binance/OKX, live) + COMEX gold futures (Yahoo → Stooq) as reference
  Oil    : WTI (CL=F) and Brent (BZ=F) futures — Yahoo Finance, Stooq as fallback (exchange delay ~10 min)
  Crypto : total market cap, BTC / ETH / USDT / USDC / stablecoin / Others dominance — CoinGecko, CoinPaprika as fallback
All free, no keys. Cached for 60 s so the sources are not hammered.
"""
from __future__ import annotations

import csv
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; CryptoAI/1.0)"}
_cache = {"at": 0.0, "data": None}
_lock = threading.Lock()
TTL = 60


def _yahoo(sym):
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params={"range": "5d", "interval": "1d"},
                     headers=UA, timeout=10)
    r.raise_for_status()
    m = r.json()["chart"]["result"][0]["meta"]
    price, prev = float(m["regularMarketPrice"]), float(m.get("chartPreviousClose") or m.get("previousClose") or 0)
    return {"price": price, "chg24h": (price / prev - 1) if prev else None, "source": "Yahoo Finance"}


def _stooq(sym):
    r = requests.get("https://stooq.com/q/l/", params={"s": sym, "f": "sd2t2ohlcv", "h": "", "e": "csv"}, headers=UA, timeout=10)
    r.raise_for_status()
    row = next(csv.DictReader(io.StringIO(r.text)))
    close, open_ = float(row["Close"]), float(row["Open"])
    return {"price": close, "chg24h": (close / open_ - 1) if open_ else None, "source": "Stooq"}


def _first(*fns):
    for fn in fns:
        try:
            return fn()
        except Exception:
            continue
    return None


def _paxg():
    import trader_engine
    rows, src = trader_engine.fetch_rows("PAXG", "1h", 25)
    return {"price": rows[-1][4], "chg24h": rows[-1][4] / rows[0][4] - 1, "source": f"PAXG · {src}"}


def _dominance_coingecko():
    r = requests.get("https://api.coingecko.com/api/v3/global", headers=UA, timeout=10)
    r.raise_for_status()
    d = r.json()["data"]
    pct = d["market_cap_percentage"]
    btc, eth, usdt, usdc = (float(pct.get(k, 0)) for k in ("btc", "eth", "usdt", "usdc"))
    top = sum(float(v) for v in pct.values())   # CoinGecko lists the top 10 coins
    return {
        "total_mcap": float(d["total_market_cap"]["usd"]),
        "total_chg24h": float(d.get("market_cap_change_percentage_24h_usd") or 0) / 100,
        "btc": btc, "eth": eth, "usdt": usdt, "usdc": usdc, "stables": usdt + usdc,
        "others": max(0.0, 100 - top), "source": "CoinGecko",
    }


def _dominance_paprika():
    g = requests.get("https://api.coinpaprika.com/v1/global", headers=UA, timeout=10)
    g.raise_for_status()
    g = g.json()
    total = float(g["market_cap_usd"])

    def mcap(cid):
        t = requests.get(f"https://api.coinpaprika.com/v1/tickers/{cid}", headers=UA, timeout=10)
        t.raise_for_status()
        return float(t.json()["quotes"]["USD"]["market_cap"])
    eth, usdt, usdc = mcap("eth-ethereum"), mcap("usdt-tether"), mcap("usdc-usd-coin")
    btc = float(g["bitcoin_dominance_percentage"])
    return {
        "total_mcap": total, "total_chg24h": float(g.get("market_cap_change_24h") or 0) / 100,
        "btc": btc, "eth": eth / total * 100, "usdt": usdt / total * 100, "usdc": usdc / total * 100,
        "stables": (usdt + usdc) / total * 100, "others": None, "source": "CoinPaprika",
    }


def _build():
    out = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    jobs = {
        "gold": lambda: _first(_paxg),
        "gold_futures": lambda: _first(lambda: _yahoo("GC=F"), lambda: _stooq("gc.f")),
        "wti": lambda: _first(lambda: _yahoo("CL=F"), lambda: _stooq("cl.f")),
        "brent": lambda: _first(lambda: _yahoo("BZ=F"), lambda: _stooq("cb.f")),
        "dominance": lambda: _first(_dominance_coingecko, _dominance_paprika),
    }
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {k: ex.submit(fn) for k, fn in jobs.items()}
        for k, f in futs.items():
            out[k] = f.result()
    if out["gold"] is None and out["gold_futures"]:
        out["gold"] = out["gold_futures"]
    out["ok"] = any(out.get(k) for k in ("gold", "wti", "brent", "dominance"))
    return out


def get_markets() -> dict:
    with _lock:
        fresh = _cache["data"] is not None and time.time() - _cache["at"] < TTL
        if fresh:
            return _cache["data"]
    data = _build()
    with _lock:
        if data["ok"] or _cache["data"] is None:
            _cache.update(at=time.time(), data=data)
        return _cache["data"]


def hint() -> str:
    """Short English line for AI prompts."""
    try:
        m = get_markets()
    except Exception:
        return ""
    parts = []
    if m.get("gold"):
        parts.append(f"gold {m['gold']['price']:,.0f} USD/oz")
    if m.get("wti"):
        parts.append(f"WTI oil {m['wti']['price']:.2f}")
    if m.get("brent"):
        parts.append(f"Brent {m['brent']['price']:.2f}")
    d = m.get("dominance")
    if d:
        parts.append(f"BTC dominance {d['btc']:.1f}%, ETH {d['eth']:.1f}%, USDT {d['usdt']:.1f}%, total crypto cap {d['total_mcap'] / 1e12:.2f}T USD ({d['total_chg24h'] * 100:+.1f}% 24h)")
    return "; ".join(parts)
