#!/usr/bin/env python3
"""Exercise the production modern x86 package gate without executing guest code."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True, type=Path)
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
source = (ROOT / 'windows-runtime-plugin/WindowsVRRuntimePlugin.mm').read_text()
def function(signature):
    start = source.index(signature)
    brace = source.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end].replace('[NSBundle mainBundle].resourceURL', 'testResources')
code = '''#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#include <string>
#include <vector>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <climits>
static NSURL *testResources;
static unsigned int testABI;
static size_t testCount;
bool HasD3D12Package() { return true; }
unsigned int wvr_dxmt_wow64_transport_abi_v1() { return testABI; }
size_t wvr_dxmt_wow64_unix_call_count_v1() { return testCount; }
'''
for signature in ('bool IsContainedPath(', 'bool ReadPEInfo(', 'bool ReadPEMachine(', 'bool SHA256File(', 'bool HasModernX86Package('):
    code += function(signature) + '\n'
code += '''int main(int argc, char **argv) { @autoreleasepool {
    testResources = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]] isDirectory:YES];
    testABI = strtoul(argv[2], nullptr, 10); testCount = strtoul(argv[3], nullptr, 10);
    return HasModernX86Package() ? 0 : 2;
} }
'''
unit = args.build / 'modern-x86-package.mm'
unit.write_text(code)
binary = args.build / 'modern-x86-package'
subprocess.run(['xcrun', '--sdk', 'macosx', 'clang++', '-std=c++20', '-fobjc-arc',
                '-Wno-deprecated-declarations', '-Wno-pointer-bool-conversion', str(unit),
                '-framework', 'Foundation', '-o', str(binary)], check=True)
with tempfile.TemporaryDirectory(prefix='fixture-', dir=args.build) as directory:
    resources = Path(directory)
    farm = resources / 'Runtime/i386-windows'
    farm.mkdir(parents=True)
    metadata = resources / 'WindowsVR/D3D12Experimental'
    metadata.mkdir(parents=True)
    hashes = {}
    for name in ('d3d11.dll', 'd3d12.dll', 'dxgi.dll', 'winemetal.dll'):
        data = bytearray(512)
        data[:2] = b'MZ'; data[60:64] = (64).to_bytes(4, 'little')
        data[64:68] = b'PE\0\0'; data[68:70] = (0x14c).to_bytes(2, 'little')
        data[84:86] = (224).to_bytes(2, 'little'); data[88:90] = (0x10b).to_bytes(2, 'little')
        path = farm / name
        path.write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    marker = resources / 'WindowsVR/GraphicsCapabilities.json'
    capability = {'x86Direct3D11': True, 'wow64TransportABI': 1, 'wow64DispatchTableExpectedEntryCount': 148}
    marker.write_text(json.dumps(capability))
    receipt = metadata / 'AVPPLAY_DXMT_D3D12_PROFILE.json'
    receipt.write_text(json.dumps({'x86GuestArtifactsSha256': hashes}))
    def valid(abi=1, count=148):
        return subprocess.run([str(binary), directory, str(abi), str(count)], check=False).returncode == 0
    assert valid(), 'Matching modern x86 package should pass'
    assert not valid(0), 'Absent/unimplemented native WOW64 transport must fail'
    assert not valid(1, 147), 'An incomplete native call table must fail'
    for field, value in [('x86Direct3D11', False), ('x86Direct3D11', 1),
                         ('wow64TransportABI', True), ('wow64TransportABI', 0),
                         ('wow64DispatchTableExpectedEntryCount', 147)]:
        marker.write_text(json.dumps({**capability, field: value}))
        assert not valid(), 'Invalid capability must fail: ' + field
    marker.write_text(json.dumps(capability))
    for name in hashes:
        path = farm / name
        original = path.read_bytes()
        path.write_bytes(original + b'stale')
        assert not valid(), 'Changed modern DLL must fail: ' + name
        path.unlink()
        assert not valid(), 'Missing modern DLL must fail: ' + name
        path.write_bytes(original)
    assert valid()
print('PASS: production modern x86 package gate rejects missing native ABI, incomplete call table, invalid capability and stale/missing i386 DLLs')
