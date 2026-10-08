# GTAC robotic arm: SPIKE Prime hub program (official SPIKE App 3, Python)
#
# The LMS-ESP32 board is plugged into PORT A and looks like a Distance Sensor.
#   Muscle mode: the reading is muscle strength. Relaxed = the motor's home (baseline) position,
#                full squeeze = home + MAX_ANGLE.
#   Remote mode: the iPad remote or a Blockly program sends motor commands through the board.
# This program also tells the board to turn its Wi-Fi on, and reports motor positions and
# home positions back to it, using the Distance Sensor's lights. See PROTOCOL.md.
#
# Hub buttons: left / right choose the muscle motor. Hold BOTH for 1 second: Wi-Fi on / off.

from hub import port, button, light_matrix
import distance_sensor
import device
import motor
import runloop
import time

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------
SENSOR_PORT = port.A          # where the board is plugged in
START_WIFI = True             # turn the board's Wi-Fi on when this program starts

MAX_ANGLE = 180               # muscle mode: how far the motor turns at full squeeze (degrees)
MUSCLE_DIRECTION = 1          # use -1 to make the squeeze turn the other way
MUSCLE_SPEED = 200            # muscle mode motor speed (degrees per second)
SMOOTHING = 3                 # average the last N muscle readings

DIRECTIONS = (1, 1, 1, 1, 1)  # remote: use -1 to swap forward and back for motors B, C, D, E, F
SPEEDS = (60, 150, 300)       # slow, medium, fast (degrees per second)

REHOME_DEG = 8                # a still motor moved by hand more than this...
REHOME_STILL_MS = 1000        # ...and then held still this long = its new home position
LOST_AFTER_MS = 600           # no good reading for this long = stop the remote's motors
# ---------------------------------------------------------------------------

MOTOR_PORTS = (port.B, port.C, port.D, port.E, port.F)
NAMES = "BCDEF"
MOTOR_IDS = (48, 49, 65, 75, 76)          # medium, large, small, medium angular, large angular

# Board -> hub commands (must match the board's main.py)
CMD_MM, CMD_STEP = 1100, 5
STOP_ALL, HOME, REBASE, MUSCLE_MOTOR, GO_HEAD, GO_ANGLE, TURN_HEAD = 35, 36, 37, 38, 43, 88, 160
REMOTE_HOLD_MS = 1500                     # stay in remote mode this long after the last remote command
GO_DIRECTIONS = (motor.SHORTEST_PATH, motor.CLOCKWISE, motor.COUNTERCLOCKWISE)

negative_range = False                    # True once a motor reports positions below 0 (-180..179)


def decode_command(mm):
    """Distance in mm -> command code, or None."""
    offset = mm - CMD_MM
    code = round(offset / CMD_STEP)
    if 0 <= code <= TURN_HEAD + 14 and abs(offset - code * CMD_STEP) <= 2:
        return code
    return None


def read_board():
    """The board's reading, or -1 while there is no Distance Sensor on the port
    (board unplugged, or still starting up: it needs a few seconds after power-up)."""
    try:
        return distance_sensor.distance(SENSOR_PORT)
    except OSError:
        return -1


def fitted():
    """Motor numbers 0-4 that have a motor plugged in."""
    found = []
    for i in range(5):
        try:
            if device.id(MOTOR_PORTS[i]) in MOTOR_IDS:
                found.append(i)
        except Exception:
            pass
    return found


def position(i):
    """Motor i's position, 0..359, or -1 if there is no motor."""
    global negative_range
    try:
        p = motor.absolute_position(MOTOR_PORTS[i])
    except Exception:
        return -1
    if p < 0:
        negative_range = True
    return p % 360


def to_motor(angle):
    """0..359 -> the range this hub's motors use."""
    angle %= 360
    if negative_range and angle > 179:
        return angle - 360
    return angle


def go(i, angle, speed, direction=motor.SHORTEST_PATH):
    try:
        motor.run_to_absolute_position(MOTOR_PORTS[i], to_motor(angle), speed, direction=direction)
    except Exception:
        pass


def set_home(i):
    """This motor's home (baseline) is where it is now: relative position 0."""
    try:
        motor.reset_relative_position(MOTOR_PORTS[i], 0)
    except Exception:
        pass


def go_from_home(i, offset, speed):
    """Move to `offset` degrees from home. Never wraps, so it never swings the long way round."""
    try:
        motor.run_to_relative_position(MOTOR_PORTS[i], int(offset), speed)
    except Exception:
        pass


def turn(i, degrees, speed):
    """Turn motor i by `degrees` (negative: back) from where it is now."""
    try:
        motor.run_for_degrees(MOTOR_PORTS[i], int(degrees) * DIRECTIONS[i], speed)
    except Exception:
        pass


def run_state(i, state):
    try:
        if state == 0:
            motor.stop(MOTOR_PORTS[i])
        elif state <= 3:
            motor.run(MOTOR_PORTS[i], DIRECTIONS[i] * SPEEDS[state - 1])
        else:
            motor.run(MOTOR_PORTS[i], -DIRECTIONS[i] * SPEEDS[state - 4])
    except Exception:
        pass


