#!/usr/bin/env python3
"""Compare actual i386 Windows and ARM64 visionOS transport record ABIs.

All winemetal request/command records are shared directly across the boundary.
SM50 uses its explicit *32 records for pointer-bearing requests and compilation
arguments, while reflection and 64-bit opaque outputs remain layout-identical.
Both compiler layouts are retained as evidence; no Windows code is executed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dxmt-source', required=True, type=Path)
parser.add_argument('--llvm-mingw-root', required=True, type=Path)
parser.add_argument('--build', required=True, type=Path)
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
metal = args.dxmt_source / 'src/winemetal'
air = args.dxmt_source / 'src/airconv'
unix = metal / 'unix/winemetal_unix.c'
text = unix.read_text()
# These actual conversion records are private to the native implementation.
# Extract complete declarations, including any anonymous nested unions.
records = []
for match in re.finditer(r'struct (SM50_\w+32)\s*\{', text):
    end, depth = match.end(), 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    records.append(text[match.start():end] + ';')
assert records, 'Expected the actual SM50 explicit32 conversion records'
unit = args.build / 'layout.c'
unit.write_text('#include "winemetal_thunks.h"\n#include "airconv_thunks.h"\n' + '\n'.join(records))
includes = ['-I' + str(metal), '-I' + str(air)]
common = ['-std=gnu2x', '-Xclang', '-fdump-record-layouts-complete', '-fsyntax-only', *includes, str(unit)]
commands = {
    'i386': [str(args.llvm_mingw_root / 'bin/i686-w64-mingw32-clang'), *common],
    'arm64': ['xcrun', '--sdk', 'xros', 'clang', '-target', 'arm64-apple-xros2.0', *common],
}
layouts = {}
for arch, command in commands.items():
    result = subprocess.run(command, capture_output=True, text=True)
    dump = result.stdout + result.stderr
    (args.build / (arch + '.txt')).write_text(dump)
    if result.returncode:
        raise SystemExit(dump)
    parsed = {}
    for body in dump.split('*** Dumping AST Record Layout')[1:]:
        name = re.search(r'^\s*0 \| (struct (?:WMT|unixcall_|wmtcmd_|SM50_|sm50_|MTL_)\w+)\s*$', body, re.M)
        extent = re.search(r'\[sizeof=(\d+), align=(\d+)\]', body)
        if not name or not extent:
            continue
        fields = {}
        for offset, field in re.findall(r'^\s*([\d]+(?::[\d]+-[\d]+)?) \|   ([^ ].*)$', body, re.M):
            fields[field.rsplit(' ', 1)[-1]] = offset
        parsed[name[1]] = {'size': int(extent[1]), 'alignment': int(extent[2]), 'fields': fields}
    layouts[arch] = parsed

pe, host = layouts['i386'], layouts['arm64']
comparisons = {}
failures = []
for name, guest in sorted(pe.items()):
    if name.endswith('32') or name == 'struct sm50_ptr64_t':
        continue  # Explicit32 types are selected as the native counterpart below.
    target = name + '32' if name + '32' in host and name.startswith(('struct SM50_', 'struct sm50_')) else name
    if target not in host:
        failures.append('Missing ARM64 record: ' + target)
        continue
    native = host[target]
    guest_fields = {key: value for key, value in guest['fields'].items() if key != 'high_part'}
    native_fields = {key: value for key, value in native['fields'].items() if key != 'high_part'}
    # The existing SM50 conversion explicitly copies src->flag to data->flags.
    if target == 'struct SM50_SHADER_COMMON_DATA32':
        native_fields['flags'] = native_fields.pop('flag')
    same = guest['size'] == native['size'] and guest['alignment'] == native['alignment'] and guest_fields == native_fields
    comparisons[name] = {'nativeRecord': target, 'i386': guest, 'arm64': native, 'matches': same}
    if not same:
        failures.append(f'{name} -> {target}: i386={guest}, ARM64={native}')

wmt_count = sum(name.startswith(('struct WMT', 'struct unixcall_', 'struct wmtcmd_')) for name in comparisons)
assert wmt_count >= 161, f'Incomplete public record comparison: {wmt_count}'
assert 'struct SM50_COMPILED_BITCODE' in comparisons, 'Opaque compiled-bitcode output was not inspected'
assert 'struct sm50_initialize_params' in comparisons, 'Explicit32 shader request layout was not inspected'
assert 'struct SM50_SHADER_ROOT_SIGNATURE_DATA' in comparisons, 'Nested shader argument layout was not inspected'
# The original bug admitted 4-byte-aligned pointer boxes on i386 while native
# code required 8. A valid new guest cannot place these records at base+4 or
# produce a misaligned array element by advancing its declared sizeof.
for name in ('struct WMTMemoryPointer', 'struct WMTConstMemoryPointer', 'struct wmtcmd_base',
             'struct wmtcmd_render_setviewports', 'struct wmtcmd_compute_memory_barrier'):
    record = pe[name]
    if record['alignment'] != 8 or record['size'] % 8:
        failures.append(f'Four-byte aligned fixture would be legal for {name}: {record}')
result = {'status': 'fail' if failures else 'pass', 'winemetalRecords': wmt_count,
          'totalComparedRecords': len(comparisons), 'comparisons': comparisons,
          'failures': failures, 'commands': commands,
          'productionInputsSha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in (metal / 'winemetal.h', metal / 'winemetal_thunks.h', metal / 'airconv_thunks.h', air / 'airconv_public.h', unix)}}
(args.build / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
if failures:
    raise SystemExit('\n'.join(failures))
print(f'PASS: {wmt_count} winemetal records and {len(comparisons) - wmt_count} SM50/reflection/explicit32 records match in size, alignment and every field offset; four-byte command alignment rejected')
