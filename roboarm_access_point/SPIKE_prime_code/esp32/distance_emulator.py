# Makes an LMS-ESP32 pretend to be a genuine LEGO SPIKE Distance Sensor.
#
# Shared by the programs on the board that talk to the hub as a sensor.
# Needs lpf2.py (copy it next to this file).

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
