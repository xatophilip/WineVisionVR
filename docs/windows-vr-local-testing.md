# Local correctness and performance workflow

Run the host checks before changing the frame or query paths. They need Apple
silicon, Python 3, and full Xcode. They do not need Wine, signing, a game, or a
headset. Choose a build directory with ample free space; the runner directs its
scratch files, Swift/module caches, logs and results there.

```sh
export DEVELOPER_DIR=/Volumes/XRDev/Applications/Xcode-27-beta-3.app/Contents/Developer
python3 windows-vr-tools/test_local.py \
  --build /Volumes/XRDev/build/WineVisionVR/checks
```

The checks cover packaging, the Swift core contracts, real Swift OpenXR/OpenVR
registration, Steam launch selection against public Windlands metadata,
sanitized completion-ticket handling, presentation math, the
production compositor bridge, frame ownership, GPU statistics, and an old/new
shader pixel comparison using the Mac's actual Metal device. The runner also
builds WindowsVRMetal and all native bridge translation units against the visionOS
device SDK without signing. These are component builds, not a complete runnable
app. `--skip-visionos-build` omits them. The standalone native bridge check uses
the default configuration without the optional source AIR writer.

The pixel comparison uses the shader from commit `adfdf25`; keep that history
available. The lower-level `test_fps_batch.py` supports `--baseline-renderer`
when an explicit source file is preferable.

After the runtime assembler has prepared a patched overlay, add its actual
DXMT and OpenComposite source paths:

```sh
python3 windows-vr-tools/test_local.py \
  --build /Volumes/XRDev/build/WineVisionVR/checks-with-runtime \
  --dxmt-source /absolute/path/to/patched/dxmt \
  --opencomposite-source /absolute/path/to/patched/opencomposite
```

These checks exercise exact pending-event progress, completed-event caching,
flush coalescing, query publication and readback, encoder boundaries, and logger
initialization. Query publication runs under ThreadSanitizer and query readback
under Address/Undefined Behavior Sanitizers. The input contract is included when
the pinned OpenXR headers have been fetched. The runtime source-repair regression
is included when the clean pinned Madeira checkout is available; it verifies the
640 MiB JIT pool and battery-property handling under sanitizers, applying patches
only in temporary copies. `--madeira-source` overrides that clean source path;
do not pass the already patched runtime overlay. Missing optional dependencies are
recorded as skipped, not passed. `results.json` records commands, logs, source
hashes and failures; the runner returns nonzero if any requested check fails.

For additional visionOS coverage, boot a visionOS 27 simulator in Xcode, then add
`--simulator UDID`. The existing simulator scripts compile and run five native
probes: compositor, frame transfer, GPU statistics, presentation, and audio
policy. They use the default CoreSimulator device set. They do not launch Wine.

## Initial local baseline, October 15, 2026

The checkout passed 15 packaging tests, 9 Swift core tests, the Swift registration
contract, and the complete host CPU/Metal batch. WindowsVRMetal and the native
bridge also compiled and linked for arm64 visionOS 27. All 4,096 compared production
shader pixels had identical color and depth. Logs are under
`/Volumes/XRDev/build/WineVisionVR/baseline` on this development Mac.

The expanded local run also passed the patched DXMT event/query/encoder tests,
query publication under ThreadSanitizer, query readback under Address/Undefined
Behavior Sanitizers, the runtime JIT/battery source-repair checks, the controller
input contract, and the OpenComposite logger's constructor/concurrent-write
checks. The runner selects Apple's host compiler shims even when the guest-build
environment has prepended LLVM-MinGW to `PATH`.

The added benchmark tooling increases packaging coverage to 32 tests. The Swift
launch-selection regression also passes: Windlands' installed SteamVR entry is
preferred over its earlier Oculus entry, and menu labels distinguish their launch
arguments even though both routes name the same executable.

OpenComposite initially failed on the external case-sensitive filesystem because
upstream used capitalized Windows header names and `OpenGL32` while LLVM-MinGW
ships lowercase filenames. Patch
`windows-vr-openvr/patches/0006-case-sensitive-windows-headers.patch` normalizes
those references. The actual D3D12-enabled x64 DLL then compiled, linked, staged,
and passed the self-contained C++ dependency check. This establishes a buildable
guest bridge, not compatibility with a particular game.

