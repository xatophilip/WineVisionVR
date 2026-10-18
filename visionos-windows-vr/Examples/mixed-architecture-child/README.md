# Mixed architecture child startup fixture

Build with `windows-vr-tools/build_mixed_architecture_child.sh`, setting
`AVPPLAY_LLVM_MINGW_ROOT` to the pinned toolchain and
`AVPPLAY_MIXED_CHILD_OUTPUT` to an external output directory. Compilation does
not run Windows code, launch the app, install a bundle, or alter a runtime.

The builder creates two importable app-owned game folders:

- `mixed`: x64 `parent64.exe` starts i386 `child32.exe` through `CreateProcessW`,
  waits at most 30 seconds, and checks its fresh `mixed-child-result.json` marker
  and zero exit status. The parent removes a stale marker before launch.
- `direct`: the identical i386 child runs directly and writes
  `direct-child-result.json` in its working folder. Remove any prior direct
  marker before a control run and verify the new marker's timestamp.

The child calls imported ntdll `RtlRunOnceExecuteOnce` twice and requires one
callback, successful statuses, a retained context, 32-bit pointers, and a marker
write before exit 0. The mixed fixture exercises WOW64 startup inside a running
x64 process, which top-level i386 desktop/VR fixtures do not cover. Reaching its
main is already beyond the failing native `wow64!Wow64LdrpInitialize` import.

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
marker and preserves other files. Parent success prints its PASS line to the
runtime log. Launcher/runtime capture remains `Documents/launcher-log.txt`,
`Documents/madeira-log.txt` (with rotated previous logs), and per-attempt
`Documents/SessionDiagnostics/<attempt>/journal.json`. A child that fails before
main creates no marker; inspect the runtime fault and parent exit status.
