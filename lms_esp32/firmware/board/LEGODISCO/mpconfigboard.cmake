# LMS-ESP32 (ESP32-WROVER) running the GTAC robot arm with internet sharing.
#
# PSRAM is deliberately not used: on the original ESP32 it needs a compiler
# workaround that slows all code and squeezes the Wi-Fi fast paths out of
# IRAM, and it would move the Python heap to slow external RAM. See README.
# BOARD_VARIANT=PSRAM builds a fallback that uses it (for rev 3 chips only).
set(IDF_TARGET esp32)

set(SDKCONFIG_DEFAULTS
    boards/sdkconfig.base
    ${MICROPY_BOARD_DIR}/sdkconfig.board
    ${MICROPY_BOARD_DIR}/../sdkconfig.fast
)

set(MICROPY_FROZEN_MANIFEST ${MICROPY_BOARD_DIR}/manifest.py)
