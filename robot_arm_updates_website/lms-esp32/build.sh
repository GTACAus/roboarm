#!/bin/sh
# Rebuild every model the assembly viewer loads (out/).
#   ./build.sh [path/to/LMS_ESP32_case_GTAC.stl]
set -e
cd "$(dirname "$0")"
KICAD=/Applications/KiCad/KiCad.app/Contents
python3 gen_models.py
"$KICAD/Frameworks/Python.framework/Versions/Current/bin/python3" gen_pcb.py 2>&1 | grep -v wxApp
for n in lms-esp32 emg myoware; do
  "$KICAD/MacOS/kicad-cli" pcb export glb -f --include-silkscreen --include-soldermask --include-pads \
    -o "out/$n.glb" "$n/$n.kicad_pcb" | grep -v '^$'
done
python3 case.py "$@"
python3 ldraw.py           # SPIKE hub; reads the LDraw files cached in ldraw/
python3 spike_box.py       # SPIKE Prime storage box: tub and lid
