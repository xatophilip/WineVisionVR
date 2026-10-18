# Windows VR implementation status

## Return to an existing VR session (2026-10-18)

An ordinary immersive-space closure previously called native stop and required
an app restart. The source now keeps the accepted guest/session and offers
**Return to VR** in the launcher. Reopening creates a fresh presentation and
waits for tracked targets without another Wine/JIT/Steam launch. Explicit
**End session** retains its stop behavior. Failed/cancelled reopening preserves
the guest and offers retry. Replacement render tasks await predecessor cleanup,
and paused waits are cancellable, so old cleanup cannot clear new targets.

Actual-source lifecycle/UI tests, 18 tracking cases and the renderer task-store
contracts pass locally. Existing OpenXR pause/resize/exit and session-stop checks
also pass; this change needs no native runtime modification. A new signed app
and physical leave/return acceptance are still pending; the installed r8 results
below remain distinct from these source changes.

Recent error review also confirms that the new XInput module loads in
CyberThreat and Tilt Brush, and Tilt Brush really starts the packaged WMIC BIOS
and baseboard queries. Those older missing-component warnings are not the current
blocker. CyberThreat's fresh Unity log reaches OpenVR initialization without a
fatal exception; its sampled preload thread is busy and no game frame is observed.
Tilt Brush submits 90 frames but the user leaves while it is loading and cannot
reenter. Neither observation establishes a game crash or completed loading.
Audioshield's separate repeat-fault termination below remains a confirmed failure.

## Latest signed package: startup recovery (2026-10-18)

The r8 main app built and passed signing/package validation from app source
`8051a4f155821bd2fa68a7b7f193cceafc7f190f`. It reuses the exact validated r7
native archives, source AIR writer and generated game/runtime resources from
`f60825a3f97854b2a2de82d99fc6cd3e1b53c05d`; this is an app-only compile/link,
not a new native/guest runtime build. Current source integration fingerprints
and the complete native/guest/graphics/AIR receipt graph all match those inputs.
The app UUID is `A8509109-2C41-34BF-8A5F-4518CADC8004` and runtime plugin UUID is
`4956DA8A-1DE5-39F9-A09C-0B541B5B8C67`. All 1,121 packaged file names remain present;
resource bytes and the seven owned Windows test PEs match r7 exactly. Their six
passing local executions are linked by hashes rather than relabelled as new r8
executions. The original main identity, provisioning profile and entitlements
are retained.

The broader local suite completed from the same clean app-source commit with
**37 passing groups, zero failures and six explicit optional skips**. Its
packaging group passed 68 tests, and the tracking startup group passed all 17
controlled cases. The two omitted device-SDK component builds are covered by
the complete signed app build. Separate legacy/general DXMT checks, the optional
OpenComposite logger check and simulator execution were not requested in that
run. Modern WOW64 transport/layout, native child bootstrap/imports, real-resource
XInput/WMIC, OpenXR input/action/session and real host Metal checks passed.
These are correctness results, not headset FPS or game compatibility claims.

The exact app is saved at
`/Volumes/XRDev/build/WineVisionVR/startup-oct18-r8/artifacts/xcode-derived/Build/Products/Release-xros/WineVisionVR.app`.
The r8 build root's `verified-app-complete.json`, `reuse-inputs.json`,
`build-inputs.json`, `validation/app-files.json` and `artifact-handoff.json`
identify its source, inputs and sealed bytes. The complete audit SHA-256 is
`6aa18d52203f0f944d309b0d5b769417c5461a73b8fa602588f13a0d68fe8c39`. The broader suite report is
`/Volumes/XRDev/build/WineVisionVR/startup-host-suite-oct18/results.json`.

After the headset restarted, r8 installed successfully under the original main
bundle identifier. All ten existing Steam app manifests remain present. Fresh
headset controls passed both direct i386 (PID 559) and x64-parent-to-i386-child
(PID 569) exception handling/continuation, with exact packaged fixture hashes,
fresh result markers, the r8 plugin UUID above and Wine exit zero. The automated
runner completed successfully, including its owned-process cleanup. Evidence is
`startup-oct18-r8/device-install.json` and
`startup-oct18-r8/device-controls-run-2/result.json` under the external build root.

