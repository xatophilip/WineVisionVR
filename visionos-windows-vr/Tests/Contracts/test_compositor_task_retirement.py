#!/usr/bin/env python3
"""Execute actual compositor task store and serial executor under Swift 6.

Controlled suspension proves retired renderers finish cleanup before a replacement
starts. No graphics, ARKit session, guest runtime or headset is invoked.
"""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',required=True,type=Path)
a=p.parse_args();a.build=a.build.resolve();a.build.mkdir(parents=True,exist_ok=True)
(a.build/'tmp').mkdir(exist_ok=True)
env=dict(os.environ,TMPDIR=str(a.build/'tmp'))
source=(ROOT/'visionos-windows-vr/Sources/Rendering/WindowsVRCompositorScene.swift').read_text()
def extract(signature):
 start=source.index(signature);opening=source.index('{',start);end=opening+1;depth=1
 while depth:depth+=(source[end]=='{')-(source[end]=='}');end+=1
 return source[start:end]
store=extract('private final class WindowsVRCompositorTaskStore:')
executor=extract('private final class WindowsVRRenderTaskExecutor:')
shell=r"""
import Foundation
enum LaunchLogFile { static func append(_ category:String,_ message:String) {} }
func wvr_compositor_pause_v1() {}
actor Gate {
 var continuation:CheckedContinuation<Void,Never>?
 var open=false
 func wait() async {
  if open { return }
  await withCheckedContinuation { continuation=$0 }
 }
 func release() { open=true;continuation?.resume();continuation=nil }
}
actor Events {
 var entries:[String]=[]
 func add(_ text:String) { entries.append(text) }
 func has(_ text:String)->Bool { entries.contains(text) }
 func snapshot()->[String] { entries }
}
func require(_ value:Bool,_ message:String) { if !value { fatalError(message) } }
func until(_ events:Events,_ value:String) async {
 for _ in 0..<200 {
  if await events.has(value) { return }
  try? await Task.sleep(for:.milliseconds(2))
 }
 fatalError("Timed out waiting for "+value)
}
""" + store + '\n' + executor + r"""
@main struct Probe {
 static func main() async {
  let store=WindowsVRCompositorTaskStore()
  let events=Events(),gate=Gate()
  store.install {
   await events.add("old-start")
   await gate.wait()
   await events.add("old-cleanup")
  }
  await until(events,"old-start")
  store.stop() // Must retain this predecessor, even across a close/reopen.
  store.install { await events.add("new-start") }
  try? await Task.sleep(for:.milliseconds(30))
  require(!(await events.has("new-start")),"New renderer entered before stopped predecessor cleanup")
  await gate.release();await until(events,"new-start")
  let order=await events.snapshot()
  require(order.firstIndex(of:"old-cleanup")! < order.firstIndex(of:"new-start")!,
          "Retired renderer paused state after replacement")
  print("PASS actual store/executor stop->replace waits for suspended predecessor cleanup")

  let rapid=WindowsVRCompositorTaskStore(),rapidEvents=Events(),rapidGate=Gate()
  rapid.install {
   await rapidEvents.add("first")
   await rapidGate.wait()
   await rapidEvents.add("retired")
  }
  await until(rapidEvents,"first")
  rapid.install { await rapidEvents.add("cancelled-middle") }
  rapid.install { await rapidEvents.add("last") }
  try? await Task.sleep(for:.milliseconds(20))
  require(!(await rapidEvents.has("last")),"Replacement chain bypassed predecessor")
  await rapidGate.release();await until(rapidEvents,"last")
  require(!(await rapidEvents.has("cancelled-middle")),"Cancelled waiting renderer started")
  print("PASS rapid replacement preserves retirement chain and never starts cancelled middle renderer")

  let stopped=WindowsVRCompositorTaskStore(),stopEvents=Events(),stopGate=Gate()
  stopped.install {
   await stopEvents.add("first")
   await stopGate.wait()
   await stopEvents.add("retired")
  }
  await until(stopEvents,"first")
  stopped.install { await stopEvents.add("must-not-start") }
  stopped.stop()
  await stopGate.release();await until(stopEvents,"retired")
  try? await Task.sleep(for:.milliseconds(20))
  require(!(await stopEvents.has("must-not-start")),"Stopped waiting replacement started")
  print("PASS stop while waiting suppresses new operation after predecessor retirement")
 }
}
"""
unit=a.build/'production-store.swift';unit.write_text(shell)
command=['xcrun','swiftc','-swift-version','6','-parse-as-library','-module-cache-path',
         str(a.build/'tmp/cache'),str(unit),'-o',str(a.build/'probe')]
subprocess.run(command,env=env,check=True,timeout=60)
result=subprocess.run([str(a.build/'probe')],env=env,capture_output=True,text=True,timeout=10)
(a.build/'stdout.txt').write_text(result.stdout);(a.build/'stderr.txt').write_text(result.stderr)
assert result.returncode==0,result.stdout+result.stderr
(a.build/'result.json').write_text(json.dumps(dict(passed=True,scope=__doc__,command=command,
 sourceSha256=hashlib.sha256(source.encode()).hexdigest(),stdout=result.stdout),indent=2)+'\n')
print(result.stdout,end='')
