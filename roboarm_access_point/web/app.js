'use strict';
/* GTAC Robot Arm: iPad page. Talks to the LMS-ESP32 board (see PROTOCOL.md).
   Blockly (blockly.js, with blocks.js inside) is loaded only when the code canvas is needed. */

const MOTORS = 'BCDEF';
const $ = (id) => document.getElementById(id);
const AXES = { dpad: ['Up / down', 'Left / right'], slider: ['Up / down'], joy: ['Up / down', 'Left / right'], button: ['Button'] };
const KIND = { dpad: 'D-pad', slider: 'Slider', joy: 'Joystick', button: 'Button' };
const MAX_WIDGETS = 5;

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (_) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} }
};
function defaults() {
  return [{ n: 1, t: 'dpad', size: 2, ax: [{ m: 'E', rev: false, sp: 2 }, { m: 'B', rev: false, sp: 2 }] },
          { n: 2, t: 'slider', size: 2, ax: [{ m: 'C', rev: false, sp: 3 }] }];
}
const S = {
  tab: 'remote',                  // the page always opens on the Remote tab
  sub: store.get('gtac-sub', 'basic'),
  layout: (() => { const l = store.get('gtac-remote-v3', null); return Array.isArray(l) && l.length ? l : defaults(); })(),
  gain: store.get('gtac-gain', 10),
  port: store.get('gtac-port', 'B'),
  editing: false,
  outs: {},                       // control number -> [axis 0, axis 1], signed speed level -3..3
  prog: [0, 0, 0, 0, 0],          // Advanced mode: run state digits set by the program
  pos: [-1, -1, -1, -1, -1], base: [-1, -1, -1, -1, -1],
  hubMode: 0, hubMotor: 'B', mask: 31, muscle: 0
};
const saveLayout = () => store.set('gtac-remote-v3', S.layout);

/* ================= link to the board ================= */
const Link = {
  ws: null, open: false, busy: false, dirty: false, lastRx: 0,
  connect() {
    try { this.ws = new WebSocket('ws://' + location.host + '/ws'); } catch (_) { setTimeout(() => this.connect(), 3000); return; }
    this.ws.onopen = () => { this.open = true; this.send(); };
    this.ws.onmessage = (e) => this.receive(String(e.data));
    this.ws.onclose = () => { this.open = false; setTimeout(() => this.connect(), 1500); };
    this.ws.onerror = () => { try { this.ws.close(); } catch (_) {} };
  },
  message(extra) {
    let m = 'x=' + (S.tab === 'remote' ? 1 : 0) + '&m=' + digits() + '&g=' + S.gain + '&p=' + S.port;
    return extra ? m + '&' + extra : m;
  },
  send(extra) {
    const msg = this.message(extra);
    if (this.open) { try { this.ws.send(msg); return; } catch (_) { this.open = false; } }
    if (this.busy) { this.dirty = true; if (extra) this.pending = extra; return; }
    this.busy = true; this.dirty = false;
    fetch('/s?' + msg, { cache: 'no-store' }).then((r) => r.text()).then((t) => this.receive(t))
      .catch(() => {}).finally(() => {
        this.busy = false;
        if (this.dirty) { const p = this.pending; this.pending = null; this.send(p); }
      });
  },
  receive(text) {
    this.lastRx = performance.now();
    for (const line of text.split('\n')) {
      const f = line.trim().split(' ');
      if (f[0] === 'm' && f.length > 1) muscleSample(+f[1] || 0);
      else if ((f[0] === 'p' || f[0] === 'b') && f.length > 2) {
        const i = MOTORS.indexOf(f[1]);
        if (i >= 0) { (f[0] === 'p' ? S.pos : S.base)[i] = +f[2]; motorsDirty = true; }
      } else if (f[0] === 'h' && f.length > 3) {
        S.hubMode = +f[1]; S.hubMotor = f[2]; S.mask = +f[3]; motorsDirty = true;
      }
    }
  }
};
function linkState() {
  const age = performance.now() - Link.lastRx;
  const el = $('link');
  if (age < 2500) { el.textContent = Link.open ? 'Connected' : 'Connected (slow)'; el.className = 'pill' + (Link.open ? '' : ' slow'); }
  else { el.textContent = 'Not connected'; el.className = 'pill off'; }
}

