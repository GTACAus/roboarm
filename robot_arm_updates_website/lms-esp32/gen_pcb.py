"""Write the two board models as KiCad boards, so kicad-cli can export them (with silkscreen)
as glTF for the assembly viewer:

    lms-esp32/lms-esp32.kicad_pcb    Anton's Mindstorms LMS-ESP32 v2.0, 39.8 x 55.8 mm
    emg/emg.kicad_pcb                DFRobot SEN0240 EMG signal board, 35 x 22 mm

Runs under KiCad's bundled Python:
    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 gen_pcb.py

These are models, not designs: footprints sit where the parts are on the real boards (measured
from Anton's top-view photo at about 26.9 px/mm and DFRobot's dimension photo), with no nets or
tracks. The silkscreen carries the labels exactly as printed on the boards.

Board frame: x right, y down, origin at the board's top-left corner. LMS-ESP32 seen from the top
with the USB-C at the top edge, the 14 x 2 header down the right edge and the Grove and Qwiic
sockets on the bottom edge.
"""
import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
FPLIB = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
mm = pcbnew.VECTOR2I_MM


def new_board():
    board = pcbnew.CreateEmptyBoard()
    board.GetDesignSettings().SetCopperLayerCount(2)
    return board


def add(board, ref, fpid, x, y, rot=0, value=""):
    lib, name = fpid.split(":")
    fp = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(ref)
    fp.SetValue(value or name)
    fp.SetPosition(mm(x, y))
    fp.SetOrientationDegrees(rot)
    fp.Reference().SetLayer(pcbnew.F_Fab)
    fp.Value().SetLayer(pcbnew.F_Fab)
    for g in list(fp.GraphicalItems()):      # some (the audio jack) cut their own board-edge notch
        if g.GetLayer() == pcbnew.Edge_Cuts:
            fp.Remove(g)
    board.Add(fp)
    return fp


def own_model(fp, step):
    """Swap a library footprint's 3D model (missing from KiCad's library) for one of ours."""
    fp.Models().clear()
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = "${KIPRJMOD}/../lms-esp32.3dshapes/" + step
    fp.Models().append(m)


def model_only(board, ref, step, x, y, rot=0):
    """A footprint with no pads that just carries a 3D model (for parts KiCad has no model of)."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.Reference().SetLayer(pcbnew.F_Fab)
    fp.Value().SetLayer(pcbnew.F_Fab)
    fp.SetPosition(mm(x, y))
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = "${KIPRJMOD}/../lms-esp32.3dshapes/" + step
    fp.Models().append(m)
    board.Add(fp)
    fp.SetOrientationDegrees(rot)
    return fp


def hole(board, ref, x, y, drill, ring):
    """Plated mounting hole: one through-hole pad."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.Reference().SetLayer(pcbnew.F_Fab)
    fp.Value().SetLayer(pcbnew.F_Fab)
    fp.SetPosition(mm(x, y))
    p = pcbnew.PAD(fp)
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetSize(mm(ring, ring))
    p.SetDrillSize(mm(drill, drill))
    p.SetLayerSet(pcbnew.PAD.PTHMask())
    p.SetPosition(mm(x, y))
    fp.Add(p)
    board.Add(fp)


def text(board, s, x, y, h=0.8, w=None, angle=0, bold=False, knockout=False, justify=None, layer=pcbnew.F_SilkS):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(mm(x, y))
    t.SetLayer(layer)
    t.SetMirrored(layer == pcbnew.B_SilkS)
    t.SetTextSize(mm(w or h, h))
    t.SetTextThickness(pcbnew.FromMM(h * (0.2 if bold else 0.14)))
    t.SetTextAngleDegrees(angle)
    t.SetIsKnockout(knockout)
    if justify == "left":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    elif justify == "right":
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
    board.Add(t)


def shape(board, kind, layer=pcbnew.F_SilkS, width=0.15, **pts):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(kind)
    for k, v in pts.items():
        getattr(s, "Set" + k)(mm(*v))
    s.SetLayer(layer)
    s.SetWidth(pcbnew.FromMM(width))
    board.Add(s)
    return s


def silk_box(board, x0, y0, x1, y1, width=0.15):
    shape(board, pcbnew.SHAPE_T_RECT, width=width, Start=(x0, y0), End=(x1, y1))


def silk_fill(board, x0, y0, x1, y1):
    s = shape(board, pcbnew.SHAPE_T_RECT, width=0, Start=(x0, y0), End=(x1, y1))
    s.SetFilled(True)


