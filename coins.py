"""coins.py — names people type when they search: ticker, English name, Persian name."""
COINS = [
    ("BTC", "Bitcoin", "بیت‌کوین", ["بیتکوین", "بیت کوین", "btc", "xbt"]),
    ("ETH", "Ethereum", "اتریوم", ["اتر", "ether", "eth"]),
    ("USDT", "Tether", "تتر", ["usdt", "tether"]),
    ("BNB", "BNB", "بی‌ان‌بی", ["بایننس کوین", "binance coin"]),
    ("SOL", "Solana", "سولانا", []),
    ("XRP", "XRP", "ریپل", ["ripple"]),
    ("DOGE", "Dogecoin", "دوج‌کوین", ["دوج", "دوجکوین", "doge"]),
    ("TON", "Toncoin", "تون‌کوین", ["تون", "تونکوین", "toncoin"]),
    ("ADA", "Cardano", "کاردانو", []),
    ("TRX", "TRON", "ترون", ["tron"]),
    ("AVAX", "Avalanche", "آوالانچ", ["اوالانچ"]),
    ("LINK", "Chainlink", "چین‌لینک", ["چینلینک"]),
    ("DOT", "Polkadot", "پولکادات", []),
    ("POL", "Polygon", "پالیگان", ["matic", "ماتیک", "polygon"]),
    ("LTC", "Litecoin", "لایت‌کوین", ["لایتکوین"]),
    ("BCH", "Bitcoin Cash", "بیت‌کوین کش", ["بیتکوین کش"]),
    ("NEAR", "NEAR", "نیر", []),
    ("APT", "Aptos", "آپتوس", []),
    ("ARB", "Arbitrum", "آربیتروم", []),
    ("OP", "Optimism", "آپتیمیزم", []),
    ("SUI", "Sui", "سویی", []),
    ("PEPE", "Pepe", "پپه", []),
    ("SHIB", "Shiba Inu", "شیبا", ["شیبا اینو"]),
    ("ATOM", "Cosmos", "کازماس", ["کاسموس"]),
    ("INJ", "Injective", "اینجکتیو", []),
    ("FET", "Fetch.ai", "فچ", []),
    ("XLM", "Stellar", "استلار", []),
    ("UNI", "Uniswap", "یونی‌سواپ", ["یونیسواپ"]),
    ("AAVE", "Aave", "آوه", []),
    ("ETC", "Ethereum Classic", "اتریوم کلاسیک", []),
    ("FIL", "Filecoin", "فایل‌کوین", ["فایلکوین"]),
    ("HBAR", "Hedera", "هدرا", []),
    ("ICP", "Internet Computer", "اینترنت کامپیوتر", []),
    ("RENDER", "Render", "رندر", ["rndr"]),
    ("WLD", "Worldcoin", "ورلدکوین", []),
    ("NOT", "Notcoin", "نات‌کوین", ["ناتکوین"]),
    ("TAO", "Bittensor", "بیت‌تنسور", []),
    ("ENA", "Ethena", "اتنا", []),
    ("SEI", "Sei", "سی", []),
    ("TIA", "Celestia", "سلستیا", []),
    ("BONK", "Bonk", "بونک", []),
    ("WIF", "dogwifhat", "داگ‌ویف‌هت", []),
    ("PAXG", "PAX Gold", "پکس گلد", ["طلا توکن"]),
]

_INDEX = {}
for sym, en, fa, extra in COINS:
    for k in [sym, en, fa, fa.replace("‌", ""), *extra]:
        _INDEX[k.strip().lower()] = sym


def find(q: str) -> str | None:
    """Return a ticker for what the person typed, or a plausible ticker (2-10 letters/digits), or None."""
    k = (q or "").strip().lower().replace("/usdt", "").replace("usdt", "") if q and q.strip().lower() != "usdt" else (q or "").strip().lower()
    if k in _INDEX:
        return _INDEX[k]
    if k.replace("‌", "") in _INDEX:
        return _INDEX[k.replace("‌", "")]
    up = k.upper()
    if 2 <= len(up) <= 10 and up.isascii() and up.isalnum():
        return up
    return None


def names(sym: str):
    for s, en, fa, _ in COINS:
        if s == sym:
            return en, fa
    return sym, sym


def suggest(q: str, limit=8):
    k = (q or "").strip().lower()
    if not k:
        return []
    out = []
    for sym, en, fa, extra in COINS:
        hay = [sym.lower(), en.lower(), fa, fa.replace("‌", ""), *[e.lower() for e in extra]]
        if any(h.startswith(k) for h in hay):
            out.append({"sym": sym, "en": en, "fa": fa})
    return out[:limit]
