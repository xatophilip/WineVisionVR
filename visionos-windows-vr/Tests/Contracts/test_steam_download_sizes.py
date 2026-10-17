#!/usr/bin/env python3
"""Exercise production Steam size metadata, depot filters and old cached games."""
import argparse
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True, type=Path)
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
root = Path(__file__).resolve().parents[2]
steam = root / 'Sources/Steam'
app = (steam / 'SwiftSteam/Library/SteamAppInfo.swift').read_text()
owned = (steam / 'SteamOwnedGame.swift').read_text()
fetcher = (steam / 'SwiftSteam/Library/SteamLibraryFetcher.swift').read_text()
vdf = fetcher[fetcher.index('enum VDFParser {'):]
probe = r'''
import Foundation
enum SteamInstallFiles { static func safeFolderName(_ value: String) -> String { value } }
func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}
func depot(_ id: UInt32, download: UInt64 = 100, size: UInt64 = 250,
           arch: String = "64", language: String = "") -> SteamAppInfo.DepotInfo {
    var d = SteamAppInfo.DepotInfo(depotID: id)
    d.oslist = "windows"; d.osarch = arch; d.language = language
    d.manifests = ["public": 123]; d.publicDownloadBytes = download; d.publicSizeBytes = size
    return d
}
var app = SteamAppInfo(appID: 42)
app.name = "Fixture"
app.depots = [depot(1), depot(2, download: 200, size: 500, arch: "")]
var excluded = depot(3, download: 9999); excluded.oslist = "linux"
app.depots += [excluded, depot(4, download: 9999, arch: "32"), depot(5, download: 9999, language: "german")]
excluded = depot(6, download: 9999); excluded.dlcAppID = 99; app.depots.append(excluded)
excluded = depot(7, download: 9999); excluded.isSharedInstall = true; app.depots.append(excluded)
check(app.installSizeEstimates().download == 300, "Download must sum selected Windows depots only")
check(app.installSizeEstimates().installed == 750, "Compressed and installed figures must stay distinct")
let game = SteamOwnedGame(app)
check(game.downloadBytes == 300 && game.installedBytes == 750, "Library entry retains both estimates")
var oldCache = try JSONSerialization.jsonObject(with: JSONEncoder().encode(game)) as! [String: Any]
oldCache.removeValue(forKey: "downloadBytes"); oldCache.removeValue(forKey: "installedBytes")
let restored = try JSONDecoder().decode(SteamOwnedGame.self, from: JSONSerialization.data(withJSONObject: oldCache))
check(restored.downloadBytes == nil && restored.installedBytes == nil, "Older cached entries remain readable")
app.depots = [depot(1), depot(2, download: 0, size: 0)]
app.depots[1].maxSize = 500
check(app.installSizeEstimates().download == nil, "Missing compressed metadata must not display a partial total or disk bytes")
check(app.installSizeEstimates().installed == 750, "Legacy maxsize is usable only for installed estimate")
app.depots[1].maxSize = 0
check(app.installSizeEstimates().installed == nil, "Incomplete disk metadata must stay unknown")
app.depots = [depot(1), depot(2)]
app.depots[1].manifests = [:]; app.depots[1].fromApp = 99
check(app.installSizeEstimates().download == nil && app.installSizeEstimates().installed == nil, "Unresolved required shared depots cannot disappear from totals")
app.depots = [depot(1, download: UInt64.max), depot(2)]
check(app.installSizeEstimates().download == nil, "Unrepresentable metadata must not trap or display a clamped size")
app.depots = [depot(1, download: 50, size: 100, arch: "32")]
check(app.installSizeEstimates().download == 50, "32-bit-only games use the installer fallback")
app.depots = []
check(app.installSizeEstimates().download == nil, "Unknown is not zero bytes")
let parsed = SteamAppInfo.parse(appID: 42, from: ["common": ["name": "Fixture"], "depots": ["1": ["config": ["oslist": "windows"], "manifests": ["public": ["gid": "123", "download": "1234", "size": "5678"]]]]])!
check(parsed.installSizeEstimates().download == 1234 && parsed.installSizeEstimates().installed == 5678, "Modern PICS values reach the UI estimates")
print("PASS: Windows download/storage estimates, depot filters, missing/shared metadata, overflow and old-cache compatibility")
'''
unit = args.build / 'DownloadSizes.swift'
unit.write_text(app + '\n' + owned + '\n' + vdf + '\n' + probe)
env = dict(os.environ)
env['CLANG_MODULE_CACHE_PATH'] = str(args.build / 'module-cache')
binary = args.build / 'download-sizes'
subprocess.run(['xcrun', 'swiftc', str(unit), '-o', str(binary)], check=True, env=env)
subprocess.run([str(binary)], check=True, env=env)
