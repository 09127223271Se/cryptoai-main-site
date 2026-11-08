/* floor.js — base floor + sharp if-break projection overlay */
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
    function isEN() {
      if (window.LANG === "en") return true;
      if (window.LANG === "fa") return false;
      var lang = (document.documentElement.lang || "").toLowerCase();
      if (lang.indexOf("en") === 0) return true;
      if (location.pathname.indexOf("/en") === 0) return true;
      return false;
    }
    function label(x, text, color, tx, ty) {
      x.font = "700 11px IBM Plex Mono, ui-monospace, monospace";
      x.textBaseline = "middle";
      var padX = 5, padY = 3;
      var w = x.measureText(text).width;
      var bx = Math.round(tx), by = Math.round(ty);
      x.fillStyle = "rgba(8,12,28,0.88)";
      x.fillRect(bx - 2, by - 8, w + padX * 2, 16);
      x.fillStyle = color;
      x.fillText(text, bx + padX - 2, by + 0.5);
    }

    async function redraw() {
      var btn = document.querySelector("#fl-coins button[aria-pressed='true']");
      var sym = (btn && btn.dataset.s) || "BTC";
      var c;
      try { c = await (await fetch((window.API_BASE || "") + "/api/coin/" + sym)).json(); } catch (e) { return; }
      if (!c || !c.candles || !c.res || !c.sup) return;
      var rng = Math.max((c.res - c.sup) || 0, (c.price || 1) * 0.004);
      var projUp = Math.max((c.res || 0) + rng, c.p75 || 0);
      var projDn = Math.min((c.sup || 0) - rng, c.p25 || 0);
      var dpr = Math.min(window.devicePixelRatio || 1, 3);
      var W = host.clientWidth, H = host.clientHeight;
      if (W < 40 || H < 40) return;
      ov.width = Math.round(W * dpr);
      ov.height = Math.round(H * dpr);
      var x = ov.getContext("2d");
      x.setTransform(dpr, 0, 0, dpr, 0, 0);
      x.imageSmoothingEnabled = false;
      x.clearRect(0, 0, W, H);
      var k = c.candles;
      var vals = k.flatMap(function (r) { return [r[2], r[3]]; }).concat([c.p05, c.p95, c.res, c.sup, projUp, projDn].filter(function (v) { return v != null; }));
      var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
      var pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
      var L = 4, Rk = W - 138, Rz = W - 72, Tp = 8, B = H - 10;
      var Y = function (v) { return B - (v - lo) / (hi - lo) * (B - Tp); };
      var px = Rk + 4, py = Y(c.price);
      var EN = isEN();
      var gold = "#ffd666", dn = "#ff6bb5";
      var midX = Math.round(L + (Rk - L) * 0.58);
      var midX2 = Math.round(L + (Rk - L) * 0.70);
      var brokeRes = c.price > c.res, brokeSup = c.price < c.sup;

      // upside path
      var yRes = Math.round(Y(c.res)), yUp = Math.round(Y(projUp));
      x.setLineDash([5, 5]); x.strokeStyle = gold; x.lineWidth = 2; x.globalAlpha = 1;
      x.beginPath(); x.moveTo(midX, yRes); x.lineTo(midX, yUp); x.stroke();
      x.beginPath(); x.moveTo(midX, yUp); x.lineTo(Rz, yUp); x.stroke();
      x.setLineDash([]);
      x.globalAlpha = 0.14; x.fillStyle = gold;
      x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, yUp); x.lineTo(Rz, yRes); x.closePath(); x.fill();
      x.globalAlpha = 1;
      x.fillStyle = gold; x.beginPath(); x.arc(midX, yRes, 3.5, 0, 7); x.fill();
      label(x, usd(projUp), gold, Rz + 2, yUp - 10);
      label(x, EN ? (brokeRes ? "after RES break" : "if RES breaks") : (brokeRes ? "پس از شکست مقاومت" : "اگر مقاومت بشکند"), gold, Rz + 2, yUp + 8);

      // downside path
      var ySup = Math.round(Y(c.sup)), yDn = Math.round(Y(projDn));
      x.setLineDash([5, 5]); x.strokeStyle = dn; x.lineWidth = 2;
      x.beginPath(); x.moveTo(midX2, ySup); x.lineTo(midX2, yDn); x.stroke();
      x.beginPath(); x.moveTo(midX2, yDn); x.lineTo(Rz, yDn); x.stroke();
      x.setLineDash([]);
      x.globalAlpha = 0.14; x.fillStyle = dn;
      x.beginPath(); x.moveTo(px, py); x.lineTo(Rz, yDn); x.lineTo(Rz, ySup); x.closePath(); x.fill();
      x.globalAlpha = 1;
      x.fillStyle = dn; x.beginPath(); x.arc(midX2, ySup, 3.5, 0, 7); x.fill();
      label(x, usd(projDn), dn, Rz + 2, yDn - 10);
      label(x, EN ? (brokeSup ? "after SUP break" : "if SUP breaks") : (brokeSup ? "پس از شکست حمایت" : "اگر حمایت بشکند"), dn, Rz + 2, yDn + 8);
    }

    setTimeout(redraw, 900);
    setTimeout(redraw, 2500);
    setInterval(redraw, 12000);
    document.addEventListener("click", function (e) {
      if (e.target && e.target.closest && e.target.closest("#fl-coins button")) setTimeout(redraw, 600);
    });
    window.addEventListener("resize", function () { setTimeout(redraw, 200); });
  };
  document.head.appendChild(s);
})();
