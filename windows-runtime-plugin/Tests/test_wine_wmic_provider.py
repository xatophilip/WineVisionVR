#!/usr/bin/env python3
"""Exercise pinned WMIC alias/BIOS provider code without running Wine.

The production alias lookup and fill_bios body are compiled with sanitizers.
Firmware access, table allocation/filtering and SMBIOS field decoding are mocked
boundaries. This proves provider choice and preserved upstream placeholder
semantics, not COM activation, a hardware serial, or Tilt Brush compatibility.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--runtime-source', required=True, type=Path)
p.add_argument('--build', required=True, type=Path)
p.add_argument('--prefix-template', type=Path)
p.add_argument('--resource-source', type=Path, help='Require live packaging verification against this freshly built Madeira farm')
a = p.parse_args()
a.build.mkdir(parents=True, exist_ok=True)
wmic = (a.runtime_source/'wine/programs/wmic/main.c').read_text()
provider = (a.runtime_source/'wine/dlls/wbemprox/builtin.c').read_text()

def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    end, depth = brace+1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

aliases = wmic[wmic.index('static const struct'):wmic.index('static int WINAPIV output_string')]
record = provider[provider.index('struct record_bios\n'):provider.index('struct record_cache_memory\n')]
fill = function(provider, 'static enum fill_status fill_bios(')
query = function(wmic, 'static int query_prop(')
assert 'CoCreateInstance( &CLSID_WbemLocator' in query and 'CLSCTX_INPROC_SERVER' in query
assert 'ROOT\\\\CIMV2' in query and 'SELECT %s FROM %s' in query
assert re.search(r'\{ L"Win32_BIOS",.*fill_bios \}', provider)
idl = (a.runtime_source/'wine/dlls/wbemprox/wbemprox.idl').read_text()
assert '#pragma makedep register' in idl and '4590f811-1d3a-11d0-891f-00aa004b2e24' in idl
bridge = (a.runtime_source/'app/Madeira/WineProcessBridge.m').read_text()
assert '"wbemprox.dll"' in bridge and '"wmic.exe"' in bridge and 'madeira_link_wbem(fm, prefix, @"system32", dllSource);' in bridge
recipe = (ROOT/'windows-vr-tools/build_wine_guest_resources.sh').read_text()
assert 'enable_wmic=arm64ec' in recipe
assert 'programs/wmic/arm64ec-windows/wmic.exe' in recipe
module_call = recipe.split('bash "$runtime_root/build/wine-pe/build-modules.sh"',1)[1].split('# Build the genuine',1)[0]
assert 'wbemprox' in module_call.split()
# Execute the actual production target array/copy loop with only make/strip
# replaced at the build-tool boundary. Fixture bytes must emerge unchanged.
start = recipe.index('core_program_targets=(')
end = recipe.index('# Check the newly packaged WMI roots',start)
programs = a.build/'program-copy'
(programs/'farm').mkdir(parents=True,exist_ok=True)
(programs/'toolchain/bin').mkdir(parents=True,exist_ok=True)
strip = programs/'toolchain/bin/arm64ec-w64-mingw32-strip'
strip.write_text('#!/bin/sh\n[ "$1" = --strip-debug ]\n')
strip.chmod(0o755)
shell = r'''
set -euo pipefail
wine_build="$1/build"
wine_farm="$1/farm"
AVPPLAY_LLVM_MINGW_ROOT="$1/toolchain"
make() {
    shift 3
    for target in "$@"; do
        mkdir -p "$wine_build/$(dirname "$target")"
        printf 'same-source:%s\n' "$target" > "$wine_build/$target"
    done
}
'''+recipe[start:end]
subprocess.run(['bash','-c',shell,'wmic-test',str(programs.resolve())],check=True)
assert (programs/'farm/wmic.exe').read_bytes() == b'same-source:programs/wmic/arm64ec-windows/wmic.exe\n'

# Exercise actual staging and ledger policy. The source-farm receipt remains
# untouched: this verifies selection/copy behavior, not new build provenance.
sys.path.insert(0,str(ROOT/'windows-vr-tools'))
import stage_resources
import resource_receipt
assert 'wmic.exe' in stage_resources.WINE_TOOLS == resource_receipt.WINE_TOOLS
assert stage_resources.packaged_builtin(Path('wmic.exe'),'arm64ec-windows')
assert stage_resources.packaged_builtin(Path('WMIC.EXE'),'arm64ec-windows')
assert not stage_resources.packaged_builtin(Path('unlisted-helper.exe'),'arm64ec-windows')
assert stage_resources.packaged_builtin(Path('wbemprox.dll'),'arm64ec-windows')
resources=a.resource_source or a.runtime_source/'app/Madeira'
packaging={'policyVerified':True,'liveFreshPECopyVerified':False}
if a.resource_source or (resources/'arm64ec-windows/wmic.exe').is_file():
    for name in ['wmic.exe','wbemprox.dll']:
        assert stage_resources.is_arm64ec_pe(resources/'arm64ec-windows'/name)
    copied=a.build/'production-packaging';copied.mkdir()
    stage_resources.copy_builtins(resources,copied)
    ledger=resource_receipt.guest_resource_files(resources)
    hashes={}
    for name in ['wmic.exe','wbemprox.dll']:
        relative='arm64ec-windows/'+name
        expected=hashlib.sha256((resources/relative).read_bytes()).hexdigest()
        assert hashlib.sha256((copied/relative).read_bytes()).hexdigest()==expected
        assert ledger[relative]==expected
        hashes[name]=expected
    packaging.update(liveFreshPECopyVerified=True,resources=str(resources),copiedPEsSha256=hashes)
    print('PASS: production copy_builtins and guest_resource_files preserve fresh WMIC/WBEM PEs; unlisted EC executables remain excluded')
else:
    print('SKIP: live PE packaging copy; pass --resource-source after the guest build')

prelude = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
typedef wchar_t WCHAR;
typedef unsigned UINT;
typedef uint8_t UINT8;
typedef uint16_t UINT16;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define wcsicmp wcscasecmp
#define TRACE(...) ((void)0)
#define RSMB 0x52534d42u
enum fill_status { FILL_STATUS_UNFILTERED, FILL_STATUS_FAILED };
struct table { void *data; unsigned num_rows; };
struct expr { int unused; };
static unsigned firmware_calls;
static unsigned GetSystemFirmwareTable(unsigned provider,unsigned id,void *buffer,unsigned length) {
 assert(provider==RSMB && id==0);++firmware_calls;
 if(buffer) { assert(length==16);((char *)buffer)[0]=42; } else assert(length==0);
 return 16;
}
static int resize_table(struct table *t,unsigned rows,size_t size) { assert(rows==1);t->data=calloc(rows,size);return t->data!=NULL; }
static int match_row(struct table *t,unsigned row,const struct expr *c,enum fill_status *s) {
 assert(t->data && row==0 && !c && *s==FILL_STATUS_UNFILTERED);return 1;
}
static void free_row_values(struct table *t,unsigned row) { (void)t;(void)row;abort(); }
static unsigned decode(const char *b,unsigned len) { assert(b[0]==42 && len==16);return 7; }
#define get_bios_ec_firmware_major_release decode
#define get_bios_ec_firmware_minor_release decode
#define get_bios_smbiosmajorversion decode
#define get_bios_smbiosminorversion decode
#define get_bios_system_bios_major_release decode
#define get_bios_system_bios_minor_release decode
static const WCHAR *decode_text(const char *b,unsigned len) { decode(b,len);return L"mocked SMBIOS boundary"; }
#define get_bios_manufacturer decode_text
#define get_bios_releasedate decode_text
#define get_bios_smbiosbiosversion decode_text
'''
tests = r'''
int main(void) {
 assert(!wcscmp(find_class(L"bios"),L"Win32_BIOS"));
 assert(!wcscmp(find_class(L"BIOS"),L"Win32_BIOS"));assert(!find_class(L"unknown-class"));
 struct table table={0};assert(fill_bios(&table,NULL)==FILL_STATUS_UNFILTERED);
 struct record_bios *bios=table.data;
 assert(table.num_rows==1 && firmware_calls==2);
 assert(!wcscmp(bios->serialnumber,L"Serial number"));
 assert(!wcscmp(bios->manufacturer,L"mocked SMBIOS boundary"));
 free(table.data);
 puts("PASS: actual WMIC bios alias, actual BIOS provider/firmware boundary, unchanged upstream serial placeholder");
}
'''
unit=a.build/'provider.c';binary=a.build/'provider'
unit.write_text(prelude+aliases+record+fill+tests)
command=['xcrun','clang','-std=c11','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(unit),'-o',str(binary)]
subprocess.run(command,check=True);subprocess.run([str(binary)],check=True)
prefix = a.prefix_template or (Path(os.environ['AVPPLAY_WINE_PREFIX_TEMPLATE']) if os.environ.get('AVPPLAY_WINE_PREFIX_TEMPLATE') else None)
registration=None
if prefix:
    with tarfile.open(prefix) as tar:
        registry=tar.extractfile('prefix/system.reg').read().decode(errors='replace')
    blocks=[b for b in registry.split('\n\n') if '4590f811-1d3a-11d0-891f-00aa004b2e24' in b.lower() and 'InprocServer32' in b]
    assert any('wbemprox.dll' in b.lower() for b in blocks)
    registration=True
    print('PASS: existing prefix WbemLocator registration points at Wine wbemprox; no registry edit')
else:
    print('SKIP: prefix registration verification; no --prefix-template or AVPPLAY_WINE_PREFIX_TEMPLATE')
(a.build/'result.json').write_text(json.dumps({'passed':True,'productionPackaging':packaging,'scope':'Production staging/ledger policy and optional live PE copy; production WMIC alias and BIOS provider with mocked firmware/table boundaries; actual build target-copy loop with mocked make/strip; no Wine/COM/device execution','serialSemantics':'Unchanged upstream placeholder; not a physical serial','prefixLocatorRegistrationVerified':registration,'wmicSourceSha256':hashlib.sha256(wmic.encode()).hexdigest(),'providerSourceSha256':hashlib.sha256(provider.encode()).hexdigest(),'command':command},indent=2)+'\n')
