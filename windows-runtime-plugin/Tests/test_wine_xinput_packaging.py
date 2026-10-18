#!/usr/bin/env python3
"""Verify genuine ARM64EC XInput packaging and production no-controller semantics.

Compile production entry points with ASan/UBSan. Host-pad/HID discovery and
LoadLibrary/GetProcAddress are explicit mocked boundaries: this is not execution
of ARM64EC Wine, physical controller input, or game compatibility.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MODULES = ("xinput1_3", "xinput1_4", "xinput9_1_0")
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--runtime-source", required=True, type=Path)
p.add_argument("--resource-source", type=Path)
p.add_argument("--build", required=True, type=Path)
a = p.parse_args()
a.build.mkdir(parents=True, exist_ok=False)
source = a.runtime_source.resolve()
resources = (a.resource_source or source/"app/Madeira").resolve()
recipe = (ROOT/"windows-vr-tools/build_wine_guest_resources.sh").read_text()
build_script = source/"build/wine-pe/build-modules.sh"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def function(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    end, depth = brace + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]

# Execute the normal recipe's actual module invocation and pinned module
# target/copy loop. Only make/strip are mocked at the compilation boundary.
call = recipe[recipe.index('JOBS="${AVPPLAY_BUILD_JOBS:-4}" bash "$runtime_root/build/wine-pe/build-modules.sh"'):
              recipe.index("# Build the genuine pinned Wine programs")]
targets = call.replace("\\\n", " ").split()[3:]
for name in MODULES:
    assert name in targets, f"normal recipe omits {name}"
loop = a.build/"production-loop"
(loop/"build/wine-pe").mkdir(parents=True)
(loop/"wine/build-arm64ec").mkdir(parents=True)
(loop/"wine/build-arm64ec/config.status").touch()
shutil.copy2(build_script, loop/"build/wine-pe/build-modules.sh")
tc = loop/"toolchains/llvm-mingw-20260421-ucrt-macos-universal/bin"
tc.mkdir(parents=True)
for name in targets:
    directory = loop/"wine/dlls"/name
    directory.mkdir(parents=True)
    shutil.copy2(source/"wine/dlls"/name/"Makefile.in", directory/"Makefile.in")
(tc/"make").write_text("""#!/usr/bin/env python3
import pathlib,sys
args=sys.argv[1:]; root=pathlib.Path(args[args.index('-C')+1])
for target in args[args.index('-C')+2:]:
 if target.startswith('-'): continue
 path=root/target; path.parent.mkdir(parents=True,exist_ok=True)
 path.write_bytes(('actual-target:'+target+'\\n').encode())
