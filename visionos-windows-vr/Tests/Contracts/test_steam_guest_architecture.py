#!/usr/bin/env python3
"""Run production bounded PE architecture inspection against real file fixtures."""
from pathlib import Path
import argparse
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True, type=Path)
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
source = (root / 'visionos-windows-vr/Sources/LauncherModel.swift').read_text()
methods = 'nonisolated static func steamGuestArchitecture(' + source.split(
    'nonisolated static func steamGuestArchitecture(', 1)[1].split('    func selectSteamGame(', 1)[0]
restore = 'private func restoreSteamSelection(' + source.split(
    'private func restoreSteamSelection(', 1)[1].split('    func selectProfile(', 1)[0]
effective = 'private func effectiveManifest()' + source.split(
    'private func effectiveManifest()', 1)[1].split('    private static func systemString(', 1)[0]
manifest = (root / 'windows-vr/Sources/WindowsVRCore/WindowsGameManifest.swift').read_text()
# The launch option used for handoff must be the same one inspected before
# preflight, even if prepareForLaunch refreshes the catalog asynchronously.
launch = source.split('    func launch(preparePresentation:', 1)[1].split('    func select', 1)[0]
assert launch.index('restoreSteamSelection(for: manifest)') < launch.index('let launchManifest = try effectiveManifest()') < launch.index('runtime.preflight(')
assert launch.count('restoreSteamSelection(') == 1
assert launch.index('bundledX86RuntimeAvailable(') < launch.index('runtime.preflight(')
assert 'guard let selection = launchSelection,' in launch.split('await SteamLibraryModel.shared.prepareForLaunch()', 1)[1]
probe = r'''
import Foundation
PRODUCTIONMANIFEST
func L(_ english: String, _ german: String) -> String { english }
struct SteamLaunchOption { let executable: String; var index: UInt32? = 0 }
struct DockGame { let library: String; let installDir: String; var id = 412740; var name = "Fixture"; var installed = true }
struct Probe {
METHODS
}
func check(_ value: @autoclosure () throws -> Bool, _ message: String) throws {
    if try !value() { fatalError(message) }
}
let base = URL(fileURLWithPath: CommandLine.arguments[1])
let game = DockGame(library: "steamapps", installDir: "Fixture")
let folder = base.appendingPathComponent("steamapps/common/Fixture")
try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
func pe(_ name: String, _ machine: UInt16) throws {
    var bytes = Data(repeating: 0, count: 256)
    bytes[0] = 0x4d; bytes[1] = 0x5a; bytes[60] = 128
    bytes[128] = 0x50; bytes[129] = 0x45
    bytes[132] = UInt8(machine & 255); bytes[133] = UInt8(machine >> 8)
    try bytes.write(to: folder.appendingPathComponent(name))
}
func inspect(_ path: String) -> WindowsGuestArchitecture? {
    Probe.steamGuestArchitecture(option: SteamLaunchOption(executable: path), game: game, drive: base)
}
try pe("game32.exe", 0x14c)
try pe("game64.exe", 0x8664)
try check(inspect("game32.exe") == .x86, "32-bit Steam child must select 32-bit VR DLLs")
try check(inspect("game64.exe") == nil, "64-bit game retains existing default runtime selection")
try check(inspect("missing.exe") == nil, "Missing game does not invent architecture")
try check(inspect("../Fixture/game32.exe") == nil, "Reject traversal")
try check(inspect("C:\\game32.exe") == nil, "Reject Windows drive path")
try check(inspect("/game32.exe") == nil, "Reject absolute path")
try Data([1, 2, 3]).write(to: folder.appendingPathComponent("bad.exe"))
try check(inspect("bad.exe") == nil, "Reject truncated header")
var bad = Data(repeating: 0, count: 80); bad[0] = 0x4d; bad[1] = 0x5a
for i in 60..<64 { bad[i] = 255 }
try bad.write(to: folder.appendingPathComponent("bad-offset.exe"))
try check(inspect("bad-offset.exe") == nil, "Reject out-of-file PE offset")
let outside = base.appendingPathComponent("outside.exe")
try Data(contentsOf: folder.appendingPathComponent("game32.exe")).write(to: outside)
try FileManager.default.createSymbolicLink(at: folder.appendingPathComponent("escaped.exe"), withDestinationURL: outside)
try check(inspect("escaped.exe") == nil, "Reject symlink outside the installed game")
enum WindowsVRLibraryError: Error { case noActiveGame, invalidProfileArguments }
enum DockError: Error { case message(String) }
struct Log { func notice(_ message: String) {} }
let launchLog = Log()
class UserDefaults {
    static let standard = UserDefaults()
    var values: [String: Any] = [:]
    func dictionary(forKey key: String) -> [String: Any]? { values[key] as? [String: Any] }
}
enum MadeiraDock {
    static var drive = URL(fileURLWithPath: "/")
    static var installedGames: [DockGame] = []
    static func games(drive: URL) -> [DockGame] { installedGames }
}
enum SteamLocalAppInfo {
    static var options: [SteamLaunchOption]?
    static func launchOptions(appID: Int, game: DockGame, drive: URL) -> [SteamLaunchOption]? { options }
}
struct CatalogGame { var launches: [SteamLaunchOption] }
struct CatalogEntry { var id: Int; var game: CatalogGame }
class SteamLibraryModel {
    static let shared = SteamLibraryModel()
    var games: [CatalogEntry] = []
    static func isInstalled(_ option: SteamLaunchOption, game: DockGame, drive: URL) -> Bool {
        FileManager.default.fileExists(atPath: drive.appendingPathComponent(game.library + "/common/" + game.installDir + "/" + option.executable).path)
    }
    static func preferredLaunchOption(_ options: [SteamLaunchOption], game: DockGame, drive: URL) -> SteamLaunchOption? {
        options.first { isInstalled($0, game: game, drive: drive) }
    }
}
struct Profile {
    var id: String
    var architecture: WindowsGuestArchitecture?
    func applying(to base: WindowsGameManifest) throws -> WindowsGameManifest {
        try WindowsGameManifest(id: base.id, title: base.title, executableRelativePath: base.executableRelativePath,
            backend: base.backend, graphics: base.graphics, launchArguments: base.launchArguments,
            environment: base.environment, presentation: base.presentation, guestArchitecture: architecture, schemaVersion: 1)
    }
}
struct Entry { var manifest: WindowsGameManifest; var profiles: [Profile] }
class RestoredProbe {
    var manifest: WindowsGameManifest?
    var steamSelection: (game: DockGame, option: UInt32)?
    var draftArguments: [String] = []
    var presentationModeDraft: WindowsPresentationMode = .immersiveVR
    var selectedEntry: Entry?
    var selectedProfileID: String?
    static let steamLaunchOptionsKey = "options"
ARCHBODY
RESTOREBODY
EFFECTIVEBODY
    func restoredManifest(_ saved: WindowsGameManifest) throws -> WindowsGameManifest {
        manifest = saved
        restoreSteamSelection(for: saved)
        return try effectiveManifest()
    }
}
func saved(_ architecture: WindowsGuestArchitecture?, id: String = "steam.shared") throws -> WindowsGameManifest {
    try WindowsGameManifest(id: id, title: "Fixture", executableRelativePath: "AVPPlaySteam/dockhost.exe",
        backend: .windowsWineFEX, graphics: .direct3D11, launchArguments: [], guestArchitecture: architecture, schemaVersion: 1)
}
MadeiraDock.drive = base
MadeiraDock.installedGames = [game]
SteamLocalAppInfo.options = [SteamLaunchOption(executable: "game32.exe")]
// Old saved entries lack the new field; profiles may retain a wrong field.
let restored = RestoredProbe()
try check(try restored.restoredManifest(saved(nil)).guestArchitecture == .x86, "Restored old Steam entry must inspect its actual 32-bit child")
try check(try restored.restoredManifest(saved(.x64)).guestArchitecture == .x86, "Restored stale x64 field must not select x64 VR DLLs for a 32-bit child")
let old = try saved(.x64)
restored.selectedEntry = Entry(manifest: old, profiles: [Profile(id: "stale", architecture: .arm64ec)])
restored.selectedProfileID = "stale"
try check(try restored.restoredManifest(old).guestArchitecture == .x86, "Actual Steam child overrides a stale selected profile architecture")
restored.selectedEntry = nil; restored.selectedProfileID = nil
SteamLocalAppInfo.options = [SteamLaunchOption(executable: "game64.exe")]
try check(try restored.restoredManifest(saved(.x86)).guestArchitecture == nil, "Restored x64 game clears a stale x86 field")
// Restore must reconcile a removed launch option before architecture inspection.
UserDefaults.standard.values["options"] = [String(game.id): 99]
SteamLocalAppInfo.options = [SteamLaunchOption(executable: "game32.exe")]
try check(try restored.restoredManifest(saved(nil)).guestArchitecture == .x86 && restored.steamSelection?.option == 0,
      "Missing remembered option must reconcile to the installed option before preflight")
try check(try restored.restoredManifest(saved(.arm64ec, id: "direct.fixture")).guestArchitecture == .arm64ec,
      "Direct non-Steam manifests retain their own explicit architecture")
SteamLocalAppInfo.options = nil
UserDefaults.standard.values["options"] = [String(game.id): 0]
try check(try restored.restoredManifest(saved(.x86)).guestArchitecture == .x86,
      "Missing offline metadata retains a remembered option and known x86 architecture")
try check(try restored.restoredManifest(saved(nil)).guestArchitecture == nil,
      "Missing offline metadata must not block an explicitly remembered x64 launch")
UserDefaults.standard.values["options"] = [:]
do {
    _ = try restored.restoredManifest(saved(nil))
    fatalError("Missing metadata without a remembered choice must still require selection")
} catch DockError.message { }
let resources = base.appendingPathComponent("resources")
try check(!Probe.bundledX86RuntimeAvailable(resources: nil, immersiveVR: false), "No bundle cannot supply x86")
try check(!Probe.bundledX86RuntimeAvailable(resources: resources, immersiveVR: false), "Verified x64-only bundle must reject x86 child before old native plugin")
let x86Files = ["Runtime/i386-windows/ntdll.dll", "WindowsVR/Guest/x86/wvr_openxr.dll", "WindowsVR/Guest/x86/OpenComposite/bin/vrclient.dll"]
for (index, relative) in x86Files.enumerated() {
    let file = resources.appendingPathComponent(relative)
    try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
    try Data([0x4d, 0x5a]).write(to: file)
    try check(Probe.bundledX86RuntimeAvailable(resources: resources, immersiveVR: false), "Desktop x86 requires its Wine farm")
    try check(Probe.bundledX86RuntimeAvailable(resources: resources, immersiveVR: true) == (index == 2), "Immersive x86 requires both architecture-matched bridge files")
}
try FileManager.default.removeItem(at: resources.appendingPathComponent(x86Files[0]))
try check(!Probe.bundledX86RuntimeAvailable(resources: resources, immersiveVR: true), "VR bridges cannot replace a missing x86 Wine farm")
print("PASS: actual PE architecture, restored Steam/profile fields, option reconciliation, direct manifests and x86-only package guard")
'''.replace('METHODS', methods).replace('PRODUCTIONMANIFEST', manifest).replace('ARCHBODY', methods).replace('RESTOREBODY', restore).replace('EFFECTIVEBODY', effective)
unit = args.build / 'SteamArchitecture.swift'
unit.write_text(probe)
binary = args.build / 'steam-architecture'
subprocess.run(['xcrun', 'swiftc', str(unit), '-o', str(binary)], check=True)
with tempfile.TemporaryDirectory(prefix='fixture-', dir=args.build) as fixture:
    subprocess.run([str(binary), fixture], check=True)
