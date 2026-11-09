/* desk.js — load multi-agent desk opinions into the floor panel */
(function () {
  function isEN() {
    if (window.LANG === "en") return true;
    if (window.LANG === "fa") return false;
    var lang = (document.documentElement.lang || "").toLowerCase();
    if (lang.indexOf("en") === 0) return true;
    if (location.pathname.indexOf("/en") === 0) return true;
    return false;
  }
  function activeSym() {
    var btn = document.querySelector("#fl-coins button[aria-pressed='true']");
    return (btn && btn.dataset.s) || "BTC";
  }
  function render(data) {
    var box = document.getElementById("desk-agents");
    if (!box || !data || !data.agents) return;
    var EN = isEN();
    box.innerHTML = "";
    // Top bias pill
    var pillWrap = document.createElement("div");
    pillWrap.style.cssText = "grid-column:1/-1;display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;";
    var pill = document.createElement("span");
    var pclass = (data.agents.find(function(a){return a.id==="chief";}) || {}).pill || "flat";
    pill.className = "fl-bias-pill " + pclass;
    var chief = data.agents.find(function(a){return a.id==="chief";}) || {};
    pill.textContent = EN ? (chief.en || "").split("·")[0] : (chief.fa || "").split("·")[0];
    var tf = document.createElement("span");
    tf.className = "fl-tf";
    tf.textContent = EN ? (data.tf_label_en || "1h") : (data.tf_label_fa || "۱ ساعت");
    pillWrap.appendChild(pill);
    pillWrap.appendChild(tf);
    box.appendChild(pillWrap);
    data.agents.forEach(function (a) {
      var card = document.createElement("div");
      card.style.cssText = "background:#111827;border-radius:10px;padding:10px 12px;border-left:4px solid " + (a.color || "#64748b") + ";";
      var name = document.createElement("div");
      name.style.cssText = "font-weight:700;font-size:13px;color:" + (a.color || "#e2e8f0") + ";margin-bottom:4px;";
      name.textContent = a.name;
      var txt = document.createElement("div");
      txt.style.cssText = "font-size:12.5px;line-height:1.45;color:#e2e8f0;white-space:pre-wrap;";
      txt.textContent = EN ? (a.en || a.fa) : (a.fa || a.en);
      card.appendChild(name);
      card.appendChild(txt);
      box.appendChild(card);
    });
  }
  async function load() {
    var sym = activeSym();
    var box = document.getElementById("desk-agents");
    if (box) box.innerHTML = "<div style='opacity:.6;padding:8px;'>Loading desk…</div>";
    try {
      var r = await fetch((window.API_BASE || "") + "/api/desk/" + encodeURIComponent(sym));
      var j = await r.json();
      if (j && j.ok) render(j);
      else if (box) box.innerHTML = "<div style='color:#f87171;padding:8px;'>Desk unavailable</div>";
    } catch (e) {
      if (box) box.innerHTML = "<div style='color:#f87171;padding:8px;'>Network error</div>";
    }
  }
  function boot() {
    var panel = document.getElementById("desk-panel");
    if (!panel) return;
    load();
    var btn = document.getElementById("desk-refresh");
    if (btn) btn.addEventListener("click", load);
    document.addEventListener("click", function (e) {
      if (e.target && e.target.closest && e.target.closest("#fl-coins button")) {
        setTimeout(load, 600);
      }
    });
    setInterval(load, 45000);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
