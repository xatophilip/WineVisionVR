// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef WINDOWS_VR_WOW64_TRANSPORT_H
#define WINDOWS_VR_WOW64_TRANSPORT_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* Madeira's x86 addresses live in [base, base + 4GiB). Object handles and GPU
 * addresses are opaque 64-bit values and MUST NOT use these CPU-pointer APIs.
 * The outer unix-call record has already been translated by Wine. */
static inline uintptr_t wvr_wow64_guest_to_host(uintptr_t base, uint32_t guest) {
    return guest ? base + (uintptr_t)guest : 0;
}
/* Some explicitly 64-bit CPU-pointer fields also carry native compiler data.
 * On Apple arm64 a host pointer cannot exist below the 4GiB PAGEZERO. */
static inline uintptr_t wvr_wow64_wide_to_host(uintptr_t base, uint64_t value) {
    return value >= UINT64_C(0x100000000) ? (uintptr_t)value :
        wvr_wow64_guest_to_host(base, (uint32_t)value);
}
static inline bool wvr_wow64_host_to_guest(uintptr_t base, uintptr_t host, uint32_t *guest) {
    if (!host) { *guest = 0; return true; }
    if (host < base || host - base > UINT32_MAX) return false;
    *guest = (uint32_t)(host - base);
    return *guest != 0;
}
#endif
