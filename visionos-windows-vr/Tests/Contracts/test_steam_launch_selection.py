#!/usr/bin/env python3
"""Run production Swift launch selection/labels with public Windlands metadata.

The model/UI shells are minimal stubs. Selection, file-existence checks and label
methods are extracted unchanged from production sources. No game is downloaded
or executed; fixture executables are empty files in a temporary directory.
"""
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
model = (ROOT / 'Sources/Steam/SteamLibraryModel.swift').read_text()
selection = 'nonisolated static func isInstalled(' + model.split(
    'nonisolated static func isInstalled(', 1)[1].split('    func play(', 1)[0]
view = (ROOT / 'Sources/Steam/SteamLibraryView.swift').read_text()
label = 'private func optionLabel(' + view.split(
    'private func optionLabel(', 1)[1].split('    private func bytes(', 1)[0]

launcher = (ROOT / 'Sources/LauncherModel.swift').read_text()
compatibility = 'nonisolated static func steamCompatibilityEnvironment(' + launcher.split(
    'nonisolated static func steamCompatibilityEnvironment(', 1)[1].split('    /// Steam\'s 64-bit launch host', 1)[0]
assert 'environment: Self.steamCompatibilityEnvironment(appID: game.id)' in launcher
dock = (ROOT / 'Sources/Steam/MadeiraDock.swift').read_text()
extra_arguments = 'static func extraLaunchArguments(' + dock.split('static func extraLaunchArguments(', 1)[1].split('    @MainActor static func configure(', 1)[0]
assert 'extraLaunchArguments(appID: game.id)' in dock
assert 'unsetenv("MADEIRA_STEAM_HOST_EXTRA_ARGS")' in dock

