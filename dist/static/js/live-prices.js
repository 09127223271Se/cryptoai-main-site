/* CryptoAI — tick-by-tick prices straight from the exchange, in the visitor's browser.
   1) Binance market-data WebSocket (every trade update, ~1/s per coin)
   2) if Binance is unreachable: Coinbase WebSocket (USD pairs)
   3) if both fail: the site's /api/prices every 10 s
   Usage: LivePrices.subscribe(["BTC","ETH"], (sym, {price, chg24h, source, ts}) => {...}, onStatus) */
(function () {
  const listeners = [];
  let symbols = new Set(), ws = null, mode = null, pollTimer = null, retry = 0, statusCb = () => {};
  const last = {};

  function emit(sym, price, chg24h, source) {
    if (!isFinite(price)) return;
    last[sym] = { price, chg24h, source, ts: Date.now() };
    listeners.forEach(fn => { try { fn(sym, last[sym]); } catch (e) {} });
  }
  function status(s) { try { statusCb(s); } catch (e) {} }
  function stopAll() { if (ws) { ws.onclose = null; try { ws.close(); } catch (e) {} ws = null; } clearInterval(pollTimer); }

  function startBinance() {
    stopAll(); mode = "Binance";
    const streams = [...symbols].map(s => s.toLowerCase() + "usdt@ticker").join("/");
    let opened = false;
    try { ws = new WebSocket("wss://data-stream.binance.vision/stream?streams=" + streams); } catch (e) { return startCoinbase(); }
    const guard = setTimeout(() => { if (!opened) startCoinbase(); }, 6000);
    ws.onopen = () => { opened = true; clearTimeout(guard); retry = 0; status({ live: true, source: "Binance" }); };
    ws.onmessage = ev => {
      try { const d = JSON.parse(ev.data).data; emit(d.s.replace(/USDT$/, ""), +d.c, +d.P / 100, "Binance"); } catch (e) {}
    };
    ws.onclose = () => { clearTimeout(guard); if (opened && retry++ < 5) setTimeout(startBinance, 2000 * retry); else startCoinbase(); };
    ws.onerror = () => {};
  }

  function startCoinbase() {
    stopAll(); mode = "Coinbase";
    let opened = false;
    try { ws = new WebSocket("wss://ws-feed.exchange.coinbase.com"); } catch (e) { return startPoll(); }
    const guard = setTimeout(() => { if (!opened) startPoll(); }, 6000);
    ws.onopen = () => {
      opened = true; clearTimeout(guard); status({ live: true, source: "Coinbase" });
      ws.send(JSON.stringify({ type: "subscribe", product_ids: [...symbols].map(s => s + "-USD"), channels: ["ticker"] }));
    };
    ws.onmessage = ev => {
      try {
        const d = JSON.parse(ev.data); if (d.type !== "ticker") return;
        const p = +d.price, o = +d.open_24h; emit(d.product_id.replace(/-USD$/, ""), p, o ? p / o - 1 : NaN, "Coinbase");
      } catch (e) {}
    };
    ws.onclose = () => { clearTimeout(guard); if (!opened) startPoll(); else setTimeout(startCoinbase, 4000); };
    ws.onerror = () => {};
  }

  function startPoll() {
    stopAll(); mode = "poll";
    const tick = async () => {
      try {
        const j = await (await fetch((window.API_BASE || "") + "/api/prices?symbols=" + [...symbols].join(","))).json();
        if (!j.ok) { status({ live: false }); return; }
        status({ live: true, source: j.source + (window.LANG === "en" ? " (every 10 s)" : " (هر ۱۰ ثانیه)") });
        j.prices.forEach(p => emit(p.c, p.price, p.chg24h, p.source));
      } catch (e) { status({ live: false }); }
    };
    tick(); pollTimer = setInterval(tick, 10000);
  }

  window.LivePrices = {
    subscribe(list, fn, onStatus) {
      if (fn) listeners.push(fn);
      if (onStatus) statusCb = onStatus;
      const before = symbols.size;
      list.forEach(s => symbols.add(s.toUpperCase()));
      Object.entries(last).forEach(([s, v]) => fn && fn(s, v));
      const off = () => { const i = listeners.indexOf(fn); if (i >= 0) listeners.splice(i, 1); };
      if (window.SITE_MODE !== "server") { status({ live: false }); return off; }
      if (!mode || symbols.size !== before) startBinance();
      return off;
    },
    get(sym) { return last[sym]; }
  };
})();
