const MOTORS = ['B', 'C', 'D', 'E', 'F'];
const KEY = 'gtac-remote-v2';
const $ = (id) => document.getElementById(id);
const SVG = 'http://www.w3.org/2000/svg';
const NAMES = {
  dpad: ['Up / down', 'Left / right'],
  slider: ['Slider up / down'],
  joy: ['Up / down', 'Left / right'],
  button: ['Button']
};

let layout = load();
let editing = false;
let nextId = 100;
let remoteMode = loadMode();

function loadMode() {
  try {
    return localStorage.getItem('gtac-mode') !== 'muscle';
  } catch (_) {
    return true;
  }
}

function setMode(remote) {
  remoteMode = remote;
  try {
    localStorage.setItem('gtac-mode', remote ? 'remote' : 'muscle');
  } catch (_) {}

  if (!remote && editing) $('edit').click();

  $('mRemote').classList.toggle('sel', remote);
  $('mMuscle').classList.toggle('sel', !remote);
  $('panel').classList.toggle('muscle', !remote);
  releaseAll();

  if (document.readyState !== 'loading') {
    $('status').textContent = remote ? 'Hold the controls to move the arm' : 'Muscle sensor mode (Simulated / Live)';
  }
}

const outs = {}; // widget id -> signed speed level (-3..3) for each axis

function defaults() {
  return [
    { id: 1, t: 'dpad', size: 2, ax: [{ m: 'E', rev: false, sp: 2 }, { m: 'B', rev: false, sp: 2 }] },
    { id: 2, t: 'slider', size: 2, ax: [{ m: 'C', rev: false, sp: 3 }] }
  ];
}

function load() {
  try {
    const s = localStorage.getItem(KEY);
    if (s) {
      const l = JSON.parse(s);
      if (Array.isArray(l) && l.length) return l;
    }
  } catch (_) {}
  return defaults();
}

function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(layout));
  } catch (_) {}
}

/* ---------- Board Communication ---------- */
let busy = false;
let dirty = false;
let lastLiveSignalTime = 0;

function digits() {
  const lv = [0, 0, 0, 0, 0];
  if (!remoteMode) return '00000';

  for (const w of layout) {
    const o = outs[w.id] || [];
    w.ax.forEach((a, i) => {
      const k = MOTORS.indexOf(a.m);
      if (k < 0) return;
      lv[k] += (a.rev ? -1 : 1) * (o[i] || 0);
    });
  }
  return lv.map((l) => {
    l = Math.max(-3, Math.min(3, l));
    return l >= 0 ? l : 3 - l;
  }).join('');
}

let ws = null;
let wsOpen = false;

function connectWS() {
  try {
    ws = new WebSocket('ws://' + location.host + '/ws');
  } catch (_) {
    ws = null;
    setTimeout(connectWS, 3000);
    return;
  }
  ws.onopen = () => {
    wsOpen = true;
    $('status').textContent = 'Connected (live)';
    send();
  };
  ws.onmessage = (e) => handleReply(String(e.data));
  ws.onclose = () => {
    wsOpen = false;
    setTimeout(connectWS, 1500);
  };
  ws.onerror = () => {
    try { ws.close(); } catch (_) {}
  };
}

function handleReply(t) {
  const parts = t.split(' '); // "ok" or "ok <muscle %>"
  if (parts.length > 1) {
    const p = Math.max(0, Math.min(100, parseInt(parts[1]) || 0));
    $('pct').textContent = p + '%';
    addSample(p);
    lastLiveSignalTime = performance.now();
  }
}

function send() {
  const msg = 'm=' + digits() + '&x=' + (remoteMode ? 1 : 0);
  if (wsOpen) {
    try {
      ws.send(msg);
      return;
    } catch (_) {
      wsOpen = false;
    }
  }
  if (busy) {
    dirty = true;
    return;
  }
  busy = true;
  dirty = false;
  fetch('/s?' + msg, { cache: 'no-store' })
    .then((r) => r.text())
    .then((t) => {
      if (!wsOpen) $('status').textContent = remoteMode ? 'Connected' : 'Muscle sensor mode';
      handleReply(t);
    })
    .catch(() => {
      if (!wsOpen && remoteMode) $('status').textContent = 'Not connected: check the Wi-Fi';
    })
    .finally(() => {
      busy = false;
      if (dirty) send();
    });
}