The preceding attempt is retained as `device-controls-run-1`: it timed out waiting
for StikDebug after reboot, before Wine ran, then exhausted its bounded capture
window. It is not a game/runtime failure or a passing test. The successful retry
followed confirmation that LocalDevVPN and StikDebug were both connected.
Fresh x64 and i386 VR smoke scenes also rendered visibly in both eyes with
matching backgrounds and working head movement, confirmed by the user. Fresh
current-PID logs show both Sense controllers connected and tracked, stereo targets
with valid render poses, and successful guest/presentation GPU completion. In
the x64 sample, guest GPU completions advanced 285 to 1,185 and presentation
completions 575 to 1,477 over 10.023 seconds, with zero GPU failures. The i386
sample reached guest completion 370 and presentation completion 627 before the
user left the view/removed the headset; its subsequent layer invalidation is not
recorded as a spontaneous crash or a sustained-stability pass. Captures are
`startup-oct18-r8/vr-x64-run-1`, `startup-oct18-r8/vr-x86-run-1` and the latter's
`vr-x86-followup-*` files in the same build root. These controlled scenes do not
establish game compatibility, deliberate controller actions, or pause/reentry.

Windlands was separately reported **playable on r8**. Its current-session
launcher shows both Sense controllers connected/tracked and guest GPU completions
271 to 3,139 plus presentation completions 1,948 to 5,046 over 35.061 seconds,
with zero GPU failures. The retained native log confirms PID 607, the r8 plugin
UUID and the actual x64 Windlands/OpenVR/OpenXR modules. The original automatic
capture stopped on a live-log socket-copy failure and remains failed; this
result uses a separate successful recovery of the immutable rotated log and
user feedback. See `startup-oct18-r8/windlands-recovered-evidence.json`.
The later process switch included a CyberThreat selection; the record does not
establish why PID 607 ended or imply a CyberThreat gameplay result.

Job Simulator was also confirmed to display its game and allow grabbing on r8.
The right Sense controller is connected/tracked with changing grip/button values;
the left is absent in this sample, so this does not establish two-handed input.
Over 25.045 seconds, guest GPU completions advance 1,622 to 4,968 and presentation
completions 2,915 to 5,142, with zero failures. Short transfer-rate windows report
approximately 60–69 new frames/second while the compositor displays 88–90; this
is an interactive observation, not a controlled benchmark. Evidence is
`startup-oct18-r8/job-simulator-run-1/launcher-2.txt` and its copy receipt.

Audioshield's fresh r8 x86 run fails before game frames. A successfully copied
current-PID native log ends in 2,000 identical host-fault redeliveries followed by
process termination. It identifies an unaligned ARM64 SWPAL emitted for the guest
kernel32 InterlockedExchange path; this is a concrete translator/atomic handling
failure, not evidence that adding another DLL fixes the game. Owned reproduction
and a narrow handler fix are being investigated. Keep the failed result:
`startup-oct18-r8/audioshield-run-1/runtime-1.txt` and its successful copy receipt.

Tomb Raider I reached its intro video and menu on a flat desktop, confirmed by
the user, but was reported too slow to continue and did not respond to Sense
controls. The toolbar Enter command does work. Its diagnostic journal identifies
Steam app 224960, x86 and the shared signed-in prefix. The missing windowed-game
controller routing has a separate scoped source fix with local tests, not yet
installed in r8; no Tomb Raider gameplay/performance success is claimed.
See [DOSBox status](windows-desktop-dosbox.md).

## Fork checkpoint (2026-10-18)

The dated sections below preserve the earlier development record. For this
fork's current run/rebuild instructions, use the [reproducibility guide](windows-vr-reproducibility.md)
and [fork changes](windows-vr-fork-changes.md). Windlands, Job Simulator and
Space Pirate Trainer have user-confirmed gameplay in earlier builds; this does
not establish that every later package passes those games.

The combined main app retains the existing Steam identity and supports the
experimental modern i386 and x64 routes. The r6 headset controls passed direct
i386 and x64-parent-to-i386-child exception handling and continuation; see the
[native child bootstrap evidence](windows-vr-native-child-bootstrap.md).

A normal fresh signed r7 build now includes the genuine missing ARM64EC XInput
1.3, 1.4 and 9.1.0 modules, with source/runtime commit
`f60825a3f97854b2a2de82d99fc6cd3e1b53c05d`. Its native/guest/graphics receipts,
19 native archives, 998 source guest payloads and 1,121 packaged files passed
validation without resource overlays or compiled-runtime reuse. Signing and
actual-source/real-PE packaging and sanitizer contracts passed. The app UUID is
`EB1AD993-6EE1-3FCC-900E-FC2727A2EFE3`; the runtime plugin UUID is
`1BF91AF5-E9CC-3D61-A265-B6583A082A5A`.

