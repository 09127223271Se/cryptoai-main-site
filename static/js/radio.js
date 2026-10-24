/* CryptoAI — radio globe (orthographic d3 globe on canvas). Data: /api/stations (server) or static/data/stations.json (preview). */
(async () => {
"use strict";
const $ = id => document.getElementById(id);

/* ---------------- data ---------------- */
let DATA;
try {
  const url = window.SITE_MODE === "server" ? (window.API_BASE + "/api/stations") : (window.ASSET_BASE + "data/stations.json");
  DATA = await (await fetch(url)).json();
} catch (e) {
  $("st-name").textContent = "داده‌های ایستگاه بارگذاری نشد";
  return;
}
const STATIONS = DATA.stations;
$("updated").textContent = `اخبار کریپتو از هر گوشهٔ دنیا · به‌روز تا ${DATA.updated_fa} (${DATA.updated})`;
const tk = $("ticker");
function fmtPrice(p) { return p >= 1000 ? "$" + p.toLocaleString("en-US", { maximumFractionDigits: 0 }) : p >= 1 ? "$" + p.toFixed(2) : "$" + p.toPrecision(3); }
function showSnapshot() {
  tk.textContent = "";
  (DATA.market || []).forEach(m => {
    const s = document.createElement("span"); s.className = "pill";
    s.innerHTML = `${m.c} <b class="num"></b> <small class="num"></small>`;
    s.querySelector("b").textContent = "≈ " + m.p; s.querySelector("small").textContent = DATA.market_date || "";
    tk.append(s);
  });
}
async function showLive() {
  try {
    const j = await (await fetch(window.API_BASE + "/api/prices?symbols=BTC,ETH,BNB,SOL")).json();
    if (!j.ok) return false;
    tk.textContent = "";
    j.prices.forEach(p => {
      const s = document.createElement("span"); s.className = "pill live";
      s.innerHTML = `${p.c} <b class="num"></b> <small class="num"></small>`;
      s.querySelector("b").textContent = fmtPrice(p.price);
      const sm = s.querySelector("small"); sm.textContent = (p.chg24h >= 0 ? "+" : "") + (p.chg24h * 100).toFixed(2) + "%";
      sm.style.color = p.chg24h >= 0 ? "var(--up)" : "var(--down)";
      tk.append(s);
    });
    const t = document.createElement("span"); t.className = "pill"; t.textContent = "زنده · " + j.source; tk.append(t);
    DATA.liveMarket = j.prices.map(p => `${p.c} ${fmtPrice(p.price)} (${(p.chg24h * 100).toFixed(2)}% 24h)`).join(", ");
    return true;
  } catch (e) { return false; }
}
showSnapshot();
if (window.SITE_MODE === "server") {
  showLive();
  setInterval(() => { if (!document.hidden) showLive(); }, 60000);
}

/* ---------------- globe ---------------- */
const cv = $("cv"), ctx = cv.getContext("2d"), box = $("globe");
let W = 0, H = 0, R = 0, dpr = 1, scaleK = 1;
const proj = d3.geoOrthographic().clipAngle(90).precision(.4);
const path = d3.geoPath(proj, ctx);
const grat = d3.geoGraticule10();

function decodeEcharts(json) {
  if (!json || !json.features) return null;
  const sc = json.UTF8Scale || 1024;
  const dec = (s, off) => { const out = []; let px = off[0], py = off[1]; for (let i = 0; i < s.length; i += 2) { let x = s.charCodeAt(i) - 64, y = s.charCodeAt(i + 1) - 64; x = (x >> 1) ^ (-(x & 1)); y = (y >> 1) ^ (-(y & 1)); x += px; y += py; px = x; py = y; out.push([x / sc, y / sc]); } return out; };
  const feats = [];
  for (const f of json.features) {
    const g = f.geometry; if (!g) continue;
    let polys = [];
    if (json.UTF8Encoding) {
      if (g.type === "Polygon") polys = [g.coordinates.map((r, i) => typeof r === "string" ? dec(r, g.encodeOffsets[i]) : r)];
      else if (g.type === "MultiPolygon") polys = g.coordinates.map((p, i) => p.map((r, j) => typeof r === "string" ? dec(r, g.encodeOffsets[i][j]) : r));
    } else polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
    for (let p of polys) {
      p = p.map(r => { const c = r.slice(); if (c.length && (c[0][0] !== c[c.length - 1][0] || c[0][1] !== c[c.length - 1][1])) c.push(c[0]); return c; }).filter(r => r.length > 3);
      if (!p.length) continue;
      let poly = { type: "Polygon", coordinates: p };
      if (d3.geoArea(poly) > 2 * Math.PI) poly = { type: "Polygon", coordinates: p.map(r => r.slice().reverse()) };
      feats.push(poly);
    }
  }
  return feats.length ? { type: "GeometryCollection", geometries: feats } : null;
}
let land = null;
try { land = decodeEcharts(window.__worldGeo); } catch (e) { land = null; }
if (!land) $("mapnote").hidden = false;

let rot = [-20, -20, 0], auto = true, lastInteract = 0, selected = null, tween = null;
const t0 = performance.now();
function resize() {
  const r = box.getBoundingClientRect(); dpr = window.devicePixelRatio || 1; W = r.width; H = r.height;
  cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); R = Math.min(W, H) * .44;
}
function draw(now) {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
  proj.translate([W / 2, H / 2]).scale(R * scaleK).rotate(rot);
  const rr = R * scaleK;
  const g = ctx.createRadialGradient(W / 2, H / 2, rr * .92, W / 2, H / 2, rr * 1.12);
  g.addColorStop(0, "rgba(34,211,238,.16)"); g.addColorStop(1, "rgba(34,211,238,0)");
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(W / 2, H / 2, rr * 1.12, 0, 7); ctx.fill();
  ctx.beginPath(); path({ type: "Sphere" }); ctx.fillStyle = "#0a1322"; ctx.fill(); ctx.strokeStyle = "#16243b"; ctx.lineWidth = 1; ctx.stroke();
  ctx.beginPath(); path(grat); ctx.strokeStyle = "rgba(120,150,200,.10)"; ctx.lineWidth = .6; ctx.stroke();
  if (land) { ctx.beginPath(); path(land); ctx.fillStyle = "#1b293e"; ctx.fill(); ctx.strokeStyle = "#2c3f5c"; ctx.lineWidth = .6; ctx.stroke(); }
  const center = proj.invert([W / 2, H / 2]);
  const pulse = (Math.sin((now - t0) / 420) + 1) / 2;
  for (const s of STATIONS) {
    if (d3.geoDistance([s.lon, s.lat], center) > Math.PI / 2 - .02) continue;
    const [x, y] = proj([s.lon, s.lat]); const sel = selected === s;
    ctx.beginPath(); ctx.arc(x, y, sel ? 11 + pulse * 7 : 6 + pulse * 3, 0, 7); ctx.fillStyle = sel ? "rgba(255,201,77,.22)" : "rgba(255,201,77,.14)"; ctx.fill();
    ctx.beginPath(); ctx.arc(x, y, sel ? 5.5 : 4, 0, 7); ctx.fillStyle = "#ffc94d"; ctx.fill();
    if (sel || scaleK > 1.4) { ctx.font = "600 12px Vazirmatn, Tahoma, sans-serif"; ctx.fillStyle = "#e6ebf4"; ctx.textAlign = "center"; ctx.fillText(s.fa, x, y - 14); }
  }
}
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
function frame(now) {
  if (tween) { const k = Math.min(1, (now - tween.start) / tween.dur), e = d3.easeCubicInOut(k); rot = tween.i(e); if (k >= 1) tween = null; }
  else if (auto && now - lastInteract > 4000 && !reduceMotion) rot = [rot[0] + .04, rot[1], 0];
  draw(now); requestAnimationFrame(frame);
}
function flyTo(s) { tween = { start: performance.now(), dur: 1100, i: d3.interpolate(rot.slice(), [-s.lon, -s.lat, 0]) }; }

const pts = new Map(); let down = null, moved = 0, pinch0 = null;
cv.addEventListener("pointerdown", e => {
  cv.setPointerCapture(e.pointerId); pts.set(e.pointerId, [e.offsetX, e.offsetY]);
  down = { x: e.offsetX, y: e.offsetY, rot: rot.slice() }; moved = 0; tween = null; lastInteract = performance.now(); cv.classList.add("drag");
  if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch0 = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), k: scaleK }; }
});
cv.addEventListener("pointermove", e => {
  if (!pts.has(e.pointerId)) return; pts.set(e.pointerId, [e.offsetX, e.offsetY]); lastInteract = performance.now();
  if (pts.size === 2 && pinch0) { const [a, b] = [...pts.values()]; setZoom(pinch0.k * Math.hypot(a[0] - b[0], a[1] - b[1]) / pinch0.d); moved = 99; return; }
  if (!down) return; const dx = e.offsetX - down.x, dy = e.offsetY - down.y; moved = Math.max(moved, Math.hypot(dx, dy));
  const k = 70 / (R * scaleK); rot = [down.rot[0] + dx * k, Math.max(-85, Math.min(85, down.rot[1] - dy * k)), 0];
});
function up(e) {
  if (!pts.has(e.pointerId)) return; pts.delete(e.pointerId); cv.classList.remove("drag"); if (pts.size < 2) pinch0 = null;
  if (pts.size === 0) {
    if (moved < 6) { const hit = nearestScreen(e.offsetX, e.offsetY, 22); if (hit) tune(hit, true); }
    else { const c = proj.invert([W / 2, H / 2]); let best = null, bd = 1; for (const s of STATIONS) { const d = d3.geoDistance([s.lon, s.lat], c); if (d < bd) { bd = d; best = s; } } if (best && bd < .12 && best !== selected) tune(best, false); }
    down = null;
  }
}
cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up);
cv.addEventListener("wheel", e => { e.preventDefault(); lastInteract = performance.now(); setZoom(scaleK * Math.exp(-e.deltaY * .0015)); }, { passive: false });
function setZoom(k) { scaleK = Math.max(.8, Math.min(4, k)); }
$("zin").onclick = () => { setZoom(scaleK * 1.35); lastInteract = performance.now(); };
$("zout").onclick = () => { setZoom(scaleK / 1.35); lastInteract = performance.now(); };
function nearestScreen(x, y, maxd) { const c = proj.invert([W / 2, H / 2]); let best = null, bd = maxd; for (const s of STATIONS) { if (d3.geoDistance([s.lon, s.lat], c) > Math.PI / 2) continue; const p = proj([s.lon, s.lat]); const d = Math.hypot(p[0] - x, p[1] - y); if (d < bd) { bd = d; best = s; } } return best; }

