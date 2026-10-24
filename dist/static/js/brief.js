/* CryptoAI — market intelligence home: news pressure per asset + analysed news feed. */
(function () {
  const $ = id => document.getElementById(id);
  const NAMES = { BTC: "بیت‌کوین", ETH: "اتریوم", ALT: "آلت‌کوین‌ها", GOLD: "طلا", OIL: "نفت", SPX: "S&P 500", DXY: "دلار" };
  const STRENGTH = { 1: "ملایم", 2: "متوسط", 3: "قوی" };
  let BRIEF = null, selected = null, filter = "all";
  const prices = {};

  const fa = n => Number(n).toLocaleString("fa-IR");
  function ago(ts) {
    const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
    if (m < 1) return "همین الان"; if (m < 60) return fa(m) + " دقیقه پیش";
    const h = Math.floor(m / 60); if (h < 24) return fa(h) + " ساعت پیش";
    return fa(Math.floor(h / 24)) + " روز پیش";
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
        <div class="meter" title="فشار خبری از نزولی قوی تا صعودی قوی"><i style="left:calc(${(a.score + 100) / 2}% - 2px)"></i></div>
        <div class="drv"></div>`;
      b.querySelector(".nm").textContent = a.name;
      b.querySelector(".pressure").textContent = a.label;
      b.querySelector(".drv").textContent = top ? (top.d > 0 ? "↑ " : "↓ ") + top.t : "خبر اثرگذاری در ۲۴ ساعت اخیر نبوده";
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
    $("dr-title").textContent = a.name;
    const lb = $("dr-label"); lb.className = "pressure " + cls(a.score); lb.textContent = "فشار خبری: " + a.label;
    $("dr-summary").textContent = a.summary || (a.drivers.length
      ? `مهم‌ترین عامل امروز برای ${a.name}: ${a.drivers[0].t} — ${a.drivers[0].w}`
      : `در ۲۴ ساعت اخیر خبر اثرگذاری برای ${a.name} نبوده است.`);
    const list = $("dr-list"); list.textContent = "";
    a.drivers.forEach(d => {
      const el = document.createElement("div"); el.className = "driver";
      el.innerHTML = `<span class="ar ${d.d > 0 ? "up" : "down"}">${d.d > 0 ? "↑" : "↓"}</span><div><b></b><p></p><div class="meta"><span></span><a target="_blank" rel="noopener"></a></div></div>`;
      el.querySelector("b").textContent = d.t;
      el.querySelector("p").textContent = `${d.d > 0 ? "اثر صعودی" : "اثر نزولی"} ${STRENGTH[d.s] || ""}: ${d.w}`;
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
    if (selected) $("af-text").textContent = "خبرهایی که روی " + NAMES[selected] + " اثر دارند";
    if (!items.length) { const e = document.createElement("div"); e.className = "empty"; e.textContent = "فعلاً خبری در این دسته نیست."; box.append(e); return; }
    items.slice(0, 30).forEach(n => {
      const el = document.createElement("article"); el.className = "news" + (n.imp >= 3 ? " imp3" : "");
      el.innerHTML = `<div class="meta"></div><h3></h3><p></p><div class="chips"></div>`;
      const meta = el.querySelector(".meta");
      if (n.imp >= 3) { const b = document.createElement("span"); b.className = "badge hot"; b.textContent = "مهم"; meta.append(b); }
      if (n.kind === "official") { const b = document.createElement("span"); b.className = "badge official"; b.textContent = "منبع رسمی"; meta.append(b); }
      const t = document.createElement("span"); t.textContent = ago(n.ts) + (n.city ? " · " + n.city : ""); meta.append(t);
      const a = document.createElement("a"); a.target = "_blank"; a.rel = "noopener"; a.href = n.source.url; a.textContent = n.source.name; meta.append(a);
      el.querySelector("h3").textContent = n.t; el.querySelector("p").textContent = n.b;
      const chips = el.querySelector(".chips");
      const ims = (n.im || []).filter(x => x.d);
      ims.forEach(x => {
        const c = document.createElement("button"); c.type = "button"; c.className = "chip " + (x.d > 0 ? "up" : "down");
        c.textContent = `${NAMES[x.a] || x.a} ${x.d > 0 ? "↑" : "↓"} ${STRENGTH[x.s] || ""}`;
        c.onclick = () => openAsset(x.a);
        chips.append(c);
      });
      if (ims.length) {
        const more = document.createElement("button"); more.type = "button"; more.className = "more"; more.textContent = "چرا؟";
        const why = document.createElement("div"); why.className = "why"; why.hidden = true;
        ims.forEach(x => { const s = document.createElement("span"); s.innerHTML = "<b></b> "; s.querySelector("b").textContent = (NAMES[x.a] || x.a) + ":"; s.append(x.w); why.append(s); });
        more.onclick = () => { why.hidden = !why.hidden; more.textContent = why.hidden ? "چرا؟" : "بستن"; };
        el.append(more, why);
      }
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
      if (!j.assets || !j.assets.length) { $("updated").textContent = "در حال خواندن و تحلیل خبرهای تازه… چند ثانیه دیگر"; setTimeout(load, 8000); return; }
      BRIEF = j;
      const t = new Date(j.updated);
      $("updated").textContent = "آخرین تحلیل: " + new Intl.DateTimeFormat("fa-IR", { hour: "2-digit", minute: "2-digit" }).format(t);
      renderAssets(); renderFeed();
      if (selected) { const k = selected; selected = null; openAsset(k); }
    } catch (e) { $("updated").textContent = "اتصال برقرار نشد؛ دوباره تلاش می‌شود…"; setTimeout(load, 10000); }
  }
  async function loadMarkets() {
    try {
      const m = await (await fetch((window.API_BASE || "") + "/api/markets")).json();
      if (m.wti) prices.OIL = { txt: usd(m.wti.price), chg: m.wti.chg24h };
      if (m.spx) prices.SPX = { txt: m.spx.price.toLocaleString("en-US", { maximumFractionDigits: 2 }), chg: m.spx.chg24h };
      if (m.dxy) prices.DXY = { txt: m.dxy.price.toFixed(2), chg: m.dxy.chg24h };
      if (m.gold && !prices.GOLD) prices.GOLD = { txt: usd(m.gold.price), chg: m.gold.chg24h };
      if (m.dominance && m.dominance.others != null) prices.ALT = { txt: m.dominance.others.toFixed(1) + "% سهم بازار", chg: null };
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
    $("updated").textContent = "پیش‌نمایش";
  }
})();
