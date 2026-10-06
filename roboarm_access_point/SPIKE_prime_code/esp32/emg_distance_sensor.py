# LMS-ESP32 + muscle (EMG) sensor that pretends to be a LEGO SPIKE Distance Sensor.
#
# Plug the board into a SPIKE Prime hub with the normal LEGO firmware. The hub
# sees a genuine Distance Sensor. The muscle strength is reported as distance:
#
#     relaxed = 5 cm        full squeeze = 100 cm
#
# so "distance in cm" on the hub is the muscle strength from about 5 to 100.
# (Never 0: the hub shows a 0 reading as 200 cm, "no object".)
#
# Needs on the board: lpf2.py (Anton's PUPRemote library, version 2.1 or newer).
# This is one self-contained file. Save it on the board as main.py to run at power-up.

import machine
import utime
import lpf2

# Startup description of a real LEGO SPIKE Prime Distance Sensor (LUMP type 62).
#
# Recorded from a genuine sensor at 2400 baud with code/capture-distance-sensor.py,
# then split into messages (each ends with its checksum byte). The ESP32 sends these
# bytes in this order so the hub believes a real Distance Sensor is plugged in.
# Do not edit by hand: any changed byte can make the hub reject the sensor.
#
# Order: TYPE (62), MODES (9), SPEED (115200), VERSION, then the info for
# modes 8..0 (CALIB, ADRAW, PING, LIGHT, TRAW, LISTN, SINGL, DISTS, DISTL), then ACK.

try:
    from ubinascii import unhexlify
except ImportError:
    from binascii import unhexlify

_HEX = (
    "403e81",
    "5107060800a7",
    "5200c201006e",
    "5f0000001000000010a0",
    "a02043414c49420040400000048400000000ba",
    "98210000000000007f437a",
    "9822000000000000c842cf",
    "98230000000000007f4378",
    "9024504354000c",
    "8825000052",
    "90a007000300cb",
    "a70041445241570040000000048400000000d9",
    "9f010000000000008044a5",
    "9f02000000000000c842e8",
    "9f030000000000008044a7",
    "9704504354002b",
    "8f059000e5",
    "978001010400ec",
    "a60050494e4700004080000004840000000009",
    "9e01000000000000803fdf",
    "9e02000000000000c842e9",
    "9e03000000000000803fdd",
    "9604504354002a",
    "8e050090e4",
    "968001000100e9",
    "a5004c494748540040200000048400000000e4",
    "9d01000000000000c842e9",
    "9d02000000000000c842ea",
    "9d03000000000000c842eb",
    "95045043540029",
    "8d05001067",
    "958004000300ed",
    "a400545241570000400000000484000000008b",
    "9c010000000000c4634683",
    "9c02000000000000c842eb",
    "9c030000000000c4634681",
    "8c04755351",
    "8c059000e6",
    "948001020500ed",
    "a3004c4953544e0040000000048400000000d0",
    "9b01000000000000803fda",
    "9b02000000000000c842ec",
    "9b03000000000000803fd8",
    "8b04535477",
    "8b05100061",
    "938001000100ec",
    "a20053494e474c0040000000048400000000c2",
    "9a010000000000401c457d",
    "9a02000000000000c842ed",
    "9a030000000000007a435f",
    "8a04434d7f",
    "8a059000e0",
    "928001010501e9",
    "a10044495354530040000000048400000000c7",
    "9901000000000000a04384",
    "9902000000000000c842ee",
    "9903000000000000004227",
    "8904434d7c",
    "8905f10082",
    "918001010401eb",
    "a000444953544c0040000000048400000000d9",
    "98010000000000401c457f",
    "9802000000000000c842ef",
    "98030000000000007a435d",
    "8804434d7d",
    "88059100e3",
    "908001010501eb",
    "a008002400400243323138543130000000001c",
    "04",
)

