# Makes the LMS-ESP32 look like a genuine LEGO SPIKE Distance Sensor (LUMP protocol).
#
# Board -> hub: set(mode, value) changes what the hub reads.
# Hub -> board: messages the hub writes to the sensor (its four lights, mode 5) go to on_write.
#
# The connect sequence follows lpf2.py from Anton Vanhoucke's PUPRemote project (GPL),
# which is proven with SPIKE Prime hubs; this file keeps only what this sensor needs.

import machine
import utime
import struct
from ubinascii import unhexlify

# The real Distance Sensor's start-up description, recorded from a genuine sensor
# (type 62, 9 modes: DISTL DISTS SINGL LISTN TRAW LIGHT PING ADRAW CALIB). Do not edit.
DESCRIPTOR = unhexlify(
    "403e815107060800a75200c201006e5f0000001000000010a0a02043414c49420040400000048400000000ba98210000"
    "000000007f437a9822000000000000c842cf98230000000000007f43789024504354000c882500005290a007000300cb"
    "a70041445241570040000000048400000000d99f010000000000008044a59f02000000000000c842e89f030000000000"
    "008044a79704504354002b8f059000e5978001010400eca60050494e47000040800000048400000000099e0100000000"
    "0000803fdf9e02000000000000c842e99e03000000000000803fdd9604504354002a8e050090e4968001000100e9a500"
    "4c494748540040200000048400000000e49d01000000000000c842e99d02000000000000c842ea9d03000000000000c8"
    "42eb950450435400298d05001067958004000300eda400545241570000400000000484000000008b9c010000000000c4"
    "6346839c02000000000000c842eb9c030000000000c46346818c047553518c059000e6948001020500eda3004c495354"
    "4e0040000000048400000000d09b01000000000000803fda9b02000000000000c842ec9b03000000000000803fd88b04"
    "5354778b05100061938001000100eca20053494e474c0040000000048400000000c29a010000000000401c457d9a0200"
    "0000000000c842ed9a030000000000007a435f8a04434d7f8a059000e0928001010501e9a10044495354530040000000"
    "048400000000c79901000000000000a043849902000000000000c842ee99030000000000000042278904434d7c8905f1"
    "0082918001010401eba000444953544c0040000000048400000000d998010000000000401c457f9802000000000000c8"
    "42ef98030000000000007a435d8804434d7d88059100e3908001010501eba00800240040024332313854313000000000"
    "1c04"
)

# Each mode's data: (struct format, size code). Size code n means 2**n bytes on the wire.
MODES = (("<H", 1), ("<H", 1), ("<H", 1), ("<B", 0), ("<I", 2),   # DISTL DISTS SINGL LISTN TRAW
         ("<4B", 2), ("<B", 0), ("<H", 1), ("<7B", 3))             # LIGHT PING ADRAW CALIB
ZERO = (0, 0, 0, 0, 0, (0, 0, 0, 0), 0, 0, (0,) * 7)
LIGHT = 5

NACK = 0x02
ACK = 0x04
EXT_MODE = 0x46
DCM_MS = 450           # how long to watch the hub's line before introducing ourselves
ACK_WAIT_MS = 2500     # how long to wait for the hub to accept us
LINE_DEAD_MS = 1000    # no keep-alive from the hub for this long: start again


def _length(header):
    """Total bytes in a message that starts with this header byte."""
    kind = header & 0xC0
    if kind == 0x00:
        return 1                                 # system byte (sync, ack, nack)
    size = 1 << ((header >> 3) & 7)
    return size + (3 if kind == 0x80 else 2)     # info messages have one extra byte


def _checksum(data):
    c = 0xFF
    for b in data:
        c ^= b
    return c


