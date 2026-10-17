# Upstream integration and fresh-checkout build — 17 October 2026

## Revisions and scope

Merged HudsonMCox/WineVisionVR through `76bf424cbf3aa46ef4f8f000505d4677bb2f237f`
into this fork's local changes. The merge is `c016aaa8b3492c4f5b5f4994234800e3ab985d4f`;
the source-built app includes subsequent build repairs through `0dca7af` on
`codex/upstream-integration`. No pull request has been opened.

The earlier user-confirmed Windlands and Job Simulator results belong to the
preserved composite app, UUID `FF26154C-9A14-3681-B78F-420221BBC4BC`. The user
reports acceptable speed in those two games and very slow Fantastic Contraption
when it rendered, alongside earlier freezes/crashes. This is qualitative evidence,
not measured FPS. The new source-built app is a separate candidate until headset
acceptance completes; no game performance improvement is claimed.

## What was combined

Upstream adds persistent FEX caching and native dispatch, ARM64EC guest runtime
packages, coherent frame waits/state snapshots, input CPU improvements, foveation,
depth transport, reconstruction and experimental frame extrapolation.

The merge preserves this fork's desktop input/window support, launch selection and
single-option selection, download queue and size display, session logging and
force-quit controls, Windlands OpenSSL workaround, six extra Wine DLL providers,
Steam host launch-argument fix, OpenComposite crop/flip and x64/i386 ABI fixes,
per-hand action sets and action-space lifetime repairs. Experimental x86 remains
separate from the modern profile; this build has x86 disabled.

Conflicts were resolved around the runtime/plugin lifecycle, guest dependency
selection, frame transport, OpenComposite patches, launch diagnostics and build
staging. Desktop launches avoid VR-package requirements. A translated x86 child
process cannot select the 64-bit FEX cache wrapper merely because its Steam parent
is x64. Build receipts and strict source hashes remain enforced.

## Fresh build evidence

A new clone was downloaded from the fork into
`/Volumes/XRDev/src/WineVisionVR-fresh-checkout`. Dependency sources were fetched
into that clone's `third-party` directory. Wine, FEX, DXMT, native frameworks,
Wine PE DLLs, OpenComposite/OpenXR guest packages, FEX cache helpers, Steam host,
desktop/VR smoke fixtures, source AIR writer and Swift app were built in new paths.
None of the preserved gameplay-tested runtime frameworks were copied into this
candidate.

External inputs reused were the pinned LLVM-MinGW 20260421 bundle, locked native
visionOS LLVM source/build cache at `8dfdcc7b7bf66834a761bd8de445840ef68e4d1a`,
and clean Wine prefix archive with matching provenance. Xcode 27 beta 3 and its
visionOS/Metal SDKs were installed tools. This demonstrates a fresh project build
with documented compiler/prefix dependencies; it is not an empty-machine rebuild
of those dependencies. Signing uses a local development identity, kept out of Git.

Fresh-build defects repaired in tracked source include the modern DXMT patch
context, native Wine header preparation, complete staging fingerprint inputs,
OpenComposite patch ordering, generation of Steam host notices from the five
pinned license texts, source AIR writer compilation/link search paths, and x86-only
resources isolated in `project.x86.yml`. A custom modern graphics output directory
must exist before assembly. After interruptions, completed stages were resumed
without changing provenance receipts to represent unbuilt code. See the
[portable recipe and restart limits](windows-vr-reproducibility.md).

Build products and logs are under
`/Volumes/XRDev/build/WineVisionVR/fresh-upstream-oct17-r2/`:

| Evidence | Result |
|---|---|
| `app-unsigned-complete.log` | Debug app: BUILD SUCCEEDED |
| `app-signed-release.log` | Release app: BUILD SUCCEEDED |
| `verify-release-bundle.log` | Bootstrap/NLS/fonts, PE imports across 100 binaries, modern graphics package, x64/ARM64EC OpenVR/OpenXR and native FEX cache helpers verified |
| `verify-release-signing.log` | Strict signature/profile match, JIT/debug permission, increased memory, JIT protocol, diagnostics on and frame capture off |
| `headset/install.json` | Installed as `com.philipanderson.WineVisionVR`, retaining the existing app data container |

Signed Release product:
`artifacts/xcode-derived/Build/Products/Release-xros/WineVision VR.app`.
App executable UUID: **`E9FD876E-E3EA-3012-B717-072467AA28C5`**.
This candidate includes newly built native frameworks, unlike the historical
composite. The old package remains preserved at the path in the recovery handoff.

