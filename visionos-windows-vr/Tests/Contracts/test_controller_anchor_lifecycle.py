#!/usr/bin/env python3
"""Compile actual controller anchor-state/diagnostic methods with controlled SDK boundaries.
No controller, ARKit session, UI, native runtime or device is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--build", type=Path, required=True)
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix="controller-anchors-", dir=args.build.resolve()))
source = ROOT / "visionos-windows-vr/Sources/Rendering/WindowsVRControllerProvider.swift"
text = source.read_text()

def method(signature):
    start = text.index(signature)
    opening = text.index("{", start)
    end, depth = opening + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]

methods = "\n\n".join(method(s) for s in (
    "private func store(_ anchor: AccessoryAnchor,",
    "private func handleAnchorUpdate(",
    "private func removeAnchor(for role:",
    "private func logTrackingDiagnostic(",
    "private func logConnectedInventory(",
    "private func isCurrentTrackingGeneration(",
    "private static func role(for chirality:",
))
shell = r"""
import Foundation
import Darwin
struct Accessory {
 enum Chirality { case left,right,unspecified }
 let inherentChirality:Chirality
}
struct AccessoryAnchor {
 let id:UUID
 let accessory:Accessory
 var isTracked=false
 var trackingState="untracked"
}
struct AnchorUpdate<T> {
 enum Event { case added,updated,removed }
 let event:Event
 let anchor:T
}
final class AccessoryTrackingProvider { var state="running" }
protocol GCDevice:AnyObject {}
final class FakeDevice:GCDevice {}
@MainActor final class CHHapticEngine {
 var stops=0
 func stop(){stops+=1}
}
@MainActor enum LaunchDiagnostics { static var enabled=true }
@MainActor enum LaunchLogFile {
 static var rows:[(String,String)]=[]
 static func append(_ category:String,_ message:String){rows.append((category,message))}
}
@MainActor final class Probe {
 let lock=NSLock()
 var trackingGeneration:UInt64=1
 var anchorsByRole:[UInt32:AccessoryAnchor]=[:]
 var hapticPlayersByRole:[UInt32:Int]=[:]
 var hapticEnginesByRole:[UInt32:CHHapticEngine]=[:]
 var unavailable:[UInt32]=[]
 var lastConnectedInventory:String?
 var lastTrackingDiagnosticByRole:[UInt32:String]=[:]
 private func publishUnavailable(role:UInt32){unavailable.append(role)}
"""
driver = r"""
 func check(_ condition:Bool,_ message:String){
  if !condition {print("FAIL: "+message);exit(77)}
 }
 func run(){
  let old=AccessoryAnchor(id:UUID(),accessory:Accessory(inherentChirality:.right))
  let replacement=AccessoryAnchor(id:UUID(),accessory:Accessory(inherentChirality:.right),isTracked:true,trackingState:"positionOrientationTracked")
  let left=AccessoryAnchor(id:UUID(),accessory:Accessory(inherentChirality:.left))
  handleAnchorUpdate(AnchorUpdate(event:.added,anchor:old),generation:1)
  handleAnchorUpdate(AnchorUpdate(event:.added,anchor:left),generation:1)
  handleAnchorUpdate(AnchorUpdate(event:.updated,anchor:replacement),generation:1)
  let rightEngine=CHHapticEngine(),leftEngine=CHHapticEngine()
  hapticEnginesByRole=[0:leftEngine,1:rightEngine];hapticPlayersByRole=[0:2,1:3]
  handleAnchorUpdate(AnchorUpdate(event:.removed,anchor:old),generation:1)
  check(anchorsByRole[1]?.id==replacement.id,"old removal erased replacement")
  check(anchorsByRole[0]?.id==left.id && unavailable.isEmpty,"stale removal affected another role or native state")
  check(rightEngine.stops==0 && hapticPlayersByRole[1]==3,"stale removal stopped replacement haptics")
  print("PASS actual event pipeline keeps same-hand replacement after old removal")
  handleAnchorUpdate(AnchorUpdate(event:.removed,anchor:replacement),generation:0)
  check(anchorsByRole[1]?.id==replacement.id && unavailable.isEmpty,"old generation removed current anchor")
  handleAnchorUpdate(AnchorUpdate(event:.removed,anchor:replacement),generation:1)
  check(anchorsByRole[1]==nil && unavailable==[1],"current removal did not publish unavailable exactly once")
  check(rightEngine.stops==1 && hapticPlayersByRole[1]==nil,"current removal did not stop its haptics")
  check(anchorsByRole[0]?.id==left.id && leftEngine.stops==0 && hapticPlayersByRole[0]==2,"right removal changed left")
  handleAnchorUpdate(AnchorUpdate(event:.removed,anchor:replacement),generation:1)
  check(unavailable==[1] && rightEngine.stops==1,"duplicate removal repeated native/haptic release")
  handleAnchorUpdate(AnchorUpdate(event:.added,anchor:old),generation:0)
  let unknown=AccessoryAnchor(id:UUID(),accessory:Accessory(inherentChirality:.unspecified))
  handleAnchorUpdate(AnchorUpdate(event:.added,anchor:unknown),generation:1)
  check(anchorsByRole.count==1 && anchorsByRole[0]?.id==left.id,"stale or unspecified update accepted")
  print("PASS current/duplicate removal, generation isolation, chirality and opposite-hand haptics")
  LaunchLogFile.rows=[]
  let a=FakeDevice(),b=FakeDevice()
  logConnectedInventory([a,b]);logConnectedInventory([b,a])
  check(LaunchLogFile.rows.count==1,"stable reordered raw inventory flooded logs")
  logConnectedInventory([a]);logConnectedInventory([a]);logConnectedInventory([a,b])
  check(LaunchLogFile.rows.count==3,"raw inventory disappearance/reconnect not reported")
  check(LaunchLogFile.rows[0].1.contains("raw connected count=2"),"raw inventory count missing")
  print("PASS raw device inventory logs only actual set transitions")
  LaunchLogFile.rows=[]
  let provider=AccessoryTrackingProvider()
  logTrackingDiagnostic(role:0,provider:nil,anchor:nil,predictedAnchor:nil)
  logTrackingDiagnostic(role:0,provider:nil,anchor:nil,predictedAnchor:nil)
  logTrackingDiagnostic(role:0,provider:provider,anchor:nil,predictedAnchor:nil)
  logTrackingDiagnostic(role:0,provider:provider,anchor:left,predictedAnchor:nil)
  logTrackingDiagnostic(role:0,provider:provider,anchor:left,predictedAnchor:left)
  logTrackingDiagnostic(role:0,provider:provider,anchor:replacement,predictedAnchor:replacement)
  logTrackingDiagnostic(role:0,provider:provider,anchor:replacement,predictedAnchor:replacement)
  check(LaunchLogFile.rows.count==5,"tracking diagnostic repeated stable state")
  let reasons=["no-provider","no-anchor","prediction-unavailable","anchor-untracked","tracked"]
  for (index,reason) in reasons.enumerated(){
   check(LaunchLogFile.rows[index].1.contains("reason="+reason+" "),"missing precise tracking reason")
  }
  LaunchDiagnostics.enabled=false
  logConnectedInventory([]);logTrackingDiagnostic(role:1,provider:nil,anchor:nil,predictedAnchor:nil)
  check(LaunchLogFile.rows.count==5,"diagnostics disabled still logged")
  print("PASS diagnostic reasons separate missing anchor/prediction/untracked and stay transition-only")
 }
}
@main struct Main { @MainActor static func main(){Probe().run()} }
"""
unit = work / "current.swift"
unit.write_text(shell + methods + driver)
env = dict(os.environ, TMPDIR=str(work), CLANG_MODULE_CACHE_PATH=str(work/"module-cache"))
command = ["xcrun", "swiftc", "-swift-version", "6", "-parse-as-library", str(unit), "-o", str(work/"probe")]
subprocess.run(command, env=env, check=True, timeout=90)
result = subprocess.run([str(work/"probe")], env=env, capture_output=True, text=True, timeout=10)
(work/"stdout.txt").write_text(result.stdout)
(work/"stderr.txt").write_text(result.stderr)
assert result.returncode == 0, result.stdout + result.stderr
# Reproduce the previous role-only removal by dropping only the anchor-ID
# predicate from the actual method. The identical event test must reject it.
assert "anchorsByRole[role]?.id == anchorID" in methods
broken = methods.replace("anchorsByRole[role]?.id == anchorID", "true", 1)
negative = work/"role-only-negative.swift"
negative.write_text(shell + broken + driver)
negative_command = [*command[:-3], str(negative), "-o", str(work/"role-only-negative")]
subprocess.run(negative_command, env=env, check=True, timeout=90)
bad = subprocess.run([str(work/"role-only-negative")], env=env, capture_output=True, text=True, timeout=10)
assert bad.returncode == 77 and "old removal erased replacement" in bad.stdout, bad.stdout + bad.stderr
report = dict(passed=True, scope=__doc__, sourceSha256=hashlib.sha256(source.read_bytes()).hexdigest(),
              methodsSha256=hashlib.sha256(methods.encode()).hexdigest(), command=command,
              stdout=result.stdout, negativeCommand=negative_command, negativeExit=bad.returncode,
              negativeStdout=bad.stdout, generatedSourceSha256=hashlib.sha256(unit.read_bytes()).hexdigest())
(work/"result.json").write_text(json.dumps(report, indent=2)+"\n")
print(result.stdout, end="")
print("PASS prior role-only removal rejected by actual pipeline regression")
print("Receipt:", work/"result.json")
