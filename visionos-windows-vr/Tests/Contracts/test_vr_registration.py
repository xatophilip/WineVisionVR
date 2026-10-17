#!/usr/bin/env python3
"""Execute the production Swift registration against a temporary Wine prefix."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[2]
source=(root/'Sources/Steam/OpenXRRegistration.swift').read_text()
probe=r'''
func wineserver_is_running()->Int32 { 0 }
func wine_process_is_running()->Int32 { 0 }
let fm=FileManager.default
let root=Bundle.main.resourceURL!
let prefix=root.appendingPathComponent("test-prefix")
let local=prefix.appendingPathComponent("drive_c/users/mobile/AppData/Local/openvr")
try fm.createDirectory(at:local,withIntermediateDirectories:true)
try "WINE REGISTRY Version 2\n".write(to:prefix.appendingPathComponent("system.reg"),atomically:true,encoding:.utf8)
var expectedRuntimeByView: [String: String] = [:]
for architecture in ["x64", "arm64ec", "x86", "arm64ec"] {
let clientName = architecture == "x86" ? "vrclient.dll" : "vrclient_x64.dll"
let guest=root.appendingPathComponent("WindowsVR/Guest/\(architecture)")
try fm.createDirectory(at:guest.appendingPathComponent("OpenComposite/bin"),withIntermediateDirectories:true)
try Data([1]).write(to:guest.appendingPathComponent("wvr_openxr.dll"))
try Data([2]).write(to:guest.appendingPathComponent("OpenComposite/bin/" + clientName))
let registry=local.appendingPathComponent("openvrpaths.vrpath")
try JSONSerialization.data(withJSONObject:["external_drivers":["C:\\existing-driver"],"config":["C:\\existing-config"]]).write(to:registry)
for _ in 0..<2 { try OpenXRRegistration.install(prefix:prefix,architecture:architecture) }
let json=try JSONSerialization.jsonObject(with:Data(contentsOf:registry)) as! [String:Any]
assert(json["jsonid"] as? String=="vrpathreg")
assert(json["runtime"] as? [String]==[#"C:\windows-vr-runtime\active"#+"\\"+architecture+#"\OpenComposite"#])
assert(json["config"] as? [String]==["C:\\existing-config"])
assert(json["external_drivers"] as? [String]==["C:\\existing-driver"])
let linked=prefix.appendingPathComponent("drive_c/windows-vr-runtime/active/\(architecture)/OpenComposite/bin/" + clientName)
let linkedData=try Data(contentsOf:linked)
assert(linkedData==Data([2]))
let systemRegistry=try String(contentsOf:prefix.appendingPathComponent("system.reg"),encoding:.utf8)
let view = architecture == "x86" ? #"Software\\Wow6432Node\\Khronos\\OpenXR\\1"# : #"Software\\Khronos\\OpenXR\\1"#
expectedRuntimeByView[view] = (#"C:\windows-vr-runtime\active"# + "\\" + architecture + #"\runtime.json"#).replacingOccurrences(of: "\\", with: "\\\\")
for (expectedView, expectedPath) in expectedRuntimeByView {
let sections = systemRegistry.components(separatedBy: "\n[")
let matching = sections.filter { $0.hasPrefix(expectedView + "]") }
assert(matching.count == 1)
assert(matching[0].contains("\"ActiveRuntime\"=\"" + expectedPath + "\""))
}
}
do {
try OpenXRRegistration.install(prefix:prefix, architecture:"../outside")
fatalError("Unsafe architecture accepted")
} catch {}
print("PASS: x86/x64/ARM64EC real Swift OpenXR/OpenVR registration, DLL mapping, preserved registry views/configuration, repeat installation and rejected invalid architecture")
'''
with tempfile.TemporaryDirectory(prefix='wvr-registration-') as work:
    work=Path(work);(work/'main.swift').write_text(source+'\n'+probe)
    subprocess.run(['xcrun','swiftc','-module-cache-path',str(work/'cache'),str(work/'main.swift'),'-o',str(work/'probe')],check=True)
    subprocess.run([str(work/'probe')],check=True,cwd=work)
