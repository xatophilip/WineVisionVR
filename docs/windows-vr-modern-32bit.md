# Modern 32-bit Windows support — development status

This work was developed on `codex/modern-x86-support` and fast-forwarded into
`codex/local-build-and-benchmarks` on 18 October 2026 for a combined main app.
The separate x86 test app remains useful for diagnostics. The authored 32-bit
desktop app now passes its headset self-test, including pointer input; physical
Count clicks taps also work. The 32-bit CPU fixture passes on the headset, and
the 32-bit VR scene renders in both eyes with head tracking. No 32-bit game is confirmed playable by these changes yet.

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

## Space Pirate Trainer diagnostic logging crash

The main app's saved 17 October capture shows Space Pirate Trainer beginning
at 17:24:44, submitting 3,334 VR frames, and then stopping new guest frames at
about 17:27:16. This capture used the cache-disabled path. The native log shows
`debug buffer overflow`, followed by an unhandled `0x80000005` exception and
process termination. There is no JIT-arena exhaustion or AGX pipeline failure
in this capture. Subsequent CPU samples show approximately one core busy in
the exception path; they do not establish repeated shader compilation.

The foveation diagnostic streamed two `uint8_t` values as characters. A zero
inserted an embedded NUL, truncating the C-string sent to Wine before its
newline. Repeated truncated records filled Wine's thread-local debug buffer,
which raises `STATUS_BUFFER_OVERFLOW`. DXMT patch `0026` formats those values
as unsigned numbers and escapes embedded NULs at the logger boundary. Host
ASan/UBSan tests execute the production formatting and logger code against a
Wine-style C-string sink, including 5,000 binary messages and file-output parity.

Patch `0026` is checked into the next modern profile inputs. It is **not in the
installed UUID `230FDB6F-D27A-361C-BB08-ADFA51EB4682` app**, and has not yet
been built or tested on the headset. The saved main-app gameplay capture is
older than that separate test app. After JIT access is restored, rebuild and
stage the modern profile and retest Space Pirate Trainer before calling this
fixed on device. Only the right controller was tracked in the saved capture;
that is a separate possible explanation for incomplete controls, not the
logging exception.


## Debugger tunnel timeout repair

The disconnected helper's nominal two-second TCP probe used a blocking connect,
which actually stalled for about 75 seconds per stale address. A separately
built and installed StikDebug repair bounds that probe and skips timed-out
endpoints before pairing. Its complete source delta, upstream pin, AGPL license
and reproduction instructions are in [the dependency note](dependencies/stikdebug-timeout/README.md).
The helper passes host socket tests and signing verification; Xcode activation
still timed out after installation, so headset tunnel recovery is unverified.


## First modern 32-bit headset execution

After reconnecting StikDebug, the separate app attached its debugger at 19:28:30
on 17 October and launched the authored i386 desktop executable through WOW64/FEX.
The PE probe reported `machine=0x14c`; the trace loaded the i386 main image, ntdll,
GDI and the Windows desktop test window. The freshly generated file under
`Documents/WindowsVR/Apps/DesktopDemoX86/demo-selftest-result.txt` reported:

```text
FAIL GDI desktop self-test pointerBits=32 SendInput=0 edit=1 button=1 save=1 load=1 UTF8roundtrip=1
```

Here `SendInput=0` means the injected click did not increment the counter, not
that the API rejected its events: the event trace explicitly accepted two events.
The EDIT handler, programmatic button handler and UTF-8 save/load round trip passed.
The user independently confirmed that tapping Count clicks did not increment it.
Button traces show mouse-up without the corresponding mouse-down, while parent
windows receive other pointer events. Pointer routing remains unresolved.

The launcher also falsely reported a startup stall despite that execution: its
watchdog used a forward-translation-only marker that missed the actual WOW64
ntdll startup markers. It also sought to EOF before reading and relied on a
platform-dependent nil-versus-empty-Data fallback to rewind.
That diagnostic bug is separate from the pointer failure. These results prove
32-bit desktop execution, not correct mouse controls, D3D11 rendering or gameplay.


