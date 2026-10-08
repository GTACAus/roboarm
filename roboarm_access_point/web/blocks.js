'use strict';
/* GTAC Robot Arm: the blocks students code with, and a small interpreter that runs them.
   Bundled after Blockly's core into blockly.js. Uses window.Arm (app.js) to move the motors. */
(function () {
  const C = { event: '#FFCD1F', control: '#FF6D3A', motor: '#4C34E5', sense: '#00BC74', op: '#9B83F0' };
  const MOTOR = [['Motor B', 'B'], ['Motor C', 'C'], ['Motor D', 'D'], ['Motor E', 'E'], ['Motor F', 'F']];
  const CONTROL = [['1', '1'], ['2', '2'], ['3', '3'], ['4', '4'], ['5', '5']];
  const ACTION = [['up', 'up'], ['down', 'down'], ['left', 'left'], ['right', 'right'], ['button', 'pressed'], ['let go', 'released']];
  const HOLD = ACTION.slice(0, 5);
  const SPEED = [['slow', '1'], ['medium', '2'], ['fast', '3']];
  const DEG_PER_S = [0, 60, 150, 300];      // the hub program's slow / medium / fast
  const dd = (name, options) => ({ type: 'field_dropdown', name, options });
  const num = (name) => ({ type: 'input_value', name, check: 'Number' });
  const stmt = (name) => ({ type: 'input_statement', name });
  const hat = (o) => Object.assign({ nextStatement: null, colour: C.event }, o);
  const cmd = (o) => Object.assign({ previousStatement: null, nextStatement: null }, o);

  Blockly.defineBlocksWithJsonArray([
    // ---------- events
    hat({ type: 'ev_start', message0: 'when program starts' }),
    hat({ type: 'ev_control', message0: 'when remote %1 %2', args0: [dd('N', CONTROL), dd('ACTION', ACTION)],
      tooltip: 'Runs when you use a control on the remote. The numbers match the yellow badges.' }),
    hat({ type: 'ev_muscle', message0: 'when muscle signal goes above %1 %', args0: [num('PCT')], inputsInline: true }),
    // ---------- control
    cmd({ type: 'c_wait', message0: 'wait %1 seconds', args0: [num('S')], inputsInline: true, colour: C.control }),
    cmd({ type: 'c_repeat', message0: 'repeat %1 times %2 %3', args0: [num('N'), { type: 'input_dummy' }, stmt('DO')], colour: C.control }),
    { type: 'c_forever', message0: 'forever %1 %2', args0: [{ type: 'input_dummy' }, stmt('DO')], previousStatement: null, colour: C.control },
    cmd({ type: 'c_if', message0: 'if %1 then %2 %3', args0: [{ type: 'input_value', name: 'IF', check: 'Boolean' }, { type: 'input_dummy' }, stmt('DO')], colour: C.control }),
    cmd({ type: 'c_ifelse', message0: 'if %1 then %2 %3 else %4', args0: [{ type: 'input_value', name: 'IF', check: 'Boolean' }, { type: 'input_dummy' }, stmt('DO'), stmt('ELSE')], colour: C.control }),
    cmd({ type: 'c_until', message0: 'wait until %1', args0: [{ type: 'input_value', name: 'IF', check: 'Boolean' }], colour: C.control }),
    { type: 'c_end', message0: 'stop this program', previousStatement: null, colour: C.control },
    // ---------- motors
    cmd({ type: 'm_go', message0: 'go %1 to position %2 ° %3', inputsInline: true, colour: C.motor,
      args0: [dd('M', MOTOR), num('A'), dd('DIR', [['shortest path', '0'], ['clockwise', '1'], ['counter-clockwise', '2']])],
      tooltip: 'Turns the motor to an angle (0 to 359 degrees).' }),
    cmd({ type: 'm_turn', message0: 'turn %1 %2 %3 degrees', inputsInline: true, colour: C.motor,
      args0: [dd('M', MOTOR), dd('DIR', [['forward', '1'], ['back', '-1']]), num('D')],
      tooltip: 'Turns the motor this many degrees from where it is now (360 = one full turn).' }),
    cmd({ type: 'm_stop', message0: 'stop motor %1', args0: [dd('M', MOTOR.map(([a, b]) => [b, b]))], colour: C.motor }),
    cmd({ type: 'm_start', message0: 'start %1 %2', args0: [dd('M', MOTOR), dd('DIR', [['forward', '1'], ['back', '-1']])], colour: C.motor }),
    cmd({ type: 'm_for', message0: 'run %1 %2 for %3 seconds', inputsInline: true, args0: [dd('M', MOTOR), dd('DIR', [['forward', '1'], ['back', '-1']]), num('S')], colour: C.motor }),
    cmd({ type: 'm_speed', message0: 'set %1 speed to %2', args0: [dd('M', MOTOR), dd('SP', SPEED)], colour: C.motor }),
    cmd({ type: 'm_home', message0: 'move all motors home', colour: C.motor }),
    cmd({ type: 'm_stopall', message0: 'stop all motors', colour: C.motor }),
    // ---------- sensing
    { type: 's_muscle', message0: 'muscle signal %', output: 'Number', colour: C.sense },
    { type: 's_pos', message0: '%1 position', args0: [dd('M', MOTOR)], output: 'Number', colour: C.sense },
    { type: 's_held', message0: 'remote %1 %2 is held', args0: [dd('N', CONTROL), dd('ACTION', HOLD)], output: 'Boolean', colour: C.sense },
    // ---------- operators
    { type: 'o_num', message0: '%1', args0: [{ type: 'field_number', name: 'V', value: 0 }], output: 'Number', colour: C.op },
    { type: 'o_compare', message0: '%1 %2 %3', inputsInline: true, output: 'Boolean', colour: C.op,
      args0: [num('A'), dd('OP', [['<', 'lt'], ['=', 'eq'], ['>', 'gt']]), num('B')] },
    { type: 'o_logic', message0: '%1 %2 %3', inputsInline: true, output: 'Boolean', colour: C.op,
      args0: [{ type: 'input_value', name: 'A', check: 'Boolean' }, dd('OP', [['and', 'and'], ['or', 'or']]), { type: 'input_value', name: 'B', check: 'Boolean' }] },
    { type: 'o_not', message0: 'not %1', args0: [{ type: 'input_value', name: 'A', check: 'Boolean' }], output: 'Boolean', colour: C.op },
    { type: 'o_math', message0: '%1 %2 %3', inputsInline: true, output: 'Number', colour: C.op,
      args0: [num('A'), dd('OP', [['+', 'add'], ['−', 'sub'], ['×', 'mul'], ['÷', 'div']]), num('B')] },
    { type: 'o_random', message0: 'pick random %1 to %2', inputsInline: true, output: 'Number', colour: C.op, args0: [num('A'), num('B')] }
  ]);

  const n = (name, v) => '<value name="' + name + '"><shadow type="o_num"><field name="V">' + v + '</field></shadow></value>';
  const TOOLBOX = '<xml>' +
    '<category name="Motors" colour="' + C.motor + '"><block type="m_turn">' + n('D', 5) + '</block><block type="m_speed"></block>' +
      '<block type="m_go">' + n('A', 90) + '</block><block type="m_stop"></block>' +
      '<block type="m_start"></block><block type="m_for">' + n('S', 1) + '</block>' +
      '<block type="m_home"></block><block type="m_stopall"></block></category>' +
    '<category name="Events" colour="' + C.event + '"><block type="ev_start"></block><block type="ev_control"></block>' +
      '<block type="ev_muscle">' + n('PCT', 50) + '</block></category>' +
    '<category name="Control" colour="' + C.control + '"><block type="c_wait">' + n('S', 1) + '</block>' +
      '<block type="c_repeat">' + n('N', 4) + '</block><block type="c_forever"></block><block type="c_if"></block>' +
      '<block type="c_ifelse"></block><block type="c_until"></block><block type="c_end"></block></category>' +
    '<category name="Sensing" colour="' + C.sense + '"><block type="s_muscle"></block><block type="s_pos"></block><block type="s_held"></block></category>' +
    '<category name="Operators" colour="' + C.op + '"><block type="o_compare">' + n('A', 0) + n('B', 50) + '</block>' +
      '<block type="o_logic"></block><block type="o_not"></block><block type="o_math">' + n('A', 0) + n('B', 0) + '</block>' +
      '<block type="o_random">' + n('A', 1) + n('B', 10) + '</block><block type="o_num"></block></category></xml>';

  const theme = Blockly.Theme.defineTheme('gtac', {
    name: 'gtac',
    componentStyles: { workspaceBackgroundColour: '#F9F6E7', toolboxBackgroundColour: '#272A24', toolboxForegroundColour: '#F9F6E7',
      flyoutBackgroundColour: '#ECE7D1', flyoutForegroundColour: '#272A24', flyoutOpacity: 1, scrollbarColour: '#C9C3AA',
      insertionMarkerColour: '#4C34E5', cursorColour: '#4C34E5' },
    fontStyle: { family: 'Figtree, system-ui, -apple-system, Arial, sans-serif', weight: '700', size: 14 }
  });
  const KEY = 'gtac-blocks-v2';
  // The starting program does what the starting remote does: each control turns its motor 5 degrees.
  const turn = (n, action, motor, dir, x, y) => ({ type: 'ev_control', x, y, fields: { N: String(n), ACTION: action },
    next: { block: { type: 'm_turn', fields: { M: motor, DIR: dir }, inputs: { D: { shadow: { type: 'o_num', fields: { V: 5 } } } } } } });
  const STARTER = { blocks: { languageVersion: 0, blocks: [
    turn(1, 'up', 'E', '1', 20, 20), turn(1, 'down', 'E', '-1', 20, 130),
    turn(1, 'left', 'B', '-1', 20, 240), turn(1, 'right', 'B', '1', 20, 350),
    turn(2, 'up', 'C', '1', 20, 460), turn(2, 'down', 'C', '-1', 20, 570)] } };

  let ws = null;            // the visible workspace (once the canvas has been opened)
  let hidden = null;        // a workspace without a screen, to run programs without opening the canvas
  function workspace() {
    if (ws) return ws;
    if (!hidden) { hidden = new Blockly.Workspace(); load(hidden); }
    return hidden;
  }
  function load(w) {
    let json = null;
    try { json = JSON.parse(localStorage.getItem(KEY)); } catch (_) {}
    try { Blockly.serialization.workspaces.load(json || STARTER, w); } catch (_) { Blockly.serialization.workspaces.load(STARTER, w); }
  }

  // ================= the interpreter =================
  let generation = 0;          // bumps on every start/stop: old scripts notice and end
  const runningHats = new Set();
  const speeds = { B: 2, C: 2, D: 2, E: 2, F: 2 };
  let lastMuscle = 0;
  class End extends Error {}
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function value(b, name, fallback) {
    const t = b.getInputTargetBlock(name);
    return t ? evaluate(t) : fallback;
  }
  function evaluate(b) {
    const f = (k) => b.getFieldValue(k);
    switch (b.type) {
      case 'o_num': return Number(f('V')) || 0;
      case 's_muscle': return Arm.muscle();
      case 's_pos': return Arm.position(f('M'));
      case 's_held': return Arm.held(Number(f('N')), f('ACTION'));
      case 'o_compare': { const a = value(b, 'A', 0), c = value(b, 'B', 0), o = f('OP');
        return o === 'lt' ? a < c : o === 'gt' ? a > c : Math.abs(a - c) < 1e-9; }
      case 'o_logic': return f('OP') === 'and' ? !!value(b, 'A', false) && !!value(b, 'B', false) : !!value(b, 'A', false) || !!value(b, 'B', false);
      case 'o_not': return !value(b, 'A', false);
      case 'o_math': { const a = value(b, 'A', 0), c = value(b, 'B', 0), o = f('OP');
        return o === 'add' ? a + c : o === 'sub' ? a - c : o === 'mul' ? a * c : (c ? a / c : 0); }
      case 'o_random': { const a = Math.ceil(value(b, 'A', 1)), c = Math.floor(value(b, 'B', 10));
        return Math.floor(Math.random() * (Math.abs(c - a) + 1)) + Math.min(a, c); }
    }
    return 0;
  }
  async function runStack(block, gen) {
    for (let b = block; b; b = b.getNextBlock()) {
      if (gen !== generation) throw new End();
      const show = ws && b.workspace === ws;
      if (show) ws.highlightBlock(b.id);
      await step(b, gen);
      await sleep(0);
    }
  }
  async function step(b, gen) {
    const f = (k) => b.getFieldValue(k);
    switch (b.type) {
      case 'c_wait': await waitFor(value(b, 'S', 1) * 1000, gen); break;
      case 'c_repeat': { const times = Math.max(0, Math.floor(value(b, 'N', 0)));
        for (let i = 0; i < times; i++) { await runStack(b.getInputTargetBlock('DO'), gen); await sleep(10); } break; }
      case 'c_forever': for (;;) { await runStack(b.getInputTargetBlock('DO'), gen); await sleep(20); }
      case 'c_if': if (value(b, 'IF', false)) await runStack(b.getInputTargetBlock('DO'), gen); break;
      case 'c_ifelse': await runStack(b.getInputTargetBlock(value(b, 'IF', false) ? 'DO' : 'ELSE'), gen); break;
      case 'c_until': while (!value(b, 'IF', false)) { if (gen !== generation) throw new End(); await sleep(20); } break;
      case 'c_end': Program.stop(); throw new End();
      case 'm_go': Arm.goTo(f('M'), value(b, 'A', 0), Number(f('DIR')), speeds[f('M')]); await sleep(60); break;
      case 'm_turn': { const d = Math.abs(value(b, 'D', 0)) * Number(f('DIR')), lv = speeds[f('M')];
        Arm.turn(f('M'), d, lv); await waitFor(Math.abs(d) / DEG_PER_S[lv] * 1000 + 150, gen); break; }
      case 'm_stop': Arm.stop(f('M')); break;
      case 'm_start': Arm.run(f('M'), f('DIR') === '1', speeds[f('M')]); break;
      case 'm_for': Arm.run(f('M'), f('DIR') === '1', speeds[f('M')]); await waitFor(value(b, 'S', 1) * 1000, gen); Arm.stop(f('M')); break;
      case 'm_speed': speeds[f('M')] = Number(f('SP')); break;
      case 'm_home': Arm.home(); break;
      case 'm_stopall': Arm.stopAll(); break;
    }
  }
  async function waitFor(ms, gen) {
    const end = performance.now() + ms;
    while (performance.now() < end) { if (gen !== generation) throw new End(); await sleep(Math.min(50, end - performance.now())); }
  }
  function fire(test) {            // start every event script whose hat matches
    if (!Program.running) return;
    for (const hatBlock of workspace().getTopBlocks(true)) {
      if (!test(hatBlock) || runningHats.has(hatBlock.id)) continue;
      const gen = generation;
      runningHats.add(hatBlock.id);
      runStack(hatBlock.getNextBlock(), gen).catch((e) => { if (!(e instanceof End)) console.error(e); })
        .finally(() => { runningHats.delete(hatBlock.id); if (ws) ws.highlightBlock(null); });
    }
  }

  const Program = window.Program = {
    running: false,
    show(div) {
      if (!ws) {
        ws = Blockly.inject(div, { toolbox: TOOLBOX, theme, renderer: 'zelos', media: 'media/', sounds: false, trashcan: true,
          zoom: { controls: true, wheel: false, startScale: 0.85 }, move: { scrollbars: true, drag: true, wheel: false } });
        load(ws);
        if (hidden) { hidden.dispose(); hidden = null; }
        ws.addChangeListener((e) => { if (!e.isUiEvent) Program.save(); });
      }
      Blockly.svgResize(ws);
    },
    save() { if (ws) { try { localStorage.setItem(KEY, JSON.stringify(Blockly.serialization.workspaces.save(ws))); } catch (_) {} } },
    start() {
      Program.stop(true);
      Program.running = true; generation++;
      fire((b) => b.type === 'ev_start');
      Arm.changed();
    },
    stop(quiet) {
      const was = Program.running;
      Program.running = false; generation++;
      runningHats.clear();
      if (ws) ws.highlightBlock(null);
      if (was || !quiet) Arm.stopAll();
      Arm.changed();
    },
    control(num, before, after) {      // a remote control changed (Advanced mode)
      const pressed = Object.keys(after).filter((k) => !before[k]);
      const letGo = Object.keys(before).length && !Object.keys(after).length;
      fire((b) => b.type === 'ev_control' && Number(b.getFieldValue('N')) === num &&
        (pressed.includes(b.getFieldValue('ACTION')) || (letGo && b.getFieldValue('ACTION') === 'released')));
    },
    muscle(v) {                        // a new muscle reading
      const old = lastMuscle; lastMuscle = v;
      fire((b) => b.type === 'ev_muscle' && (() => { const t = value(b, 'PCT', 50); return old <= t && v > t; })());
    }
  };
})();