function setOut(w, i, v) {
  const o = outs[w.id] || (outs[w.id] = [0, 0]);
  if (o[i] !== v) {
    o[i] = v;
    send();
    return true;
  }
  return false;
}

function releaseAll() {
  for (const id in outs) outs[id] = [0, 0];
  document.querySelectorAll('.on').forEach((e) => e.classList.remove('on'));
  send();
}

function zone(v, sp) {
  const a = Math.abs(v);
  if (a < 0.2) return 0;
  const f = Math.min(1, (a - 0.2) / 0.8);
  const l = 1 + Math.min(sp - 1, Math.floor(f * sp));
  return v < 0 ? -l : l;
}

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

function caption(w) {
  const names = w.ax.filter((a) => a.m).map((a) => 'Motor ' + a.m);
  if (w.t === 'button') return (w.name || 'Button') + (names.length ? ' · ' + names[0] : '');
  return names.join(' · ') || 'No motor chosen';
}

function pointerHold(node, w, onDown, onMove, onUp) {
  let id = null;
  node.addEventListener('pointerdown', (e) => {
    if (editing || !remoteMode) return;
    e.preventDefault();
    id = e.pointerId;
    try { node.setPointerCapture(e.pointerId); } catch (_) {}
    onDown(e);
  });
  node.addEventListener('pointermove', (e) => {
    if (e.pointerId === id) onMove(e);
  });
  ['pointerup', 'pointercancel', 'lostpointercapture'].forEach((n) =>
    node.addEventListener(n, (e) => {
      if (e.pointerId === id) {
        id = null;
        onUp(e);
      }
    })
  );
}

/* ---------- Control Widgets ---------- */
function buildDpad(w) {
  const box = el('div', 'dpad');
  box.innerHTML =
    '<svg viewBox="0 0 200 200"><circle cx="100" cy="100" r="100" fill="#0ba89a"/>' +
    '<rect class="arm V" x="68" y="14" width="64" height="172" rx="32"/><rect class="arm H" x="14" y="68" width="172" height="64" rx="32"/>' +
    '<path class="arrow U" d="M100 32 L112 50 L88 50 Z"/><path class="arrow D" d="M100 168 L112 150 L88 150 Z"/>' +
    '<path class="arrow L" d="M32 100 L50 88 L50 112 Z"/><path class="arrow R" d="M168 100 L150 88 L150 112 Z"/></svg>';
  const q = (s) => box.querySelector(s);

  function paint() {
    const o = outs[w.id] || [0, 0];
    q('.U').classList.toggle('on', o[0] > 0);
    q('.D').classList.toggle('on', o[0] < 0);
    q('.R').classList.toggle('on', o[1] > 0);
    q('.L').classList.toggle('on', o[1] < 0);
    q('.V').classList.toggle('on', o[0] !== 0);
    q('.H').classList.toggle('on', o[1] !== 0);
  }

  function at(e) {
    const r = box.getBoundingClientRect();
    const R = r.width / 2;
    const dx = e.clientX - (r.left + R);
    const dy = e.clientY - (r.top + R);
    const d = Math.hypot(dx, dy);
    let up = 0;
    let side = 0;

    if (d > 0.2 * R) {
      if (Math.abs(dy) > 0.38 * d) up = dy < 0 ? 1 : -1;
      if (Math.abs(dx) > 0.38 * d) side = dx > 0 ? 1 : -1;
    }
    setOut(w, 0, up * w.ax[0].sp);
    setOut(w, 1, side * w.ax[1].sp);
    paint();
  }

  pointerHold(box, w, at, at, () => {
    setOut(w, 0, 0);
    setOut(w, 1, 0);
    paint();
  });
  return box;
}

