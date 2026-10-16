#!/usr/bin/env python3
"""Link/load the production optional graphics probes with and without providers."""
import argparse
import ctypes
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True, type=Path)
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
text = (root / 'windows-runtime-plugin/WindowsVRRuntimePlugin.mm').read_text()
declarations = text.split('// Optional symbols', 1)[1].split('extern "C" void winios_post_key', 1)[0]
declarations = '// Optional symbols' + declarations
function = 'bool IsModernDXMTNativeProfile() {' + text.split('bool IsModernDXMTNativeProfile() {', 1)[1].split('\n}', 1)[0] + '\n}'
unit = args.build / 'profile.cpp'
unit.write_text('#include <cstddef>\n#include <cstdint>\n' + declarations + function + '\nextern "C" int profile_probe() { return IsModernDXMTNativeProfile(); }\n')
for name, count, expected in [('legacy', None, 0), ('modern', 148, 1), ('wrong-count', 147, 0)]:
    library = args.build / (name + '.dylib')
    command = ['xcrun', 'clang++', '-dynamiclib', '-std=c++20', str(unit), '-o', str(library),
               '-Wl,-U,_wvr_dxmt_d3d12_unix_call_count_v1', '-Wl,-U,_wvr_dxmt_d3d12_transport_abi_v1']
    if count is not None:
        provider = args.build / (name + '.cpp')
        provider.write_text('#include <cstddef>\n#include <cstdint>\nextern "C" size_t wvr_dxmt_d3d12_unix_call_count_v1() { return ' + str(count) + '; }\nextern "C" uint32_t wvr_dxmt_d3d12_transport_abi_v1() { return 1; }\n')
        command.append(str(provider))
    subprocess.run(command, check=True)
    loaded = ctypes.CDLL(str(library))
    loaded.profile_probe.restype = ctypes.c_int
    assert loaded.profile_probe() == expected, name
print('PASS: actual Mach-O legacy missing weak symbols, valid modern provider and incompatible dispatch count')
