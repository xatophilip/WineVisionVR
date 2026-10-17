# Modern 32-bit Windows support — development status

This work is isolated on `codex/modern-x86-support`. It is not part of the
published working branch or the currently installed main app. No 32-bit game
is confirmed playable by these changes yet.

## Problems found in captured diagnostics

- The installed modern package has no i386 Wine farm; Tomb Raider I's installed
  `dosbox.exe` is an actual 32-bit PE. Its mismatched filename case was repaired
  separately, but that alone cannot supply the missing architecture.
- The older experimental x86 VR scene created a D3D11 device and submitted four
  frames, then reported AGX bitcode errors and grey in one eye. Its AIR container
  metadata repair still needs a new device rendering test.
- Audioshield's captured executable is i386. Direct x86 execution and Steam's
  x64-parent-to-x86-child launch must be tested separately.
- A captured Fantastic Contraption attempt exhausted the shared 640 MiB
  executable-memory arena after cache-launch helper processes reserved large
  tail buffers. That capture used the cache-launch path; it does not prove the
  latest cache-disabled default fails the same way.
- Earlier cache-launch children could enter GDI with a null shared handle table.
  Native one-time initialization does not publish into every child's PEB.
- Google Earth VR's OpenGL requirement is a separate unsupported graphics path;
  adding x86 transport does not implement it.

## Implementation

Modern DXMT patch `0025` adds pointer-aware WOW64 wrappers to the existing
148-slot dispatch ABI, preserving the native 64-bit table. Public pointer boxes
are explicitly aligned to eight bytes; cross-compiler layout tests compare
161 graphics records and 32 shader/reflection records. Malformed misaligned or
cyclic command chains fail before native casts or in-place pointer conversion. The adapter checks
actual native ABI/count exports and four same-source i386 graphics DLL hashes.
It rejects incomplete packages and mixed legacy/modern graphics. Modern i386
Wine/FEX components are built before matching modern DXMT guest DLLs; receipts
are created only after the complete architecture/import/hash closure validates.

Wine patch `0012` serializes fresh executable-memory head/tail reservations,
rechecks the available budget at commit time, and preserves space for later DLL
loads. Failed reservations do not advance either cursor. It retains the existing
640 MiB arena and live-code retirement guards; it does not promise that every
game will fit. Captured exhaustion arithmetic and concurrent reservation tests
pass with sanitizers. Actual game startup still requires a headset retest.

Wine patch `0011` publishes GDI state into each child's PEB after native client
initialization, including 64-bit children. For x86 launches the adapter selects
section-backed shared GDI state before the Wine parent starts.

Use `AVPPLAY_ENABLE_X86=1` with `AVPPLAY_ENABLE_D3D12=1` for the new source build.
The assembler selects `project.source-air-x86.yml`, combining source AIR with
explicit experimental x86 resources. The older legacy x86 route remains a
separate diagnostic option; its graphics DLLs must not be copied into this one.

## Validation so far

- Production modern WOW64 wrappers compile against the visionOS SDK.
- ASan/UBSan contracts pass for shifted guest pointers, nested command payloads,
  cache/readback and shader input/output translation; dispatch has 148 entries.
- Compiled production GDI guard, publisher and client initialization pass tests
  for parent/child PEBs, repeated calls, delayed initialization and 32-bit section
  mapping. Host dependencies are mocked; this is not guest execution.
- Packaging, receipt mutation and native capability-gate tests pass.
- The bootstrap fixture isolates the selected architecture from ambient build
  environment variables; x86 opt-in still rejects missing i386 bootstrap files.
- A separate signed `com.philipanderson.WineVisionVR.x86test` diagnostic app has
  been built from the preserved legacy runtime and current bridge sources. It is
  explicitly a composite diagnostic, not a proof of a fresh modern source build.

