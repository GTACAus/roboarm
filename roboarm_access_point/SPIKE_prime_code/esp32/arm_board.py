# LMS-ESP32 for the robotic arm: muscle sensor AND web remote in one program.
#
# Plugged into the hub, the board looks like a LEGO Distance Sensor and does two jobs:
#   * Nobody has the remote page open, or the page is switched to "Muscle sensor":
#       it listens to the muscle sensor (readings 5 to 100 cm).
#   * Someone has the remote page open and set to "Remote":
#       it sends the remote's motor commands (readings above 110 cm).
# The hub program arm-spike-app3.py follows whichever one it is hearing.
#
# Needs on the board (all in this repo): lpf2.py, distance_emulator.py,
# emg_distance_sensor.py and remote_web.py. Save THIS file as main.py to run at power-up.

import utime
import machine
import lpf2
from distance_emulator import DistanceSensorEmulator, make_modes
import emg_distance_sensor as muscle
import remote_web as web

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------
EMG_ENABLED = True      # False if no muscle sensor is plugged in: the muscle reading then stays relaxed
DEBUG = False           # True prints connection details from the sensor library
# ---------------------------------------------------------------------------


def main():
    if not hasattr(lpf2.LPF2, "_send_info_sequence"):
        raise RuntimeError("lpf2.py is too old. Copy the newest lpf2.py from the PUPRemote project onto the board.")

    remote = web.WebRemote()            # starts the Wi-Fi network first, so it is there during calibration
    emg = muscle.Emg()
    if EMG_ENABLED:
        emg.calibrate()

    sensor = DistanceSensorEmulator(make_modes(), sensor_id=62, debug=DEBUG)
    last_send = utime.ticks_ms()
    target = 0
    percent = 0
    mode = "muscle"
    if EMG_ENABLED:
        remote.muscle_percent = 0       # the page shows the Remote / Muscle sensor toggle and a meter

    while True:
        remote.poll()
        active = remote.remote_wanted()

        if active != (mode == "remote"):
            mode = "remote" if active else "muscle"
            print("Mode:", mode)

        if mode == "muscle" and EMG_ENABLED:
            target = emg.measure()

        held = utime.ticks_diff(utime.ticks_ms(), last_send)
        if mode == "remote":
            due = held >= web.FRAME_MS or (remote.has_urgent() and held >= web.HOLD_MS)   # changes go out at once
        else:
            due = held >= muscle.SEND_EVERY_MS
        if due:
            last_send = utime.ticks_ms()
            if mode == "remote":
                mm = remote.next_distance_mm()
            else:
                percent = emg.step(target) if EMG_ENABLED else 0
                mm = muscle.MIN_MM + int(percent * (muscle.MAX_MM - muscle.MIN_MM) / 100)
                if EMG_ENABLED:
                    remote.push_muscle(int(percent))          # live graph on the page
            sensor.update_payload(mm, 0)                  # DISTL
            sensor.update_payload(min(mm, 320), 1)        # DISTS
            sensor.update_payload(mm, 2)                  # SINGL
            sensor.update_payload(int(mm * 5.83), 4)      # TRAW
            sensor.update_payload(mm, 7)                  # ADRAW

        sensor.heartbeat()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise                      # Ctrl+C / Stop in Thonny still works
    except Exception as error:
        print("Error:", error)
        utime.sleep_ms(3000)
        machine.reset()
