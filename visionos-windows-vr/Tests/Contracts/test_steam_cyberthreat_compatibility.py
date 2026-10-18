#!/usr/bin/env python3
"""Execute CyberThreat's opt-in production helper and actual Dock configure under Swift 6.

Entry-route assertions bind normal, diagnostic and restored launches to that
boundary. Credential, logging and unrelated host-configuration services are
recording stand-ins. No Steam, game, Wine runtime or headset executes.
"""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--build", required=True, type=Path)
a = p.parse_args()
a.build = a.build.resolve()
if a.build == ROOT or ROOT in a.build.parents:
    p.error("--build must be outside the checkout")
a.build.mkdir(parents=True, exist_ok=True)
tmp = a.build / "tmp"
tmp.mkdir(exist_ok=True)
env = dict(os.environ, TMPDIR=str(tmp), CLANG_MODULE_CACHE_PATH=str(tmp/"cache"),
           SWIFT_MODULECACHE_PATH=str(tmp/"cache"))
paths = {name: ROOT/relative for name, relative in {
    "helper":"visionos-windows-vr/Sources/Steam/SteamLabCompatibility.swift",
    "cyber":"visionos-windows-vr/Sources/Steam/SteamCyberThreatCompatibility.swift",
    "dock":"visionos-windows-vr/Sources/Steam/MadeiraDock.swift",
    "launcher":"visionos-windows-vr/Sources/LauncherModel.swift",
    "view":"visionos-windows-vr/Sources/ContentView.swift"}.items()}
text = {name:path.read_text() for name,path in paths.items()}
def body(source, signature):
    start=source.index(signature); end=source.index("{",start)+1;depth=1
    while depth:
        depth+=(source[end]=="{")-(source[end]=="}");end+=1
    return source[start:end]
