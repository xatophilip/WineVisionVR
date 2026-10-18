#!/usr/bin/env python3
"""Execute production health classification and bounded current-session log provenance.

Controlled clocks and owned files exercise boundaries. Optional real captures are
copied into scratch files; no device, game, Steam account or graphics executes.
"""
import argparse, hashlib, json, os, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--build",required=True,type=Path)
p.add_argument("--captured-runtime",type=Path)
p.add_argument("--captured-pid",type=int)
p.add_argument("--captured-executable")
p.add_argument("--captured-failure",choices=["rendering","guest-exit-3","repeated-fault","none"])
a=p.parse_args()
if a.captured_runtime and (not a.captured_pid or not a.captured_executable or not a.captured_failure):
    p.error("Captured evidence requires PID, executable and expected failure")
a.build=a.build.resolve()
if a.build==ROOT or ROOT in a.build.parents:p.error("--build must be outside the checkout")
if a.captured_runtime:
    parent=a.captured_runtime.resolve().parent
    if a.build==parent or parent in a.build.parents:p.error("--build must not be inside the capture directory")
a.build.mkdir(parents=True,exist_ok=True)
scratch=Path(tempfile.mkdtemp(prefix="run-",dir=a.build))
tmp=a.build/"tmp";tmp.mkdir(exist_ok=True)
env=dict(os.environ,TMPDIR=str(tmp),CLANG_MODULE_CACHE_PATH=str(tmp/"cache"),SWIFT_MODULECACHE_PATH=str(tmp/"cache"))
source_path=ROOT/"visionos-windows-vr/Sources/GuestSessionHealth.swift"
source=source_path.read_text()
localization_path=ROOT/"windows-vr/Sources/WindowsVRCore/Localization.swift"
localization=localization_path.read_text()
assert "import WindowsVRCore" in source
probe_source=source.replace("import WindowsVRCore\n","")+"\n"+localization
main=r'''
func require(_ value:Bool,_ message:String){precondition(value,message)}
@main struct Probe {
 static func main() async throws {
  var state=GuestSessionHealth(now:0)
  require(state.update(now:0,frames:0,visible:true,running:true)==nil,"initial")
  require(state.update(now:34.9,frames:0,visible:true,running:true)==nil,"early")
  require(state.update(now:35,frames:0,visible:true,running:true) == .noFrames,"35s")
  require(state.update(now:36,frames:1,visible:true,running:true)==nil,"progress")
  require(state.update(now:80.9,frames:1,visible:true,running:true)==nil,"early stall")
  require(state.update(now:81,frames:1,visible:true,running:true) == .stalledFrames,"45s")
  require(state.update(now:82,frames:1,visible:false,running:true)==nil,"closed")
  require(state.update(now:1000,frames:1,visible:false,running:true)==nil,"away")
  require(state.update(now:1001,frames:1,visible:true,running:true)==nil,"return")
  require(state.update(now:1045.9,frames:1,visible:true,running:true)==nil,"return grace")
  require(state.update(now:1046,frames:1,visible:true,running:true) == .stalledFrames,"visible time")
  require(state.update(now:1047,frames:2,visible:true,running:true,failure:.rendering) == .reportedFailure(.rendering),"same-sample error")
  require(state.update(now:1048,frames:3,visible:true,running:true)==nil,"recover")
  require(state.update(now:1049,frames:3,visible:false,running:true,failure:.guestExit(3)) == .reportedFailure(.guestExit(3)),"real exit")
  require(state.update(now:1050,frames:3,visible:false,running:false,failure:.repeatedFault)==nil,"stop")
  print("PASS production visible-time thresholds, closure/return grace, progress recovery and explicit-error distinction")
  let root=URL(fileURLWithPath:CommandLine.arguments[1])
  try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
  let file=root.appendingPathComponent("runtime.txt")
  let header="revision-A: running image /owned/WindowsRuntimePlugin.framework/WindowsRuntimePlugin pid=732 LC_UUID=owned\n"
  let module="D 8C Load module TheLab.exe (owned): 100000\n"
  let fatal="008c:err:process:NtTerminateProcess NtTerminateProcess(handle=0x0, exit_code=0x3) syscalls=0\n"
  func write(_ text:String) throws {try Data(text.utf8).write(to:file)}
  func append(_ text:String) throws {
   let handle=try FileHandle(forWritingTo:file);try handle.seekToEnd()
   try handle.write(contentsOf:Data(text.utf8));try handle.close()
  }
  try write(header+module+fatal)
  let reader=GuestSessionLogMonitor(url:file,expectedPID:732,expectedExecutable:"TheLab.exe",startedAt:.distantPast)
  require(await reader.sample()==nil,"baseline old bytes")
  try append("ml989: running image /owned/WindowsRuntimePlugin.framework/WindowsRuntimePlugin pid=731 LC_UUID=old\nCannot create DX texture swap chain: err -25\n")
  require(await reader.sample()==nil,"wrong PID")
  try append("revision-B: running image /owned/other.dll pid=732 LC_UUID=unrelated\n"+module+fatal)
  require(await reader.sample()==nil,"unrelated image cannot establish native identity")
  try append(header+"D 90 Load module helper.exe (owned): 100000\n"+fatal)
  require(await reader.sample()==nil,"unowned thread")
  try append(module+"0090:err:process:NtTerminateProcess NtTerminateProcess(handle=0x0, exit_code=0x3)\n")
  require(await reader.sample()==nil,"helper termination")
  try append("008c:err:process:NtTerminateProcess NtTerminateProcess(handle=0x0, exit_code=0x0)\n")
  require(await reader.sample()==nil,"normal exit")
  try append(header+"[15:10:21.000] "+fatal)
  require(await reader.sample() == .guestExit(3),"timestamp and repeated native header")
  try append("dll-missing optional.dll.dll\nOpenXR Call failed ShutdownSession\nREFUSING unaligned atomic\n")
  require(await reader.sample()==nil,"generic warnings")
  try append("Cannot create DX texture swap chain: err -")
  require(await reader.sample()==nil,"partial")
  try append("25\n")
  require(await reader.sample() == .rendering,"render error")
  try append("[redeliv] terminating process rev=owned\n")
  require(await reader.sample() == .repeatedFault,"native fatal")
  let future=GuestSessionLogMonitor(url:file,expectedPID:732,expectedExecutable:"TheLab.exe",startedAt:Date().addingTimeInterval(3600))
  try append(fatal)
  require(await future.sample()==nil,"mtime before attempt")
  try FileManager.default.moveItem(at:file,to:root.appendingPathComponent("previous.txt"))
  try write("ml989: running image /owned/WindowsRuntimePlugin.framework/WindowsRuntimePlugin pid=731 LC_UUID=old\n"+module+fatal)
  require(await reader.sample()==nil,"rotation resets PID")
  try FileManager.default.removeItem(at:file)
  let bounded=GuestSessionLogMonitor(url:file,expectedPID:732,expectedExecutable:"TheLab.exe",startedAt:.distantPast)
  try write(header+String(repeating:"x",count:GuestSessionLogMonitor.maximumReadBytes)+"\nCannot create DX texture swap chain: err -25\n")
  require(await bounded.sample()==nil,"read budget")
  require(await bounded.sample() == .rendering,"cursor progress")
  let link=root.appendingPathComponent("linked.txt")
  try FileManager.default.createSymbolicLink(at:link,withDestinationURL:file)
  let unsafe=GuestSessionLogMonitor(url:link,expectedPID:732,expectedExecutable:"TheLab.exe",startedAt:.distantPast)
  require(await unsafe.sample()==nil,"reject link")
  let spaced=root.appendingPathComponent("spaced.txt")
  let spacedReader=GuestSessionLogMonitor(url:spaced,expectedPID:732,expectedExecutable:"C:\\Games\\Owned Game.exe",startedAt:.distantPast)
  try Data((header+"[15:10:21.000] D 8C Load module Owned Game.exe (owned): 100000\n"+fatal).utf8).write(to:spaced)
  require(await spacedReader.sample() == .guestExit(3),"module filename with spaces")
  print("PASS actual reader: stale bytes/PID/child, normal exit, partial writes, warning exclusions, mtime, rotation, bounds, links and spaced filenames")
  let journalRoot=root.appendingPathComponent("journal")
  try FileManager.default.createDirectory(at:journalRoot,withIntermediateDirectories:true)
  let journal=try SessionDiagnostics(documentsDirectory:journalRoot)
  let metadata=SessionDiagnostics.Metadata(title:"Owned game",manifestID:"owned",architecture:"x64",graphics:"Direct3D11",renderScale:1,appVersion:"test",buildNumber:"test")
  try journal.beginAttempt(metadata:metadata)
  let recovered=try SessionDiagnostics(documentsDirectory:journalRoot)
  require(try recovered.recoverPendingAttempt()=="Owned game","recovered title for UI")
  require(try recovered.recoverPendingAttempt()==nil,"no repeat recovery")
  try recovered.beginAttempt(metadata:metadata)
  try recovered.finish(outcome:.stopped,reason:"Confirmed stop")
  require(try recovered.recoverPendingAttempt()==nil,"confirmed stop is not interrupted")
  print("PASS actual journal recovery distinguishes pending attempts from confirmed stops without claiming crash cause")
  if CommandLine.arguments.count>2 {
   let input=URL(fileURLWithPath:CommandLine.arguments[2]),data=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[2]))
   let copy=root.appendingPathComponent("captured.txt")
   let monitor=GuestSessionLogMonitor(url:copy,expectedPID:Int32(CommandLine.arguments[3])!,expectedExecutable:CommandLine.arguments[4],startedAt:.distantPast)
   try data.write(to:copy)
   var failures:[GuestSessionHealth.Failure]=[]
   for _ in 0..<(data.count/GuestSessionLogMonitor.maximumReadBytes+2) {
    if let failure=await monitor.sample(){failures.append(failure)}
   }
   require(await monitor.currentGameWasObserved(),"capture must match actual current native PID and game module")
   let expected:GuestSessionHealth.Failure
   switch CommandLine.arguments[5] {
   case "rendering":expected = .rendering
   case "guest-exit-3":expected = .guestExit(3)
   default:expected = .repeatedFault
   }
   if CommandLine.arguments[5]=="none" {require(failures.isEmpty,"recovered capture must not become fatal")}
   else {require(failures.contains(expected),"actual capture")}
   require(try Data(contentsOf:input)==data,"capture preservation")
   print("PASS real captured runtime through production reader")
  }
 }
}
'''
journal_path=ROOT/"visionos-windows-vr/Sources/SessionDiagnostics.swift"
journal=journal_path.read_text()
probe=scratch/"probe.swift";probe.write_text(probe_source+"\n"+journal+"\n"+main)
cmd=["xcrun","swiftc","-swift-version","6","-parse-as-library","-module-cache-path",str(tmp/"cache"),str(probe),"-o",str(scratch/"probe")]
compiled=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=120)
(a.build/"compile.log").write_text(compiled.stdout+compiled.stderr);compiled.check_returncode()
command=[str(scratch/"probe"),str(scratch/"owned-files")]
if a.captured_runtime:command += [str(a.captured_runtime.resolve()),str(a.captured_pid),a.captured_executable,a.captured_failure]
run=subprocess.run(command,env=env,capture_output=True,text=True,timeout=25)
(a.build/"execution.log").write_text(run.stdout+run.stderr);run.check_returncode()

