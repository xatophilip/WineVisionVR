#!/usr/bin/env python3
"""Execute the production startup reader against bounded, real log files."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', required=True, type=Path)
parser.add_argument('--runtime-log', type=Path, help='Optional captured runtime log to verify')
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
source = (ROOT / 'visionos-windows-vr/Sources/LauncherModel.swift').read_text()
helper = 'private enum GuestStartupLog {' + source.split('private enum GuestStartupLog {', 1)[1].split('struct TransferredWindowsVRGame:', 1)[0]
watchdog = source.split('private func watchGuestStartup()', 1)[1].split('    func recordLifecycleEvent', 1)[0]
assert 'GuestStartupLog.hasLoadedNTDLL(at: log)' in watchdog
assert 'seekToEnd' not in watchdog
scratch = Path(tempfile.mkdtemp(prefix='run-', dir=args.build.resolve()))
main = scratch / 'main.swift'
main.write_text(r'''
import Foundation
PRODUCTION_HELPER
func check(_ value: @autoclosure () throws -> Bool, _ message: String) throws {
    if try !value() { fatalError(message) }
}
let directory = URL(fileURLWithPath: CommandLine.arguments[1])
let log = directory.appendingPathComponent("madeira-log.txt")
let x64 = "XLATE-HOOK installed p_ios_jit_translate_addr=0x105a31c00\n"
let reverse = "XLATE-HOOK-REV installed p_ios_jit_reverse_translate_addr=0x105a31c48 at 0x70fffb2988\n"
let x86 = "E [wow-image] i386 ntdll guest=0xfff40000 host=0x71fff40000 (LdrSystemDllInitBlock.ntdll_handle is a GUEST address)\n"
func write(_ text: String) throws { try Data(text.utf8).write(to: log) }
try check(!GuestStartupLog.hasLoadedNTDLL(at: log), "Missing log must not count as startup")
try write("")
try check(!GuestStartupLog.hasLoadedNTDLL(at: log), "Empty log must not count as startup")
for (name, marker) in [("64-bit forward hook", x64), ("32-bit reverse hook", reverse), ("32-bit ntdll guest image", x86)] {
    try write("runtime starting\n" + marker + "still loading game\n")
    try check(GuestStartupLog.hasLoadedNTDLL(at: log), "Missing startup evidence: " + name)
    print("PASS: " + name)
}
// A 32-bit session deliberately lacks the forward export. Generic module errors,
// bootstrap intent, and mapped pages do not prove ntdll reached initialization.
try write("""
[wow-window] session armed: a 32-bit process is expected
XLATE-HOOK enter: module=0x70ffef0000 exports=0x70fff966a8
XLATE-HOOK p_ios_jit_translate_addr export NOT FOUND
0024:err:module:load_dll ntdll.dll status=c0000135
[guest-image] 32-bit image page, EXEC has no host meaning here
""")
try check(!GuestStartupLog.hasLoadedNTDLL(at: log), "Intent, mapping, or generic error must not suppress watchdog")
print("PASS: pre-startup/error-only log remains negative")
// Real file larger than the budget, with successful startup only near its head.
// Verify EOF yields no evidence, then exercise the production reader itself.
var large = Data(x86.utf8)
large.append(Data(repeating: 120, count: GuestStartupLog.maximumBytes + 256))
try large.write(to: log)
let oldHandle = try FileHandle(forReadingFrom: log)
let size = try oldHandle.seekToEnd()
let oldRead = try oldHandle.read(upToCount: Int(min(size, 3_000_000)))
try oldHandle.close()
try check(oldRead == nil || oldRead!.isEmpty, "EOF read must not contain the startup marker")
try check(GuestStartupLog.hasLoadedNTDLL(at: log), "Reader must observe startup at head of a >3MB log")
// Evidence after the configured head bound must not be read accidentally.
var beyond = Data(repeating: 120, count: GuestStartupLog.maximumBytes)
beyond.append(Data(x64.utf8))
try beyond.write(to: log)
try check(!GuestStartupLog.hasLoadedNTDLL(at: log), "Reader scanned beyond its 3MB budget")
print("PASS: real EOF regression and bounded first-3MB read")
if CommandLine.arguments.count > 2 {
    try check(GuestStartupLog.hasLoadedNTDLL(at: URL(fileURLWithPath: CommandLine.arguments[2])),
              "Captured runtime log must contain successful startup evidence")
    print("PASS: captured runtime startup evidence")
}
'''.replace('PRODUCTION_HELPER', helper))
executable = scratch / 'guest-startup-watchdog'
subprocess.run(['xcrun', 'swiftc', str(main), '-o', str(executable)], check=True)
command = [str(executable), str(scratch)]
if args.runtime_log:
    command.append(str(args.runtime_log.resolve()))
subprocess.run(command, check=True, timeout=15)
