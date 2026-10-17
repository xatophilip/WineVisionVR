#!/usr/bin/env python3
"""Execute the production Foundation journal against real temporary files."""
from pathlib import Path
import argparse, subprocess, tempfile, shutil
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--build',type=Path);a=p.parse_args()
PROBE=r'''
import Foundation
func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}
let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let docs = root.appendingPathComponent("Documents", isDirectory: true)
let prefix = docs.appendingPathComponent("WindowsVR/Prefixes/owned", isDirectory: true)
let launcher = docs.appendingPathComponent("launcher-log.txt")
let native = docs.appendingPathComponent("madeira-log.txt")
let xr = prefix.appendingPathComponent("drive_c/windows-vr-runtime/openxr-trace.txt")
let oc = prefix.appendingPathComponent("drive_c/usersmadeira/AppData/Local/OpenComposite/logs/opencomposite.log")
let fm=FileManager.default
func write(_ url: URL,_ text: String) throws {
    try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    try Data(text.utf8).write(to: url)
}
func append(_ url: URL,_ text: String) throws {
    let handle=try FileHandle(forWritingTo: url);try handle.seekToEnd();try handle.write(contentsOf: Data(text.utf8));try handle.close()
}
func metadata(_ title:String)->SessionDiagnostics.Metadata {
    SessionDiagnostics.Metadata(title:title,manifestID:"game.\(title)",steamAppID:356400,steamLaunchOptionID:5,architecture:"x86",graphics:"direct3D11",renderScale:0.8,appVersion:"1.0",buildNumber:"test",runtimeBuildID:nil,profileID:"legacy",profileName:"Legacy DXMT")
}
func bundle(_ diagnostics:SessionDiagnostics)throws->([String:Any],String,Int){
    let data=try Data(contentsOf: diagnostics.exportBundle())
    return (try JSONSerialization.jsonObject(with:data) as! [String:Any],String(decoding:data,as:UTF8.self),data.count)
}
func attempts(_ bundle:[String:Any])->[[String:Any]]{bundle["attempts"] as! [[String:Any]]}
func logs(_ attempt:[String:Any])->String{(attempt["logs"] as! [[String:Any]]).map{$0["text"] as! String}.joined(separator:"\n")}
try write(launcher,"OLD_GAME_LAUNCHER\n")
try write(native,"OLD_GAME_NATIVE\n")
try write(xr,"OLD_GAME_OPENXR\n")
try write(oc,"OLD_GAME_OPENCOMPOSITE\n")
let d=try SessionDiagnostics(documentsDirectory:docs)
try d.recoverPendingAttempt()
try d.beginAttempt(metadata:metadata("preflight-failure"),prefixURL:prefix)
try append(launcher,"NEW_PREFLIGHT_FAILED\npassword=super-secret-value\n")
try d.finish(outcome:.failed,reason:"Preflight rejected unsupported binary")
var b=try bundle(d)
check(!b.1.contains("OLD_GAME"),"Unchanged prior-game logs must not be attributed to failed preflight")
check(b.1.contains("NEW_PREFLIGHT_FAILED"),"Launcher must capture only new append range")
check(!b.1.contains("super-secret-value"),"Sensitive log values must be omitted")
check(!b.1.contains("relativePath") && !b.1.contains(docs.path),"Export must omit private source paths and baselines")
check((attempts(b.0)[0]["metadata"] as! [String:Any])["runtimeBuildID"]==nil,"Unknown runtime build must stay omitted")
try d.beginAttempt(metadata:metadata("rotation"),prefixURL:prefix)
let middle=String(repeating:"MIDDLE_NOT_RETAINED \"\\\" repeated text\n",count:30000)
let initial="NATIVE_STARTUP_UNIQUE\n"+middle+"NATIVE_TAIL_UNIQUE\n"
try Data(initial.utf8).write(to:native,options:.atomic)
try fm.removeItem(at:xr)
try write(xr,"OPENXR_NEW_ATTEMPT\n")
try d.snapshot(reason:"Running after shared log rotation")
b=try bundle(d)
var latest=attempts(b.0).last!
var text=logs(latest)
check(text.contains("NATIVE_STARTUP_UNIQUE") && text.contains("NATIVE_TAIL_UNIQUE"),"Retain both startup and latest tail")
check(text.contains("log truncated"),"Truncation must be explicit")
check(text.utf8.count<300000,"Per-attempt logs must remain bounded")
check(text.contains("OPENXR_NEW_ATTEMPT") && !text.contains("OLD_GAME_OPENXR"),"Deleted guest trace must restart at zero")
// In-place truncation/rewrite with the same inode must also capture from zero.
try write(native,"ROTATED_NATIVE_NEW_TAIL\n")
try d.finish(outcome:.completed,reason:"Normal stop")
b=try bundle(d);text=logs(attempts(b.0).last!)
check(text.contains("NATIVE_STARTUP_UNIQUE") && text.contains("ROTATED_NATIVE_NEW_TAIL"),"A later rotation preserves startup and newest content")
// A nonterminal observation persists pending state across an app force quit.
try d.beginAttempt(metadata:metadata("force-quit"),prefixURL:prefix)
try append(launcher,"BEFORE_FORCE_QUIT\n")
try d.snapshot(reason:"Stop requested but guest remains active",outcome:.failed)
b=try bundle(d);latest=attempts(b.0).last!
check(latest["isPending"] as! Bool,"Snapshot outcome must not close a running attempt")
try append(native,"NATIVE_AFTER_LAST_SNAPSHOT\n")
let restarted=try SessionDiagnostics(documentsDirectory:docs)
try restarted.recoverPendingAttempt()
b=try bundle(restarted);latest=attempts(b.0).last!
check(latest["outcome"] as! String == "failed" && !(latest["isPending"] as! Bool),"Recovery must archive the pending journal while preserving an already recorded failure")
check(logs(latest).contains("NATIVE_AFTER_LAST_SNAPSHOT"),"Recovery must snapshot before the next launch rotates runtime logs")
// Follow no source symlink outside the exact owned prefix.
try restarted.beginAttempt(metadata:metadata("symlink-escape"),prefixURL:prefix)
let outside=root.appendingPathComponent("outside-sensitive.log")
try write(outside,"OUTSIDE_PRIVATE_MUST_NOT_EXPORT\n")
try fm.removeItem(at:xr)
try fm.createSymbolicLink(at:xr,withDestinationURL:outside)
try restarted.finish(outcome:.failed,reason:"Guest trace unavailable")
b=try bundle(restarted)
check(!b.1.contains("OUTSIDE_PRIVATE_MUST_NOT_EXPORT"),"Guest source symlink escape must be refused")
do {try restarted.beginAttempt(metadata:metadata("outside-prefix"),prefixURL:root);fatalError("Outside prefix accepted")} catch SessionDiagnostics.DiagnosticsError.unsafePath {}
try fm.removeItem(at:xr);try write(xr,"SAFE_LOG\n")
try restarted.beginAttempt(metadata:metadata("internal-private-leaf"),prefixURL:prefix)
let privateLeaf=prefix.appendingPathComponent("drive_c/launch.auth")
try write(privateLeaf,"PRIVATE_BLOB_WITHOUT_ANY_KEYWORDS\n")
try fm.removeItem(at:xr);try fm.createSymbolicLink(at:xr,withDestinationURL:privateLeaf)
try restarted.finish(outcome:.failed,reason:"Fixed log leaf redirected")
b=try bundle(restarted)
check(!b.1.contains("PRIVATE_BLOB_WITHOUT_ANY_KEYWORDS"),"A log leaf must not redirect into auth data even inside the exact prefix")
try fm.removeItem(at:xr);try write(xr,"SAFE_LOG\n")
try restarted.beginAttempt(metadata:metadata("prior-before-failed-begin"),prefixURL:prefix)
do {try restarted.beginAttempt(metadata:metadata("unsafe-new-begin"),prefixURL:root);fatalError("Unsafe begin accepted")} catch SessionDiagnostics.DiagnosticsError.unsafePath {}
try append(launcher,"AFTER_FAILED_BEGIN_MUST_NOT_TAG_PRIOR\n")
try restarted.snapshot(reason:"A new game continued without diagnostics")
b=try bundle(restarted)
check(!b.1.contains("AFTER_FAILED_BEGIN_MUST_NOT_TAG_PRIOR"),"Failed begin must clear the previous current attempt before subsequent snapshots")
// Retention and total bundle bounds survive many attempts with large text files.
for n in 0..<23 {
    try restarted.beginAttempt(metadata:metadata("retained-\(n)"),prefixURL:prefix)
    try Data(("HEAD \(n)\n"+middle+"TAIL \(n)\n").utf8).write(to:native,options:.atomic)
    try append(launcher,"NEW ATTEMPT \(n)\n")
    try restarted.finish(outcome:.stopped,reason:"Game closed")
}
b=try bundle(restarted)
check(attempts(b.0).count==20,"Retain exactly the newest 20 completed journals")
check(b.2<=32*1024*1024,"Combined JSON must respect the 32 MiB cap")
let titles=attempts(b.0).map{($0["metadata"] as! [String:Any])["title"] as! String}
check(titles.first=="retained-3" && titles.last=="retained-22","Retention ordering must survive subsecond attempts")
let folders=try fm.contentsOfDirectory(at:docs.appendingPathComponent("WindowsVR/SessionDiagnostics"),includingPropertiesForKeys:nil).filter{UUID(uuidString:$0.lastPathComponent) != nil}
check(folders.count==20,"Old journals must also be removed from disk")
print("PASS: actual durable journals recover force quit, isolate new-game log ranges, handle rotation, preserve startup/tail, redact secrets, refuse prefix symlink escapes, retain 20 sessions and export bounded JSON (\(b.2) bytes)")
'''
def run(build:Path):
    build.mkdir(parents=True,exist_ok=True)
    if (build/'files').exists():shutil.rmtree(build/'files')
    source=build/'main.swift';source.write_text(PROBE)
    subprocess.run(['xcrun','--sdk','macosx','swiftc','-swift-version','6','-O','-module-cache-path',str(build/'cache'),str(ROOT/'Sources/SessionDiagnostics.swift'),str(source),'-o',str(build/'probe')],check=True)
    subprocess.run([str(build/'probe'),str(build/'files')],check=True,timeout=60)
if a.build:run(a.build.resolve())
else:
    with tempfile.TemporaryDirectory(prefix='wvr-session-diagnostics-')as tmp:run(Path(tmp))
