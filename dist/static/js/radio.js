/* CryptoAI — radio globe (orthographic d3 globe on canvas). Data: /api/stations (server) or static/data/stations.json (preview). */
(async () => {
"use strict";
const $ = id => document.getElementById(id);

/* ---------------- data ---------------- */
let DATA;
const dataUrl = window.SITE_MODE === "server" ? (window.API_BASE + "/api/stations") : (window.ASSET_BASE + "data/stations.json");
try { DATA = await (await fetch(dataUrl)).json(); }
catch (e) { $("st-name").textContent = "داده‌های ایستگاه بارگذاری نشد"; return; }
let STATIONS = DATA.stations.filter(s => s.news && s.news.length);
const faTime = (d, tz, sec) => new Intl.DateTimeFormat("fa-IR", { hour: "2-digit", minute: "2-digit", second: sec ? "2-digit" : undefined, hour12: false, timeZone: tz }).format(d);
function ago(ts) {
  const m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
  if (m < 1) return "همین الان"; if (m < 60) return m.toLocaleString("fa-IR") + " دقیقه پیش";
  const h = Math.floor(m / 60); if (h < 24) return h.toLocaleString("fa-IR") + " ساعت پیش";
  return Math.floor(h / 24).toLocaleString("fa-IR") + " روز پیش";
}
function renderUpdated() {
  const el = $("updated");
  if (DATA.live) {
    const t = new Date(DATA.updated);
    el.textContent = `خبرهای زنده از ${(DATA.feeds || []).join("، ")} · آخرین به‌روزرسانی ${faTime(t, undefined, false)} (هر ۱۰ دقیقه)`;
  } else if (DATA.refreshing) {
    el.textContent = "در حال گرفتن خبرهای زنده… تا آن موقع خبرهای ذخیره‌شده نمایش داده می‌شوند.";
  } else {
    el.textContent = `اخبار کریپتو از هر گوشهٔ دنیا · به‌روز تا ${DATA.updated_fa} (${DATA.updated})`;
  }
}
renderUpdated();

/* ---------------- live prices (tick by tick from the exchange) ---------------- */
const tk = $("ticker");
const TICK = ["BTC", "ETH", "BNB", "SOL"];
function fmtPrice(p) { return p >= 1 ? "$" + p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "$" + p.toPrecision(4); }
const pills = {};
TICK.forEach(c => {
  const s = document.createElement("span"); s.className = "pill";
  s.innerHTML = `${c} <b class="num">…</b> <small class="num"></small>`;
  tk.append(s); pills[c] = s;
});
const srcPill = document.createElement("span"); srcPill.className = "pill"; srcPill.textContent = "در حال اتصال به صرافی…"; tk.append(srcPill);
const clockPill = document.createElement("span"); clockPill.className = "pill num"; tk.append(clockPill);
const marketNow = {};
if (window.SITE_MODE === "server") {
  LivePrices.subscribe(TICK, (sym, v) => {
    const s = pills[sym]; if (!s) return;
    marketNow[sym] = v;
    const b = s.querySelector("b"), prev = parseFloat((b.dataset.p || "0"));
    b.textContent = fmtPrice(v.price); b.dataset.p = v.price;
    b.style.color = v.price > prev && prev ? "var(--up)" : v.price < prev ? "var(--down)" : "";
    const sm = s.querySelector("small");
    if (isFinite(v.chg24h)) { sm.textContent = (v.chg24h >= 0 ? "+" : "") + (v.chg24h * 100).toFixed(2) + "%"; sm.style.color = v.chg24h >= 0 ? "var(--up)" : "var(--down)"; }
    s.className = "pill live";
  }, st => { srcPill.textContent = st.live ? "قیمت لحظه‌ای · " + st.source : "قیمت زنده در دسترس نیست"; });
} else {
  (DATA.market || []).forEach(m => { if (pills[m.c]) { pills[m.c].querySelector("b").textContent = "≈ " + m.p; pills[m.c].querySelector("small").textContent = DATA.market_date || ""; } });
  srcPill.textContent = "پیش‌نمایش · قیمت ذخیره‌شده";
}
function tickClock() {
  const now = new Date();
  clockPill.textContent = "ساعت شما " + faTime(now, undefined, true);
  if (selected) $("st-clock").textContent = "ساعت محلی " + selected.fa + ": " + faTime(now, selected.tz, true);
  document.querySelectorAll("#news .ago").forEach(el => { el.textContent = ago(+el.dataset.ts); });
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
let rot = [-20, -20, 0], auto = true, lastInteract = 0, selected = null, tween = null;
const t0 = performance.now();
function resize() {
  const r = box.getBoundingClientRect(); dpr = window.devicePixelRatio || 1; W = r.width; H = r.height;
  cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); R = Math.min(W, H) * .44;
}
let land = null;
try { land = decodeEcharts(window.__worldGeo); } catch (e) { land = null; }

/* ---- satellite Earth texture (NASA Blue Marble, equirectangular), drawn per pixel with lighting ---- */
const TEX_URLS = [
  "https://cdn.jsdelivr.net/npm/three-globe@2.31.0/example/img/earth-blue-marble.jpg",
  "https://unpkg.com/three-globe@2.31.0/example/img/earth-blue-marble.jpg",
  "https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
];
let tex = null;              // {d: Uint8ClampedArray, w, h}
let texTried = false;
function loadTexture(i = 0) {
  if (i >= TEX_URLS.length) { texTried = true; if (!land) $("mapnote").hidden = false; return; }
  const img = new Image(); img.crossOrigin = "anonymous"; img.decoding = "async";
  img.onload = () => {
    try {
      const w = Math.min(img.naturalWidth, 2048), h = Math.round(w / 2);
      const c = document.createElement("canvas"); c.width = w; c.height = h;
      const g = c.getContext("2d", { willReadFrequently: true }); g.drawImage(img, 0, 0, w, h);
      tex = { d: g.getImageData(0, 0, w, h).data, w, h }; texTried = true; dirty = true;
    } catch (e) { loadTexture(i + 1); }
  };
  img.onerror = () => loadTexture(i + 1);
  img.src = TEX_URLS[i];
}
loadTexture();

const buf = document.createElement("canvas"), bctx = buf.getContext("2d");
let bufImg = null, dirty = true, lastKey = "", stillSince = 0;
const D2R = Math.PI / 180;
// light from the upper-left front, in the screen frame (depth, x, y)
const L = (() => { const v = [0.78, -0.42, 0.46], n = Math.hypot(...v); return v.map(x => x / n); })();
function renderEarth(rr, q) {
  const bw = Math.max(2, Math.round(W * dpr * q)), bh = Math.max(2, Math.round(H * dpr * q));
  if (buf.width !== bw || buf.height !== bh || !bufImg) { buf.width = bw; buf.height = bh; bufImg = bctx.createImageData(bw, bh); }
  const out = bufImg.data; out.fill(0);
  const rad = rr * dpr * q, cx = bw / 2, cy = bh / 2;
  const dl = rot[0] * D2R, dp = rot[1] * D2R, cp = Math.cos(dp), sp = Math.sin(dp);
  const T = tex.d, tw = tex.w, th = tex.h, TWO_PI = Math.PI * 2;
  const y0 = Math.max(0, Math.floor(cy - rad)), y1 = Math.min(bh, Math.ceil(cy + rad));
  for (let y = y0; y < y1; y++) {
    const v = (cy - y - 0.5) / rad, vv = v * v;
    if (vv >= 1) continue;
    const half = Math.sqrt(1 - vv) * rad;
    const x0 = Math.max(0, Math.floor(cx - half)), x1 = Math.min(bw, Math.ceil(cx + half));
    for (let x = x0; x < x1; x++) {
      const u = (x + 0.5 - cx) / rad, d = u * u + vv;
      if (d >= 1) continue;
      const z0 = Math.sqrt(1 - d);
      const X = z0 * cp + v * sp, Z = v * cp - z0 * sp;
      let lon = Math.atan2(u, X) - dl;
      const lat = Math.asin(Z < -1 ? -1 : Z > 1 ? 1 : Z);
      lon = ((lon / TWO_PI + 0.5) % 1 + 1) % 1;
      const tx = (lon * tw) | 0, ty = Math.min(th - 1, ((0.5 - lat / Math.PI) * th) | 0);
      const ti = (ty * tw + tx) * 4;
      let shade = 0.32 + 0.78 * Math.max(0, z0 * L[0] + u * L[1] + v * L[2]);
      const limb = 1 - Math.pow(1 - z0, 3) * 0.55;      // darker toward the edge
      shade *= limb;
      const o = (y * bw + x) * 4;
      out[o] = Math.min(255, T[ti] * shade + 6 * (1 - z0));
      out[o + 1] = Math.min(255, T[ti + 1] * shade + 14 * (1 - z0));
      out[o + 2] = Math.min(255, T[ti + 2] * shade + 34 * (1 - z0));
      out[o + 3] = 255;
    }
  }
  bctx.putImageData(bufImg, 0, 0);
}

// stars behind the globe
const STARS = Array.from({ length: 160 }, () => [Math.random(), Math.random(), Math.random() * 1.2 + 0.2, Math.random() * 0.6 + 0.2]);

function drawFallbackEarth(rr) {
  // plain Earth colours if the satellite image cannot load
  const ocean = ctx.createRadialGradient(W / 2 - rr * .35, H / 2 - rr * .35, rr * .1, W / 2, H / 2, rr);
  ocean.addColorStop(0, "#2f7fd0"); ocean.addColorStop(1, "#0b2f63");
  ctx.beginPath(); path({ type: "Sphere" }); ctx.fillStyle = ocean; ctx.fill();
  if (land) {
    ctx.beginPath(); path(land); ctx.fillStyle = "#4f8a3c"; ctx.fill(); ctx.strokeStyle = "rgba(30,60,25,.6)"; ctx.lineWidth = .6; ctx.stroke();
    ctx.save(); ctx.beginPath(); path(land); ctx.clip();
    ctx.beginPath(); path(d3.geoCircle().center([0, 90]).radius(22)()); path(d3.geoCircle().center([0, -90]).radius(26)()); ctx.fillStyle = "#eef3f7"; ctx.fill();
    ctx.restore();
  }
}

function draw(now) {
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
  proj.translate([W / 2, H / 2]).scale(R * scaleK).rotate(rot);
  const rr = R * scaleK;
  // stars
  ctx.fillStyle = "#fff";
  for (const [sx, sy, sz, sa] of STARS) { ctx.globalAlpha = sa; ctx.fillRect(sx * W, sy * H, sz, sz); }
  ctx.globalAlpha = 1;
  // atmosphere glow
  const g = ctx.createRadialGradient(W / 2, H / 2, rr * .96, W / 2, H / 2, rr * 1.16);
  g.addColorStop(0, "rgba(120,180,255,.45)"); g.addColorStop(.35, "rgba(80,150,255,.16)"); g.addColorStop(1, "rgba(60,120,255,0)");
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(W / 2, H / 2, rr * 1.16, 0, 7); ctx.fill();
  // earth
  if (tex) {
    const key = rot.map(x => x.toFixed(3)).join() + "|" + rr.toFixed(1) + "|" + W + "x" + H;
    const moving = key !== lastKey;
    if (moving) { stillSince = now; lastKey = key; renderEarth(rr, 0.5); dirty = true; }
    else if (dirty && now - stillSince > 250) { renderEarth(rr, 1); dirty = false; }
    ctx.imageSmoothingEnabled = true; ctx.drawImage(buf, 0, 0, W, H);
  } else {
    drawFallbackEarth(rr);
  }
  // thin rim
  ctx.beginPath(); ctx.arc(W / 2, H / 2, rr, 0, 7); ctx.strokeStyle = "rgba(160,200,255,.35)"; ctx.lineWidth = 1; ctx.stroke();
  // stations
  const center = proj.invert([W / 2, H / 2]);
  const pulse = (Math.sin((now - t0) / 420) + 1) / 2;
  for (const s of STATIONS) {
    if (d3.geoDistance([s.lon, s.lat], center) > Math.PI / 2 - .02) continue;
    const [x, y] = proj([s.lon, s.lat]); const sel = selected === s;
    ctx.beginPath(); ctx.arc(x, y, sel ? 12 + pulse * 8 : 7 + pulse * 3, 0, 7); ctx.fillStyle = sel ? "rgba(255,201,77,.30)" : "rgba(255,201,77,.22)"; ctx.fill();
    ctx.beginPath(); ctx.arc(x, y, sel ? 6 : 4.5, 0, 7); ctx.fillStyle = "#ffc94d"; ctx.fill();
    ctx.lineWidth = 1.5; ctx.strokeStyle = "rgba(20,12,0,.7)"; ctx.stroke();
    if (sel || scaleK > 1.4) {
      ctx.font = "700 12.5px Vazirmatn, Tahoma, sans-serif"; ctx.textAlign = "center";
      ctx.lineWidth = 3.5; ctx.strokeStyle = "rgba(5,9,19,.85)"; ctx.strokeText(s.fa, x, y - 15);
      ctx.fillStyle = "#fff"; ctx.fillText(s.fa, x, y - 15);
    }
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

/* ---------------- speech: neural voice from the server, phone voice as fallback ---------------- */
const synth = window.speechSynthesis || null; let voices = [], playing = false, playToken = 0;
const audio = new Audio(); audio.preload = "auto";
function loadVoices() { if (synth) voices = synth.getVoices() || []; }
if (synth) { loadVoices(); synth.onvoiceschanged = loadVoices; }
function pickVoice() { const fa = voices.find(v => /^fa/i.test(v.lang)); if (fa) return { v: fa, lang: "fa" }; const en = voices.find(v => /^en/i.test(v.lang)); return { v: en || null, lang: "en" }; }
function setPlaying(on) { playing = on; $("ic-play").hidden = on; $("ic-pause").hidden = !on; $("eq").classList.toggle("on", on); $("play").setAttribute("aria-label", on ? "توقف" : "پخش"); }
function clearLive() { document.querySelectorAll(".item.live").forEach(x => x.classList.remove("live")); }
function markLive(i) { document.querySelectorAll(".item").forEach((x, j) => x.classList.toggle("live", j === i)); }
function stopSpeech() { playToken++; try { audio.pause(); audio.removeAttribute("src"); } catch (e) {} if (synth) synth.cancel(); setPlaying(false); clearLive(); }
const ttsUrl = (s, i) => `${window.API_BASE}/api/tts?sid=${encodeURIComponent(s.id)}&i=${i}&v=${encodeURIComponent(DATA.updated || "")}`;

function playUrl(url, token) {
  return new Promise((resolve, reject) => {
    if (token !== playToken) return resolve(false);
    audio.onended = () => resolve(true);
    audio.onerror = () => reject(new Error("audio"));
    audio.src = url;
    const p = audio.play(); if (p && p.catch) p.catch(reject);
  });
}
async function speakNeural(s) {
  const token = ++playToken;
  setPlaying(true); $("voice").textContent = "در حال آماده‌سازی صدای گوینده…";
  const order = [-1, ...s.news.map((_, i) => i)];
  for (let k = 0; k < order.length; k++) {
    if (token !== playToken) return true;
    const i = order[k];
    if (k + 1 < order.length) { const pre = new Audio(); pre.preload = "auto"; pre.src = ttsUrl(s, order[k + 1]); }  // warm the next item
    markLive(i);
    await playUrl(ttsUrl(s, i), token);
    if (k === 0) $("voice").textContent = "گوینده: دلارا · صدای عصبی فارسی";
  }
  if (token === playToken) { setPlaying(false); clearLive(); }
  return true;
}
function speakDevice(s) {
  if (!synth) { $("voice").textContent = "این مرورگر پخش صدا را پشتیبانی نمی‌کند."; setPlaying(false); return; }
  synth.cancel(); loadVoices();
  const pv = pickVoice();
  $("voice").textContent = pv.lang === "fa" ? "صدای دستگاه (صدای گوینده در دسترس نبود)" : "صدای فارسی روی این دستگاه نیست؛ نسخهٔ انگلیسی پخش می‌شود";
  const parts = [{ txt: pv.lang === "fa" ? `این‌جا رادیو کریپتو، ${s.fa}.` : `This is Crypto Radio, ${s.en}.`, i: -1 }];
  s.news.forEach((n, i) => parts.push({ txt: pv.lang === "fa" && n.lang !== "en" ? n.t + ". " + n.b : n.en, i }));
  setPlaying(true);
  parts.forEach((p, k) => {
    const u = new SpeechSynthesisUtterance(p.txt); u.lang = pv.lang === "fa" ? "fa-IR" : "en-US"; if (pv.v) u.voice = pv.v; u.rate = 0.92; u.pitch = 0.95;
    u.onstart = () => markLive(p.i);
    if (k === parts.length - 1) u.onend = () => { setPlaying(false); clearLive(); };
    u.onerror = () => { if (k === parts.length - 1) setPlaying(false); };
    synth.speak(u);
  });
}
async function speakStation(s) {
  if (window.SITE_MODE === "server") {
    try { await speakNeural(s); return; } catch (e) { /* fall back to the device voice */ }
  }
  stopSpeech(); speakDevice(s);
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
    d.innerHTML = `<b></b><p></p><div class="meta"><span class="num"></span><span class="ago"></span><a target="_blank" rel="noopener"></a></div>`;
    if (n.lang === "en") { d.querySelector("b").dir = "ltr"; d.querySelector("p").dir = "ltr"; }
    d.querySelector("b").textContent = n.t; d.querySelector("p").textContent = n.b; d.querySelector(".num").textContent = n.d;
    if (n.ts) { const ag = d.querySelector(".ago"); ag.dataset.ts = n.ts; ag.textContent = ago(n.ts); }
    if (n.kind === "official" || n.kind === "macro") { const k = document.createElement("span"); k.className = "kind " + n.kind; k.textContent = n.kind === "official" ? "منبع رسمی" : "اقتصاد کلان"; d.querySelector(".meta").prepend(k); }
    const a = d.querySelector("a"); a.textContent = n.source.name; a.href = n.source.url; nb.append(d);
  });
  if (s.live) renderNotes(s.notes, s.notes.length ? "تحلیل هوش مصنوعی روی خبرهای زنده" : "برای این خبرها هنوز تحلیلی نیامده؛ «تحلیل دوباره» را بزنید.");
  else renderNotes(s.notes, `تحلیل Claude هنگام جمع‌آوری خبرها (${DATA.updated_fa})`);
  tickClock();
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
  const live = Object.entries(marketNow).map(([c, v]) => `${c} ${fmtPrice(v.price)} (${(v.chg24h * 100).toFixed(2)}% 24h)`).join(", ");
  const M = window.MARKETS || {}, D = M.dominance;
  const macro = [M.gold && `gold ${M.gold.price.toFixed(0)} USD/oz`, M.wti && `WTI ${M.wti.price.toFixed(2)}`, M.brent && `Brent ${M.brent.price.toFixed(2)}`,
    D && `BTC dominance ${D.btc.toFixed(2)}%, USDT dominance ${D.usdt.toFixed(2)}%, total cap ${(D.total_mcap / 1e12).toFixed(2)}T`].filter(Boolean).join("; ");
  const m = (macro ? macro + "; " : "") + (live ? "live now: " + live : (DATA.market || []).map(x => `${x.c} ${x.p}`).join(", ") + " (" + DATA.market_date + ")");
  const prompt = `You are a crypto market analyst for a Persian-language Telegram channel.
Below are recent news items from one region (${s.en}). Decide which coins or market segments each item could move, and in which direction.
Reply with ONLY a JSON object like this (max 4 notes):
{"notes":[{"c":["BTC","ETH"],"dir":"up"|"down"|"mixed","n":"one sentence in Persian (Farsi), max 30 words, on the likely market effect","w":"short Persian reason or timing note, max 15 words, may be empty"}]}
Rules: no buy/sell advice, no price targets, no entry points. If an item has no real market effect, say so with dir "mixed". Use coin tickers in Latin letters.
Market context: ${m}.
NEWS:
${JSON.stringify(s.news.map(n => ({ date: n.d, title: n.en })), null, 1)}`;
  try {
    const res = await AI.ask(prompt, { json: true, signal: ctl.signal });
    const arr = Array.isArray(res) ? res : (res && res.notes);
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
setInterval(tickClock, 1000); tickClock();

/* refresh live news every 2 minutes (the server refreshes its feeds every 10) */
if (window.SITE_MODE === "server") {
  setInterval(async () => {
    if (document.hidden) return;
    try {
      const j = await (await fetch(dataUrl)).json();
      if (!j.stations || (j.updated === DATA.updated && j.live === DATA.live)) return;
      DATA = j; STATIONS = j.stations.filter(s => s.news && s.news.length);
      const keep = STATIONS.find(s => s.id === (selected && selected.id)) || STATIONS[0];
      selected = keep; renderUpdated(); renderDial(); if (!playing) renderSheet(keep);
    } catch (e) {}
  }, DATA.live ? 120000 : 20000);
}
})();