class Lump:
    def __init__(self, on_write=None, debug=False):
        try:
            from lms_esp32 import RX_PIN, TX_PIN
        except ImportError:
            RX_PIN, TX_PIN = 18, 19
        self.rx_n, self.tx_n = RX_PIN, TX_PIN
        self.on_write = on_write
        self.debug = debug
        self.connected = False
        self.mode = 0                            # the mode the hub is reading
        self.ext = 0                             # "extended mode" offset for the next message
        self.last_nack = 0
        self.uart = None
        self.inbox = b""
        self.payloads = [self._payload(m, ZERO[m]) for m in range(len(MODES))]
        print("Sensor pins: rx={}, tx={}".format(self.rx_n, self.tx_n))

    # ---------- building messages for the hub
    @staticmethod
    def _payload(mode, value):
        fmt, size = MODES[mode]
        data = struct.pack(fmt, *value) if isinstance(value, tuple) else struct.pack(fmt, value)
        ext = 8 if mode > 7 else 0
        msg = bytearray(3 + 1 + (1 << size) + 1)
        msg[0] = EXT_MODE
        msg[1] = ext
        msg[2] = 0xFF ^ EXT_MODE ^ ext
        msg[3] = 0xC0 | (size << 3) | (mode & 7)
        msg[4:4 + len(data)] = data
        msg[-1] = _checksum(msg[3:-1])
        return msg

    def set(self, mode, value):
        """New reading for one mode. Sent at once if the hub is reading that mode."""
        self.payloads[mode] = self._payload(mode, value)
        if self.connected and mode == self.mode:
            self.uart.write(self.payloads[mode])

    # ---------- joining the hub (same steps and timing as lpf2.py)
    def connect(self):
        self.connected = False
        rx = machine.Pin(self.rx_n, machine.Pin.IN)
        tx = machine.Pin(self.tx_n, machine.Pin.OUT, machine.Pin.PULL_DOWN)
        tx.value(1)
        utime.sleep_ms(5)
        tx.value(0)
        utime.sleep_ms(0)
        start = utime.ticks_ms()
        for _ in range(24):
            if utime.ticks_diff(utime.ticks_ms(), start) >= DCM_MS:
                break
            n = 0
            while rx.value() == 1 and n <= 20:
                utime.sleep_ms(1)
                n += 1
            low_since = utime.ticks_ms()
            while rx.value() == 0 and utime.ticks_diff(utime.ticks_ms(), low_since) < 1000:
                utime.sleep_ms(1)
        self.uart = machine.UART(2, baudrate=2400, rx=self.rx_n, tx=self.tx_n)
        remaining = DCM_MS - utime.ticks_diff(utime.ticks_ms(), start)
        if remaining > 0:
            utime.sleep_ms(remaining)

        # Introduce ourselves: the recorded description, a short gap before each mode's name
        i = 0
        while i < len(DESCRIPTOR):
            n = _length(DESCRIPTOR[i])
            if DESCRIPTOR[i] & 0xC0 == 0x80 and DESCRIPTOR[i + 1] & 0xDF == 0x00:
                utime.sleep_ms(20)
            self.uart.write(DESCRIPTOR[i:i + n])
            i += n

        deadline = utime.ticks_add(utime.ticks_ms(), ACK_WAIT_MS)
        while utime.ticks_diff(deadline, utime.ticks_ms()) > 0:
            if self.uart.any() and self.uart.read(1) == b"\x04":
                self.connected = True
                break
            utime.sleep_ms(1)
        if self.connected:
            self.uart = machine.UART(2, baudrate=115200, rx=self.rx_n, tx=self.tx_n)
            self.last_nack = utime.ticks_ms()
            self.inbox = b""
            self.mode = 0
            print("Hub connected")
        else:
            print("Hub did not answer, trying again")

    # ---------- listening to the hub; call this often
    def poll(self):
        if not self.connected:
            self.connect()
            return
        if utime.ticks_diff(utime.ticks_ms(), self.last_nack) > LINE_DEAD_MS:
            print("Hub went quiet, reconnecting")
            self.connect()
            return
        n = self.uart.any()
        if n:
            self.inbox += self.uart.read(n)
        while self.inbox:
            b = self.inbox[0]
            if b & 0xC0 == 0:                        # single system byte
                self.inbox = self.inbox[1:]
                if b == NACK:                        # keep-alive: send the current reading
                    self.last_nack = utime.ticks_ms()
                    self.uart.write(self.payloads[self.mode])
                continue
            n = _length(b)
            if len(self.inbox) < n:
                break                                # wait for the rest
            msg = self.inbox[:n]
            if _checksum(msg[:-1]) != msg[-1]:
                if self.debug:
                    print("hub: bad message", msg)
                self.inbox = self.inbox[1:]          # resync on the next byte
                continue
            self.inbox = self.inbox[n:]
            self._handle(msg)
        if len(self.inbox) > 64:
            self.inbox = b""

    def _handle(self, msg):
        h = msg[0]
        body = msg[1:-1]
        if h == 0x43:                                # select mode
            self.last_nack = utime.ticks_ms()
            self.mode = body[0]
            self.uart.write(self.payloads[self.mode])
        elif h == EXT_MODE:
            self.ext = body[0]
        elif h & 0xC0 == 0xC0 or h & 0xC7 == 0x44:  # data written by the hub
            mode = (h & 7) + self.ext
            self.ext = 0
            if self.debug:
                print("hub wrote mode", mode, list(body))
            if self.on_write:
                self.on_write(mode, body)
        elif self.debug:
            print("hub: message", list(msg))
