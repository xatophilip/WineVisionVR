#!/usr/bin/env python3
"""Execute production desktop request parsing/readiness on the Mac, without Wine."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', type=Path, default=ROOT / '.build-desktop-contract')
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
source = (ROOT / 'windows-runtime-plugin/WindowsVRRuntimePlugin.mm').read_text()

def function(signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

request = source[source.index('struct LaunchRequest {'):source.index('\n};', source.index('struct LaunchRequest {')) + 3]
pieces = [request, *(function(signature) for signature in (
    'bool PresentationIsReady(', 'bool IsString(', 'bool ReadString(',
    'bool IsAllowedEnvironmentKey(', 'bool ParseRequest('))]
probe = r'''
int main() {
    @autoreleasepool {
        NSMutableDictionary *base = [@{
            @"schemaVersion": @1, @"gameID": @"desktop-test",
            @"backend": @"windowsWineFEX", @"graphics": @"direct3D11",
            @"gameDirectory": @"/tmp/app", @"executablePath": @"/tmp/app/demo.exe",
            @"arguments": @[], @"environment": @{}
        } mutableCopy];
        auto parse = [&](NSDictionary *dict, LaunchRequest &request) {
            NSData *data = [NSJSONSerialization dataWithJSONObject:dict options:0 error:nil];
            std::string json((const char *)data.bytes, data.length), error;
            return ParseRequest(json.c_str(), request, error);
        };
        LaunchRequest legacy;
        assert(parse(base, legacy) && legacy.presentation == "immersiveVR");
        base[@"presentation"] = @"desktop";
        LaunchRequest desktop;
        assert(parse(base, desktop) && desktop.presentation == "desktop");
        for (id invalid in @[@"unknown", @"", @1, @YES, NSNull.null, @[], @{}]) {
            base[@"presentation"] = invalid;
            LaunchRequest rejected;
            assert(!parse(base, rejected));
        }
        base[@"presentation"] = @"desktop";
        for (NSString *reserved in @[@"MADEIRA_DESKTOP", @"WVR_REQUIRE_COMPOSITOR_DEVICE", @"XR_RUNTIME_JSON"]) {
            base[@"environment"] = @{reserved: @"override"};
            LaunchRequest rejected;
            assert(!parse(base, rejected));
        }
        WVRCompositorReadinessV1 readiness{};
        assert(!PresentationIsReady(desktop, readiness));
        assert(!PresentationIsReady(legacy, readiness));
        readiness.metalDeviceBound = 1;
        assert(PresentationIsReady(desktop, readiness));
        assert(!PresentationIsReady(legacy, readiness));
        readiness.stereoTargetsPublished = 1;
        assert(PresentationIsReady(desktop, readiness));
        assert(PresentationIsReady(legacy, readiness));
        readiness.metalDeviceBound = 0;
        assert(!PresentationIsReady(desktop, readiness));
        assert(!PresentationIsReady(legacy, readiness));
        puts("PASS: production desktop/legacy parsing, invalid requests, reserved environment and Metal/stereo readiness");
    }
}
'''
unit = args.build / 'desktop-contract.mm'
unit.write_text('#import <Foundation/Foundation.h>\n#include <cassert>\n#include <cstring>\n'
                '#include <string>\n#include <vector>\n#include <utility>\n'
                '#include "WindowsVRCompositorBridge.h"\n' + '\n'.join(pieces) + probe)
binary = args.build / 'desktop-contract'
command = ['xcrun', '--sdk', 'macosx', 'clang++', '-std=c++20', '-fobjc-arc',
           '-fsanitize=address,undefined', '-g', '-I' + str(ROOT / 'windows-vr-native/include'),
           str(unit), '-framework', 'Foundation', '-o', str(binary)]
subprocess.run(command, check=True)
subprocess.run([str(binary)], check=True)
(args.build / 'result.json').write_text(json.dumps({
    'status': 'pass', 'scope': 'Host production parser/readiness contract with ASan/UBSan; no guest execution',
    'runtimePluginSourceSha256': hashlib.sha256(source.encode()).hexdigest(),
    'extractedProbeSha256': hashlib.sha256(unit.read_bytes()).hexdigest(),
    'command': command
}, indent=2) + '\n')
