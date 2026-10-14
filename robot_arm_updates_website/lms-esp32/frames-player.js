// Step player: shows a step model's pre-rendered frames (made by render_frames.py) instead of a live 3D model.
// Drag sideways (or use the arrow keys) to turn it, and up or down to look from higher or lower when the frames
// have several heights (F.rows); changing step plays the move between steps where there is one.
//   const p = FramesPlayer(host, window.FRAMES, 'frames/hub/', tags, tagClass); p.setStep(2);
// p.setBase('frames/wiring/2/') swaps to another set of the same frames (another cable colour set).
// tags: [{ html, cls, tf, lead }] laid over the frame at the positions stored per frame (tf: the CSS transform from that
// point). lead: [dx, dy] in px puts the label that far away, joined to its point by a line, so it doesn't hide it.
// tagClass(i, step): extra classes for tag i in that step.
function FramesPlayer(host, F, base, tagDefs, tagClass) {
  const C = F.center, ROWS = F.rows || 1, RC = F.rowCenter || 0, reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  host.style.background = F.bg;
  const view = document.createElement('div'); view.className = 'fp-view'; host.prepend(view);
  const imgs = [0, 1].map(() => { const im = document.createElement('img'); im.alt = ''; im.draggable = false; view.appendChild(im); return im; });
  const tags = tagDefs.map(d => {
    const box = document.createElement('div'); box.className = 'tag-at'; box.style.display = 'none';
    const [dx, dy] = d.lead || [0, 0];
    if (d.lead) box.innerHTML = `<svg class="lead" width="1" height="1"><line x1="0" y1="0" x2="${dx}" y2="${dy}"/></svg><span class="pin"></span>`;
    const label = document.createElement('div'); label.className = 'tag ' + (d.cls || ''); label.innerHTML = d.html;
    label.style.transform = `translate(${dx}px, ${dy}px) ${d.tf}`; box.appendChild(label); view.appendChild(box);
    return { box, label };
  });
  const stepUrl = (s, r, k) => ROWS > 1 ? `${base}s${s}-${r}-${k}.webp` : `${base}s${s}-${k}.webp`;
  const stepTags = (s, r, k) => ROWS > 1 ? F.steps[s].tags[r][k] : F.steps[s].tags[k];
  const moveUrl = (key, k) => `${base}t${key.replace('-', '')}-${k + 1}.webp`;

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
      tags.forEach(({ box }, i) => {
        const p = pts[i];
        box.style.display = p ? '' : 'none';
        if (p) { box.style.left = p[0] * 100 + '%'; box.style.top = p[1] * 100 + '%'; }
      });
      // keep every label inside the picture (a short card would otherwise cut off one near the edge)
      const H = host.getBoundingClientRect();
      tags.forEach(({ label }) => {
        label.style.translate = '';
        const L = label.getBoundingClientRect();
        if (!L.width) return;
        const dx = Math.max(H.left + 4 - L.left, Math.min(0, H.right - 4 - L.right));
        const dy = Math.max(H.top + 4 - L.top, Math.min(0, H.bottom - 4 - L.bottom));
        if (dx || dy) label.style.translate = `${dx}px ${dy}px`;
      });
    });
  }

  // Load frames in the background, nearest the current view first, a few at a time; a new step or set starts a new list
  const have = new Set();
  let queue = [], busy = 0;
  function pump() {
    while (busy < 6 && queue.length) {
      const u = queue.shift();
      if (have.has(u)) continue;
      busy++;
      const im = new Image();
      im.onload = im.onerror = () => { busy--; have.add(u); pump(); };
      im.src = u;
    }
  }
  function preloadStep(s) {
    const moves = Object.keys(F.trans).filter(key => key.split('-').includes(String(s)))
      .flatMap(key => [...Array(F.trans[key].n).keys()].map(j => moveUrl(key, j)));
    const views = [];
    for (let rr = 0; rr < ROWS; rr++) for (let kk = 0; kk < F.n; kk++) views.push([rr, kk]);
    views.sort((a, b) => (Math.abs(a[0] - r) * 4 + Math.abs(a[1] - k)) - (Math.abs(b[0] - r) * 4 + Math.abs(b[1] - k)));
    const urls = views.map(([rr, kk]) => stepUrl(s, rr, kk));
    queue = [...urls.slice(0, F.n), ...moves, ...F.steps.map((_, o) => stepUrl(o, RC, C)), ...urls.slice(F.n)];
    pump();
  }

  let step = 0, k = C, r = RC, playing = 0;
  const frame = () => show(stepUrl(step, r, k), stepTags(step, r, k));
  function classes() { tags.forEach(({ label }, i) => { label.className = 'tag ' + (tagDefs[i].cls || '') + ' ' + (tagClass ? tagClass(i, step) : ''); }); }

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
      k = C; r = RC;
    }
    frame();
  }

  // Drag to turn: dragging right turns the near side of the model to the right; dragging down looks from higher up
  let drag = null;
  host.addEventListener('pointerdown', e => { playing++; drag = { x: e.clientX, y: e.clientY, k, r }; host.setPointerCapture(e.pointerId); });
  host.addEventListener('pointermove', e => {
    if (!drag) return;
    const per = Math.max(10, view.clientWidth / (F.n * 1.6)), perRow = Math.max(24, view.clientHeight / (ROWS * 1.3));
    const nk = Math.max(0, Math.min(F.n - 1, drag.k - Math.round((e.clientX - drag.x) / per)));
    const nr = Math.max(0, Math.min(ROWS - 1, drag.r + Math.round((e.clientY - drag.y) / perRow)));
    if (nk !== k || nr !== r) { k = nk; r = nr; frame(); }
  });
  const end = () => { if (drag) preloadStep(step); drag = null; };
  host.addEventListener('pointerup', end); host.addEventListener('pointercancel', end);
  host.tabIndex = 0;
  host.addEventListener('keydown', e => {
    const d = { ArrowLeft: [0, 1], ArrowRight: [0, -1], ArrowUp: [-1, 0], ArrowDown: [1, 0] }[e.key];
    if (!d || (d[0] && ROWS < 2)) return;
    e.preventDefault(); playing++;
    r = Math.max(0, Math.min(ROWS - 1, r + d[0])); k = Math.max(0, Math.min(F.n - 1, k + d[1])); frame();
  });

  classes(); frame(); preloadStep(0);
  function setBase(b) { base = b; playing++; preloadStep(step); return frame(); }
  return { setStep, setBase };
}
