# LMS-ESP32 customisable web remote for the robotic arm, as a pretend LEGO Distance Sensor.
#
# The board makes its own Wi-Fi network. Students join it with a tablet or phone,
# open http://1.1.1.1 and use the remote. Joining the Wi-Fi also pops up a landing page
# with a button to the remote (like a hotel Wi-Fi sign-in page). The pencil button lets them add D-pads,
# sliders, joysticks and buttons, and choose which motor (B to F) each one controls.
# The motor commands travel to the hub as a "distance" reading, and the hub program
# (arm-remote-spike-app3.py) moves the motors.
#
# Needs on the board: lpf2.py and distance_emulator.py (both in this repo).
# Save this file as main.py to run at power-up.

import network
import socket
import utime
import ubinascii
import machine
try:
    import hashlib
except ImportError:
    import uhashlib as hashlib
import lpf2
from distance_emulator import DistanceSensorEmulator, make_modes

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------
WIFI_NAME = "GTAC 6"            # the Wi-Fi network name students look for
ADD_BOARD_CODE = False          # True adds 4 letters from the board (e.g. "GTAC 6-A1B2") so several boards differ
WIFI_PASSWORD = "gtacrobot"     # at least 8 characters
ADDRESS = "1.1.1.1"             # the remote's web address
FRAME_MS = 30                   # how long each routine motor message is held for the hub
HOLD_MS = 15                    # shortest hold: a changed motor goes out as soon as this has passed
RELEASE_AFTER_MS = 1000         # no message from the page for this long = everything stops
DEBUG = False                   # True prints connection details from the sensor library
# ---------------------------------------------------------------------------

# Motors B, C, D, E, F each have a state: 0 stop, 1-3 forward (slow, medium, fast), 4-6 back.
# The board sends one motor at a time to the hub, as a distance reading:
#   distance in mm = BASE_MM + STEP_MM * (motor_number * 7 + state)
# BASE_MM is above 1000 mm so the hub can tell these messages from muscle sensor readings.
MOTOR_COUNT = 5
BASE_MM = 1100
STEP_MM = 20
PAGE_TIMEOUT_MS = 3000          # the page counts as open while it has spoken within this time