DESCRIPTOR = tuple(unhexlify(h) for h in _HEX)

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------
EMG_PIN = 33            # the muscle sensor signal pin (IO33)
CALIBRATE_MS = 2500     # keep the arm relaxed for this long at power-up
SMOOTHING = 0.07        # 0..1, applied twice. Higher reacts faster, lower is smoother
MIN_SPAN = 30           # smallest signal strength that still counts as 0 to 100
PEAK_DECAY = 0.002      # how fast the "full squeeze" level relaxes
PEAK_ATTACK = 0.02      # how fast it can rise: a brief spike barely moves it
REST_WINDOW_S = 12      # "zero" follows the quietest level of the last this many seconds
MAX_RISE = 1.5            # biggest jump up per update, in percent (smaller = calmer)
MAX_FALL = 1            # biggest drop per update, in percent
BURST = 40              # ADC readings per measurement (40 x 0.5 ms = 20 ms, one 50 Hz hum cycle)
BURST_GAP_US = 500      # time between readings. Do not go below 400: the ADC gives bad values
SEND_EVERY_MS = 20      # how often a new value goes to the hub
DEBUG = False           # True prints connection details from the sensor library
SHOW_SIGNAL = False     # True prints the signal levels 4 times a second
# ---------------------------------------------------------------------------

MIN_MM = 50             # relaxed is sent as 50 mm (5 cm): the hub shows 0 and very small readings as 200 cm ("no object")
MAX_MM = 1000           # full squeeze = 1000 mm = 100 cm