def outline(board, w, h, r):
    """Rounded-rectangle board edge."""
    e = pcbnew.Edge_Cuts
    for (x0, y0), (x1, y1) in (((r, 0), (w - r, 0)), ((w, r), (w, h - r)),
                               ((w - r, h), (r, h)), ((0, h - r), (0, r))):
        shape(board, pcbnew.SHAPE_T_SEGMENT, e, 0.1, Start=(x0, y0), End=(x1, y1))
    for cx, cy, sx, sy in ((r, r, 0, r), (w - r, r, w - r, 0), (w - r, h - r, w, h - r), (r, h - r, r, h)):
        shape(board, pcbnew.SHAPE_T_ARC, e, 0.1, Center=(cx, cy), Start=(sx, sy)).SetArcAngleAndEnd(
            pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T))


STACKUP = """(stackup
			(layer "F.SilkS" (type "Top Silk Screen") (color "White"))
			(layer "F.Mask" (type "Top Solder Mask") (color "Black") (thickness 0.01))
			(layer "F.Cu" (type "copper") (thickness 0.035))
			(layer "dielectric 1" (type "core") (thickness 1.51) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
			(layer "B.Cu" (type "copper") (thickness 0.035))
			(layer "B.Mask" (type "Bottom Solder Mask") (color "Black") (thickness 0.01))
			(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
			(copper_finish "ENIG")
			(dielectric_constraints no)
		)
		"""


def save(board, path, mask="Black"):
    """Save, then set the soldermask colour (white silkscreen) like the real boards
    (the 3D export takes its colours from the stackup, which pcbnew's Python can't set)."""
    board.Save(path)
    t = open(path).read()
    assert "(stackup" not in t
    t = t.replace("(setup\n\t\t", "(setup\n\t\t" + STACKUP.replace('"Black"', f'"{mask}"'), 1)
    assert "(stackup" in t
    open(path, "w").write(t)


# ---------------------------------------------------------------------------------------------
# LMS-ESP32 v2.0

W, H = 39.8, 55.8

# 14 x 2 header, right edge. Pin 1 (top of the inner column) is GND; pin 2 beside it is 3V3.
HDR_X, HDR_Y, P = 34.86, 11.5, 2.54
INNER = ["GND", "IO13", "IO14", "IO26", "IO32", "IO0", "GND", "GND", "GND", "5V", "IO20", "GND", "5V", "IO22"]
OUTER = ["3V3", "IO15", "IO12", "IO27", "IO33", "IO2", "3V3", "5V", "GND", "5V", "IO19", "GND", "5V", "IO21"]

# The HUB box header (2 x 3): rows top to bottom, left column then right.
HUB = [("IO8", "IO7"), ("3V3", "GND"), ("M+", "M-")]

# Display connector pins, top to bottom (from Anton's pinout table).
DISPLAY = ["26", "15", "3V3", "14", "12", "13", "27", "32", "GND", "33"]


