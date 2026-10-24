/* CryptoAI — market bar on every page: gold (live tick), oil, total crypto cap and dominance. */
(function () {
  const bar = document.getElementById("mbar");
  if (!bar || window.SITE_MODE !== "server") { if (bar) bar.hidden = true; return; }
  const ITEMS = [
    ["gold", "طلا · اونس"], ["wti", "نفت WTI"], ["brent", "نفت برنت"],
    ["total", "ارزش کل کریپتو"], ["btcd", "دامیننس BTC"], ["ethd", "دامیننس ETH"],
    ["usdtd", "دامیننس USDT"], ["usdcd", "دامیننس USDC"], ["stablesd", "دامیننس استیبل‌ها"], ["othersd", "دامیننس Others"]
  ];
  const el = {};
  ITEMS.forEach(([k, label]) => {
    const s = document.createElement("span"); s.className = "mb"; s.dataset.k = k;
    s.innerHTML = `<i></i><b class="num">…</b><small class="num"></small>`;
    s.querySelector("i").textContent = label; bar.append(s); el[k] = s;
  });
  const usd = (p, d = 2) => "$" + p.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const big = v => v >= 1e12 ? "$" + (v / 1e12).toFixed(3) + "T" : "$" + (v / 1e9).toFixed(1) + "B";
  function set(k, val, chg, title) {
    const s = el[k]; if (!s) return;
    if (val == null) { s.hidden = true; return; }
    s.hidden = false;
    const b = s.querySelector("b"), prev = parseFloat(b.dataset.v || "NaN"), num = typeof val === "number" ? val : NaN;
    b.textContent = typeof val === "string" ? val : val; if (!isNaN(num)) b.dataset.v = num;
    const sm = s.querySelector("small");
    if (chg != null && isFinite(chg)) { sm.textContent = (chg >= 0 ? "+" : "") + (chg * 100).toFixed(2) + "%"; sm.style.color = chg >= 0 ? "var(--up)" : "var(--down)"; }
    else sm.textContent = "";
    if (title) s.title = title;
  }
  let goldLive = false;
  async function load() {
    try {
      const m = await (await fetch((window.API_BASE || "") + "/api/markets")).json();
      if (m.gold && !goldLive) set("gold", usd(m.gold.price), m.gold.chg24h, m.gold.source);
      if (m.wti) set("wti", usd(m.wti.price), m.wti.chg24h, m.wti.source + " · قراردادهای آتی، تأخیر بورس حدود ۱۰ دقیقه"); else set("wti", null);
      if (m.brent) set("brent", usd(m.brent.price), m.brent.chg24h, m.brent.source + " · قراردادهای آتی، تأخیر بورس حدود ۱۰ دقیقه"); else set("brent", null);
      const d = m.dominance;
      if (d) {
        const pc = v => v == null ? null : v.toFixed(2) + "%";
        set("total", big(d.total_mcap), d.total_chg24h, d.source);
        set("btcd", pc(d.btc), null, d.source); set("ethd", pc(d.eth), null, d.source);
        set("usdtd", pc(d.usdt), null, d.source); set("usdcd", pc(d.usdc), null, d.source);
        set("stablesd", pc(d.stables), null, "USDT + USDC · " + d.source); set("othersd", pc(d.others), null, "بیرون از ۱۰ کوین بزرگ · " + d.source);
      }
      window.MARKETS = m;
    } catch (e) {}
  }
  load(); setInterval(() => { if (!document.hidden) load(); }, 60000);
  // gold tick by tick through the tokenised-gold market (PAXG ≈ 1 troy ounce)
  if (window.LivePrices) LivePrices.subscribe(["PAXG"], (sym, v) => {
    if (sym !== "PAXG") return;
    goldLive = true;
    const b = el.gold.querySelector("b"), prev = parseFloat(b.dataset.v || "NaN");
    set("gold", usd(v.price), v.chg24h, "لحظه‌ای · PAXG (توکن طلا، معادل یک اونس) · " + v.source);
    b.dataset.v = v.price;
    if (isFinite(prev) && prev !== v.price) { b.style.color = v.price > prev ? "var(--up)" : "var(--down)"; setTimeout(() => { b.style.color = ""; }, 900); }
  });
})();
