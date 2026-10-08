# GTAC robotic arm: LMS-ESP32 firmware. Runs at power-up.
#
# At power-up the board is a plain LEGO Distance Sensor that reports the muscle sensor (IO32).
# The Wi-Fi access point starts only when the hub program asks for it. Then the iPad page can
# switch between the muscle sensor and the remote, and run Blockly programs.
# How the board, hub and page talk: PROTOCOL.md.
#
# Files on the board: main.py, lump.py, emg.py, web.py and the www folder (made by tools/build.py).

import utime
import machine
import gc
from lump import Lump, LIGHT
from emg import Emg

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------
EMG_ENABLED = True      # False if no muscle sensor is plugged in (the reading then stays relaxed)
WIFI_AT_BOOT = False    # True starts the Wi-Fi without waiting for the hub (for testing)
DEBUG = False           # True prints every message from the hub
# ---------------------------------------------------------------------------

MOTORS = "BCDEF"
MIN_MM, MAX_MM = 50, 1000          # muscle readings: relaxed .. full squeeze
CMD_MM, CMD_STEP = 1100, 5          # commands: mm = 1100 + 5 x code
STOP_ALL, HOME, REBASE, MUSCLE_MOTOR, GO_HEAD, GO_ANGLE, TURN_HEAD = 35, 36, 37, 38, 43, 88, 160
FRAME_MS = 30                       # remote: each motor's state is repeated in turn this often
HOLD_MS = 15                        # shortest hold of a command, so the hub reads it twice
MUSCLE_MS = 20                      # muscle reading update rate
REFRESH_MS = 2000                   # the page's muscle motor choice is repeated this often


