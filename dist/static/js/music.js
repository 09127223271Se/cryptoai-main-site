/* CryptoAI — optional background music. Off by default; one small button.
   • If the site has MUSIC_EMBED (an official Spotify/YouTube embed URL set in Render), the button opens that player.
   • Otherwise it plays an original lo-fi loop generated live in the browser (Web Audio): soft chords, bass and a quiet beat.
   No audio files are hosted, so there is nothing to license. */
(() => {
  const btn = document.getElementById("music-btn"); if (!btn) return;
  const EN = window.LANG === "en", embed = window.MUSIC_EMBED || "";
  let ctx = null, master = null, timer = null, on = false, panel = null, step = 0;
  const label = () => btn.setAttribute("aria-pressed", on ? "true" : "false");

  /* ---------- official embed (Spotify / YouTube) ---------- */
  function toggleEmbed() {
    if (!panel) {
      panel = document.createElement("div"); panel.className = "music-panel";
      const f = document.createElement("iframe");
      f.src = embed; f.allow = "autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture";
      f.loading = "lazy"; f.title = EN ? "Music player" : "پخش‌کنندهٔ موزیک";
      const x = document.createElement("button"); x.type = "button"; x.className = "music-x"; x.textContent = "×"; x.setAttribute("aria-label", EN ? "Close" : "بستن");
      x.onclick = () => { panel.remove(); panel = null; on = false; label(); };
      panel.append(x, f); document.body.append(panel);
      on = true;
    } else { panel.remove(); panel = null; on = false; }
    label();
  }

  /* ---------- original generative lo-fi ---------- */
  const N = m => 440 * Math.pow(2, (m - 69) / 12);
  const CHORDS = [[57, 60, 64, 67], [53, 57, 60, 64], [48, 52, 55, 59], [55, 59, 62, 65]];   // Am7 Fmaj7 Cmaj7 G7
  function voice(freq, t, dur, type, vol, dest) {
    const o = ctx.createOscillator(), g = ctx.createGain(), f = ctx.createBiquadFilter();
    o.type = type; o.frequency.value = freq; f.type = "lowpass"; f.frequency.value = 1400;
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vol, t + 0.08); g.gain.exponentialRampToValueAtTime(0.0008, t + dur);
    o.connect(f); f.connect(g); g.connect(dest); o.start(t); o.stop(t + dur + 0.05);
  }
  function noise(t, dur, vol, hp) {
    const b = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate), d = b.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
    const s = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    s.buffer = b; f.type = hp ? "highpass" : "lowpass"; f.frequency.value = hp ? 7000 : 300; g.gain.value = vol;
    s.connect(f); f.connect(g); g.connect(master); s.start(t);
  }
  function kick(t) {
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.setValueAtTime(110, t); o.frequency.exponentialRampToValueAtTime(42, t + 0.18);
    g.gain.setValueAtTime(0.5, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.3);
    o.connect(g); g.connect(master); o.start(t); o.stop(t + 0.32);
  }
  const BEAT = 60 / 72;                                   // 72 bpm
  function schedule() {
    const t0 = ctx.currentTime + 0.05;
    for (let i = 0; i < 4; i++) {                          // one bar per call
      const t = t0 + i * BEAT, bar = Math.floor(step / 4) % CHORDS.length, ch = CHORDS[bar];
      if (i === 0) ch.forEach((m, k) => voice(N(m), t + k * 0.012, BEAT * 4.2, "triangle", 0.035, master));
      if (i === 0 || i === 2) voice(N(ch[0] - 24), t, BEAT * 1.6, "sine", 0.12, master);
      if (i === 0 || i === 2) kick(t);
      if (i === 1 || i === 3) noise(t, 0.18, 0.08, false);
      noise(t + BEAT / 2, 0.05, 0.035, true); noise(t, 0.05, 0.025, true);
      if (Math.random() < 0.45) voice(N(ch[1 + Math.floor(Math.random() * 3)] + 12), t + BEAT * (Math.random() < .5 ? 0 : .5), BEAT, "sine", 0.03, master);
      step++;
    }
  }
  function startSynth() {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume();
    master = ctx.createGain(); master.gain.value = 0; master.connect(ctx.destination);
    master.gain.linearRampToValueAtTime(0.55, ctx.currentTime + 1.5);
    schedule(); timer = setInterval(schedule, BEAT * 4 * 1000);
    on = true; label();
  }
  function stopSynth() {
    clearInterval(timer); timer = null;
    if (master) { const m = master; m.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.6); setTimeout(() => m.disconnect(), 800); }
    on = false; label();
  }
  btn.onclick = () => embed ? toggleEmbed() : (on ? stopSynth() : startSynth());
  label();
})();