class Emg:
    """Measures how strongly the muscle is working, as a number from 0 to 100."""

    def __init__(self, pin=EMG_PIN):
        self.adc = machine.ADC(machine.Pin(pin))
        try:
            self.adc.atten(machine.ADC.ATTN_11DB)
        except AttributeError:
            pass
        self.samples = [0] * BURST
        self.recent = []
        self.rms_now = 0.0
        self.env = 0.0
        self.env2 = 0.0
        self.floor = 0.0
        self.margin = 2.0
        self.rest = 0.0
        self.rest_cap = 0.0
        self.buckets = []
        self.bucket_min = 1e9
        self.bucket_start = utime.ticks_ms()
        self.peak = 0.0
        self.shown = 0.0

    def rms(self):
        """Strength of the muscle signal over one short burst of readings.

        Takes the readings, removes the average (the sensor's resting voltage)
        and returns how far the signal wiggles around it.
        """
        samples = self.samples
        total = 0
        for i in range(BURST):
            v = self.adc.read_u16() >> 4   # 12-bit counts
            samples[i] = v
            total += v
            utime.sleep_us(BURST_GAP_US)
        mean = total / BURST
        acc = 0.0
        for v in samples:
            d = v - mean
            acc += d * d
        return (acc / BURST) ** 0.5

    def calibrate(self):
        print("Relax your muscle for", CALIBRATE_MS // 1000, "seconds...")
        start = utime.ticks_ms()
        values = []
        while utime.ticks_diff(utime.ticks_ms(), start) < CALIBRATE_MS:
            values.append(self.rms())
        rest = sum(values) / len(values)
        spread = (sum((v - rest) ** 2 for v in values) / len(values)) ** 0.5
        # Anything within 3 steps of the resting noise counts as zero
        self.margin = max(3 * spread, 2)
        self.rest = rest
        self.rest_cap = rest + 2 * MIN_SPAN   # zero may never creep above this
        self.floor = rest + self.margin
        self.env = rest
        self.env2 = rest
        self.peak = self.floor + MIN_SPAN
        self.bucket_start = utime.ticks_ms()
        print("Resting level:", rest, "noise:", spread, "zero below:", self.floor)

    def measure(self):
        """One measurement: returns the strength 0..100, calm and rate-limited."""
        self.rms_now = self.rms()
        # The middle of the last five bursts ignores one-off spikes
        self.recent.append(self.rms_now)
        if len(self.recent) > 5:
            self.recent.pop(0)
        middle = sorted(self.recent)[len(self.recent) // 2]
        self.env += (middle - self.env) * SMOOTHING
        self.env2 += (self.env - self.env2) * SMOOTHING   # second stage, flatter

        # "Zero" follows the quietest 1-second stretch of the last REST_WINDOW_S seconds,
        # so a drifting baseline (motor noise, power dips) cannot leave it stuck.
        if self.env2 < self.bucket_min:
            self.bucket_min = self.env2
        if utime.ticks_diff(utime.ticks_ms(), self.bucket_start) >= 1000:
            self.buckets.append(self.bucket_min)
            if len(self.buckets) > REST_WINDOW_S:
                self.buckets.pop(0)
            self.bucket_min = 1e9
            self.bucket_start = utime.ticks_ms()
            self.rest = min(min(self.buckets), self.rest_cap)
            self.floor = self.rest + self.margin

        # "Full squeeze" rises slowly (a spike does not count) and relaxes steadily.
        if self.env2 > self.peak:
            self.peak += (self.env2 - self.peak) * PEAK_ATTACK
        else:
            self.peak -= (self.peak - (self.floor + MIN_SPAN)) * PEAK_DECAY
        if self.peak < self.floor + MIN_SPAN:
            self.peak = self.floor + MIN_SPAN

        span = self.peak - self.floor
        target = 100 * (self.env2 - self.floor) / span if span > 1 else 0
        if target < 0:
            target = 0
        elif target > 100:
            target = 100
        return target

    def step(self, target):
        """Move the shown value toward the target, but only by a small step."""
        if target > self.shown:
            self.shown = min(target, self.shown + MAX_RISE)
        else:
            self.shown = max(target, self.shown - MAX_FALL)
        return self.shown


class DistanceSensorEmulator(lpf2.LPF2):
    """LPF2 sensor that introduces itself with a real Distance Sensor's description."""

    def _send_info_sequence(self):
        # Give every mode an all-zero reading, so the hub can select any of them.
        for number, mode in enumerate(self.modes):
            self.load_payload(b"\x00" * mode[8], number)
        gap = getattr(lpf2, "MODE_GAP_MS", 20)
        for message in DESCRIPTOR:
            # A mode's NAME message starts a new block: leave a short pause first.
            if message[0] & 0xC0 == 0x80 and message[1] & ~0x20 == 0x00:
                utime.sleep_ms(gap)
            self.write(message)


def make_modes():
    """One entry per real mode. Only the data size and type matter here."""
    mode = lpf2.LPF2.mode
    return [
        mode("DISTL", 1, lpf2.DATA16),   # 0 distance, long range
        mode("DISTS", 1, lpf2.DATA16),   # 1 distance, short range
        mode("SINGL", 1, lpf2.DATA16),   # 2 single measurement
        mode("LISTN", 1, lpf2.DATA8),    # 3 listen for other sensors
        mode("TRAW", 1, lpf2.DATA32),    # 4 raw echo time
        mode("LIGHT", 4, lpf2.DATA8),    # 5 the four lights (hub writes)
        mode("PING", 1, lpf2.DATA8),     # 6 ping
        mode("ADRAW", 1, lpf2.DATA16),   # 7 raw analog value
        mode("CALIB", 7, lpf2.DATA8),    # 8 calibration
    ]


def main():
    if not hasattr(lpf2.LPF2, "_send_info_sequence"):
        raise RuntimeError("lpf2.py is too old. Copy the newest lpf2.py from the PUPRemote project onto the board.")

    emg = Emg()
    emg.calibrate()

    sensor = DistanceSensorEmulator(make_modes(), sensor_id=62, debug=DEBUG)
    last_send = utime.ticks_ms()
    last_show = last_send
    target = 0

    while True:
        target = emg.measure()

        if utime.ticks_diff(utime.ticks_ms(), last_send) >= SEND_EVERY_MS:
            last_send = utime.ticks_ms()
            percent = emg.step(target)
            mm = MIN_MM + int(percent * (MAX_MM - MIN_MM) / 100)
            sensor.update_payload(mm, 0)                  # DISTL
            sensor.update_payload(min(mm, 320), 1)        # DISTS
            sensor.update_payload(mm, 2)                  # SINGL
            sensor.update_payload(int(mm * 5.83), 4)      # TRAW, echo time in microseconds
            sensor.update_payload(mm, 7)                  # ADRAW
            if SHOW_SIGNAL and utime.ticks_diff(last_send, last_show) >= 250:
                last_show = last_send
                print("rms", int(emg.rms_now), "env", int(emg.env), "zero<", int(emg.floor),
                      "peak", int(emg.peak), "sent mm", mm)

        sensor.heartbeat()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise                      # Ctrl+C / Stop in Thonny still works
    except Exception as error:
        # Running on its own: show what happened, wait a moment, and start again.
        print("Error:", error)
        utime.sleep_ms(3000)
        machine.reset()
