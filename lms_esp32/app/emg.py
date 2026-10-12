# Muscle (EMG) sensor on IO32: how hard the muscle is working, 0 to 100.
#
# Same signal processing that was tuned on the real arm:
# RMS over one 50 Hz hum cycle -> spike filter -> two smoothing stages ->
# "zero" follows the quietest recent second -> "full squeeze" follows sustained effort -> rate limit.

import machine
import utime
from array import array

PIN = 32               # the muscle sensor signal
CALIBRATE_MS = 2500    # keep the arm relaxed for this long at power-up
SMOOTHING = 0.07       # 0..1, applied twice. Higher reacts faster, lower is smoother
MIN_SPAN = 30          # smallest signal strength that still counts as 0 to 100
PEAK_DECAY = 0.002     # how fast the "full squeeze" level relaxes
PEAK_ATTACK = 0.02     # how fast it can rise: a brief spike barely moves it
REST_WINDOW_S = 12     # "zero" follows the quietest level of the last this many seconds
MAX_RISE = 1.5         # biggest jump up per update, in percent (smaller = calmer)
MAX_FALL = 1           # biggest drop per update, in percent
BURST = 40             # readings per measurement (40 x 0.5 ms = 20 ms, one 50 Hz hum cycle)
GAP_US = 500           # time between readings. Do not go below 400: the ADC gives bad values


class Emg:
    def __init__(self, pin=PIN):
        self.adc = machine.ADC(machine.Pin(pin))
        try:
            self.adc.atten(machine.ADC.ATTN_11DB)
        except AttributeError:
            pass
        self.samples = array("H", bytes(2 * BURST))
        self.recent = []
        self.env = self.env2 = self.floor = self.rest = self.rest_cap = self.peak = 0.0
        self.margin = 2.0
        self.shown = 0.0
        self.buckets = []
        self.bucket_min = 1e9
        self.bucket_start = utime.ticks_ms()

    def rms(self):
        """How far the signal wiggles around its resting voltage over one burst."""
        s = self.samples
        total = 0
        for i in range(BURST):
            v = self.adc.read_u16() >> 4       # 12-bit counts
            s[i] = v
            total += v
            utime.sleep_us(GAP_US)
        mean = total / BURST
        acc = 0.0
        for v in s:
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
        self.margin = max(3 * spread, 2)        # within 3 steps of resting noise counts as zero
        self.rest = self.env = self.env2 = rest
        self.rest_cap = rest + 2 * MIN_SPAN      # zero may never creep above this
        self.floor = rest + self.margin
        self.peak = self.floor + MIN_SPAN
        self.bucket_start = utime.ticks_ms()
        print("Resting level:", rest, "noise:", spread)

    def measure(self):
        """One measurement (about 20 ms). Returns the target strength 0..100."""
        r = self.recent
        r.append(self.rms())
        if len(r) > 5:
            r.pop(0)
        middle = sorted(r)[len(r) // 2]          # the middle of five ignores one-off spikes
        self.env += (middle - self.env) * SMOOTHING
        self.env2 += (self.env - self.env2) * SMOOTHING

        if self.env2 < self.bucket_min:
            self.bucket_min = self.env2
        if utime.ticks_diff(utime.ticks_ms(), self.bucket_start) >= 1000:
            b = self.buckets
            b.append(self.bucket_min)
            if len(b) > REST_WINDOW_S:
                b.pop(0)
            self.bucket_min = 1e9
            self.bucket_start = utime.ticks_ms()
            self.rest = min(min(b), self.rest_cap)
            self.floor = self.rest + self.margin

        if self.env2 > self.peak:
            self.peak += (self.env2 - self.peak) * PEAK_ATTACK
        else:
            self.peak -= (self.peak - (self.floor + MIN_SPAN)) * PEAK_DECAY
        if self.peak < self.floor + MIN_SPAN:
            self.peak = self.floor + MIN_SPAN

        span = self.peak - self.floor
        t = 100 * (self.env2 - self.floor) / span if span > 1 else 0
        return 0 if t < 0 else (100 if t > 100 else t)

    def step(self, target):
        """Move the output toward the target by a small step (calm, steady movement)."""
        if target > self.shown:
            self.shown = min(target, self.shown + MAX_RISE)
        else:
            self.shown = max(target, self.shown - MAX_FALL)
        return self.shown
