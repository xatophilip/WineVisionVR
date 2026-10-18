#!/usr/bin/env python3
"""Run applied Wine import selection and pointer redirection on actual shipped PEs.

Compile the original and patched loader selection, unchanged production metadata
reader and redirect function under ASan/UBSan. Only PE-loading and host JIT alias
boundaries are adapted; no guest instructions, Wine, or device actions run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--runtime-source', required=True, type=Path)
p.add_argument('--resource-source', type=Path, help='Defaults to runtime-source/app/Madeira')
p.add_argument('--build', required=True, type=Path)
a = p.parse_args()
a.build.mkdir(parents=True, exist_ok=True)
scratch = Path(tempfile.mkdtemp(prefix='native-arm64-import-', dir=a.build.resolve()))
resources = a.resource_source or a.runtime_source / 'app/Madeira'
relative = Path('wine/dlls/ntdll/loader.c')
target = scratch / relative
target.parent.mkdir(parents=True)
shutil.copyfile(a.runtime_source / relative, target)
patch = ROOT / 'windows-runtime-plugin/patches/0015-wine-native-arm64-import-redirection.patch'
def apply(*flags):
    return subprocess.run(['git', 'apply', *flags, str(patch)], cwd=scratch, capture_output=True, text=True)
if apply('--check').returncode:
    result = apply('--reverse', '--check')
    assert result.returncode == 0, result.stderr
    result = apply('--reverse')
    assert result.returncode == 0, result.stderr
before = target.read_text()
result = apply()
assert result.returncode == 0, result.stderr
after = target.read_text()
# Both real import branches must keep their exported-x64-IAT protection.
protection = 'else if (imp_metadata && !arm64ec_iat_is_exported_x64( module, thunk_list ))'
assert before.count(protection) == after.count(protection) == 2

def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

def selection(source):
    start = source.index('    const IMAGE_ARM64EC_METADATA *imp_metadata = NULL;', source.index('static BOOL import_dll('))
    end = source.index('#endif', start)
    return 'static const IMAGE_ARM64EC_METADATA *select_metadata(HMODULE module, HMODULE imp_mod) {\n' + source[start:end] + '\nreturn imp_metadata;\n}\n'

signal = (a.runtime_source / 'wine/dlls/ntdll/signal_arm64ec.c').read_text()
reader = function(signal, 'IMAGE_ARM64EC_METADATA *arm64ec_get_module_metadata(')
redirect = function(signal, 'void *arm64ec_redirect_ptr(')

# Map actual PE sections, retaining real export/import/CHPE metadata and code.
# Turn only the CHPE absolute VA into an RVA; the harness rebases that pointer
# after allocating the image, exactly as PE relocation would do at runtime.
def image(path, out):
    binary = path.read_bytes()
    pe = struct.unpack_from('<I', binary, 0x3c)[0]
    assert binary[pe:pe+4] == b'PE\0\0'
    machine, count = struct.unpack_from('<HH', binary, pe+4)
    opt = pe+24
    assert struct.unpack_from('<H', binary, opt)[0] == 0x20b
    size = struct.unpack_from('<I', binary, opt+56)[0]
    headers = struct.unpack_from('<I', binary, opt+60)[0]
    base = struct.unpack_from('<Q', binary, opt+24)[0]
    mapped = bytearray(size)
    mapped[:headers] = binary[:headers]
    section = opt + struct.unpack_from('<H', binary, pe+20)[0]
    for i in range(count):
        virtual_size, rva, raw_size, raw = struct.unpack_from('<IIII', binary, section+i*40+8)
        mapped[rva:rva+raw_size] = binary[raw:raw+raw_size]
    cfg, cfg_size = struct.unpack_from('<II', mapped, opt+112+10*8)
    if cfg and cfg_size >= 208:
        pointer = struct.unpack_from('<Q', mapped, cfg+200)[0]
        if pointer:
            struct.pack_into('<Q', mapped, cfg+200, pointer-base)
    out.write_bytes(mapped)
    return {'path': str(path), 'sha256': hashlib.sha256(binary).hexdigest(), 'machine': hex(machine)}

inputs = {}
for name, rel in [('native', 'aarch64-windows/wow64.dll'), ('ec', 'arm64ec-windows/ntdll.dll')]:
    inputs[name] = image(resources / rel, scratch / (name+'.image'))

prelude = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void *HMODULE;
typedef uint32_t ULONG;
typedef uintptr_t ULONG_PTR;
typedef int32_t LONG;
typedef struct { uint32_t Signature; struct { uint16_t Machine; unsigned char pad[18]; } FileHeader;
 struct { unsigned char pad[56]; uint32_t SizeOfImage; } OptionalHeader; } IMAGE_NT_HEADERS;
typedef struct { ULONG Size; unsigned char pad[196]; uintptr_t CHPEMetadataPointer; } IMAGE_LOAD_CONFIG_DIRECTORY;
typedef struct { ULONG Version,CodeMap,CodeMapCount,CodeRangesToEntryPoints,RedirectionMetadata;
 ULONG pad[8]; ULONG RedirectionMetadataCount; } IMAGE_ARM64EC_METADATA;
typedef struct { ULONG Source,Destination; } IMAGE_ARM64EC_REDIRECTION_ENTRY;
typedef struct list { struct list *Flink,*Blink; } LIST_ENTRY;
typedef struct { LIST_ENTRY InLoadOrderLinks; void *DllBase; size_t SizeOfImage; } LDR_DATA_TABLE_ENTRY;
static struct { struct { LIST_ENTRY InLoadOrderModuleList; } *LdrData; } peb;
#define RtlGetCurrentPeb() (&peb)
#define CONTAINING_RECORD(p,type,field) ((type *)((char *)(p)-offsetof(type,field)))
#define TRUE 1
#define IMAGE_DIRECTORY_ENTRY_LOAD_CONFIG 10
#define IMAGE_FILE_MACHINE_ARM64 0xaa64
#define min(a,b) ((a)<(b)?(a):(b))
static void *get_rva(HMODULE base, ULONG rva) { return (char *)base+rva; }
static IMAGE_NT_HEADERS *RtlImageNtHeader(HMODULE base) {
 uint32_t offset; memcpy(&offset,(char *)base+0x3c,4);return get_rva(base,offset);
}
static void *RtlImageDirectoryEntryToData(HMODULE base,int mapped,unsigned index,ULONG *size) {
 (void)mapped; unsigned char *opt=(unsigned char *)RtlImageNtHeader(base)+24;
 ULONG rva;memcpy(&rva,opt+112+index*8,4);memcpy(size,opt+116+index*8,4);
 return rva?get_rva(base,rva):NULL;
}
static unsigned aliases;
static void *xlate_ios_jit(void *p) { ++aliases;return p; }
IMAGE_ARM64EC_METADATA *arm64ec_get_module_metadata(HMODULE);
'''
tests = r'''
static void *load(const char *path) {
 FILE *f=fopen(path,"rb");assert(f);assert(!fseek(f,0,SEEK_END));long size=ftell(f);
 assert(size>0);rewind(f);unsigned char *p=calloc(1,(size_t)size);assert(p);
 assert(fread(p,1,(size_t)size,f)==(size_t)size);fclose(f);
 ULONG cfg_size;IMAGE_LOAD_CONFIG_DIRECTORY *cfg=RtlImageDirectoryEntryToData(p,TRUE,10,&cfg_size);
 if(cfg && cfg_size>=208 && cfg->CHPEMetadataPointer) cfg->CHPEMetadataPointer+=(uintptr_t)p;
 return p;
}
int main(int argc,char **argv) {
 assert(argc==3);void *native=load(argv[1]),*ec=load(argv[2]),*amd64=load(argv[2]);
 assert(RtlImageNtHeader(native)->FileHeader.Machine==IMAGE_FILE_MACHINE_ARM64);
 assert(!arm64ec_get_module_metadata(native));assert(arm64ec_get_module_metadata(ec));
 const IMAGE_ARM64EC_METADATA *selected=select_metadata(native,ec);
 void *raw=get_rva(ec,FUNCTION_RVA), *body=get_rva(ec,NATIVE_RVA);
 assert(!memcmp(raw,"\x48\x8b\xc4\x48\x89\x58\x20\x55\x5d\xe9",10));
 void *bound=selected?arm64ec_redirect_ptr(ec,raw,selected):raw;
#ifdef EXPECT_BASELINE
 assert(!selected && bound==raw);
 printf("PASS: old production selection binds ARM64 wow64 to x64 RtlRunOnceExecuteOnce RVA %#x\n", FUNCTION_RVA);
#else
 assert(selected && bound==body);
 printf("PASS: fixed production selection binds ARM64 wow64 to native RtlRunOnceExecuteOnce RVA %#x\n", NATIVE_RVA);
#endif
 /* EC importers still receive native targets and preserve the JIT alias hook. */
 selected=select_metadata(ec,ec);assert(selected);
 unsigned calls=aliases;assert(arm64ec_redirect_ptr(ec,raw,selected)==body && aliases>calls);
 /* Actual AMD64-shaped image: remove CHPE metadata while retaining AMD64 Machine. */
 ULONG size;IMAGE_LOAD_CONFIG_DIRECTORY *cfg=RtlImageDirectoryEntryToData(amd64,TRUE,10,&size);
 cfg->CHPEMetadataPointer=0;
 assert(RtlImageNtHeader(amd64)->FileHeader.Machine==0x8664 && !arm64ec_get_module_metadata(amd64));
 selected=select_metadata(amd64,ec);assert(!selected);
 bound=selected?arm64ec_redirect_ptr(ec,raw,selected):raw;assert(bound==raw);
 /* Native target has no EC thunks; import selection must not redirect it. */
 assert(!select_metadata(native,native) && !select_metadata(ec,native));
 /* Real ntdll data export __wine_unixlib_handle stays data, including its alias callback. */
 void *data=get_rva(ec,DATA_RVA);calls=aliases;
 assert(arm64ec_redirect_ptr(ec,data,arm64ec_get_module_metadata(ec))==data && aliases>calls);
 assert(!arm64ec_redirect_ptr(ec,NULL,arm64ec_get_module_metadata(ec)));
 free(native);free(ec);free(amd64);puts("PASS: EC redirection, AMD64 preservation, native targets, data export and JIT alias callback");
}
'''
# Locate the actual exported data RVA rather than manufacturing a test pointer.
def export_rva(mapped, symbol):
    pe = struct.unpack_from('<I', mapped, 0x3c)[0]
    exp = struct.unpack_from('<I', mapped, pe+24+112)[0]
    count, functions, names, ordinals = struct.unpack_from('<IIII', mapped, exp+24)
    for i in range(count):
        name = struct.unpack_from('<I', mapped, names+i*4)[0]
        if mapped[name:mapped.index(0,name)] == symbol:
            ordinal = struct.unpack_from('<H', mapped, ordinals+i*2)[0]
            return struct.unpack_from('<I', mapped, functions+ordinal*4)[0]
    raise AssertionError('Missing real ntdll export: ' + repr(symbol))
mapped = (scratch/'ec.image').read_bytes()
data = export_rva(mapped, b'__wine_unixlib_handle')
raw_rva = export_rva(mapped, b'RtlRunOnceExecuteOnce')
assert mapped[raw_rva:raw_rva+10] == bytes.fromhex('488bc448895820555de9')
native_rva = raw_rva + 14 + struct.unpack_from('<i', mapped, raw_rva+10)[0]
assert 0 <= native_rva < len(mapped)
# Current r4 fixture produces 0x923d0 -> 0x67ec0. A freshly rebuilt ntdll may
# move both functions; derive its independently encoded target from its thunk.
commands=[]
for label, loader in [('before',before),('after',after)]:
    unit=scratch/(label+'.c');binary=scratch/label
    unit.write_text(prelude+reader+'\n'+redirect+'\n'+selection(loader)+'\n'+tests.replace('DATA_RVA',hex(data)).replace('FUNCTION_RVA',hex(raw_rva)).replace('NATIVE_RVA',hex(native_rva)))
    command=['xcrun','clang','-std=c11','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(unit),'-o',str(binary)]
    if label=='before':command.insert(2,'-DEXPECT_BASELINE')
    subprocess.run(command,check=True)
    subprocess.run([str(binary),str(scratch/'native.image'),str(scratch/'ec.image')],check=True)
    commands.append(command)
(a.build/'result.json').write_text(json.dumps({'passed':True,'scope':'Actual before/after Wine import selection, metadata reader and pointer redirection; actual mapped shipped ARM64/ARM64EC PEs; no device execution','patchSha256':hashlib.sha256(patch.read_bytes()).hexdigest(),'loaderSourceSha256':hashlib.sha256((a.runtime_source/relative).read_bytes()).hexdigest(),'signalSourceSha256':hashlib.sha256(signal.encode()).hexdigest(),'inputs':inputs,'commands':commands,'exportedX64IATGuardsUnchanged':True,'rawFunctionRVA':hex(raw_rva),'nativeFunctionRVA':hex(native_rva)},indent=2)+'\n')
