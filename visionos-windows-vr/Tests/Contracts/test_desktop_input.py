#!/usr/bin/env python3
"""Execute production desktop input method bodies against a recording host sink.

UIKit views/events, point conversion and native input delivery are boundary
mocks. The production keyboard mapper and desktop input method bodies are
compiled unchanged; only the unavailable Objective-C selector annotation is
removed. This does not run a GUI, Wine, Windows code or a headset.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True, type=pathlib.Path)
args = parser.parse_args()
repo = ROOT
out = args.build.expanduser().resolve()
out.mkdir(parents=True, exist_ok=True)
source=repo/'visionos-windows-vr/Sources/Desktop/WindowsDesktopView.swift'
keyboard=repo/'windows-vr/Sources/WindowsVRCore/WindowsDesktopKeyboard.swift'
s=source.read_text()
methods=s[s.index('    func toggleKeyboard() {'):s.index('    var keyboardType:')]
methods=methods.replace('@objc private func hover','private func hover')
fields=s[s.index('    private weak var controls:'):s.index('    init(controls:')]
fields=fields.replace('    private var attached = false\n','').replace('    var didAttach: (() -> Void)?\n','').replace('    var didDetach: (() -> Void)?\n','')
prefix=r'''
import Foundation
enum NativeEvent: Equatable { case pointer(Int32,Int32,UInt32,UInt32), key(Int32,Int32) }
var events: [NativeEvent] = []
var mapping = true
func winios_pointer(_ x:Int32,_ y:Int32,_ f:UInt32,_ d:UInt32) { events.append(.pointer(x,y,f,d)) }
func winios_post_key(_ k:Int32,_ d:Int32) { events.append(.key(k,d)) }
func winios_desktop_point_from_window(_ x:Double,_ y:Double,_ ox:inout Int32,_ oy:inout Int32) -> Int32 {
 if !mapping { return 0 }; ox=Int32(x*2); oy=Int32(y*2); return 1
}
func L(_ en:String,_ de:String)->String { en }
class WindowsDesktopControls { var inputMessage:String? }
struct ButtonMask:OptionSet { let rawValue:Int; static let secondary=ButtonMask(rawValue:2) }
class UIEvent { var buttonMask:ButtonMask; init(_ b:ButtonMask=[]) { buttonMask=b } }
class UIPressesEvent {}
class UIView {
 var window:UIView?; var isFirstResponder=false
 var otherBegan=0; var otherEnded=0
 func becomeFirstResponder() { isFirstResponder=true }
 func resignFirstResponder() { isFirstResponder=false }
 func convert(_ point:CGPoint,to:UIView?) -> CGPoint { point }
 func touchesBegan(_ t:Set<UITouch>,with e:UIEvent?) {}
 func touchesMoved(_ t:Set<UITouch>,with e:UIEvent?) {}
 func touchesEnded(_ t:Set<UITouch>,with e:UIEvent?) {}
 func touchesCancelled(_ t:Set<UITouch>,with e:UIEvent?) {}
 func pressesBegan(_ p:Set<UIPress>,with e:UIPressesEvent?) { otherBegan += p.count }
 func pressesEnded(_ p:Set<UIPress>,with e:UIPressesEvent?) { otherEnded += p.count }
 func pressesCancelled(_ p:Set<UIPress>,with e:UIPressesEvent?) {}
}
class UITouch:Hashable {
 var point:CGPoint; init(_ x:Double,_ y:Double) { point=CGPoint(x:x,y:y) }
 func location(in:UIView)->CGPoint { point }
 static func ==(a:UITouch,b:UITouch)->Bool { a === b }
 func hash(into h:inout Hasher) { h.combine(ObjectIdentifier(self)) }
}
class UIHoverGestureRecognizer { func location(in:UIView)->CGPoint { CGPoint(x:0,y:0) } }
struct Code { var rawValue:Int }
struct Key { var keyCode:Code }
class UIPress:Hashable {
 var key:Key?; init(_ usage:Int?) { key=usage.map { Key(keyCode:Code(rawValue:$0)) } }
 static func ==(a:UIPress,b:UIPress)->Bool { a === b }
 func hash(into h:inout Hasher) { h.combine(ObjectIdentifier(self)) }
}
'''
main=r'''
func check(_ value: @autoclosure () -> Bool,_ why:String) { if !value() { fatalError(why) } }
let c=WindowsDesktopControls(), s=WindowsDesktopSurface(c), window=UIView()
s.window=window
let t=UITouch(10,20), stray=UITouch(40,50)
s.touchesBegan([t],with:nil); s.pulseKey(0x41); s.rightClick();s.scroll(1);s.insertText("A")
check(events.isEmpty,"disabled input escaped")
s.inputEnabled=true;mapping=false;s.touchesBegan([t],with:nil)
check(events.isEmpty,"unmapped touch escaped")
mapping=true;s.touchesBegan([t],with:nil)
check(events == [.pointer(20,40,0x8003,0)],"left down mapping/flags")
s.touchesBegan([stray],with:nil);s.rightClick();s.touchesMoved([stray],with:nil)
check(events.count==1,"second touch or right click disturbed active drag")
t.point=CGPoint(x:12,y:23);s.touchesMoved([t],with:nil)
s.touchesEnded([stray],with:nil);check(events.count==2,"unrelated touch ended drag")
s.touchesEnded([t],with:nil)
check(events == [.pointer(20,40,0x8003,0),.pointer(24,46,0x8001,0),.pointer(24,46,0x8004,0)],"left drag/release")
events=[]
s.touchesBegan([t],with:UIEvent(.secondary));s.touchesCancelled([t],with:nil)
check(events == [.pointer(24,46,0x8009,0),.pointer(24,46,0x8010,0)],"secondary/cancel release")
events=[];s.rightClick();s.scroll(-120)
check(events == [.pointer(24,46,0x8008,0),.pointer(24,46,0x8010,0),.pointer(24,46,0x800,UInt32(bitPattern:-120))],"toolbar click/wheel")
print("PASS: disabled/unmapped input, mapped click, drag identity, secondary/cancellation, toolbar click and signed scroll")
events=[];let a=UIPress(0x04),unknown=UIPress(nil)
s.pressesBegan([a,unknown],with:nil);s.pressesBegan([a],with:nil);s.insertText("A");s.pulseKey(0x41)
check(events == [.key(0x41,1)] && s.otherBegan==1,"hardware repeat/duplicate text or unhandled dispatch")
s.pressesEnded([a,unknown],with:nil);s.pressesEnded([a],with:nil)
check(events == [.key(0x41,1),.key(0x41,0)] && s.otherEnded==1,"hardware release")
events=[];s.insertText("Aa!\n")
check(events == [.key(0x10,1),.key(0x41,1),.key(0x41,0),.key(0x10,0),.key(0x41,1),.key(0x41,0),.key(0x10,1),.key(0x31,1),.key(0x31,0),.key(0x10,0),.key(0x0d,1),.key(0x0d,0)],"soft keyboard sequence")
events=[];s.insertText("a🙂");check(events.isEmpty && c.inputMessage != nil,"unsupported text partially emitted")
s.insertText("b");check(events == [.key(0x42,1),.key(0x42,0)] && c.inputMessage == nil,"keyboard did not recover")
events=[];s.deleteBackward();check(events == [.key(8,1),.key(8,0)],"delete did not pulse backspace")
print("PASS: hardware key repeat/release, UIKit forwarding, duplicate text suppression, US shifted text, unsupported text atomicity, backspace")
events=[];s.pressesBegan([a],with:nil);s.touchesBegan([t],with:nil);s.becomeFirstResponder();s.inputEnabled=false
check(events == [.key(0x41,1),.pointer(24,46,0x8003,0),.pointer(24,46,0x8004,0),.key(0x41,0)] && !s.isFirstResponder,"disable did not release held input")
s.releaseInput();check(events.count==4,"duplicate cleanup emitted releases")
s.inputEnabled=true;events=[];s.pressesBegan([a],with:nil);s.pressesCancelled([a],with:nil)
check(events == [.key(0x41,1),.key(0x41,0)],"cancelled key stuck")
print("PASS: disabling input releases pointer and held keys, resigns keyboard, cleanup is idempotent and key cancellation releases")
'''
unit=out/'main.swift'
unit.write_text(prefix+keyboard.read_text()+'\nfinal class WindowsDesktopSurface:UIView {\n'+fields+'\ninit(_ controls:WindowsDesktopControls) { self.controls=controls;super.init() }\n'+methods+'\n}\n'+main)
binary=out/'desktop-input-host'
command=['xcrun','swiftc',str(unit),'-o',str(binary)]
subprocess.run(command,check=True)
r=subprocess.run([str(binary)],check=True,capture_output=True,text=True,timeout=15)
print(r.stdout,end='')
(out/'result.json').write_text(json.dumps(dict(passed=True,scope='Production input method bodies compiled on macOS; UIKit/coordinate mapper/native sink mocked; no GUI or guest execution',sourceSHA256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,keyboard)},command=command,extractedProbeSHA256=hashlib.sha256(unit.read_bytes()).hexdigest(),result=r.stdout),indent=2)+'\n')