class Board:
    """Messages to the board through the Distance Sensor's lights (at most 20 a second)."""

    def __init__(self):
        self.queue = []
        self.last = 0

    def send(self, kind, a=0, b=0, c=0, first=False):
        msg = [kind, a, b, c]
        same_motor = kind in (2, 3)                 # positions: one per motor; others: one per kind
        self.queue = [m for m in self.queue if not (m[0] == kind and (not same_motor or m[1] == a))]
        if first:
            self.queue.insert(0, msg)
        else:
            self.queue.append(msg)

    def angle(self, kind, i, angle):
        self.send(kind, i, angle // 100, angle % 100)

    def tick(self, now):
        if self.queue and time.ticks_diff(now, self.last) >= 50:
            self.last = now
            try:
                distance_sensor.show(SENSOR_PORT, self.queue.pop(0))
            except Exception:
                pass


async def main():
    board = Board()
    motors = fitted()
    mask = sum(1 << i for i in motors)
    baseline = [position(i) for i in range(5)]
    rest = list(baseline)                 # where each motor should be resting (None: learn it once settled)
    busy_until = [0] * 5                  # commanded motors are not checked for re-homing
    candidate = [-1] * 5
    candidate_since = [0] * 5
    reported = [-1] * 5

    muscle_motor = motors[0] if motors else 0
    mode = 0                              # 0 muscle, 1 remote
    applied = [0] * 5                     # remote run state of each motor
    go_head = None                        # a go-to header waiting for its angle
    turn_head = None                      # a turn header: [motor, speed, direction and full turns, time]
    last_code = None                      # the board's commands count once, when the reading changes
    readings = []
    last_angle = -1
    previous = -1
    last_good = time.ticks_ms()
    last_remote = time.ticks_ms() - 100000
    lost = True
    wifi = START_WIFI
    both_since = None
    last_status = 0
    last_report = 0
    report_next = 0
    rebase_at = None                      # re-read the homes once the motors have settled
    for i in motors:
        set_home(i)

    def send_hello():
        board.send(1, 1 if wifi else 0, first=True)
        for i in motors:
            board.angle(3, i, baseline[i])
        board.send(4, mode, muscle_motor, mask)

    def rebase():
        for i in motors:
            baseline[i] = rest[i] = position(i)
            set_home(i)
            board.angle(3, i, baseline[i])

    def commanded(i, ms, expect=None):
        """Motor i was told to move: skip re-homing checks for `ms`, then expect it at `expect`
        (None: learn where it settles, e.g. after a plain stop)."""
        busy_until[i] = time.ticks_add(time.ticks_ms(), ms)
        rest[i] = None if expect is None else expect % 360

    def stop_all():
        for i in range(5):
            run_state(i, 0)
            applied[i] = 0

    light_matrix.write("?")                  # until the board answers on port A
    print("Waiting for the board on port A...")

    while True:
        now = time.ticks_ms()
        mm = read_board()
        steady = mm == previous
        previous = mm
        code = decode_command(mm) if steady and mm >= 1100 else None
        muscle = steady and 0 < mm <= 1050

        if code is not None or muscle:
            if lost:                      # the board (re)connected: introduce ourselves
                lost = False
                send_hello()
                light_matrix.write(("R" if mode else NAMES[muscle_motor]) if motors else "X")
                print("Board found on port A")
            last_good = now

        if muscle:
            last_code = None
        fresh = code is not None and code != last_code
        if fresh:
            last_code = code
            if code < 35 or code >= GO_HEAD:              # remote commands
                last_remote = now
                if mode != 1:
                    mode = 1
                    light_matrix.write("R")
                    try:
                        motor.stop(MOTOR_PORTS[muscle_motor])
                    except Exception:
                        pass
                    board.send(4, mode, muscle_motor, mask)
            if code < 35:
                i, state = code // 7, code % 7
                if applied[i] != state:
                    applied[i] = state
                    run_state(i, state)
                    commanded(i, 100000 if state else 1500)
            elif code == STOP_ALL:
                stop_all()
                if mode == 0 and muscle_motor in motors:
                    last_angle = -1
            elif code == HOME:
                stop_all()
                for i in motors:
                    go_from_home(i, 0, SPEEDS[1])
                    commanded(i, 3000, baseline[i])
            elif code == REBASE:
                rebase_at = time.ticks_add(now, 800)   # after the stop has settled
            elif code < GO_HEAD:                          # muscle motor chosen on the iPad
                m = code - MUSCLE_MOTOR
                if m != muscle_motor and m in motors:
                    if mode == 0:
                        go_from_home(muscle_motor, 0, MUSCLE_SPEED)    # park the old one at home
                        commanded(muscle_motor, 2000, baseline[muscle_motor])
                        light_matrix.write(NAMES[m])
                    muscle_motor = m
                    last_angle = -1
                    board.send(4, mode, muscle_motor, mask)
            elif code >= TURN_HEAD:                       # turn header
                h = code - TURN_HEAD
                turn_head = [h // 3, h % 3, None, now]
                go_head = None
            elif code < GO_ANGLE:                         # go-to header
                h = code - GO_HEAD
                go_head = (h // 9, (h // 3) % 3, h % 3, now)
                turn_head = None
            elif turn_head is not None and time.ticks_diff(now, turn_head[3]) < 300:
                if turn_head[2] is None:                  # 1st value: direction and full turns
                    turn_head[2] = code - GO_ANGLE
                    turn_head[3] = now
                else:                                     # 2nd value: the rest, in 5-degree steps
                    i, v, a, _ = turn_head
                    turn_head = None
                    degrees = ((a % 36) * 72 + code - GO_ANGLE) * 5
                    if a >= 36:
                        degrees = -degrees
                    applied[i] = 0
                    turn(i, degrees, SPEEDS[v])
                    commanded(i, int(abs(degrees) * 1000 / SPEEDS[v]) + 1000)
            elif go_head is not None and time.ticks_diff(now, go_head[3]) < 300:
                i, d, v, _ = go_head
                go_head = None
                angle = (code - GO_ANGLE) * 5
                applied[i] = 0
                go(i, angle, SPEEDS[v], GO_DIRECTIONS[d])
                commanded(i, 3000, angle)

        elif muscle and time.ticks_diff(now, last_remote) > REMOTE_HOLD_MS:
            if mode != 0:
                mode = 0
                stop_all()
                last_angle = -1
                light_matrix.write(NAMES[muscle_motor])
                board.send(4, mode, muscle_motor, mask)
            if motors:
                pct = (mm - 50) / 9.5
                readings.append(pct)
                if len(readings) > SMOOTHING:
                    readings.pop(0)
                fraction = max(0, min(1, sum(readings) / len(readings) / 100))
                offset = int(MUSCLE_DIRECTION * fraction * MAX_ANGLE)
                if abs(offset - last_angle) >= 2:
                    last_angle = offset
                    go_from_home(muscle_motor, offset, MUSCLE_SPEED)
                commanded(muscle_motor, 1500, baseline[muscle_motor] + offset)

        elif time.ticks_diff(now, last_good) > LOST_AFTER_MS:
            if not lost:
                lost = True
                stop_all()
                if mode == 0 and motors and last_angle != 0:
                    last_angle = 0
                    go_from_home(muscle_motor, 0, MUSCLE_SPEED)   # relax the arm
                light_matrix.write("?")
                print("Waiting for the board on port A...")

        # Hub buttons: left / right choose the muscle motor; both for 1 s toggle the Wi-Fi
        left = button.pressed(button.LEFT) > 0
        right = button.pressed(button.RIGHT) > 0
        if left and right:
            if both_since is None:
                both_since = now
            elif time.ticks_diff(now, both_since) > 1000:
                both_since = time.ticks_add(now, 100000)   # once per hold
                wifi = not wifi
                board.send(1, 1 if wifi else 0, first=True)
                light_matrix.write("W" if wifi else "-")
        else:
            both_since = None
            if (left or right) and mode == 0 and len(motors) > 1:
                k = motors.index(muscle_motor) if muscle_motor in motors else 0
                m = motors[(k + (1 if right else -1)) % len(motors)]
                go_from_home(muscle_motor, 0, MUSCLE_SPEED)
                commanded(muscle_motor, 2000, baseline[muscle_motor])
                muscle_motor = m
                last_angle = -1
                light_matrix.write(NAMES[m])
                board.send(4, mode, muscle_motor, mask)
                await runloop.sleep_ms(300)

        # Positions for the iPad, and re-homing: a still motor moved by hand gets a new home
        if motors and time.ticks_diff(now, last_report) >= 100:
            last_report = now
            i = motors[report_next % len(motors)]
            report_next += 1
            p = position(i)
            if p >= 0:
                if abs(p - reported[i]) >= 2:
                    reported[i] = p
                    board.angle(2, i, p)
                idle = time.ticks_diff(now, busy_until[i]) > 0 and applied[i] == 0
                if idle and rest[i] is None:
                    rest[i] = p                           # settled after a command: that is where it rests
                moved = 0 if rest[i] is None else min(abs(p - rest[i]), 360 - abs(p - rest[i]))
                if idle and moved > REHOME_DEG:
                    if candidate[i] < 0 or min(abs(p - candidate[i]), 360 - abs(p - candidate[i])) > 2:
                        candidate[i] = p
                        candidate_since[i] = now
                    elif time.ticks_diff(now, candidate_since[i]) > REHOME_STILL_MS:
                        baseline[i] = rest[i] = p
                        set_home(i)
                        candidate[i] = -1
                        board.angle(3, i, p)
                else:
                    candidate[i] = -1

        if rebase_at is not None and time.ticks_diff(now, rebase_at) > 0:
            rebase_at = None
            rebase()

        if time.ticks_diff(now, last_status) > 2000:
            last_status = now
            board.send(4, mode, muscle_motor, mask)

        board.tick(now)
        await runloop.sleep_ms(5)


runloop.run(main())