Wine patch `0013` addresses the missing client mouse-down: the captured button
returned `MA_ACTIVATE`, then Wine discarded the press when its redundant
foreground request returned false even though the requested root was already
active. The fix matches Wine's existing non-client activation handling: discard
on activation failure only if that root is not active. Intentional
`MA_ACTIVATEANDEAT`/`MA_NOACTIVATEANDEAT` behavior remains intact. Sanitizer tests
execute the production activation branch and cover those cases. This changes
the baseline source fingerprint and requires a fresh build; the installed app
does not yet contain the fix, and physical clicking must be retested.


## Clean rebuild containing the input and logger repairs

Commit `3346430` was exported into a new source directory with no generated
Resources, native archives or Windows guest DLLs copied from the previous build.
The standard assembler rebuilt the baseline, modern profile, both translators,
Wine guest modules, modern graphics DLLs, AIR writer and final source-matched
resource closure. It reused the pinned compiler/toolchain cache, verified source
downloads and provenance-backed prefix template. Both full app assembly and
signed Release completed successfully.

The separate test app UUID `3818D44F-608E-3315-AF8C-A2034F6BC4FB` was verified
and installed on 17 October. It contains mouse patch `0013`, DXMT logger patch
`0026` and the startup-watchdog correction. Signature, debugging, diagnostics
and increased-memory entitlements passed verification. The normal app was not
replaced. Xcode's subsequent activation request timed out with no fresh startup
log; manual opening and a new mouse/self-test result remain required.

Build inputs, complete logs, signing verification and install receipt are
retained locally under `x86-modern-oct17-r3`. A newer codesign tool defaults to
abstract entitlement output; the external verification script explicitly uses
`--xml` before parsing it. This was a verification-script correction after a
successful signed build, not an app source or signing change.


## 18 October retest: pointer failure persists

The r3 runtime was confirmed running by its installed bundle path and matching
plugin UUID `7CD7B730-72DE-3A40-BB81-A80260C15474`. The new startup watchdog
correctly detected ntdll. The desktop result still failed only its pointer-click
check; edit, programmatic button, save, load and UTF-8 round trip passed again.
The user confirmed manual Count clicks still did nothing. Disassembly confirms
patch `0013` is present in the running native message path, so that patch alone
does not resolve this failure. No further behavioral fix is claimed.

An opt-in `--trace-input` mode in the authored fixture now records up to 256
non-move mouse stages around GetMessage, IsDialogMessage and DispatchMessage,
plus child/parent callback entries and results. It preserves the self-test pass
criteria and never logs note contents. The separately transferred i386 fixture
is titled **32-bit input trace**. It uses the installed r3 runtime; no native
runtime or app rebuild was needed. Temporary native `trace+win` output can be
enabled for this diagnostic via the host app environment
`MADEIRA_DEBUG_VERBOSE=1`; the bridge overrides direct WINEDEBUG values.


## Parent-cache failure isolated by the automatic probe

The app-only diagnostic UUID `D9C9C908-F2A8-341C-B54D-3FD6D9C8542F` retained
the exact r3 native plugin and automatically ran the traced i386 fixture. Its
root reported GA_PARENT equal to the desktop handle, GA_ROOT zero, and
GA_ROOTOWNER equal to the real root; both child controls showed the same zero
GA_ROOT despite valid immediate parents. The message-loop trace received only
mouse-up; IsDialogMessage did not consume it and DispatchMessage delivered it.
Thus the missing mouse-down is upstream of guest dialog filtering/dispatch.

Patch `0014` changes list_window_parents to use its existing authoritative
wineserver query when a local WND lookup fails, as it already does for windows
from other processes. It queries the original HWND and preserves errors for
invalid/stale handles, server failures and actual allocation failures. It does
not substitute the active window. Sanitizer tests execute the production
get_win_ptr, parent traversal and ancestor functions with mocked cache/server
boundaries: the original code reproduces the observed valid-parent/zero-root
relationship when the embedded desktop lacks a client WND, and the patched code
recovers the correct root. The precise missing local entry was inferred from
that reproduction, not directly logged on the headset.

This patch requires a new source profile and full package build with the current
receipt model. The r3 native runtime was not modified. Hardware confirmation is
still required; the preceding activation-only fix was insufficient.


## Local testing gate for the next device build