""")
(tc/"arm64ec-w64-mingw32-strip").write_text('#!/bin/sh\n[ "$1" = --strip-debug ]\n')
for path in tc.iterdir():
    path.chmod(0o755)
subprocess.run(["bash", "-c", 'set -euo pipefail\nruntime_root="$1"\nAVPPLAY_BUILD_JOBS=2\n'+call,
                "xinput-contract", str(loop.resolve())], check=True,
               stdout=(a.build/"production-loop.log").open("w"), stderr=subprocess.STDOUT)
for name in MODULES:
    target = f"dlls/{name}/arm64ec-windows/{name}.dll"
    assert (loop/"app/Madeira/arm64ec-windows"/(name+".dll")).read_bytes() == (
        "actual-target:"+target+"\n").encode()

sys.path.insert(0, str(ROOT/"windows-vr-tools"))
import stage_resources as stage
import resource_receipt as receipt
import verify_wine_imports as imports
expected = {name+".dll" for name in MODULES}
assert expected <= stage.ARM64EC_REQUIRED_BUILTINS
for name in expected:
    assert stage.is_arm64ec_pe(resources/"arm64ec-windows"/name)
stage.validate_wine_resources(resources, enable_x86=True)
copied = a.build/"production-staging"
copied.mkdir()
stage.copy_builtins(resources, copied, enable_x86=True)
ledger = receipt.guest_resource_files(resources, enable_x86=True)
hashes = {}
for name in expected:
    relative = "arm64ec-windows/"+name
    hashes[name] = sha(resources/relative)
    assert sha(copied/relative) == hashes[name] == ledger[relative]

# A missing DLL must fail both the source validator and actual staged-copy
# validator. Remove only scratch copies and restore each, never alter inputs.
for name in expected:
    path = copied/"arm64ec-windows"/name
    saved = path.read_bytes()
    path.unlink()
    try:
        try:
            stage.validate_wine_resources(copied, enable_x86=True)
        except SystemExit as error:
            assert name in str(error), error
        else:
            raise AssertionError("source validator accepted missing "+name)
        negative = a.build/("missing-"+name)
        negative.mkdir()
        try:
            stage.copy_builtins(copied, negative, enable_x86=True)
        except SystemExit as error:
            assert name in str(error), error
        else:
            raise AssertionError("staging accepted missing "+name)
    finally:
        path.write_bytes(saved)

# Real PE imports/forwarders plus explicit dynamic fallback and export checks.
tc = Path(os.environ["AVPPLAY_LLVM_MINGW_ROOT"])/"bin"
tools = {name: str(tc/name) for name in ("llvm-readobj", "llvm-objdump")}
farm = resources/"arm64ec-windows"
files = sorted(path for path in farm.iterdir() if path.suffix.lower() in (".dll", ".exe", ".drv"))
assert not imports.inspect_closure(files, tools)
details = {}
for name in expected:
    path = farm/name
    output = subprocess.check_output([tools["llvm-readobj"], "--coff-imports", "--coff-exports", str(path)], text=True)
    (a.build/(name+".pe.txt")).write_text(output)
    exports = set(re.findall(r"^  Name: (XInput\w+)$", output, re.M))
    assert {"XInputGetState", "XInputGetCapabilities", "XInputSetState"} <= exports
    details[name] = {"sha256": sha(path), "exports": sorted(exports)}
main = (source/"wine/dlls/xinput1_3/main.c").read_text()
fallback = (source/"wine/dlls/xinput9_1_0/main.c").read_text()
initializer = function(fallback, "static BOOL WINAPI init_xinput1_4_funcs(")
assert 'LoadLibraryExW(L"xinput1_4.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32)' in initializer
assert "xinput1_4.dll" in expected  # Dynamic dependency is absent from static PE imports.
assert 'PARENTSRC = ../xinput1_3' in (source/"wine/dlls/xinput1_4/Makefile.in").read_text()

prelude = r"""
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
typedef uint32_t DWORD;
typedef int BOOL;
typedef void *HMODULE;
typedef struct { int ran; } INIT_ONCE;
typedef INIT_ONCE *PINIT_ONCE;
typedef struct { uint16_t wButtons; } XINPUT_GAMEPAD;
typedef struct { DWORD dwPacketNumber; XINPUT_GAMEPAD Gamepad; } XINPUT_STATE;
typedef struct { DWORD unused; } XINPUT_CAPABILITIES;
typedef struct { uint16_t left,right; } XINPUT_VIBRATION;
#define WINAPI
#define DECLSPEC_HOTPATCH
#define TRUE 1
#define FALSE 0
#define TRACE(...) ((void)0)
#define ERR(...) ((void)0)
#define ERROR_SUCCESS 0
#define ERROR_BAD_ARGUMENTS 160
#define ERROR_DEVICE_NOT_CONNECTED 1167
#define XUSER_MAX_COUNT 4
#define XINPUT_GAMEPAD_GUIDE 0x0400
#define LOAD_LIBRARY_SEARCH_SYSTEM32 0x800
static int controllers[4], updates, state_calls, library_calls, load_ok, export_ok;
static int host_enabled = TRUE;
#define NtUserGamepadOp_State 0
static BOOL NtUserGetGamepadState(DWORD i,DWORD op,XINPUT_STATE *s) {
 (void)i;(void)op;(void)s;return FALSE; /* no platform controller */
}
static int InterlockedCompareExchange(int *p,int a,int b) { (void)a;(void)b;return *p; }
static void start_update_thread(void) { ++updates; }
static BOOL controller_lock(int *c) { (void)c; return FALSE; }
static void controller_unlock(int *c) { (void)c; assert(0); }
"""
# Only the unused successful HID copy needs the real member name.
prelude = prelude.replace("static int controllers[4], updates", "static struct { XINPUT_STATE state; } controllers[4];\nstatic int updates")
prelude = prelude.replace("controller_lock(int *c)", "controller_lock(void *c)").replace(
    "controller_unlock(int *c)", "controller_unlock(void *c)")
base = function(main, "static BOOL host_pad_state(")+"\n"+function(main, "static DWORD xinput_get_state(")+"\n"+function(
    main, "DWORD WINAPI DECLSPEC_HOTPATCH XInputGetState(")
boundary = r"""
static INIT_ONCE init_xinput1_4_once;
static HMODULE xinput1_4;
static DWORD (*pXInputGetCapabilities)(DWORD,DWORD,XINPUT_CAPABILITIES*);
static DWORD (*pXInputGetState)(DWORD,XINPUT_STATE*);
static DWORD (*pXInputSetState)(DWORD,XINPUT_VIBRATION*);
static DWORD state_probe(DWORD i,XINPUT_STATE *s) { ++state_calls;return XInputGetState(i,s); }
static DWORD caps_probe(DWORD i,DWORD f,XINPUT_CAPABILITIES *c) {(void)i;(void)f;(void)c;return 1167;}
static DWORD set_probe(DWORD i,XINPUT_VIBRATION *v) {(void)i;(void)v;return 1167;}
static HMODULE LoadLibraryExW(const wchar_t *name,void *file,DWORD flags) {
 ++library_calls;assert(!wcscmp(name,L"xinput1_4.dll"));assert(!file);assert(flags==0x800);
 return load_ok ? (void*)1 : NULL;
}
static void *GetProcAddress(HMODULE h,const char *name) {
 assert(h==(void*)1);
 if (!export_ok) return NULL;
 if (!strcmp(name,"XInputGetState")) return (void*)state_probe;
 if (!strcmp(name,"XInputGetCapabilities")) return (void*)caps_probe;
 if (!strcmp(name,"XInputSetState")) return (void*)set_probe;
 assert(0);return NULL;
}
static void InitOnceExecuteOnce(INIT_ONCE *once,BOOL (*fn)(INIT_ONCE*,void*,void**),void *p,void **ctx) {
 if (!once->ran) {assert(fn(once,p,ctx));once->ran=1;}
}
"""
wrapper = function(fallback, "DWORD WINAPI DECLSPEC_HOTPATCH XInputGetState(").replace(
    "XInputGetState(", "fallback_get_state(", 1)
checks = r"""
int main(void) {
 XINPUT_STATE state={0};
 assert(XInputGetState(0,NULL)==160);assert(XInputGetState(4,&state)==160);
 for(DWORD i=0;i<4;++i) assert(XInputGetState(i,&state)==1167);
 assert(updates==4);assert(state.dwPacketNumber==0 && state.Gamepad.wButtons==0);
 /* Loader unavailable: no success or fabricated controller is reported. */
 assert(fallback_get_state(0,&state)==1167);assert(library_calls==1);
 assert(fallback_get_state(0,&state)==1167);assert(library_calls==1);
 init_xinput1_4_once.ran=0;load_ok=1;export_ok=0;
 assert(fallback_get_state(0,&state)==1167);
 init_xinput1_4_once.ran=0;export_ok=1;
 for(DWORD i=0;i<4;++i) assert(fallback_get_state(i,&state)==1167);
 assert(state_calls==4);assert(library_calls==3);
 assert(fallback_get_state(0,NULL)==160);assert(fallback_get_state(4,&state)==160);
 puts("PASS: production XInput no-controller/error returns and dynamic system32 fallback");
 return 0;
}
"""
unit = a.build/"production-xinput.c"
unit.write_text(prelude+"\n"+base+"\n"+boundary+"\n"+initializer+"\n"+wrapper+"\n"+checks)
binary = a.build/"production-xinput"
command = ["xcrun","clang","-std=c11","-O1","-g","-fsanitize=address,undefined",
           "-fno-omit-frame-pointer",str(unit),"-o",str(binary)]
subprocess.run(command, check=True)
subprocess.run([str(binary)], check=True)
result = {"passed": True, "runtimeSource": str(source), "resourceSource": str(resources),
          "sourceSha256": {str(path.relative_to(source)): sha(path) for path in [
              source/"wine/dlls/xinput1_3/main.c", source/"wine/dlls/xinput9_1_0/main.c", build_script]},
          "recipeSha256": sha(ROOT/"windows-vr-tools/build_wine_guest_resources.sh"),
          "stagingSha256": sha(ROOT/"windows-vr-tools/stage_resources.py"),
          "modules": details, "closureFiles": len(files), "dynamicFallback": "xinput9_1_0 -> xinput1_4",
          "scope": "Actual build target/copy loop with mocked make/strip; real PE architecture/import/export/staging; production no-controller/fallback ASan/UBSan with host-pad/HID/loader boundaries mocked; no Wine/game/device execution"}
(a.build/"contract-receipt.json").write_text(json.dumps(result,indent=2)+"\n")
print("PASS: genuine three-module XInput build roots, required staging, real PE closure and dynamic fallback")
