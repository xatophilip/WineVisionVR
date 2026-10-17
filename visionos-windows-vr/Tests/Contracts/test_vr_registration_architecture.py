#!/usr/bin/env python3
"""Execute production Swift registration while switching real Wine registry views."""
from pathlib import Path
import argparse
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True, type=Path)
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
source = (root / 'Sources/Steam/OpenXRRegistration.swift').read_text()
launcher = (root / 'Sources/LauncherModel.swift').read_text()
# Execute the production launch-registration block with small manifest/runtime
# stand-ins, so native guest selection is tested rather than assuming x64.
match = re.search(r'            if launchManifest.id == "steam.shared" && launchManifest.presentation == \.immersiveVR \{\n.*?^            \}', launcher, re.M | re.S)
assert match, "Steam immersive registration must remain scoped to VR launches"
launch_registration = match.group(0)
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
for (abi, client, marker) in [("x86", "vrclient.dll", UInt8(32)), ("x64", "vrclient_x64.dll", UInt8(64)), ("arm64ec", "vrclient_x64.dll", UInt8(100))] {
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
// Exercise the actual launcher block: native ARM64EC for 64-bit apps,
// explicit x86 precedence, x64 fallback, and no VR mutation for desktop apps.
try registerFromLauncher(architecture: .x64, native: "arm64ec", presentation: .immersiveVR)
try verify("arm64ec", "vrclient_x64.dll", 100)
let native32 = try registrySection(key32)
assert(native32 == section32)
try registerFromLauncher(architecture: .x86, native: "arm64ec", presentation: .immersiveVR)
try verify("x86", "vrclient.dll", 32)
let preservedNative64 = try registrySection(key64)
assert(preservedNative64.contains(#""ActiveRuntime"="C:\\windows-vr-runtime\\active\\arm64ec\\runtime.json""#))
let desktopRegistry = try Data(contentsOf: system)
let desktopPaths = try Data(contentsOf: pathRegistry)
try registerFromLauncher(architecture: .x64, native: "x64", presentation: .desktop)
let afterDesktopRegistry = try Data(contentsOf: system)
let afterDesktopPaths = try Data(contentsOf: pathRegistry)
assert(afterDesktopRegistry == desktopRegistry)
assert(afterDesktopPaths == desktopPaths)
try registerFromLauncher(architecture: nil, native: nil, presentation: .immersiveVR)
try verify("x64", "vrclient_x64.dll", 64)
// Never rewrite files while the prefix's server is running.
serverRunning = 1
let beforeRejected = try Data(contentsOf: system)
do {
    try OpenXRRegistration.install(prefix: prefix, architecture: .x86)
    fatalError("running Wine must reject registration")
} catch {}
let afterRejected = try Data(contentsOf: system)
assert(beforeRejected == afterRejected)
print("PASS: real Swift x86/x64/ARM64EC registration, production launcher native selection/x86 precedence/x64 fallback/desktop isolation, registry-view/config preservation, repeat installation and active-server rejection")
'''
# The extracted launch code uses the same names as the production entry point.
# Native runtime architecture is a reported plugin capability, not a game path.
probe = r'''
enum TestArchitecture { case x86, x64 }
enum TestPresentation { case desktop, immersiveVR }
struct TestManifest { let id = "steam.shared"; let guestArchitecture: TestArchitecture?; let presentation: TestPresentation }
struct TestRuntime { let guestRuntimeArchitecture: String? }
enum MadeiraDock { static var prefix: URL { Bundle.main.resourceURL!.appendingPathComponent("registry-prefix") } }
func registerFromLauncher(architecture: TestArchitecture?, native: String?, presentation: TestPresentation) throws {
    let launchManifest = TestManifest(guestArchitecture: architecture, presentation: presentation)
    let runtime = TestRuntime(guestRuntimeArchitecture: native)
''' + launch_registration + "\n}\n" + probe
with tempfile.TemporaryDirectory(prefix='vr-registration-', dir=args.build) as work:
    work = Path(work)
    (work / 'main.swift').write_text(source + '\n' + probe)
    subprocess.run(['xcrun', 'swiftc', '-module-cache-path', str(work / 'cache'), str(work / 'main.swift'), '-o', str(work / 'probe')], check=True)
    subprocess.run([str(work / 'probe')], cwd=work, check=True)
