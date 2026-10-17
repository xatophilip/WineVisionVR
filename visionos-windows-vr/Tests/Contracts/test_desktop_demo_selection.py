#!/usr/bin/env python3
"""Compile real x64/i386 GDI fixtures and run the production Swift selector.

No Wine, Windows executable or headset is run. The Swift probe uses actual
fixture files in isolated resource/document directories; only the app shell is
stubbed. It checks architecture selection, note isolation and unsafe targets.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True, type=Path)
args = parser.parse_args()
build = args.build.resolve()
build.mkdir(parents=True, exist_ok=True)
launcher = (ROOT / 'visionos-windows-vr/Sources/LauncherModel.swift').read_text()
selector = 'func selectDesktopDemo(' + launcher.split('func selectDesktopDemo(', 1)[1].split('    func selectVRSmoke(', 1)[0]
view = (ROOT / 'visionos-windows-vr/Sources/ContentView.swift').read_text()
branch = view.split('ProcessInfo.processInfo.arguments.contains("--desktop-smoke-test")', 1)[1].split('} else if LaunchDiagnostics.enabled', 1)[0]
assert 'ProcessInfo.processInfo.arguments.contains("--x86-guest") ? .x86 : nil' in branch
assert 'LaunchDiagnostics.enabled,' in view.split('ProcessInfo.processInfo.arguments.contains("--desktop-smoke-test")', 1)[0][-80:]
assert 'try model.selectDesktopDemo()' in view  # Ordinary launcher button remains x64.

scratch = Path(tempfile.mkdtemp(prefix='run-', dir=build))
resources = scratch / 'resources'
for arch, folder, machine in [('x64', 'DesktopDemo', 0x8664), ('x86', 'DesktopDemoX86', 0x14c)]:
    env = os.environ.copy()
    env.update(AVPPLAY_DESKTOP_DEMO_ARCH=arch, AVPPLAY_DESKTOP_DEMO_OUTPUT=str(resources / folder))
    subprocess.run(['bash', str(ROOT / 'windows-vr-tools/build_desktop_demo.sh')], env=env, check=True)
    data = (resources / folder / 'desktop-demo.exe').read_bytes()
    pe = int.from_bytes(data[60:64], 'little')
    assert int.from_bytes(data[pe + 4:pe + 6], 'little') == machine
    receipt = json.loads((resources / folder / 'build.json').read_text())
    assert receipt['architecture'] == arch and receipt['executed'] is False
manifest = (ROOT / 'windows-vr/Sources/WindowsVRCore/WindowsGameManifest.swift').read_text()
probe = r'''
import Foundation
PRODUCTION_MANIFEST
func L(_ english: String, _ german: String) -> String { english }
func check(_ value: @autoclosure () throws -> Bool, _ message: String) throws {
    if try !value() { fatalError(message) }
}
let scratch = URL(fileURLWithPath: CommandLine.arguments[1])
struct Bundle {
    static var main = Bundle()
    var missing: String?
    func url(forResource name: String, withExtension ext: String?) -> URL? {
        if missing == name { return nil }
        return scratch.appendingPathComponent("resources/" + name)
    }
}
struct FileManager {
    static let `default` = FileManager()
    func urls(for directory: Foundation.FileManager.SearchPathDirectory,
              in domain: Foundation.FileManager.SearchPathDomainMask) -> [URL] {
        [scratch.appendingPathComponent("Documents")]
    }
    func createDirectory(at url: URL, withIntermediateDirectories value: Bool) throws {
        try Foundation.FileManager.default.createDirectory(at: url, withIntermediateDirectories: value)
    }
}
enum ImportFailure: Error { case folderAccessDenied }
final class Probe {
    var canChangeSelection = true
    var manifest: WindowsGameManifest?
    var manifestName: String?
    var gameDirectory: URL?
    var gameFolderName: String?
    var presentationModeDraft = WindowsPresentationMode.immersiveVR
    var selectedLibraryEntryID: UUID?
    var selectedProfileID: UUID?
    var renderScaleDraft = 0.5
    var launchArgumentsText = "unrelated"
    var launchError: String? = "old failure"
    var releases = 0
    func releaseGameDirectoryAccess() { releases += 1 }
    func isAppOwnedURL(_ url: URL) -> Bool {
        url.path.hasPrefix(scratch.appendingPathComponent("Documents").path + "/")
    }
    PRODUCTION_SELECTOR
}
let probe = Probe()
try probe.selectDesktopDemo()
try check(probe.manifest?.id == "winevision.desktop-demo" && probe.manifest?.guestArchitecture == nil,
          "Default selection must retain the original 64-bit demo")
try check(probe.gameDirectory?.lastPathComponent == "DesktopDemo" && probe.presentationModeDraft == .desktop,
          "Default app must use its existing desktop folder")
let original = probe.gameDirectory!
try Data("keep my note".utf8).write(to: original.appendingPathComponent("demo-note.txt"))
try probe.selectDesktopDemo(architecture: .x86)
let x86 = probe.gameDirectory!
try check(probe.manifest?.id == "winevision.desktop-demo-x86" && probe.manifest?.guestArchitecture == .x86,
          "Explicit 32-bit selection must carry its own identity and architecture")
try check(x86.lastPathComponent == "DesktopDemoX86" && x86 != original,
          "32-bit test must have a separate persistent directory/prefix identity")
try check(probe.launchArgumentsText == "[]" && probe.launchError == nil && probe.renderScaleDraft == 1,
          "Selecting a fixture must clear previous launch state")
try Data("32-bit note".utf8).write(to: x86.appendingPathComponent("demo-note.txt"))
try probe.selectDesktopDemo(architecture: .x86)
try check(String(data: Data(contentsOf: x86.appendingPathComponent("demo-note.txt")), encoding: .utf8) == "32-bit note",
          "Repeat selection must preserve the 32-bit note")
try check(String(data: Data(contentsOf: original.appendingPathComponent("demo-note.txt")), encoding: .utf8) == "keep my note",
          "32-bit selection must never replace the ordinary demo's note")
let before = probe.releases
probe.canChangeSelection = false
try probe.selectDesktopDemo()
try check(probe.releases == before && probe.gameDirectory == x86,
          "A running session must prevent fixture reselection")
probe.canChangeSelection = true
Bundle.main.missing = "DesktopDemoX86"
do { try probe.selectDesktopDemo(architecture: .x86); fatalError("Missing x86 fixture silently fell back") }
catch let error as CocoaError { try check(error.code == .fileNoSuchFile, "Expected a missing-resource error") }
Bundle.main.missing = nil
do { try probe.selectDesktopDemo(architecture: .arm64ec); fatalError("Unsupported ARM64EC fixture accepted") }
catch WindowsGameManifestError.invalidLaunchConfiguration {}
let executable = x86.appendingPathComponent("desktop-demo.exe")
try Foundation.FileManager.default.removeItem(at: executable)
let outside = scratch.appendingPathComponent("outside.exe")
try Data([7, 8, 9]).write(to: outside)
try Foundation.FileManager.default.createSymbolicLink(at: executable, withDestinationURL: outside)
do { try probe.selectDesktopDemo(architecture: .x86); fatalError("Symlink executable was overwritten") }
catch ImportFailure.folderAccessDenied {}
try check(Data(contentsOf: outside) == Data([7, 8, 9]), "Selection changed a file outside its owned folder")
print("PASS: production desktop selector, real x64/i386 fixtures, default preservation, note isolation, missing/unsupported resource and symlink rejection")
'''
probe = probe.replace('PRODUCTION_MANIFEST', manifest).replace('PRODUCTION_SELECTOR', selector)
unit = build / 'main.swift'
unit.write_text(probe)
subprocess.run(['swiftc', str(unit), '-o', str(build / 'selection-probe')], check=True)
subprocess.run([str(build / 'selection-probe'), str(scratch)], check=True)
