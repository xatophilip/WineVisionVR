#!/usr/bin/env python3
"""Compile mixed/direct PE fixtures and exercise the actual diagnostic selector."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--build', required=True, type=Path)
a = p.parse_args()
build = a.build.resolve()
build.mkdir(parents=True, exist_ok=True)
scratch = Path(tempfile.mkdtemp(prefix='run-', dir=build))
resources = scratch / 'resources/MixedArchitectureChild'
env = os.environ.copy()
env['AVPPLAY_MIXED_CHILD_OUTPUT'] = str(resources)
subprocess.run(['bash', str(ROOT / 'windows-vr-tools/build_mixed_architecture_child.sh')], env=env, check=True)
receipt = json.loads((resources / 'build.json').read_text())
assert receipt['executed'] is False
launcher = (ROOT / 'visionos-windows-vr/Sources/LauncherModel.swift').read_text()
selector = 'func selectMixedArchitectureChildTest(' + launcher.split('func selectMixedArchitectureChildTest(', 1)[1].split('    func waitForCompositorReady(', 1)[0]
view = (ROOT / 'visionos-windows-vr/Sources/ContentView.swift').read_text()
branch = view.split('ProcessInfo.processInfo.arguments.contains("--mixed-architecture-child-test")', 1)[1].split('} else if LaunchDiagnostics.enabled', 1)[0]
assert 'ProcessInfo.processInfo.arguments.contains("--direct-child-control")' in branch
assert 'LaunchDiagnostics.enabled,' in view.split('ProcessInfo.processInfo.arguments.contains("--mixed-architecture-child-test")', 1)[0][-100:]
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
    func removeItem(at url: URL) throws { try Foundation.FileManager.default.removeItem(at: url) }
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
try probe.selectMixedArchitectureChildTest()
try check(probe.manifest?.guestArchitecture == .x64 && probe.manifest?.executableRelativePath == "parent64.exe",
          "Mixed launch must explicitly select its x64 parent")
let mixed = probe.gameDirectory!
try check(mixed.lastPathComponent == "MixedArchitectureChild" && probe.presentationModeDraft == .desktop,
          "Mixed fixture uses only its owned desktop directory")
try check(Data(contentsOf: mixed.appendingPathComponent("child32.exe")) == Data(contentsOf: scratch.appendingPathComponent("resources/MixedArchitectureChild/mixed/child32.exe")),
          "Mixed fixture must copy the actual child beside its parent")
let note = mixed.appendingPathComponent("unrelated-note.txt")
try Data("keep".utf8).write(to: note)
let oldMarker = mixed.appendingPathComponent("mixed-child-result.json")
try Data("stale pass".utf8).write(to: oldMarker)
try probe.selectMixedArchitectureChildTest()
try check(!Foundation.FileManager.default.fileExists(atPath: oldMarker.path), "A prior mixed pass must be removed")
try check(Data(contentsOf: note) == Data("keep".utf8), "Fixture selection must preserve unrelated owned files")
try probe.selectMixedArchitectureChildTest(directControl: true)
let direct = probe.gameDirectory!
try check(probe.manifest?.guestArchitecture == .x86 && probe.manifest?.executableRelativePath == "child32.exe" && direct != mixed,
          "Direct control must select the identical child as a top-level x86 process")
try check(Data(contentsOf: direct.appendingPathComponent("child32.exe")) == Data(contentsOf: mixed.appendingPathComponent("child32.exe")),
          "Controls must use identical child bytes")
try check(probe.launchArgumentsText == "[]" && probe.launchError == nil && probe.renderScaleDraft == 1,
          "Fixture selection clears previous launch state")
let directMarker = direct.appendingPathComponent("direct-child-result.json")
try Data("stale".utf8).write(to: directMarker)
try probe.selectMixedArchitectureChildTest(directControl: true)
try check(!Foundation.FileManager.default.fileExists(atPath: directMarker.path), "A prior direct pass must be removed")
let releases = probe.releases
probe.canChangeSelection = false
try probe.selectMixedArchitectureChildTest()
try check(probe.releases == releases && probe.gameDirectory == direct, "A running session prevents fixture selection")
probe.canChangeSelection = true
Bundle.main.missing = "MixedArchitectureChild"
do { try probe.selectMixedArchitectureChildTest(); fatalError("Missing fixture silently fell back") }
catch let error as CocoaError { try check(error.code == .fileNoSuchFile, "Expected missing resource error") }
Bundle.main.missing = nil
let child = mixed.appendingPathComponent("child32.exe")
try Foundation.FileManager.default.removeItem(at: child)
let outside = scratch.appendingPathComponent("outside.exe")
try Data([1, 2, 3]).write(to: outside)
try Foundation.FileManager.default.createSymbolicLink(at: child, withDestinationURL: outside)
do { try probe.selectMixedArchitectureChildTest(); fatalError("Symlink child was overwritten") }
catch ImportFailure.folderAccessDenied {}
try check(Data(contentsOf: outside) == Data([1, 2, 3]), "Fixture selection changed a file outside its owned directory")
print("PASS: actual mixed/direct selector with real x64/i386 PEs, explicit architectures, marker freshness, file isolation, launch guards and symlink rejection")
'''
probe = probe.replace('PRODUCTION_MANIFEST', manifest).replace('PRODUCTION_SELECTOR', selector)
unit = build / 'main.swift'
unit.write_text(probe)
subprocess.run(['swiftc', str(unit), '-o', str(build / 'selection-probe')], check=True)
subprocess.run([str(build / 'selection-probe'), str(scratch)], check=True)
