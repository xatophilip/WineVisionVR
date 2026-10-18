#!/usr/bin/env python3
"""Execute The Lab's production shared Steam argument/environment boundary under Swift 6.

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
assert "base: argumentsOverride ?? extraLaunchArguments(appID: game.id)" in configure
extra = body(text["dock"], "static func extraLaunchArguments(")
shell = r"""
import Foundation
enum LaunchDiagnostics {static let enabled=false}
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
  func value()->String? {getenv("MADEIRA_STEAM_HOST_EXTRA_ARGS").map{String(cString:$0)}}
  let fixed="-noaq -aqmaxscale 1"
  let lab=DockGame(id:450390)
  // All three production entry routes converge on this exact implementation.
  for _ in 0..<3 {
   setenv("MADEIRA_STEAM_HOST_EXTRA_ARGS","stale-other-game",1)
   MadeiraDock.configure(lab)
   precondition(value()==fixed)
   precondition(getenv("MADEIRA_STEAM_HOST_APPID").map{String(cString:$0)}=="450390")
   precondition(getenv("MADEIRA_STEAM_HOST_LAUNCH_OPTION").map{String(cString:$0)}=="0")
  }
  MadeiraDock.configure(lab,launchOption:7,argumentsOverride:"")
  precondition(value()==fixed)
  precondition(getenv("MADEIRA_STEAM_HOST_LAUNCH_OPTION").map{String(cString:$0)}=="7")
  let explicit="-console -logFile \"C:\\Owned Logs\\lab.txt\" -aqmaxscale 0.8"
  MadeiraDock.configure(lab,argumentsOverride:explicit)
  precondition(value()==explicit+" "+fixed) // Exact user text, order and quoting survive.
  precondition(SteamLabCompatibility.arguments(appID:450390,base:value())==value())
  MadeiraDock.configure(lab,argumentsOverride:fixed)
  precondition(value()==fixed)
  for id in [0,428370,327140,412740,450389,450391] {
   MadeiraDock.configure(DockGame(id:id))
   precondition(value()==nil)
   MadeiraDock.configure(DockGame(id:id),argumentsOverride:explicit)
   precondition(value()==explicit)
  }
  MadeiraDock.configure(DockGame(id:386690))
  precondition(value()=="-vrmode openvr")
  let dosbox="-conf \"C:\\owned\\software.conf\" -noautoexec -c \"mount C .\""
  MadeiraDock.configure(DockGame(id:224960),argumentsOverride:dosbox)
  precondition(value()==dosbox)
  precondition(DockOffline.apps.suffix(2)==[386690,224960])
  print("PASS production configure applies official fixed quality only to450390, preserves explicit arguments/launchoption, clears stale extras and retains other-game/DOSBox/OpenVR behavior")
 }
}
"""
probe = a.build/"probe.swift"
probe.write_text(text["helper"]+"\n"+text["cyber"]+"\n"+shell+extra+"\n"+configure+tests)
cmd=["xcrun","swiftc","-swift-version","6","-parse-as-library","-module-cache-path",str(tmp/"cache"),str(probe),"-o",str(a.build/"probe")]
compile_result=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=120)
(a.build/"compile.log").write_text(compile_result.stdout+compile_result.stderr)
compile_result.check_returncode()
result=subprocess.run([str(a.build/"probe")],env=env,capture_output=True,text=True,timeout=20)
(a.build/"execution.log").write_text(result.stdout+result.stderr)
result.check_returncode()
report={"passed":True,"scope":__doc__,"command":cmd,"sourceSha256":{str(paths[n]):hashlib.sha256(t.encode()).hexdigest() for n,t in text.items()},
        "testScriptSha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "entryRouteAssertions":["normal UI -> startLaunch -> model.launch -> sharedconfigure",
                                "diagnostic Steam selection -> startLaunch -> model.launch -> sharedconfigure",
                                "model.launch restores selection before freezing -> sharedconfigure"],
        "stdout":result.stdout}
(a.build/"result.json").write_text(json.dumps(report,indent=2)+"\n")
print(result.stdout,end="")
