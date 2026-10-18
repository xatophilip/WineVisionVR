#!/usr/bin/env python3
"""Execute production desktop parsing, readiness and monitor setup on the Mac.

Optionally compile the prepared runtime's actual Wine monitor-size reader too.
No Windows process, GUI, headset or runtime engine build is started.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', type=Path, default=ROOT / '.build-desktop-contract')
parser.add_argument('--runtime-source', type=Path, help='Prepared Madeira source for actual Wine monitor reader')
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
source = (ROOT / 'windows-runtime-plugin/WindowsVRRuntimePlugin.mm').read_text()

def function(signature, text=source):
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

request = source[source.index('struct LaunchRequest {'):source.index('\n};', source.index('struct LaunchRequest {')) + 3]
environment = next(line for line in source.splitlines() if line.startswith('std::map<std::string, std::optional<std::string>> g_originalEnvironment'))
pieces = [request, environment, 'static int wine_process_is_running() { return 0; }', *(function(signature) for signature in (
    'bool PresentationIsReady(', 'bool IsString(', 'bool ReadString(',
    'bool IsAllowedEnvironmentKey(', 'bool ParseRequest(',
    'uint16_t RuntimeGuestMachine(', 'bool SupportsPersistentFEXCache(',
    'void SetLaunchEnvironment(', 'void ConfigurePresentationEnvironment('))]
pieces.append(function('struct LaunchScope {') + ';')
run = function('int32_t RunRequest(')
assert run.index('ConfigurePresentationEnvironment(request);') < run.index('wineserver_start(')
runtime_screen = None
if args.runtime_source:
    runtime_screen = args.runtime_source / 'build/win32u-unix/sysparams_ios.c'
    screen = runtime_screen.read_text()
    globals_start = screen.index('static int ios_screen_cur_w, ios_screen_cur_h;')
    globals_end = screen.index('static void ios_screen_size(', globals_start)
    pieces += ['#define TEST_RUNTIME_SCREEN 1', screen[globals_start:globals_end],
               function('static void ios_screen_size(', screen)]
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
        for (NSString *arch in @[@"x86", @"x64", @"arm64ec"]) {
            base[@"guestArchitecture"] = arch;
            LaunchRequest selected;
            assert(parse(base, selected) && selected.guestArchitecture == arch.UTF8String);
        }
        for (id invalid in @[@"other", @1, NSNull.null, @[]]) {
            base[@"guestArchitecture"] = invalid;
            LaunchRequest rejected;
            assert(!parse(base, rejected));
        }
        [base removeObjectForKey:@"guestArchitecture"];
        base[@"presentation"] = @"desktop";
        for (NSString *reserved in @[@"MADEIRA_DESKTOP", @"MADEIRA_SCREEN_W", @"MADEIRA_SCREEN_H",
                                    @"MADEIRA_SCREEN_SRC", @"WVR_REQUIRE_COMPOSITOR_DEVICE", @"XR_RUNTIME_JSON"]) {
            base[@"environment"] = @{reserved: @"override"};
            LaunchRequest rejected;
            assert(!parse(base, rejected));
        }
        // A 64-bit Steam launcher can start a 32-bit child: classify the child,
        // not just dockhost.exe, before enabling the 64-bit offline compiler.
        LaunchRequest cacheRequest;
        cacheRequest.backend = "windowsWineFEX";
        assert(SupportsPersistentFEXCache(cacheRequest, 0x8664));
        assert(!SupportsPersistentFEXCache(cacheRequest, 0x014c));
        cacheRequest.guestArchitecture = "x86";
        assert(!SupportsPersistentFEXCache(cacheRequest, 0x8664));
        cacheRequest.guestArchitecture = "arm64ec";
        assert(SupportsPersistentFEXCache(cacheRequest, 0x8664));
        cacheRequest.backend = "nativeARM64";
        assert(!SupportsPersistentFEXCache(cacheRequest, 0xA641));
        // Use the production environment writer and scope against the actual
        // process environment. Inherited VR dimensions must stay untouched.
        setenv("MADEIRA_DESKTOP", "host-mode", 1);
        setenv("MADEIRA_SCREEN_W", "2048", 1);
        setenv("MADEIRA_SCREEN_H", "1152", 1);
        setenv("MADEIRA_SCREEN_SRC", "host-vr", 1);
        setenv("VR_OVERRIDE", "host-vr-runtime", 1);
        setenv("XR_RUNTIME_JSON", "host-xr-runtime", 1);
        {
            LaunchScope scope;
            ConfigurePresentationEnvironment(legacy);
            assert(!strcmp(getenv("MADEIRA_DESKTOP"), "0"));
            assert(!strcmp(getenv("MADEIRA_SCREEN_W"), "2048"));
            assert(!strcmp(getenv("MADEIRA_SCREEN_H"), "1152"));
            assert(!strcmp(getenv("MADEIRA_SCREEN_SRC"), "host-vr"));
            assert(!strcmp(getenv("VR_OVERRIDE"), "host-vr-runtime"));
#ifdef TEST_RUNTIME_SCREEN
            ios_screen_cur_w = ios_screen_cur_h = 0;
            int width, height;
            ios_screen_size(&width, &height);
            assert(width == 2048 && height == 1152);
#endif
        }
        assert(g_originalEnvironment.empty());
        for (const char *architecture : {"x64", "x86"}) {
            desktop.guestArchitecture = architecture;
            LaunchScope scope;
            ConfigurePresentationEnvironment(desktop);
            assert(!strcmp(getenv("MADEIRA_DESKTOP"), "1"));
            assert(!strcmp(getenv("MADEIRA_SCREEN_W"), "1280"));
            assert(!strcmp(getenv("MADEIRA_SCREEN_H"), "720"));
            assert(!strcmp(getenv("MADEIRA_SCREEN_SRC"), "winevision-desktop-720p"));
            assert(!getenv("VR_OVERRIDE") && !getenv("XR_RUNTIME_JSON"));
#ifdef TEST_RUNTIME_SCREEN
            ios_screen_cur_w = ios_screen_cur_h = 0;
            int width, height;
            ios_screen_size(&width, &height);
            assert(width == 1280 && height == 720);
#endif
        }
        assert(g_originalEnvironment.empty());
        assert(!strcmp(getenv("MADEIRA_DESKTOP"), "host-mode"));
        assert(!strcmp(getenv("MADEIRA_SCREEN_W"), "2048"));
        assert(!strcmp(getenv("MADEIRA_SCREEN_H"), "1152"));
        assert(!strcmp(getenv("MADEIRA_SCREEN_SRC"), "host-vr"));
        assert(!strcmp(getenv("VR_OVERRIDE"), "host-vr-runtime"));
        assert(!strcmp(getenv("XR_RUNTIME_JSON"), "host-xr-runtime"));
        puts("PASS: x64/x86 desktop seeds 1280x720, VR dimensions preserved, environment restored after session");
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
                '#include <map>\n#include <optional>\n#include <cstdlib>\n'
                '#include "WindowsVRDesktop.h"\n'
                '#include "WindowsVRCompositorBridge.h"\n' + '\n'.join(pieces) + probe)
binary = args.build / 'desktop-contract'
command = ['xcrun', '--sdk', 'macosx', 'clang++', '-std=c++20', '-fobjc-arc',
           '-fsanitize=address,undefined', '-g', '-I' + str(ROOT / 'windows-vr-native/include'),
           '-I' + str(ROOT / 'windows-vr/include'),
           str(unit), '-framework', 'Foundation', '-o', str(binary)]
subprocess.run(command, check=True)
subprocess.run([str(binary)], check=True)
# Execute the real legacy Steam virtual-desktop argument helper with the
# shared C constants imported by Swift, including its installer chain.
dock = (ROOT / 'visionos-windows-vr/Sources/Steam/MadeiraDock.swift').read_text()
executable = next(line for line in dock.splitlines() if line.strip().startswith('static let executable ='))
arguments = function('static func launchArguments(', dock)
swift = args.build / 'desktop-arguments.swift'
swift.write_text('import Foundation\nenum MadeiraDock {\n' + executable + '\n' + arguments + '\n}\n' + r'''
precondition(MadeiraDock.launchArguments() == "/desktop=madeira,1280x720 C:\\windows\\system32\\dockhost.exe")
precondition(MadeiraDock.launchArguments(installers: "C:\\install.cmd") == "/desktop=madeira,1280x720 C:\\windows\\system32\\cmd.exe /c call C:\\install.cmd & C:\\windows\\system32\\dockhost.exe")
print("PASS: production Steam virtual desktop arguments use 1280x720 with and without installer chain")
''')
arguments_binary = args.build / 'desktop-arguments'
subprocess.run(['xcrun', 'swiftc', '-import-objc-header', str(ROOT / 'windows-vr/include/WindowsVRDesktop.h'),
                str(swift), '-o', str(arguments_binary)], check=True)
subprocess.run([str(arguments_binary)], check=True)
(args.build / 'result.json').write_text(json.dumps({
    'status': 'pass', 'scope': 'Host production parser/readiness/monitor environment with ASan/UBSan and Steam launch geometry; no guest execution',
    'runtimeScreenSourceSha256': hashlib.sha256(runtime_screen.read_bytes()).hexdigest() if runtime_screen else None,
    'desktopGeometryHeaderSha256': hashlib.sha256((ROOT / 'windows-vr/include/WindowsVRDesktop.h').read_bytes()).hexdigest(),
    'runtimePluginSourceSha256': hashlib.sha256(source.encode()).hexdigest(),
    'extractedProbeSha256': hashlib.sha256(unit.read_bytes()).hexdigest(),
    'command': command
}, indent=2) + '\n')