class Arm:
    def __init__(self):
        self.sensor = None
        self.web = None
        self.wifi_wanted = WIFI_AT_BOOT
        self.states = [0] * 5           # remote run state of motors B..F
        self.queue = []                 # command codes waiting to go to the hub
        self.rotate = 0
        self.remote_tab = False         # the page's tab: Remote (True) or Muscle sensor
        self.remote = False             # current mode
        self.gain = 1.0                 # amplifier bar on the page
        self.muscle_motor = None        # chosen on the page (None: the hub's buttons choose)
        self.positions = [-1] * 5
        self.baselines = [-1] * 5
        self.hub = "h 0 B 0"
        self.percent = 0
        self.last_send = utime.ticks_ms()
        self.last_refresh = self.last_send
        self.last_mm = 0                # the hub only notices a change, so never send the same command twice in a row

    # ---------- messages from the hub (its distance sensor lights)
    def hub_wrote(self, mode, data):
        if mode != LIGHT or len(data) < 4:
            return
        kind, a, b, c = data[0], data[1], data[2], data[3]
        if kind == 1:
            self.wifi_wanted = a == 1
        elif kind in (2, 3) and a < 5:
            angle = b * 100 + c
            (self.positions if kind == 2 else self.baselines)[a] = angle
            self.tell("%s %s %d" % ("p" if kind == 2 else "b", MOTORS[a], angle))
        elif kind == 4:
            self.hub = "h %d %s %d" % (a, MOTORS[b] if b < 5 else "B", c)
            self.tell(self.hub)

    def tell(self, line):
        if self.web:
            self.web.broadcast(line)

    # ---------- messages from the page
    def page(self, p):
        if "x" in p:
            remote_tab = p["x"] != "0"
            if remote_tab != self.remote_tab:
                self.remote_tab = remote_tab
                self.release()
                self.queue.append(REBASE)          # new tab: the hub reads fresh baselines
        if "g" in p:
            try:
                self.gain = max(0.1, min(5.0, int(p["g"]) / 10))
            except ValueError:
                pass
        if "p" in p and p["p"] in MOTORS:
            m = MOTORS.index(p["p"])
            if m != self.muscle_motor:
                self.muscle_motor = m
                self.queue.append(MUSCLE_MOTOR + m)
        if "m" in p and self.remote_tab and len(p["m"]) == 5:
            for i in range(5):
                s = ord(p["m"][i]) - 48
                if 0 <= s <= 6 and s != self.states[i]:
                    self.states[i] = s
                    if i not in self.queue:
                        self.queue.append(i)       # a motor index: its state goes out next
        c = p.get("c")
        if c == "stop":
            self.release()
        elif c == "home":
            self.release()
            self.queue.append(HOME)
        elif c == "base":
            self.queue.append(REBASE)
        elif c == "go" and p.get("k", "") in MOTORS:
            try:
                m = MOTORS.index(p["k"])
                angle = int(p.get("a", "0")) % 360
                d = min(2, max(0, int(p.get("d", "0"))))
                v = min(2, max(0, int(p.get("v", "1"))))
            except ValueError:
                return ""
            self.states[m] = 0
            self.queue.append(GO_HEAD + m * 9 + d * 3 + v)
            self.queue.append(GO_ANGLE + (angle + 2) // 5 % 72)
        elif c == "turn" and p.get("k", "") in MOTORS:
            try:
                m = MOTORS.index(p["k"])
                deg = int(p.get("g", "0"))
                v = min(2, max(0, int(p.get("v", "1"))))
            except ValueError:
                return ""
            steps = min(35 * 72 + 71, (abs(deg) + 2) // 5)       # 5-degree steps, up to 12,955 degrees
            if steps:
                self.states[m] = 0
                self.queue.append(TURN_HEAD + m * 3 + v)
                self.queue.append(GO_ANGLE + (36 if deg < 0 else 0) + steps // 72)   # direction and full turns
                self.queue.append(GO_ANGLE + steps % 72)                              # the rest
        lines = ["m %d" % self.percent, self.hub]
        for i in range(5):
            if self.positions[i] >= 0:
                lines.append("p %s %d" % (MOTORS[i], self.positions[i]))
            if self.baselines[i] >= 0:
                lines.append("b %s %d" % (MOTORS[i], self.baselines[i]))
        return "\n".join(lines)

    def release(self):
        """Stop every motor: the safety rule for every change of mode."""
        self.states = [0] * 5
        self.queue = [q for q in self.queue if 5 <= q < GO_HEAD]      # drop moves and turns not yet sent
        self.queue.insert(0, STOP_ALL)

    # ---------- the main loop's work
    def code_mm(self, code):
        if code < 5:                       # a motor index: send its current run state
            code = code * 7 + self.states[code]
        return CMD_MM + CMD_STEP * code

    def tick(self, emg):
        # Wi-Fi on or off, as the hub asked
        if self.wifi_wanted and not self.web:
            import web
            self.web = web.Web(self.page)
        elif not self.wifi_wanted and self.web:
            self.web.stop()
            self.web = None
            self.remote_tab = False
            gc.collect()

        remote = bool(self.web) and self.web.page_open() and self.remote_tab
        if remote != self.remote:
            self.remote = remote
            self.release()
            print("Mode:", "remote" if remote else "muscle sensor")

        if not remote and emg:
            target = emg.measure()          # about 20 ms
        now = utime.ticks_ms()
        held = utime.ticks_diff(now, self.last_send)

        if self.muscle_motor is not None and utime.ticks_diff(now, self.last_refresh) > REFRESH_MS:
            self.last_refresh = now
            if MUSCLE_MOTOR + self.muscle_motor not in self.queue:
                self.queue.append(MUSCLE_MOTOR + self.muscle_motor)

        mm = None
        wait = MUSCLE_MS
        if self.queue:
            wait = HOLD_MS
            if held >= HOLD_MS and self.code_mm(self.queue[0]) != self.last_mm:
                mm = self.code_mm(self.queue.pop(0))
            # else: the same command again; a different reading goes out in between
        if mm is not None:
            pass
        elif remote and held >= (wait if self.queue else FRAME_MS):
            mm = self.code_mm(self.rotate)
            self.rotate = (self.rotate + 1) % 5
        elif not remote and held >= wait:
            pct = emg.step(target) if emg else 0
            self.percent = int(min(100, pct * self.gain))
            mm = MIN_MM + int(self.percent * (MAX_MM - MIN_MM) / 100)
            self.tell("m %d" % self.percent)
        if mm is not None:
            self.last_send = now
            self.last_mm = mm
            s = self.sensor
            s.set(0, mm)                    # DISTL: what distance_sensor.distance() reads
            s.set(1, min(mm, 320))
            s.set(2, mm)
            s.set(4, int(mm * 5.83))
            s.set(7, mm)


def main():
    arm = Arm()
    emg = None
    if EMG_ENABLED:
        emg = Emg()
        emg.calibrate()
    arm.sensor = Lump(on_write=arm.hub_wrote, debug=DEBUG)
    while True:
        arm.sensor.poll()
        if arm.web:
            arm.web.poll()
        arm.tick(emg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise                      # Stop in Thonny still works
    except Exception as error:
        print("Error:", error)
        utime.sleep_ms(3000)
        machine.reset()