The integrated host run on 17 October 2026 completed 30 check groups with no
failures and five explicit optional skips (two device-SDK builds omitted because
the separate app build covered those sources, legacy DXMT transport, a patched
OpenComposite logger source, and simulator execution). Its packaging group ran
64 tests with one case-sensitive-filesystem fixture skipped.

Fresh modern native/guest compilation and signed app packaging have now completed.
Real headset CPU, desktop and D3D11 rendering tests remain required. Keep the
working main app and its fallback build until the separate test app passes.

## Repeat the host checks

After preparing the baseline and modern profile, use the actual prepared trees:

```sh
python3 windows-vr-tools/test_local.py --build /external/tests \
  --madeira-source "$AVPPLAY_SOURCE_CACHE_ROOT/madeira" \
  --runtime-source "$AVPPLAY_D3D12_PROFILE_SOURCE" \
  --dxmt-modern-wow64-source "$AVPPLAY_D3D12_PROFILE_SOURCE/dxmt"
```

Set `AVPPLAY_LLVM_MINGW_ROOT` for the real i386 compiler/layout and desktop
fixture checks. Optional missing inputs are reported as explicit skips. The
runner never treats host tests as proof of Windows execution or headset FPS.

The authored desktop fixture supports `--desktop-smoke-test --x86-guest` in a
diagnostics-enabled app. It records `pointerBits=32` and an explicit result in
`demo-selftest-result.txt`; it uses its own note file and leaves the window open.
A PASS verifies injected Windows input and persistence, not physical hand-tap
or controller behavior. Test actual VR rendering separately with
`--vr-smoke-test --x86-guest`.

## First complete component build

The first fresh build compiled the native runtime, both CPU translators, all
718 selected i386 Wine modules, and all four modern i386 graphics DLLs. The
strict final import check then rejected two missing providers: optional Wine
D3D10 consumers imported `d3d10core.dll`, and diagnostic/media modules imported
`d3d9.dll`. The corrected build explicitly compiles those two providers from
the same Wine source, preserves the four modern DXMT DLLs, and records their
build/packaged hashes. This supplies imports; D3D9/D3D10 rendering remains
unverified and is not advertised.

A diagnostic build of the providers closed the real i386 dependency graph across
719 binaries, with only the existing explicit unsupported Win16 forwarders.
The updated offline suite passes 68 tests with one optional skip. The clean second
modern profile build completed native compilation, both translators, the i386
Wine closure, four matching modern graphics DLLs and strict staging. The first
attempt remains a failed package build; its receipts were not edited to pass.

## Signed modern package and headset startup

The complete modern Release app was signed and installed separately as
`com.philipanderson.WineVisionVR.x86test` on 17 October 2026. Executable UUID:
`230FDB6F-D27A-361C-BB08-ADFA51EB4682`. It replaces the earlier composite test
app, not the working main app. Bundle verification counted 100 ARM64EC, 137
ARM64 and 721 i386 binaries and checked the real WOW64 ABI exports, dependency
closure, development signing and JIT resources. The build reused the pinned
compiler cache and the verified unchanged baseline, while rebuilding the modern
profile and its native outputs from source.

The authored VR fixture builder now honors `AVPPLAY_SOURCE_CACHE_ROOT` for
OpenVR headers and records their hash. Both x64 and x86 fixtures compiled using
the external source cache; no untracked local header copy is required.

Xcode activation timed out, but opening the separate app manually succeeded.
Its startup log then reached debugger preparation and timed out after 90 seconds
without debugger attachment. StikDebug received the exact test bundle ID, live
PID and embedded script, but its tunnel remained disconnected while trying
addresses discovered before a Wi-Fi change. No runtime log or fresh Windows
self-test PASS was produced. This is a JIT prerequisite failure, not evidence
that a 32-bit Windows process executed or crashed. The transferred authored
32-bit desktop self-test is ready for a retry once the tunnel reconnects.

Local build, signing, install and diagnostic records are retained under the
external `x86-modern-oct17-r2` build directory. Pairing credentials and device
logs are deliberately excluded from Git.