/* ---------------- tuning static ---------------- */
let actx = null;
function staticBurst() {
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)(); if (actx.state === "suspended") actx.resume();
    const len = actx.sampleRate * .35, buf = actx.createBuffer(1, len, actx.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len);
    const src = actx.createBufferSource(), bp = actx.createBiquadFilter(), gn = actx.createGain();
    bp.type = "bandpass"; bp.frequency.value = 1800; bp.Q.value = .8; gn.gain.value = .12;
    src.buffer = buf; src.connect(bp).connect(gn).connect(actx.destination); src.start();
  } catch (e) {}
}

/* ---------------- speech ---------------- */
const synth = window.speechSynthesis || null; let voices = [], playing = false;
function loadVoices() { if (synth) voices = synth.getVoices() || []; }
if (synth) { loadVoices(); synth.onvoiceschanged = loadVoices; }
function pickVoice() { const fa = voices.find(v => /^fa/i.test(v.lang)); if (fa) return { v: fa, lang: "fa" }; const en = voices.find(v => /^en/i.test(v.lang)); return { v: en || null, lang: "en" }; }
function setPlaying(on) { playing = on; $("ic-play").hidden = on; $("ic-pause").hidden = !on; $("eq").classList.toggle("on", on); $("play").setAttribute("aria-label", on ? "توقف" : "پخش"); }
function clearLive() { document.querySelectorAll(".item.live").forEach(x => x.classList.remove("live")); }
function stopSpeech() { if (synth) synth.cancel(); setPlaying(false); clearLive(); }
function speakStation(s) {
  if (!synth) { $("voice").textContent = "این مرورگر خواندن متن را پشتیبانی نمی‌کند."; return; }
  synth.cancel(); loadVoices();
  const pv = pickVoice();
  $("voice").textContent = pv.lang === "fa" ? "پخش با صدای فارسی دستگاه" : (voices.length ? "صدای فارسی روی این دستگاه نیست؛ نسخهٔ انگلیسی پخش می‌شود" : "در حال پخش…");
  const parts = [{ txt: pv.lang === "fa" ? `این‌جا رادیو کریپتو، ${s.fa}.` : `This is Crypto Radio, ${s.en}.`, i: -1 }];
  s.news.forEach((n, i) => parts.push({ txt: pv.lang === "fa" ? n.t + ". " + n.b : n.en, i }));
  setPlaying(true);
  parts.forEach((p, k) => {
    const u = new SpeechSynthesisUtterance(p.txt); u.lang = pv.lang === "fa" ? "fa-IR" : "en-US"; if (pv.v) u.voice = pv.v;
    u.onstart = () => document.querySelectorAll(".item").forEach((x, j) => x.classList.toggle("live", j === p.i));
    if (k === parts.length - 1) u.onend = () => { setPlaying(false); clearLive(); };
    u.onerror = () => { if (k === parts.length - 1) setPlaying(false); };
    synth.speak(u);
  });
}
$("play").onclick = () => { if (!selected) return; if (playing) stopSpeech(); else speakStation(selected); };

