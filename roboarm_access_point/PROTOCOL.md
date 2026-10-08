# Board ⇄ hub protocol

The LMS-ESP32 pretends to be a LEGO SPIKE Distance Sensor on hub port A. Both directions use
normal SPIKE App 3 calls, so the hub keeps the official LEGO firmware.

## Board → hub: the "distance" reading

The hub reads it with `distance_sensor.distance(port.A)` (millimetres). It acts on a reading only
after seeing the same value twice in a row, so a glitch can never start a motor, and a command counts once,
when the reading changes to it. The board never sends the same command twice in a row: it puts a different
reading (another motor's state, or the muscle reading) in between.

| Reading (mm) | Meaning |
|---|---|
| 50 – 1000 | Muscle sensor: `mm = 50 + 9.5 × percent` (percent already amplified by the page's gain) |
| 1100 – 1999 | A command: `code = (mm − 1100) / 5` (the hub accepts ±2 mm) |

| Code | Command |
|---|---|
| 0 – 34 | Run state: `code = motor × 7 + state` (motor 0–4 = B–F; state 0 stop, 1–3 forward slow/medium/fast, 4–6 back slow/medium/fast) |
| 35 | Stop all motors (sent on every change of mode) |
| 36 | Home: every motor to its baseline |
| 37 | Re-read baselines now (sent when the page switches between Muscle sensor and Remote) |
| 38 – 42 | Muscle sensor drives motor B – F |
| 43 – 87 | Go-to header: `43 + motor × 9 + direction × 3 + speed` (direction 0 shortest path, 1 clockwise, 2 counter-clockwise; speed 0–2 slow/medium/fast) |
| 88 – 159 | Go-to angle that follows a header: `angle = (code − 88) × 5` degrees (0 – 355) |
| 160 – 174 | Turn header: `160 + motor × 3 + speed`, followed by two values in 88 – 159: |
| | first `88 + 36 × back + full turns` (back 0/1, full turns 0 – 35), then `88 + rest`; degrees = (full turns × 72 + rest) × 5 |

Run-state codes and go-to commands put the hub in remote mode; muscle readings put it in muscle mode.
Codes 35 – 42 work in either mode. In remote mode the board repeats every motor's run state in turn
(every 30 ms) so a lost reading is repaired; a changed motor is sent as soon as the previous reading
has been held 15 ms.

## Hub → board: the Distance Sensor's four lights

The hub calls `distance_sensor.show(port.A, [kind, a, b, c])`. Every value is 0 – 100.

| kind | a | b | c | Meaning |
|---|---|---|---|---|
| 1 | 1 = on, 0 = off | 0 | 0 | Turn the Wi-Fi access point on or off |
| 2 | motor 0 – 4 | position ÷ 100 | position % 100 | Current motor position (0 – 359°) |
| 3 | motor 0 – 4 | baseline ÷ 100 | baseline % 100 | Baseline (home) position (0 – 359°) |
| 4 | hub mode (0 muscle, 1 remote) | muscle motor 0 – 4 | motors fitted (bit mask, 0 – 31) | Hub status |

The board starts as a plain distance sensor (muscle readings) with Wi-Fi off. It turns the access point
on only when the hub sends kind 1 with a = 1.

## Page ⇄ board (WebSocket `/ws`, or `GET /s?...` as a fallback)

Page → board, one text message of `key=value` pairs joined by `&`:

| Keys | Meaning |
|---|---|
| `m=ddddd` | Run state digit (0 – 6) for motors B – F |
| `x=1` / `x=0` | Remote tab / Muscle sensor tab |
| `g=10` | Muscle gain × 10 (amplifier bar, 1 – 50) |
| `p=B` | Motor the muscle sensor drives |
| `c=stop` · `c=home` · `c=base` | Stop all · go home · re-read baselines |
| `c=go&k=E&a=90&d=0&v=1` | Motor E to 90°, direction 0 – 2, speed 0 – 2 |
| `c=turn&k=E&g=-450&v=1` | Turn motor E by −450° (back), speed 0 – 2 |

Board → page, one or more lines:

| Line | Meaning |
|---|---|
| `m 37` | Muscle signal after gain (percent) |
| `p E 123` | Motor E is at 123° |
| `b E 90` | Motor E's baseline is 90° |
| `h 1 B 27` | Hub status: mode (0 muscle, 1 remote), muscle motor, motors fitted (bit mask) |
