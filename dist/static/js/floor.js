/* CryptoAI — analysis floor: six agents, live chart, honest track record, streaming activity log. */
(() => {
  const $ = id => document.getElementById(id);
  if (!$("floor") || window.SITE_MODE !== "server") { if ($("floor")) $("floor").hidden = true; return; }
  const EN = window.LANG === "en";
  const T = EN ? {
    bt: "backtest · 30 days", live: "live record", of: (h, c) => `${h} of ${c} calls right`, none: "Collecting the record…",
    verdict: { up_strong: "Strong bullish", down_strong: "Strong bearish", up: "Leaning up", down: "Leaning down", conflict: "Chart vs news conflict", range: "Ranging" },
    idle: "IDLE", run: "RUN", noData: "Live market data is loading…", calls: "calls",
    sub: (bt, live) => `${bt}${live ? " · live: " + live : ""}`,
  } : {
    bt: "بک‌تست ۳۰ روز", live: "کارنامهٔ زنده", of: (h, c) => `${h} از ${c} پیش‌بینی درست`, none: "در حال جمع‌آوری کارنامه…",
    verdict: { up_strong: "صعودی قوی", down_strong: "نزولی قوی", up: "متمایل به صعود", down: "متمایل به نزول", conflict: "چارت و خبر متضاد", range: "نوسانی" },
    idle: "IDLE", run: "RUN", noData: "دادهٔ زندهٔ بازار در حال بارگذاری است…", calls: "پیش‌بینی",
    sub: (bt, live) => `${bt}${live ? " · زنده: " + live : ""}`,
  };
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || n;
  const usd = v => v >= 100 ? "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 }) : v >= 1 ? "$" + v.toFixed(3) : "$" + v.toPrecision(4);
  const el = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; };

  /* ---------- characters (original shapes, two eyes) ---------- */
  function bot(shape, color) {
    const body = {
      square: `<rect x="8" y="10" width="44" height="40" rx="12" fill="${color}"/>`,
      pill: `<rect x="4" y="16" width="52" height="30" rx="15" fill="${color}"/>`,
      hex: `<polygon points="30,6 52,18 52,42 30,54 8,42 8,18" fill="${color}"/>`,
      circle: `<circle cx="30" cy="30" r="23" fill="${color}"/>`,
      tri: `<path d="M30 8 L54 50 Q55 53 51 53 H9 Q5 53 6 50 Z" fill="${color}"/>`,
      blob: `<path d="M12 34 C8 18 22 8 33 10 C47 12 54 22 52 34 C50 48 38 53 28 52 C18 51 14 44 12 34Z" fill="${color}"/>`,
    }[shape];
    const ey = shape === "tri" ? 38 : 30;
    return `<svg class="fl-bot" viewBox="0 0 60 60" aria-hidden="true">${body}<ellipse cx="23" cy="${ey}" rx="3.4" ry="4.6" fill="#0b1020"/><ellipse cx="37" cy="${ey}" rx="3.4" ry="4.6" fill="#0b1020"/><ellipse cx="24" cy="${ey - 1.6}" rx="1.1" ry="1.4" fill="#fff"/><ellipse cx="38" cy="${ey - 1.6}" rx="1.1" ry="1.4" fill="#fff"/></svg>`;
  }

  let STATE = null, coin = "BTC", COIN = null, queue = [], shown = new Set(), timer = null, GEO = null, unsub = null;
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;

  function buildAgents(agents) {
    const desks = $("fl-desks"), cards = $("fl-cards");
    desks.textContent = ""; cards.textContent = "";
    agents.forEach(a => {
      const d = el("div", "fl-desk"); d.dataset.a = a.id; d.style.setProperty("--c", a.color);
      d.innerHTML = `<div class="fl-bubble" dir="auto"></div><div class="fl-mon" data-mon="${a.id}">…</div><div class="fl-table"></div>${bot(a.shape, a.color)}<div class="fl-name">${a.name}</div>`;
      desks.append(d);
      const c = el("div", "fl-card"); c.dataset.a = a.id; c.style.setProperty("--c", a.color);
      c.innerHTML = `${bot(a.shape, a.color)}<small><span>${a.n} · ${a.id.toUpperCase()}</span><em>${T.idle}</em></small><b>${a.name}</b><p dir="auto"></p>`;
      c.querySelector("p").textContent = EN ? a.role_en : a.role_fa;
      cards.append(c);
    });
  }

  function monitors() {
    if (!STATE) return;
    const s = STATE.stats, set = (id, t) => { const m = document.querySelector(`[data-mon="${id}"]`); if (m) m.textContent = t; };
    set("scan", `${s.coins} · ${s.patterns}◆`);
    set("news", `${s.news} NEWS`);
    set("editor", `${s.posts} POSTS`);
    if (COIN) {
      set("trend", `${COIN.sym} ${COIN.trend === "up" ? "▲" : COIN.trend === "down" ? "▼" : "▬"} RSI ${COIN.rsi.toFixed(0)}`);
      set("risk", `±${((COIN.p75 - COIN.p25) / 2 / COIN.price * 100).toFixed(1)}% 24h`);
      set("judge", (T.verdict[COIN.verdict] || "").slice(0, 18));
    }
  }

  /* ---------- track record ---------- */
  function record() {
    const bt = STATE.backtest || {}, lv = STATE.live || {};
    const use = (lv.calls || 0) >= 10 ? lv : bt;
    $("fa-src").textContent = use === lv ? T.live : T.bt;
    if (use.rate == null) { $("fa-rate").textContent = "–"; $("fa-sub").textContent = T.none; return; }
    $("fa-rate").textContent = use.rate + "%"; $("fa-rate").className = "fl-big" + (use.rate >= 55 ? " up" : "");
    $("fa-sub").textContent = T.sub(T.of(use.hits, use.calls), (lv.calls && use !== lv) ? `${lv.hits}/${lv.calls}` : "");
    $("fa-50").textContent = use.in50 != null ? use.in50 + "%" : "–";
    $("fa-90").textContent = use.in90 != null ? use.in90 + "%" : "–";
    const by = $("fa-by"); by.textContent = "";
    Object.entries(use.by || {}).forEach(([k, v]) => {
      if (!v.calls) return;
      const r = Math.round(100 * v.hits / v.calls), row = el("div");
      row.innerHTML = `<span>${k}</span><u><i style="width:${r}%"></i></u><span>${r}%</span>`; by.append(row);
    });
    const cv = $("fa-curve"), pts = use.curve || [];
    const dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight; cv.width = W * dpr; cv.height = H * dpr;
    const x = cv.getContext("2d"); x.scale(dpr, dpr);
    if (pts.length < 2) return;
    const lo = Math.min(0, ...pts), hi = Math.max(1, ...pts), Y = v => H - 6 - (v - lo) / (hi - lo) * (H - 12);
    x.strokeStyle = "#1b2647"; x.beginPath(); x.moveTo(0, Y(0)); x.lineTo(W, Y(0)); x.stroke();
    const g = x.createLinearGradient(0, 0, W, 0); g.addColorStop(0, "#a78bfa"); g.addColorStop(1, "#22d3ee");
    x.strokeStyle = g; x.lineWidth = 2; x.beginPath();
    pts.forEach((v, i) => { const px = i / (pts.length - 1) * (W - 4) + 2; i ? x.lineTo(px, Y(v)) : x.moveTo(px, Y(v)); });
    x.stroke();
  }

  /* ---------- chart ---------- */
  function chart() {
    const c = COIN, cv = $("fl-chart");
    const dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight; cv.width = W * dpr; cv.height = H * dpr;
    const x = cv.getContext("2d"); x.scale(dpr, dpr);
    if (!c) { x.fillStyle = "#6f7ca3"; x.font = "13px " + css("--f-body"); x.fillText(T.noData, 12, 30); return; }
    const k = c.candles, n = k.length;
    const vals = k.flatMap(r => [r[2], r[3]]).concat([c.p05, c.p95, c.res, c.sup]);
    let lo = Math.min(...vals), hi = Math.max(...vals); const pad = (hi - lo) * .06 || 1; lo -= pad; hi += pad;
    const L = 4, Rk = W - 130, Rz = W - 66, Tp = 8, B = H - 10, Y = v => B - (v - lo) / (hi - lo) * (B - Tp), step = (Rk - L) / n;
    x.strokeStyle = "rgba(60,80,140,.25)"; x.lineWidth = 1;
    for (let i = 0; i < 5; i++) { const y = Tp + i * (B - Tp) / 4; x.beginPath(); x.moveTo(L, y); x.lineTo(Rz, y); x.stroke(); }
    const up = "#22d3ee", dn = "#ff4fa3";
    const zc = c.verdict.startsWith("up") ? "#33d39a" : c.verdict.startsWith("down") ? dn : "#a78bfa";
    const px = Rk + 4, py = Y(c.price);
    x.globalAlpha = .16; x.fillStyle = zc; x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, Y(c.p95)); x.lineTo(Rz, Y(c.p05)); x.fill();
    x.globalAlpha = .34; x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, Y(c.p75)); x.lineTo(Rz, Y(c.p25)); x.fill();
    x.globalAlpha = 1; x.strokeStyle = zc; x.setLineDash([3, 4]); x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, Y(c.p50)); x.stroke(); x.setLineDash([]);
    [[c.res, dn, EN ? "RES" : "مقاومت"], [c.sup, "#33d39a", EN ? "SUP" : "حمایت"]].forEach(([v, col, lab]) => {
      x.setLineDash([6, 6]); x.strokeStyle = col; x.globalAlpha = .8; x.beginPath(); x.moveTo(L, Y(v)); x.lineTo(Rz, Y(v)); x.stroke(); x.setLineDash([]); x.globalAlpha = 1;
      x.fillStyle = col; x.font = "600 11px " + css("--f-mono"); x.fillText(usd(v), Rz + 4, Y(v) + 4);
      x.font = "10px " + css("--f-body"); x.fillText(lab, Rz + 4, Y(v) + 16);
    });
    k.forEach((r, i) => {
      const [, o, h, l, cl] = r, cx = L + i * step + step / 2, col = cl >= o ? up : dn;
      x.strokeStyle = col; x.beginPath(); x.moveTo(cx, Y(h)); x.lineTo(cx, Y(l)); x.stroke();
      x.fillStyle = col; x.shadowColor = col; x.shadowBlur = 6;
      const t = Y(Math.max(o, cl)), b = Y(Math.min(o, cl)); x.fillRect(cx - step * .34, t, step * .68, Math.max(1, b - t)); x.shadowBlur = 0;
    });
    x.fillStyle = "#fff"; x.beginPath(); x.arc(px - 4, py, 3.5, 0, 7); x.fill();
    GEO = { Y, L, Rk, Rz, px, py, W, H, step, n };
  }
  async function loadCoin(sym) {
    coin = sym;
    document.querySelectorAll("#fl-coins button").forEach(b => b.setAttribute("aria-pressed", b.dataset.s === sym ? "true" : "false"));
    try {
      const c = await (await fetch(`${window.API_BASE || ""}/api/coin/${sym}`)).json();
      if (!c.ok || c.stable) throw 0;
      COIN = c;
      $("fl-sym").textContent = `${c.sym}/USDT · 1H`;
      $("fl-px").textContent = usd(c.price);
      const ch = $("fl-ch"); ch.textContent = (c.ch24 >= 0 ? "+" : "") + c.ch24.toFixed(2) + "% 24h"; ch.className = c.ch24 >= 0 ? "up" : "down";
      const vd = $("fl-vd"); vd.textContent = T.verdict[c.verdict];
      vd.style.color = c.verdict.startsWith("up") ? "#33d39a" : c.verdict.startsWith("down") ? "#ff4fa3" : c.verdict === "conflict" ? "#ffc94d" : "#a78bfa";
    } catch (e) { COIN = null; }
    chart(); monitors(); live(sym);
  }
  function live(sym) {
    if (!window.LivePrices || !COIN) return;
    if (unsub) { try { unsub(); } catch (e) {} unsub = null; }
    let last = 0;
    const r = LivePrices.subscribe([sym], (s, v) => {
      if (s !== sym || !COIN || COIN.sym !== sym) return;
      const k = COIN.candles[COIN.candles.length - 1], p = v.price;
      const hourStart = Math.floor(Date.now() / 3600000) * 3600;
      if (k[0] < hourStart - 60) COIN.candles.push([hourStart, k[4], Math.max(k[4], p), Math.min(k[4], p), p]), COIN.candles.shift();
      const c = COIN.candles[COIN.candles.length - 1];
      c[4] = p; c[2] = Math.max(c[2], p); c[3] = Math.min(c[3], p);
      COIN.price = p;
      $("fl-px").textContent = usd(p);
      const now = performance.now(); if (now - last > 400) { last = now; chart(); }
    });
    if (typeof r === "function") unsub = r;
  }
  ["BTC", "ETH", "SOL", "XRP", "TON", "DOGE"].forEach(s => {
    const b = el("button", null, s); b.type = "button"; b.dataset.s = s; b.onclick = () => loadCoin(s); $("fl-coins").append(b);
  });

  /* ---------- activity stream ---------- */
  const AG = id => (STATE.agents.find(a => a.id === id) || {});
  function push(e, instant) {
    const a = AG(e.agent), rows = $("fl-rows");
    const r = el("div", "fl-row");
    const nm = el("b", null, a.name || e.agent); nm.style.color = a.color;
    const k = el("span", e.d > 0 ? "k-up" : e.d < 0 ? "k-down" : "", e.kind);
    const p = el("p", null, EN ? e.en : e.fa); p.dir = "auto";
    r.append(nm, k, p);
    rows.prepend(r);
    while (rows.childElementCount > 60) rows.lastChild.remove();
    if (instant) return;
    document.querySelectorAll(".fl-desk.on,.fl-card.on").forEach(x => { x.classList.remove("on"); const em = x.querySelector("em"); if (em) em.textContent = T.idle; });
    const desk = document.querySelector(`.fl-desk[data-a="${e.agent}"]`), card = document.querySelector(`.fl-card[data-a="${e.agent}"]`);
    if (desk) { desk.classList.add("on"); if (calm) desk.querySelector(".fl-bubble").textContent = EN ? e.en : e.fa; else fly(desk, e); }
    if (card) { card.classList.add("on"); card.querySelector("em").textContent = "● " + T.run; }
  }
  let slot = 0;
  /* ---------- a bot walks to the chart, writes its finding there, walks back ---------- */
  function target(e) {
    const g = GEO; if (!g || !COIN) return null;
    const mine = (e.en || "").startsWith(COIN.sym);
    const top = () => { slot = (slot + 1) % 3; return { x: g.L + 90 + Math.random() * (g.Rk - g.L - 180), y: 22 + slot * 26 }; };
    if (!mine && ["trend", "risk", "judge"].includes(e.agent)) return top();
    switch (e.agent) {
      case "trend": return mine ? { x: g.L + (g.Rk - g.L) * .55, y: g.Y(e.d < 0 ? COIN.sup : COIN.res), label: `${EN ? "RES" : "مقاومت"} ${usd(COIN.res)} · ${EN ? "SUP" : "حمایت"} ${usd(COIN.sup)}` } : { x: g.L + (g.Rk - g.L) * .4, y: g.Y(COIN.res) };
      case "risk": return { x: g.Rz - 12, y: (g.Y(COIN.p75) + g.Y(COIN.p25)) / 2, label: mine ? `24h ${usd(COIN.p25)}–${usd(COIN.p75)}` : null };
      case "judge": return { x: g.px - 10, y: g.py - 26, label: mine ? T.verdict[COIN.verdict] : null };
      case "news": { const i = Math.floor(g.n * (.55 + Math.random() * .4)), c = COIN.candles[i] || COIN.candles[g.n - 1];
        return { x: g.L + i * g.step, y: g.Y(e.d < 0 ? c[3] : c[2]) + (e.d < 0 ? 18 : -18) }; }
      default: return top();
    }
  }
  function note(t, text, color, d) {
    const scr = document.querySelector(".fl-screen"), cv = $("fl-chart");
    const n = el("div", "fl-note-chip"); n.dir = "auto"; n.textContent = (d > 0 ? "▲ " : d < 0 ? "▼ " : "") + text;
    n.style.setProperty("--c", color);
    n.style.left = (cv.offsetLeft + Math.min(Math.max(t.x, 60), cv.clientWidth - 60)) + "px";
    n.style.top = (cv.offsetTop + Math.max(t.y, 14)) + "px";
    scr.append(n);
    const all = scr.querySelectorAll(".fl-note-chip"); if (all.length > 4) all[0].remove();
    setTimeout(() => { n.classList.add("out"); setTimeout(() => n.remove(), 700); }, 9000);
  }
  function fly(desk, e) {
    const t = target(e), room = document.querySelector(".fl-room"), home = desk.querySelector(".fl-bot");
    if (!t || !room || !home) { desk.querySelector(".fl-bubble").textContent = EN ? e.en : e.fa; return; }
    const a = AG(e.agent), rr = room.getBoundingClientRect(), hb = home.getBoundingClientRect(), cr = $("fl-chart").getBoundingClientRect();
    const sx = hb.left - rr.left, sy = hb.top - rr.top;
    const tx = cr.left - rr.left + t.x - hb.width / 2, ty = cr.top - rr.top + t.y - hb.height - 4;
    const f = el("div", "fl-flyer"); f.innerHTML = bot(a.shape, a.color); f.style.setProperty("--c", a.color);
    f.style.left = sx + "px"; f.style.top = sy + "px"; room.append(f);
    home.style.visibility = "hidden";
    const dx = tx - sx, dy = ty - sy, hop = Math.min(-60, dy - 40);
    const go = f.animate([{ transform: "translate(0,0) scale(1)" },
      { transform: `translate(${dx * .5}px,${dy * .5 + hop * .5}px) scale(.9) rotate(-8deg)`, offset: .5 },
      { transform: `translate(${dx}px,${dy}px) scale(.8)` }], { duration: 900, easing: "cubic-bezier(.45,.05,.3,1)", fill: "forwards" });
    go.onfinish = () => {
      f.classList.add("writing");
      const short = t.label || ((EN ? e.en : e.fa) || "").slice(0, 46);
      note(t, short, a.color, e.d);
      setTimeout(() => {
        f.classList.remove("writing");
        const back = f.animate([{ transform: `translate(${dx}px,${dy}px) scale(.8)` },
          { transform: `translate(${dx * .5}px,${dy * .5 + hop * .4}px) scale(.9) rotate(8deg)`, offset: .5 },
          { transform: "translate(0,0) scale(1)" }], { duration: 850, easing: "cubic-bezier(.45,.05,.3,1)", fill: "forwards" });
        back.onfinish = () => { f.remove(); home.style.visibility = ""; };
      }, 1700);
    };
  }

  function cycle() {
    if (!queue.length && STATE) {             // replay the latest real events so the floor keeps working
      queue = STATE.activity.slice(0, 18).reverse();
    }
    const e = queue.shift(); if (e) push(e);
  }

  async function load(first) {
    try {
      const j = await (await fetch(`${window.API_BASE || ""}/api/floor`)).json();
      const fresh = !STATE;
      STATE = j;
      if (fresh) buildAgents(j.agents);
      $("fs-coins").textContent = j.stats.coins; $("fs-pat").textContent = j.stats.patterns;
      $("fs-news").textContent = j.stats.news; $("fs-posts").textContent = j.stats.posts;
      $("fl-count").textContent = j.activity.length + " EVENTS";
      record(); monitors();
      if (fresh) {
        j.activity.slice(6).reverse().forEach(e => { shown.add(e.ts + e.fa); push(e, true); });
        queue = j.activity.slice(0, 6).reverse();
      } else {
        j.activity.filter(e => !shown.has(e.ts + e.fa)).reverse().forEach(e => queue.push(e));
      }
      j.activity.forEach(e => shown.add(e.ts + e.fa));
      if (!timer) { cycle(); timer = setInterval(() => { if (!document.hidden) cycle(); }, calm ? 2600 : 4200); }
    } catch (e) { if (first) setTimeout(() => load(true), 8000); }
  }
  setInterval(() => { $("fs-clock").textContent = "LIVE " + new Date().toLocaleTimeString("en-GB", { hour12: false }); }, 1000);
  load(true); loadCoin("BTC");
  setInterval(() => { if (!document.hidden) load(); }, 60000);
  setInterval(() => { if (!document.hidden) loadCoin(coin); }, 120000);
  addEventListener("resize", () => { chart(); if (STATE) record(); });
})();
