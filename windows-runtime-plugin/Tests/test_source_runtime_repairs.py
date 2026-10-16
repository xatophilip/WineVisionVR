#!/usr/bin/env python3
"""Compile/run patched JIT, Apple battery and process-alias routines on macOS.

No Wine guest or headset is started. Pass the locked Madeira checkout with
--source, or use third-party/madeira. Dependencies are copied to a temporary
overlay; the vendor checkout remains untouched.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def run_probe(work, name, source, *, cpp=False, frameworks=()):
    path = work / (name + (".cpp" if cpp else ".c"))
    path.write_text(source)
    command = ["xcrun", "--sdk", "macosx", "clang++" if cpp else "clang",
               "-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    if cpp:
        command += ["-std=c++20"]
    for framework in frameworks:
        command += ["-framework", framework]
    subprocess.run(command + [str(path), "-o", str(work / name)], check=True)
    subprocess.run([str(work / name)], check=True)


JIT_HARNESS = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <sys/mman.h>
using mach_port_t = unsigned;
using vm_address_t = uintptr_t;
using vm_prot_t = int;
using kern_return_t = int;
constexpr int KERN_SUCCESS=0, VM_FLAGS_ANYWHERE=1, VM_INHERIT_NONE=0;
constexpr int VM_PROT_READ=1, VM_PROT_WRITE=2;
constexpr bool FALSE=false;
namespace FEXCore { namespace DualMap { int64_t WriteOffset=0; } }
static bool debugged=true;
static int allocation_calls=0, remap_calls=0, protect_calls=0;
static size_t allocated_size=0, remapped_size=0, protected_size=0;
static void fex_log(const char*, ...) {}
static bool jit_check_debugged() { return debugged; }
static unsigned mach_task_self() { return 1; }
static const char* mach_error_string(int) { return "mock error"; }
static void* jit26_prepare_region(void*, size_t size) {
    ++allocation_calls; allocated_size=size;
    void *p=mmap(nullptr,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
    assert(p != MAP_FAILED); return p;
}
static int vm_remap(unsigned, uintptr_t *rw, size_t size, int, int,
                    unsigned, uintptr_t rx, bool, int*, int*, int) {
    ++remap_calls; remapped_size=size; *rw=rx; return 0;
}
static int vm_protect(unsigned, uintptr_t, size_t size, bool, int protection) {
    ++protect_calls; protected_size=size;
    assert(protection==(VM_PROT_READ|VM_PROT_WRITE)); return 0;
}
static int vm_deallocate(unsigned, uintptr_t addr, size_t size) {
    return munmap(reinterpret_cast<void*>(addr),size);
}
'''
JIT_MAIN = r'''
int main() {
    constexpr size_t expected=640ULL*1024*1024;
    debugged=false;
    assert(!jit_pool_init()); assert(allocation_calls==0);
    debugged=true;
    assert(jit_pool_init());
    assert(allocated_size==expected && remapped_size==expected && protected_size==expected);
    assert(g_jit_pool_size==expected);
    uint64_t rx=0,rw=0,size=0;
    assert(fex_get_jit_pool_info(&rx,&rw,&size));
    assert(rx==reinterpret_cast<uintptr_t>(g_jit_rx_base) && rw==rx && size==expected);
    assert(!fex_get_jit_pool_info(nullptr,&rw,&size));
    assert(jit_pool_init());
    assert(allocation_calls==1 && remap_calls==1 && protect_calls==1);
    assert(jit_pool_alloc(1)==g_jit_rx_base);
    assert(g_jit_pool_offset==JIT_PAGE_SIZE);
    assert(jit_pool_alloc(expected-JIT_PAGE_SIZE)!=MAP_FAILED);
    assert(g_jit_pool_offset==expected);
    assert(jit_pool_alloc(1)==MAP_FAILED);
    assert(is_in_jit_pool(reinterpret_cast<void*>(rx+expected-1)));
    assert(!is_in_jit_pool(reinterpret_cast<void*>(rx+expected)));
    munmap(g_jit_rx_base,expected);
    puts("PASS: 640 MiB debugger/remap/protection/export size, single initialization and allocator bounds");
}
'''
BATTERY_HARNESS = r'''
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/ps/IOPSKeys.h>
#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef int BOOL, NTSTATUS;
typedef uint64_t ULONGLONG;
typedef int64_t LONGLONG;
#define TRUE 1
#define STATUS_SUCCESS 0
#define STATUS_NOT_SUPPORTED 1
#define STATUS_ACCESS_DENIED 2
typedef struct {
    unsigned char AcOnLine, BatteryPresent, Charging, Discharging;
    uint32_t MaxCapacity, RemainingCapacity, Rate, EstimatedTime, DefaultAlert1, DefaultAlert2;
} SYSTEM_BATTERY_STATE;
static CFMutableDictionaryRef blob, battery;
static CFArrayRef sources;
static int missing_blob, missing_sources;
static CFTypeRef IOPSCopyPowerSourcesInfo(void) {
    return missing_blob ? NULL : CFRetain(blob);
}
static CFArrayRef IOPSCopyPowerSourcesList(CFTypeRef b) {
    assert(b==blob); return missing_sources ? NULL : (CFArrayRef)CFRetain(sources);
}
static CFDictionaryRef IOPSGetPowerSourceDescription(CFTypeRef b, CFTypeRef item) {
    assert(b==blob && CFGetRetainCount(blob)==2); return item;
}
static const void *checked_property(CFDictionaryRef dictionary, const void *key) {
    /* IOPS returns a dictionary borrowed from its blob. */
    assert(CFGetRetainCount(blob)==2);
    return CFDictionaryGetValue(dictionary,key);
}
#define CFDictionaryGetValue checked_property
'''
BATTERY_MAIN = r'''
#undef CFDictionaryGetValue
static void number(CFStringRef key, int32_t value) {
    CFNumberRef n=CFNumberCreate(NULL,kCFNumberIntType,&value);
    CFDictionarySetValue(battery,key,n); CFRelease(n);
}
static void reset(void) {
    CFDictionaryRemoveAllValues(battery);
    CFDictionarySetValue(battery,CFSTR(kIOPSTransportTypeKey),CFSTR(kIOPSInternalType));
    CFDictionarySetValue(battery,CFSTR(kIOPSIsPresentKey),kCFBooleanTrue);
    CFDictionarySetValue(battery,CFSTR(kIOPSIsChargingKey),kCFBooleanFalse);
    CFDictionarySetValue(battery,CFSTR(kIOPSPowerSourceStateKey),CFSTR(kIOPSBatteryPowerValue));
    number(CFSTR(kIOPSMaxCapacityKey),5000);
    number(CFSTR(kIOPSCurrentCapacityKey),2500);
    number(CFSTR(kIOPSVoltageKey),12000);
    number(CFSTR(kIOPSCurrentKey),-1000);
    number(CFSTR(kIOPSTimeToEmptyKey),30);
    missing_blob=missing_sources=0;
}
static SYSTEM_BATTERY_STATE check(NTSTATUS expected) {
    SYSTEM_BATTERY_STATE state={0};
    assert(fill_battery_state(&state)==expected);
    assert(CFGetRetainCount(blob)==1 && CFGetRetainCount(sources)==1);
    return state;
}
int main(void) {
    blob=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    battery=CFDictionaryCreateMutable(NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
    const void *items[]={battery};
    sources=CFArrayCreate(NULL,items,1,&kCFTypeArrayCallBacks);
    reset();
    SYSTEM_BATTERY_STATE state=check(STATUS_SUCCESS);
    assert(state.BatteryPresent && state.Discharging && !state.AcOnLine);
    assert(state.MaxCapacity==60000000 && state.RemainingCapacity==30000000);
    assert(state.DefaultAlert1==3000000 && state.DefaultAlert2==20000000);
    assert((int32_t)state.Rate==-12000 && state.EstimatedTime==1800);
    const CFStringRef required[]={CFSTR(kIOPSTransportTypeKey),CFSTR(kIOPSIsPresentKey),
        CFSTR(kIOPSIsChargingKey),CFSTR(kIOPSPowerSourceStateKey),
        CFSTR(kIOPSMaxCapacityKey),CFSTR(kIOPSCurrentCapacityKey)};
    for(unsigned i=0;i<sizeof(required)/sizeof(*required);++i) {
        reset(); CFDictionaryRemoveValue(battery,required[i]); check(STATUS_NOT_SUPPORTED);
        reset(); CFDictionarySetValue(battery,required[i],kCFNull); check(STATUS_NOT_SUPPORTED);
    }
    const CFStringRef optional[]={CFSTR(kIOPSVoltageKey),CFSTR(kIOPSCurrentKey),CFSTR(kIOPSTimeToEmptyKey)};
    for(unsigned i=0;i<sizeof(optional)/sizeof(*optional);++i) {
        reset(); CFDictionarySetValue(battery,optional[i],kCFNull); check(STATUS_NOT_SUPPORTED);
        reset(); CFDictionaryRemoveValue(battery,optional[i]); check(STATUS_SUCCESS);
    }
    reset(); missing_blob=1; check(STATUS_ACCESS_DENIED);
    reset(); missing_sources=1; check(STATUS_ACCESS_DENIED);
    reset(); CFDictionarySetValue(battery,CFSTR(kIOPSIsPresentKey),kCFBooleanFalse);
    state=check(STATUS_SUCCESS); assert(!state.BatteryPresent && state.AcOnLine);
    reset(); CFDictionarySetValue(battery,CFSTR(kIOPSTransportTypeKey),CFSTR("USB"));
    state=check(STATUS_SUCCESS); assert(!state.BatteryPresent && state.AcOnLine);
    reset(); number(CFSTR(kIOPSVoltageKey),0); check(STATUS_NOT_SUPPORTED);
    reset(); number(CFSTR(kIOPSMaxCapacityKey),INT_MAX); check(STATUS_NOT_SUPPORTED);
    reset(); number(CFSTR(kIOPSCurrentCapacityKey),-1); check(STATUS_NOT_SUPPORTED);
    reset(); number(CFSTR(kIOPSCurrentKey),INT_MAX); check(STATUS_NOT_SUPPORTED);
    reset(); number(CFSTR(kIOPSTimeToEmptyKey),INT_MAX); check(STATUS_NOT_SUPPORTED);
    CFRelease(sources); CFRelease(battery); CFRelease(blob);
    puts("PASS: real CoreFoundation battery queries, missing/wrong-typed keys, blob lifetime, error cleanup and arithmetic bounds");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "third-party/madeira")
    args = parser.parse_args()
    files = ("app/Madeira/FEXBridge.mm", "app/Madeira/FEXBridge.h",
             "app/Madeira/WineProcessBridge.m", "app/Madeira/WineProcessBridge.h",
             "wine/dlls/ntdll/unix/system.c")
    with tempfile.TemporaryDirectory(prefix="wvr-source-repairs-") as temporary:
        work = Path(temporary)
        for relative in files:
            path = work / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.source / relative, path)
        subprocess.run(["git", "init", "--quiet"], cwd=work, check=True)
        for name in ("0001-Madeira-launch-profile.patch", "0006-madeira-visionos-jit-pool.patch",
                     "0007-wine-apple-battery-properties.patch"):
            subprocess.run(["git", "apply", str(ROOT / "windows-runtime-plugin/patches" / name)],
                           cwd=work, check=True)
        fex = (work / files[0]).read_text()
        pool = fex[fex.index("static constexpr size_t JIT_POOL_SIZE"):
                   fex.index("// Custom mmap/munmap hooks")]
        export_start = fex.index('extern "C" bool fex_get_jit_pool_info')
        export = fex[export_start:fex.index("\n}", export_start) + 2]
        run_probe(work, "jit", JIT_HARNESS + pool + export + JIT_MAIN, cpp=True)
        system = (work / files[-1]).read_text()
        battery_start = system.index("static BOOL apple_battery_number")
        battery = system[battery_start:system.index("#elif defined(__FreeBSD__)", battery_start)]
        run_probe(work, "battery", BATTERY_HARNESS + battery + BATTERY_MAIN,
                  frameworks=("CoreFoundation",))

        # The upstream regression extracts the patched production alias routing
        # and runs both legacy and per-process modes with ASan/UBSan.
        for relative in ("build/ntdll-unix/virtual_ios.c",
                         "tests/host/check-child-ntdll-alias.py"):
            path = work / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.source / relative, path)
        subprocess.run(["git", "apply", str(ROOT / "windows-runtime-plugin/patches/0009-wine-process-jit-aliases.patch")],
                       cwd=work, check=True)
        subprocess.run(["python3", str(work / "tests/host/check-child-ntdll-alias.py")], check=True)


if __name__ == "__main__":
    main()
