#!/usr/bin/env python3
"""Write STEP models for parts KiCad's library doesn't have, so the boards render whole.

    python3 gen_models.py      -> lms-esp32.3dshapes/*.step

Reuses the box-solid STEP writer from the growcube PCB repo (../../PCB/models/gen_models.py).
Each model is in its footprint's frame (KiCad model axes: x right, y up = footprint y flipped,
z up from the board's top), origin at the part's top-left corner.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "PCB", "models"))
from gen_models import Step, b  # noqa: E402

OUT = os.path.join(HERE, "lms-esp32.3dshapes")

MODULE_PCB, CAN, MARK = (0.07, 0.07, 0.08), (0.78, 0.78, 0.80), (0.20, 0.20, 0.22)
SW_BODY, BLACK, FERRITE = (0.86, 0.85, 0.82), (0.06, 0.06, 0.07), (0.16, 0.16, 0.17)
LED_BODY, LED_WINDOW = (0.95, 0.95, 0.93), (0.93, 0.82, 0.45)
GOLD, BORE = (0.85, 0.64, 0.22), (0.02, 0.02, 0.02)
TRIM_BODY, TRIM_ROTOR = (0.93, 0.92, 0.88), (0.72, 0.72, 0.74)


def esp32_pico_mini_02():
    """ESP32-PICO-MINI-02 (13.2 x 16.6 x 2.4 mm), lying with its antenna end at footprint x = 0
    (the LMS-ESP32's left edge): a black module board, the shield can over the other 10.8 mm."""
    out = [b(0, 0, 16.6, 13.2, 0, 0.8, MODULE_PCB),
           b(5.8, 0.3, 16.4, 12.9, 0.8, 2.4, CAN)]
    out.append(b(15.3, 11.6, 15.7, 12.0, 2.4, 2.41, MARK))      # pin-1 dot on the can
    return out


def side_switch():
    """The RST switch: a pale 5.2 x 3.7 mm side-push body centred on the footprint, its black
    plunger poking 1 mm past the board's top edge (footprint -y)."""
    return [b(-2.6, -1.85, 2.6, 1.85, 0, 1.9, SW_BODY),
            b(-0.7, -2.95, 0.7, -1.85, 0.4, 1.5, BLACK)]


def inductor_4x4():
    """The 2R2 power inductor, a 4.5 mm square shielded drum, 2 mm tall, centred."""
    return [b(-2.25, -2.25, 2.25, 2.25, 0, 2.0, FERRITE)]


def led_2020():
    """WS2812B-2020 RGB LED: 2 mm white body with its yellow window, centred."""
    return [b(-1.0, -1.0, 1.0, 1.0, 0, 0.8, LED_BODY), b(-0.7, -0.7, 0.7, 0.7, 0.8, 0.84, LED_WINDOW)]



def jack_35():
    """The EMG board's 3.5 mm jack, sized from DFRobot's drawing: a 6.5 mm wide black body
    running 11.3 mm in from the board edge, its nose 2.4 mm out past the edge, a gold cage over
    the mouth. Origin on the board edge at the jack's centre line; the bore's axis is 2.6 mm up."""
    out = [b(0, -3.25, 11.3, 3.25, 0, 5.2, BLACK),
           b(-2.4, -2.5, 0, 2.5, 0.1, 5.1, BLACK),
           b(0, -3.4, 2.8, 3.4, 0, 5.4, GOLD),
           b(-2.42, -1.75, -2.4, 1.75, 0.85, 4.35, BORE)]
    for x in (1.2, 6.0, 10.2):                                              # gold tabs
        for y in (-3.9, 3.9):
            out.append(b(x - 0.6, y - 0.45, x + 0.6, y + 0.45, 0, 0.3, GOLD))
    return out


def trimmer_3mm():
    """The MyoWare's gain trimmer: a 3 x 3.6 mm white base with a silver slotted rotor, centred."""
    return [b(-1.5, -1.8, 1.5, 1.8, 0, 1.0, TRIM_BODY), b(-1.2, -1.2, 1.2, 1.2, 1.0, 1.6, TRIM_ROTOR),
            b(-0.9, -0.15, 0.9, 0.15, 1.6, 1.65, BORE)]


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("ESP32-PICO-MINI-02", esp32_pico_mini_02), ("RST_Side_Switch", side_switch),
                     ("Inductor_4.5x4.5", inductor_4x4), ("LED_2020_RGB", led_2020), ("Jack_3.5mm_EMG", jack_35),
                     ("Trimmer_3mm", trimmer_3mm)):
        path = os.path.join(OUT, name + ".step")
        Step().write(path, name, fn())
        print("wrote", os.path.relpath(path, HERE))
