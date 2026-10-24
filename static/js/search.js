/* CryptoAI — search: any coin (live chart analysis) and any word in the analysed news. Persian and English. */
(() => {
  const $ = id => document.getElementById(id);
  const EN = window.LANG === "en";
  const NAMES = EN ? { BTC: "Bitcoin", ETH: "Ethereum", ALT: "Altcoins", GOLD: "Gold", OIL: "Oil", SPX: "S&P 500", DXY: "US Dollar" }
                   : { BTC: "بیت‌کوین", ETH: "اتریوم", ALT: "آلت‌کوین‌ها", GOLD: "طلا", OIL: "نفت", SPX: "S&P 500", DXY: "دلار" };
  const STRENGTH = EN ? { 1: "weak", 2: "moderate", 3: "strong" } : { 1: "ملایم", 2: "متوسط", 3: "قوی" };
  const S = EN ? {
    loading: "Searching…", none: q => `No coin or news found for “${q}”.`, news: (n, q) => `${n} stories about “${q}”`, nonews: q => `No recent stories about “${q}”.`,
    coinErr: s => `No live market found for ${s}/USDT on the exchanges we read.`, stable: "A stablecoin pegged to the US dollar (≈ $1). No chart analysis needed.",
    trend: "Hourly trend", up: "up", down: "down", range: "flat", rsi: "RSI 14", res: "Resistance", sup: "Support", touch: p => `${p}% chance to touch in 24h`,
    r50: "Likely 24h range (50%)", r90: "Wider 24h range (90%)", week: "7-day high / low", newsP: k => `News pressure on ${k}`,
    pos: "positive", neg: "negative", noEffect: "No clear effect on the markets", hot: "Important", official: "Official source",
    note: "Probabilities from 4,000 simulated price paths at today's volatility, plus chart patterns and news pressure. Not a buy/sell signal and not an entry point.",
    now: "just now", min: " min ago", hr: " h ago", day: " d ago", chart: "Last 72 hours · shaded cone = likely range for the next 24 hours", loc: "en-GB"
  } : {
    loading: "در حال جستجو…", none: q => `برای «${q}» کوین یا خبری پیدا نشد.`, news: (n, q) => `${n} خبر دربارهٔ «${q}»`, nonews: q => `خبر تازه‌ای دربارهٔ «${q}» نیست.`,
    coinErr: s => `بازار زنده‌ای برای ${s}/USDT در صرافی‌هایی که می‌خوانیم پیدا نشد.`, stable: "استیبل‌کوین متصل به دلار آمریکا (حدود ۱ دلار)؛ تحلیل چارت لازم ندارد.",
    trend: "روند ساعتی", up: "صعودی", down: "نزولی", range: "خنثی", rsi: "RSI ۱۴", res: "مقاومت", sup: "حمایت", touch: p => `احتمال لمس در ۲۴ ساعت ${p}٪`,
    r50: "محدودهٔ محتمل ۲۴ ساعت (۵۰٪)", r90: "محدودهٔ وسیع‌تر ۲۴ ساعت (۹۰٪)", week: "سقف / کف ۷ روز", newsP: k => `فشار خبری روی ${k}`,
    pos: "اثر مثبت", neg: "اثر منفی", noEffect: "اثر روشنی روی بازارها ندارد", hot: "مهم", official: "منبع رسمی",
    note: "احتمال‌ها از ۴۰۰۰ مسیر شبیه‌سازی‌شدهٔ قیمت با نوسان امروز، به‌همراه الگوهای چارت و فشار خبری به دست آمده‌اند. سیگنال خرید یا فروش و نقطهٔ ورود نیست.",
    now: "همین الان", min: " دقیقه پیش", hr: " ساعت پیش", day: " روز پیش", chart: "۷۲ ساعت اخیر · قیف رنگی = محدودهٔ محتمل ۲۴ ساعت آینده", loc: "fa-IR"
  };
  const usd = v => v >= 100 ? "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : v >= 1 ? "$" + v.toFixed(3) : "$" + v.toPrecision(4);
  const pct = v => (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function ago(ts) {
    const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
    if (m < 1) return S.now; if (m < 60) return m.toLocaleString(S.loc) + S.min;
    const h = Math.floor(m / 60); if (h < 24) return h.toLocaleString(S.loc) + S.hr;
    return Math.floor(h / 24).toLocaleString(S.loc) + S.day;
  }
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  /* ---------- coin card ---------- */
  function drawChart(cv, c) {
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    const x = cv.getContext("2d"); x.scale(dpr, dpr);
    const k = c.candles, n = k.length;
    const vals = k.flatMap(r => [r[2], r[3]]).concat([c.p05, c.p95, c.res, c.sup]);
    let lo = Math.min(...vals), hi = Math.max(...vals); const pad = (hi - lo) * .06 || 1; lo -= pad; hi += pad;
    const L = 10, Rk = W - 120, Rz = W - 60, T = 14, B = H - 18;
    const Y = v => B - (v - lo) / (hi - lo) * (B - T), step = (Rk - L) / n;
    const up = css("--up"), dn = css("--down"), line = css("--line"), muted = css("--muted"), brand = css("--brand");
    x.strokeStyle = line; x.lineWidth = 1;
    for (let i = 0; i < 4; i++) { const y = T + i * (B - T) / 3; x.beginPath(); x.moveTo(L, y); x.lineTo(Rz, y); x.stroke(); }
    const zc = c.verdict.startsWith("up") ? up : c.verdict.startsWith("down") ? dn : brand;
    const px = Rk + 4, py = Y(c.price);
    x.globalAlpha = .18; x.fillStyle = zc; x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, Y(c.p95)); x.lineTo(Rz, Y(c.p05)); x.fill();
    x.globalAlpha = .38; x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, Y(c.p75)); x.lineTo(Rz, Y(c.p25)); x.fill();
    x.globalAlpha = 1; x.strokeStyle = zc; x.lineWidth = 2; x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, Y(c.p50)); x.stroke();
    [[c.res, dn], [c.sup, up]].forEach(([v, col]) => {
      x.setLineDash([6, 6]); x.strokeStyle = col; x.lineWidth = 1.5; x.beginPath(); x.moveTo(L, Y(v)); x.lineTo(Rz, Y(v)); x.stroke(); x.setLineDash([]);
      x.fillStyle = col; x.font = "600 11px " + css("--f-mono"); x.textAlign = "left"; x.fillText(usd(v), Rz + 4, Y(v) + 4);
    });
    k.forEach((r, i) => {
      const [, o, h, l, cl] = r, cx = L + i * step + step / 2, col = cl >= o ? up : dn;
      x.strokeStyle = col; x.lineWidth = 1; x.beginPath(); x.moveTo(cx, Y(h)); x.lineTo(cx, Y(l)); x.stroke();
      x.fillStyle = col; const t = Y(Math.max(o, cl)), b = Y(Math.min(o, cl)); x.fillRect(cx - step * .35, t, step * .7, Math.max(1, b - t));
    });
  }
  function renderCoin(c) {
    const box = $("coin"); box.textContent = ""; box.hidden = false;
    const top = el("div", "top");
    top.append(el("span", "nm", EN ? c.en : c.fa), el("span", "sym", c.sym + "/USDT"));
    if (c.stable) { top.append(el("span", "px num", "$1.00")); box.append(top, el("p", "note", S.stable)); return; }
    const px = el("span", "px num", usd(c.price)); const ch = el("span", "num " + (c.ch24 >= 0 ? "up" : "down"), pct(c.ch24) + " 24h");
    const vd = el("span", "vd", EN ? c.verdict_en : c.verdict_fa);
    vd.style.color = c.verdict.startsWith("up") ? css("--up") : c.verdict.startsWith("down") ? css("--down") : c.verdict === "conflict" ? css("--signal") : css("--mixed");
    top.append(px, ch, vd); box.append(top);
    const cv = el("canvas"); cv.setAttribute("aria-label", S.chart); box.append(cv, el("p", "note", S.chart));
    const st = el("div", "cstats");
    const add = (label, val, cls) => { const d = el("div"); d.append(el("small", null, label)); const b = el("b", "num " + (cls || ""), val); d.append(b); st.append(d); return d; };
    add(S.trend, S[c.trend], c.trend === "up" ? "up" : c.trend === "down" ? "down" : "");
    add(S.newsP(NAMES[c.news_key] || c.news_key), (c.news_score > 0 ? "+" : "") + c.news_score, c.news_score >= 12 ? "up" : c.news_score <= -12 ? "down" : "");
    add(S.rsi, c.rsi.toFixed(0));
    add(S.res, usd(c.res), "down").append(el("small", null, S.touch(Math.round(c.touch_res * 100))));
    add(S.sup, usd(c.sup), "up").append(el("small", null, S.touch(Math.round(c.touch_sup * 100))));
    add(S.r50, usd(c.p25) + " – " + usd(c.p75));
    add(S.r90, usd(c.p05) + " – " + usd(c.p95));
    add(S.week, usd(c.week_high) + " / " + usd(c.week_low));
    box.append(st);
    const tags = EN ? c.tags_en : c.tags;
    if (tags && tags.length) { const tg = el("div", "ctags"); tags.forEach(t => tg.append(el("span", "chip", t))); box.append(tg); }
    box.append(el("p", "note", S.note));
    requestAnimationFrame(() => drawChart(cv, c));
    addEventListener("resize", () => drawChart(cv, c), { once: true });
  }

  /* ---------- news ---------- */
  function renderNews(list, q) {
    const box = $("feed"); box.textContent = "";
    $("results").hidden = false;
    $("r-title").textContent = list.length ? S.news(list.length.toLocaleString(S.loc), q) : S.nonews(q);
    list.forEach(n => {
      const a = el("article", "news" + (n.imp >= 3 ? " imp3" : ""));
      const meta = el("div", "meta");
      if (n.imp >= 3) meta.append(el("span", "badge hot", S.hot));
      if (n.kind === "official") meta.append(el("span", "badge official", S.official));
      const city = EN ? n.city_en : n.city;
      meta.append(el("span", null, ago(n.ts) + (city ? " · " + city : "")));
      const s = el("a", null, n.source.name); s.href = n.source.url; s.target = "_blank"; s.rel = "noopener"; meta.append(s);
      a.append(meta, el("h3", null, EN ? (n.en_t || n.t) : n.t), el("p", null, EN ? (n.en_b || "") : (n.b || "")));
      const eff = el("div", "effects");
      const ims = (n.im || []).filter(x => x.d);
      if (!ims.length) eff.append(el("span", "eff none", S.noEffect));
      ims.forEach(x => {
        const upx = x.d > 0, ln = el("div", "eff " + (upx ? "up" : "down"));
        ln.append(el("span", "ar", upx ? "▲" : "▼"), el("b", null, NAMES[x.a] || x.a),
          el("span", "tag", EN ? `${STRENGTH[x.s] || ""} ${upx ? S.pos : S.neg} effect` : `${upx ? S.pos : S.neg} ${STRENGTH[x.s] || ""}`));
        const r = EN ? x.we : x.w; if (r) ln.append(el("span", "rs", "— " + r));
        eff.append(ln);
      });
      a.append(eff); box.append(a);
    });
  }

  /* ---------- search ---------- */
  let ctl = null;
  async function run(q) {
    q = (q || "").trim(); if (!q) return;
    try { history.replaceState(null, "", "?q=" + encodeURIComponent(q)); } catch (e) {}
    if (ctl) ctl.abort(); ctl = new AbortController(); const sig = ctl.signal;
    $("sstatus").textContent = S.loading; $("sugg").hidden = true; $("coin").hidden = true; $("results").hidden = true;
    try {
      const r = await (await fetch((window.API_BASE || "") + "/api/search?q=" + encodeURIComponent(q), { signal: sig })).json();
      let coinOk = false;
      if (r.coin) {
        try {
          const cr = await fetch((window.API_BASE || "") + "/api/coin/" + encodeURIComponent(r.coin.sym), { signal: sig });
          const c = await cr.json();
          if (c.ok) { renderCoin(c); coinOk = true; }
          else if (/^[A-Z0-9]{2,10}$/.test(q.toUpperCase()) || r.suggest.length) { $("coin").hidden = false; $("coin").textContent = ""; $("coin").append(el("p", "err", S.coinErr(r.coin.sym))); }
        } catch (e) { if (e.name === "AbortError") return; }
      }
      renderNews(r.news || [], q);
      $("sstatus").textContent = (!coinOk && !(r.news || []).length) ? S.none(q) : "";
    } catch (e) { if (e.name !== "AbortError") $("sstatus").textContent = S.none(q); }
  }
  $("sform").addEventListener("submit", e => { e.preventDefault(); run($("q").value); });
  let tmr = null;
  $("q").addEventListener("input", () => {
    clearTimeout(tmr);
    const v = $("q").value.trim();
    if (!v) { $("sugg").hidden = true; return; }
    tmr = setTimeout(async () => {
      try {
        const r = await (await fetch((window.API_BASE || "") + "/api/search?q=" + encodeURIComponent(v) + "&s=1")).json();
        const box = $("sugg"); box.textContent = "";
        (r.suggest || []).forEach(s => { const b = el("button", null, `${EN ? s.en : s.fa} · ${s.sym}`); b.type = "button"; b.onclick = () => { $("q").value = s.sym; run(s.sym); }; box.append(b); });
        box.hidden = !box.childElementCount;
      } catch (e) {}
    }, 250);
  });
  if ($("q").value) run($("q").value);
})();