def lms_esp32():
    board = new_board()
    outline(board, W, H, 2.4)
    for x in (3.9, 35.9):                        # LEGO 5 x 7 frame holes, 4.8 mm on 8 mm pitch
        for y in (3.9, 51.9):
            hole(board, "H", x, y, 4.85, 5.9)

    model_only(board, "U1", "ESP32-PICO-MINI-02.step", 0.0, 10.0)
    add(board, "U2", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm", 23.9, 19.2, 0, "CH340C")
    add(board, "U5", "Package_TO_SOT_SMD:SOT-223-3_TabPin2", 15.1, 36.0, -90, "AMS1117")
    add(board, "U3", "Package_TO_SOT_SMD:SOT-23-6", 21.8, 30.0, 90)
    add(board, "U4", "Package_TO_SOT_SMD:SOT-23-6", 21.8, 36.4, 90)
    add(board, "U6", "Package_TO_SOT_SMD:SOT-23-6", 20.0, 45.5, 90)
    add(board, "Q3", "Package_TO_SOT_SMD:SOT-23", 10.0, 30.2, 90)
    add(board, "Q4", "Package_TO_SOT_SMD:SOT-23", 2.9, 30.2, 90)
    own_model(add(board, "L1", "Inductor_SMD:L_Taiyo-Yuden_NR-40xx", 25.2, 44.4, 0, "2R2"), "Inductor_4.5x4.5.step")
    own_model(add(board, "D2", "LED_SMD:LED_WS2812B-2020_PLCC4_2.0x2.0mm", 10.3, 7.0, 0, "RGB"), "LED_2020_RGB.step")
    add(board, "D1", "LED_SMD:LED_0805_2012Metric", 3.1, 26.6, 0, "PWR")
    own_model(add(board, "SW1", "Button_Switch_SMD:SW_Push_1P1T-MP_NO_Horizontal_Alps_SKRTLAE010", 12.7, 1.9, 0, "RST"),
              "RST_Side_Switch.step")
    add(board, "J1", "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal", 24.35, 3.6, 0)
    add(board, "J2", "Connector_PinHeader_2.54mm:PinHeader_2x14_P2.54mm_Vertical", HDR_X, HDR_Y, 0)
    add(board, "J3", "Connector_IDC:IDC-Header_2x03_P2.54mm_Vertical", 3.7, 37.7, 0, "HUB")
    add(board, "J4", "Connector_JST:JST_SH_BM10B-SRSS-TB_1x10-1MP_P1.00mm_Vertical", 28.6, 32.8, 90, "DISPLAY")
    add(board, "J5", "Connector_JST:JST_PH_S4B-PH-K_1x04_P2.00mm_Horizontal", 29.2, 56.2, 180, "Grove")
    add(board, "J6", "Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal", 14.15, 53.6, 180, "Qwiic")

    passives = [   # (footprint size, x, y, rot) from the photo
        ("C_0603", 9.3, 2.8, 90), ("C_0402", 12.5, 6.7, 90), ("C_0402", 13.6, 6.7, 90),
        ("R_0402", 21.8, 8.7, 0), ("R_0402", 26.7, 8.7, 0), ("C_0805", 10.3, 24.4, 0),
        ("R_0402", 5.9, 26.2, 90), ("R_0402", 5.9, 28.7, 90), ("R_0402", 7.2, 28.7, 90),
        ("C_0805", 14.4, 29.7, 90), ("C_0805", 10.6, 34.4, 90), ("R_0402", 22.0, 27.2, 0),
        ("R_0402", 24.4, 28.5, 90), ("R_0402", 19.8, 30.5, 90), ("R_0402", 21.8, 34.0, 0),
        ("R_0402", 24.4, 36.0, 90), ("C_1206", 15.1, 40.0, 0), ("C_0805", 19.4, 40.9, 0),
        ("C_0805", 21.0, 42.3, 90), ("R_0402", 13.6, 44.7, 90), ("R_0402", 16.0, 44.0, 0),
        ("R_0402", 17.0, 45.1, 0), ("C_0805", 28.7, 45.3, 90), ("C_0805", 31.0, 45.3, 90),
    ]
    for i, (size, x, y, rot) in enumerate(passives):
        lib = "Capacitor_SMD" if size[0] == "C" else "Resistor_SMD"
        add(board, f"{size[0]}{i + 1}", f"{lib}:{size}_{dict(C_0402='1005', R_0402='1005', C_0603='1608', C_0805='2012', C_1206='3216')[size]}Metric", x, y, rot)

    # --- silkscreen, as printed ---
    lab = dict(h=0.78, w=0.62, angle=90)        # the header labels read bottom to top
    for i, s in enumerate(INNER):
        text(board, s, 33.15, HDR_Y + i * P, **lab)
    for i, s in enumerate(OUTER):
        text(board, s, 39.05, HDR_Y + i * P, **lab)
    silk_box(board, 33.75, HDR_Y - 1.4, 38.55, HDR_Y + 13 * P + 1.4)
    shape(board, pcbnew.SHAPE_T_CIRCLE, width=0.15, Center=(38.95, 9.4), End=(39.25, 9.4))   # pin-1 mark

    text(board, "RGB", 7.55, 7.0, 1.05, angle=90)
    text(board, "IO25", 8.65, 7.0, 0.6, angle=90)
    text(board, "RST", 17.7, 2.3, 1.05, angle=90)
    text(board, "PWR", 3.4, 24.6, 0.95, angle=180)
    shape(board, pcbnew.SHAPE_T_CIRCLE, width=0.2, Center=(5.6, 24.6), End=(5.75, 24.6))
    text(board, "HUB", 10.95, 39.6, 1.2, angle=90)
    text(board, "DISPLAY", 26.1, 32.8, 0.75, angle=90)
    for i, s in enumerate(DISPLAY):
        text(board, s, 30.9, 28.3 + i, 0.5, w=0.42, justify="left")
    # HUB pin key in its little box by the Qwiic socket
    silk_box(board, 7.05, 48.4, 9.0, 54.9)
    text(board, "M+ 3V3 IO8", 7.6, 51.65, 0.55, w=0.45, angle=90)
    text(board, "M- GND IO7", 8.45, 51.65, 0.55, w=0.45, angle=90)
    # Qwiic: G, 3 (3V3), IO5, IO4
    for x, s in zip((12.65, 13.65, 14.65, 15.65), ("G", "3", "IO5", "IO4")):
        text(board, s, x, 50.6, 0.6, w=0.5, angle=90)
    # Grove: GND VCC SDA/IO5 SCL/IO4
    gy = 48.2
    text(board, "GND", 23.2, gy, 0.75, w=0.62, angle=90)
    text(board, "VCC", 25.2, gy, 0.75, w=0.62, angle=90)
    text(board, "SDA", 26.8, gy, 0.75, w=0.62, angle=90)
    text(board, "IO5", 27.65, gy, 0.75, w=0.62, angle=90)
    text(board, "SCL", 28.8, gy, 0.75, w=0.62, angle=90)
    text(board, "IO4", 29.65, gy, 0.75, w=0.62, angle=90)
    silk_box(board, 21.9, 50.2, 30.8, 55.5)

    return board


# ---------------------------------------------------------------------------------------------
# DFRobot SEN0240 EMG sensor, signal board: 3.5 mm jack on the left edge, Gravity 3-pin PH2.0
# socket on the right edge. Its pins, top to bottom, are - (GND, black wire), + (VCC, red) and A
# (signal, blue): pin 1 is A, at the bottom.

EW, EH = 35.0, 22.0
PH_PINS = (12.2, 10.2, 8.2)          # y of the Gravity socket's pins 1 (A), 2 (+), 3 (-)


def emg():
    board = new_board()
    outline(board, EW, EH, 2.0)
    for y in (3.1, 18.9):
        hole(board, "H", 5.9, y, 3.0, 6.0)
    model_only(board, "J1", "Jack_3.5mm_EMG.step", 0.0, 9.4)          # electrodes plug in here
    add(board, "J2", "Connector_JST:JST_PH_S3B-PH-K_1x03_P2.00mm_Horizontal", 28.4, 12.2, 90, "Gravity")
    add(board, "U1", "Package_SO:MSOP-8_3x3mm_P0.65mm", 14.8, 15.0, 0)
    add(board, "U2", "Package_TO_SOT_SMD:SOT-23-6", 16.0, 4.6, 0)
    add(board, "U3", "Package_TO_SOT_SMD:SOT-23", 22.5, 17.2, 90)
    caps = ((22.6, 5.2, 0), (22.6, 7.0, 0), (22.6, 8.8, 0), (22.6, 10.6, 0), (22.6, 12.4, 0),
            (11.9, 1.6, 0), (11.9, 4.4, 90), (19.4, 9.6, 90), (10.6, 18.4, 0), (18.8, 15.2, 90))
    for i, (x, y, rot) in enumerate(caps):
        add(board, f"C{i + 1}", "Capacitor_SMD:C_0603_1608Metric", x, y, rot)
    for i, (x, y, rot) in enumerate(((22.6, 14.2, 0), (19.4, 12.0, 90), (12.4, 19.6, 0), (18.6, 19.2, 0))):
        add(board, f"R{i + 1}", "Resistor_SMD:R_0603_1608Metric", x, y, rot)

    # Gravity and A badges: knocked-out text on white blocks
    text(board, "Gravity", 18.4, 1.6, 1.3, w=1.05, bold=True, knockout=True)
    text(board, "A", 33.4, 18.6, 1.6, bold=True, knockout=True, angle=90)
    for y, s in ((PH_PINS[2], "-"), (PH_PINS[1], "+"), (PH_PINS[0], "A")):
        text(board, s, 25.0, y, 0.9, angle=90, bold=True)
    return board


# ---------------------------------------------------------------------------------------------
# MyoWare Muscle Sensor (Advancer Technologies AT-04-001, Pololu 2732), 53.3 x 20.8 mm, red.
# Frame as in Pololu's top-view photo, which shows the board upside down: the printing reads
# rotated 180 degrees. Left end: + - SIG pins (bottom to top) with a 1 x 3 male header soldered
# in for the Dupont leads; right end: GND SHID RAW; top edge: R E M electrode pads. The two
# electrode snaps (on the underside) and the reference lead are drawn in the viewer.

MW, MH = 53.3, 20.8
MYO_PINS = {"SIG": 8.0, "-": 10.54, "+": 13.08}       # x 1.25
MYO_SNAPS = ((10.7, 10.5), (41.6, 10.5))


def myoware():
    board = new_board()
    outline(board, MW, MH, 6.5)
    hole(board, "H", 4.0, 4.0, 3.2, 4.6)
    hole(board, "H", 48.3, 16.7, 3.2, 4.6)
    add(board, "J1", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", 1.25, 8.0, 0, "SIG - +")
    for i, y in enumerate((7.8, 10.34, 12.88)):            # GND SHID RAW
        hole(board, f"P{i}", 51.0, y, 1.0, 1.8)
    for i, x in enumerate((13.2, 15.74, 18.28)):           # M E R
        hole(board, f"E{i}", x, 1.4, 1.0, 1.8)
    for x, y in MYO_SNAPS:                                   # snap rivets through the board
        hole(board, "S", x, y, 3.0, 9.6)
    add(board, "U1", "Package_SO:MSOP-8_3x3mm_P0.65mm", 19.0, 10.0, 90, "INA")
    add(board, "U2", "Package_SO:MSOP-8_3x3mm_P0.65mm", 26.0, 10.2, 90)
    add(board, "U3", "Package_SO:TSSOP-14_4.4x5mm_P0.65mm", 33.3, 10.2, 90)
    add(board, "D1", "LED_SMD:LED_0603_1608Metric", 16.4, 8.4, 90, "SIG")
    add(board, "D2", "LED_SMD:LED_0603_1608Metric", 16.4, 12.5, 90, "PWR")
    add(board, "F1", "Fuse:Fuse_1206_3216Metric", 4.4, 15.9, 0, "F02")
    add(board, "SW1", "Button_Switch_SMD:SW_SPDT_PCM12", 10.7, 19.0, 180, "ON/OFF")
    own_model(add(board, "RV1", "Resistor_SMD:R_1206_3216Metric", 47.4, 4.6, 90, "Gain"), "Trimmer_3mm.step")
    caps = [(x, 4.0, 90) for x in (22.4, 24.2, 26.0, 27.8, 29.6, 31.4, 33.2, 35.0, 36.8)] + \
           [(x, 16.8, 90) for x in (19.6, 21.2, 22.8, 24.4, 26.0, 30.2, 31.8, 33.4)] + \
           [(11.2, 2.6, 0), (19.2, 4.4, 90), (37.9, 16.6, 90), (23.0, 13.8, 0)]
    for i, (x, y, rot) in enumerate(caps):
        add(board, f"C{i + 1}", "Capacitor_SMD:C_0603_1608Metric", x, y, rot)

    # printing, which reads upside down in this frame
    up = dict(angle=180, bold=True)
    text(board, "SIG", 4.4, MYO_PINS["SIG"], 1.0, **up)
    text(board, "-", 3.9, MYO_PINS["-"], 1.0, **up)
    text(board, "+", 3.9, MYO_PINS["+"], 1.0, **up)
    for y, s in ((7.8, "GND"), (10.34, "SHID"), (12.88, "RAW")):
        text(board, s, 47.9, y, 0.9, w=0.8, **up)
    for x, s in ((13.2, "M"), (15.74, "E"), (18.28, "R")):
        text(board, s, x, 3.3, 0.9, **up)
    for x, y, s in ((9.0, 1.8, "LED"), (16.3, 6.4, "SIG"), (16.4, 14.6, "PWR"), (16.4, 16.9, "LED"),
                    (6.4, 19.0, "NC"), (14.6, 18.7, "OFF"), (44.6, 4.6, "Gain")):
        text(board, s, x, y, 0.6, w=0.5, angle=180)
    # underside: the maker's name, the MyoWare flexed-arm triangle (the photo's bottom view is
    # this frame flipped top to bottom)
    bs = dict(layer=pcbnew.B_SilkS, angle=180)
    text(board, "Advancer", 23.8, 18.4, 1.7, bold=True, **bs)
    text(board, "Technologies", 23.8, 16.4, 1.1, **bs)
    text(board, "MyoWare", 26.0, 4.4, 1.3, **bs)
    for (x0, y0), (x1, y1) in (((24.1, 14.8), (20.8, 6.6)), ((20.8, 6.6), (27.4, 6.6)), ((27.4, 6.6), (24.1, 14.8))):
        shape(board, pcbnew.SHAPE_T_SEGMENT, pcbnew.B_SilkS, 0.5, Start=(x0, y0), End=(x1, y1))
    return board


if __name__ == "__main__":
    for name, fn, mask in (("lms-esp32", lms_esp32, "Black"), ("emg", emg, "Black"), ("myoware", myoware, "Red")):
        path = os.path.join(HERE, name, name + ".kicad_pcb")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        save(fn(), path, mask)
        print("wrote", os.path.relpath(path, HERE))