/* ---------------- sheet ---------------- */
const ARW = { up: "↑", down: "↓", mixed: "↕" }, DIRFA = { up: "احتمال اثر مثبت", down: "احتمال اثر منفی", mixed: "اثر دوطرفه یا نامشخص" };
function renderNotes(list, label) {
  const nb = $("notes"); nb.textContent = "";
  list.forEach(n => {
    const d = document.createElement("div"); d.className = "note";
    const dir = ["up", "down", "mixed"].includes(n.dir) ? n.dir : "mixed";
    d.innerHTML = `<span class="arrow ${dir}" aria-label="${DIRFA[dir]}">${ARW[dir]}</span><div><div class="coins"></div><p></p><small></small></div>`;
    const cs = d.querySelector(".coins"); (n.c || []).forEach(c => { const s = document.createElement("span"); s.className = "coin"; s.textContent = String(c); cs.append(s); });
    d.querySelector("p").textContent = n.n || ""; d.querySelector("small").textContent = n.w || "";
    nb.append(d);
  });
  $("ai-s").textContent = label || "";
}
function renderSheet(s) {
  $("freq").textContent = `CRYPTO FM ${s.freq} · ${s.lat.toFixed(2)}°, ${s.lon.toFixed(2)}°`;
  $("st-name").textContent = "رادیو کریپتو " + s.fa;
  $("st-where").textContent = s.country;
  const nb = $("news"); nb.textContent = "";
  s.news.forEach(n => {
    const d = document.createElement("div"); d.className = "item";
    d.innerHTML = `<b></b><p></p><div class="meta"><span class="num"></span><a target="_blank" rel="noopener"></a></div>`;
    d.querySelector("b").textContent = n.t; d.querySelector("p").textContent = n.b; d.querySelector(".num").textContent = n.d;
    const a = d.querySelector("a"); a.textContent = n.source.name; a.href = n.source.url; nb.append(d);
  });
  renderNotes(s.notes, `تحلیل Claude هنگام جمع‌آوری خبرها (${DATA.updated_fa})`);
}
function renderDial() {
  const d = $("dial"); d.textContent = "";
  STATIONS.forEach(s => {
    const b = document.createElement("button"); b.type = "button"; b.setAttribute("role", "tab"); b.setAttribute("aria-current", s === selected ? "true" : "false");
    const cnt = s.notes.reduce((a, n) => (a[n.dir] = (a[n.dir] || 0) + 1, a), {});
    const col = (cnt.down || 0) > (cnt.up || 0) ? "var(--down)" : (cnt.up || 0) > (cnt.down || 0) ? "var(--up)" : "var(--mixed)";
    b.innerHTML = `<span class="d" style="background:${col}"></span>`; b.append(s.fa); b.onclick = () => tune(s, true); d.append(b);
  });
}
function tune(s, fly) {
  if (selected === s && !fly) return;
  selected = s; auto = false; lastInteract = performance.now();
  if (fly) flyTo(s);
  stopSpeech(); staticBurst(); renderSheet(s); renderDial();
  try { history.replaceState(null, "", "#" + s.id); } catch (e) {}
}

