#!/usr/bin/env python3
"""Execute production compositor startup/lifecycle with controlled ARKit boundaries.

No ARKit service, headset, game, native runtime or compositor is invoked.
The actual renderer run/startTracking methods are compiled with session/layer
stand-ins that record startup, failure, cancellation, pause and cleanup.
"""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build',required=True,type=Path)
parser.add_argument('--baseline-source',type=Path)
args=parser.parse_args()
args.build=args.build.resolve();args.build.mkdir(parents=True,exist_ok=True)
(args.build/'tmp').mkdir(exist_ok=True)
env=dict(os.environ,TMPDIR=str(args.build/'tmp'),CLANG_MODULE_CACHE_PATH=str(args.build/'tmp/cache'),SWIFT_MODULECACHE_PATH=str(args.build/'tmp/cache'))
source_path=ROOT/'visionos-windows-vr/Sources/Rendering/WindowsVRCompositorScene.swift'

def body(text,signature):
 start=text.index(signature);opening=text.index('{',start);end=opening+1;depth=1
 while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]

shell=r'''
import Foundation
enum ProviderState { case initialized,running,stopped }
@MainActor protocol DataProvider:AnyObject { var state:ProviderState { get set } }
@MainActor final class World:DataProvider { var state=ProviderState.initialized }
typealias WorldTrackingProvider=World
@MainActor final class ControllerProvider:DataProvider { var state=ProviderState.initialized }
@MainActor struct Log {
 func notice(_ message:String) {}
 func error(_ message:String) {}
}
@MainActor enum LaunchLogFile { static func append(_ category:String,_ message:String) {} }
@MainActor func wvr_compositor_pause_v1() {}
@MainActor func wvr_compositor_bind_metal_device_v1(_ pointer:UnsafeMutableRawPointer)->Int32 { 0 }
enum Permission:Hashable { case worldSensing,accessoryTracking }
enum Authorization { case allowed }
enum Failure:Error { case unavailable }
@MainActor final class Layer {
 enum State { case running,paused,invalidated }
 struct Configuration { var isFoveationEnabled=false }
 let configuration=Configuration()
 let device=NSObject()
 var state=State.running
 var resumes=0
 func waitUntilRunning() { resumes+=1;state = .running }
 func pause() {
  state = .paused
  Task { try? await Task.sleep(for:.milliseconds(40));resumes+=1;state = .running }
 }
}
@MainActor final class Session {
 var outcomes:[Bool]
 var attempts=0,stops=0,overlaps=0,stoppedReuses=0
 var providers:[any DataProvider]=[],retired:[any DataProvider]=[]
 var delayedStopState=false
 var runHookAttempt=1
 var active=false
 var authorizationHook:(()->Void)?
 var runHook:(()->Void)?
 var times:[TimeInterval]=[]
 init(_ outcomes:[Bool]) { self.outcomes=outcomes }
 func requestAuthorization(for permissions:[Permission]) async->[Permission:Authorization] {
  await Task.yield();let hook=authorizationHook;authorizationHook=nil;hook?()
  return [.worldSensing:.allowed,.accessoryTracking:.allowed]
 }
 func run(_ providers:[any DataProvider]) async throws {
  attempts+=1;times.append(ProcessInfo.processInfo.systemUptime)
  await Task.yield()
  if active { overlaps+=1 }
  if providers.contains(where:{ provider in provider.state == .stopped || retired.contains(where:{$0 === provider}) }) { stoppedReuses+=1;throw Failure.unavailable }
  self.providers=providers
  let success=outcomes.isEmpty ? true:outcomes.removeFirst()
  if !success { retired.append(contentsOf:providers);for provider in providers { provider.state = .stopped };throw Failure.unavailable }
  for provider in providers { provider.state = .running }
  active=true
  if attempts==runHookAttempt { let hook=runHook;runHook=nil;hook?() }
 }
 func stop() { stops+=1;active=false;retired.append(contentsOf:providers);if !delayedStopState { for provider in providers { provider.state = .stopped } };providers=[] }
}
@MainActor final class Controllers {
 var configurations=0,resets=0
 var configured=false
 var configureHook:(()->Void)?
 func configure(authorized:Bool) async->[any DataProvider] {
  configurations+=1;configured=true
  await Task.yield();let hook=configureHook;configureHook=nil;hook?()
  return [ControllerProvider()]
 }
 func reset() { resets+=1;configured=false }
 func publishUnavailableState() {}
}
@MainActor final class Renderer {
 static let log=Log()
 let layerRenderer=Layer(),controllerTracking=Controllers()
 var worldTracking=World()
 let arSession:Session
 var frames=0,invalidFrames=0
 var pauseAfterFirst=false
 init(_ outcomes:[Bool]) { arSession=Session(outcomes) }
 func publishUnavailablePose() {}
 func renderNextFrame() {
  if layerRenderer.state != .running || Task.isCancelled { invalidFrames+=1 }
  frames+=1
  if pauseAfterFirst && frames==1 { layerRenderer.pause() }
  if frames>=3 { withUnsafeCurrentTask { $0?.cancel() } }
 }
'''
driver=r'''
}
@MainActor func check(_ value:@autoclosure ()->Bool,_ message:String) {
 if !value(){fatalError(message)}
}
@main struct Probe {
 @MainActor static func main() async {
  let baseline=CommandLine.arguments.contains("--baseline")
  let names=baseline ? ["recovery"]:["recovery","fallback","pause","cancel-authorization",
       "cancel-configure","pause-run","invalidate-run","cancel-run","persistent-cancel",
       "delayed-stop","pause-authorization","invalidate-authorization","pause-configure",
       "invalidate-configure","pause-fallback","cancel-fallback","invalidate-fallback","cancel-paused"]
  for name in names {
   let outcomes:[Bool]=name=="recovery" ? [false,false,true] :
       (name=="fallback" || name.hasSuffix("-fallback") ? [false,true,true] : (name=="persistent-cancel" ? Array(repeating:false,count:100):[true,true]))
   let renderer=Renderer(outcomes)
   if name=="pause" || name=="delayed-stop" { renderer.pauseAfterFirst=true }
   if name=="delayed-stop" { renderer.arSession.delayedStopState=true }
   for phase in ["authorization","configure","fallback"] {
    if name=="pause-"+phase || name=="invalidate-"+phase || name=="cancel-"+phase {
     let hook:()->Void={
      if name.hasPrefix("pause-") { renderer.layerRenderer.pause() }
      else if name.hasPrefix("invalidate-") { renderer.layerRenderer.state = .invalidated }
      else { withUnsafeCurrentTask { $0?.cancel() } }
     }
     if phase=="authorization" { renderer.arSession.authorizationHook=hook }
     if phase=="configure" { renderer.controllerTracking.configureHook=hook }
     if phase=="fallback" { renderer.arSession.runHookAttempt=2;renderer.arSession.runHook=hook }
    }
   }
   if name=="cancel-authorization" {
    renderer.arSession.authorizationHook={ withUnsafeCurrentTask { $0?.cancel() } }
   }
   if name=="cancel-configure" {
    renderer.controllerTracking.configureHook={ withUnsafeCurrentTask { $0?.cancel() } }
   }
   if name=="pause-run" { renderer.arSession.runHook={ renderer.layerRenderer.pause() } }
   if name=="invalidate-run" { renderer.arSession.runHook={ renderer.layerRenderer.state = .invalidated } }
   if name=="cancel-run" { renderer.arSession.runHook={ withUnsafeCurrentTask { $0?.cancel() } } }
   if name=="cancel-paused" { renderer.layerRenderer.state = .paused }
   let start=ProcessInfo.processInfo.systemUptime
   let task=Task { await renderer.run() }
   if name=="cancel-paused" {
    try? await Task.sleep(for:.milliseconds(50));task.cancel()
   }
   if name=="persistent-cancel" {
    try? await Task.sleep(for:.milliseconds(1200))
    task.cancel()
   }
   await task.value
   let session=renderer.arSession,controllers=renderer.controllerTracking
   check(!session.active && !controllers.configured,"Session/controller left active: "+name)
   check(session.overlaps==0,"Duplicate active session: "+name)
   if !baseline { check(session.stoppedReuses==0,"Stopped ARKit provider reused: "+name) }
   check(renderer.invalidFrames==0,"Rendered after cancellation/pause/invalidation: "+name)
   if name=="recovery" {
    check(session.attempts==3 && controllers.configurations==2 && renderer.frames==3,
          "Failed startup was latched as started; recovery never retried")
    check(session.times[2]-session.times[0]>=0.8,"Failed startup retried without bounded backoff")
   } else if name=="fallback" {
    check(session.attempts==2 && controllers.configurations==1 && renderer.frames==3,
          "World-only fallback should remain active without duplicate controller startup")
   } else if name=="pause" || name=="delayed-stop" || name=="pause-run" {
    check(session.attempts==2 && controllers.configurations==2 && renderer.layerRenderer.resumes==1,
          "Pause did not cleanly restart tracking")
   } else if name=="pause-authorization" || name=="pause-configure" {
    check(session.attempts==1 && renderer.layerRenderer.resumes==1 && renderer.frames==3,
          "Pause during setup failed to recover")
   } else if name=="invalidate-authorization" || name=="invalidate-configure" {
    check(session.attempts==0 && renderer.frames==0,"Session started after invalidation")
   } else if name=="pause-fallback" {
    check(session.attempts==3 && renderer.layerRenderer.resumes==1 && renderer.frames==3,
          "Pause after world-only run failed to recover")
   } else if name=="cancel-fallback" || name=="invalidate-fallback" {
    check(session.attempts==2 && renderer.frames==0,"World-only run rendered after termination")
   } else if name=="cancel-authorization" || name=="cancel-configure" {
    check(session.attempts==0 && renderer.frames==0,"Session started after cancellation")
   } else if name=="invalidate-run" || name=="cancel-run" {
    check(session.attempts==1 && renderer.frames==0,"Post-await termination rendered or restarted")
   } else if name=="cancel-paused" {
    check(session.attempts==0 && renderer.frames==0 && ProcessInfo.processInfo.systemUptime-start<0.3,
          "Paused SDK wait blocked renderer retirement")
   } else if name=="persistent-cancel" {
    check(session.attempts>=4 && session.attempts<=6,"Persistent failure hot loop or missing retry")
    check(ProcessInfo.processInfo.systemUptime-start<1.8,"Backoff ignored cancellation")
   }
   print("PASS tracking startup: "+name+" runCalls="+String(session.attempts)+" configurations="+String(controllers.configurations))
  }
 }
}
'''
def execute(text,name,baseline=False):
 unit=args.build/(name+'.swift')
 unit.write_text(shell+body(text,'func run() async')+'\n'+body(text,'private func startTracking()')+'\n'+driver)
 exe=args.build/name
 command=['xcrun','swiftc','-swift-version','6','-parse-as-library','-module-cache-path',str(args.build/'tmp/cache'),str(unit),'-o',str(exe)]
 subprocess.run(command,env=env,check=True,timeout=60)
 result=subprocess.run([str(exe),*(['--baseline'] if baseline else [])],env=env,capture_output=True,text=True,timeout=20)
 (args.build/(name+'.stdout')).write_text(result.stdout)
 (args.build/(name+'.stderr')).write_text(result.stderr)
 return dict(command=command,exitCode=result.returncode,stdout=result.stdout,stderr=result.stderr[:2000],sourceSha256=hashlib.sha256(text.encode()).hexdigest())

report={'scope':__doc__,'passed':False,'deviceActions':False}
if args.baseline_source:
 baseline=execute(args.baseline_source.read_text(),'baseline',True)
 assert baseline['exitCode']!=0 and 'Failed startup was latched as started' in baseline['stderr'],baseline
 report['baseline']=baseline
 print('PASS exact prior-source negative control reproduces latched failed startup')
current=execute(source_path.read_text(),'current')
report['current']=current
assert current['exitCode']==0,current
report['passed']=True
(args.build/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(current['stdout'],end='')
print('PASS actual compositor startup methods; controlled ARKit boundary only')
