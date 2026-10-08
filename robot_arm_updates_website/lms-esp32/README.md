# LMS-ESP32 EMG rig models

3D models of a LEGO **SPIKE Prime hub** cabled to Anton's Mindstorms **LMS-ESP32 v2.0** in
GTAC-Science's printed case, which is wired to
DFRobot's **SEN0240 Gravity EMG sensor**, with snap electrodes in its 3.5 mm jack. `viewer.html`
shows them together, with an Explode slider like the growbox build book.

```bash
./build.sh            # regenerate everything in out/
./serve.sh            # then open http://localhost:8765/viewer.html
```

Needs KiCad 10 in `/Applications/KiCad` and the growcube PCB repo next to this one
(`../../PCB/models/gen_models.py` supplies the STEP writer).

| File | What |
|---|---|
| `gen_pcb.py` | The LMS-ESP32, Gravity EMG and MyoWare boards as KiCad files (no nets). Parts sit where they are on the real boards, and the silkscreen carries the labels as printed. **Edit this.** |
| `gen_models.py` | STEP models KiCad's library lacks: ESP32-PICO-MINI-02, RST side switch, 2R2 inductor, 2020 RGB LED, the EMG board's jack |
| `ldraw.py` | LDraw part -> glTF. Makes `out/spike-hub.glb` from 45601; the part and its subparts are cached in `ldraw/` (set `LDRAWDIR` to an unzipped LDraw library to fetch others) |
| `spike_box.py` | The SPIKE Prime (45678) storage box (yellow tub, white lid), 41.3 × 30.3 × 15.5 cm, as `out/spike-box-tub.glb` and `out/spike-box-lid.glb` |
| `glb.py` | The small glTF writer `ldraw.py` and `spike_box.py` share |
| `case.py` | Splits `case/LMS_ESP32_case_GTAC.stl` into base, lid and button cap, each placed around the board |
| `viewer.html` | The assembly. Wiring, the Gravity cable and the electrode leads are drawn in the page |
| `out/` | `lms-esp32.glb`, `emg.glb`, `myoware.glb`, `spike-hub.glb`, `spike-box-*.glb`, `case-*.stl` |

## Wiring shown

| Gravity pin | Wire | LMS-ESP32 header |
|---|---|---|
| A (signal) | blue | IO32, inner row, 5th from the USB end |
| + | red | 3V3, outer row, 7th |
| − | black | GND, inner row, 7th |

SPIKE cable: the LMS-ESP32's 2 × 3 HUB header (IO8/IO7 serial, 3V3, GND, M+/M−) to hub port A,
through the lid's cutout over the header.

## Step players on the instruction pages

The instruction cards embed `wiring-steps.html` and `hub-buttons.html?for=arm|myo`. These show pre-rendered
frames (`frames/wiring/`, `frames/hub/`: 19 angles across ±45° per step, plus the moves between steps)
through `frames-player.js`, rather than a live 3D model, so they stay light on iPads and slow networks.
Students drag sideways (or use the arrow keys) to turn the model.

The frames are drawn from the live 3D versions, `wiring-steps-3d.html` and `hub-buttons-3d.html`. After
changing a model or a step there, render again (needs Chrome or Edge, and the internet for three.js):

    python make_embeds.py      # only if a model in out/ changed: repackages it for the 3D pages
    python render_frames.py    # -> frames/wiring/ and frames/hub/

If you change a step's text or tags, change them in both the 3D page and its player page.

## Sources and guesses

- LMS-ESP32 header, HUB, RGB/IO25, RST, PWR, DISPLAY and Grove labels: read off Anton's photos.
  The display socket's per-pin numbers are too small to read in the photos; they come from
  Anton's pinout table. The small passives are placed approximately.
- Case: thingiverse.com/thing:7032044 by GTAC-Science, CC BY-SA (see `case/`).
- EMG board: DFRobot's product photos and their board drawing (socket pins −, +, A top to bottom).
- SPIKE hub: LDraw 45601 by Philippe Hurbain (CC BY 4.0). It has no prints, so the port letters,
  arrows and 5 × 5 matrix are a decal drawn in the viewer. LPF2 plug sized from published
  measurements (13.9 × 7.5 × 13.7 mm, 5.85 mm plugged depth); its shape is simplified.
- Snap electrodes: Plastics One drawing 2052-50 (Snap 222).