/* Run state digit per motor: 0 stop, 1-3 forward, 4-6 back */
function digits() {
  if (S.tab !== 'remote') return '00000';
  if (S.sub === 'advanced') return S.prog.join('');
  const lv = [0, 0, 0, 0, 0];
  for (const w of S.layout) {
    const o = S.outs[w.n] || [];
    w.ax.forEach((a, i) => { const k = MOTORS.indexOf(a.m); if (k >= 0) lv[k] += (a.rev ? -1 : 1) * (o[i] || 0); });
  }
  return lv.map((l) => { l = Math.max(-3, Math.min(3, l)); return l >= 0 ? l : 3 - l; }).join('');
}

let toastTimer = 0;
function toast(text) {
  const s = $('status'); s.textContent = text; s.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => s.classList.remove('show'), 2200);
}

/* ================= the remote's controls ================= */
function zone(v, sp) {                 // how far a slider or stick is pushed -> speed level
  const a = Math.abs(v); if (a < 0.2) return 0;
  const l = 1 + Math.min(sp - 1, Math.floor(Math.min(1, (a - 0.2) / 0.8) * sp));
  return v < 0 ? -l : l;
}
function el(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; }

/* Which directions of control n are held: {up, down, left, right, pressed} */
function heldOf(w) {
  const o = S.outs[w.n] || [0, 0], h = {};
  if (w.t === 'button') { if (o[0]) h.pressed = true; return h; }
  if (o[0] > 0) h.up = true; if (o[0] < 0) h.down = true;
  if (o[1] > 0) h.right = true; if (o[1] < 0) h.left = true;
  return h;
}
function setOut(w, i, v) {
  const o = S.outs[w.n] || (S.outs[w.n] = [0, 0]);
  if (o[i] === v) return;
  const before = heldOf(w);
  o[i] = v;
  if (S.sub === 'basic') Link.send();
  else if (window.Program) window.Program.control(w.n, before, heldOf(w));
  motorsDirty = true;
}
function active() { return !S.editing && S.tab === 'remote'; }
function pointerHold(node, onDown, onMove, onUp) {
  let id = null;
  node.addEventListener('pointerdown', (e) => {
    if (!active()) return;
    e.preventDefault(); id = e.pointerId;
    try { node.setPointerCapture(e.pointerId); } catch (_) {}
    onDown(e);
  });
  node.addEventListener('pointermove', (e) => { if (e.pointerId === id) onMove(e); });
  ['pointerup', 'pointercancel', 'lostpointercapture'].forEach((n) =>
    node.addEventListener(n, (e) => { if (e.pointerId === id) { id = null; onUp(e); } }));
}
function buildDpad(w) {
  const box = el('div', 'dpad');
  box.innerHTML = '<svg viewBox="0 0 200 200"><circle cx="100" cy="100" r="100" fill="#4C34E5"/>' +
    '<rect class="arm V" x="68" y="14" width="64" height="172" rx="32"/><rect class="arm H" x="14" y="68" width="172" height="64" rx="32"/>' +
    '<path class="arrow U" d="M100 30 L114 52 L86 52 Z"/><path class="arrow D" d="M100 170 L114 148 L86 148 Z"/>' +
    '<path class="arrow L" d="M30 100 L52 86 L52 114 Z"/><path class="arrow R" d="M170 100 L148 86 L148 114 Z"/></svg>';
  const q = (s) => box.querySelector(s);
  const paint = () => {
    const o = S.outs[w.n] || [0, 0];
    q('.U').classList.toggle('on', o[0] > 0); q('.D').classList.toggle('on', o[0] < 0);
    q('.R').classList.toggle('on', o[1] > 0); q('.L').classList.toggle('on', o[1] < 0);
    q('.V').classList.toggle('on', o[0] !== 0); q('.H').classList.toggle('on', o[1] !== 0);
  };
  const at = (e) => {
    const r = box.getBoundingClientRect(), R = r.width / 2;
    const dx = e.clientX - (r.left + R), dy = e.clientY - (r.top + R), d = Math.hypot(dx, dy);
    let up = 0, side = 0;
    if (d > 0.2 * R) { if (Math.abs(dy) > 0.38 * d) up = dy < 0 ? 1 : -1; if (Math.abs(dx) > 0.38 * d) side = dx > 0 ? 1 : -1; }
    setOut(w, 0, up * w.ax[0].sp); setOut(w, 1, side * w.ax[1].sp); paint();
  };
  pointerHold(box, at, at, () => { setOut(w, 0, 0); setOut(w, 1, 0); paint(); });
  return box;
}
function buildSlider(w) {
  const track = el('div', 'track'), handle = el('div', 'handle', '<i></i><i></i>');
  track.appendChild(handle);
  const at = (e) => {
    const r = track.getBoundingClientRect(), half = (r.height - handle.offsetHeight) / 2;
    const off = Math.max(-half, Math.min(half, e.clientY - (r.top + r.height / 2)));
    handle.classList.remove('back'); handle.style.top = (r.height / 2 + off) + 'px';
    const l = zone(-off / half, w.ax[0].sp); setOut(w, 0, l); handle.classList.toggle('on', l !== 0);
  };
  pointerHold(track, at, at, () => { handle.classList.add('back'); handle.style.top = '50%'; setOut(w, 0, 0); handle.classList.remove('on'); });
  return track;
}
function buildJoy(w) {
  const base = el('div', 'joy'), knob = el('div', 'knob');
  base.appendChild(knob);
  const at = (e) => {
    const r = base.getBoundingClientRect(), R = r.width / 2, lim = R * 0.62;
    let dx = e.clientX - (r.left + R), dy = e.clientY - (r.top + R); const d = Math.hypot(dx, dy);
    if (d > lim) { dx *= lim / d; dy *= lim / d; }
    knob.classList.remove('back'); knob.style.left = (R + dx) + 'px'; knob.style.top = (R + dy) + 'px';
    const a = zone(-dy / lim, w.ax[0].sp), b = zone(dx / lim, w.ax[1].sp);
    setOut(w, 0, a); setOut(w, 1, b); knob.classList.toggle('on', a !== 0 || b !== 0);
  };
  pointerHold(base, at, at, () => { knob.classList.add('back'); knob.style.left = '50%'; knob.style.top = '50%'; setOut(w, 0, 0); setOut(w, 1, 0); knob.classList.remove('on'); });
  return base;
}
function buildButton(w) {
  const b = el('button', 'btn'); b.textContent = w.name || 'Hold';
  pointerHold(b, () => { b.classList.add('on'); setOut(w, 0, w.ax[0].sp); }, () => {}, () => { b.classList.remove('on'); setOut(w, 0, 0); });
  return b;
}
const BUILD = { dpad: buildDpad, slider: buildSlider, joy: buildJoy, button: buildButton };