All six exact packaged x64/i386 local GDI, CPU and direct/mixed-child controls
also passed, with the signed app unchanged; these are Mac Wine controls, not
headset runtime execution. The packaging unit suite passed all 68 tests.

The headset battery ran out before Tomb Raider could be tested. The r7 package
has not been installed or executed on Vision Pro. The new XInput packaging
resolves missing-module availability, not a verified fix for Tilt Brush,
CyberThreat or Audioshield gameplay. See [XInput verification](windows-vr-xinput-packaging.md)
and [the DOSBox status](windows-desktop-dosbox.md).

## Startup recovery and VR dependency checks (2026-10-18)

A subsequent Swift-only fix addresses a reproduced compositor startup failure:
two failed ARKit run attempts previously returned without starting tracking, but
the renderer still latched tracking as started and never retried. Startup now
reports success explicitly, retries failures with an interruptible one-second
wait, and checks cancellation and layer state after asynchronous setup. It
creates fresh world-tracking providers for startup and world-only fallback;
[Apple's ARKit run contract](https://developer.apple.com/documentation/arkit/arkitsession/run(_:))
does not permit restarting stopped providers. Failed/aborted setup stops the
session and clears controller state.

Seventeen controlled cases compile and execute the actual production methods
with ARKit/layer boundaries substituted. They cover failed startup recovery,
world-only fallback, pause/resume, delayed provider-state visibility, and
cancellation/pause/invalidation at setup/fallback suspension points. The exact
prior source reproduces the failed-startup latch. Independent review, pinned
visionOS API typechecking and source parsing passed. This does not execute an
ARKit service or prove total authorization/pause timing or global renderer-task
exclusivity. The signed r8 app build and the physical startup/stereo controls above have
passed; game acceptance and pause/reentry remain separate checks.
External evidence is under `cold-start-review-oct18/tracking-final/` beside the
other build records.

A read-only audit against the exact r7 package resolved all 1,547 imports from
the available genuine Windlands EXE/native plugins and all 511 imports from
Fantastic Contraption's UnityPlayer, including ordinal/recursive forwarders and
the real 672-contract API-set namespace. No additional mandatory DLL fix was
established. This does not cover every native plugin of every installed game.
Shared SDL3/Steam video-component warnings also occur in known-working game
logs; optional Oculus fallback warnings coexist with explicit OpenVR rendering.
Those messages alone do not establish a game-startup cause. See external
`vr-compat-audit-oct18/ranked-findings.json` for the checked inputs and limits.

The next headset acceptance starts with the owned direct/mixed architecture
controls and stereo VR smoke scenes, then Windlands and Job Simulator or Space
Pirate Trainer, checking visible gameplay, both tracked controllers, new guest
frames and GPU completion. Retest Audioshield, Tilt Brush, CyberThreat and
Fantastic Contraption individually with fresh logs. Static imports or submitted
frames alone do not establish visible gameplay. LocalDevVPN and StikDebug must
be ready after the headset restarts; start through WineVision's Play handoff.

## Launch-free review (2026-10-12)

The implementation is an experimental contribution seeking further development
and Vision Pro testing by someone with a paid Apple Developer account. No Windows
VR game, signed headset installation, JIT session, controller session, or
performance benchmark has been tested on a headset. The checks below are offline
regressions and compilation, not game/runtime validation.

This project began as a fork of [AVP Play](https://github.com/myMartek/avp-play) (myMartek) and now stands alone.
It keeps English/German `L()` strings and regression tests.
Library, manifest and architecture checks are separated from device operations so they can be exercised without a headset.
The Mac-side transfer tool that AVP Play had (`avpplay windows stage`) is not part of this project; Steam downloads replaced it.

- Windows VR contracts and localization: nine tests, zero failures.
- Python packaging/source-pin regressions: fifteen tests, zero failures, using
  synthetic PE headers, archives, and local Git repositories.
- Python parsing, shell syntax, and whitespace checks passed.
- The complete bilingual visionOS app builds unsigned using the previously
  compiled native/guest libraries. This pass did not rebuild or execute Wine/FEX.

Source preparation now rejects local changes and mismatched/uninitialized
recursive submodules. Prefix limits are enforced while iterating headers;
sanitizer hashes stream and receipt publication does not overwrite another
writer's file. Older prepared source receipts intentionally fail reuse when the
preparation inputs change; rebuild them rather than rewriting their hashes.

The dated build record below describes the earlier local assembly.

## Current build checkpoint (2026-10-11)

The complete unsigned Windows VR app built successfully with Xcode 27 for
arm64 visionOS 27, including its validated Runtime and WindowsVR resource folders.
The saved artifact is `dist/windows-vr-2026-10-11/WineVision VR.app`, with build logs,
file hashes, and native/guest/graphics/staging receipts beside it. See
[the local build handoff](windows-vr-local-build.md).

The build includes source-built Wine native archives, FEX core and ARM64EC
translator, the translator's LLVM-MinGW runtime DLLs, the real Wine-generated
portable prefix, x64 OpenXR/OpenComposite clients, and modern DXMT D3D11/D3D12
native/guest libraries. The graphics receipt covers the four executable graphics
DLLs; Wine's data-only API-set schema is preserved separately. Common runtime and
fresh graphics profiles use identical common-overlay provenance and native binder
sources; the final graphics binaries are recorded in the common resource ledger.

Signing is blocked by the selected Personal Team's missing certificate private
key. No signed/installable product is established. No tests, benchmarks, game
launches, installations, or device runs were performed. Compilation and package
validation do not establish JIT/device compatibility, game support, or near-native
performance.


## Experimental D3D12 continuation

The D3D12 guest OpenXR path, DXMT queue/WMT source overlay, manifest/UI
support and fail-closed package capability plumbing are implemented in source.
See [windows-vr-d3d12.md](windows-vr-d3d12.md) for the exact contract and checkpoint.
The newer upstream DXMT source is pinned separately; the D3D11 baseline is not
silently upgraded. The mobile storage/framework/shader port, embedded Wine
binding, modern D3D11 bridge, native/guest build recipes and assembly integration
are implemented in source. The old permanent build blocker is removed. The guest OpenXR/OpenComposite DLLs have compiled with D3D12 enabled. The modern native/guest DXMT closure has compiled and passed receipt-backed staging; headset behavior remains unverified. The pinned upstream D3D12 route supports Shader Model 5.1/DXBC,
not DXIL/Shader Model 6, ray tracing or mesh shaders. Tests and runtime validation remain deferred.

## Runtime completion pass

The first x64/D3D11 color-stereo path now also includes cooperative exit,
pre-JIT resource/PE checks, isolated per-game prefixes, a versioned array/region
submission path, static swapchains, tracking-loss/focus handling, and source/native/
guest coherence receipts. The V1 COM and WMT layouts remain frozen; the optional
Ext3 interface and V2 transport carry explicit slices and subrectangles. One Luna
worker completed provisioning; another was rate-limited with incomplete transport
edits, which were finished and source-reviewed by the parent. No execution result
is implied by that source review.

The provisioning scripts can rebuild the critical ARM64EC Wine/FEX/DXMT modules
from the prepared pinned overlay. The clean prefix is generated with the upstream `wineboot --init` script.
`create_prefix_snapshot.sh` invokes the real Wine build and removes host-specific
links and archive metadata through `sanitize_prefix_snapshot.py`. The documented assembler targets a Mac with Xcode/xros. Its component build commands, resource staging, and unsigned app link have completed. Signing and device/runtime verification remain outstanding.

## Implemented in source

| Area | Implementation |
|---|---|
| Headset library | Local versioned storage, imported manifests, folder bookmarks, selection/removal, stale-bookmark refresh, corruption refusal |
| Launch profiles | Named per-game profiles, exact JSON argv editing, default-compatible profile decoding, persistent spatial render scale |
| Diagnostics | Separate Wine process status and native queue counters, versioned JSON export, actual OS/build/hardware identifier where available, explicit unmeasured metrics, environment values omitted |
| Native adapter | Preflight before JIT/session consumption, x64/package rejection, isolated game-ID-hashed prefixes, private guest mappings, startup cancellation/cooperative exit, environment restoration, live-guest lifetime protection |
| OpenXR | D3D11 stereo/frame/session/space/action/haptic surface, core string/name calls, graphics-requirements enforcement, FIFO/static image ownership, retained last release, optional array/packed-region submission, focused action states, cooperative STOPPING/EXITING |
| Compositor lifecycle | Target/tracking/controller/haptic invalidation, retained in-flight leases, ordered consumer tickets, bounded outstanding tickets, atomic target-generation submission checks, owned last-frame snapshots between guest updates |
| Spatial scaling | Uniform reduced per-eye producer dimensions and ordinary Metal bilinear presentation; 100% keeps exact-size copies. Explicit BGRA8 sRGB is mapped through guest DXGI and DXMT transport |
| Pause/resume | Native stale state is cleared; guest paused frames request no rendering. Same-format/same-size target generations are refreshed; incompatible geometry reports session loss |
| Assembly | Explicit opt-in assembler, separate native/Windows resource inputs, clean-prefix archive validation, builtin/guest/license checks, transactional resource staging, XcodeGen/development-signing configuration |

Primary implementation paths:

- `visionos-windows-vr/Sources/LauncherModel.swift` and `ContentView.swift`
- `visionos-windows-vr/Sources/Rendering/`
- `windows-vr/Sources/WindowsVRCore/WindowsVRLibrary.swift`
- `windows-vr/Sources/WindowsVRCore/WindowsVRCompatibilityReport.swift`
- `windows-runtime-plugin/WindowsVRRuntimePlugin.mm`
- `windows-vr-native/Sources/WindowsVRCompositorBridge.mm`
- `windows-vr-openxr/src/WindowsVROpenXR.cpp` and its DXMT overlay
- `windows-vr-tools/stage_resources.py` and `assemble_runtime.sh`

## Entry points

The receiving bundle ID in the research app project is
`org.avpplay.visionos-windows-vr`, not the Mac companion's bundle identifier.
No store acquisition or DRM bypass was added. The CLI is implemented; a Windows
workflow in the Mac SwiftUI game catalog is not delivered.

For assembly instructions, see [the toolchain guide](../windows-vr-tools/README.md).
It requires an Apple-silicon Mac with full Xcode/xros SDK, external toolchains,
a clean prefix archive, Windows Wine/DXMT builtin resources compiled from the
matching prepared overlay, license inputs, signing/provisioning, and space.
The assembler does not manufacture the prefix. Its opt-in PE mode rebuilds critical Wine/FEX/DXMT guest modules and records matching resource hashes; pinned base PE/NLS/legal resources are still required.
Its opt-in flag is not authorization to run it under a no-testing instruction.

## Explicit limits and unfinished work

- No Windows VR title has been selected and established as compatible by this
  continuation. First-game acceptance, controller correctness, JIT/device
  compatibility, sustained play, saves, latency, and performance remain unknown.
- The unsigned app and matching resource package are built. Signing and headset
  runtime verification remain outstanding; a successful build is not runtime readiness.
- Madeira still owns one native runtime session per app process. Stop now requests
  cooperative OpenXR exit and can cancel startup at safe boundaries; it does not
  forcibly kill a Wine thread. A guest that ignores the request still requires app
  restart. Access and ownership remain retained until actual Wine exit.
  Launch acceptance and active Wine are not evidence of game readiness.
- Baseline packaging is x64/D3D11. Experimental D3D12 packaging has an explicit modern-profile build/staging route; its binaries have compiled and passed final receipt-backed staging. ARM64EC games need a separately matched
  package; Vulkan, arbitrary SteamVR drivers, and broad game support are
  not delivered by this path.
- The guest OpenXR implementation is limited, not conformant. Color array slices
  and packed subrectangles are implemented through Ext3/V2; composition depth,
  stage bounds, MSAA, optional extensions, and advanced controller-profile behavior
  remain unsupported. Finite image-wait timeouts
  are not enforceable through the current transport.
- The compositor holds owned copies of the last valid eye colors between guest
  updates; it clears output before the first valid frame or after target
  invalidation. Re-presenting a snapshot does not count as a newly rendered frame.
  Depth-correct/pose-aware reprojection and deadline/rate-mismatch behavior still
  need further implementation and device evaluation.
- Spatial scaling has no established image-quality or GPU-benefit result.
  Temporal MetalFX SR remains unavailable on the initial visionOS SDK target.
  A separate supported temporal backend and proven eye/resource routing are needed
  before temporal NGX/SR can be exposed; bilinear scaling is not DLSS.
- Guest-render-pass foveation and stereo frame generation remain research work,
  not features completed by launcher toggles or a final compositor blit.
- Source/binary license obligations still apply to the upstream runtime stack.
  No game assets, credentials, NVIDIA models, or proprietary NGX binaries are
  distributed by this implementation.

These are remaining engineering and delivery gates, not a request to run tests.
