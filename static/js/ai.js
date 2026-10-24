/* CryptoAI — one AI entry point for every page.
   SITE_MODE "server": calls the Flask backend (/api/ai → Groq or whatever ai_client.py is set to).
   SITE_MODE "static": hosted preview on claude.ai → uses Claude through the page's `sample` capability.
   Usage: await AI.ask(prompt, {json:true, images:[file], onText}) */
(function () {
  const base = () => (window.API_BASE || "");
  let samplePromise = null;
  function sample() {
    if (!samplePromise) {
      samplePromise = (async () => {
        try { return window.claude ? await window.claude.use("sample") : null; } catch (e) { return null; }
      })();
    }
    return samplePromise;
  }
  const ERR = {
    not_granted: "اجازهٔ استفاده از Claude داده نشد.",
    sampling_disabled: "Claude برای این حساب فعال نیست.",
    rate_limited: "درخواست زیاد بود؛ کمی بعد دوباره امتحان کنید.",
    session_expired: "دوباره وارد حساب شوید.",
    invalid_json: "پاسخ هوش مصنوعی قابل خواندن نبود؛ دوباره امتحان کنید.",
    image_rejected: "این تصویر قابل خواندن نبود؛ تصویر دیگری بفرستید.",
    no_ai: "هوش مصنوعی در دسترس نیست. روی سرور، کلید GROQ_API_KEY را تنظیم کنید.",
    cancelled: "متوقف شد."
  };
  function parseJSON(text) {
    try { return JSON.parse(text); } catch (e) {}
    const m = text.match(/```(?:json)?\s*([\s\S]*?)```/); if (m) { try { return JSON.parse(m[1]); } catch (e) {} }
    const a = text.search(/[\[{]/), b = Math.max(text.lastIndexOf("]"), text.lastIndexOf("}"));
    if (a >= 0 && b > a) { try { return JSON.parse(text.slice(a, b + 1)); } catch (e) {} }
    throw { code: "invalid_json" };
  }
  const AI = {
    errorText(e) { return ERR[e && e.code] || (e && e.message) || "خطا در ارتباط؛ دوباره امتحان کنید."; },
    async status() {
      if (window.SITE_MODE === "server") {
        try {
          const r = await fetch(base() + "/api/ai/status"); const j = await r.json();
          return { ok: !!j.ok, images: !!j.images, label: j.ok ? "هوش مصنوعی: " + j.provider : "سرور آنلاین · بدون کلید AI" };
        } catch (e) { return { ok: false, images: false, label: "سرور در دسترس نیست" }; }
      }
      const s = await sample();
      if (!s) return { ok: false, images: false, label: "پیش‌نمایش · بدون AI" };
      const lim = await s.limits().catch(() => null);
      return { ok: true, images: !!(lim && lim.images), label: "هوش مصنوعی: Claude" };
    },
    async ask(prompt, opts = {}) {
      if (window.SITE_MODE === "server") {
        const r = await fetch(base() + "/api/ai", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt, json: !!opts.json }), signal: opts.signal
        });
        const j = await r.json().catch(() => ({ ok: false }));
        if (!j.ok) throw { code: j.code || "no_ai", message: j.error };
        if (opts.onText) opts.onText({ text: j.text });
        return opts.json ? parseJSON(j.text) : j.text;
      }
      const s = await sample();
      if (!s) throw { code: "no_ai" };
      const o = { modelTier: "default", signal: opts.signal };
      if (opts.images) { o.images = opts.images; o.cache = false; }
      if (opts.onText && !opts.json) o.onText = opts.onText;
      if (opts.json) return await s.json(prompt, o);
      const { text } = await s(prompt, o);
      return text;
    }
  };
  window.AI = AI;
})();
