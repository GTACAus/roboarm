#ifndef MICROPY_HW_BOARD_NAME
#define MICROPY_HW_BOARD_NAME "LMS-ESP32 GTAC arm"
#endif
#define MICROPY_HW_MCU_NAME "ESP32"

// Not used by the arm: dropping Bluetooth frees a large block of internal RAM
// for Python and the Wi-Fi / NAT buffers.
#define MICROPY_PY_BLUETOOTH (0)

// gtac.local comes from the repeater module's own responder instead, which
// answers IPv6 lookups with "none" so iPads don't stall seconds waiting.
#define MICROPY_HW_ENABLE_MDNS_QUERIES (0)
#define MICROPY_HW_ENABLE_MDNS_RESPONDER (0)