PAGE = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, minimum-scale=1, user-scalable=no, viewport-fit=cover">
<title>Robot arm remote</title>
<style>
  :root{--teal:#0ba89a;--lit:#6ff5e6;--ink:#101010;--dim:#4a4a4a}
  *{box-sizing:border-box;touch-action:manipulation;-webkit-tap-highlight-color:transparent}
  html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
  html,body{min-height:100%;margin:0;background:#0a0a0a;overscroll-behavior:none}
  body{display:flex;align-items:center;justify-content:center;font-family:system-ui,-apple-system,Arial,sans-serif;
       color:#9a9a9a;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none;touch-action:none;min-height:100vh}
  .panel{position:relative;width:min(97vw,980px);margin:2vmin 0;padding:6vmin 3vmin 3vmin;border-radius:28px;
         border:10px solid #2b2b2b;background-color:#121212;
         background-image:radial-gradient(#242424 1.4px,transparent 1.7px);background-size:18px 18px;
         box-shadow:0 10px 30px rgba(0,0,0,.6)}
  #board{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-evenly;gap:3vmin;min-height:30vmin}
  .sz1{--u:min(24vmin,240px)} .sz2{--u:min(34vmin,330px)} .sz3{--u:min(44vmin,420px)}
  .wgt{position:relative;display:flex;flex-direction:column;align-items:center;gap:1.2vmin;padding:6px;border-radius:20px}
  .editing .wgt{outline:2px dashed #2f6f68;background:rgba(11,168,154,.06)}
  .cap{font-size:max(12px,2vmin);color:#8a8a8a;text-align:center;min-height:1.2em}
  .tools{display:none;gap:6px;margin-top:2px}
  .editing .tools{display:flex}
  .tools button{width:40px;height:40px;border:none;border-radius:50%;background:#222;color:#cfd;font-size:16px;touch-action:manipulation}
  .arrow{fill:var(--dim);transition:fill .08s} .arrow.on{fill:var(--lit)}
  .arm{fill:var(--ink);transition:fill .08s} .arm.on{fill:#1c3a37}
  .dpad{width:var(--u);height:var(--u);touch-action:none} .dpad svg{width:100%;height:100%;display:block}
  .track{position:relative;width:calc(var(--u)*.26);height:var(--u);border-radius:999px;background:var(--teal);touch-action:none}
  .handle{position:absolute;left:12%;right:12%;top:50%;height:calc(var(--u)*.38);margin-top:calc(var(--u)*-.19);
          border-radius:999px;background:var(--ink);display:flex;flex-direction:column;align-items:center;
          justify-content:center;gap:5px;box-shadow:0 2px 6px rgba(0,0,0,.5)}
  .handle.on{background:#1c3a37} .handle.back{transition:top .18s ease-out,left .18s ease-out}
  .handle i{display:block;width:34%;height:3px;border-radius:2px;background:#8a8a8a} .handle.on i{background:var(--lit)}
  .joy{position:relative;width:var(--u);height:var(--u);border-radius:50%;background:var(--teal);touch-action:none}
  .knob{position:absolute;left:50%;top:50%;width:38%;height:38%;margin:-19% 0 0 -19%;border-radius:50%;background:var(--ink);
        box-shadow:0 2px 6px rgba(0,0,0,.5)}
  .knob.on{background:#1c3a37}
  .btn{width:calc(var(--u)*.6);height:calc(var(--u)*.6);border-radius:50%;background:var(--teal);color:#06211e;border:none;
       font-weight:700;font-size:max(14px,2.6vmin);touch-action:none;box-shadow:0 4px 0 #07756b}
  .btn.on{background:var(--lit);transform:translateY(3px);box-shadow:0 1px 0 #07756b}
  .hdr{position:absolute;top:8px;right:10px;display:flex;gap:8px}
  .hdr button{width:44px;height:44px;border-radius:50%;border:none;background:#1b1b1b;color:#bbb;
              display:flex;align-items:center;justify-content:center;touch-action:manipulation}
  .hdr svg{width:22px;height:22px}
  .hdr button.sel{background:var(--teal);color:#06211e}
  #modes{position:absolute;top:8px;left:10px;display:none;background:#1b1b1b;border-radius:999px;padding:4px}
  #modes.show{display:flex}
  #modes button{border:none;background:transparent;color:#aaa;border-radius:999px;padding:9px 16px;font-size:max(14px,2.2vmin)}
  #modes button.sel{background:var(--teal);color:#06211e;font-weight:700}
  #musclebox{display:none;flex-direction:column;align-items:center;gap:1.5vmin;padding:2vmin 0 1vmin}
  .muscle #musclebox{display:flex} .muscle #board,.muscle #editbar,.muscle #edit{display:none!important}
  #graph{width:min(88vw,820px);height:min(46vh,340px);display:block;touch-action:none}
  #musclebox .big{font-size:max(28px,6vmin);color:#e8fffc;font-weight:700}
  #editbar{display:none;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:3vmin}
  .editing #editbar{display:flex}
  #editbar button{border:1px solid #2f6f68;background:#14201f;color:#bfeee9;border-radius:999px;padding:10px 16px;
                  font-size:max(14px,2.2vmin);touch-action:manipulation}
  #editbar button.warn{border-color:#5a3333;background:#241616;color:#f0b9b9}
  #status{text-align:center;font-size:max(12px,2vmin);margin-top:2vmin;min-height:1.2em}
  #dlg{position:fixed;inset:0;background:rgba(0,0,0,.65);display:none;align-items:center;justify-content:center;z-index:5;touch-action:auto}
  #dlg.open{display:flex}
  #dlgbox{width:min(92vw,460px);max-height:90vh;overflow:auto;background:#181818;border:1px solid #333;border-radius:20px;padding:18px;color:#ddd}
  #dlgbox h2{margin:0 0 12px;font-size:1.1em}
  .ax{border-top:1px solid #2a2a2a;padding:12px 0}
  .ax b{display:block;margin-bottom:8px;color:#bfeee9}
  .ax label{display:inline-flex;align-items:center;gap:6px;margin-right:12px;font-size:15px}
  select,input[type=text]{background:#222;color:#eee;border:1px solid #444;border-radius:10px;padding:9px 10px;font-size:16px}
  #dlgbox .done{margin-top:12px;width:100%;padding:12px;border:none;border-radius:999px;background:var(--teal);color:#06211e;font-weight:700;font-size:16px}
</style></head><body>
<div class="panel" id="panel">
  <div id="modes"><button id="mRemote" class="sel">Remote</button><button id="mMuscle">Muscle sensor</button></div>
  <div class="hdr">
    <button id="edit" aria-label="Change the remote">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M13.5 6.5l4 4"/></svg>
    </button>
  </div>
  <div id="board"></div>
  <div id="musclebox"><div class="big" id="pct">0%</div><canvas id="graph"></canvas><div>Muscle signal over the last 30 seconds. The muscle sensor is moving the arm.</div></div>
  <div id="editbar">
    <button data-add="dpad">+ D-pad</button><button data-add="slider">+ Slider</button>
    <button data-add="joy">+ Joystick</button><button data-add="button">+ Button</button>
    <button class="warn" id="reset">Start again</button>
  </div>
  <div id="status">Hold the controls to move the arm</div>
</div>
<div id="dlg"><div id="dlgbox"></div></div>
<script>
const MOTORS=['B','C','D','E','F'];
const KEY='gtac-remote-v2';
const $=id=>document.getElementById(id);
const SVG='http://www.w3.org/2000/svg';
const NAMES={dpad:['Up / down','Left / right'],slider:['Slider up / down'],joy:['Up / down','Left / right'],button:['Button']};
let layout=load(), editing=false, nextId=100, remoteMode=loadMode();
function loadMode(){ try{ return localStorage.getItem('gtac-mode')!=='muscle'; }catch(_){ return true; } }
function setMode(remote){
  remoteMode=remote; try{localStorage.setItem('gtac-mode',remote?'remote':'muscle')}catch(_){}
  if(!remote && editing) $('edit').click();
  $('mRemote').classList.toggle('sel',remote); $('mMuscle').classList.toggle('sel',!remote);
  $('panel').classList.toggle('muscle',!remote); releaseAll();
  if(document.readyState!=='loading') $('status').textContent=remote?'Hold the controls to move the arm':'Muscle sensor mode';
}
const outs={};                     // widget id -> signed speed level (-3..3) for each axis

function defaults(){return [
  {id:1,t:'dpad',size:2,ax:[{m:'E',rev:false,sp:2},{m:'B',rev:false,sp:2}]},
  {id:2,t:'slider',size:2,ax:[{m:'C',rev:false,sp:3}]}];}
function load(){
  try{const s=localStorage.getItem(KEY); if(s){const l=JSON.parse(s); if(Array.isArray(l)&&l.length) return l;}}catch(_){}
  return defaults();
}
function save(){ try{localStorage.setItem(KEY,JSON.stringify(layout))}catch(_){} }

/* ---------- talking to the board ---------- */
let busy=false, dirty=false;
function digits(){
  const lv=[0,0,0,0,0];
  if(!remoteMode) return '00000';
  for(const w of layout){ const o=outs[w.id]||[]; w.ax.forEach((a,i)=>{
    const k=MOTORS.indexOf(a.m); if(k<0) return;
    lv[k]+=(a.rev?-1:1)*(o[i]||0); }); }
  return lv.map(l=>{l=Math.max(-3,Math.min(3,l)); return l>=0?l:3-l;}).join('');
}
/* Live link to the board (WebSocket): presses go out at once and muscle readings stream in.
   If it cannot connect, the page falls back to ordinary requests. */
let ws=null, wsOpen=false;
function connectWS(){
  try{ ws=new WebSocket('ws://'+location.host+'/ws'); }catch(_){ ws=null; setTimeout(connectWS,3000); return; }
  ws.onopen=()=>{ wsOpen=true; $('status').textContent='Connected (live)'; send(); };
  ws.onmessage=e=>handleReply(String(e.data));
  ws.onclose=()=>{ wsOpen=false; setTimeout(connectWS,1500); };
  ws.onerror=()=>{ try{ws.close()}catch(_){} };
}
function handleReply(t){
  const parts=t.split(' ');                         // "ok" or "ok <muscle %>" when the board has a muscle sensor
  if(parts.length>1){ $('modes').classList.add('show');
    const p=Math.max(0,Math.min(100,parseInt(parts[1])||0));
    $('pct').textContent=p+'%'; addSample(p); }
}
function send(){
  const msg='m='+digits()+'&x='+(remoteMode?1:0);
  if(wsOpen){ try{ ws.send(msg); return; }catch(_){ wsOpen=false; } }
  if(busy){dirty=true;return;}
  busy=true; dirty=false;
  fetch('/s?'+msg,{cache:'no-store'})
    .then(r=>r.text()).then(t=>{ if(!wsOpen) $('status').textContent='Connected'; handleReply(t); })
    .catch(()=>{ if(!wsOpen) $('status').textContent='Not connected: check the Wi-Fi'})
    .finally(()=>{busy=false; if(dirty) send();});
}
function setOut(w,i,v){
  const o=outs[w.id]||(outs[w.id]=[0,0]);
  if(o[i]!==v){o[i]=v; send(); return true;} return false;
}
function releaseAll(){ for(const id in outs) outs[id]=[0,0]; document.querySelectorAll('.on').forEach(e=>e.classList.remove('on')); send(); }
function zone(v,sp){                 // how far a slider or stick is pushed -> speed level
  const a=Math.abs(v); if(a<0.2) return 0;
  const f=Math.min(1,(a-0.2)/0.8), l=1+Math.min(sp-1,Math.floor(f*sp));
  return v<0?-l:l;
}
function el(tag,cls,html){const e=document.createElement(tag); if(cls) e.className=cls; if(html!==undefined) e.innerHTML=html; return e;}
function caption(w){
  const names=w.ax.filter(a=>a.m).map(a=>'Motor '+a.m);
  if(w.t==='button') return (w.name||'Button')+(names.length?' · '+names[0]:'');
  return names.join(' · ')||'No motor chosen';
}
function pointerHold(node,w,onDown,onMove,onUp){
  let id=null;
  node.addEventListener('pointerdown',e=>{ if(editing||!remoteMode) return; e.preventDefault(); id=e.pointerId;
    try{node.setPointerCapture(e.pointerId)}catch(_){} onDown(e); });
  node.addEventListener('pointermove',e=>{ if(e.pointerId===id) onMove(e); });
  ['pointerup','pointercancel','lostpointercapture'].forEach(n=>node.addEventListener(n,e=>{ if(e.pointerId===id){ id=null; onUp(e);} }));
}

/* ---------- the four kinds of widget ---------- */
function buildDpad(w){
  const box=el('div','dpad');
  box.innerHTML='<svg viewBox="0 0 200 200"><circle cx="100" cy="100" r="100" fill="#0ba89a"/>'+
    '<rect class="arm V" x="68" y="14" width="64" height="172" rx="32"/><rect class="arm H" x="14" y="68" width="172" height="64" rx="32"/>'+
    '<path class="arrow U" d="M100 32 L112 50 L88 50 Z"/><path class="arrow D" d="M100 168 L112 150 L88 150 Z"/>'+
    '<path class="arrow L" d="M32 100 L50 88 L50 112 Z"/><path class="arrow R" d="M168 100 L150 88 L150 112 Z"/></svg>';
  const q=s=>box.querySelector(s);
  function paint(){ const o=outs[w.id]||[0,0];
    q('.U').classList.toggle('on',o[0]>0); q('.D').classList.toggle('on',o[0]<0);
    q('.R').classList.toggle('on',o[1]>0); q('.L').classList.toggle('on',o[1]<0);
    q('.V').classList.toggle('on',o[0]!==0); q('.H').classList.toggle('on',o[1]!==0); }
  function at(e){
    const r=box.getBoundingClientRect(), R=r.width/2, dx=e.clientX-(r.left+R), dy=e.clientY-(r.top+R), d=Math.hypot(dx,dy);
    let up=0, side=0;
    if(d>0.2*R){ if(Math.abs(dy)>0.38*d) up=dy<0?1:-1; if(Math.abs(dx)>0.38*d) side=dx>0?1:-1; }
    setOut(w,0,up*w.ax[0].sp); setOut(w,1,side*w.ax[1].sp); paint();
  }
  pointerHold(box,w,at,at,()=>{setOut(w,0,0); setOut(w,1,0); paint();});
  return box;
}
function buildSlider(w){
  const track=el('div','track'), handle=el('div','handle','<i></i><i></i>'); track.appendChild(handle);
  function at(e){
    const r=track.getBoundingClientRect(), h=handle.offsetHeight, half=(r.height-h)/2, mid=r.top+r.height/2;
    const off=Math.max(-half,Math.min(half,e.clientY-mid));
    handle.classList.remove('back'); handle.style.top=(r.height/2+off)+'px';
    const l=zone(-off/half,w.ax[0].sp); setOut(w,0,l); handle.classList.toggle('on',l!==0);
  }
  function home(){ handle.classList.add('back'); handle.style.top='50%'; setOut(w,0,0); handle.classList.remove('on'); }
  pointerHold(track,w,at,at,home);
  return track;
}
function buildJoy(w){
  const base=el('div','joy'), knob=el('div','knob'); base.appendChild(knob);
  function at(e){
    const r=base.getBoundingClientRect(), R=r.width/2, lim=R*0.62;
    let dx=e.clientX-(r.left+R), dy=e.clientY-(r.top+R); const d=Math.hypot(dx,dy);
    if(d>lim){dx*=lim/d; dy*=lim/d;}
    knob.classList.remove('back'); knob.style.left=(R+dx)+'px'; knob.style.top=(R+dy)+'px';
    const a=zone(-dy/lim,w.ax[0].sp), b=zone(dx/lim,w.ax[1].sp);
    setOut(w,0,a); setOut(w,1,b); knob.classList.toggle('on',a!==0||b!==0);
  }
  function home(){ knob.style.left='50%'; knob.style.top='50%'; setOut(w,0,0); setOut(w,1,0); knob.classList.remove('on'); }
  pointerHold(base,w,at,at,home);
  return base;
}
function buildButton(w){
  const b=el('button','btn'); b.textContent=w.name||'Hold';
  pointerHold(b,w,()=>{b.classList.add('on'); setOut(w,0,w.ax[0].sp);},()=>{},()=>{b.classList.remove('on'); setOut(w,0,0);});
  b.addEventListener('contextmenu',e=>e.preventDefault());
  return b;
}
const BUILD={dpad:buildDpad,slider:buildSlider,joy:buildJoy,button:buildButton};

/* ---------- drawing the whole remote ---------- */
function render(){
  const board=$('board'); board.innerHTML='';
  layout.forEach((w,idx)=>{
    outs[w.id]=[0,0];
    const box=el('div','wgt sz'+w.size);
    box.appendChild(BUILD[w.t](w));
    box.appendChild(el('div','cap',caption(w)));
    const tools=el('div','tools');
    [['◀','left'],['▶','right'],['⚙','set'],['⤢','size'],['✕','del']].forEach(([txt,act])=>{
      const b=el('button',null,txt); b.setAttribute('aria-label',act);
      b.addEventListener('click',()=>tool(act,idx)); tools.appendChild(b); });
    box.appendChild(tools); board.appendChild(box);
  });
  send();
}
function tool(act,idx){
  const w=layout[idx];
  if(act==='left'&&idx>0){layout.splice(idx-1,2,layout[idx],layout[idx-1]);}
  else if(act==='right'&&idx<layout.length-1){layout.splice(idx,2,layout[idx+1],layout[idx]);}
  else if(act==='size'){w.size=w.size%3+1;}
  else if(act==='del'){ layout.splice(idx,1); }
  else if(act==='set'){ openDialog(w); return; }
  save(); render();
}
function addWidget(t){
  const used=new Set(layout.flatMap(w=>w.ax.map(a=>a.m)));
  const free=MOTORS.filter(m=>!used.has(m));
  const n=NAMES[t].length, ax=[];
  for(let i=0;i<n;i++) ax.push({m:free[i]||'',rev:false,sp:t==='slider'||t==='joy'?3:2});
  layout.push({id:nextId++,t:t,size:2,ax:ax,name:t==='button'?'Hold':''});
  save(); render();
}

/* ---------- settings window for one widget ---------- */
function openDialog(w){
  const box=$('dlgbox'); box.innerHTML='';
  const title={dpad:'D-pad',slider:'Slider',joy:'Joystick',button:'Button'}[w.t];
  box.appendChild(el('h2',null,title+': choose the motors'));
  if(w.t==='button'){
    const d=el('div','ax'); d.innerHTML='<b>Name on the button</b>';
    const i=el('input'); i.type='text'; i.maxLength=10; i.value=w.name||'';
    i.addEventListener('input',()=>{w.name=i.value; save();}); d.appendChild(i); box.appendChild(d);
  }
  w.ax.forEach((a,i)=>{
    const d=el('div','ax'); d.appendChild(el('b',null,NAMES[w.t][i]));
    const sel=el('select'); sel.innerHTML='<option value="">No motor</option>'+MOTORS.map(m=>'<option value="'+m+'"'+(a.m===m?' selected':'')+'>Motor '+m+'</option>').join('');
    sel.addEventListener('change',()=>{a.m=sel.value; save();});
    const rev=el('label',null,'<input type="checkbox"'+(a.rev?' checked':'')+'> Reverse');
    rev.firstChild.addEventListener('change',e=>{a.rev=e.target.checked; save();});
    const sp=el('select'); const analog=(w.t==='slider'||w.t==='joy');
    sp.innerHTML=[['Slow',1],['Medium',2],['Fast',3]].map(([n,v])=>'<option value="'+v+'"'+(a.sp===v?' selected':'')+'>'+(analog?'Top speed: ':'Speed: ')+n+'</option>').join('');
    sp.addEventListener('change',()=>{a.sp=+sp.value; save();});
    d.appendChild(sel); d.appendChild(document.createTextNode(' ')); d.appendChild(sp);
    const lab=el('div'); lab.style.marginTop='8px'; lab.appendChild(rev); d.appendChild(lab);
    box.appendChild(d);
  });
  const done=el('button','done','Done'); done.addEventListener('click',()=>{$('dlg').classList.remove('open'); render();});
  box.appendChild(done); $('dlg').classList.add('open');
}

/* ---------- top buttons ---------- */
$('edit').addEventListener('click',()=>{
  editing=!editing; releaseAll();
  $('panel').classList.toggle('editing',editing); $('edit').classList.toggle('sel',editing);
  $('status').textContent=editing?'Change the remote: add, move, resize or set up the controls':'Hold the controls to move the arm';
});
document.querySelectorAll('[data-add]').forEach(b=>b.addEventListener('click',()=>addWidget(b.dataset.add)));
$('reset').addEventListener('click',()=>{ if(confirm('Go back to the starting remote?')){ layout=defaults(); save(); render(); } });

document.addEventListener('contextmenu',e=>e.preventDefault());
/* ---------- rolling muscle graph: last 30 seconds, 0-100 % ---------- */
const WINDOW_MS=30000, samples=[];
function addSample(v){ const t=performance.now(); samples.push([t,v]);
  while(samples.length && samples[0][0]<t-WINDOW_MS-1000) samples.shift(); }
function drawGraph(){
  const c=$('graph'), dpr=window.devicePixelRatio||1, w=c.clientWidth, h=c.clientHeight;
  if(!w||!h) return;
  if(c.width!==Math.round(w*dpr)||c.height!==Math.round(h*dpr)){ c.width=Math.round(w*dpr); c.height=Math.round(h*dpr); }
  const g=c.getContext('2d'); g.setTransform(dpr,0,0,dpr,0,0); g.clearRect(0,0,w,h);
  const L=44, R=10, T=10, B=26, pw=w-L-R, ph=h-T-B, now=performance.now();
  const X=t=>L+pw*(1-(now-t)/WINDOW_MS), Y=v=>T+ph*(1-v/100);
  g.font='12px system-ui,-apple-system,Arial,sans-serif'; g.textBaseline='middle';
  for(const v of [0,25,50,75,100]){                       // scale: 0 - 100 %
    g.strokeStyle=v===0?'#3a3a3a':'#262626'; g.lineWidth=1;
    g.beginPath(); g.moveTo(L,Y(v)+.5); g.lineTo(L+pw,Y(v)+.5); g.stroke();
    g.fillStyle='#7a7a7a'; g.textAlign='right'; g.fillText(v+'%',L-8,Y(v)); }
  g.textAlign='center'; g.textBaseline='top';
  for(const s of [30,20,10,0]){                           // time: 30 seconds ago .. now
    const x=L+pw*(1-s/30); g.strokeStyle='#202020';
    g.beginPath(); g.moveTo(x+.5,T); g.lineTo(x+.5,T+ph); g.stroke();
    g.fillStyle='#7a7a7a'; g.fillText(s===0?'now':'-'+s+' s',x,T+ph+8); }
  const pts=samples.filter(p=>p[0]>=now-WINDOW_MS-1000);
  if(pts.length<2) return;
  g.save(); g.beginPath(); g.rect(L,T,pw,ph); g.clip();
  const grad=g.createLinearGradient(0,T,0,T+ph); grad.addColorStop(0,'rgba(11,168,154,.45)'); grad.addColorStop(1,'rgba(11,168,154,0)');
  g.beginPath(); g.moveTo(X(pts[0][0]),Y(0));
  for(const p of pts) g.lineTo(X(p[0]),Y(p[1]));
  g.lineTo(X(pts[pts.length-1][0]),Y(0)); g.closePath(); g.fillStyle=grad; g.fill();
  g.beginPath(); pts.forEach((p,i)=>i?g.lineTo(X(p[0]),Y(p[1])):g.moveTo(X(p[0]),Y(p[1])));
  g.strokeStyle='#3fe0cf'; g.lineWidth=2.5; g.lineJoin='round'; g.stroke();
  const last=pts[pts.length-1]; g.fillStyle='#e8fffc';
  g.beginPath(); g.arc(X(last[0]),Y(last[1]),4,0,Math.PI*2); g.fill();
  g.restore();
}
(function loop(){ if(!remoteMode) drawGraph(); requestAnimationFrame(loop); })();
setInterval(()=>{ if(!remoteMode && !wsOpen) send(); },150);  // no live link: ask for muscle readings ~7 times a second

$('mRemote').addEventListener('click',()=>setMode(true));
$('mMuscle').addEventListener('click',()=>setMode(false));
/* iPad: never zoom (double-tap or pinch) */
let lastTouch=0;
document.addEventListener('touchend',e=>{ const n=Date.now(); if(n-lastTouch<350 && !e.target.closest('select,input')) e.preventDefault(); lastTouch=n; },{passive:false});
document.addEventListener('dblclick',e=>e.preventDefault(),{passive:false});
['gesturestart','gesturechange','gestureend'].forEach(n=>document.addEventListener(n,e=>e.preventDefault(),{passive:false}));
setInterval(send,500);       // heartbeat: tells the board the page is open
window.addEventListener('blur',()=>{ releaseAll(); render(); });
document.addEventListener('visibilitychange',()=>{ if(document.hidden){ releaseAll(); render(); } });
render();
setMode(remoteMode);
connectWS();
</script></body></html>"""

LANDING = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>Robot arm</title><style>
*{touch-action:manipulation}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0a0a0a;
font-family:system-ui,-apple-system,Arial,sans-serif;color:#bbb;text-align:center}
.box{background:#121212;border:10px solid #2b2b2b;border-radius:28px;padding:32px 24px;width:min(92vw,520px)}
h1{color:#e8fffc;font-size:1.5em;margin:0 0 18px}
a{display:block;background:#0ba89a;color:#06211e;font-weight:700;font-size:1.3em;text-decoration:none;
border-radius:999px;padding:18px;margin:10px 0 18px}
p{line-height:1.45;margin:8px 0}</style></head><body><div class="box">
<h1>Robot arm</h1>
<a href="http://1.1.1.1/">Open the remote</a>
<p>You can also open <b>Safari</b> and go to <b>1.1.1.1</b> for the full-screen remote.</p>
<p>If a <b>Done</b> button appears at the top, tap <b>Done</b> to stay on this Wi-Fi. Do not tap Cancel.</p>
</div></body></html>"""

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_LIVE = 4                    # live (WebSocket) connections kept open at once


def ws_frame(text):
    """One WebSocket text message from the board."""
    data = text.encode()
    if len(data) < 126:
        return bytes((0x81, len(data))) + data
    return bytes((0x81, 126, len(data) >> 8, len(data) & 255)) + data


def ws_accept_key(key):
    digest = hashlib.sha1((key + WS_GUID).encode()).digest()
    return ubinascii.b2a_base64(digest).strip().decode()


# What phones and tablets expect from a network that is "open" (no sign-in needed)
APPLE_OK = "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"


def encode_frame(index, state):
    return BASE_MM + STEP_MM * (index * 7 + state)


def parse_request(line):
    """From 'GET /s?m=00600&x=1 HTTP/1.1' return ([0, 0, 6, 0, 0], True), or None.

    x=1: the page wants remote mode, x=0: muscle sensor mode (x missing counts as remote)."""
    parts = line.split(" ")
    if len(parts) < 2 or not parts[1].startswith("/s?m="):
        return None
    text = parts[1][5:]
    want_remote = True
    if "&x=" in text:
        text, flag = text.split("&x=", 1)
        want_remote = flag[:1] != "0"
    if len(text) != MOTOR_COUNT:
        return None
    states = []
    for ch in text:
        if ch < "0" or ch > "6":
            return None
        states.append(int(ch))
    return states, want_remote


def dns_reply(query, ip):
    """Answer any DNS question with our own address, so every web address leads to the remote."""
    if len(query) < 12:
        return None
    end = 12
    while end < len(query) and query[end] != 0:     # skip the question name
        end += query[end] + 1
    end += 5                                        # zero byte, type, class
    if end > len(query):
        return None
    header = query[:2] + b"\x81\x80" + query[4:6] + query[4:6] + b"\x00\x00\x00\x00"
    answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + bytes(int(n) for n in ip.split("."))
    return header + query[12:end] + answer


class WebRemote:
    def __init__(self):
        self.states = [0] * MOTOR_COUNT
        self.pending = []           # motors whose state just changed: sent first
        self.rotate = 0             # then every motor in turn, so a lost frame is repaired
        self.last_message = utime.ticks_ms()
        self.seen_page = False      # has any page been opened since power-up?
        self.want_remote = True     # the page's Remote / Muscle sensor toggle
        self.muscle_percent = None  # set by arm_board.py: the page then shows the toggle and a muscle meter
        self.accepted = []          # devices that opened the remote: told the network is "open"
        self.live = []              # open WebSocket connections: [socket, unread bytes]

        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        self.ssid = WIFI_NAME
        if ADD_BOARD_CODE:
            self.ssid += "-" + ubinascii.hexlify(ap.config("mac")[-2:]).decode().upper()
        ap.config(essid=self.ssid, password=WIFI_PASSWORD, authmode=3)
        try:
            ap.ifconfig((ADDRESS, "255.255.255.0", ADDRESS, ADDRESS))
        except Exception as error:
            print("Could not set the address:", error)
        self.ap = ap

        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("0.0.0.0", 80))
        self.server.listen(4)
        self.server.setblocking(False)

        self.dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.dns.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.dns.bind(("0.0.0.0", 53))
        self.dns.setblocking(False)
        print("Wi-Fi:", self.ssid, "password:", WIFI_PASSWORD, "-> open http://" + ADDRESS)

    def set_states(self, states):
        for i in range(MOTOR_COUNT):
            if states[i] != self.states[i]:
                self.states[i] = states[i]
                if i not in self.pending:
                    self.pending.append(i)

    def poll(self):
        """Answer one waiting DNS question and one web request, if there are any. Never waits long."""
        try:
            query, sender = self.dns.recvfrom(512)
            reply = dns_reply(query, ADDRESS)
            if reply:
                self.dns.sendto(reply, sender)
        except OSError:
            pass

        try:
            client, address = self.server.accept()
        except OSError:
            client = None
        if client is not None:
            keep = False
            try:
                client.settimeout(0.3)
                request = client.recv(600).decode()
                keep = self.answer(client, request, address[0])
            except Exception:
                pass
            finally:
                if not keep:
                    try:
                        client.close()
                    except Exception:
                        pass

        self.read_live()

        # The page stopped talking (closed, Wi-Fi lost): let go of every control.
        if utime.ticks_diff(utime.ticks_ms(), self.last_message) > RELEASE_AFTER_MS:
            self.set_states([0] * MOTOR_COUNT)

    def answer(self, client, request, device):
        lines = request.split("\r\n")
        line = lines[0]
        host = ""
        for header in lines[1:]:
            if header.lower().startswith("host:"):
                host = header[5:].strip().split(":")[0].lower()
        parts = line.split(" ")
        path = parts[1] if len(parts) > 1 else "/"

        if path.startswith("/ws"):
            # Open a live WebSocket link
            key = ""
            for header in lines[1:]:
                if header.lower().startswith("sec-websocket-key:"):
                    key = header.split(":", 1)[1].strip()
            if not key:
                client.write(b"HTTP/1.0 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
                return False
            client.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                          "Sec-WebSocket-Accept: %s\r\n\r\n" % ws_accept_key(key)).encode())
            client.setblocking(False)
            if len(self.live) >= MAX_LIVE:
                self.close_live(self.live[0])
            self.live.append([client, b""])
            if device not in self.accepted:
                self.accepted.append(device)
            return True

        if self.handle_message(line):
            body = self.reply_text()
            client.write(("HTTP/1.0 200 OK\r\nCache-Control: no-store\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body)).encode())
            return False

        if host == ADDRESS and (path == "/" or path.startswith("/index")):
            # The remote itself
            self.last_message = utime.ticks_ms()
            self.seen_page = True
            if device not in self.accepted:
                self.accepted.append(device)
                if len(self.accepted) > 20:
                    self.accepted.pop(0)
            self.send_page(client, PAGE)
            return

        if path.startswith("/favicon"):
            client.write(b"HTTP/1.0 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            return

        if device in self.accepted:
            # This device already opened the remote: tell it the network is fine, so it stays connected
            if path.startswith("/generate_204") or path.startswith("/gen_204"):
                client.write(b"HTTP/1.0 204 No Content\r\nContent-Length: 0\r\n\r\n")
                return
            if "hotspot-detect" in path or host.endswith("apple.com"):
                client.write(("HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\n\r\n%s" % (len(APPLE_OK), APPLE_OK)).encode())
                return

        # Anything else (a sign-in check, or any other web address): the landing page
        self.send_page(client, LANDING)
        return False

    def handle_message(self, line):
        """A control message from the page (a request line, or the text of a live message)."""
        message = parse_request(line)
        if message is None:
            return False
        states, self.want_remote = message
        self.set_states(states if self.want_remote else [0] * MOTOR_COUNT)
        self.last_message = utime.ticks_ms()
        self.seen_page = True
        return True

    def reply_text(self):
        return "ok" if self.muscle_percent is None else "ok %d" % self.muscle_percent

    # ---- live WebSocket links
    def close_live(self, item):
        try:
            item[0].close()
        except Exception:
            pass
        if item in self.live:
            self.live.remove(item)

    def read_live(self):
        for item in list(self.live):
            sock = item[0]
            try:
                data = sock.recv(256)
            except OSError:
                data = None                 # nothing waiting
            if data is not None:
                if not data:
                    self.close_live(item)   # the page went away
                    continue
                item[1] += data
            buf = item[1]
            while len(buf) >= 2:
                opcode = buf[0] & 0x0F
                masked = buf[1] & 0x80
                length = buf[1] & 0x7F
                start = 2
                if length == 126:
                    if len(buf) < 4:
                        break
                    length = (buf[2] << 8) | buf[3]
                    start = 4
                elif length == 127:
                    self.close_live(item)
                    buf = b""
                    break
                mask_at = start
                if masked:
                    start += 4
                if len(buf) < start + length:
                    break
                payload = bytearray(buf[start:start + length])
                if masked:
                    for i in range(length):
                        payload[i] ^= buf[mask_at + (i & 3)]
                buf = buf[start + length:]
                if opcode == 1:                                     # text: a control message
                    if self.handle_message("GET /s?" + bytes(payload).decode() + " HTTP/1.1"):
                        self.send_live(item, self.reply_text())
                elif opcode == 8:                                   # close
                    self.close_live(item)
                    buf = b""
                    break
                elif opcode == 9:                                   # ping -> pong
                    try:
                        sock.write(bytes((0x8A, len(payload))) + payload)
                    except Exception:
                        pass
            item[1] = buf

    def send_live(self, item, text):
        try:
            item[0].write(ws_frame(text))
        except Exception:
            self.close_live(item)

    def push_muscle(self, percent):
        """Stream the muscle reading to every live page (for the graph)."""
        self.muscle_percent = percent
        if self.live:
            text = "ok %d" % percent
            for item in list(self.live):
                self.send_live(item, text)

    def send_page(self, client, page):
        client.settimeout(3)
        client.write(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nCache-Control: no-store\r\n\r\n")
        for start in range(0, len(page), 1024):
            client.write(page[start:start + 1024].encode())

    def page_active(self):
        """True while someone has the remote page open."""
        return self.seen_page and utime.ticks_diff(utime.ticks_ms(), self.last_message) < PAGE_TIMEOUT_MS

    def remote_wanted(self):
        """True while the page is open AND set to Remote (not Muscle sensor)."""
        return self.page_active() and self.want_remote

    def has_urgent(self):
        """A motor just changed: the hub should hear about it now."""
        return len(self.pending) > 0

    def next_distance_mm(self):
        """The next motor message for the hub."""
        if self.pending:
            index = self.pending.pop(0)
        else:
            index = self.rotate
            self.rotate = (self.rotate + 1) % MOTOR_COUNT
        return encode_frame(index, self.states[index])


def main():
    if not hasattr(lpf2.LPF2, "_send_info_sequence"):
        raise RuntimeError("lpf2.py is too old. Copy the newest lpf2.py from the PUPRemote project onto the board.")

    remote = WebRemote()
    sensor = DistanceSensorEmulator(make_modes(), sensor_id=62, debug=DEBUG)
    last_frame = utime.ticks_ms()

    while True:
        remote.poll()

        held = utime.ticks_diff(utime.ticks_ms(), last_frame)
        if held >= FRAME_MS or (remote.has_urgent() and held >= HOLD_MS):
            last_frame = utime.ticks_ms()
            mm = remote.next_distance_mm()
            sensor.update_payload(mm, 0)                  # DISTL
            sensor.update_payload(min(mm, 320), 1)        # DISTS
            sensor.update_payload(mm, 2)                  # SINGL
            sensor.update_payload(int(mm * 5.83), 4)      # TRAW
            sensor.update_payload(mm, 7)                  # ADRAW

        sensor.heartbeat()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise                      # Ctrl+C / Stop in Thonny still works
    except Exception as error:
        print("Error:", error)
        utime.sleep_ms(3000)
        machine.reset()
