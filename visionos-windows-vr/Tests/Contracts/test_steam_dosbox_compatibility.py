#!/usr/bin/env python3
"""Exercise the real Swift DOSBox adapter/resolver on owned temporary files.

No Steam credentials, game assets, Wine execution or gameplay are involved.
Optionally parse the exact returned command line with pinned Wine's actual
CommandLineToArgvW, compiled natively with ASan/UBSan and allocator/API stubs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--build', required=True, type=Path)
p.add_argument('--wine-source', type=Path)
a = p.parse_args()
a.build.mkdir(parents=True, exist_ok=True)
scratch = Path(tempfile.mkdtemp(prefix='run-', dir=a.build.resolve()))
helper = (ROOT/'visionos-windows-vr/Sources/Steam/SteamDOSBoxCompatibility.swift').read_text()
resolver = (ROOT/'visionos-windows-vr/Sources/Steam/SteamInstalledExecutable.swift').read_text()
launcher = (ROOT/'visionos-windows-vr/Sources/LauncherModel.swift').read_text()
compatibility = 'nonisolated static func steamCompatibilityEnvironment(' + launcher.split(
    'nonisolated static func steamCompatibilityEnvironment(',1)[1].split("    /// Steam's 64-bit launch host",1)[0]
# The config must be prepared before credentials are written to the one-use handoff.
start = launcher.index('let arguments = try SteamDOSBoxCompatibility.prepare(')
assert start < launcher.index('try MadeiraDock.writeHandoff(', start) < launcher.index('argumentsOverride: arguments',start)
shell = r'''
import Foundation
struct DockGame { var id: Int; var library: String; var installDir: String }
struct SteamLaunchOption { var executable: String; var index: UInt32 = 0 }
enum DockError: Error { case message(String) }
'''
probe = r'''
func check(_ condition: @autoclosure () throws -> Bool, _ message: String) throws {
    if try !condition() { fatalError(message) }
}
let root = URL(fileURLWithPath: CommandLine.arguments[1])
let fm = FileManager.default
func write(_ path: URL, _ text: String) throws {
    try fm.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true)
    try Data(text.utf8).write(to: path)
}
let game = DockGame(id: 224960, library: "Steam/steamapps", installDir: "Tomb Raider I")
let folder = root.appendingPathComponent("Steam/steamapps/common/Tomb Raider I", isDirectory: true)
let owned = ["dosbox.exe", "dosboxTRWindowed.conf", "GAME.DAT", "TOMBRAID/TOMBno3Dfx.EXE", "dosbox.conf", "TOMBRAID/SETTINGS.DAT"]
for name in owned { try write(folder.appendingPathComponent(name), "installed fixture: " + name) }
let originals = try Dictionary(uniqueKeysWithValues: owned.map { ($0, try Data(contentsOf: folder.appendingPathComponent($0))) })
let manifest = root.appendingPathComponent("Steam/steamapps/appmanifest_224960.acf")
try write(manifest, "owned appmanifest fixture; never modify")
let manifestBefore = try Data(contentsOf: manifest)
let expectedArguments = "-conf \"C:\\AVPPlaySteam\\Compatibility\\224960\\software.conf\" -noautoexec -c \"mount C .\" -c \"imgmount d GAME.DAT -t iso -fs iso\" -c \"C:\" -c \"cd TOMBRAID\" -c \"TOMBNO~1.EXE\""
let expectedSettings = "[sdl]\nfullscreen=false\noutput=surface\nautolock=false\n[render]\nscaler=normal2x\n[glide]\nglide=false\n[ne2000]\nne2000=false\n"
let settings = root.appendingPathComponent("AVPPlaySteam/Compatibility/224960/software.conf")
let option = SteamLaunchOption(executable: "DOSBox.exe", index: 1)
for executable in ["DOSBox.exe", "dosbox.exe", ".\\DOSBox.exe", "./dosbox.exe"] {
    let actual = try SteamDOSBoxCompatibility.prepare(game: game, option: SteamLaunchOption(executable: executable), drive: root)
    try check(actual == expectedArguments, "Exact proven extra arguments and command ordering must remain unchanged")
}
try check(Data(contentsOf: settings) == Data(expectedSettings.utf8), "Exact app-owned software settings differ")
for name in owned {
    try check(Data(contentsOf: folder.appendingPathComponent(name)) == originals[name], "Installed file was modified: " + name)
}
try check(Data(contentsOf: manifest) == manifestBefore, "Steam appmanifest was changed")
try Data("stale owned config".utf8).write(to: settings)
_ = try SteamDOSBoxCompatibility.prepare(game: game, option: option, drive: root)
try check(Data(contentsOf: settings) == Data(expectedSettings.utf8), "Owned config must refresh atomically")
// Scope includes the selected executable, not merely a game label or option index.
for id in [0, 428370, 412740] {
    let other = DockGame(id: id, library: game.library, installDir: game.installDir)
    try check(SteamDOSBoxCompatibility.prepare(game: other, option: option, drive: root) == nil, "Unrelated app received DOSBox arguments")
}
for executable in ["tombati.exe", "tombub.exe", "Tools/DOSBox.exe", "../DOSBox.exe", "C:\\DOSBox.exe"] {
    try check(SteamDOSBoxCompatibility.prepare(game: game, option: SteamLaunchOption(executable: executable), drive: root) == nil,
              "Unsupported launch option received DOSBox arguments")
}
do { _ = try SteamDOSBoxCompatibility.prepare(game: game, option: nil, drive: root); fatalError("Missing Tomb Raider launch metadata silently used vendor Glide recipe") }
catch DockError.message {}
let otherWithoutOption = DockGame(id: 428370, library: game.library, installDir: game.installDir)
try check(SteamDOSBoxCompatibility.prepare(game: otherWithoutOption, option: nil, drive: root) == nil, "Missing metadata for unrelated games must remain unchanged")
let inherited = ["KEEP": "yes"]
try check(CompatibilityProbe.steamCompatibilityEnvironment(appID: 224960, base: inherited, optionExecutable: "DOSBox.exe") == ["KEEP":"yes", "SDL_VIDEODRIVER":"windib"], "DOSBox must select windib only for this route")
try check(CompatibilityProbe.steamCompatibilityEnvironment(appID: 224960, base: inherited, optionExecutable: "tombati.exe") == inherited, "Native Tomb Raider route inherited DOSBox environment")
try check(CompatibilityProbe.steamCompatibilityEnvironment(appID: 428370, base: inherited, optionExecutable: "dosbox.exe") == ["KEEP":"yes", "OPENSSL_ia32cap":"0"], "Working Windlands setting changed")
try check(CompatibilityProbe.steamCompatibilityEnvironment(appID: 412740, base: inherited, optionExecutable: "dosbox.exe") == inherited, "Another DOSBox executable got a global override")
// Every required file must fail before overwriting the existing owned config.
for name in ["dosbox.exe", "dosboxTRWindowed.conf", "GAME.DAT", "TOMBRAID/TOMBno3Dfx.EXE"] {
    let path = folder.appendingPathComponent(name), saved = try Data(contentsOf: path)
    try fm.removeItem(at: path)
    do { _ = try SteamDOSBoxCompatibility.prepare(game: game, option: option, drive: root); fatalError("Incomplete game silently accepted: " + name) }
    catch DockError.message {}
    try check(Data(contentsOf: settings) == Data(expectedSettings.utf8), "Failed preparation changed owned settings")
    try saved.write(to: path)
}
for name in ["TOMBNO~1.EXE", "TOMBnoOther.EXE"] {
    let competitor = folder.appendingPathComponent("TOMBRAID/"+name)
    try write(competitor, "competing DOS name")
    do { _ = try SteamDOSBoxCompatibility.prepare(game: game, option: option, drive: root); fatalError("Ambiguous DOS short name accepted") }
    catch DockError.message {}
    try fm.removeItem(at: competitor)
}
let outside = root.appendingPathComponent("outside-owned-fixture")
try fm.createDirectory(at: outside, withIntermediateDirectories: true)
let outsideFile = outside.appendingPathComponent("untouched.conf")
try write(outsideFile,"untouched")
try fm.removeItem(at: settings)
try fm.createSymbolicLink(at: settings, withDestinationURL: outsideFile)
do { _ = try SteamDOSBoxCompatibility.prepare(game: game, option: option, drive: root); fatalError("Output symlink accepted") }
catch DockError.message {}
try check(Data(contentsOf: outsideFile) == Data("untouched".utf8), "Output symlink target was modified")
try fm.removeItem(at: settings)
let compatibilityFolder = root.appendingPathComponent("AVPPlaySteam/Compatibility/224960")
try fm.removeItem(at: compatibilityFolder)
try fm.createSymbolicLink(at: compatibilityFolder, withDestinationURL: outside)
do { _ = try SteamDOSBoxCompatibility.prepare(game: game, option: option, drive: root); fatalError("Output directory symlink accepted") }
catch DockError.message {}
try check(!fm.fileExists(atPath: outside.appendingPathComponent("software.conf").path), "Output directory symlink was followed")
try fm.removeItem(at: compatibilityFolder)
_ = try SteamDOSBoxCompatibility.prepare(game: game, option: option, drive: root)
// A legitimate installed case variant must not be mistaken for a competing DOS name.
let software = folder.appendingPathComponent("TOMBRAID/TOMBno3Dfx.EXE")
let variant = folder.appendingPathComponent("TOMBRAID/tombno3dfx.exe")
let held = folder.appendingPathComponent("TOMBRAID/rename-temporary.exe")
try fm.moveItem(at: software, to: held);try fm.moveItem(at: held, to: variant)
var caseVariantAccepted = false
var caseVariantError = ""
do { caseVariantAccepted = try SteamDOSBoxCompatibility.prepare(game: game, option: option, drive: root) == expectedArguments }
catch { caseVariantError = String(describing: error) }
let evidence: [String:Any] = ["arguments":expectedArguments, "settings":expectedSettings,
    "installedFilesUnchanged":true, "appManifestUnchanged":true,
    "caseVariantAccepted":caseVariantAccepted, "caseVariantError":caseVariantError]
try JSONSerialization.data(withJSONObject:evidence,options:[.prettyPrinted,.sortedKeys]).write(to:root.appendingPathComponent("probe-result.json"))
print("PASS: actual DOSBox adapter/resolver, exact arguments/settings, app+option scoping, installed-file preservation, missing content, DOS short-name ambiguity and output symlink rejection")
try check(caseVariantAccepted, "Legitimate case variant rejected: " + caseVariantError)
'''
source=shell+resolver+helper+'\nenum CompatibilityProbe {\n'+compatibility+'\n}\n'+probe
unit=scratch/'main.swift';binary=scratch/'probe';unit.write_text(source)
command=['xcrun','--sdk','macosx','swiftc','-O','-module-cache-path',str(scratch/'cache'),str(unit),'-o',str(binary)]
subprocess.run(command,check=True)
subprocess.run([str(binary),str(scratch/'drive')],check=True)
result=json.loads((scratch/'drive/probe-result.json').read_text())
result.update(scope='Actual production Swift helper, executable resolver and scoped environment on owned fixture files. No Wine execution or gameplay.',passed=True,command=command,
              helperSha256=hashlib.sha256(helper.encode()).hexdigest(),resolverSha256=hashlib.sha256(resolver.encode()).hexdigest())

# Optional: actual pinned Wine Win32 argument parsing, rather than POSIX shlex.
wine=a.wine_source
if wine is None:
    for name in ('AVPPLAY_D3D12_PROFILE_SOURCE','AVPPLAY_RUNTIME_SOURCE'):
        if os.environ.get(name) and (Path(os.environ[name])/'wine/dlls/shcore/main.c').is_file():
            wine=Path(os.environ[name])/'wine';break
if wine is None and (ROOT/'third-party/madeira/wine/dlls/shcore/main.c').is_file():wine=ROOT/'third-party/madeira/wine'
if wine is not None:
    text=(wine/'dlls/shcore/main.c').read_text()
    start=text.index('WCHAR** WINAPI CommandLineToArgvW(');opening=text.index('{',start);end=opening+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    parser=text[start:end]
    prelude=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint16_t WCHAR;
typedef unsigned DWORD;
#define WINAPI
#define ERROR_INVALID_PARAMETER 87
#define MAX_PATH 260
#define LMEM_FIXED 0
static void SetLastError(unsigned e) { (void)e; }
static void *LocalAlloc(unsigned f,size_t n) { (void)f;return malloc(n); }
static void LocalFree(void *p) { free(p); }
static DWORD GetModuleFileNameW(unsigned h,WCHAR *p,DWORD n) { (void)h;(void)p;(void)n;abort(); }
static unsigned lstrlenW(const WCHAR *p) { unsigned n=0;while(p[n])++n;return n; }
static WCHAR *lstrcpyW(WCHAR *d,const WCHAR *s) { WCHAR *p=d;while((*p++=*s++)) {} return d; }
'''
    main=r'''
int main(int argc,char **argv) {
 assert(argc==2);size_t n=strlen(argv[1]);WCHAR *line=calloc(n+1,sizeof(*line));assert(line);
 for(size_t i=0;i<n;++i){assert((unsigned char)argv[1][i]<128);line[i]=(unsigned char)argv[1][i];}
 int count;WCHAR **args=CommandLineToArgvW(line,&count);assert(args);
 for(int i=0;i<count;++i){for(WCHAR *c=args[i];*c;++c)putchar((char)*c);putchar('\n');}
 LocalFree(args);free(line);
}
'''
    c=scratch/'argv.c';exe=scratch/'argv';c.write_text(prelude+parser+main)
    subprocess.run(['xcrun','clang','-std=c11','-O1','-g','-fsanitize=address,undefined',str(c),'-o',str(exe)],check=True)
    vendor='"C:\\Program Files (x86)\\Steam\\steamapps\\common\\Tomb Raider I\\DOSBox.exe" -conf dosbox.conf -conf dosboxTRWindowed.conf -noconsole '
    parsed=subprocess.check_output([str(exe),vendor+result['arguments']],text=True).splitlines()
    expected=[r'C:\Program Files (x86)\Steam\steamapps\common\Tomb Raider I\DOSBox.exe','-conf','dosbox.conf','-conf','dosboxTRWindowed.conf','-noconsole','-conf',r'C:\AVPPlaySteam\Compatibility\224960\software.conf','-noautoexec','-c','mount C .','-c','imgmount d GAME.DAT -t iso -fs iso','-c','C:','-c','cd TOMBRAID','-c','TOMBNO~1.EXE']
    assert parsed==expected,(parsed,expected)
    result.update(win32Arguments=parsed,win32ParserSourceSha256=hashlib.sha256(parser.encode()).hexdigest(),win32ParserPassed=True)
    print('PASS: actual pinned Wine CommandLineToArgvW preserves vendor arguments and exact extra DOSBox command boundaries')
else:
    result['win32ParserSkipped']='Supply --wine-source or a prepared runtime to compile actual Wine CommandLineToArgvW'
    print('SKIP: actual pinned Wine argument parser; no Wine source available')
(a.build/'result.json').write_text(json.dumps(result,indent=2)+'\n')