Creating a visionOS 27 simulator in an external device set failed because
CoreSimulatorService was denied access to its `data/Library/Caches` directory
(Cocoa error 513 / POSIX EPERM). No simulator runtime execution is claimed for
this local baseline. Host GPU checks still ran successfully. A previous author's
simulator result in other documents is separate evidence from this local run.

The desktop update passed 11 Swift core tests, 32 packaging tests, the sanitized
production desktop parser/readiness contract, and Steam launch-selection checks.
The signed Release update is installed. See [desktop smoke tests](windows-desktop.md)
for the physical checks and the subsequent input failures.

The notarized upstream idevice_pair 1.1.0 Mac app validates the Vision Pro's
RemotePairing record after the user opened General → Remote Devices. The record
was sent locally to StikDebug with approval and its presence on-device verified.
With LocalDevVPN installed and connected, the RSD handshake and developer
tunnel succeeded and the mounted DDI was detected. The x64 Windows demo
subsequently ran with readable text, but button actions and cooperative quit
failed. No game execution or FPS improvement has been demonstrated.

## Physical performance comparison

Choose the actual owned game before interpreting performance. Record the title,
version, scene, launch arguments, eye resolution, graphics settings, headset
model/OS, app revision, and whether the run starts with cold shader caches. Use
the same repeatable 60–90 second segment for each build and repeat after warmup.

The launcher log distinguishes fresh guest-image transfer FPS from compositor
presentation FPS. A 90 Hz display presenting cached reprojected frames does not
mean the game produces 90 frames/s. Compare fresh-frame median/p95 intervals,
CPU encode time, and separate guest/snapshot/presentation GPU execution and
queue delays. Treat loading and scene changes separately from steady gameplay.
Do not add mean GPU command-buffer durations together as a frame-time estimate.

Use those measurements to select the next change. Preserve exact GPU-event
progress, producer-image ownership, and the second-page encoder-boundary fix.
The existing snapshot copy makes cached reprojection safe after the game reuses
its texture; removing it requires a replacement ownership/fence design. Synthetic
host speedups and simulator correctness cannot establish a headset FPS gain.

## Windows DLL dependency regression

The physical Windlands attempt passed JIT and opened the native immersive
compositor, then Madeira Dock exited with code 20 before starting the game.
Its CryptoAPI check first lacked `rsaenh.dll`/`crypt32.dll`, then the forwarded
`advapi32.SystemFunction036` target `cryptbase.dll`. The guest build now builds
the missing ARM64EC dependencies from the pinned Wine source. The full resource
farm passes `verify_wine_imports.py` across 93 binaries, checking imports, delay
imports and export forwarders. API-set names are virtual references handled by
the separately verified `apisetschema.dll`. This static check cannot prove
support for dynamic DLL names or runtime behavior. Bundle verification invokes
it for receipt-backed builds. All 44 Python packaging tests pass, including preservation/hashing of Windows
`.drv` modules in the resource stage.

Benchmark builds accept `--steam-smoke-test=428370` to select installed Windlands
with the user's remembered launch option and start it. Normal startup restores
the last selected installed Steam game without automatically running it, so a
retry after restarting the app needs only Play. These paths still use the user's
Steam entitlement and the normal scripted JIT request.

## Later physical startup and alias regression

The complete crypto closure passed the physical client identity check, then
Steam's client loading exposed missing ARM64EC `psapi.dll`. It is now built from
the pinned Wine source and required by staging/bundle checks. All 45 packaging
tests pass. The corrected physical run authenticated Steam online, checked the
owned Windlands entitlement and started its option-5 process. The child faulted
in its FEX image aliases before submitting VR frames. Steam's `game-running=1`
and the compositor's 90 Hz display rate are not evidence of rendered gameplay.

