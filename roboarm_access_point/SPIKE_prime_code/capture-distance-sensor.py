# One-off tool: record what a real SPIKE Distance Sensor says when it powers up.
#
# Needs a hub running Pybricks (not the sensor emulation firmware).
# 1. Plug the real SPIKE Distance Sensor into PORT A. Nothing else needs to be connected.
# 2. Run this program from Pybricks Code (Python file).
# 3. Copy everything it prints in the terminal and send it back.
#
# A LEGO sensor starts at 2400 baud and sends its type, modes and every mode's
# details in one burst, then repeats until the hub answers. We listen and never answer.

from pybricks.iodevices import UARTDevice
from pybricks.parameters import Port
from pybricks.tools import wait, StopWatch

PORT = Port.A
BAUDRATE = 2400
LISTEN_MS = 6000

uart = UARTDevice(PORT, BAUDRATE, timeout=100)
clock = StopWatch()
data = b""

print("Listening for", LISTEN_MS // 1000, "seconds...")
while clock.time() < LISTEN_MS:
    chunk = uart.read_all()
    if chunk:
        data += chunk
    wait(20)

print("BYTES:", len(data))
print("BEGIN-HEX")
line = ""
for i, b in enumerate(data):
    line += "%02x" % b
    if (i + 1) % 32 == 0:
        print(line)
        line = ""
        wait(10)
if line:
    print(line)
print("END-HEX")
