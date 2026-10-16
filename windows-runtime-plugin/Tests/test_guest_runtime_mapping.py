#!/usr/bin/env python3
"""Exercise the production OpenComposite copy against a read-only bundle fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', type=Path, required=True)
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
source = (ROOT / 'windows-runtime-plugin/WindowsVRRuntimePlugin.mm').read_text()
start = source.index('bool CopyGuestOpenComposite(')
brace = source.index('{', start)
end, depth = brace + 1, 1
while depth:
    depth += (source[end] == '{') - (source[end] == '}')
    end += 1
function = source[start:end]
probe = r'''
#import <Foundation/Foundation.h>
#include <cassert>
#include <fstream>
#include <filesystem>
#include <string>
#include <cerrno>
COPY_FUNCTION
int main(int argc, char **argv) { @autoreleasepool {
    assert(argc == 3);
    NSString *source = @(argv[1]), *root = @(argv[2]);
    NSFileManager *fm = NSFileManager.defaultManager;
    NSString *legacy = [root stringByAppendingPathComponent:@"legacy-link"];
    assert([fm createSymbolicLinkAtPath:legacy withDestinationPath:source error:nil]);
    errno = 0;
    std::ofstream denied(std::filesystem::path(legacy.UTF8String) / "bin/applist.json");
    assert(!denied && errno == EACCES);
    std::string error;
    NSString *copy = [root stringByAppendingPathComponent:@"session-a"];
    assert(CopyGuestOpenComposite(source, copy, error));
    assert([[[fm attributesOfItemAtPath:copy error:nil] objectForKey:NSFileType] isEqual:NSFileTypeDirectory]);
    NSString *originalDLL = [source stringByAppendingPathComponent:@"bin/vrclient_x64.dll"];
    NSString *copiedDLL = [copy stringByAppendingPathComponent:@"bin/vrclient_x64.dll"];
    assert([fm contentsEqualAtPath:originalDLL andPath:copiedDLL]);
    std::ofstream settings(std::filesystem::path(copy.UTF8String) / "bin/applist.json");
    assert(settings); settings << "{\"probe\":true}"; settings.close();
    assert(![fm fileExistsAtPath:[source stringByAppendingPathComponent:@"bin/applist.json"]]);
    NSData *saved = [NSData dataWithContentsOfFile:[copy stringByAppendingPathComponent:@"bin/applist.json"]];
    assert(saved.length > 0);
    assert(!CopyGuestOpenComposite(source, copy, error) && !error.empty());
    assert([saved isEqual:[NSData dataWithContentsOfFile:[copy stringByAppendingPathComponent:@"bin/applist.json"]]]);
    NSString *other = [root stringByAppendingPathComponent:@"session-b"];
    assert(CopyGuestOpenComposite(source, other, error));
    assert(![fm fileExistsAtPath:[other stringByAppendingPathComponent:@"bin/applist.json"]]);
    assert(!CopyGuestOpenComposite(@"/nonexistent/wvr-runtime-fixture", [root stringByAppendingPathComponent:@"missing"], error));
    puts("PASS: old bundle symlink denies settings; production copy accepts writes, preserves DLL bytes and source, rejects overwrite and isolates sessions");
} }
'''.replace('COPY_FUNCTION', function)
unit = args.build / 'runtime-copy.mm'
unit.write_text(probe)
binary = args.build / 'runtime-copy'
command = ['xcrun', '--sdk', 'macosx', 'clang++', '-std=c++20', '-fobjc-arc',
           '-fsanitize=address,undefined', '-g', str(unit), '-framework', 'Foundation', '-o', str(binary)]
subprocess.run(command, check=True)
with tempfile.TemporaryDirectory(prefix='runtime-copy-', dir=args.build) as directory:
    root = Path(directory)
    bundle = root / 'bundle/OpenComposite'
    (bundle / 'bin').mkdir(parents=True)
    dll = bundle / 'bin/vrclient_x64.dll'
    dll.write_bytes(b'PE fixture: byte preservation only; not a loadable DLL')
    dll.chmod(0o444)
    (bundle / 'bin').chmod(0o555)
    bundle.chmod(0o555)
    try:
        subprocess.run([str(binary), str(bundle), str(root)], check=True)
    finally:
        bundle.chmod(0o755)
        (bundle / 'bin').chmod(0o755)
(args.build / 'result.json').write_text(json.dumps({
    'status': 'pass', 'scope': 'Real Foundation filesystem behavior and production copy helper with ASan/UBSan; no Windows/OpenXR execution',
    'runtimePluginSourceSha256': hashlib.sha256(source.encode()).hexdigest(),
    'probeSha256': hashlib.sha256(unit.read_bytes()).hexdigest(), 'command': command
}, indent=2) + '\n')
