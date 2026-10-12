# Test board: the LEGODISCO firmware on a XIAO ESP32S3 (e.g. a spare one), with
# the hub and muscle sensor simulated (config.py sets SIMULATE = True) so the
# whole site can be exercised with no arm attached. Networking and the web UI
# are the same as the real board; only the chip target and this note differ.
# PSRAM and Bluetooth are left off, as on the real board.
set(IDF_TARGET esp32s3)

set(SDKCONFIG_DEFAULTS
    boards/sdkconfig.base
    boards/sdkconfig.240mhz
    boards/sdkconfig.flash_qio_80m
    ${MICROPY_BOARD_DIR}/sdkconfig.board
    ${MICROPY_BOARD_DIR}/../sdkconfig.fast
)

set(MICROPY_FROZEN_MANIFEST ${MICROPY_BOARD_DIR}/manifest.py)
