# Fallback build that uses the WROVER's PSRAM (rev 3 chips only); see sdkconfig.psram.
list(APPEND SDKCONFIG_DEFAULTS ${MICROPY_BOARD_DIR}/sdkconfig.psram)
list(APPEND MICROPY_DEF_BOARD MICROPY_HW_BOARD_NAME="LMS-ESP32 GTAC arm (PSRAM)")
