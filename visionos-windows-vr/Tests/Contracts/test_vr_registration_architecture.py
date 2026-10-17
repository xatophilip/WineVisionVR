#!/usr/bin/env python3
"""Execute production Swift registration while switching real Wine registry views."""
from pathlib import Path
import argparse
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True, type=Path)
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
source = (root / 'Sources/Steam/OpenXRRegistration.swift').read_text()
launcher = (root / 'Sources/LauncherModel.swift').read_text()
assert 'OpenXRRegistration.install(prefix: MadeiraDock.prefix, architecture: launchManifest.guestArchitecture == .x86 ? .x86 : .x64)' in launcher
probe = r'''
var serverRunning: Int32 = 0
func wineserver_is_running() -> Int32 { serverRunning }
func wine_process_is_running() -> Int32 { 0 }
let fm = FileManager.default
let resources = Bundle.main.resourceURL!
let prefix = resources.appendingPathComponent("registry-prefix")
let local = prefix.appendingPathComponent("drive_c/users/mobile/AppData/Local/openvr")
try fm.createDirectory(at: local, withIntermediateDirectories: true)
let system = prefix.appendingPathComponent("system.reg")
let key64 = #"Software\\Khronos\\OpenXR\\1"#
let key32 = #"Software\\Wow6432Node\\Khronos\\OpenXR\\1"#
let initial = "WINE REGISTRY Version 2\n\n[" + key64 + "] 1\n\"ActiveRuntime\"=\"C:\\\\old64.json\"\n\"Other64\"=dword:0000002a\n\n[Unrelated] 1\n\"Sentinel\"=\"keep\"\n\n[" + key32 + "] 1\n\"ActiveRuntime\"=\"C:\\\\old32.json\"\n\n"
try initial.write(to: system, atomically: true, encoding: .utf8)
for (abi, client, marker) in [("x86", "vrclient.dll", UInt8(32)), ("x64", "vrclient_x64.dll", UInt8(64))] {
    let guest = resources.appendingPathComponent("WindowsVR/Guest/" + abi)
    try fm.createDirectory(at: guest.appendingPathComponent("OpenComposite/bin"), withIntermediateDirectories: true)
    try Data([marker]).write(to: guest.appendingPathComponent("wvr_openxr.dll"))
    try Data([marker, 1]).write(to: guest.appendingPathComponent("OpenComposite/bin/" + client))
}
let pathRegistry = local.appendingPathComponent("openvrpaths.vrpath")
try JSONSerialization.data(withJSONObject: ["external_drivers": ["C:\\driver"], "config": ["C:\\config"]]).write(to: pathRegistry)
func registrySection(_ key: String) throws -> String {
    let lines = try String(contentsOf: system, encoding: .utf8).components(separatedBy: "\n")
    guard let start = lines.firstIndex(where: { $0.hasPrefix("[" + key + "]") }) else { fatalError("missing registry view") }
    let end = lines[(start + 1)...].firstIndex(where: { $0.hasPrefix("[") }) ?? lines.count
    return lines[start..<end].joined(separator: "\n")
}
func verify(_ abi: String, _ client: String, _ marker: UInt8) throws {
    let stable = prefix.appendingPathComponent("drive_c/windows-vr-runtime/active/" + abi)
    let manifest = try JSONSerialization.jsonObject(with: Data(contentsOf: stable.appendingPathComponent("runtime.json"))) as! [String: Any]
    let runtime = manifest["runtime"] as! [String: Any]
    assert(runtime["library_path"] as? String == "C:\\windows-vr-runtime\\active\\" + abi + "\\wvr_openxr.dll")
    let dll = try Data(contentsOf: stable.appendingPathComponent("wvr_openxr.dll"))
    let bridge = try Data(contentsOf: stable.appendingPathComponent("OpenComposite/bin/" + client))
    assert(dll == Data([marker]) && bridge == Data([marker, 1]))
    let paths = try JSONSerialization.jsonObject(with: Data(contentsOf: pathRegistry)) as! [String: Any]
    assert(paths["runtime"] as? [String] == ["C:\\windows-vr-runtime\\active\\" + abi + "\\OpenComposite"])
    assert(paths["external_drivers"] as? [String] == ["C:\\driver"])
    assert(paths["config"] as? [String] == ["C:\\config"])
}
let original64 = try registrySection(key64)
try OpenXRRegistration.install(prefix: prefix, architecture: .x86)
try verify("x86", "vrclient.dll", 32)
let kept64 = try registrySection(key64)
assert(kept64 == original64)
let section32 = try registrySection(key32)
assert(section32.contains(#""ActiveRuntime"="C:\\windows-vr-runtime\\active\\x86\\runtime.json""#))
let first = try Data(contentsOf: system)
try OpenXRRegistration.install(prefix: prefix, architecture: .x86)
let repeated = try Data(contentsOf: system)
assert(first == repeated)
// The no-argument API must still select x64, preserving the separate x86 view.
try OpenXRRegistration.install(prefix: prefix)
try verify("x64", "vrclient_x64.dll", 64)
let kept32 = try registrySection(key32)
assert(kept32 == section32)
let section64 = try registrySection(key64)
assert(section64.contains(#""ActiveRuntime"="C:\\windows-vr-runtime\\active\\x64\\runtime.json""#))
let unrelated = try registrySection("Unrelated")
assert(unrelated.contains("Sentinel") && unrelated.contains("keep"))
let retained32 = try Data(contentsOf: prefix.appendingPathComponent("drive_c/windows-vr-runtime/active/x86/wvr_openxr.dll"))
assert(retained32 == Data([32]))
// Never rewrite files while the prefix's server is running.
serverRunning = 1
let beforeRejected = try Data(contentsOf: system)
do {
    try OpenXRRegistration.install(prefix: prefix, architecture: .x86)
    fatalError("running Wine must reject registration")
} catch {}
let afterRejected = try Data(contentsOf: system)
assert(beforeRejected == afterRejected)
print("PASS: real Swift x86/x64 registry views, matching runtime/bridge paths, repeat installation, other-view/config preservation and active-server rejection")
'''
with tempfile.TemporaryDirectory(prefix='vr-registration-', dir=args.build) as work:
    work = Path(work)
    (work / 'main.swift').write_text(source + '\n' + probe)
    subprocess.run(['xcrun', 'swiftc', '-module-cache-path', str(work / 'cache'), str(work / 'main.swift'), '-o', str(work / 'probe')], check=True)
    subprocess.run([str(work / 'probe')], cwd=work, check=True)