The 18 October r4 package was assembled from a clean export of `63543bd`,
including parent-cache patch `0014`. Source/resource provenance, complete guest
import closure, Release signing, diagnostics and debugging entitlements passed.
The runtime plugin UUID is `A616C513-818F-3767-8915-E594AAD36635`; the launcher
UUID remains `D9C9C908-F2A8-341C-B54D-3FD6D9C8542F` because its code did not
change. Use the plugin identity when distinguishing this build from r3.

The deployment gate required local execution of authored dummy executables, at
the user's request; those checks completed before the device installation. Six focused host check groups passed: production Wine parent
lookup and activation paths with sanitizers, startup-watchdog markers, compiled
x64/i386 desktop fixture selection, the native desktop launch contract, and
production Swift input method sequences. The last test is now part of
`windows-vr-tools/test_local.py`; UIKit, coordinate conversion and native input
delivery are explicit recording mocks. It covers clicks, drag ownership,
secondary click, cancellation, signed scroll, hardware key repetition/release,
soft-keyboard mapping and cleanup. It does not execute Windows or a GUI.

The pre-existing Mac Wine bootstrap runtime cannot serve as the full dummy-app
test environment: it has no i386 loader and was configured without FreeType.
An actual x64 desktop run created the window and incremented its injected-click
counter, then faulted in Wine text shaping before completion. The authored x64
VR fixture's CPU-only mode passed, but that does not exercise graphics or VR.
A separate font-enabled WOW64 host runtime was then built with isolated prefixes.
Both architectures passed with byte-identical copies of the four executables in
the signed r4 package:

| Local executable check | x64 | i386 |
| --- | --- | --- |
| Desktop: injected click, edit, programmatic button, save/load, UTF-8 roundtrip | PASS (64-bit) | PASS (32-bit) |
| CPU: arithmetic `0xf0d18bc8`, signaled event, exit status zero | PASS (64-bit) | PASS (32-bit) |

Each desktop result explicitly reported all six checks equal to one and the
expected pointer width. An independent agent rehashed all 99 staged runtime PE
modules in each prefix and checked the live memory maps: no old runtime fallback
was found. Local execution used new same-source modules and FreeType, with stock
registry/directory state from the verified same-pin prefix template. Template
runtime binaries and links were rejected; new modules were staged by architecture.
Fresh Wine prefix bootstrap remains incomplete in this targeted Mac test build
and was deliberately not tested by these successful fixture runs. No user
Steam/Wine prefix or working main Vision Pro app was changed.

Local receipts and logs are retained under
`/Volumes/XRDev/build/WineVisionVR/local-dummy-oct18`; signed r4 artifacts and
build verification are under `x86-modern-oct18-r4`. These machine-local test
artifacts and device credentials are not committed. Hardware input, FEX and
D3D/OpenVR rendering still need separate headset validation.


### Repeat actual local dummy execution

`windows-vr-tools/test_dummy_wine.py` preserves the executed runner. It requires
a Mac Wine build with x86_64 and i386 PE modules, a working x86_64 FreeType
backend, and an output directory outside the repository. Our host profile used
Wine `257f271cfffed9f22f7987cac53bc00095d092fe` (11.4), FreeType
`42608f77f20749dd6ddc9e0536788eaad70ea4b5`, and Rosetta on Apple Silicon.
Wine configure included `--enable-archs=i386,x86_64 --with-freetype --without-x`,
x86_64 host compilers and native build tools from `--with-wine-tools`. This is
a separate Mac test runtime, not the packaged visionOS runtime. The exact local
configure/build recipe and source hashes are retained in the build receipt.

Stage the app package's four EXEs under a separate fixture root (copy the exact
packaged artifacts, not recompilations):

| App resource | Fixture-root destination |
| --- | --- |
| `DesktopDemo/desktop-demo.exe` | `x64/desktop-demo.exe` |
| `DesktopDemoX86/desktop-demo.exe` | `x86/desktop-demo.exe` |
| `VRSmoke/vr-smoke.exe` | `vr-x64/vr-smoke.exe` |
| `VRSmokeX86/vr-smoke.exe` | `vr-x86/vr-smoke.exe` |

