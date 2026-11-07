/* floor.js — base floor + dotted if-break projection overlay */
(function () {
  var s = document.createElement("script");
  s.src = "https://cdn.jsdelivr.net/gh/09127223271Se/cryptoai-main-site@75d95e5ffc608eadba8dcfaa811e4bcbd3058ca5/static/js/floor.js";
  s.onload = function () {
    var host = document.getElementById("fl-chart");
    if (!host) return;
    var wrap = host.parentElement;
    if (!wrap || wrap.querySelector("#fl-chart-proj")) return;
    wrap.style.position = "relative";
    var ov = document.createElement("canvas");
    ov.id = "fl-chart-proj";
    ov.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:5;";
    wrap.appendChild(ov);
    function usd(v) {
      if (v == null || !isFinite(v)) return "—";
      return v >= 1000 ? "$" + Math.round(v).toLocaleString("en-US") : "$" + Number(v).toFixed(2);
    }
    async function redraw() {
      var btn = document.querySelector("#fl-coins button[aria-pressed='true']");
      var sym = (btn && btn.dataset.s) || "BTC";
      var c;
      try { c = await (await fetch((window.API_BASE||"") + "/api/coin/" + sym)).json(); } catch (e) { return; }
      if (!c || !c.candles || !c.res || !c.sup) return;
      var rng = Math.max((c.res - c.sup) || 0, (c.price || 1) * 0.004);
      var projUp = Math.max((c.res || 0) + rng, c.p75 || 0);
      var projDn = Math.min((c.sup || 0) - rng, c.p25 || 0);
      var dpr = devicePixelRatio || 1, W = host.clientWidth, H = host.clientHeight;
      if (W < 40 || H < 40) return;
      ov.width = W * dpr; ov.height = H * dpr;
      var x = ov.getContext("2d");
      x.setTransform(dpr, 0, 0, dpr, 0, 0);
      x.clearRect(0, 0, W, H);
      var k = c.candles;
      var vals = k.flatMap(function(r){return [r[2],r[3]];}).concat([c.p05,c.p95,c.res,c.sup,projUp,projDn].filter(function(v){return v!=null;}));
      var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
      var pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
      var L = 4, Rk = W - 130, Rz = W - 66, Tp = 8, B = H - 10;
      var Y = function(v){ return B - (v - lo) / (hi - lo) * (B - Tp); };
      var px = Rk + 4, py = Y(c.price);
      var EN = window.LANG === "en";
      var gold = "#ffc94d", dn = "#ff4fa3";
      var midX = L + (Rk - L) * 0.62, midX2 = L + (Rk - L) * 0.72;
      var brokeRes = c.price > c.res, brokeSup = c.price < c.sup;
      var yRes = Y(c.res), yUp = Y(projUp);
      x.setLineDash([4,5]); x.strokeStyle = gold; x.lineWidth = 2; x.globalAlpha = 0.95;
      x.beginPath(); x.moveTo(midX, yRes); x.lineTo(midX, yUp); x.stroke();
      x.beginPath(); x.moveTo(midX, yUp); x.lineTo(Rz-2, yUp); x.stroke();
      x.setLineDash([]); x.lineWidth = 1; x.globalAlpha = 0.18; x.fillStyle = gold;
      x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, yUp); x.lineTo(Rz, yRes); x.closePath(); x.fill();
      x.globalAlpha = 1; x.fillStyle = gold; x.font = "700 12px monospace";
      x.fillText(usd(projUp), Rz + 4, yUp + 3);
      x.font = "11px Vazirmatn,sans-serif";
      x.fillText(EN ? (brokeRes ? "after RES break" : "if RES breaks") : (brokeRes ? "پس از شکست مقاومت" : "اگر مقاومت بشکند"), Rz + 4, yUp + 17);
      x.beginPath(); x.arc(midX, yRes, 4, 0, 7); x.fill();
      var ySup = Y(c.sup), yDn = Y(projDn);
      x.setLineDash([4,5]); x.strokeStyle = dn; x.lineWidth = 2; x.globalAlpha = 0.95;
      x.beginPath(); x.moveTo(midX2, ySup); x.lineTo(midX2, yDn); x.stroke();
      x.beginPath(); x.moveTo(midX2, yDn); x.lineTo(Rz-2, yDn); x.stroke();
      x.setLineDash([]); x.lineWidth = 1; x.globalAlpha = 0.18; x.fillStyle = dn;
      x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, yDn); x.lineTo(Rz, ySup); x.closePath(); x.fill();
      x.globalAlpha = 1; x.fillStyle = dn; x.font = "700 12px monospace";
      x.fillText(usd(projDn), Rz + 4, yDn + 3);
      x.font = "11px Vazirmatn,sans-serif";
      x.fillText(EN ? (brokeSup ? "after SUP break" : "if SUP breaks") : (brokeSup ? "پس از شکست حمایت" : "اگر حمایت بشکند"), Rz + 4, yDn + 17);
      x.beginPath(); x.arc(midX2, ySup, 4, 0, 7); x.fill();
    }
    setTimeout(redraw, 800);
    setTimeout(redraw, 2500);
    setInterval(redraw, 12000);
    document.addEventListener("click", function(e){
      if (e.target && e.target.closest && e.target.closest("#fl-coins button")) setTimeout(redraw, 600);
    });
    window.addEventListener("resize", function(){ setTimeout(redraw, 200); });
  };
  document.head.appendChild(s);
})();
