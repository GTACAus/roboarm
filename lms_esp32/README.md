# legodisco

Firmware for the GTAC robot arm's LMS-ESP32 board (ESP32-WROVER) that also
shares the internet. The iPad joins the board's own Wi-Fi, **GTAC n**, and
can both browse the web and drive the arm. Students no longer switch between
the arm's Wi-Fi and the site's Wi-Fi.

No Wi-Fi names or passwords are in this repo or the firmware: they are
entered when the boards are flashed (see [Flashing a classroom set](#flashing-a-classroom-set))
and live only in each board's `config.py`.

The arm itself works exactly as in
[roboarm](https://github.com/GTACAus/roboarm/tree/main/roboarm_access_point):
same hub protocol, muscle sensor and page. This repo adds the internet sharing
and a tool to flash a classroom set of boards.

> **Status:** builds, but not yet run on a board. See
> [First test on a real board](#first-test-on-a-real-board).

## For students

| | |
|---|---|
| Wi-Fi | **GTAC n** (the number on the board), with the hotspot password set when flashing |
| Arm page | **http://gtac.local** or **http://10.10.10.10** (or the "Robot arm" app) |
| Internet | works as normal while on GTAC n |

Every board answers to `gtac.local` on its own Wi-Fi, so the address is the
same for every arm. If the hotspot password differs from the one on the
printed QR codes, reprint them.

## How it behaves

- **Hotspot always on.** It comes up at power-up; the hub's Wi-Fi on/off
  message is ignored, so a SPIKE program ending can't cut the iPad's internet.
- **Internet from the site's Wi-Fi (the "uplink").** The board joins the
  strongest access point of the uplink network and shares it with NAT, in C (module `repeater`), so forwarding never
  waits on the Python loop. The forwarding runs on CPU core 0 and the arm's
  Python on core 1.
- **While the arm page is open, the uplink is left alone.** No scans or
  reconnects, because a scan pauses the hotspot for about 1.5 s, which could
  trip the stop-all-motors safety rule. If the uplink drops during arm
  control, the board reconnects once the page is closed.
- **While the arm page is closed,** the Python loop checks the web server
  every 20 ms instead of continuously. The hub link and muscle sensor keep
  running, since the hub needs its "distance sensor" at all times.
- **If the uplink is down** (or none was set), the iPad is given the board as
  its DNS server and gets the old captive pop-up, so the arm still works
  offline. Leases last 2 minutes, so an iPad switches between captive and
  internet within about a minute of the uplink coming or going.
- **Only the hotspot can reach the arm.** The web server listens on
  10.10.10.10 only, so other devices on the uplink network can't drive it.

## Flashing a classroom set

One-time setup on the computer:

```bash
pip install esptool mpremote
```

Then, with Thonny closed:

```bash
python tools/provision.py
```

The first time, it asks for the Wi-Fi settings:

| Setting | Example |
|---|---|
| Hotspot name, before the number | `GTAC` (boards become GTAC 1, GTAC 2, ...) |
| Hotspot password | what students type, or what's on the QR codes |
| Network to share internet from | the site's Wi-Fi name (empty for none) |
| Its password | hidden as you type |

and offers to keep them in `tools/site.json` (ignored by git) so later
sessions don't ask again. Use `--ask` to change them.

Then, for each board, it asks you to plug it in, and:

1. reads its MAC address and picks its number: the next free one, or the
   same as last time if this board has been flashed before;
2. wipes it and flashes `firmware/dist/legodisco.bin`;
3. writes `config.py` (its name and the Wi-Fi settings) and `main.py`;
4. watches it boot and checks its hotspot comes up;
5. tells you the name to put on the label, and asks for the next board.

Numbers are remembered in `tools/boards.csv`. Each board takes about 30 s,
because the whole app, page files included, is in the one firmware image.

```bash
python tools/provision.py --start 12      # new boards from GTAC 12
python tools/provision.py --number 7      # one board as GTAC 7 (a replacement)
python tools/provision.py --ask           # enter different Wi-Fi settings
```

To move boards to another site's Wi-Fi, re-run with `--ask` and the new
settings; each board keeps its number.

### On Windows (PowerShell)

Provisioning only needs Python and the committed `firmware/dist/legodisco.bin`,
not the build toolchain.

1. Install Python 3 from python.org and tick **Add python.exe to PATH**.
2. Install the tools and run the script (`py` is Windows' Python launcher;
   `python` also works if it's on the PATH):

   ```powershell
   py -m pip install esptool mpremote
   py tools\provision.py
   ```

3. If a plugged-in board doesn't appear as a **COM** port in Device Manager,
   install the driver for its USB chip (WCH CH340/CH9102 or Silicon Labs
   CP210x; Device Manager shows which).
4. Close Thonny first: it holds the COM port.

Building the firmware (`firmware/build.sh`) needs macOS or Linux (or WSL on
Windows); provisioning doesn't.

### Getting IT to allow the boards online

The uplink network may only let known devices onto the internet. As the
boards are flashed, provisioning writes **`tools/authorization-request.txt`**:
a ready-to-send list of the boards and their MAC addresses to give IT. Because
each board NATs its iPad, only these board addresses ever appear on the uplink
network, so that one list is all IT needs. Fill in the name/contact lines at
the top before sending.

Rebuild it at any time without flashing:

```bash
python tools/provision.py --authorization
```

## Building the firmware

```bash
firmware/build.sh
```

The first run downloads MicroPython v1.29.0 and ESP-IDF v5.5.2 and installs
the Xtensa toolchain (about 3 GB in all, into `~/esp/legodisco-deps` and
`~/.espressif`; override the former with `LEGODISCO_DEPS`). Output:
`firmware/dist/legodisco.bin`.

To update the arm page, copy the built `firmware/www` folder from roboarm
into `app/www` and rebuild. The page files are packed into the firmware by
`tools/make_www.py`.

| Path | What |
|---|---|
| `app/arm.py` | the arm program (roboarm's `main.py`; Wi-Fi always on, uplink hold, status lines) |
| `app/config.py` | not in the repo: written to each board by `tools/provision.py` |
| `app/web.py` | hotspot, uplink, web server, WebSocket; serves page files from flash |
| `app/lump.py`, `app/emg.py` | unchanged from roboarm |
| `app/simhub.py` | fake hub + muscle sensor for the test board (see below) |
| `app/main.py` | two lines on the board's filesystem that start `arm` |
| `firmware/modules/repeater/` | C module: uplink, NAT, DNS hand-out, `gtac.local` responder |
| `firmware/board/LEGODISCO/` | MicroPython board definition and speed settings |
| `firmware/board/XIAO_S3_TEST/` | same app on a XIAO ESP32S3, hub + sensor simulated |
| `tools/provision.py` | flash and name a set of boards |

## Testing the site on a spare XIAO ESP32S3

You can try the whole site — hotspot, web pages, `gtac.local`, internet
sharing — on a XIAO ESP32S3 with no arm attached. A build of the same app for
that chip is committed at `firmware/dist/legodisco-xiao-test.bin`; it sets
`SIMULATE = True`, which swaps in `app/simhub.py`: a fake LEGO hub (five
motors, modelled on PROTOCOL.md) and a fake muscle sensor. Driving a motor on
the page moves its position readout, go-to and home move to an angle, and
muscle mode makes the chosen motor follow a gently wandering muscle bar.

```bash
python tools/provision.py --chip esp32s3 --simulate \
    --firmware firmware/dist/legodisco-xiao-test.bin --number 99
```

(The XIAO's firmware flashes at offset `0x0`, which `--chip esp32s3` selects.)
Then join its hotspot and open `http://gtac.local`. Leave `--uplink` empty
when asked to test the captive-portal path, or give it a network to test
internet sharing.

What this covers: the networking, the web UI and the command protocol between
page and board. What it can't cover: the real hub's UART timing, the real
muscle sensor, and the WROVER's exact Wi-Fi performance. Rebuild the test
image with `firmware/build.sh xiao-test`.

## Diagnostics page and changing the network

On the hotspot, **http://gtac.local/stats** (or `http://10.10.10.10/stats`)
shows a diagnostics page for the board: the uplink network and signal, the
board's address on it, the hotspot channel, how many clients are connected
(and their addresses), uptime and free memory. On a test board it also says
`SIMULATION`.

The same page has a form to **change the internet network**: enter a new SSID
and password and the board saves them to its `config.py` and restarts onto the
new network. This is served on the hotspot only (the web server listens on
`10.10.10.10`), so only someone already on the board's Wi-Fi can change it.

`gtac.local` resolves on iPads and Macs; on Android, which doesn't resolve
`.local`, use `http://10.10.10.10/stats`.

## Design notes: speed

**No PSRAM.** The WROVER's 8 MB PSRAM is deliberately unused:

- On the original ESP32, PSRAM needs a compiler workaround for a chip bug that
  adds instructions throughout the code (slower everywhere) and makes the
  firmware too big for IRAM, so MicroPython's PSRAM build turns off the Wi-Fi
  fast paths and compiles for size.
- MicroPython would put the whole Python heap in PSRAM, which is reached
  through the same small cache as the program. The muscle-sensor maths
  allocates a heap object for every float, so the arm loop and garbage
  collection slow down.
- What PSRAM buys is memory headroom, and dropping Bluetooth plus freezing
  the app into flash should leave enough internal RAM for Python (56 KB heap
  to start), the Wi-Fi buffers and the NAT table (16 KB).

The boot log prints free memory (`Python heap free ... system RAM free ...
(lowest ...)`). If the lowest system RAM falls under about 20 KB while an
iPad is browsing, build the fallback, which uses PSRAM without the workaround
(rev 3 chips, i.e. WROVER-E, only). It also has to give up the Wi-Fi receive
fast path to fit, so it is slower on the network side:

```bash
firmware/build.sh PSRAM     # -> firmware/dist/legodisco-psram.bin
python tools/provision.py --firmware firmware/dist/legodisco-psram.bin
```

**Other speed settings** (`firmware/board/LEGODISCO/sdkconfig.board`):

- CPU at 240 MHz (MicroPython's default is 160 MHz).
- Flash in quad mode at 80 MHz, since Python runs from flash.
- Wi-Fi and lwIP forwarding paths in IRAM.
- 1 ms scheduler tick.
- Wi-Fi power saving off; 20 MHz channels (steadier than 40 MHz on a busy
  channel).
- IPv4 only.

**Smaller and faster to boot:** Bluetooth is removed, MicroPython's own mDNS
is replaced by a tiny responder that answers IPv6 lookups with "none" (which
avoids a 2–5 s stall on the iPad's first lookup), and the app is frozen into
flash.

## First test on a real board

1. `python tools/provision.py --number 99`, then open Thonny and watch the
   boot log: `Wi-Fi on: GTAC 99 ...`, the memory line, and
   `Internet via <uplink>: up, -NN dBm`.
2. iPad on GTAC 99: browse a few sites; open http://gtac.local.
3. Drive the arm while the iPad downloads something in another tab; check
   the arm responds as before.
4. Muscle mode while the iPad downloads: check the reading isn't noisier
   (Wi-Fi transmitting can add noise to the analogue input).
5. Leave a video playing for a few minutes; check the memory line in Thonny
   (`lowest` system RAM) and decide on the PSRAM fallback.
6. Turn the uplink's access point off or walk out of range: the iPad should
   get the captive pop-up within about a minute; back in range, internet
   returns.

If quad-mode flash ever refuses to boot on a board (unlikely on Espressif
modules), change `CONFIG_ESPTOOLPY_FLASHMODE_QIO` to `DIO` in
`sdkconfig.board` and rebuild.

## Credits

`lump.py`'s connect sequence follows `lpf2.py` from Anton Vanhoucke's
PUPRemote project (GPL). The `gtac.local` responder and repeater logic come
from the tinywifi XIAO repeater.