## Correctness checks

The integration runner completed **26 passing checks, zero failures and three
explicit skips** at merge `c016aaa`: legacy WOW64 source was not supplied, the
optional OpenComposite logger source was not supplied, and simulator checks were
run separately. Source preparation/patch application and OpenVR/OpenXR cross
builds covered x64, x86 and ARM64EC; only x64/ARM64EC are packaged in this candidate.

Additional native input/action lifetime, frame-state/wait, depth, crop mapping and
Metal UV tests passed, including sanitizer and allocation/pose-parity checks.
Real Mac Metal tests passed for frame synthesis, reconstruction and guest
foveation. Five visionOS 27 simulator suites passed: compositor, frame transfer,
GPU statistics, presentation and audio policy. Guest foveation is unsupported in
the simulator because it lacks rasterization rate maps; it was not counted as a
simulator pass. The temporary simulator was removed after the run.

Detailed results remain under
`/Volumes/XRDev/build/WineVisionVR/upstream-integration/final-checks/` and
`native-gpu/`. These establish component correctness and compilation, not headset
JIT, game compatibility or sustained game FPS.

## Headset acceptance and performance

The candidate is installed; interactive gameplay validation is pending. The
headset reports `passcodeRequired: true`, preventing that test until it is unlocked.
An attempted `--vr-smoke-test` launch timed out after 20 seconds; no guest frame or
gameplay success is inferred from installation alone.
The final packaging/import test suite passed all **60 tests** after the app-build
repairs. Start with
the small VR smoke fixture, then use Windlands and Job Simulator as compatibility
controls. Test Fantastic Contraption separately for loading stalls and game FPS.
Use both Sense controllers, an awake/unlocked headset and connected LocalDevVPN.

For a useful speed comparison, keep scene, render scale, presentation mode and
cache state comparable; report real guest frames separately from 90 Hz display
reprojection. Prior Fantastic Contraption logs recorded guest frames stopping
while compositor/GPU completions continued, so that case cannot be explained
solely by a slow headset display. No measured FPS gain or reliable Fantastic
Contraption fix has yet been established.


## Subsequent headset regression investigation

The source-built candidate did not preserve the prior gameplay result: the user
reported errors in several games and initially no Windlands view. Steam selected
Windlands option 5 and reported launch-client-error=0, but the game child faulted
before submitting guest frames. The Wine log identifies a null per-process GDI
shared-handle table: the faulting staged gdi32 exports are `get_gdi_client_ptr`
(RVA 0x2c1d8, read 0x60e) and `SelectObject` (RVA 0x2d25c, read 0x656).
This is not evidence of missing packaged font files: the fresh and preserved apps
have matching font resources. Repeated FEX code-buffer mprotect warnings alone
are not proof of the fatal cause.

A diagnostic launch with `FEX_ENABLECODECACHINGWIP=0` bypasses the new cache
launcher wrapper. The user initially reported a Windlands splash screen, then explicitly confirmed
a menu or playable level. The corresponding log progressed from 80 submitted
guest frames during loading to 1,571, with ongoing submissions past the splash.
This establishes progress on this diagnostic run; controller interaction and a
sustained session remain separate checks.
The application now leaves this experimental wrapper disabled by default while
preserving explicit opt-in overrides. The package and native persistent-cache
implementation remain available. This mitigation is not a claim that the deeper
Wine GDI child-initialization issue has been repaired.

The native follow-up is to publish per-child GDI state after the process-local
initialization entry in `build/win32u-unix/class_ios.c` and allow the existing
64-bit publisher through `win32u_gdi_check_publish` in
`wine/dlls/win32u/win32u_private.h`, while preserving the WoW64 section gate.
Those are generated/prepared dependency paths: any repair must be implemented as
a tracked preparation patch, rebuilt with matching receipts, and tested across
launcher, Steam and game children. No such native change is represented by the
current workaround.


## Space Pirate Trainer — provisional after clarification

On 17 October the user confirmed **Space Pirate Trainer (Steam 418650) works**
on the installed source-built update, app UUID
`772767BC-4724-3F1A-96DE-FDE41E4B334B` (source `84663b7`). The app defaults
`FEX_ENABLECODECACHINGWIP=0`. This supersedes earlier Space Pirate Trainer failures
for this build; no FPS or long-session stability measurement was supplied.
The user then clarified that it is slow to load and only almost works. This later
qualification is authoritative: Space Pirate Trainer is provisional, not fully
validated gameplay.
