# Robotic arm code for LEGO SPIKE Prime

Two ways to run the muscle-sensor arm. Both use the same settings and behaviour.

## A. Official SPIKE App 3 (preferred, no hub changes)

The LMS-ESP32 board pretends to be a **LEGO Distance Sensor**. Distance in cm = muscle strength (about 5 to 100). The board never sends 0 or tiny values, because the hub shows them as 200 cm ("no object").

| File | Runs on | What it does |
|---|---|---|
| `esp32/emg_distance_sensor.py` | LMS-ESP32 (save as `main.py`) | One file. Reads the EMG on IO33 and acts as a Distance Sensor, using the startup description recorded from a genuine sensor |
| `myosensor-spike-app3.py` | SPIKE Prime hub, SPIKE App 3 (Python) | Moves the motors from the "distance" value |

The board also needs `esp32/lpf2.py` (copied from the PUPRemote project, GPL, version 2.1). Older boards have an older copy: replace it.

Ordering for first test:
1. Save `esp32/emg_distance_sensor.py` on the board (as `main.py`). Power it from the hub, keeping your arm relaxed for 2.5 s.
2. In the SPIKE App, connect the hub. The Port A device should show as a Distance Sensor.
3. Squeeze: the distance in cm should rise from 0 to about 100.
4. Run `myosensor-spike-app3.py`.

If the hub does not recognise the sensor, set `DEBUG = True` in `emg_distance_sensor.py` and read the board's output.
To check what the board sends, run `capture-distance-sensor.py` on a Pybricks hub with the board in Port A. The output should match the real sensor's capture.

## B. Pybricks (fallback, hubs need Pybricks firmware)

`myosensor-spike-prime.py` reads the board's original UartRemote `muscle_data` messages (19200 baud).
It needs the original board program, not the Distance Sensor one. Use code.pybricks.com (Chrome/Edge or Bluefy on iPad).

## C. Customisable web remote for the arm (replaces the Mindstorms virtual remote)

The LMS-ESP32 makes its own Wi-Fi network (`GTAC 6`, password `gtacrobot`; set `ADD_BOARD_CODE = True` in
`remote_web.py` to give each board its own name). The remote is at `http://1.1.1.1`. Joining the Wi-Fi pops up a
landing page with an "Open the remote" button: the board answers every web address and DNS name itself, like a hotel
sign-in page, and once a device has opened the remote it tells that device the network is fine so it stays connected.
The Remote / Muscle sensor buttons at the top of the page choose what moves the arm; in Muscle sensor mode the page
shows a rolling 30-second graph of the muscle signal (0-100 %). The page keeps a live WebSocket link to the board
(`/ws`): presses arrive at once and the board streams about 50 muscle readings a second. If the live link cannot
connect, the page falls back to ordinary requests. The pencil button lets them build their own remote: add a D-pad, slider,
joystick or button, then choose which motor (B to F) each control moves, its speed, and whether it is reversed.
The layout is remembered on the iPad. The slider and joystick change speed with how far they are pushed.

How it works: the board sends one motor's command at a time (motors B..F in turn every 30 ms; a changed motor goes out
as soon as the previous message has been held 15 ms, so the hub can read it twice) as a distance reading: `mm = 1100 + 20 x (motor x 7 + state)`, state 0 stop, 1-3 forward
(slow, medium, fast), 4-6 back. The hub acts on a reading it sees twice, so a glitch cannot start a motor.
Remote readings are always above 110 cm, so the hub can tell them from muscle readings (5 to 100 cm).

Safety: if the page stops talking for 1 s the board releases every control, and if the hub loses the board for
0.6 s it stops the remote's motors.

## D. One board, one hub program: muscle sensor AND web remote (recommended)

| File | Runs on | What it does |
|---|---|---|
| `esp32/arm_board.py` | LMS-ESP32 (save as `main.py`) | Muscle sensor when nobody has the remote page open, remote commands when someone does |
| `esp32/emg_distance_sensor.py`, `esp32/remote_web.py`, `esp32/distance_emulator.py`, `esp32/lpf2.py` | LMS-ESP32 | Needed by `arm_board.py`: copy all of them to the board |
| `arm-spike-app3.py` | SPIKE Prime hub, SPIKE App 3 (Python) | Follows the board: muscle mode (left/right buttons pick the motor) or remote mode (ports B to F) |

"Someone is connected" means the remote page is open on a device and set to Remote (it sends a heartbeat twice a second). Joining the
Wi-Fi alone does not switch it, and the board returns to the muscle sensor about 3 s after the page is closed.
If no muscle sensor is plugged in, set `EMG_ENABLED = False` in `arm_board.py`, so the muscle reading stays relaxed.

Tested without hardware: board and hub logic in timing simulations (mode switching both ways, start about 30 ms,
stop about 10 ms, glitchy readings, lost board, silent page), the web server, and the page's touch handling and layout
editing in a browser.

## One-off tools

`capture-distance-sensor.py` records a real Distance Sensor's startup bytes on a Pybricks hub (Python file).

## Not tested on hardware

The emulator was tested against a simulated hub: the info bytes match the recording exactly, and
keepalive, mode switching and data messages decode correctly. Whether the real SPIKE App 3 accepts
the board, and the EMG scaling on a real arm, still need a hardware test.
