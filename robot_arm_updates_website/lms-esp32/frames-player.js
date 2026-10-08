// Step player: shows a step model's pre-rendered frames (made by render_frames.py) instead of a live 3D model.
// Drag sideways (or use the arrow keys) to turn it; changing step plays the move between steps where there is one.
//   const p = FramesPlayer(host, window.FRAMES, 'frames/hub/', tags, tagClass); p.setStep(2);
// p.setBase('frames/wiring/2/') swaps to another set of the same frames (another cable colour set).
// tags: [{ html, cls, tf }] laid over the frame at the positions stored per frame (tf: the CSS transform from that point).
// tagClass(i, step): extra classes for tag i in that step.
function FramesPlayer(host, F, base, tagDefs, tagClass) {
  const C = F.center, reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  host.style.background = F.bg;
  const view = document.createElement('div'); view.className = 'fp-view'; host.prepend(view);
  const imgs = [0, 1].map(() => { const im = document.createElement('img'); im.alt = ''; im.draggable = false; view.appendChild(im); return im; });
  const tags = tagDefs.map(d => {
    const el = document.createElement('div'); el.className = 'tag ' + (d.cls || ''); el.innerHTML = d.html;
    el.style.transform = d.tf; el.style.display = 'none'; view.appendChild(el); return el;
  });
  const stepUrl = (s, k) => `${base}s${s}-${k}.webp`, moveUrl = (key, k) => `${base}t${key.replace('-', '')}-${k + 1}.webp`;

  // Keep the frame's shape, as large as fits
  function fit() {
    const W = host.clientWidth, H = host.clientHeight, s = Math.min(W / F.w, H / F.h);
    Object.assign(view.style, { width: F.w * s + 'px', height: F.h * s + 'px', left: (W - F.w * s) / 2 + 'px', top: (H - F.h * s) / 2 + 'px' });
  }
  new ResizeObserver(fit).observe(host); fit();

  // Show a frame once it is decoded (two images, swapped, so nothing flickers)
  let front = 0, wanted = '';
  function show(url, pts) {
    wanted = url;
    const back = imgs[1 - front];
    back.src = url;
    return (back.decode ? back.decode() : new Promise(r => { back.onload = back.onerror = r; })).catch(() => {}).then(() => {
      if (wanted !== url) return;
      imgs.forEach(im => { im.style.visibility = im === back ? 'visible' : 'hidden'; }); front = imgs.indexOf(back);
      tags.forEach((el, i) => {
        const p = pts[i];
        el.style.display = p ? '' : 'none';
        if (p) { el.style.left = p[0] * 100 + '%'; el.style.top = p[1] * 100 + '%'; }
      });
    });
  }

  // Load the frames in the background: this step's (middle out), its moves, then every step's middle frame
  const loading = new Set();
  function preload(urls) { urls.forEach(u => { const im = new Image(); loading.add(im); im.onload = im.onerror = () => loading.delete(im); im.src = u; }); }
  function preloadStep(s) {
    const order = [...Array(F.n).keys()].sort((a, b) => Math.abs(a - C) - Math.abs(b - C));
    preload(order.map(k => stepUrl(s, k)));
    Object.keys(F.trans).filter(key => key.split('-').includes(String(s))).forEach(key => preload([...Array(F.trans[key].n).keys()].map(k => moveUrl(key, k))));
  }

  let step = 0, k = C, playing = 0;
  const frame = () => show(stepUrl(step, k), F.steps[step].tags[k]);
  function classes() { tags.forEach((el, i) => { el.className = 'tag ' + (tagDefs[i].cls || '') + ' ' + (tagClass ? tagClass(i, step) : ''); }); }

  async function setStep(s) {
    const from = step, my = ++playing;
    step = s; preloadStep(s); classes();
    const fwd = F.trans[`${from}-${s}`], back = F.trans[`${s}-${from}`];
    const move = !reduce && (fwd || back);
    if (move) {
      const key = fwd ? `${from}-${s}` : `${s}-${from}`, ks = [...Array(move.n).keys()];
      if (!fwd) ks.reverse();
      for (const j of ks) {
        const t0 = performance.now();
        await show(moveUrl(key, j), move.tags[j]);
        if (my !== playing) return;
        const wait = 45 - (performance.now() - t0);
        if (wait > 0) await new Promise(r => setTimeout(r, wait));
        if (my !== playing) return;
      }
      k = C;
    }
    frame();
  }

  // Drag to turn: dragging right turns the near side of the model to the right
  let drag = null;
  host.addEventListener('pointerdown', e => { playing++; drag = { x: e.clientX, k }; host.setPointerCapture(e.pointerId); });
  host.addEventListener('pointermove', e => {
    if (!drag) return;
    const per = Math.max(10, view.clientWidth / (F.n * 1.6));
    const nk = Math.max(0, Math.min(F.n - 1, drag.k - Math.round((e.clientX - drag.x) / per)));
    if (nk !== k) { k = nk; frame(); }
  });
  const end = () => { drag = null; };
  host.addEventListener('pointerup', end); host.addEventListener('pointercancel', end);
  host.tabIndex = 0;
  host.addEventListener('keydown', e => {
    const d = { ArrowLeft: 1, ArrowRight: -1 }[e.key];
    if (!d) return;
    e.preventDefault(); playing++;
    k = Math.max(0, Math.min(F.n - 1, k + d)); frame();
  });

  classes(); frame(); preloadStep(0);
  preload(F.steps.map((_, s) => stepUrl(s, C)));
  function setBase(b) { base = b; playing++; preloadStep(step); preload(F.steps.map((_, s) => stepUrl(s, C))); return frame(); }
  return { setStep, setBase };
}