Runtime patch `0009` backports upstream per-process alias callbacks and the
acquire-read follow-up. `test_source_runtime_repairs.py` extracts the patched
production functions and exercises parent/child ownership, a dead registrant,
late mappings and alias-table headroom under ASan/UBSan. The fresh native build
and signing passed; headset validation of this candidate remains pending.

The actual visionOS 27 simulator additionally passed all five existing GPU/audio
probes. See `overnight-tests/simulator-results.json` and
`overnight-tests/correctness/results.json` under the external build root for
results and scope. The temporary simulator was removed after these tests.


## Writable guest runtime mapping regression

Run `python3 windows-runtime-plugin/Tests/test_guest_runtime_mapping.py --build
/absolute/external/build/path` (put the command on one line). It extracts and
compiles the production OpenComposite copy helper with ASan/UBSan, then checks
real filesystem permissions, settings writes, DLL preservation, missing sources,
no-overwrite behavior and session isolation. `test_local.py` includes this as
`guest-runtime-mapping`. This host filesystem test does not prove guest rendering.

On October 16, the physical Windlands run reached Unity/OpenComposite but a
hidden modal reported `Failed to write applist json: Permission denied` and
submitted zero VR frames. The signed bundle symlink was replaced with a private
writable session copy; the focused regression and signed app build pass.


## MSVC/MinGW OpenVR aggregate return regression

`windows-vr-openvr/tests/test_msvc_aggregate_abi.py` takes `--source` (the clean
pinned OpenComposite checkout), `--build` (fresh scratch directory),
`--llvm-mingw`, `--wine` (host x64 Wine loader), and `--wine-prefix` (an existing
isolated host test prefix). It applies the actual generator patch in scratch
files, emits its production bridge thunks and links a real MSVC ABI caller with
a MinGW implementation. The failing control reports the wrong receiver; the
bridged case verifies two matrix sizes, receiver canary and native qualified
calls. This host Wine test does not establish headset/FEX gameplay.


## OpenXR stopping-session regression

`python3 windows-vr-openxr/tests/test_session_stop.py --build /external/build/path`
extracts the production begin/end/request-exit session functions, uses the pinned
OpenXR headers and runs an ASan/UBSan host fixture. It checks STOPPING with a
begun startup frame, early-end rejection without mutation, frame-token reset,
waiter notification, IDLE/EXITING order and runtime-stop restart. It does not
submit graphics or execute a guest DLL. `test_local.py` includes `session-stop`
when the pinned headers are available.

The continuously awake October 16 Windlands run reached OpenComposite's real
graphics-session replacement, then failed `xrEndSession` with
`XR_ERROR_CALL_ORDER_INVALID` while native headset tracking continued. This is
captured in `black-screen-oct16/active-opencomposite.log`; there were zero VR
images. The runtime was wrongly rejecting a begun frame during STOPPING.


## RGBA producer and padded Unity eye targets

The display publishes an RGBA8 sRGB producer contract independently of its
BGRA drawable format. The existing spatial shader samples the producer and
writes the actual display format; cached images retain the producer format, so
snapshot blits remain within one format. Producer extents of at least 64 pixels
round upward to a 64-pixel boundary after render scale; tiny probes retain exact
sizes. This permits Unity's 3840-wide stereo allocation with 1920-wide eye
subrects while the physical view stays 1888 pixels wide. Existing slice, crop,
format, generation and region-size guards remain enforced.

`test_fps_batch.py` already compiles and runs the production host GPU probes.
Presentation now covers both BGRA and RGBA source textures against BGRA output,
with crop, scaling, arrays, reprojection, opaque alpha and valid depth. The
expanded full host run compares 8192 pixels (65536-byte color/depth fixtures),
with zero baseline/patched color or depth difference. Bridge/ownership, GPU
statistics, Swift math and ticket sanitizer checks also pass. Evidence is in
`black-screen-oct16/gpu-review/host-batch/results.json`; the separate direct GPU
logs are `black-screen-oct16/rgba-gpu/`. This is not Windows/FEX/headset gameplay
or an FPS improvement result.


The existing input contract now executes production `SyncActions` under
ASan/UBSan, covering a single action set activated for one/both hands, duplicate
pairs, wildcard ordering, zero active sets, focus loss, invalid/undeclared paths,
transactional rejection, controller read failure, and haptic hand isolation.
This reproduces OpenComposite's internal left/right infoset synchronization;
host success is separate from headset rendering.