# Execute the actual model method across a controlled async reader boundary.
model_path=ROOT/"visionos-windows-vr/Sources/LauncherModel.swift"
model=model_path.read_text()
def method(text, signature):
    start=text.index(signature);end=text.index("{",start)+1;depth=1
    while depth:
        depth+=(text[end]=="{")-(text[end]=="}");end+=1
    return text[start:end]
refresh=method(model,"private func refreshSessionHealth(").replace("private func","func",1)
presentation=method(model,"private func healthPresentationIsActive(").replace("private func","func",1)
dismissal_request=method(model,"var sessionHealthPresentationDismissal:")
dismissal=method(model,"func dismissPresentationForSessionFailure(")
view_path=ROOT/"visionos-windows-vr/Sources/ContentView.swift"
view=view_path.read_text()
reveal=method(view,"private func revealConfirmedSessionFailure(").replace("private func","func",1)
monitor=method(model,"private func beginStatusMonitoring()")
assert "await self.refreshSessionHealth(attempt: attempt)" in monitor
assert "guard !Task.isCancelled, attempt == self.sessionHealthAttempt, self.hasAcceptedLaunch" in monitor
assert "await self.stop()" not in refresh
shell=r'''
actor GuestSessionLogMonitor {
 let failure:GuestSessionHealth.Failure?
 var arrived=false,released:Bool
 var gate:CheckedContinuation<Void,Never>?
 init(_ failure:GuestSessionHealth.Failure?=nil,released:Bool=true){self.failure=failure;self.released=released}
 func sample() async->GuestSessionHealth.Failure?{
  arrived=true
  if !released{await withCheckedContinuation{gate=$0}}
  return failure
 }
 func waiting()->Bool{arrived}
 func release(){released=true;gate?.resume();gate=nil}
}
struct Counter{var completedFrames:UInt64=0}
enum Presentation{case immersiveVR,desktop}
struct WVRCompositorReadinessV1{
 var structSize:UInt32=0,metalDeviceBound:UInt32=1,stereoTargetsPublished:UInt32=1,trackedHeadPoseAvailable:UInt32=1
 var trackingTimestampNanoseconds:UInt64=9_900_000_000
}
@MainActor enum NativeReadiness{static var value=WVRCompositorReadinessV1();static var status:Int32=0}
@MainActor func wvr_compositor_copy_readiness_v1(_ out:inout WVRCompositorReadinessV1)->Int32{out=NativeReadiness.value;return NativeReadiness.status}
func CACurrentMediaTime()->Double{10}
@MainActor enum LaunchLogFile{static var calls=0;static func append(_ a:String,_ b:String){calls+=1}}
@MainActor final class Model{
 var sessionHealthAttempt=UUID(),hasAcceptedLaunch=true
 var sessionHealthDismissedAttempt:UUID?
 var isLaunching=false
 var sessionHealthLog:GuestSessionLogMonitor?
 var sessionHealth:GuestSessionHealth?
 var sessionHealthNotice:GuestSessionHealth.Notice?
 var compositorCounters:Counter?=Counter()
 var presentationModeDraft=Presentation.immersiveVR
 var immersiveSpaceIsOpen=true,isReturningToVR=false,isStopping=false,stopRequested=false,requiresRestart=false
 var snapshots=0
 init(){
  let before=ProcessInfo.processInfo.systemUptime-100
  var health=GuestSessionHealth(now:before)
  _=health.update(now:before,frames:0,visible:true,running:true)
  sessionHealth=health
 }
 func snapshotTestSession(reason:String){snapshots+=1}
 func recordLifecycleEvent(_ reason:String){}
'''
model_main=r'''
}
@main struct ModelProbe{
 @MainActor static func main() async {
  for race in 0..<4{
   let m=Model(),log=GuestSessionLogMonitor(.rendering,released:false)
   m.sessionHealthLog=log
   let token=m.sessionHealthAttempt
   let task=Task{await m.refreshSessionHealth(attempt:token)}
   while !(await log.waiting()){await Task.yield()}
   switch race{
   case 0:m.hasAcceptedLaunch=false
   case 1:m.sessionHealthAttempt=UUID()
   case 2:task.cancel()
   default:m.stopRequested=true
   }
   await log.release();await task.value
   precondition(m.sessionHealthNotice==nil&&m.snapshots==0)
  }
  let m=Model()
  await m.refreshSessionHealth(attempt:m.sessionHealthAttempt)
  precondition(m.sessionHealthNotice == .noFrames&&m.snapshots==1)
  m.compositorCounters=Counter(completedFrames:1)
  await m.refreshSessionHealth(attempt:m.sessionHealthAttempt)
  precondition(m.sessionHealthNotice==nil)
  m.sessionHealthLog=GuestSessionLogMonitor(.rendering)
  await m.refreshSessionHealth(attempt:m.sessionHealthAttempt)
  precondition(m.sessionHealthNotice == .reportedFailure(.rendering))
  precondition(m.hasAcceptedLaunch && !m.requiresRestart && !m.stopRequested)
  m.compositorCounters=Counter(completedFrames:2);m.sessionHealthLog=nil
  await m.refreshSessionHealth(attempt:m.sessionHealthAttempt)
  precondition(m.sessionHealthNotice==nil)
  m.immersiveSpaceIsOpen=false;m.sessionHealthLog=GuestSessionLogMonitor(.rendering)
  await m.refreshSessionHealth(attempt:m.sessionHealthAttempt)
  precondition(m.sessionHealthNotice==nil)
  m.immersiveSpaceIsOpen=true
  NativeReadiness.value.stereoTargetsPublished=0 // Paused while still open.
  m.sessionHealthLog=nil
  await m.refreshSessionHealth(attempt:m.sessionHealthAttempt)
  precondition(m.sessionHealthNotice==nil)
  precondition(!m.healthPresentationIsActive())
  NativeReadiness.value.stereoTargetsPublished=1
  NativeReadiness.value.trackingTimestampNanoseconds=0 // Inactive/stale tracking.
  precondition(!m.healthPresentationIsActive())
  NativeReadiness.value.trackingTimestampNanoseconds=9_900_000_000
  m.presentationModeDraft = .desktop
  precondition(!m.healthPresentationIsActive())
  await m.refreshSessionHealth(attempt:m.sessionHealthAttempt)
  precondition(m.sessionHealthNotice==nil)
  m.presentationModeDraft = .immersiveVR
  precondition(m.healthPresentationIsActive())
  NativeReadiness.status = -1;precondition(!m.healthPresentationIsActive());NativeReadiness.status = 0
  NativeReadiness.value.metalDeviceBound=0;precondition(!m.healthPresentationIsActive());NativeReadiness.value.metalDeviceBound=1
  NativeReadiness.value.trackedHeadPoseAvailable=0;precondition(!m.healthPresentationIsActive());NativeReadiness.value.trackedHeadPoseAvailable=1
  NativeReadiness.value.trackingTimestampNanoseconds=11_000_000_000
  precondition(!m.healthPresentationIsActive())
  NativeReadiness.value.trackingTimestampNanoseconds=9_900_000_000
  m.isReturningToVR=true;precondition(!m.healthPresentationIsActive());m.isReturningToVR=false
  m.sessionHealthLog=GuestSessionLogMonitor(.guestExit(3))
  await m.refreshSessionHealth(attempt:m.sessionHealthAttempt)
  precondition(m.sessionHealthNotice == .reportedFailure(.guestExit(3)))
  precondition(m.hasAcceptedLaunch && !m.requiresRestart && !m.stopRequested)
  // Invoke the exact ContentView handler and exact model guard, including a
  // queued task whose attempt becomes stale before it is dispatched.
  for refusal in 0..<11 {
   let f=Model();f.sessionHealthNotice = .reportedFailure(.guestExit(3))
   let token=f.sessionHealthAttempt
   switch refusal {
   case 0:f.sessionHealthNotice = .noFrames
   case 1:f.sessionHealthNotice = .stalledFrames
   case 2:f.hasAcceptedLaunch=false
   case 3:f.immersiveSpaceIsOpen=false
   case 4:f.isStopping=true
   case 5:f.stopRequested=true
   case 6:f.isReturningToVR=true
   case 7:f.presentationModeDraft = .desktop
   case 8:f.sessionHealthAttempt=UUID()
   case 9:f.isLaunching=true
   default:f.requiresRestart=true
   }
   let view=View(model:f)
   await view.revealConfirmedSessionFailure(attempt:token)
   precondition(view.dismissals==0 && f.hasAcceptedLaunch == (refusal != 2))
  }
  let fatal=Model();fatal.sessionHealthNotice = .reportedFailure(.repeatedFault)
  let fatalView=View(model:fatal),token=fatal.sessionHealthAttempt
  await fatalView.revealConfirmedSessionFailure(attempt:token)
  precondition(fatalView.dismissals==1 && fatal.hasAcceptedLaunch && !fatal.requiresRestart && !fatal.stopRequested)
  precondition(fatal.sessionHealthPresentationDismissal==nil)
  await fatalView.revealConfirmedSessionFailure(attempt:token)
  precondition(fatalView.dismissals==1,"persistent error must not dismiss Return to VR again")
  fatal.sessionHealthAttempt=UUID() // New launch must reject the old queued UI action.
  await fatalView.revealConfirmedSessionFailure(attempt:token)
  precondition(fatalView.dismissals==1)
  let cancelled=Model();cancelled.sessionHealthNotice = .reportedFailure(.rendering)
  let cancelledView=View(model:cancelled)
  let task=Task { @MainActor in
   while !Task.isCancelled { await Task.yield() }
   await cancelledView.revealConfirmedSessionFailure(attempt:cancelled.sessionHealthAttempt)
  }
  task.cancel();await task.value
  precondition(cancelledView.dismissals==0)
  let pending=Model();pending.sessionHealthNotice = .reportedFailure(.guestExit(3))
  let pendingView=View(model:pending);pendingView.hold=true
  let pendingToken=pending.sessionHealthAttempt
  let inFlight=Task { await pendingView.revealConfirmedSessionFailure(attempt:pendingToken) }
  while pendingView.gate==nil { await Task.yield() }
  pending.sessionHealthAttempt=UUID();pending.sessionHealthNotice=nil
  pendingView.gate?.resume();await inFlight.value
  precondition(pending.hasAcceptedLaunch && pending.sessionHealthNotice==nil && pending.sessionHealthDismissedAttempt==pendingToken)
  print("PASS exact ContentView fatal handler and model guard: warnings preserve VR, stale/cancelled/closed/stopping/returning/desktop calls refused, one presentation dismissal, native session retained and no postawait replacement mutation")
  print("PASS actual model post-await accepted/token/cancellation/stop guards, visible warnings/progress recovery, no autoend/restart and closed-view rendering-error exclusion")
 }
}
'''
view_shell=r"""
@MainActor final class View {
 let model:Model
 var dismissals=0,hold=false
 var gate:CheckedContinuation<Void,Never>?
 init(model:Model){self.model=model}
 func dismissImmersiveSpace() async {
  dismissals+=1
  if hold {await withCheckedContinuation {gate=$0}}
 }
"""
model_probe=scratch/"model.swift"
model_probe.write_text(source.replace("import WindowsVRCore\n","").split("/// Reads only newly written",1)[0]+"\n"+localization+"\n"+shell+presentation+"\n"+dismissal_request+"\n"+dismissal+"\n"+refresh+"\n}\n"+view_shell+reveal+model_main)
model_cmd=["xcrun","swiftc","-swift-version","6","-parse-as-library","-module-cache-path",str(tmp/"cache"),str(model_probe),"-o",str(scratch/"model")]
compiled=subprocess.run(model_cmd,env=env,capture_output=True,text=True,timeout=120)
(a.build/"model-compile.log").write_text(compiled.stdout+compiled.stderr);compiled.check_returncode()
model_run=subprocess.run([str(scratch/"model")],env=env,capture_output=True,text=True,timeout=25)
(a.build/"model-execution.log").write_text(model_run.stdout+model_run.stderr);model_run.check_returncode()
view_path=ROOT/"visionos-windows-vr/Sources/ContentView.swift"
view=view_path.read_text()
assert '.onChange(of: model.sessionHealthPresentationDismissal)' in view
assert 'Task { await revealConfirmedSessionFailure(attempt: attempt) }' in view
assert '.accessibilityIdentifier("session-health-notice")' in view
assert '.accessibilityIdentifier("previous-session-notice")' in view
assert 'model.hasAcceptedLaunch, let notice = model.sessionHealthNotice' in view
assert 'Button(role: .destructive) { Task { await model.stop() } }' in view

report={"passed":True,"scope":__doc__,"source":str(source_path),"sourceSha256":hashlib.sha256(source.encode()).hexdigest(),
        "localizationSourceSha256":hashlib.sha256(localization.encode()).hexdigest(),"journalSourceSha256":hashlib.sha256(journal.encode()).hexdigest(),"scratch":str(scratch),
        "testScriptSha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"command":cmd,"stdout":run.stdout,"modelCommand":model_cmd,"modelStdout":model_run.stdout,"modelSourceSha256":hashlib.sha256(model.encode()).hexdigest(),"viewSourceSha256":hashlib.sha256(view.encode()).hexdigest()}
if a.captured_runtime:report["capture"]={"path":str(a.captured_runtime.resolve()),"sha256":hashlib.sha256(a.captured_runtime.read_bytes()).hexdigest(),"expectedNativePID":a.captured_pid,"expectedExecutable":a.captured_executable,"expectedFailure":a.captured_failure}
(a.build/"result.json").write_text(json.dumps(report,indent=2)+"\n")
print(run.stdout+model_run.stdout,end="")