```sh
python3 windows-vr-tools/test_dummy_wine.py \
  --wine-build /external/host/wine-build \
  --wine-source /external/host/wine-source \
  --fixture-root /external/packaged-fixtures \
  --freetype-lib /external/host/freetype-install/lib/libfreetype.6.dylib \
  --output-root /external/dummy-results \
  --prefix-template /external/prefix-template.tar.gz \
  --template-sha256 HASH_FROM_VERIFIED_PREFIX_RECEIPT
```

All paths must be absolute. The optional template must contain only stock prefix
state (no runtime DLLs, executables or links); its hash must match the caller's
verified provenance. Our run used template SHA256
`88659fe2aa9c18a3803f5358d0fa1817feaf7f01aefa6a0e946a88515485fb53`. The
runner stages new same-build modules into each isolated architecture directory,
seeds Wine's open fonts and skips the template's INF reinstall using the matching
source timestamp. This explicitly leaves first-run prefix initialization outside
the result. Omitting the template attempts fresh prefix initialization and needs
a complete Mac Wine installation, beyond our targeted fixture module build.

Each invocation creates new result directories, checks complete result lines and
expected pointer widths, records executable/module hashes and captures memory
maps. Desktop windows intentionally stay open; the runner stops only its own
WINEPREFIX after capturing results. A CPU-only PASS never implies OpenVR or GPU
rendering passed. Keep this tool separate from the no-Wine host contract runner.

The separate r4 test app installed successfully after the local gate passed,
at bundle path `DD31ECBE-77E7-47CB-9932-FADD45B25F1C`. Xcode's automatic
open request timed out and the subsequent process list contained no WineVision
process. Hardware retesting is pending; this is not a device self-test PASS.


## 18 October r4 headset desktop and CPU confirmation

The installed r4 bundle `DD31ECBE-77E7-47CB-9932-FADD45B25F1C` opened after
the earlier Xcode timeout. The new launcher log maps both frameworks from that
exact bundle at 11:28:42 and confirms ntdll startup at 11:28:46. Its packaged
runtime plugin is `A616C513-818F-3767-8915-E594AAD36635`, built from `63543bd`.

```text
PASS GDI desktop self-test pointerBits=32 SendInput=1 edit=1 button=1 save=1 load=1 UTF8roundtrip=1
```

The new ancestry trace returns the correct GA_ROOT for the root, button and
editor, where r3 returned zero. GetMessage now delivers mouse-down and mouse-up;
the real injected click increments the counter before the separate programmatic
BM_CLICK check. Subsequent physical input increases the counter through 3–8,
corroborating the user's explicit confirmation that tapping Count clicks works.
This closes the captured missing-down/zero-root pointer failure on this fixture.

The same app was then restarted with
`--vr-smoke-test --x86-guest --cpu-self-test`. Its fresh 11:30 session loaded
ntdll, completed normally, and recorded:

```text
CPU SELF TEST PASS pointerBits=32 arithmetic=0xf0d18bc8 event=signaled
exit status=0
```

This confirms actual 32-bit Wine/FEX CPU and GDI/input execution on Vision Pro,
in addition to local Mac tests. It does not establish D3D11/OpenVR rendering or
32-bit game compatibility. The next separate test is the 32-bit VR scene.
Evidence is retained under `x86-modern-oct18-r4/retest`: the desktop result,
appended ancestry/input events, launcher identity log and CPU result/startup log.
Earlier failures in the appended event file remain historical evidence; the
successful r4 block starts at its new ancestry snapshot.


### 32-bit VR scene: both-eye and head-tracking confirmation

The subsequent r4 D3D11/OpenVR run submitted more than 2,400 guest frames. The
user confirmed the coloured cube is visible in both eyes and follows head
movement. Logs show two matched views/targets, completed guest and presentation
GPU work with zero failed command buffers in the captured interval, and live
head tracking. From 11:31:06.765 to 11:31:16.787 the guest submission count
rose from 1,388 to 2,290: approximately 90 guest frames/second over this ten-second
fixture interval, not a game benchmark or long-duration stability result.
Guest textures were 1920 by 1792 per eye. Guest foveation was not exercised.

