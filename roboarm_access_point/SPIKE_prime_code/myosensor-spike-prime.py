# GTAC robotic arm: muscle sensor control for LEGO SPIKE Prime (Pybricks)
#
# Port of the Mindstorms "RoboticArmSensor" program. The muscle sensor board
# plugs into PORT A and sends "muscle_data" messages (UartRemote protocol,
# 19200 baud). This program only receives, so the UartRemote library is not needed.
#
# Left / right hub buttons choose which motor port is controlled.
# The centre button stops the program (Pybricks does this automatically).

from pybricks.hubs import PrimeHub
from pybricks.pupdevices import Motor
from pybricks.iodevices import UARTDevice
from pybricks.parameters import Port, Button
from pybricks.tools import wait, StopWatch

try:
    import ustruct as struct
except ImportError:
    import struct

# ---------------------------------------------------------------------------
# SETTINGS: change these numbers to change how your arm moves
# ---------------------------------------------------------------------------
SENSOR_PORT = Port.A        # where the muscle sensor is plugged in
BAUDRATE = 19200            # must match the sensor board

MOTOR_SPEED = 300           # how fast the motor moves (degrees per second)
MAX_ANGLE = 180             # how far the motor turns at 100% muscle (degrees)

SMOOTHING = 5               # average the last N readings (bigger = smoother, slower)
REST_BELOW = 40             # muscle value below this = relax, motor goes back to 0

SPIKE_ABOVE = 70            # a reading above this counts as a big squeeze
SPIKES_NEEDED = 3           # this many big squeezes...
SPIKE_WINDOW_MS = 2000      # ...within this many milliseconds trigger full open
SPIKE_HOLD_MS = 500         # how long to hold fully open
# ---------------------------------------------------------------------------

MOTOR_PORTS = (Port.B, Port.C, Port.D, Port.E, Port.F)
PORT_NAMES = {Port.B: "B", Port.C: "C", Port.D: "D", Port.E: "E", Port.F: "F"}


def parse_repr(text):
    """Read text like "(57,)" or "(1.5, 2)" sent by the sensor board."""
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    values = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(part))
        except ValueError:
            try:
                values.append(float(part))
            except ValueError:
                values.append(part.strip("'\""))
    if len(values) == 1:
        return values[0]
    return tuple(values)


def decode(payload):
    """payload = [length, cmd_len, cmd..., fmt_len, fmt..., data...]"""
    name_len = payload[1]
    cmd = bytes(payload[2:2 + name_len]).decode()
    data = bytes(payload[2 + name_len:])
    if data == b"\x01z":
        return cmd, None
    start = data[0] + 1
    fmt = data[1:start]
    body = data[start:]
    if fmt == b"raw":
        return cmd, body
    if fmt == b"repr":
        return cmd, parse_repr(body.decode())
    values = struct.unpack(fmt.decode(), body)
    if len(values) == 1:
        return cmd, values[0]
    return cmd, values


class FrameReader:
    """Collects UART bytes and cuts out '<' length payload '>' messages."""

    def __init__(self):
        self.buf = b""

    def clear(self):
        self.buf = b""

    def feed(self, data):
        self.buf += data
        if len(self.buf) > 512:
            self.buf = self.buf[-512:]

    def next_message(self):
        """Return (command, value) for the next complete message, else None."""
        while True:
            buf = self.buf
            start = 0
            while start < len(buf) and buf[start] != 0x3C:  # '<'
                start += 1
            buf = buf[start:]
            if len(buf) < 2:
                self.buf = buf
                return None
            size = buf[1]
            if len(buf) < size + 3:
                self.buf = buf
                return None  # message not complete yet
            if buf[size + 2] != 0x3E:  # '>'
                self.buf = buf[1:]  # false start, look for the next '<'
                continue
            payload = buf[1:size + 2]
            self.buf = buf[size + 3:]
            try:
                return decode(payload)
            except Exception:
                continue  # damaged message, try the next one


def find_motors():
    found = []
    for port in MOTOR_PORTS:
        try:
            found.append((port, Motor(port)))
        except OSError:
            pass  # nothing (or not a motor) on this port
    return found


def main():
    hub = PrimeHub()
    clock = StopWatch()

    motors = find_motors()
    if not motors:
        print("No motors found on ports B, C, D, E or F.")
        hub.display.char("X")
        wait(3000)
        return

    uart = UARTDevice(SENSOR_PORT, BAUDRATE)
    reader = FrameReader()

    index = 0
    readings = []
    spikes = []
    last_data = clock.time()
    last_button = 0

    def select(i):
        port, motor = motors[i]
        motor.reset_angle()  # 0 = the motor's marked home position
        hub.display.char(PORT_NAMES[port])
        wait(600)
        return motor

    motor = select(index)

    while True:
        now = clock.time()

        # Left / right buttons choose the motor
        pressed = hub.buttons.pressed()
        if now - last_button > 300:
            if Button.RIGHT in pressed:
                index = (index + 1) % len(motors)
                motor = select(index)
                last_button = clock.time()
            elif Button.LEFT in pressed:
                index = (index - 1) % len(motors)
                motor = select(index)
                last_button = clock.time()

        # Read whatever the sensor has sent
        waiting = uart.waiting()
        if waiting:
            reader.feed(uart.read_all())

        message = reader.next_message()
        while message is not None:
            cmd, value = message
            if cmd == "muscle_data":
                if isinstance(value, tuple):
                    value = value[0]
                last_data = clock.time()
                handle_reading(hub, motor, value, readings, spikes, clock, uart, reader)
            message = reader.next_message()

        if clock.time() - last_data > 2000:
            print("No data from the muscle sensor. Check the cable in port A.")
            last_data = clock.time()

        wait(10)


def handle_reading(hub, motor, value, readings, spikes, clock, uart, reader):
    readings.append(value)
    if len(readings) > SMOOTHING:
        readings.pop(0)
    smoothed = sum(readings) / len(readings)
    print("Smoothed muscle sensor value:", smoothed)
    show_level(hub, smoothed)

    # Relaxed: arm goes back to 0
    if value < REST_BELOW:
        motor.run_target(MOTOR_SPEED, 0, wait=False)
        return

    # Count big squeezes in the last SPIKE_WINDOW_MS
    now = clock.time()
    if value > SPIKE_ABOVE:
        spikes.append(now)
    while spikes and now - spikes[0] >= SPIKE_WINDOW_MS:
        spikes.pop(0)

    if len(spikes) >= SPIKES_NEEDED:
        print("Big squeezes detected: full open.")
        motor.run_target(MOTOR_SPEED, MAX_ANGLE, wait=False)
        wait(SPIKE_HOLD_MS)
        spikes.clear()
        readings.clear()
        uart.clear()      # drop readings that piled up while holding
        reader.clear()
    else:
        motor.run_target(MOTOR_SPEED, int(smoothed / 100 * MAX_ANGLE), wait=False)


def show_level(hub, value):
    """Draw a bar on the 5x5 light matrix: 0-100 maps to 0-5 rows."""
    level = int(value / 100 * 5)
    hub.display.off()
    for row in range(min(level, 5)):
        hub.display.pixel(4 - row, 2, 100)


if __name__ == "__main__":
    main()