function buildSlider(w) {
  const track = el('div', 'track');
  const handle = el('div', 'handle', '<i></i><i></i>');
  track.appendChild(handle);

  function at(e) {
    const r = track.getBoundingClientRect();
    const h = handle.offsetHeight;
    const half = (r.height - h) / 2;
    const mid = r.top + r.height / 2;
    const off = Math.max(-half, Math.min(half, e.clientY - mid));

    handle.classList.remove('back');
    handle.style.top = r.height / 2 + off + 'px';
    const l = zone(-off / half, w.ax[0].sp);
    setOut(w, 0, l);
    handle.classList.toggle('on', l !== 0);
  }

  function home() {
    handle.classList.add('back');
    handle.style.top = '50%';
    setOut(w, 0, 0);
    handle.classList.remove('on');
  }

  pointerHold(track, w, at, at, home);
  return track;
}

function buildJoy(w) {
  const base = el('div', 'joy');
  const knob = el('div', 'knob');
  base.appendChild(knob);

  function at(e) {
    const r = base.getBoundingClientRect();
    const R = r.width / 2;
    const lim = R * 0.62;
    let dx = e.clientX - (r.left + R);
    let dy = e.clientY - (r.top + R);
    const d = Math.hypot(dx, dy);

    if (d > lim) {
      dx *= lim / d;
      dy *= lim / d;
    }
    knob.classList.remove('back');
    knob.style.left = R + dx + 'px';
    knob.style.top = R + dy + 'px';
    const a = zone(-dy / lim, w.ax[0].sp);
    const b = zone(dx / lim, w.ax[1].sp);
    setOut(w, 0, a);
    setOut(w, 1, b);
    knob.classList.toggle('on', a !== 0 || b !== 0);
  }

  function home() {
    knob.style.left = '50%';
    knob.style.top = '50%';
    setOut(w, 0, 0);
    setOut(w, 1, 0);
    knob.classList.remove('on');
  }

  pointerHold(base, w, at, at, home);
  return base;
}

function buildButton(w) {
  const b = el('button', 'btn');
  b.textContent = w.name || 'Hold';

  pointerHold(
    b,
    w,
    () => {
      b.classList.add('on');
      setOut(w, 0, w.ax[0].sp);
    },
    () => {},
    () => {
      b.classList.remove('on');
      setOut(w, 0, 0);
    }
  );

  b.addEventListener('contextmenu', (e) => e.preventDefault());
  return b;
}

const BUILD = { dpad: buildDpad, slider: buildSlider, joy: buildJoy, button: buildButton };

/* ---------- Layout Rendering ---------- */
function render() {
  const board = $('board');
  board.innerHTML = '';
  layout.forEach((w, idx) => {
    outs[w.id] = [0, 0];
    const box = el('div', 'wgt sz' + w.size);
    box.appendChild(BUILD[w.t](w));
    box.appendChild(el('div', 'cap', caption(w)));

    const tools = el('div', 'tools');
    [
      ['◀', 'left'],
      ['▶', 'right'],
      ['⚙', 'set'],
      ['⤢', 'size'],
      ['✕', 'del']
    ].forEach(([txt, act]) => {
      const b = el('button', null, txt);
      b.setAttribute('aria-label', act);
      b.addEventListener('click', () => tool(act, idx));
      tools.appendChild(b);
    });

    box.appendChild(tools);
    board.appendChild(box);
  });
  send();
}

function tool(act, idx) {
  const w = layout[idx];
  if (act === 'left' && idx > 0) {
    layout.splice(idx - 1, 2, layout[idx], layout[idx - 1]);
  } else if (act === 'right' && idx < layout.length - 1) {
    layout.splice(idx, 2, layout[idx + 1], layout[idx]);
  } else if (act === 'size') {
    w.size = (w.size % 3) + 1;
  } else if (act === 'del') {
    layout.splice(idx, 1);
  } else if (act === 'set') {
    openDialog(w);
    return;
  }
  save();
  render();
}

function addWidget(t) {
  const used = new Set(layout.flatMap((w) => w.ax.map((a) => a.m)));
  const free = MOTORS.filter((m) => !used.has(m));
  const n = NAMES[t].length;
  const ax = [];

  for (let i = 0; i < n; i++) {
    ax.push({ m: free[i] || '', rev: false, sp: t === 'slider' || t === 'joy' ? 3 : 2 });
  }

  layout.push({ id: nextId++, t: t, size: 2, ax: ax, name: t === 'button' ? 'Hold' : '' });
  save();
  render();
}

