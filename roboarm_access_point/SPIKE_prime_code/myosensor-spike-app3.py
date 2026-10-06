# GTAC robotic arm: muscle sensor control for LEGO SPIKE Prime (official SPIKE App 3)
#
# The muscle sensor board (LMS-ESP32 running emg_distance_sensor.py) plugs into PORT A.
# The hub thinks it is a Distance Sensor: distance in cm = muscle strength, about 5 to 100.
#
#     relaxed muscle  -> motor at 0 degrees
#     full squeeze    -> motor at MAX_ANGLE degrees
#     in between      -> in proportion
#
# Left / right hub buttons choose which motor port is controlled.

from hub import port, button, light_matrix
import distance_sensor
import device
import motor
import runloop
import time

# ---------------------------------------------------------------------------
# SETTINGS: change these numbers to change how your arm moves
# ---------------------------------------------------------------------------
SENSOR_PORT = port.A        # where the muscle sensor is plugged in

MAX_ANGLE = 180             # how far the motor turns at full squeeze (degrees)
MOTOR_SPEED = 200           # how fast the motor moves (degrees per second)

MIN_CM = 5                  # sensor reading when the muscle is relaxed
MAX_CM = 100                # sensor reading that counts as a full squeeze.
                            # Lower it (for example 70) so a lighter squeeze reaches the maximum.

SMOOTHING = 3               # average the last N readings (bigger = calmer, slower)
# ---------------------------------------------------------------------------

MOTOR_PORTS = (port.B, port.C, port.D, port.E, port.F)
PORT_NAMES = ("B", "C", "D", "E", "F")
# SPIKE device ids of motors: medium, large, small, medium angular, large angular
MOTOR_IDS = (48, 49, 65, 75, 76)


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


def angle_for(cm):
    """Relaxed (MIN_CM) = 0 degrees, full squeeze (MAX_CM) = MAX_ANGLE."""
    fraction = (cm - MIN_CM) / (MAX_CM - MIN_CM)
    if fraction < 0:
        fraction = 0
    elif fraction > 1:
        fraction = 1
    return fraction


async def main():
    motors = find_motors()
    if not motors:
        print("No motors found on ports B, C, D, E or F.")
        light_matrix.write("X")
        return

    index = 0
    current = MOTOR_PORTS[motors[index]]
    light_matrix.write(PORT_NAMES[motors[index]])
    await runloop.sleep_ms(600)

    readings = []
    last_angle = -1
    last_data = time.ticks_ms()

    while True:
        # Left / right buttons choose the motor
        if button.pressed(button.RIGHT) > 0:
            index = (index + 1) % len(motors)
        elif button.pressed(button.LEFT) > 0:
            index = (index - 1) % len(motors)
        if MOTOR_PORTS[motors[index]] != current:
            await motor.run_to_absolute_position(current, 0, MOTOR_SPEED)  # park the old motor
            current = MOTOR_PORTS[motors[index]]
            last_angle = -1
            light_matrix.write(PORT_NAMES[motors[index]])
            await runloop.sleep_ms(600)
            continue

        # The hub reports the sensor's distance in mm: 10 mm = 1 cm
        mm = distance_sensor.distance(SENSOR_PORT)
        now = time.ticks_ms()
        # The board never sends more than 100 cm. A reading of -1 or 200 cm means the
        # hub lost the sensor for a moment, so ignore it and keep the last good value.
        if mm < 0 or mm > 1100:
            if time.ticks_diff(now, last_data) > 1500 and last_angle != 0:
                # Lost the sensor for a while: relax the arm instead of holding it
                print("No data from the muscle sensor. Check the cable in port A.")
                last_angle = 0
                await motor.run_to_absolute_position(current, 0, MOTOR_SPEED)
            await runloop.sleep_ms(30)
            continue
        last_data = now

        readings.append(mm / 10)
        if len(readings) > SMOOTHING:
            readings.pop(0)
        cm = sum(readings) / len(readings)

        fraction = angle_for(cm)
        angle = int(fraction * MAX_ANGLE)
        show_level(fraction)

        # Only move the motor when the target changes by a degree or more
        if angle != last_angle:
            last_angle = angle
            print("Muscle", int(cm), "cm -> motor", angle, "degrees")
            await motor.run_to_absolute_position(current, angle, MOTOR_SPEED)

        await runloop.sleep_ms(30)


runloop.run(main())