/* ---------------- live re-analysis ---------------- */
let ctl = null;
AI.status().then(st => { $("reanalyze").hidden = !st.ok; });
$("reanalyze").onclick = async () => {
  if (!selected) return; const s = selected;
  if (ctl) ctl.abort(); ctl = new AbortController();
  $("reanalyze").disabled = true; $("ai-s").textContent = "هوش مصنوعی در حال تحلیل اثر خبرها…";
  const m = DATA.liveMarket ? "live now: " + DATA.liveMarket : (DATA.market || []).map(x => `${x.c} ${x.p}`).join(", ") + " (" + DATA.market_date + ")";
  const prompt = `You are a crypto market analyst for a Persian-language Telegram channel.
Below are recent news items from one region (${s.en}). Decide which coins or market segments each item could move, and in which direction.
Reply with ONLY a JSON array (max 4 objects) like:
[{"c":["BTC","ETH"],"dir":"up"|"down"|"mixed","n":"one sentence in Persian (Farsi), max 30 words, on the likely market effect","w":"short Persian reason or timing note, max 15 words, may be empty"}]
Rules: no buy/sell advice, no price targets, no entry points. If an item has no real market effect, say so with dir "mixed". Use coin tickers in Latin letters.
Market context: ${m}.
NEWS:
${JSON.stringify(s.news.map(n => ({ date: n.d, title: n.en })), null, 1)}`;
  try {
    const arr = await AI.ask(prompt, { json: true, signal: ctl.signal });
    if (selected !== s) return;
    if (Array.isArray(arr) && arr.length) renderNotes(arr.slice(0, 4).map(x => ({ c: Array.isArray(x.c) ? x.c.slice(0, 4) : [], dir: x.dir, n: String(x.n || ""), w: String(x.w || "") })), "تحلیل تازهٔ هوش مصنوعی");
    else $("ai-s").textContent = "هوش مصنوعی نکته‌ای برنگرداند.";
  } catch (e) { if (!e || e.code !== "cancelled") $("ai-s").textContent = AI.errorText(e); }
  finally { $("reanalyze").disabled = false; }
};

/* ---------------- boot ---------------- */
resize(); addEventListener("resize", resize); new ResizeObserver(resize).observe(box);
const start = STATIONS.find(s => s.id === location.hash.slice(1)) || STATIONS[0];
selected = start; renderSheet(start); renderDial();
rot = [-start.lon + 25, -start.lat + 8, 0]; flyTo(start); lastInteract = performance.now() + 2000;
requestAnimationFrame(frame);
})();