function caption(w) {
  const names = w.ax.filter((a) => a.m).map((a) => 'Motor ' + a.m);
  if (w.t === 'button') return (w.name || 'Button') + (names.length ? ' · ' + names[0] : '');
  return names.join(' · ') || 'No motor chosen';
}
function render() {
  const board = $('board');
  board.innerHTML = '';
  S.layout.forEach((w, idx) => {
    S.outs[w.n] = [0, 0];
    const box = el('div', 'wgt sz' + w.size);
    box.appendChild(el('div', 'num', String(w.n)));
    box.appendChild(BUILD[w.t](w));
    box.appendChild(el('div', 'cap', S.sub === 'advanced' ? KIND[w.t] + ' ' + w.n : caption(w)));
    const tools = el('div', 'tools');
    [['◀', 'left', 'Move left'], ['▶', 'right', 'Move right'], ['⚙', 'set', 'Settings'], ['⤢', 'size', 'Size'], ['✕', 'del', 'Remove']]
      .forEach(([txt, act, label]) => {
        const b = el('button', null, txt); b.setAttribute('aria-label', label);
        b.addEventListener('click', () => tool(act, idx)); tools.appendChild(b);
      });
    box.appendChild(tools);
    board.appendChild(box);
  });
  document.querySelectorAll('#editbar [data-add]').forEach((b) => { b.disabled = S.layout.length >= MAX_WIDGETS; });
  Link.send();
}
function tool(act, idx) {
  const L = S.layout, w = L[idx];
  if (act === 'left' && idx > 0) L.splice(idx - 1, 2, L[idx], L[idx - 1]);
  else if (act === 'right' && idx < L.length - 1) L.splice(idx, 2, L[idx + 1], L[idx]);
  else if (act === 'size') w.size = (w.size % 3) + 1;
  else if (act === 'del') L.splice(idx, 1);
  else if (act === 'set') { openSettings(w); return; }
  saveLayout(); render();
}
function addWidget(t) {
  if (S.layout.length >= MAX_WIDGETS) return;
  const usedN = new Set(S.layout.map((w) => w.n));
  let n = 1; while (usedN.has(n)) n++;
  const used = new Set(S.layout.flatMap((w) => w.ax.map((a) => a.m)));
  const free = MOTORS.split('').filter((m) => !used.has(m));
  const ax = AXES[t].map((_, i) => ({ m: free[i] || '', rev: false, sp: t === 'slider' || t === 'joy' ? 3 : 2 }));
  S.layout.push({ n, t, size: 2, ax, name: t === 'button' ? 'Hold' : '' });
  saveLayout(); render();
}
function openSettings(w) {
  const box = $('dlgbox'); box.innerHTML = '';
  box.appendChild(el('h2', null, KIND[w.t] + ' ' + w.n + ': choose the motors'));
  if (w.t === 'button') {
    const d = el('div', 'ax', '<b>Name on the button</b>');
    const i = el('input'); i.type = 'text'; i.maxLength = 10; i.value = w.name || '';
    i.addEventListener('input', () => { w.name = i.value; saveLayout(); });
    d.appendChild(i); box.appendChild(d);
  }
  w.ax.forEach((a, i) => {
    const d = el('div', 'ax'); d.appendChild(el('b', null, AXES[w.t][i]));
    const sel = el('select');
    sel.innerHTML = '<option value="">No motor</option>' + MOTORS.split('').map((m) => '<option value="' + m + '"' + (a.m === m ? ' selected' : '') + '>Motor ' + m + '</option>').join('');
    sel.addEventListener('change', () => { a.m = sel.value; saveLayout(); });
    const sp = el('select'), analog = w.t === 'slider' || w.t === 'joy';
    sp.innerHTML = [['Slow', 1], ['Medium', 2], ['Fast', 3]].map(([n, v]) => '<option value="' + v + '"' + (a.sp === v ? ' selected' : '') + '>' + (analog ? 'Top speed: ' : 'Speed: ') + n + '</option>').join('');
    sp.addEventListener('change', () => { a.sp = +sp.value; saveLayout(); });
    const rev = el('label', null, '<input type="checkbox"' + (a.rev ? ' checked' : '') + '> Turn the other way');
    rev.firstChild.addEventListener('change', (e) => { a.rev = e.target.checked; saveLayout(); });
    d.appendChild(sel); d.appendChild(document.createTextNode(' ')); d.appendChild(sp);
    const row = el('div'); row.appendChild(rev); d.appendChild(row);
    box.appendChild(d);
  });
  const done = el('button', 'done', 'Done');
  done.addEventListener('click', () => { $('dlg').classList.remove('open'); render(); });
  box.appendChild(done);
  $('dlg').classList.add('open');
}