/* ---------- Configuration Dialog ---------- */
function openDialog(w) {
  const box = $('dlgbox');
  box.innerHTML = '';
  const title = { dpad: 'D-pad', slider: 'Slider', joy: 'Joystick', button: 'Button' }[w.t];
  box.appendChild(el('h2', null, title + ': choose the motors'));

  if (w.t === 'button') {
    const d = el('div', 'ax');
    d.innerHTML = '<b>Name on the button</b>';
    const i = el('input');
    i.type = 'text';
    i.maxLength = 10;
    i.value = w.name || '';
    i.addEventListener('input', () => {
      w.name = i.value;
      save();
    });
    d.appendChild(i);
    box.appendChild(d);
  }

  w.ax.forEach((a, i) => {
    const d = el('div', 'ax');
    d.appendChild(el('b', null, NAMES[w.t][i]));

    const sel = el('select');
    sel.innerHTML =
      '<option value="">No motor</option>' +
      MOTORS.map((m) => '<option value="' + m + '"' + (a.m === m ? ' selected' : '') + '>Motor ' + m + '</option>').join('');
    sel.addEventListener('change', () => {
      a.m = sel.value;
      save();
    });

    const rev = el('label', null, '<input type="checkbox"' + (a.rev ? ' checked' : '') + '> Reverse');
    rev.firstChild.addEventListener('change', (e) => {
      a.rev = e.target.checked;
      save();
    });

    const sp = el('select');
    const analog = w.t === 'slider' || w.t === 'joy';
    sp.innerHTML = [
      ['Slow', 1],
      ['Medium', 2],
      ['Fast', 3]
    ]
      .map(([n, v]) => '<option value="' + v + '"' + (a.sp === v ? ' selected' : '') + '>' + (analog ? 'Top speed: ' : 'Speed: ') + n + '</option>')
      .join('');
    sp.addEventListener('change', () => {
      a.sp = +sp.value;
      save();
    });

    d.appendChild(sel);
    d.appendChild(document.createTextNode(' '));
    d.appendChild(sp);

    const lab = el('div');
    lab.style.marginTop = '8px';
    lab.appendChild(rev);
    d.appendChild(lab);
    box.appendChild(d);
  });

  const done = el('button', 'done', 'Done');
  done.addEventListener('click', () => {
    $('dlg').classList.remove('open');
    render();
  });
  box.appendChild(done);
  $('dlg').classList.add('open');
}

/* ---------- Event Listeners ---------- */
$('edit').addEventListener('click', () => {
  editing = !editing;
  releaseAll();
  $('panel').classList.toggle('editing', editing);
  $('edit').classList.toggle('sel', editing);
  $('status').textContent = editing ? 'Change the remote: add, move, resize or set up the controls' : 'Hold the controls to move the arm';
});

document.querySelectorAll('[data-add]').forEach((b) => b.addEventListener('click', () => addWidget(b.dataset.add)));

$('reset').addEventListener('click', () => {
  if (confirm('Go back to the starting remote?')) {
    layout = defaults();
    save();
    render();
  }
});

document.addEventListener('contextmenu', (e) => e.preventDefault());

/* ---------- Muscle Signal Real-Time Graph ---------- */
const WINDOW_MS = 30000;
const samples = [];

function addSample(v) {
  const t = performance.now();
  samples.push([t, v]);
  while (samples.length && samples[0][0] < t - WINDOW_MS - 1000) samples.shift();
}

/* Dummy Data Generator */
let mockVal = 30;
let mockTarget = 30;
function generateMockSample() {
  if (performance.now() - lastLiveSignalTime > 1000) {
    if (Math.random() < 0.08) {
      mockTarget = Math.floor(Math.random() * 85) + 10;
    }
    mockVal += (mockTarget - mockVal) * 0.15 + (Math.random() - 0.5) * 4;
    mockVal = Math.max(0, Math.min(100, mockVal));

    const displayVal = Math.round(mockVal);
    $('pct').textContent = displayVal + '%';
    addSample(displayVal);
  }
}