launch = body(text["launcher"], "func launch(preparePresentation:")
assert launch.index("restoreSteamSelection(for: manifest)") < launch.index("let launchSelection = steamSelection")
assert launch.count("MadeiraDock.configure(")==1
assert "argumentsOverride: arguments" in launch
assert text["launcher"].count("MadeiraDock.configure(")==1
start_launch = body(text["view"], "private func startLaunch() async")
assert "await model.launch" in start_launch
assert "Button { Task { await startLaunch() } }" in text["view"]
diagnostic = body(text["view"], "do {\n                    try model.selectInstalledSteamGame")
assert "selectInstalledSteamGame" in diagnostic and "await startLaunch()" in diagnostic
configure = body(text["dock"], "@MainActor static func configure(")
assert "SteamLabCompatibility.arguments(appID: game.id," in configure
assert "SteamCyberThreatCompatibility.arguments(appID: game.id," in configure
assert "enabled: LaunchDiagnostics.enabled" in configure
assert "processArguments: ProcessInfo.processInfo.arguments" in configure
assert "base: argumentsOverride ?? extraLaunchArguments(appID: game.id)" in configure
extra = body(text["dock"], "static func extraLaunchArguments(")
shell = r"""
import Foundation
@MainActor enum LaunchDiagnostics {static var enabled=true}
struct DockGame {var id:Int;var customExecutables=false;var windowsInstallPath="C:\\owned-game"}
enum SteamRuntimeFiles {static let windowsRoot="C:\\owned-steam"}
enum SteamSignIn {static func flag(_ key:String,default fallback:Bool)->Bool {fallback}}
@MainActor enum SteamLog {static var events:[String]=[];static func event(_ value:String){events.append(value)}}
@MainActor enum DockOffline {static var apps:[Int]=[];static func configure(appID:Int){apps.append(appID)}}
enum MadeiraDock {
"""
tests = r"""
}
@main struct Probe {
 @MainActor static func main() {
  let flag=SteamCyberThreatCompatibility.diagnosticFlag
  let fixed="-screen-quality Fastest"
  let marked=["owned-app",flag]
  func resolve(_ base:String?, _ enabled:Bool=true, _ id:Int=516590, _ args:[String]?=nil)->String? {
   SteamCyberThreatCompatibility.arguments(appID:id,base:base,enabled:enabled,processArguments:args ?? marked)
  }
  precondition(resolve(nil)==fixed && resolve("")==fixed)
  let base="  -logFile \"C:\\Owned Logs\\game.txt\"\t-console  "
  precondition(resolve(base)==base+" "+fixed)
  precondition(resolve(resolve(base))==resolve(base))
  for original:String? in [nil,"",base] {
   precondition(resolve(original,false)==original)
   precondition(resolve(original,true,516590,["owned-app"])==original)
   precondition(resolve(original,true,516590,["owned-app",flag+"-extra"])==original)
   for id in [0,516589,516591,450390,327140,428370,224960] {precondition(resolve(original,true,id)==original)}
  }
  for explicit in ["-screen-quality Good","\"-screen-quality\" \"Very High\"",
   "\t-screen-quality\t\"Fantastic\"  -console","-SCREEN-QUALITY Fastest",
   "-screen-quality=Good","-logFile \"C:\\logs\\test.txt\" -screen-quality \"Fastest\"",
   "-screen-quality","-logFile \"unterminated"] {precondition(resolve(explicit)==explicit)}
  let filename="-logFile \"C:\\Owned -screen-quality name\\game.txt\""
  precondition(resolve(filename)==filename+" "+fixed)
  let escaped="-logFile \"C:\\logs\\say\\\"hi\\\".txt\""
  precondition(resolve(escaped)==escaped+" "+fixed)
  precondition(resolve("-screen-quality-extra Good")=="-screen-quality-extra Good "+fixed)
  func value()->String? {getenv("MADEIRA_STEAM_HOST_EXTRA_ARGS").map{String(cString:$0)}}
  let selected=CommandLine.arguments.contains(flag)
  let game=DockGame(id:516590)
  setenv("MADEIRA_STEAM_HOST_EXTRA_ARGS","stale-other-game",1)
  MadeiraDock.configure(game)
  precondition(value()==(selected ? fixed:nil))
  precondition(getenv("MADEIRA_STEAM_HOST_APPID").map{String(cString:$0)}=="516590")
  MadeiraDock.configure(game,launchOption:7,argumentsOverride:base)
  precondition(value()==(selected ? base+" "+fixed:base))
  precondition(getenv("MADEIRA_STEAM_HOST_LAUNCH_OPTION").map{String(cString:$0)}=="7")
  let explicit=" -screen-quality \"Good\" "
  MadeiraDock.configure(game,argumentsOverride:explicit)
  precondition(value()==explicit)
  MadeiraDock.configure(game,argumentsOverride:fixed)
  precondition(value()==fixed)
  LaunchDiagnostics.enabled=false
  MadeiraDock.configure(game,argumentsOverride:base)
  precondition(value()==base)
  MadeiraDock.configure(game)
  precondition(value()==nil)
  LaunchDiagnostics.enabled=true
  MadeiraDock.configure(DockGame(id:450390))
  precondition(value()=="-noaq -aqmaxscale 1")
  MadeiraDock.configure(DockGame(id:386690))
  precondition(value()=="-vrmode openvr")
  let dosbox="-conf \"C:\\owned\\software.conf\""
  MadeiraDock.configure(DockGame(id:224960),argumentsOverride:dosbox)
  precondition(value()==dosbox)
  for id in [327140,428370,516589] {
   MadeiraDock.configure(DockGame(id:id));precondition(value()==nil)
   MadeiraDock.configure(DockGame(id:id),argumentsOverride:base);precondition(value()==base)
  }
  print("PASS actual configure diagnostic flag present=\(selected): enabled/app/flag scope, explicit quality/base preservation, idempotence, normal/Lab/OpenVR/DOSBox behavior")
 }
}
"""
probe = a.build/"probe.swift"
probe.write_text(text["helper"]+"\n"+text["cyber"]+"\n"+shell+extra+"\n"+configure+tests)
cmd=["xcrun","swiftc","-swift-version","6","-parse-as-library","-module-cache-path",str(tmp/"cache"),str(probe),"-o",str(a.build/"probe")]
compile_result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=120)
(a.build/"compile.log").write_text(compile_result.stdout+compile_result.stderr)
compile_result.check_returncode()
runs=[]
for arguments in [[],["--cyberthreat-low-memory-test"]]:
    result=subprocess.run([str(a.build/"probe")]+arguments,env=env,capture_output=True,text=True,timeout=20)
    (a.build/("execution-flag.log" if arguments else "execution-normal.log")).write_text(result.stdout+result.stderr)
    result.check_returncode()
    runs.append({"arguments":arguments,"stdout":result.stdout})
report={"passed":True,"scope":__doc__,"command":cmd,"sourceSha256":{str(paths[n]):hashlib.sha256(t.encode()).hexdigest() for n,t in text.items()},
        "testScriptSha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "entryRouteAssertions":["normal UI -> startLaunch -> model.launch -> sharedconfigure",
                                "diagnostic Steam selection -> startLaunch -> model.launch -> sharedconfigure",
                                "model.launch restores selection before freezing -> sharedconfigure"],
        "runs":runs}
(a.build/"result.json").write_text(json.dumps(report,indent=2)+"\n")
print("".join(r["stdout"] for r in runs),end="")
