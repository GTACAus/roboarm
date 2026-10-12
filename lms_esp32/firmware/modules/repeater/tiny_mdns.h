#pragma once

#include <stdint.h>

// Answer "<host>.local" with `ip` (network byte order) on the interface that
// owns that address. Call once that interface is up.
void tiny_mdns_start(const char *host, uint32_t ip);