October 16 input-sync physical follow-up: the signed candidate installed at
`63A4E617-C1E3-49F9-803B-2531A0010EF0`. A captured earlier run resolved both
Touch interaction profiles, then rejected `xrEndFrame` with
`XR_ERROR_SWAPCHAIN_RECT_INVALID` and aborted its input-session restart when
`xrDestroyActionSet(infoSet)` returned `XR_ERROR_CALL_ORDER_INVALID`. That
earlier excerpt was observed in tool output before the log was refreshed; it
is not a preserved raw log. The fresh 20:58 retry failed earlier at
`xrCreateInstance` with `XR_ERROR_RUNTIME_FAILURE`; its runtime trace shows
target acquisition returning -2. Current evidence is in
`black-screen-oct16/input-sync-live-*` and `input-sync-built-app.json`.
No Windlands images or gameplay have been verified.


## AVP Play comparison

The user-suggested [myMartek/avp-play](https://github.com/myMartek/avp-play)
is the original launcher project WineVisionVR forked before becoming a
separate Windows runtime project. Its Klepton-based Android/Linux game
translation stack is not an upstream Madeira/Wine runtime update; our pinned
Madeira runtime has separate ancestry. Its README describes render/display resolution controls, foveation,
MetalFX and in-headset metrics. These are useful performance experiments after
Windows frames render, not proof that Windlands or Windows desktop apps work.
Our existing render-scale control and display/transfer/GPU timing already cover
some of those ideas. Klepton's upstream status lists OpenBrush as working,
which is a separate possible route to the user's later VR painting goal.

At AVP Play commit `c074cba230991359b0173b62da5873a23ed17740`,
[`xrizer-frame-timing.py`](https://github.com/myMartek/avp-play/blob/c074cba230991359b0173b62da5873a23ed17740/third-party/xrizer/xrizer-frame-timing.py)
uses measured timing instead of inherited fixed timing constants and includes
texture-bounds diagnostics. Adapting measurement and explicit rejection logging
is useful; its Linux ARM64 xrizer binary is not our Windows x64 OpenComposite
DLL, and GPU completion semantics must be checked before copying timings.

The later `input-sync-late-launcher.log` resolves the startup timing gap:
layer invalidation at 20:58:34.736 and render-task exit at 20:58:34.738 preceded
the 20:58:44.348 instance failure. That latest run had no live presentation
targets and must not be treated as evidence of a new guest graphics regression.


## Action destruction and surviving spaces

`python3 windows-vr-openxr/tests/test_action_lifetime.py` extracts the production
handle registry, action destruction and action-space paths. Its ASan/UBSan
fixture checks cascading child-handle invalidation, stale handles, unrelated
sets, binding cleanup, independent action destruction and an existing space
remaining usable while its backing resources live. Resources remain
instance-owned until instance cleanup, as allowed by
[the OpenXR destruction contract](https://registry.khronos.org/OpenXR/specs/1.1/man/html/xrDestroyActionSet.html).
The local runner includes this check when OpenXR headers are available.

The final action-lifetime and input-contract raw sanitizer logs and source
hashes are recorded in `black-screen-oct16/action-lifetime-test-result.json`.
The candidate also adds bounded exact rectangle/swapchain rejection and
backend target discovery diagnostics. Existing frame validation remains
enforced pending a continuously presented headset capture. These changes
do not yet establish Windlands rendering or a performance improvement.


The continuously presented action-lifetime run (installed
`4206A6BC-C7BA-4681-9A74-4094796896E2`) confirmed successful input-session
restart. Exact frame rejection was eye 0 offset `(0,1792)`, extent
`(1920,-1792)` in a `3840x1792` swapchain with `1920x1792` targets.
This is an inverted source rectangle, not an oversized positive eye image.
The next abort was `xrSuggestInteractionProfileBindings` returning
`XR_ERROR_ACTIONSETS_ALREADY_ATTACHED` after the input restart.
Raw evidence: `action-lifetime-live-openxr-trace.txt`,
`action-lifetime-live-opencomposite.log` and `action-lifetime-live-launcher.log`
in `black-screen-oct16/`. Zero game images were submitted.


## Built-in small VR scene: headset confirmed

Select **VR test scene**, then **Play**. The authored Windows x64 executable
is about 108 KiB after runtime-registration diagnostics, needs no Steam account
or game content, and draws a colored cube and floor using tracked head poses.
Its fixed 64mm eye separation is approximate; it is a compatibility probe,
not a calibrated game. Escape/window close exits the guest; use the existing
End session/Force quit control when a full app restart is needed.

`--vr-smoke-test` starts normal separate-eye textures in a diagnostic build.
Add `--inverted-bounds` to render a combined stereo texture and submit flipped
bounds like Windlands. `windows-vr-tools/build_vr_smoke.sh` builds only the
app-owned executable and records source/compiler/PE/import hashes.
`visionos-windows-vr/Examples/vr-smoke/test_math.py` exercises production bounds
and projection math under ASan/UBSan. It does not execute Windows graphics.

The first guest attempt exited with VR error124/OpenXR runtime unavailable.
The initial Wine process has actual HIGH integrity (`0x3000`), so the loader
ignores its environment override even when Windows `XR_RUNTIME_JSON` is set.
The probe validates the private runtime manifest/DLL, sets the Windows env,
and conditionally registers that runtime in its own Wine prefix. It restores
the prior registry value on cleanup if the value remains its own. Real host
Wine tests verified removal of a newly created value and exact type/byte
restoration of a prior REG_BINARY value. This is a test-fixture startup helper,
not a general registry fix for every imported Windows VR app.

Installed candidate `6A6FCEDB-1D24-456C-AA1A-1D0B2A062296` is recorded in
`vr-smoke-discovery-built-app.json`. The user confirmed normal mode works,
and then reported the inverted mode looks better. Normal-mode logs captured
thousands of transferred frames at about 88–90 new frames/s, source 1920x1792
RGBA to actual 1888x1792 BGRA targets with matching generations and zero
recorded GPU failures. Inverted mode used a 3840x1792 source, produced valid
1920x1792 per-eye images and reached 86.2–89.6 new frames/s after startup.
These are short tiny-scene samples; no Windlands gameplay or sustained game
performance is established. Raw evidence is `vr-smoke-discovery-late-*` and
`vr-smoke-inverted-relaunch-*` under `black-screen-oct16/`.

Windlands then drew its splash screen and submitted 134 real frames before
exiting. The user confirmed failure after the splash. The repeated fault
occurs on Unity's WWWCurl worker in bundled OpenSSL RAND/digest processing,
followed by secondary Mono exception-handler faults. The OpenComposite input
restart and binding setup now proceed without the previous XR aborts.
`gpu-review/windlands-splash-crash-audit.md` records the evidence.
The scoped `OPENSSL_ia32cap=0` trial reached the menu and introduction.
The setting is now saved only for Windlands (Steam app 428370). The exact
underlying CPU dispatch fault is not yet proven.

The next app-only candidate, installed as
`064F66F7-17BE-4C93-A404-E58032067C17`, is recorded in
`windlands-lifecycle-built-app.json`. It adds bounded lifecycle diagnostics
and the saved compatibility setting. An ordinary Windlands retry without a
CoreDevice environment override reached a level; the user confirmed controls
work and the game seems to be working. Both Sense controllers are connected
and tracked in `windlands-lifecycle-followup-launcher.log`, including changing
thumbstick input. That capture records 1,834 submitted game frames and short
47.1–48.6 new-frame/s samples at an approximately 89–90 Hz display, with zero
recorded GPU command failures. These are initial playable-level samples, not
a long stability/thermal benchmark or a comparative performance improvement.
The previous spontaneous immersive-view closure remains under investigation.

### Download queue

The Steam library now supports selecting several uninstalled games using
**Select games to download** in the menu, then **Queue N**. Selection order is
queue order. Individual game sheets also enqueue downloads and update/repair
requests. The Downloads filter includes waiting entries and shows their queue
positions; a queued game can be removed from its download sheet.

One game install runs at a time on the shared native Steam connection. The
existing downloader still fetches up to eight chunks concurrently. Completion,
failure or an explicit pause allows the next waiting game to start. A failed
game remains available for retry; a paused game waits for explicit resume.
Pending app IDs and pause/update intent are saved separately for each Steam
account, without authentication data. The queue waits during Wine launch,
gameplay and Valve-client preparation so the native and Windows Steam clients
do not compete for the account session.

Queue changes require a new app build. Host regression tests use the production
queue model with controlled session/downloader substitutes; they do not fetch
games or establish background execution while visionOS suspends the app.


### Experimental 32-bit Windows support

Audioshield (Steam app 412740) installs an i386 executable. Its captured Steam
metadata lists only the Windows VR `Audioshield.exe` launch option. The working
Windlands build did not include an i386 Wine farm or x86 VR bridge.

The opt-in route uses `AVPPLAY_ENABLE_X86=1` with `AVPPLAY_ENABLE_D3D12=0` and a
separate prepared legacy runtime. Modern DXMT currently rejects the WOW64
pointer transport, so its native archive must never be combined with these
legacy i386 graphics DLLs. Default 64-bit resources and the installed-build
rollback are kept separately.

The candidate adds freshly built i386 Wine/DXMT, native ARM64 WOW64 helpers,
FEX WOW64, and separately staged x86 OpenComposite/OpenXR DLLs. The real Steam
child executable supplies `guestArchitecture` through the manifest while Steam's
launch host remains x64. Saved Steam entries and profiles are re-inspected before
preflight, replacing missing or stale architecture fields while preserving the
same reconciled launch option throughout asynchronous preparation. Contradictory
overrides on a direct i386 executable are rejected. The i386 OpenVR adapters account for MSVC/MinGW aggregate returns;
OpenXR handles use checked conversions instead of truncating uint64 handles.

Legacy native graphics required a visionOS port: mobile pointer conversions,
shader/header generation, AIR target and SDK metadata, and actual visionOS
metallib platform fields. Optional frame interpolation is explicitly unsupported
on visionOS; ordinary rendering remains enabled. A repeat-build fix prevents
FreeType objects accumulating in the native win32u archive.

Hardware diagnostics include a CPU/event self-test, a mixed MSVC/MinGW ABI
fixture with a success sentinel, and the tiny VR scene. `--vr-smoke-test
--x86-guest --x86-abi-test` selects the ABI fixture; `--vr-smoke-test --x86-guest
--cpu-self-test` selects the CPU path; omit the last option for actual VR rendering.
The CPU scene imports graphics DLLs even though its self-test makes no graphics
calls. The ABI fixture provides the cleaner initial non-graphics check.

Component compilation, source/receipt audits, 57 tools regression tests, and
the signed visionOS app build have passed. Bundle verification checked 165
ARM64EC, 137 ARM64, and 723 i386/guest bridge binaries. The exact 141 private
Win16 compatibility forwarders from i386 kernel32 remain explicitly unsupported;
direct dependencies and other forwarders still require real providers.

On 17 October 2026, the real Vision Pro passed the i386 mixed MSVC/MinGW ABI
fixture and CPU/event fixture (`pointerBits=32`). Wine logs confirm FEX WOW64
execution, and the CPU fixture loads the matching graphics DLLs. The initial VR
scene created a D3D11 device but failed retrieving targets: WOW64 dispatch slots
151/152 did not translate the embedded request pointer into the shifted guest
window. Patch 0018 adds dedicated wrappers for that pointer while leaving native
64-bit dispatch and Metal object IDs unchanged. A sanitizer regression exercises
V1/V2 target/submission calls and reproduces both old faults. Only the native
Winemetal object/combined archive changed; fresh source/receipt audits verified
that all guest resources and other native archives remained unchanged.

Steam registration now selects the matching stable x86/x64 runtime and registry
view. The x86 path uses `Software\\Wow6432Node\\Khronos\\OpenXR\\1`; it preserves
the x64 registry view. Actual Swift/filesystem tests cover switching views and
runtime folders. On-device retesting after the pointer fix submitted the first
four 32-bit VR frames, then failed in the Metal pipeline with AGX bitcode errors;
the user saw grey in one eye. That legacy build also regressed Windlands. The
original modern build was restored and the user confirmed Windlands working.
Audioshield additionally remains blocked at its mixed-architecture Steam child
bootstrap. Neither result establishes playable 32-bit VR support. The narrow
AIR container fix for xros OS metadata is covered by a host sanitizer regression
but remains an experimental hardware candidate. A host i386 Wine attempt had
timed out during prefix initialization and was not evidence of headset incompatibility.

### Testing several games

Each launch attempt now starts a persistent diagnostic journal before preflight
and JIT. It records game/Steam app and option, requested architecture, graphics,
profile, render scale and build identity, followed by factual launch/stop/failure
milestones. Records do not classify a Wine process as successful gameplay.

The app keeps the latest 20 attempts in
`Documents/WindowsVR/SessionDiagnostics`. Pending attempts are recovered on
restart before cleanup or runtime log rotation. File identities and offsets
prevent an earlier game’s unchanged logs being attributed to a failed new launch.
Each fixed text log keeps bounded startup and tail text with an explicit
truncation marker; binary dumps, pairing records and Steam handoff files are not
collected. Captured text omits lines containing credential markers.

Use **Export test sessions** in the launcher toolbar to save all retained
attempts as one JSON file, including the current attempt. It remains available
without a selected game. Export is bounded to 32 MiB. A diagnostic storage error
is logged and does not block gameplay.

For several games, stop the current session, use **Force quit app** and reopen
when a restart is required, then select the next game. Export once at the end,
or leave the paired headset available for the saved journals to be collected.
A short note about what was visible and whether controls/audio worked adds
evidence that process and frame counters cannot establish.

### Download sizes and additional game imports

The library cards and game download panel show a full Windows download estimate
from Steam's compressed depot metadata. The panel separately shows the installed
size. Both use the installer's Windows/architecture/language/depot selection;
missing required or unresolved shared-depot metadata displays unavailable rather
than a partial total. Legacy maxsize is used only for disk size. Resume/repair
can transfer less, and installation can need additional temporary space. These
figures require no game payload download. Old cached game entries remain readable.
Update/repair is a secondary button at the far right, separated from launch.

The 17 October stable-build Fantastic Contraption attempt failed before rendering:
UnityPlayer could not import dwmapi.dll and WSOCK32.dll (c000007b). Google Earth VR
similarly rejected VCRUNTIME140.dll, MSVCP140.dll and AVRT.dll. These modules were
present only as plain ARM64 binaries in the original farm; x64/ARM64EC guests
require compatible ARM64EC modules. The build and staging requirements now include
source-built ARM64EC versions of all five. An isolated PE overlay preserves the
working modern native frameworks; it has separate provenance from the archival
runtime and must pass real game retesting before either title is called playable.

The first composite five-DLL build was installed on the Vision Pro. Fantastic
Contraption loaded dwmapi/WSOCK32, initialized Unity 2019.2 and created its D3D11
Apple M2 device, confirming the original import failure was cleared. It did not
submit VR frames: Player.log reported SteamVR initialization failure, followed
by Oculus plugin fallback errors, and FMOD had no audio device. Steam's actual
cached metadata publishes one VR launch option with no arguments. A scoped
`-vrmode openvr` request and matching ARM64EC mmdevapi are the next test; Oculus
fallback errors do not establish a need to install Oculus services.

Google Earth requires more than its corrected imports: the native iOS user
driver does not implement OpenGL initialization, the packaged OpenComposite path
is Direct3D-only, and this OpenXR runtime exposes only D3D11/D3D12 bindings.
Earth's Ion renderer is OpenGL; no supported Direct3D switch was found. Do not
report Earth gameplay as fixed. The first new Earth attempt stopped in frontend
preflight because its offline launch metadata was absent. The remembered-option
fallback now preserves the explicit prior option and known architecture while
still rejecting absent/unremembered choices and invalid known options.