/* ================= motors: live positions and homes ================= */
let motorsDirty = true;
function drawMotors() {
  if (!motorsDirty) return;
  motorsDirty = false;
  const d = digits();
  for (const strip of [$('motorStrip'), $('motorStrip2')]) {
    if (!strip.children.length) {
      for (const m of MOTORS) strip.appendChild(el('div', 'mtile', '<b>' + m + '</b><div><div class="deg">–</div><div class="home">home –</div></div>'));
    }
    [...strip.children].forEach((t, i) => {
      t.classList.toggle('none', !(S.mask & (1 << i)));
      t.classList.toggle('run', d[i] !== '0');
      t.querySelector('.deg').textContent = S.pos[i] >= 0 ? S.pos[i] + '°' : '–';
      t.querySelector('.home').textContent = 'home ' + (S.base[i] >= 0 ? S.base[i] + '°' : '–');
    });
  }
  const pick = $('musclePick');
  if (!pick.children.length) {
    for (const m of MOTORS) {
      const b = el('button', 'mbtn', '<b>' + m + '</b><small>–</small>');
      b.addEventListener('click', () => { S.port = m; store.set('gtac-port', m); Link.send(); motorsDirty = true; drawMotors(); });
      pick.appendChild(b);
    }
  }
  [...pick.children].forEach((b, i) => {
    b.classList.toggle('sel', MOTORS[i] === S.port);
    b.classList.toggle('none', !(S.mask & (1 << i)));
    b.querySelector('small').textContent = !(S.mask & (1 << i)) ? 'no motor' : (S.pos[i] >= 0 ? 'at ' + S.pos[i] + '°' : 'motor');
  });
  const k = MOTORS.indexOf(S.port);
  $('muscleExplain').innerHTML = !(S.mask & (1 << k))
    ? 'There is no motor in port <b>' + S.port + '</b>. Choose a port with a motor.'
    : 'Relax: <b>Motor ' + S.port + '</b> goes to its home position' + (S.base[k] >= 0 ? ' (' + S.base[k] + '°)' : '') +
      '. Squeeze: it turns further the harder you squeeze.';
}

