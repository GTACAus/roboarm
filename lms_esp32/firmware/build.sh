#!/usr/bin/env bash
# Build the LMS-ESP32 firmware: MicroPython + the repeater C module + the frozen arm app.
#
#   firmware/build.sh            -> firmware/dist/legodisco.bin             (the one to use)
#   firmware/build.sh PSRAM      -> firmware/dist/legodisco-psram.bin       (fallback, see README)
#   firmware/build.sh xiao-test  -> firmware/dist/legodisco-xiao-test.bin   (XIAO ESP32S3 test board)
#
# First run downloads MicroPython and ESP-IDF and installs the Xtensa toolchain
# (~3 GB, into $LEGODISCO_DEPS (default ~/esp/legodisco-deps) and ~/.espressif).
set -euo pipefail

MPY_VERSION=v1.29.0
IDF_VERSION=v5.5.2   # recommended by MicroPython v1.29

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEPS="${LEGODISCO_DEPS:-$HOME/esp/legodisco-deps}"

# Pick the board (and LEGODISCO variant) from the first argument.
TARGET="${1:-}"
VARIANT=""
case "$TARGET" in
    xiao-test) BOARD=XIAO_S3_TEST; OUT_NAME=legodisco-xiao-test ;;
    "")        BOARD=LEGODISCO;    OUT_NAME=legodisco ;;
    *)         BOARD=LEGODISCO;    VARIANT="$TARGET"
               OUT_NAME="legodisco-$(echo "$TARGET" | tr '[:upper:]' '[:lower:]')" ;;
esac
BOARD_DIR="$ROOT/firmware/board/$BOARD"
OUT="$ROOT/firmware/dist/$OUT_NAME.bin"

mkdir -p "$DEPS" "$ROOT/firmware/dist"
if [ ! -d "$DEPS/micropython" ]; then
    git clone --depth 1 --branch "$MPY_VERSION" https://github.com/micropython/micropython.git "$DEPS/micropython"
fi
if [ ! -d "$DEPS/esp-idf" ]; then
    git clone --depth 1 --branch "$IDF_VERSION" --recursive --shallow-submodules \
        https://github.com/espressif/esp-idf.git "$DEPS/esp-idf"
    # esp32 (WROVER) and esp32s3 (XIAO test) share the Xtensa toolchain
    "$DEPS/esp-idf/install.sh" esp32 esp32s3
    # Optional on macOS in ESP-IDF's installer, but required here
    python3 "$DEPS/esp-idf/tools/idf_tools.py" install cmake ninja
fi

set +u   # export.sh reads unset variables
# shellcheck disable=SC1091
source "$DEPS/esp-idf/export.sh" > /dev/null
set -u

python3 "$ROOT/tools/make_www.py"
PORT="$DEPS/micropython/ports/esp32"
make -C "$PORT" submodules BOARD_DIR="$BOARD_DIR" > /dev/null
make -C "$DEPS/micropython/mpy-cross" > /dev/null
# MicroPython's default build folder: passing BUILD= would leak into its
# mpy-cross sub-build and mix the two builds' generated headers.
BUILD="$PORT/build-$BOARD${VARIANT:+-$VARIANT}"
# Regenerate the ESP-IDF config every time: an old one would silently ignore
# edits to the board's sdkconfig files.
rm -f "$BUILD/sdkconfig"
make -C "$PORT" BOARD_DIR="$BOARD_DIR" ${VARIANT:+BOARD_VARIANT=$VARIANT} \
    USER_C_MODULES="$ROOT/firmware/modules/micropython.cmake" \
    -j"$(sysctl -n hw.ncpu 2> /dev/null || nproc)"

cp "$BUILD/firmware.bin" "$OUT"
echo "Built $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
