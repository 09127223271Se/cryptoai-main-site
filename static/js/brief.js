/* CryptoAI — market intelligence home: news pressure per asset + analysed news feed. */
(function () {
  const $ = id => document.getElementById(id);
  const EN = window.LANG === "en";
  const NAMES = EN ? { BTC: "Bitcoin", ETH: "Ethereum", ALT: "Altcoins", GOLD: "Gold", OIL: "Oil", SPX: "S&P 500", DXY: "US Dollar" }
                   : { BTC: "بیت‌کوین", ETH: "اتریوم", ALT: "آلت‌کوین‌ها", GOLD: "طلا", OIL: "نفت", SPX: "S&P 500", DXY: "دلار" };
  const STRENGTH = EN ? { 1: "weak", 2: "moderate", 3: "strong" } : { 1: "ملایم", 2: "متوسط", 3: "قوی" };
  const S = EN ? {
    now: "just now", min: " min ago", hr: " h ago", day: " d ago", meter: "News pressure from strong bearish to strong bullish",
    noDrv: "No market-moving news in the last 24h", press: "News pressure: ", topToday: (n, t, w) => `Today's main driver for ${n}: ${t} — ${w}`,
    none24: n => `No market-moving news for ${n} in the last 24 hours.`, upE: "Bullish effect", dnE: "Bearish effect",
    affects: n => "News that moves " + n, empty: "No news in this category yet.", hot: "Important", official: "Official source",
    why: "Why?", close: "Close", pos: "positive", neg: "negative", noEffect: "No clear effect on the markets",
    filterBy: n => "Show all news that moves " + n, reading: "Reading and analysing fresh news… a few seconds", last: "Last analysis: ",
    retry: "Connection failed; retrying…", share: "% market share", preview: "Preview", loc: "en-GB"
  } : {
    now: "همین الان", min: " دقیقه پیش", hr: " ساعت پیش", day: " روز پیش", meter: "فشار خبری از نزولی قوی تا صعودی قوی",
    noDrv: "خبر اثرگذاری در ۲۴ ساعت اخیر نبوده", press: "فشار خبری: ", topToday: (n, t, w) => `مهم‌ترین عامل امروز برای ${n}: ${t} — ${w}`,
    none24: n => `در ۲۴ ساعت اخیر خبر اثرگذاری برای ${n} نبوده است.`, upE: "اثر صعودی", dnE: "اثر نزولی",
    affects: n => "خبرهایی که روی " + n + " اثر دارند", empty: "فعلاً خبری در این دسته نیست.", hot: "مهم", official: "منبع رسمی",
    why: "چرا؟", close: "بستن", pos: "اثر مثبت", neg: "اثر منفی", noEffect: "اثر روشنی روی بازارها ندارد",
    filterBy: n => "همهٔ خبرهای اثرگذار روی " + n, reading: "در حال خواندن و تحلیل خبرهای تازه… چند ثانیه دیگر", last: "آخرین تحلیل: ",
    retry: "اتصال برقرار نشد؛ دوباره تلاش می‌شود…", share: "% سهم بازار", preview: "پیش‌نمایش", loc: "fa-IR"
  };
  // language-specific fields of the data
  const T = n => EN ? (n.en_t || n.t) : n.t, B = n => EN ? (n.en_b || "") : n.b, Wy = x => EN ? (x.we || "") : x.w;
  const AN = a => EN ? (a.name_en || a.name) : a.name, AL = a => EN ? (a.label_en || a.label) : a.label;
  const AS = a => EN ? (a.summary_en || "") : a.summary, CITY = n => EN ? n.city_en : n.city;
  let BRIEF = null, selected = null, filter = "all";
  const prices = {};

  const fa = n => Number(n).toLocaleString(S.loc);
  function ago(ts) {
    const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
    if (m < 1) return S.now; if (m < 60) return fa(m) + S.min;
    const h = Math.floor(m / 60); if (h < 24) return fa(h) + S.hr;
    return fa(Math.floor(h / 24)) + S.day;
  }
  const cls = s => s >= 12 ? "up" : s <= -12 ? "down" : "flat";
  const usd = (p, d = 2) => "$" + p.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

  /* ---------- asset cards ---------- */
  function priceLine(key) {
    const p = prices[key]; if (!p) return "";
    const ch = p.chg != null && isFinite(p.chg) ? `<small class="num" style="color:${p.chg >= 0 ? "var(--up)" : "var(--down)"}">${p.chg >= 0 ? "+" : ""}${(p.chg * 100).toFixed(2)}%</small>` : "";
    return `<b class="num">${p.txt}</b>${ch}`;
  }
  function renderAssets() {
    const box = $("assets"); box.textContent = "";
    (BRIEF.assets || []).forEach(a => {
      const b = document.createElement("button"); b.type = "button"; b.className = "acard"; b.dataset.k = a.key;
      b.setAttribute("aria-pressed", selected === a.key ? "true" : "false");
      const top = a.drivers[0];
      b.innerHTML = `<div class="top"><span class="nm"></span><span class="pressure ${cls(a.score)}"></span></div>
        <div class="px" data-px="${a.key}">${priceLine(a.key)}</div>
        <div class="meter" title="${S.meter}"><i style="left:calc(${(a.score + 100) / 2}% - 2px)"></i></div>
        <div class="drv"></div>`;
      b.querySelector(".nm").textContent = AN(a);
      b.querySelector(".pressure").textContent = AL(a);
      b.querySelector(".drv").textContent = top ? (top.d > 0 ? "↑ " : "↓ ") + T({ t: top.t, en_t: top.en_t }) : S.noDrv;
      b.onclick = () => openAsset(a.key);
      box.append(b);
    });
  }
  function updatePrices() {
    document.querySelectorAll("[data-px]").forEach(el => { el.innerHTML = priceLine(el.dataset.px); });
  }

  /* ---------- drawer ---------- */
  function openAsset(key) {
    if (selected === key) { closeAsset(); return; }
    selected = key;
    const a = BRIEF.assets.find(x => x.key === key); if (!a) return;
    $("dr-title").textContent = AN(a);
    const lb = $("dr-label"); lb.className = "pressure " + cls(a.score); lb.textContent = S.press + AL(a);
    $("dr-summary").textContent = AS(a) || (a.drivers.length
      ? S.topToday(AN(a), T(a.drivers[0]), Wy(a.drivers[0]))
      : S.none24(AN(a)));
    const list = $("dr-list"); list.textContent = "";
    a.drivers.forEach(d => {
      const el = document.createElement("div"); el.className = "driver";
      el.innerHTML = `<span class="ar ${d.d > 0 ? "up" : "down"}">${d.d > 0 ? "↑" : "↓"}</span><div><b></b><p></p><div class="meta"><span></span><a target="_blank" rel="noopener"></a></div></div>`;
      el.querySelector("b").textContent = T(d);
      el.querySelector("p").textContent = `${d.d > 0 ? S.upE : S.dnE} ${STRENGTH[d.s] || ""}: ${Wy(d)}`;
      el.querySelector(".meta span").textContent = ago(d.ts);
      const l = el.querySelector("a"); l.textContent = d.source; l.href = d.url;
      list.append(el);
    });
    $("drawer").hidden = false;
    renderAssets(); renderFeed();
    $("drawer").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
  }
  function closeAsset() { selected = null; $("drawer").hidden = true; renderAssets(); renderFeed(); }
  $("dr-close").onclick = closeAsset;
  $("af-clear").onclick = closeAsset;

  /* ---------- feed ---------- */
  function renderFeed() {
    const box = $("feed"); box.textContent = "";
    let items = BRIEF.feed || [];
    if (filter === "top") items = items.filter(n => n.imp >= 2);
    if (filter === "crypto") items = items.filter(n => n.kind === "crypto");
    if (filter === "macro") items = items.filter(n => n.kind !== "crypto");
    if (selected) items = items.filter(n => (n.im || []).some(x => x.a === selected && x.d));
    $("asset-filter").hidden = !selected;
    if (selected) $("af-text").textContent = S.affects(NAMES[selected]);
    if (!items.length) { const e = document.createElement("div"); e.className = "empty"; e.textContent = S.empty; box.append(e); return; }
    items.slice(0, 30).forEach(n => {
      const el = document.createElement("article"); el.className = "news" + (n.imp >= 3 ? " imp3" : "");
      el.innerHTML = `<div class="meta"></div><h3></h3><p></p><div class="chips"></div>`;
      const meta = el.querySelector(".meta");
      if (n.imp >= 3) { const b = document.createElement("span"); b.className = "badge hot"; b.textContent = S.hot; meta.append(b); }
      if (n.kind === "official") { const b = document.createElement("span"); b.className = "badge official"; b.textContent = S.official; meta.append(b); }
      const t = document.createElement("span"); t.textContent = ago(n.ts) + (CITY(n) ? " · " + CITY(n) : ""); meta.append(t);
      const a = document.createElement("a"); a.target = "_blank"; a.rel = "noopener"; a.href = n.source.url; a.textContent = n.source.name; meta.append(a);
      el.querySelector("h3").textContent = T(n); el.querySelector("p").textContent = B(n);
      // the effect of this story, always visible: one small coloured line per market
      const eff = el.querySelector(".chips"); eff.className = "effects";
      const ims = (n.im || []).filter(x => x.d);
      if (!ims.length) {
        const e = document.createElement("span"); e.className = "eff none"; e.textContent = S.noEffect; eff.append(e);
      }
      ims.forEach(x => {
        const up = x.d > 0;
        const line = document.createElement("button"); line.type = "button"; line.className = "eff " + (up ? "up" : "down");
        line.title = S.filterBy(NAMES[x.a] || x.a);
        line.innerHTML = `<span class="ar">${up ? "▲" : "▼"}</span><b></b><span class="tag"></span><span class="rs"></span>`;
        line.querySelector("b").textContent = NAMES[x.a] || x.a;
        line.querySelector(".tag").textContent = EN ? `${STRENGTH[x.s] || ""} ${up ? S.pos : S.neg} effect` : `${up ? S.pos : S.neg} ${STRENGTH[x.s] || ""}`;
        const r = Wy(x); line.querySelector(".rs").textContent = r ? "— " + r : "";
        line.onclick = () => openAsset(x.a);
        eff.append(line);
      });
      box.append(el);
    });
  }
  document.querySelectorAll("#filters button").forEach(b => b.onclick = () => {
    filter = b.dataset.f;
    document.querySelectorAll("#filters button").forEach(x => x.setAttribute("aria-pressed", x === b ? "true" : "false"));
    renderFeed();
  });

  /* ---------- data ---------- */
  async function load() {
    try {
      const j = await (await fetch((window.API_BASE || "") + "/api/brief")).json();
      if (!j.assets || !j.assets.length) { $("updated").textContent = S.reading; setTimeout(load, 8000); return; }
      BRIEF = j;
      const t = new Date(j.updated);
      $("updated").textContent = S.last + new Intl.DateTimeFormat(S.loc, { hour: "2-digit", minute: "2-digit" }).format(t);
      renderAssets(); renderFeed();
      if (selected) { const k = selected; selected = null; openAsset(k); }
    } catch (e) { $("updated").textContent = S.retry; setTimeout(load, 10000); }
  }
  async function loadMarkets() {
    try {
      const m = await (await fetch((window.API_BASE || "") + "/api/markets")).json();
      if (m.wti) prices.OIL = { txt: usd(m.wti.price), chg: m.wti.chg24h };
      if (m.spx) prices.SPX = { txt: m.spx.price.toLocaleString("en-US", { maximumFractionDigits: 2 }), chg: m.spx.chg24h };
      if (m.dxy) prices.DXY = { txt: m.dxy.price.toFixed(2), chg: m.dxy.chg24h };
      if (m.gold && !prices.GOLD) prices.GOLD = { txt: usd(m.gold.price), chg: m.gold.chg24h };
      if (m.dominance && m.dominance.others != null) prices.ALT = { txt: m.dominance.others.toFixed(1) + S.share, chg: null };
      updatePrices();
    } catch (e) {}
  }
  if (window.SITE_MODE === "server") {
    load(); setInterval(() => { if (!document.hidden) load(); }, 120000);
    loadMarkets(); setInterval(() => { if (!document.hidden) loadMarkets(); }, 60000);
    if (window.LivePrices) LivePrices.subscribe(["BTC", "ETH", "PAXG"], (sym, v) => {
      const key = sym === "PAXG" ? "GOLD" : sym;
      if (!NAMES[key]) return;
      prices[key] = { txt: usd(v.price), chg: v.chg24h };
      const el = document.querySelector(`[data-px="${key}"]`); if (el) el.innerHTML = priceLine(key);
    });
  } else {
    $("updated").textContent = S.preview;
  }
})();
