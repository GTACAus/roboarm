# GTAC robotic arm: muscle sensor AND web remote for LEGO SPIKE Prime (official SPIKE App 3)
#
# An LMS-ESP32 running arm_board.py is plugged into PORT A and looks like a Distance Sensor.
#   * Muscle mode (nobody using the remote): distance in cm is muscle strength, about 5 to 100.
#       relaxed = motor at 0 degrees, full squeeze = MAX_ANGLE.
#       The left / right hub buttons choose which motor the muscle controls.
#   * Remote mode (someone has the remote page open): the board sends motor commands for
#       ports B to F, and the motors move while controls are held.
# The program switches by itself. Readings above 110 cm are remote commands.

from hub import port, button, light_matrix
import distance_sensor
import device
import motor
import runloop
import time

# ---------------------------------------------------------------------------
# SETTINGS: change these numbers to change how your arm moves
# ---------------------------------------------------------------------------
SENSOR_PORT = port.A                      # where the board is plugged in

# Muscle mode
MAX_ANGLE = 180                           # how far the motor turns at full squeeze (degrees)
MUSCLE_SPEED = 200                        # how fast the motor moves (degrees per second)
MIN_CM = 5                                # sensor reading when the muscle is relaxed
MAX_CM = 100                              # sensor reading that counts as a full squeeze
SMOOTHING = 3                             # average the last N readings

# Remote mode
DIRECTIONS = (1, 1, 1, 1, 1)              # use -1 to swap forward and back for motors B, C, D, E, F
SPEEDS = (60, 150, 300)                   # slow, medium, fast (degrees per second)

LOST_AFTER_MS = 600                       # no good reading for this long = stop the remote's motors
# ---------------------------------------------------------------------------

MOTOR_PORTS = (port.B, port.C, port.D, port.E, port.F)
PORT_NAMES = ("B", "C", "D", "E", "F")
# SPIKE device ids of motors: medium, large, small, medium angular, large angular
MOTOR_IDS = (48, 49, 65, 75, 76)

# Must match remote_web.py
REMOTE_BASE_MM = 1100
REMOTE_STEP_MM = 20
MOTOR_COUNT = 5
REMOTE_HOLD_MS = 1500                     # stay in remote mode this long after the last remote command


def decode_remote(mm):
    """Distance in mm -> (motor number 0-4, state 0-6), or None if it is not a remote command.

    State: 0 stop, 1-3 forward (slow, medium, fast), 4-6 back (slow, medium, fast)."""
    offset = mm - REMOTE_BASE_MM
    code = round(offset / REMOTE_STEP_MM)
    if code < 0 or code >= MOTOR_COUNT * 7 or abs(offset - code * REMOTE_STEP_MM) > 6:
        return None
    return code // 7, code % 7


def apply_remote(index, state):
    try:
        if state == 0:
            motor.stop(MOTOR_PORTS[index])
        elif state <= 3:
            motor.run(MOTOR_PORTS[index], DIRECTIONS[index] * SPEEDS[state - 1])
        else:
            motor.run(MOTOR_PORTS[index], -DIRECTIONS[index] * SPEEDS[state - 4])
    except Exception:
        pass  # no motor on that port


def find_motors():
    found = []
    for i in range(len(MOTOR_PORTS)):
        try:
            if device.id(MOTOR_PORTS[i]) in MOTOR_IDS:
                found.append(i)
        except Exception:
            pass
    return found


def show_level(fraction):
    """Bar on the 5x5 light matrix: 0 to 1 maps to 0 to 5 rows."""
    level = int(fraction * 5)
    light_matrix.clear()
    for row in range(min(level, 5)):
        light_matrix.set_pixel(2, 4 - row, 100)


def muscle_fraction(cm):
    """Relaxed (MIN_CM) = 0, full squeeze (MAX_CM) = 1."""
    fraction = (cm - MIN_CM) / (MAX_CM - MIN_CM)
    if fraction < 0:
        return 0
    if fraction > 1:
        return 1
    return fraction


async def main():
    motors = find_motors()              # motors the muscle can control
    index = 0
    current = MOTOR_PORTS[motors[0]] if motors else None

    mode = "muscle"
    applied = [0] * MOTOR_COUNT         # what the remote has each motor doing
    readings = []
    last_angle = -1
    previous = -1                       # last reading: act only on a reading seen twice
    last_good = time.ticks_ms()
    last_remote = time.ticks_ms() - 100000

    if motors:
        light_matrix.write(PORT_NAMES[motors[0]])
        await runloop.sleep_ms(600)

    while True:
        mm = distance_sensor.distance(SENSOR_PORT)
        now = time.ticks_ms()
        steady = (mm == previous)
        previous = mm

        remote_message = decode_remote(mm) if (steady and mm >= 1100) else None
        muscle_reading = steady and 0 < mm <= 1050

        if remote_message is not None:
            last_good = now
            last_remote = now
            if mode != "remote":
                mode = "remote"
                if current is not None:
                    motor.stop(current)
                last_angle = -1
                readings = []
                light_matrix.write("R")
            motor_number, state = remote_message
            if applied[motor_number] != state:
                applied[motor_number] = state
                apply_remote(motor_number, state)

        elif muscle_reading and time.ticks_diff(now, last_remote) > REMOTE_HOLD_MS:
            last_good = now
            if mode != "muscle":
                for i in range(MOTOR_COUNT):
                    apply_remote(i, 0)
                applied = [0] * MOTOR_COUNT
                mode = "muscle"
            if motors:
                # Left / right buttons choose the motor
                if button.pressed(button.RIGHT) > 0:
                    index = (index + 1) % len(motors)
                elif button.pressed(button.LEFT) > 0:
                    index = (index - 1) % len(motors)
                if MOTOR_PORTS[motors[index]] != current:
                    await motor.run_to_absolute_position(current, 0, MUSCLE_SPEED)  # park the old motor
                    current = MOTOR_PORTS[motors[index]]
                    last_angle = -1
                    light_matrix.write(PORT_NAMES[motors[index]])
                    await runloop.sleep_ms(600)
                    continue

                readings.append(mm / 10)
                if len(readings) > SMOOTHING:
                    readings.pop(0)
                cm = sum(readings) / len(readings)
                fraction = muscle_fraction(cm)
                angle = int(fraction * MAX_ANGLE)
                show_level(fraction)
                if angle != last_angle:
                    last_angle = angle
                    await motor.run_to_absolute_position(current, angle, MUSCLE_SPEED)

        elif time.ticks_diff(now, last_good) > LOST_AFTER_MS:
            # The board is gone or reading nonsense: relax everything
            if mode == "remote" and applied != [0] * MOTOR_COUNT:
                for i in range(MOTOR_COUNT):
                    apply_remote(i, 0)
                applied = [0] * MOTOR_COUNT
            elif mode == "muscle" and current is not None and last_angle != 0 and time.ticks_diff(now, last_good) > 1500:
                print("No data from the board. Check the cable in port A.")
                last_angle = 0
                await motor.run_to_absolute_position(current, 0, MUSCLE_SPEED)

        await runloop.sleep_ms(5)


runloop.run(main())
