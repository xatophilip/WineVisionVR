#!/usr/bin/env python3
"""Run actual flat-controller mapping/sampler and surface key-source logic.

GC snapshots, UIKit events and the native key sink are boundary mocks. No
controller hardware, Windows executable, immersive space or device is used.
"""
import argparse,ast,hashlib,json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True,type=Path);a=p.parse_args();a.build.mkdir(parents=True,exist_ok=True)
view=(ROOT/'visionos-windows-vr/Sources/Desktop/WindowsDesktopView.swift').read_text()
gamepad=(ROOT/'visionos-windows-vr/Sources/Desktop/WindowsDesktopGamepad.swift').read_text()
keyboard=(ROOT/'windows-vr/Sources/WindowsVRCore/WindowsDesktopKeyboard.swift').read_text()
launcher=(ROOT/'visionos-windows-vr/Sources/LauncherModel.swift').read_text()
def body(text,signature):
 start=text.index(signature);brace=text.index('{',start);end=brace+1;depth=1
 while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
# Reuse UIKit/native boundary mocks from the existing desktop input contract.
tree=ast.parse((ROOT/'visionos-windows-vr/Tests/Contracts/test_desktop_input.py').read_text())
prefix=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='prefix' for t in n.targets))
fields=view[view.index('    private weak var controls:'):view.index('    init(controls:')]
for field in ('    private var attached = false\n','    var didAttach: (() -> Void)?\n','    var didDetach: (() -> Void)?\n'):fields=fields.replace(field,'')
methods=view[view.index('    func toggleKeyboard() {'):view.index('    var keyboardType:')].replace('@objc private func hover','private func hover')
mapping=body(gamepad,'enum WindowsDesktopGamepadMapping {')
sampler=body(gamepad,'private static func currentKeys()').replace('private static func','static func',1)
scope=body(launcher,'var supportsTombRaiderDesktopControls: Bool')
assert 'input.capture()' in sampler and 'GCSpatialAccessory.spatialAccessories' in sampler and 'ObjectIdentifier($0)' in sampler
assert 'import ARKit' not in gamepad and 'AccessoryTrackingProvider' not in gamepad
assert '.task(id: gamepadActive)' in view and 'controls.releaseInput()' in view
stubs=r'''
let GCInputButtonMenu="Menu",GCInputButtonOptions="Options",GCInputButtonShare="Share"
let GCProductCategorySpatialController="Spatial"
protocol GCDevice:AnyObject {}
struct Pressed { var isPressed:Bool }
struct Button { var pressedInput:Pressed }
struct Axis { var value:Float }
struct AxisInput { var absoluteInput:Axis? }
struct Dpad { var xAxis:Axis;var yAxis:Axis }
struct Snapshot { var buttons:[String:Button]=[:];var axes:[String:AxisInput]=[:];var dpads:[String:Dpad]=[:] }
protocol GCDevicePhysicalInput { func capture()->Snapshot }
final class Input:GCDevicePhysicalInput {
 var snapshot=Snapshot();var captures=0
 func capture()->Snapshot { captures+=1;return snapshot }
}
class GCController:GCDevice {
 static var connected:[GCController]=[]
 class func controllers()->[GCController] { connected }
 var productCategory=GCProductCategorySpatialController
 var input:(any GCDevicePhysicalInput)?
 init(_ input:Input) { self.input=input }
}
final class GCSpatialAccessory:GCController { static var spatialAccessories:[GCSpatialAccessory]=[] }
enum WindowsPresentationMode { case desktop,immersiveVR }
struct Manifest { var id:String;var environment:[String:String] }
enum SteamDOSBoxCompatibility { static let appID=224960 }
'''
tests=r'''
func check(_ condition:@autoclosure ()->Bool,_ message:String) { if !condition(){fatalError(message)} }
let c=WindowsDesktopControls(),s=WindowsDesktopSurface(c)
s.inputEnabled=true
let leftInput=Input(),rightInput=Input()
let left=GCSpatialAccessory(leftInput),right=GCSpatialAccessory(rightInput)
GCSpatialAccessory.spatialAccessories=[left,right];GCController.connected=[left,right]
leftInput.snapshot.buttons["Trigger"]=Button(pressedInput:Pressed(isPressed:true))
rightInput.snapshot.buttons["Right Trigger"]=Button(pressedInput:Pressed(isPressed:true))
s.updateGamepadKeys(Sampler.currentKeys());s.updateGamepadKeys(Sampler.currentKeys())
check(events == [.key(0xA2,1)],"Held latest-state snapshots must not repeat keydown")
check(leftInput.captures==2 && rightInput.captures==2,"Spatial accessories appearing as GCControllers must be sampled once")
GCSpatialAccessory.spatialAccessories=[right];GCController.connected=[right]
s.updateGamepadKeys(Sampler.currentKeys())
check(events == [.key(0xA2,1)],"Disconnecting one controller released another's held trigger")
// Physical keyboard shares the exact left-Control VK with the gamepad source.
let control=UIPress(0xE0)
s.pressesBegan([control],with:nil)
check(events == [.key(0xA2,1)],"Overlapping physical control emitted duplicate keydown")
GCSpatialAccessory.spatialAccessories=[];GCController.connected=[]
s.updateGamepadKeys(Sampler.currentKeys())
check(events == [.key(0xA2,1)],"Controller disconnect released physical control")
s.pressesEnded([control],with:nil)
check(events == [.key(0xA2,1),.key(0xA2,0)],"Final source did not release control")
events=[];s.pressesBegan([control],with:nil);s.updateGamepadKeys([0xA2]);s.pressesEnded([control],with:nil)
check(events == [.key(0xA2,1)],"Physical release interrupted held gamepad control")
s.updateGamepadKeys([]);check(events == [.key(0xA2,1),.key(0xA2,0)],"Gamepad final release missing")
print("PASS: latest-state hold, device dedup, overlapping controllers and physical/gamepad source ownership")
let all=WindowsDesktopGamepadMapping.keys(pressed:{ ["Button A","Button B","Left Shoulder","Options","Left Thumbstick Button"].contains($0) },axis:{_ in nil},stick:{_ in nil})
check(all == [0xA4,0x20,0xA0,0x1B,0x0D],"Button aliases or Windows keys changed")
let diagonal=WindowsDesktopGamepadMapping.keys(pressed:{_ in false},axis:{_ in nil},stick:{ $0=="Right Thumbstick" ? (0.5,-0.9):nil })
check(diagonal == [0x27,0x28],"Either stick must provide arrows including diagonals")
let axes=WindowsDesktopGamepadMapping.keys(pressed:{_ in false},axis:{ ["Left Thumbstick X Axis":Float(-0.8),"Left Thumbstick Y Axis":Float(0.7)][$0] },stick:{_ in nil})
check(axes == [0x25,0x26],"Separate axis aliases must work")
check(WindowsDesktopGamepadMapping.keys(pressed:{_ in false},axis:{_ in 0.39},stick:{_ in nil}).isEmpty,"Stick deadzone leaked movement")
check(WindowsDesktopGamepadMapping.keys(pressed:{_ in false},axis:{_ in .nan},stick:{_ in nil}).isEmpty,"Non-finite axes leaked movement")
let generic=GCController(Input());generic.productCategory="ExtendedGamepad";GCController.connected=[generic]
check(Sampler.currentKeys().isEmpty,"Unrelated non-spatial controllers were captured")
print("PASS: Sense button aliases, either-stick directions, axis fallback, deadzone and non-spatial exclusion")
events=[];s.updateGamepadKeys([0x0D,0x20]);s.pulseKey(0x0D)
check(events == [.key(0x0D,1),.key(0x20,1)],"Toolbar pulse released gamepad-owned key")
s.releaseInput();s.releaseInput()
check(events == [.key(0x0D,1),.key(0x20,1),.key(0x0D,0),.key(0x20,0)],"Pause/removal release must be complete and idempotent")
events=[];s.updateGamepadKeys([0x26]);s.inputEnabled=false;s.updateGamepadKeys([0x26])
check(events == [.key(0x26,1),.key(0x26,0)],"Disabled surface accepted controller input")
for flags in [[true,true,true,false,false,false,true],[false,true,true,false,false,false,true],[true,false,true,false,false,false,true],[true,true,false,false,false,false,true],[true,true,true,true,false,false,true],[true,true,true,false,true,false,true],[true,true,true,false,false,true,true],[true,true,true,false,false,false,false]] {
 let actual=WindowsDesktopGamepadMapping.allowed(supported:flags[0],enabled:flags[1],accepted:flags[2],stopping:flags[3],stopRequested:flags[4],requiresRestart:flags[5],sceneActive:flags[6])
 check(actual == (flags == [true,true,true,false,false,false,true]),"Session/toggle/scene gating leaked controller input")
}
let scope=Scope();check(scope.supportsTombRaiderDesktopControls,"Validated DOSBox desktop not enabled")
scope.manifest?.environment=[:];check(!scope.supportsTombRaiderDesktopControls,"Unvalidated native game route enabled")
scope.manifest?.environment=["SDL_VIDEODRIVER":"windib"];scope.selectedSteamAppID=428370
check(!scope.supportsTombRaiderDesktopControls,"Another Steam game enabled")
scope.selectedSteamAppID=224960;scope.presentationModeDraft = .immersiveVR
check(!scope.supportsTombRaiderDesktopControls,"Immersive game route enabled")
scope.presentationModeDraft = .desktop;scope.manifest?.id="owned.other"
check(!scope.supportsTombRaiderDesktopControls,"Other manifest enabled")
print("PASS: scoped DOSBox controls, all lifecycle gates, disabled input, pause/removal cleanup and toolbar overlap")
'''
tests += r'''
// Run the actual async poller: cancelling a live task releases its keys, and
// an inactive replacement invalidates the prior generation without late ups.
events=[];s.inputEnabled=true
GCSpatialAccessory.spatialAccessories=[left];GCController.connected=[left]
let adapter=WindowsDesktopGamepad()
var samples=0
let poll=Task { @MainActor in
 await adapter.run(enabled:true) { s.updateGamepadKeys($0);samples+=1 }
}
for _ in 0..<100 { if samples>0 {break};try? await Task.sleep(for:.milliseconds(5)) }
check(samples>0 && events == [.key(0xA2,1)],"Async sampler failed to apply latest held state")
poll.cancel();await poll.value
check(events == [.key(0xA2,1),.key(0xA2,0)],"Task cancellation failed to release controller keys")
events=[];samples=0
let old=Task { @MainActor in
 await adapter.run(enabled:true) { s.updateGamepadKeys($0);samples+=1 }
}
for _ in 0..<100 { if samples>0 {break};try? await Task.sleep(for:.milliseconds(5)) }
await adapter.run(enabled:false) { s.updateGamepadKeys($0) }
await old.value
check(events == [.key(0xA2,1),.key(0xA2,0)],"Inactive replacement or stale generation duplicated key release")
print("PASS: actual async sampler cancellation and inactive generation replacement release held keys exactly once")
'''
check_function='func check(_ condition:@autoclosure ()->Bool,_ message:String) { if !condition(){fatalError(message)} }'
tests=tests.replace(check_function,'')
unit=a.build/'main.swift' 
unit.write_text(prefix+stubs+gamepad.replace('import GameController','')+'\nenum Sampler {\n'+sampler+'\n}\n'+keyboard+'\nfinal class WindowsDesktopSurface:UIView {\n'+fields+'\ninit(_ controls:WindowsDesktopControls){self.controls=controls;super.init()}\n'+methods+'\n}\nfinal class Scope {\nvar manifest:Manifest?=Manifest(id:"steam.shared",environment:["SDL_VIDEODRIVER":"windib"])\nvar selectedSteamAppID:Int?=224960\nvar presentationModeDraft=WindowsPresentationMode.desktop\n'+scope+'\n}\n'+check_function+'\n@main struct Driver { @MainActor static func main() async {\n'+tests+'\n} }\n')
command=['xcrun','swiftc','-parse-as-library',str(unit),'-o',str(a.build/'probe')]
subprocess.run(command,check=True);result=subprocess.run([str(a.build/'probe')],check=True,capture_output=True,text=True)
print(result.stdout,end='')
(a.build/'result.json').write_text(json.dumps({'passed':True,'scope':'Actual Swift mapper/sampler, session scope and desktop surface key methods; GC/UIKit/native sink boundary mocks. No hardware, Wine or device execution.','gamepadSha256':hashlib.sha256(gamepad.encode()).hexdigest(),'surfaceSha256':hashlib.sha256(view.encode()).hexdigest(),'command':command,'result':result.stdout},indent=2)+'\n')