SHELL = r'''
import Foundation
struct SteamLaunchOption {
    var executable: String
    var index: UInt32?
    var arguments = ""
    var type = ""
    var oslist = ""
}
struct DockGame { var library: String; var installDir: String }
'''
PROBE = r'''
func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}
let inherited = ["EXISTING_SETTING": "keep", "OPENSSL_ia32cap": "custom"]
let windlandsEnvironment = CompatibilityProbe.steamCompatibilityEnvironment(appID: 428370, base: inherited)
check(windlandsEnvironment["OPENSSL_ia32cap"] == "0", "Windlands must retain the working CPU compatibility setting")
check(windlandsEnvironment["EXISTING_SETTING"] == "keep", "Keep unrelated environment entries")
check(inherited["OPENSSL_ia32cap"] == "custom", "Do not mutate the caller's settings")
check(CompatibilityProbe.steamCompatibilityEnvironment(appID: 546560, base: inherited) == inherited,
      "Other games must retain their own CPU environment unchanged")
check(CompatibilityProbe.steamCompatibilityEnvironment(appID: 0).isEmpty,
      "Do not introduce a global CPU compatibility setting")
check(SteamArgumentProbe.extraLaunchArguments(appID: 386690) == "-vrmode openvr",
      "Fantastic Contraption must request Unity OpenVR explicitly")
check(SteamArgumentProbe.extraLaunchArguments(appID: 428370) == nil && SteamArgumentProbe.extraLaunchArguments(appID: 0) == nil,
      "Do not change working Windlands or unrelated game arguments")
check(CompatibilityProbe.steamCompatibilityEnvironment(appID: 386690).isEmpty,
      "Reserved internal launch settings must never enter a game manifest")
check(CompatibilityProbe.steamCompatibilityEnvironment(appID: 428370) == ["OPENSSL_ia32cap": "0"],
      "Ordinary Windlands selection must not depend on injected app environment")
let fixture = try JSONSerialization.jsonObject(with: Data(contentsOf:
    URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
check(fixture["appid"] as? Int == 428370, "Expected original Windlands fixture")
let config = fixture["config"] as! [String: Any]
let launches = config["launch"] as! [String: [String: Any]]
let options = launches.keys.sorted { Int($0)! < Int($1)! }.map { key in
    let entry = launches[key]!
    let platform = entry["config"] as? [String: String] ?? [:]
    return SteamLaunchOption(executable: entry["executable"] as! String, index: UInt32(key),
        arguments: entry["arguments"] as? String ?? "", type: entry["type"] as? String ?? "",
        oslist: platform["oslist"] ?? "")
}
let directory = URL(fileURLWithPath: CommandLine.arguments[2])
let game = DockGame(library: "Steam/steamapps", installDir: "Windlands")
let installed = directory.appendingPathComponent("Steam/steamapps/common/Windlands")
try FileManager.default.createDirectory(at: installed, withIntermediateDirectories: true)
for name in ["Windlands_Win_x86.exe", "Windlands_Win_x64.exe", "Windlands_OSX_x64.app"] {
    try Data().write(to: installed.appendingPathComponent(name))
}
let steamVR = options.first { $0.index == 5 }!
let oculus = options.first { $0.index == 4 }!
let desktop = options.first { $0.index == 1 }!
check(steamVR.executable == oculus.executable && steamVR.executable == desktop.executable,
      "Fixture must exercise identical executables with different launch routes")
check((launches["5"]!["config"] as! [String: String])["osarch"] == "64", "Metadata declares x64")
check(SteamLibraryModel.preferredLaunchOption(options, game: game, drive: directory)?.index == 5,
      "Installed SteamVR must win over the earlier Oculus entry and desktop")
check(SteamLibraryModel.preferredVRLaunchOption(options)?.index == 5,
      "Metadata-only fallback must prefer SteamVR too")
check(SteamLibraryModel.preferredLaunchOption(options.filter { $0.index != 5 }, game: game, drive: directory)?.index == 4,
      "Keep other-VR fallback when SteamVR is absent")
check(SteamLibraryModel.preferredLaunchOption([desktop], game: game, drive: directory)?.index == 1,
      "Keep installed desktop fallback when VR is absent")
var macVR = steamVR; macVR.oslist = "macos"; macVR.index = 100
var missingVR = steamVR; missingVR.executable = "absent.exe"; missingVR.index = 101
check(SteamLibraryModel.preferredLaunchOption([macVR, missingVR] + options, game: game, drive: directory)?.index == 5,
      "Non-Windows and missing executables must not override installed Windows SteamVR")
var uppercaseVR = steamVR; uppercaseVR.type = "VR"
check(SteamLibraryModel.preferredVRLaunchOption([oculus, uppercaseVR])?.index == 5,
      "VR type matching must remain case-insensitive")
check(SteamLibraryModel.preferredLaunchOption([missingVR], game: game, drive: directory) == nil,
      "No installed executable must return nil")
for path in ["../outside.exe", "/absolute.exe"] {
    var unsafe = steamVR; unsafe.executable = path
    check(!SteamLibraryModel.isInstalled(unsafe, game: game, drive: directory), "Reject unsafe launch paths")
}

let dosGame = DockGame(library: "Steam/steamapps", installDir: "Tomb Raider I")
let dosFolder = directory.appendingPathComponent("Steam/steamapps/common/Tomb Raider I")
try FileManager.default.createDirectory(at: dosFolder, withIntermediateDirectories: true)
try Data().write(to: dosFolder.appendingPathComponent("dosbox.exe"))
let dosOptions = [SteamLaunchOption(executable: "DOSBox.exe", index: 0),
                  SteamLaunchOption(executable: "tombati.exe", index: 2),
                  SteamLaunchOption(executable: "tombub.exe", index: 3)]
check(SteamLibraryModel.installedLaunchOptions(dosOptions, game: dosGame, drive: directory).map(\.index) == [0],
      "DOSBox case mismatch must retain the one installed option and hide absent alternatives")
check(SteamLibraryModel.preferredLaunchOption(dosOptions, game: dosGame, drive: directory)?.index == 0,
      "The sole installed DOSBox option must select automatically")
let nested = dosFolder.appendingPathComponent("Tools/Runtime", isDirectory: true)
try FileManager.default.createDirectory(at: nested, withIntermediateDirectories: true)
try Data([1]).write(to: nested.appendingPathComponent("program.exe"))
check(SteamInstalledExecutable.resolve("tools\\RUNTIME\\Program.EXE", game: dosGame, drive: directory)?.lastPathComponent == "program.exe",
      "Every Windows path component must resolve case-insensitively")
check(SteamInstalledExecutable.resolve(".\\DOSBox.exe", game: dosGame, drive: directory)?.lastPathComponent == "dosbox.exe",
      "Windows current-directory prefixes must remain usable")
check(SteamInstalledExecutable.resolve("Tools/./Runtime/Program.EXE", game: dosGame, drive: directory)?.lastPathComponent == "program.exe",
      "Harmless current-directory components must normalize without allowing traversal")
check(SteamInstalledExecutable.resolve("Tools", game: dosGame, drive: directory) == nil,
      "A directory is never a launchable executable")
for invalid in ["", ".", "..", "../dosbox.exe", "/dosbox.exe", "C:\\dosbox.exe", "Tools//program.exe", "dosbox.exe\0"] {
    check(SteamInstalledExecutable.resolve(invalid, game: dosGame, drive: directory) == nil,
          "Reject malformed Windows executable path: \(invalid.debugDescription)")
}
let outside = directory.appendingPathComponent("external", isDirectory: true)
try FileManager.default.createDirectory(at: outside, withIntermediateDirectories: true)
try Data([1]).write(to: outside.appendingPathComponent("outside.exe"))
try FileManager.default.createSymbolicLink(at: dosFolder.appendingPathComponent("Escaped"), withDestinationURL: outside)
check(SteamInstalledExecutable.resolve("escaped/OUTSIDE.EXE", game: dosGame, drive: directory) == nil,
      "Case-insensitive resolution must reject a directory symlink leaving the installation")
try FileManager.default.createSymbolicLink(at: dosFolder.appendingPathComponent("outside.exe"), withDestinationURL: outside.appendingPathComponent("outside.exe"))
check(SteamInstalledExecutable.resolve("outside.exe", game: dosGame, drive: directory) == nil,
      "Exact file resolution must also reject an escaping symlink")
try FileManager.default.createSymbolicLink(at: outside.appendingPathComponent("back"), withDestinationURL: nested)
check(SteamInstalledExecutable.resolve("Escaped/back/program.exe", game: dosGame, drive: directory) == nil,
      "A symlink must not leave the installation even if a later link returns inside")
try Data([1]).write(to: dosFolder.appendingPathComponent("Choice.exe"))
try Data([2]).write(to: dosFolder.appendingPathComponent("choice.exe"))
let ambiguous = try FileManager.default.contentsOfDirectory(atPath: dosFolder.path).filter { $0.lowercased() == "choice.exe" }
check(SteamInstalledExecutable.uniqueCaseInsensitiveMatch("CHOICE.EXE", entries: [
    dosFolder.appendingPathComponent("Choice.exe"), dosFolder.appendingPathComponent("choice.exe")]) == nil,
      "Case-insensitive directory matching must reject ambiguity on every host filesystem")
if ambiguous.count == 2 {
    check(SteamInstalledExecutable.resolve("CHOICE.EXE", game: dosGame, drive: directory) == nil,
          "A fallback with two differently cased names must not guess")
    check(SteamInstalledExecutable.resolve("Choice.exe", game: dosGame, drive: directory)?.lastPathComponent == "Choice.exe",
          "An exact installed spelling wins before any ambiguous fallback")
} else {
    print("SKIP: this fixture filesystem cannot represent ambiguous case variants")
}

let labels = LabelProbe()
let steamLabel = labels.label(steamVR), oculusLabel = labels.label(oculus), desktopLabel = labels.label(desktop)
check(Set([steamLabel, oculusLabel, desktopLabel]).count == 3,
      "Same-executable SteamVR, Oculus and desktop menu choices must be distinct")
check(steamLabel.contains("SteamVR / OpenVR"), "Identify the supported SteamVR route")
check(oculusLabel.contains("-vrmode Oculus -oculus"), "Expose public Oculus launch arguments")
check(desktopLabel.contains("-vrmode None -desktop"), "Expose desktop launch arguments")
print("PASS: Windlands-only OpenSSL CPU compatibility setting, preserved environment, SteamVR preference/options, safe case-insensitive executable resolution, unavailable-option filtering and launch labels")
'''

with tempfile.TemporaryDirectory(prefix='wvr-launch-selection-') as scratch:
    scratch = Path(scratch)
    resolver = (ROOT / 'Sources/Steam/SteamInstalledExecutable.swift').read_text()
    source = (SHELL + resolver + '\nenum SteamLibraryModel {\n' + selection + '\n}\n'
              + 'enum CompatibilityProbe {\n' + compatibility + '\n}\n'
              + 'struct SteamArgumentProbe {\n' + extra_arguments + '\n}\n'
              + 'struct LabelProbe {\n' + label
              + '\nfunc label(_ option: SteamLaunchOption) -> String { optionLabel(option) }\n}\n' + PROBE)
    (scratch / 'main.swift').write_text(source)
    subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-O', '-module-cache-path', str(scratch / 'cache'),
                    str(scratch / 'main.swift'), '-o', str(scratch / 'probe')], check=True)
    subprocess.run([str(scratch / 'probe'), str(ROOT / 'Tests/Contracts/fixtures/windlands-public-appinfo.json'),
                    str(scratch / 'drive')], check=True)
