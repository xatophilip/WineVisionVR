#!/usr/bin/env python3
"""Exercise production modern WOW64 wrappers with a shifted guest window.

Pass a prepared modern DXMT checkout containing patch 0025. The test compiles
its actual wrapper bodies and public records; mock native endpoints assert the
CPU addresses they receive and leave opaque object/GPU handles untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


def function(source, name):
    match = re.search(r"(?:static\s+)?(?:NTSTATUS|int)\s+" + re.escape(name) + r"\([^)]*\)\s*\{", source)
    if not match:
        raise RuntimeError("Missing production function: " + name)
    depth, end = 1, match.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dxmt-source", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    source = args.dxmt_source / "src/winemetal/unix/winemetal_unix.c"
    text = source.read_text()
    start = text.index("/* Only embedded CPU pointers")
    helpers = text[start:text.index("#ifndef DXMT_NATIVE", start)]
    start = text.index("/* ------------------------------------------------------------------------\n * MADEIRA (WOW64_DESIGN.md section 7.4)")
    wrappers = text[start:text.index("\n#endif\n\n#if TARGET_OS_IOS", start)]
    tables = []
    for symbol in ("__wine_unix_call_funcs", "__wine_unix_call_wow64_funcs"):
        start = text.index("const void *" + symbol + "[]")
        entries = re.findall(r"&([A-Za-z_0-9]+)|\b(NULL)\b", text[start:text.index("};", start)])
        tables.append([a or b for a, b in entries])
    assert len(tables[0]) == len(tables[1]) == 148, "Changed modern dispatch ABI"
    assert tables[0][146:] == ["_WMTWindowsVRBridgeCallV1", "_WMTWindowsVRBridgeCallV2"]
    assert tables[1][146:] == ["_WMTWindowsVRBridgeCallV132", "_WMTWindowsVRBridgeCallV232"]
    assert tables[0][18] == "_MTLDevice_newBuffer" and tables[1][18] == "_MTLDevice_newBuffer32"
    assert "wvr_dxmt_wow64_transport_abi_v1" in text
    native = sorted({entry for entry in tables[0] if entry.startswith("_")})
    tested = {
        "_MTLDevice_newBuffer", "_MTLDevice_newRenderPipelineState",
        "_MTLRenderCommandEncoder_encodeCommands", "_WMTWindowsVRBridgeCallV1",
        "_WMTWindowsVRBridgeCallV2", "_CacheWriter_set", "_DispatchData_alloc_init",
        "_MTLCounterSampleBuffer_resolveCounterRange",
    }
    declarations = "\n".join("static NTSTATUS " + name + "(void *obj);" for name in native)
    mocks = "\n".join("static NTSTATUS " + name + "(void *obj) { (void)obj; return STATUS_SUCCESS; }"
                      for name in native if name not in tested)
    sm50 = function(text, "thunk32_SM50Initialize") + "\n" + function(text, "thunk32_SM50GetCompiledBitcode")
    prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "winemetal_thunks.h"
#include "airconv_thunks.h"
#include "WindowsVRWOW64Transport.h"
#undef TARGET_OS_IOS
#define TARGET_OS_IOS 1
#undef TARGET_OS_VISION
#define TARGET_OS_VISION 1
typedef int NTSTATUS;
#define STATUS_SUCCESS 0
#define STATUS_INVALID_PARAMETER ((NTSTATUS)0xC000000D)
struct unixcall_windows_vr_bridge_v1 { struct WMTMemoryPointer request; };
static unsigned char *window;
static const uint64_t opaque = UINT64_C(0x1234567812345678);
#define H(offset) ((void *)(window + (offset)))
#define G(offset) ((void *)(uintptr_t)(0x10000 + (offset)))
unsigned long ios_wow_base(void) { return (unsigned long)(uintptr_t)window - 0x10000; }
'''
    checks = r'''
static NTSTATUS _MTLDevice_newBuffer(void *obj) {
    struct unixcall_mtldevice_newbuffer *p = obj;
    struct WMTBufferInfo *i = p->info.ptr;
    assert(p->device == opaque && i == H(0x100) && i->memory.ptr == H(0x200));
    i->gpu_address = opaque; p->ret = opaque; return 0;
}
static NTSTATUS _MTLDevice_newRenderPipelineState(void *obj) {
    struct unixcall_mtldevice_newrenderpso *p = obj;
    struct WMTRenderPipelineInfo *i = (void *)p->info.ptr;
    assert(p->device == opaque && i == H(0x1000));
    assert(i->binary_archives_for_lookup.ptr == H(0x1800));
    assert(((uint64_t *)i->binary_archives_for_lookup.ptr)[0] == opaque);
    p->ret_pso = opaque; return 0;
}
static NTSTATUS _MTLRenderCommandEncoder_encodeCommands(void *obj) {
    struct unixcall_generic_obj_cmd_noret *p = obj;
    struct wmtcmd_render_setbytes *a = (void *)p->cmd_head.ptr;
    struct wmtcmd_render_setviewports *b = a->next.ptr;
    assert(p->encoder == opaque && a == H(0x400) && a->bytes.ptr == H(0x600));
    assert(b == H(0x500) && b->viewports.ptr == H(0x700) && b->next.ptr == NULL);
    assert(a->length == 16 && b->viewport_count == 1); return 0;
}
static NTSTATUS bridge(void *obj) {
    struct unixcall_windows_vr_bridge_v1 *p = obj;
    assert(p->request.ptr == H(0x900));
    assert(((uint64_t *)p->request.ptr)[0] == opaque);
    ((uint64_t *)p->request.ptr)[1] = opaque; return 0;
}
static NTSTATUS _WMTWindowsVRBridgeCallV1(void *obj) { return bridge(obj); }
static NTSTATUS _WMTWindowsVRBridgeCallV2(void *obj) { return bridge(obj); }
static NTSTATUS _CacheWriter_set(void *obj) {
    struct unixcall_cache_set *p = obj;
    assert(p->cache == opaque && p->value_data == opaque && p->key.ptr == H(0xa00));
    assert(p->key_length == 4); return 0;
}
static unsigned dispatchCalls;
static NTSTATUS _DispatchData_alloc_init(void *obj) {
    struct unixcall_generic_obj_uint64_obj_ret *p = obj;
    if (!dispatchCalls++) assert(p->handle == (uintptr_t)H(0xb00));
    else assert(p->handle == opaque);
    assert(p->arg == 16); p->ret = opaque; return 0;
}
static NTSTATUS _MTLCounterSampleBuffer_resolveCounterRange(void *obj) {
    struct unixcall_mtlcountersamplebuffer_resolvecounterrange *p = obj;
    assert(p->sample_buffer == opaque && p->data_out.ptr == H(0xc00));
    *(uint64_t *)p->data_out.ptr = opaque; return 0;
}
int SM50Initialize(const void *bytecode, size_t size, sm50_shader_t *shader,
                  struct MTL_SHADER_REFLECTION *reflection, sm50_error_t *error) {
    assert(bytecode == H(0xd00) && size == 4 && shader == H(0xd10));
    assert(reflection == H(0xd20) && error == H(0xe00));
    *shader = (void *)(uintptr_t)opaque; *error = NULL; return 0;
}
void SM50GetCompiledBitcode(sm50_bitcode_t bitcode, struct SM50_COMPILED_BITCODE *out) {
    assert((uintptr_t)bitcode == opaque && out == H(0xe20));
    out->Data = (void *)(uintptr_t)opaque; out->Size = 32;
}
'''
    run = r'''
int main(void) {
    window = calloc(1, 65536); assert(window);
    assert(wvr_wow64_guest_to_host(ios_wow_base(), 0) == 0);
    assert(wvr_wow64_guest_to_host(ios_wow_base(), 0x10200) == (uintptr_t)H(0x200));
    assert(wvr_wow64_wide_to_host(ios_wow_base(), opaque) == opaque);
    uint32_t guest = 0;
    assert(wvr_wow64_host_to_guest(ios_wow_base(), (uintptr_t)H(0x200), &guest) && guest == 0x10200);
    assert(!wvr_wow64_host_to_guest(ios_wow_base(), ios_wow_base() - 1, &guest));
    struct WMTBufferInfo *info = H(0x100); info->memory.ptr = G(0x200);
    struct unixcall_mtldevice_newbuffer buffer = { .device = opaque, .info.ptr = G(0x100) };
    assert(!_MTLDevice_newBuffer32(&buffer));
    assert(buffer.info.ptr == G(0x100) && info->memory.ptr == G(0x200));
    assert(buffer.ret == opaque && info->gpu_address == opaque);
    struct WMTRenderPipelineInfo *pipeline = H(0x1000);
    pipeline->binary_archives_for_lookup.ptr = G(0x1800); *(uint64_t *)H(0x1800) = opaque;
    struct unixcall_mtldevice_newrenderpso pso = { .device = opaque, .info.ptr = G(0x1000) };
    assert(!_MTLDevice_newRenderPipelineState32(&pso));
    assert(pso.info.ptr == G(0x1000) && pipeline->binary_archives_for_lookup.ptr == G(0x1800));
    struct wmtcmd_render_setbytes *a = H(0x400); a->type = WMTRenderCommandSetFragmentBytes;
    a->next.ptr = G(0x500); a->bytes.ptr = G(0x600); a->length = 16;
    struct wmtcmd_render_setviewports *b = H(0x500); b->type = WMTRenderCommandSetViewports;
    b->viewports.ptr = G(0x700); b->viewport_count = 1;
    struct unixcall_generic_obj_cmd_noret commands = { .encoder = opaque, .cmd_head.ptr = G(0x400) };
    assert(!_MTLRenderCommandEncoder_encodeCommands32(&commands));
    assert(commands.cmd_head.ptr == G(0x400) && a->next.ptr == G(0x500));
    assert(a->bytes.ptr == G(0x600) && b->viewports.ptr == G(0x700));
    /* Invalid i386 align4 nodes must be rejected before native casts. Use
     * memcpy so the fixture itself does not perform an unaligned C access. */
    unsigned char malformed[sizeof(*a)]; memcpy(malformed, a, sizeof(*a));
    memcpy(H(0x2044), malformed, sizeof(*a));
    commands.cmd_head.ptr = G(0x2044);
    assert(_MTLRenderCommandEncoder_encodeCommands32(&commands) == STATUS_INVALID_PARAMETER);
    assert(commands.cmd_head.ptr == G(0x2044));
    assert(!memcmp(H(0x2044), malformed, sizeof(*a)));
    commands.cmd_head.ptr = G(0x400);
    a->next.ptr = G(0x504);
    assert(_MTLRenderCommandEncoder_encodeCommands32(&commands) == STATUS_INVALID_PARAMETER);
    assert(a->next.ptr == G(0x504) && a->bytes.ptr == G(0x600));
    a->next.ptr = G(0x400); /* A cycle is rejected before any mutation too. */
    assert(_MTLRenderCommandEncoder_encodeCommands32(&commands) == STATUS_INVALID_PARAMETER);
    assert(a->next.ptr == G(0x400));
    a->next.ptr = G(0x500);
    struct unixcall_windows_vr_bridge_v1 bridgeParams = { .request.ptr = G(0x900) };
    *(uint64_t *)H(0x900) = opaque;
    assert(!_WMTWindowsVRBridgeCallV132(&bridgeParams));
    assert(!_WMTWindowsVRBridgeCallV232(&bridgeParams));
    assert(bridgeParams.request.ptr == G(0x900) && ((uint64_t *)H(0x900))[1] == opaque);
    struct unixcall_cache_set cache = { .cache = opaque, .key.ptr = G(0xa00), .key_length = 4, .value_data = opaque };
    assert(!_CacheWriter_set32(&cache) && cache.key.ptr == G(0xa00));
    struct unixcall_generic_obj_uint64_obj_ret data = { .handle = (uintptr_t)G(0xb00), .arg = 16 };
    assert(!_DispatchData_alloc_init32(&data) && data.handle == (uintptr_t)G(0xb00));
    data.handle = opaque;
    assert(!_DispatchData_alloc_init32(&data) && data.handle == opaque);
    struct unixcall_mtlcountersamplebuffer_resolvecounterrange counter = { .sample_buffer = opaque, .data_out.ptr = G(0xc00) };
    assert(!_MTLCounterSampleBuffer_resolveCounterRange32(&counter));
    assert(counter.data_out.ptr == G(0xc00) && *(uint64_t *)H(0xc00) == opaque);
    struct sm50_initialize_params32 shader = { .bytecode = 0x10d00, .bytecode_size = 4,
        .shader = 0x10d10, .reflection = 0x10d20, .error = 0x10e00 };
    assert(!thunk32_SM50Initialize(&shader) && shader.ret == 0);
    assert(*(uint64_t *)H(0xd10) == opaque);
    struct sm50_get_compiled_bitcode_params32 bitcode = { .bitcode = (void *)(uintptr_t)opaque, .data_out = 0x10e20 };
    assert(!thunk32_SM50GetCompiledBitcode(&bitcode));
    struct SM50_COMPILED_BITCODE *output = H(0xe20);
    assert((uintptr_t)output->Data == opaque && output->Size == 32);
    free(window); puts("PASS: production WOW64 wrappers, 148-slot ABI, shifted pointers and opaque 64-bit IDs");
}
'''
    output = args.output_dir or Path(tempfile.mkdtemp(prefix="wvr-modern-wow64-"))
    output.mkdir(parents=True, exist_ok=True)
    test = output / "modern-wow64-contract.c"
    test.write_text(prefix + helpers + declarations + checks + mocks + wrappers + sm50 + run)
    command = ["xcrun", "clang", "-std=gnu2x", "-g", "-O1", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
               "-Wno-unused-function", "-I" + str(args.dxmt_source / "src/winemetal"),
               "-I" + str(args.dxmt_source / "src/winemetal/unix"),
               "-I" + str(args.dxmt_source / "src/airconv"), str(test), "-o", str(output / "modern-wow64-contract")]
    print(shlex.join(command), flush=True)
    subprocess.run(command, check=True)
    result = subprocess.run([str(output / "modern-wow64-contract")], check=True, text=True, capture_output=True)
    print(result.stdout, end="")
    (output / "result.json").write_text(json.dumps({"status": "PASS", "sanitizers": ["ASan", "UBSan"],
        "productionSourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(), "dispatchSlots": 148,
        "cases": ["shifted-window/null", "buffer-inout", "nested-pipeline", "command-chain/payload-restoration",
                  "invalid-align4-head/node", "cyclic-command-chain", "bridge-v1-v2", "cache-key", "native-bitcode-wide-pointer", "counter-readback", "SM50-output"]}, indent=2) + "\n")


if __name__ == "__main__":
    main()
