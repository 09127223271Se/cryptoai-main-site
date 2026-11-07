/* chart-projections.js — dotted if-break paths on the live floor chart (no entry points). */
(function () {
  function usd(v) {
    if (v == null || !isFinite(v)) return "—";
    return v >= 1000 ? "$" + Math.round(v).toLocaleString("en-US") : "$" + v.toFixed(2);
  }

  function ensureProj(c) {
    if (!c || c.res == null || c.sup == null) return c;
    var rng = Math.max(c.res - c.sup, (c.price || c.res) * 0.004);
    if (c.proj_up == null) c.proj_up = Math.max(c.res + rng, c.p75 || (c.res + rng));
    if (c.proj_dn == null) c.proj_dn = Math.min(c.sup - rng, c.p25 || (c.sup - rng));
    if (c.broke_res == null) c.broke_res = c.price > c.res;
    if (c.broke_sup == null) c.broke_sup = c.price < c.sup;
    return c;
  }

  function drawProjections(x, c, Y, L, Rk, Rz, px, py, EN) {
    if (!c || !c.res || !c.sup) return;
    ensureProj(c);
    var gold = "#ffc94d", dn = "#ff4fa3";
    var midX = L + (Rk - L) * 0.62;
    var midX2 = L + (Rk - L) * 0.72;

    if (c.proj_up) {
      var yRes = Y(c.res), yUp = Y(c.proj_up);
      x.setLineDash([4, 5]); x.strokeStyle = gold; x.lineWidth = 1.6;
      x.globalAlpha = c.broke_res ? 1 : 0.8;
      x.beginPath(); x.moveTo(midX, yRes); x.lineTo(midX, yUp); x.stroke();
      x.beginPath(); x.moveTo(midX, yUp); x.lineTo(Rz, yUp); x.stroke();
      x.setLineDash([]); x.lineWidth = 1; x.globalAlpha = 1;
      x.globalAlpha = 0.12; x.fillStyle = gold;
      x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, yUp); x.lineTo(Rz, yRes); x.closePath(); x.fill();
      x.globalAlpha = 1;
      x.fillStyle = gold;
      x.font = "600 11px IBM Plex Mono, Vazirmatn, monospace";
      x.fillText(usd(c.proj_up), Rz + 4, yUp + 4);
      x.font = "10px Vazirmatn, sans-serif";
      x.fillText(EN ? (c.broke_res ? "after RES break" : "if RES breaks") : (c.broke_res ? "پس از شکست مقاومت" : "اگر مقاومت بشکند"), Rz + 4, yUp + 16);
      x.beginPath(); x.arc(midX, yRes, 3.2, 0, 7); x.fill();
    }

    if (c.proj_dn) {
      var ySup = Y(c.sup), yDn = Y(c.proj_dn);
      x.setLineDash([4, 5]); x.strokeStyle = dn; x.lineWidth = 1.6;
      x.globalAlpha = c.broke_sup ? 1 : 0.8;
      x.beginPath(); x.moveTo(midX2, ySup); x.lineTo(midX2, yDn); x.stroke();
      x.beginPath(); x.moveTo(midX2, yDn); x.lineTo(Rz, yDn); x.stroke();
      x.setLineDash([]); x.lineWidth = 1; x.globalAlpha = 1;
      x.globalAlpha = 0.12; x.fillStyle = dn;
      x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, yDn); x.lineTo(Rz, ySup); x.closePath(); x.fill();
      x.globalAlpha = 1;
      x.fillStyle = dn;
      x.font = "600 11px IBM Plex Mono, Vazirmatn, monospace";
      x.fillText(usd(c.proj_dn), Rz + 4, yDn + 4);
      x.font = "10px Vazirmatn, sans-serif";
      x.fillText(EN ? (c.broke_sup ? "after SUP break" : "if SUP breaks") : (c.broke_sup ? "پس از شکست حمایت" : "اگر حمایت بشکند"), Rz + 4, yDn + 16);
      x.beginPath(); x.arc(midX2, ySup, 3.2, 0, 7); x.fill();
    }
  }

  function setupOverlay() {
    var host = document.getElementById("fl-chart");
    if (!host || host.dataset.proj === "1") return;
    host.dataset.proj = "1";
    var wrap = host.parentElement;
    if (!wrap) return;
    if (!wrap.style.position || wrap.style.position === "static") wrap.style.position = "relative";
    var ov = document.createElement("canvas");
    ov.id = "fl-chart-proj";
    ov.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:2;";
    wrap.appendChild(ov);

    async function redraw() {
      var symBtn = document.querySelector("#fl-coins button[aria-pressed='true']");
      var sym = (symBtn && symBtn.dataset.s) || "BTC";
      var c;
      try {
        c = await (await fetch((window.API_BASE || "") + "/api/coin/" + sym)).json();
      } catch (e) { return; }
      if (!c || !c.ok || !c.candles) return;
      ensureProj(c);
      var dpr = devicePixelRatio || 1;
      var W = host.clientWidth, H = host.clientHeight;
      if (W < 40 || H < 40) return;
      ov.width = W * dpr; ov.height = H * dpr;
      var x = ov.getContext("2d");
      x.setTransform(dpr, 0, 0, dpr, 0, 0);
      x.clearRect(0, 0, W, H);
      var k = c.candles;
      var extra = [c.p05, c.p95, c.res, c.sup, c.proj_up, c.proj_dn].filter(function (v) { return v != null; });
      var vals = k.flatMap(function (r) { return [r[2], r[3]]; }).concat(extra);
      var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
      var pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
      var L = 4, Rk = W - 130, Rz = W - 66, Tp = 8, B = H - 10;
      var Y = function (v) { return B - (v - lo) / (hi - lo) * (B - Tp); };
      var px = Rk + 4, py = Y(c.price);
      var EN = !!(window.LANG && window.LANG !== "fa");
      drawProjections(x, c, Y, L, Rk, Rz, px, py, EN);
    }

    redraw();
    setInterval(redraw, 20000);
    document.addEventListener("click", function (e) {
      if (e.target && e.target.closest && e.target.closest("#fl-coins button")) setTimeout(redraw, 500);
    });
    window.addEventListener("resize", function () { setTimeout(redraw, 200); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setupOverlay);
  else setupOverlay();
  var tries = 0;
  var t = setInterval(function () {
    setupOverlay();
    if (++tries > 25) clearInterval(t);
  }, 400);
})();