The reported different background colours were deliberately coded into the
fixture per eye, rather than evidence of a failed texture. Both eyes now use
the same dark blue background. This visual-only fixture change requires new
EXEs and local revalidation before its next device installation; the successful
rendering observations above refer to the original r4 two-colour fixture.
32-bit game compatibility, including Audioshield, remains unconfirmed.


### Matching-background package validation

Commit `03453cf` was exported into an isolated source archive. Both VR fixture
EXEs were rebuilt, then overlaid onto a copy of the verified r4 app and its
outer bundle re-signed using the original entitlement values and provisioning
profile. All 1,110 app paths were compared: only the two VR EXEs, their build
receipts, the outer resource seal and main executable signing data changed.
Native code/data and every embedded framework/runtime resource stayed identical;
the main Mach-O changed only its signature and two signature-size bookkeeping
fields. No native engine relink or profile rebuild was performed or claimed.

Both x64/i386 desktop self-tests and CPU self-tests passed again using exact
final packaged executable hashes. An independent agent verified this package
comparison, local results and deep/strict signature validation. The cosmetic
package installed separately at bundle `D2A2DC24-929E-4A3B-A88A-3A675B77CC97`.
Its automatic open request timed out after 20 seconds. After manual opening,
the user confirmed both backgrounds now match on the headset.
Build, source export, artifact comparison, runtime-reuse proof, local test logs
and signing evidence are retained under `x86-modern-oct18-r4-background`.


## Combined main-app update and Steam identity

The tested 32-bit work was fast-forwarded onto the original working branch,
without dropping its 64-bit support or creating a pull request. The combined
package uses `project.source-air-x86.yml` with the modern source runtime and
both guest architectures enabled. The main application identity remains
`com.philipanderson.WineVisionVR`, signed as
`ZUFPF3R7HP.com.philipanderson.WineVisionVR`. The test-app identity is not used
for this update.

Update the existing main app in place. Preserve its data container and Keychain
access; do not uninstall it or copy the test app's prefix over it. Steam
authentication, Keychain service/account names, saved-library schema, download
paths and shared prefix identity are unchanged from the prior working branch.
Existing Steam games use `Documents/WindowsVR/Prefixes/SHA256(steam.shared)`;
child executable inspection chooses 32-bit guest support while the Steam host
remains 64-bit. Modern x86 support currently covers D3D11, not D3D12.

Before updating, the main app's existing data-container identity and directory
metadata were recorded. Its shared prefix contains `.update-timestamp`,
`system.reg`, `user.reg` and `userdef.reg`, avoiding the native first-run prefix
seed path. The main wrapper package was built from the verified source and modern runtime
resources; no Steam credentials were exported or committed.


### Combined main package installed and existing Steam login confirmed

The unified Release app was compiled from frozen `15b99ce`, retaining the
verified modern native archives, AIR writer and all 1,097 resources from the
locally tested package. Source/runtime architecture and import-closure checks,
Steam child-architecture routing, deep signature validation and an independent
package audit passed. Its main executable UUID is
`916EF61E-AD5C-3CD0-80D7-BC1D84AE48EB`. The embedded provisioning profile and
four signed entitlement values exactly match the prior main app, including
its main application/Keychain identity. No forced test arguments are embedded.

The in-place update installed at bundle
`FD268757-B125-4EA8-88D9-8D6C24A696A9`. The OS assigned a different physical
data-container UUID. The existing prefix marker, registries and all ten Steam
app manifests remain present. Exact metadata equality was not a suitable
retention assertion: user activity during/after the update changed registry
files and game metadata. The initial strict comparison is retained alongside
a separate assessment; neither record claims registry bytes stayed identical.

The user explicitly confirmed the main app is still signed in to the existing
Steam account and shows the downloaded games. The new main process was already
running when inspected; its launcher log maps both frameworks from the installed
main bundle and restores existing Audioshield and Tomb Raider I selections.
The root agent did not restart or launch over that active session. These startup
observations do not establish that those games render or play correctly.

Use the normal **WineVision VR** main app for both guest architectures. The
separate x86 test app remains available for diagnostics. Build, signing, resource
reuse and device-retention evidence are retained under `unified-oct18`, with
`device/retention-assessment.json` recording the user confirmation and checks.
