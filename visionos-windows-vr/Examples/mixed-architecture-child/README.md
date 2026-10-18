# Mixed architecture child startup fixture

Build with `windows-vr-tools/build_mixed_architecture_child.sh`, setting
`AVPPLAY_LLVM_MINGW_ROOT` to the pinned toolchain and
`AVPPLAY_MIXED_CHILD_OUTPUT` to an external output directory. Compilation does
not run Windows code, launch the app, install a bundle, or alter a runtime.

The builder creates two importable app-owned game folders:

- `mixed`: x64 `parent64.exe` starts i386 `child32.exe` through `CreateProcessW`,
  waits at most 30 seconds, and checks its fresh `mixed-child-result.json` marker
  and zero exit status. The parent removes both stale result and adjacent
  `.before-seh.json` markers before launch and requires complete fresh contents.
- `direct`: the identical i386 child runs directly and writes
  `direct-child-result.json` in its working folder. Remove any prior direct
  result and `direct-child-result.json.before-seh.json` before a control run;
  verify both new markers' timestamps and complete contents.

The child calls imported ntdll `RtlRunOnceExecuteOnce` twice and requires one
callback, successful statuses, a retained context, 32-bit pointers, and a marker
write before exit 0. It also registers a vectored exception handler, flushes a
bounded `beforeRaiseException` marker adjacent to the result, and raises one
private continuable exception (`0xe0425648`, one sentinel argument). PASS requires
exactly one handler call, i386 architecture plus control/integer ContextFlags,
nonzero EIP, ESP within the current i386 TEB's stack bounds, the expected
continuable exception/argument, and execution after `RaiseException` returns.
The final JSON preserves the existing pointer/callback/status/exit fields and
adds `vehCalls`, `contextFlags`, `contextI386`, `contextStackValid`,
`exceptionValid`, and `continuedAfterRaise`.

The mixed fixture exercises WOW64 startup and exception context delivery inside
a running x64 process, which top-level i386 desktop/VR fixtures do not cover.
Reaching main is already beyond the native `wow64!Wow64LdrpInitialize` import;
reaching the before-stage marker additionally proves run-once and handler
registration completed. That marker without a final result locates the failure
at or after the exception boundary; it does not itself prove a successful
handler, context restoration, or child exit. A Mac Wine control cannot prove the
visionOS/FEX/ARM64EC path.

A build receipt records compiler/source/PE hashes and `executed: false`.
A compiled fixture is not evidence that either execution path passes on device.
No Steam account, game content, or downloaded dependencies are involved.

The diagnostic app includes this folder only in the source-AIR/x86 spec. With
launch diagnostics enabled, pass `--mixed-architecture-child-test` for the x64
parent path; add `--direct-child-control` for the direct i386 control. The control
flag alone has no effect. Both use the normal desktop launch path.

The selector copies owned executables into app Documents under
`WindowsVR/Apps/MixedArchitectureChild` or `WindowsVR/Apps/DirectChildControl`.
The respective fresh marker is `mixed-child-result.json` or
`direct-child-result.json` in that folder. Selection removes only that previous
result and before-stage markers and preserves other files. Parent success prints
its PASS line to the runtime log; `CHILD_EXIT` records the real child status and
whether its before-stage file exists. Launcher/runtime capture remains `Documents/launcher-log.txt`,
`Documents/madeira-log.txt` (with rotated previous logs), and per-attempt
`Documents/SessionDiagnostics/<attempt>/journal.json`. A child that fails before
main creates neither fresh marker. A run that passed handler registration but
faulted during exception dispatch/restoration can leave only the before-stage
marker. Inspect both files, the runtime fault, and the real child/parent exit
statuses; an old marker or a live process is never a PASS.