/* ================= muscle signal graph (last 30 s, 0-100 %) ================= */
const WINDOW_MS = 30000, samples = [];
let pctShown = 0;
function muscleSample(v) {
  S.muscle = v;
  const t = performance.now();
  samples.push([t, v]);
  while (samples.length && samples[0][0] < t - WINDOW_MS - 1000) samples.shift();
  if (window.Program) window.Program.muscle(v);
}
function drawGraph() {
  const c = $('graph'), dpr = window.devicePixelRatio || 1, w = c.clientWidth, h = c.clientHeight;
  if (!w || !h) return;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); }
  const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
  const L = 46, R = 8, T = 8, B = 26, pw = w - L - R, ph = h - T - B, now = performance.now();
  const X = (t) => L + pw * (1 - (now - t) / WINDOW_MS), Y = (v) => T + ph * (1 - v / 100);
  g.font = '600 13px Figtree, system-ui, sans-serif'; g.textBaseline = 'middle'; g.textAlign = 'right';
  for (const v of [0, 25, 50, 75, 100]) {
    g.strokeStyle = v === 0 ? '#272A24' : '#E4DFC8'; g.lineWidth = v === 0 ? 2 : 1;
    g.beginPath(); g.moveTo(L, Y(v) + 0.5); g.lineTo(L + pw, Y(v) + 0.5); g.stroke();
    g.fillStyle = '#6B6E66'; g.fillText(v + '%', L - 8, Y(v));
  }
  g.textAlign = 'center'; g.textBaseline = 'top';
  for (const s of [30, 20, 10, 0]) { g.fillStyle = '#6B6E66'; g.fillText(s ? '-' + s + ' s' : 'now', L + pw * (1 - s / 30), T + ph + 7); }
  const pts = samples.filter((p) => p[0] >= now - WINDOW_MS - 1000);
  if (pts.length > 1) {
    g.save(); g.beginPath(); g.rect(L, T, pw, ph); g.clip();
    const grad = g.createLinearGradient(0, T, 0, T + ph);
    grad.addColorStop(0, 'rgba(107,231,190,.75)'); grad.addColorStop(1, 'rgba(107,231,190,.05)');
    g.beginPath(); g.moveTo(X(pts[0][0]), Y(0));
    for (const p of pts) g.lineTo(X(p[0]), Y(p[1]));
    g.lineTo(X(pts[pts.length - 1][0]), Y(0)); g.closePath(); g.fillStyle = grad; g.fill();
    g.beginPath(); pts.forEach((p, i) => (i ? g.lineTo(X(p[0]), Y(p[1])) : g.moveTo(X(p[0]), Y(p[1]))));
    g.strokeStyle = '#4C34E5'; g.lineWidth = 3; g.lineJoin = 'round'; g.stroke();
    const last = pts[pts.length - 1];
    g.fillStyle = '#4C34E5'; g.beginPath(); g.arc(X(last[0]), Y(last[1]), 5, 0, Math.PI * 2); g.fill();
    g.restore();
  } else {
    g.fillStyle = '#6B6E66'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('Waiting for the muscle sensor…', L + pw / 2, T + ph / 2);
  }
  const p = Math.round(S.muscle);
  if (p !== pctShown) { pctShown = p; $('pct').textContent = p + '%'; }
}