function drawGraph() {
  const c = $('graph');
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth;
  const h = c.clientHeight;

  if (!w || !h) return;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }

  const g = c.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);

  const L = 44;
  const R = 10;
  const T = 10;
  const B = 26;
  const pw = w - L - R;
  const ph = h - T - B;
  const now = performance.now();

  const X = (t) => L + pw * (1 - (now - t) / WINDOW_MS);
  const Y = (v) => T + ph * (1 - v / 100);

  g.font = '12px system-ui,-apple-system,Arial,sans-serif';
  g.textBaseline = 'middle';

  // Y Axis (0 - 100 %)
  for (const v of [0, 25, 50, 75, 100]) {
    g.strokeStyle = v === 0 ? '#3a3a3a' : '#262626';
    g.lineWidth = 1;
    g.beginPath();
    g.moveTo(L, Y(v) + 0.5);
    g.lineTo(L + pw, Y(v) + 0.5);
    g.stroke();
    g.fillStyle = '#7a7a7a';
    g.textAlign = 'right';
    g.fillText(v + '%', L - 8, Y(v));
  }

  // X Axis (Time Scale)
  g.textAlign = 'center';
  g.textBaseline = 'top';
  for (const s of [30, 20, 10, 0]) {
    const x = L + pw * (1 - s / 30);
    g.strokeStyle = '#202020';
    g.beginPath();
    g.moveTo(x + 0.5, T);
    g.lineTo(x + 0.5, T + ph);
    g.stroke();
    g.fillStyle = '#7a7a7a';
    g.fillText(s === 0 ? 'now' : '-' + s + ' s', x, T + ph + 8);
  }

  const pts = samples.filter((p) => p[0] >= now - WINDOW_MS - 1000);
  if (pts.length < 2) return;

  g.save();
  g.beginPath();
  g.rect(L, T, pw, ph);
  g.clip();

  const grad = g.createLinearGradient(0, T, 0, T + ph);
  grad.addColorStop(0, 'rgba(11,168,154,.45)');
  grad.addColorStop(1, 'rgba(11,168,154,0)');

  g.beginPath();
  g.moveTo(X(pts[0][0]), Y(0));
  for (const p of pts) g.lineTo(X(p[0]), Y(p[1]));
  g.lineTo(X(pts[pts.length - 1][0]), Y(0));
  g.closePath();
  g.fillStyle = grad;
  g.fill();

  g.beginPath();
  pts.forEach((p, i) => (i ? g.lineTo(X(p[0]), Y(p[1])) : g.moveTo(X(p[0]), Y(p[1]))));
  g.strokeStyle = '#3fe0cf';
  g.lineWidth = 2.5;
  g.lineJoin = 'round';
  g.stroke();

  const last = pts[pts.length - 1];
  g.fillStyle = '#e8fffc';
  g.beginPath();
  g.arc(X(last[0]), Y(last[1]), 4, 0, Math.PI * 2);
  g.fill();
  g.restore();
}

(function loop() {
  if (!remoteMode) {
    generateMockSample();
    drawGraph();
  }
  requestAnimationFrame(loop);
})();

setInterval(() => {
  if (!remoteMode && !wsOpen) send();
}, 150);

$('mRemote').addEventListener('click', () => setMode(true));
$('mMuscle').addEventListener('click', () => setMode(false));

/* Prevent touch zoom on mobile/tablets */
let lastTouch = 0;
document.addEventListener(
  'touchend',
  (e) => {
    const n = Date.now();
    if (n - lastTouch < 350 && !e.target.closest('select,input')) e.preventDefault();
    lastTouch = n;
  },
  { passive: false }
);
document.addEventListener('dblclick', (e) => e.preventDefault(), { passive: false });
['gesturestart', 'gesturechange', 'gestureend'].forEach((n) =>
  document.addEventListener(n, (e) => e.preventDefault(), { passive: false })
);

setInterval(send, 500); // Heartbeat
window.addEventListener('blur', () => {
  releaseAll();
  render();
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    releaseAll();
    render();
  }
});

render();
setMode(remoteMode);
connectWS();