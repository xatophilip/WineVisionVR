#!/usr/bin/env python3
"""Execute production Return-to-VR model/UI methods with lifecycle boundaries.

Open/dismiss immersive-space actions, compositor readiness, native runtime,
diagnostic journal and logging are recording stand-ins. No guest, ARKit service,
headset, graphics device or native plugin executes.
"""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--build', required=True, type=Path)
a = p.parse_args()
a.build = a.build.resolve()
a.build.mkdir(parents=True, exist_ok=True)
(a.build/'tmp').mkdir(exist_ok=True)
env = dict(os.environ, TMPDIR=str(a.build/'tmp'),
           CLANG_MODULE_CACHE_PATH=str(a.build/'tmp/cache'),
           SWIFT_MODULECACHE_PATH=str(a.build/'tmp/cache'))
model_path = ROOT/'visionos-windows-vr/Sources/LauncherModel.swift'
view_path = ROOT/'visionos-windows-vr/Sources/ContentView.swift'
model, view = model_path.read_text(), view_path.read_text()

def body(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    end, depth = opening+1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

methods = '\n'.join(body(model, name) for name in [
    'var canReturnToVR: Bool',
    'func immersiveSpaceDidOpen()',
    'func immersiveSpaceDidClose() async',
    'private func preserveSessionForVRReturn()',
    'func returnToVR(preparePresentation:',
    'func stop() async'])
late_close = body(model, 'if launchManifest.presentation == .immersiveVR && (!immersiveSpaceIsOpen')
ui_method = body(view, 'private func returnToVR() async').replace('private func', 'func', 1)
assert 'model.canReturnToVR || model.isReturningToVR' in view
assert '.accessibilityIdentifier("return-to-vr")' in view
assert 'Button { Task { await returnToVR() } }' in view
assert 'End session' in view and 'await model.stop()' in view

shell = r"""
import Foundation
enum Presentation { case immersiveVR, desktop }
enum Failure:Error { case notReady, stopPending }
enum LaunchPreparationFailure:Error { case immersiveSpaceClosed, immersiveSpaceUnavailable }
enum OpenResult { case opened, userCancelled, error }
enum Outcome { case stopped }
func L(_ english:String,_ german:String)->String { english }
@MainActor final class Log { func notice(_ text:String) {} }
@MainActor final class Monitor {
 var cancellations=0
 func cancel() { cancellations+=1 }
}
@MainActor final class Runtime {
 var stops=0
 var stopFails=false
 func stop() async throws { stops+=1;await Task.yield();if stopFails { throw Failure.stopPending } }
}
@MainActor final class Model {
 var presentationModeDraft=Presentation.immersiveVR
 var hasAcceptedLaunch=true,isLaunching=false,isStopping=false,stopRequested=false,requiresRestart=false
 var isReturningToVR=false,immersiveSpaceIsOpen=true,immersiveSpaceClosedDuringLaunch=false
 var runtimeStatus="",launchError:String?
 let launchLog=Log(),runtime=Runtime(),monitor=Monitor()
 var statusMonitor:Monitor?
 var snapshots:[String]=[],finished=0,released=0,readinessCalls=0
 var readinessFails=false
 init() { statusMonitor=monitor }
 func recordLifecycleEvent(_ reason:String) {}
 func snapshotTestSession(reason:String) { snapshots.append(reason) }
 func finishTestSession(outcome:Outcome,reason:String) { finished+=1 }
 func releaseGameDirectoryAccess() { released+=1 }
 func recordStopFailure(_ error:Error,becauseImmersiveClosed:Bool) { stopRequested=true }
 func waitForCompositorReady() async throws {
  readinessCalls+=1
  await Task.yield()
  if readinessFails { throw Failure.notReady }
 }
"""
ui_shell = r"""
enum WindowsVRCompositorScene { static let identifier="WindowsVRCompositor" }
@MainActor final class UI {
 let model:Model
 var nextOpen=OpenResult.opened
 var opens=0,dismissals=0
 init(_ model:Model) { self.model=model }
 func openImmersiveSpace(id:String) async->OpenResult {
  opens+=1
  await Task.yield()
  return nextOpen
 }
 func dismissImmersiveSpace() async {
  dismissals+=1
  await model.immersiveSpaceDidClose()
 }
"""
tests = r"""
func check(_ condition:@autoclosure ()->Bool,_ message:String) {
 if !condition() { fatalError(message) }
}
@main struct Driver {
 @MainActor static func main() async {
  let m=Model()
  await m.immersiveSpaceDidClose()
  check(m.canReturnToVR && m.hasAcceptedLaunch && !m.requiresRestart,"Closing accepted VR lost resumable session")
  check(m.runtime.stops==0 && m.finished==0 && m.released==0,"Closing VR stopped native guest or released its files")
  check(m.statusMonitor === m.monitor && m.monitor.cancellations==0,"Closing VR cancelled runtime monitoring")
  let ui=UI(m)
  await ui.returnToVR()
  check(ui.opens==1 && ui.dismissals==0 && m.readinessCalls==1 && m.immersiveSpaceIsOpen,"Return did not open and wait for fresh compositor")
  check(!m.canReturnToVR && !m.isReturningToVR && m.hasAcceptedLaunch,"Successful return left invalid lifecycle flags")
  check(m.runtime.stops==0 && m.finished==0 && m.released==0,"Return replaced/stopped guest or session")
  print("PASS: accepted close retains guest, journal, directory access and monitor; UI return only opens presentation and waits for readiness")

  await m.immersiveSpaceDidClose()
  ui.nextOpen = .userCancelled
  await ui.returnToVR()
  check(ui.opens==2 && ui.dismissals==0 && m.canReturnToVR && m.launchError != nil,"Cancelled open did not remain retryable")
  ui.nextOpen = .opened
  m.readinessFails=true
  await ui.returnToVR()
  check(ui.opens==3 && ui.dismissals==1 && m.canReturnToVR && m.hasAcceptedLaunch,"Failed readiness did not dismiss only new presentation and retain retry")
  check(m.runtime.stops==0 && m.released==0,"Failed reopen stopped retained game")
  m.readinessFails=false
  await ui.returnToVR()
  check(ui.opens==4 && m.immersiveSpaceIsOpen && m.launchError==nil,"Retry after cancelled/failed reopen did not recover")
  print("PASS: user-cancelled and failed-readiness reopen preserve game and allow another explicit return")

  await m.immersiveSpaceDidClose()
  var began=false,release=false
  let first=Task { @MainActor in
   await m.returnToVR {
    began=true
    while !release { await Task.yield() }
    m.immersiveSpaceDidOpen()
   }
  }
  while !began { await Task.yield() }
  let duplicate=await m.returnToVR { fatalError("Duplicate reopen executed") }
  check(!duplicate && m.isReturningToVR,"Concurrent return was not rejected")
  release=true
  check(await first.value,"First guarded reopen did not complete")
  check(!m.isReturningToVR,"Return lock not released")
  print("PASS: concurrent Return actions open only once")

  await m.immersiveSpaceDidClose()
  let cancellation=await m.returnToVR { throw CancellationError() }
  check(!cancellation && m.canReturnToVR && m.runtime.stops==0,"Cancelled return killed or stranded session")
  // Stop can win while a presentation open/readiness operation is suspended.
  let stopRace=await m.returnToVR {
   m.immersiveSpaceDidOpen()
   await m.stop()
  }
  check(!stopRace && !m.hasAcceptedLaunch && m.requiresRestart && !m.canReturnToVR,"End Session during reopen resurrected guest")
  check(m.runtime.stops==1 && m.finished==1 && m.released==1 && m.monitor.cancellations==1,"Explicit End Session did not perform its original cleanup once")
  await m.immersiveSpaceDidClose()
  check(m.runtime.stops==1,"Close after End Session stopped twice")
  print("PASS: cancellation retains guest; explicit End Session still wins and cleans up exactly once")

  let late=Model()
  late.hasAcceptedLaunch=false;late.isLaunching=true
  await late.immersiveSpaceDidClose()
  check(late.immersiveSpaceClosedDuringLaunch && !late.canReturnToVR,"Pre-acceptance close bypassed initial launch gate")
  late.hasAcceptedLaunch=true
  late.completeLateLaunch()
  late.isLaunching=false
  check(late.canReturnToVR && late.runtime.stops==0 && !late.requiresRestart,"Late accepted launch close still auto-stopped guest")
  print("PASS: close racing native acceptance preserves same guest instead of requiring restart")

  for field in 0..<8 {
   let gate=Model();gate.immersiveSpaceIsOpen=false
   switch field {
   case 0:gate.presentationModeDraft = .desktop
   case 1:gate.hasAcceptedLaunch=false
   case 2:gate.immersiveSpaceIsOpen=true
   case 3:gate.isLaunching=true
   case 4:gate.isReturningToVR=true
   case 5:gate.isStopping=true
   case 6:gate.stopRequested=true
   default:gate.requiresRestart=true
   }
   check(!gate.canReturnToVR,"Ineligible return gate admitted session")
   let result=await gate.returnToVR { fatalError("Ineligible reopen executed") }
   check(!result,"Ineligible return succeeded")
  }
  print("PASS: desktop, unaccepted, already-open, launch, return, stopping, stop-pending and restart guards reject reopen")
 }
}
"""
# Swift check takes a synchronous autoclosure; await the task value separately.
tests = tests.replace('check(await first.value,', 'let firstResult=await first.value\n  check(firstResult,')
unit = a.build/'main.swift'
unit.write_text(shell+methods+'\nfunc completeLateLaunch() {\nstruct Manifest { var presentation:Presentation }\nlet launchManifest=Manifest(presentation:presentationModeDraft)\n'+late_close+'\n}\n}\n'+ui_shell+ui_method+'\n}\n'+tests)
command = ['xcrun', 'swiftc', '-swift-version', '6', '-parse-as-library',
           '-module-cache-path', str(a.build/'tmp/cache'), str(unit), '-o', str(a.build/'probe')]
subprocess.run(command, env=env, check=True, timeout=60)
result = subprocess.run([str(a.build/'probe')], env=env, capture_output=True, text=True, timeout=20)
(a.build/'stdout.txt').write_text(result.stdout)
(a.build/'stderr.txt').write_text(result.stderr)
assert result.returncode == 0, result.stdout+result.stderr
print(result.stdout, end='')
(a.build/'result.json').write_text(json.dumps(dict(passed=True, scope=__doc__, command=command,
    sourceSha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (model_path,view_path)},
    generatedProbeSha256=hashlib.sha256(unit.read_bytes()).hexdigest(), stdout=result.stdout), indent=2)+'\n')