/* ================= tabs, modes and buttons ================= */
function show() {
  $('tMuscle').classList.toggle('sel', S.tab === 'muscle');
  $('tRemote').classList.toggle('sel', S.tab === 'remote');
  $('muscle').classList.toggle('show', S.tab === 'muscle');
  $('remote').classList.toggle('show', S.tab === 'remote');
  const adv = S.sub === 'advanced';
  $('sBasic').classList.toggle('sel', !adv); $('sAdvanced').classList.toggle('sel', adv);
  document.body.classList.toggle('advanced', adv);
  $('homeBtn').classList.toggle('hide', adv); $('editBtn').classList.toggle('hide', adv);
  $('codeBtn').classList.toggle('hide', !adv); $('runBtn').classList.toggle('hide', !adv);
  $('modeHint').textContent = S.editing ? 'Add, move, resize or set up the controls (up to 5). Tap ✎ again when you are done.'
    : adv ? 'Advanced: the controls send events to your code. Open the code canvas to program the arm.'
    : 'Basic: hold a control to move its motor. ⌂ Home returns every motor to its home position.';
  runButtons();
}
function runButtons() {
  const running = !!(window.Program && window.Program.running);
  for (const b of [$('runBtn'), $('runBtn2')]) { b.textContent = running ? '■ Stop' : '▶ Run'; b.classList.toggle('go', !running); b.classList.toggle('stop', running); }
}
function setTab(tab) {
  if (tab === S.tab) return;
  stopProgram();
  if (S.editing) toggleEdit();
  S.tab = tab; store.set('gtac-tab', tab);
  for (const k in S.outs) S.outs[k] = [0, 0];
  render(); show(); Link.send();
  toast(tab === 'muscle' ? 'Muscle sensor is in control' : 'Remote is in control');
}
function setSub(sub) {
  if (sub === S.sub) return;
  stopProgram();
  if (S.editing) toggleEdit();
  S.sub = sub; store.set('gtac-sub', sub);
  S.prog = [0, 0, 0, 0, 0];
  for (const k in S.outs) S.outs[k] = [0, 0];
  Link.send('c=stop');                      // safety: every motor stops before control changes hands
  render(); show();
  if (sub === 'advanced') loadBlockly();
  toast(sub === 'advanced' ? 'Advanced: your code is in control' : 'Basic: the remote is in control');
}
function toggleEdit() {
  S.editing = !S.editing;
  for (const k in S.outs) S.outs[k] = [0, 0];
  document.body.classList.toggle('editing', S.editing);
  $('editBtn').classList.toggle('sel', S.editing);
  Link.send(); show();
}
function stopProgram() { if (window.Program && window.Program.running) window.Program.stop(); }

/* ================= Blockly (loaded on demand) ================= */
let blocklyLoading = null;
function loadBlockly() {
  if (window.Program) return Promise.resolve();
  if (!blocklyLoading) {
    blocklyLoading = new Promise((ok, fail) => {
      const s = document.createElement('script'); s.src = 'blockly.js?v=__BLOCKLY_VERSION__';   // version set by tools/build.py
      s.onload = () => ok(); s.onerror = () => { blocklyLoading = null; fail(); };
      document.head.appendChild(s);
    });
  }
  return blocklyLoading;
}
/* What the blocks can do: everything goes through the board to the hub */
window.Arm = {
  run(k, forward, level) { const i = MOTORS.indexOf(k); if (i >= 0) { S.prog[i] = forward ? level : 3 + level; motorsDirty = true; Link.send(); } },
  stop(k) { const i = MOTORS.indexOf(k); if (i >= 0) { S.prog[i] = 0; motorsDirty = true; Link.send(); } },
  goTo(k, angle, dir, level) {
    const i = MOTORS.indexOf(k); if (i < 0) return;
    S.prog[i] = 0;
    Link.send('c=go&k=' + k + '&a=' + (((Math.round(angle) % 360) + 360) % 360) + '&d=' + dir + '&v=' + (level - 1));
  },
  turn(k, degrees, level) {
    const i = MOTORS.indexOf(k); if (i < 0) return;
    S.prog[i] = 0;
    Link.send('c=turn&k=' + k + '&g=' + Math.round(degrees) + '&v=' + (level - 1));
  },
  home() { S.prog = [0, 0, 0, 0, 0]; Link.send('c=home'); },
  stopAll() { S.prog = [0, 0, 0, 0, 0]; motorsDirty = true; Link.send('c=stop'); },
  muscle() { return S.muscle; },
  position(k) { const i = MOTORS.indexOf(k); return i >= 0 && S.pos[i] >= 0 ? S.pos[i] : 0; },
  held(n, dir) { const w = S.layout.find((x) => x.n === n); return !!(w && heldOf(w)[dir]); },
  changed() { runButtons(); }
};
function openCode() {
  $('code').classList.add('open');
  $('previewBoard').appendChild($('board'));          // the same live controls, smaller
  $('previewBoard').classList.add('mini');
  motorsDirty = true;
  loadBlockly().then(() => { $('blocklyLoading').style.display = 'none'; window.Program.show($('blockly')); })
    .catch(() => { $('blocklyLoading').textContent = 'Could not load the blocks. Check the Wi-Fi and try again.'; });
}
function closeCode() {
  $('code').classList.remove('open');
  $('boardHome').appendChild($('board'));
  $('previewBoard').classList.remove('mini');
  if (window.Program) window.Program.save();
}
function runOrStop() {
  loadBlockly().then(() => {
    if (window.Program.running) { window.Program.stop(); toast('Program stopped'); }
    else { window.Program.start(); toast('Program running'); }
    runButtons();
  }).catch(() => toast('Could not load the blocks'));
}

