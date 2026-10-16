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
let labels = LabelProbe()
let steamLabel = labels.label(steamVR), oculusLabel = labels.label(oculus), desktopLabel = labels.label(desktop)
check(Set([steamLabel, oculusLabel, desktopLabel]).count == 3,
      "Same-executable SteamVR, Oculus and desktop menu choices must be distinct")
check(steamLabel.contains("SteamVR / OpenVR"), "Identify the supported SteamVR route")
check(oculusLabel.contains("-vrmode Oculus -oculus"), "Expose public Oculus launch arguments")
check(desktopLabel.contains("-vrmode None -desktop"), "Expose desktop launch arguments")
print("PASS: Windlands-only OpenSSL CPU compatibility setting, preserved environment, SteamVR preference/options, platform/path checks and launch labels")
'''

with tempfile.TemporaryDirectory(prefix='wvr-launch-selection-') as scratch:
    scratch = Path(scratch)
    source = (SHELL + '\nenum SteamLibraryModel {\n' + selection + '\n}\n'
              + 'enum CompatibilityProbe {\n' + compatibility + '\n}\n'
              + 'struct LabelProbe {\n' + label
              + '\nfunc label(_ option: SteamLaunchOption) -> String { optionLabel(option) }\n}\n' + PROBE)
    (scratch / 'main.swift').write_text(source)
    subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-O', '-module-cache-path', str(scratch / 'cache'),
                    str(scratch / 'main.swift'), '-o', str(scratch / 'probe')], check=True)
    subprocess.run([str(scratch / 'probe'), str(ROOT / 'Tests/Contracts/fixtures/windlands-public-appinfo.json'),
                    str(scratch / 'drive')], check=True)