/* ================= wiring ================= */
$('tMuscle').addEventListener('click', () => setTab('muscle'));
$('tRemote').addEventListener('click', () => setTab('remote'));
$('sBasic').addEventListener('click', () => setSub('basic'));
$('sAdvanced').addEventListener('click', () => setSub('advanced'));
$('homeBtn').addEventListener('click', () => { Link.send('c=home'); toast('Going home'); });
$('editBtn').addEventListener('click', toggleEdit);
$('codeBtn').addEventListener('click', openCode);
$('closeCode').addEventListener('click', closeCode);
$('runBtn').addEventListener('click', runOrStop);
$('runBtn2').addEventListener('click', runOrStop);
$('helpBtn').addEventListener('click', () => $('help').classList.add('open'));
$('closeHelp').addEventListener('click', () => $('help').classList.remove('open'));
$('reset').addEventListener('click', () => { if (confirm('Go back to the starting remote?')) { S.layout = defaults(); saveLayout(); render(); } });
document.querySelectorAll('[data-add]').forEach((b) => b.addEventListener('click', () => addWidget(b.dataset.add)));
const gain = $('gain');
gain.value = S.gain; $('gainVal').textContent = '×' + (S.gain / 10).toFixed(1);
gain.addEventListener('input', () => { S.gain = +gain.value; store.set('gtac-gain', S.gain); $('gainVal').textContent = '×' + (S.gain / 10).toFixed(1); Link.send(); });

/* iPad: never zoom (double-tap or pinch), no long-press menus */
let lastTouch = 0;
document.addEventListener('touchend', (e) => {
  const n = Date.now(); if (n - lastTouch < 350 && !e.target.closest('select,input,#blockly')) e.preventDefault(); lastTouch = n;
}, { passive: false });
document.addEventListener('dblclick', (e) => { if (!e.target.closest('#blockly')) e.preventDefault(); }, { passive: false });
['gesturestart', 'gesturechange', 'gestureend'].forEach((n) => document.addEventListener(n, (e) => e.preventDefault(), { passive: false }));
document.addEventListener('contextmenu', (e) => { if (!e.target.closest('#blockly')) e.preventDefault(); });
const letGo = () => { for (const k in S.outs) S.outs[k] = [0, 0]; render(); };
window.addEventListener('blur', letGo);
document.addEventListener('visibilitychange', () => { if (document.hidden) { stopProgram(); letGo(); } });

setInterval(() => Link.send(), 500);                                     // heartbeat
setInterval(() => { if (!Link.open && S.tab === 'muscle') Link.send(); }, 200);   // no live link: poll the muscle signal
setInterval(linkState, 500);
(function frame() { if (S.tab === 'muscle') drawGraph(); drawMotors(); requestAnimationFrame(frame); })();

render(); show(); Link.connect();
if (S.sub === 'advanced') loadBlockly().catch(() => {});
