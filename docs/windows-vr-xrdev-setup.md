# XRDev Mac setup and current status

Recorded October 16, 2026. The Windlands lifecycle candidate is signed, verified
and installed as `064F66F7-17BE-4C93-A404-E58032067C17`. After an ordinary retry,
the user confirmed **“Level starts and controls work”** and **“seems to be
working”**. Both Sense controllers are connected and tracked. Normal and inverted
built-in VR scenes were also confirmed on the headset. Long-session stability
and comparative performance improvements remain unverified.

RemotePairing, LocalDevVPN and StikDebug enabled the full 640 MiB JIT arena. The
x64 Windows desktop demo displays readable text and the user confirmed typing.
Button actions, saved-note persistence and cooperative quit are not verified;
the explicit **Force quit app** control was confirmed to close WineVision.

CryptoAPI and PSAPI packaging repairs let Steam authenticate online, verify
Windlands ownership and launch the original game's x64 SteamVR option 5.
Earlier repairs passed the per-process JIT alias, writable OpenComposite settings,
session replacement and RGBA/aligned swapchain creation stages. The input-sync
candidate subsequently passed multi-hand action synchronization, then exposed
stale action handles after OpenComposite destroyed its temporary action set.
Action-set destruction now retains independently owned action spaces. The next
physical run exposed inverted texture bounds and an old session blocking new
binding suggestions. The current build adds the OpenComposite D3D11 crop/flip
repair and limits attachment checks to live sessions. A tiny Steam-free VR scene
is bundled to test this path with fewer dependencies.
The latest retry reaches gameplay; no comparative performance improvement is claimed. The later sections
retain the preceding builds and failures as historical evidence.

## Local paths and identity

| Item | Current value |
|---|---|
| Repository | `/Volumes/XRDev/src/WineVisionVR` |
| Environment | `/Volumes/XRDev/build/WineVisionVR/env.sh` |
| Build driver | `/Volumes/XRDev/build/WineVisionVR/build-app.sh` |
| App-only retry driver | `/Volumes/XRDev/build/WineVisionVR/build-app-only.sh` |
| Fresh baseline source | `/Volumes/XRDev/build/WineVisionVR/runtime-source-final10` |
| Prepared runtime / modern DXMT profile | `/Volumes/XRDev/build/WineVisionVR/runtime-final2` |
| Build products | `/Volumes/XRDev/build/WineVisionVR/artifacts` |
| Current DXMT build root | `/Volumes/XRDev/build/WineVisionVR/artifacts/dxmt-bounds-binding-refresh` |
| Current verified DXMT stage | `/Volumes/XRDev/build/WineVisionVR/artifacts/d3d12-stage-bounds-binding` |
| Full Xcode | `/Volumes/XRDev/Applications/Xcode-27-beta-3.app/Contents/Developer` |
| Pinned LLVM-MinGW | `/Volumes/XRDev/toolchains/llvm-mingw-20260421-ucrt-macos-universal` |
| Wine-generated prefix and provenance | `/Volumes/XRDev/build/WineVisionVR/prefix-host-x86_64/artifact` |
| Verified app | `/Volumes/XRDev/build/WineVisionVR/artifacts/xcode-derived/Build/Products/Release-xros/WineVision VR.app` |
| App bundle identifier | `com.philipanderson.WineVisionVR` |
| Paired Vision Pro identifier | `03939351-3C80-57D6-A489-8008453C0EBF` |
| Development team | `ZUFPF3R7HP` |
| Installed StikDebug identifier | `com.philipanderson.StikDebug` |

Builds, caches and scratch files use the external volume because internal free
space is limited. Source the environment before invoking build tools:

```sh
cd /Volumes/XRDev/src/WineVisionVR
source /Volumes/XRDev/build/WineVisionVR/env.sh
```

The local XcodeGen spec is
`visionos-windows-vr/.local.philip.benchmark.yml`; it includes the tracked
benchmark spec, overrides only the application identity, and uses
`.local.VisionOSWindowsVR.entitlements`. Both files are excluded locally through
`.git/info/exclude`. They request Release development signing, debugger attachment
and increased memory. Diagnostics are enabled and full-frame capture is disabled.
The external `verify-local-app.py` passed against the actual signed app and
provisioning profile, including debugger attachment and increased-memory
entitlements. Strict deep code-signature verification also passed.

## Completed checks and pending work

- The consolidated report at
  `/Volumes/XRDev/build/WineVisionVR/baseline/results.json` records **19 passed
  checks, no failures, and one simulator skip**. This includes 32 Python packaging
  tests, 9 Swift core tests, registration and Windlands launch contracts, host
  Metal correctness, unsigned visionOS components, source-repair sanitizer tests,
  DXMT event/query checks, OpenComposite logger/dependency checks, and FEX alias
  cache correctness. All 4,096 compared shader pixels matched in color and depth.
- The D3D12-enabled x64 OpenComposite DLL and x64 OpenXR DLL compiled and staged.
  LLVM and native FEX compiled; native Wine archives compiled with the actual
  visionOS FreeType library. The pinned Wine host generated the portable prefix.
- The final app link exposed missing native crypto dispatch tables. The new
  static-GnuTLS source patch confines its feature macros to the three crypto
  objects and makes their build verify the tables and static resolver references.
  A fresh ntdll build compiled all 37 translation units successfully. The modern
  DXMT native archive and four guest graphics DLLs were rebuilt, native/guest
  receipts regenerated, and actual `Resources/Runtime` and `Resources/WindowsVR`
  staged and verified.
- The desktop-capable Release Xcode build succeeded. Wine bootstrap files,
  production DXMT validation, OpenVR dependencies, strict code signatures and
  benchmark settings passed. `desktop-app-install.json` confirms installation.
- Desktop contracts passed: 11 Swift core tests, 32 packaging tests, sanitized
  production native parser/readiness tests, and Steam launch-selection checks.
  Packaging coverage subsequently increased to 44 passing tests. These are
  additional focused checks; the earlier consolidated baseline above
  predates desktop support.
- The first physical desktop launch verified the 640 MiB JIT arena (40,960
  pages, zero preparation errors). Wine then faulted in `get_env_var` after
  failing to load its language/case tables. The project now supplies all NLS
  tables at `<bundle>/nls`; the bundle verifier checks their presence and exact
  match with `Runtime/nls`. All 36 packaging tests pass. `nls-app-build.log`
  records the corrected signed build and bundle validation. The subsequent
  desktop test reached a real Win32 window; see the later findings below.
- The NLS retest created the actual Windows demo window and its child controls;
  Wine logged pointer movement and button events. Text rendering failed because
  no Wine UI fonts were packaged. The next build includes the pinned Wine font
  folder at `<bundle>/fonts`, checks required fonts before signing, and passes
  37 packaging tests. See `fonts-app-build.log` and `fonts-app-install.json`.
  The physical retest displayed readable button text with zero font-selection
  failures. Button actions and cooperative quit fail. Keyboard interaction and
  persistence remain unverified; the activation probe is built but untested.
- Flat apps have a normal visionOS Metal window with pointer/keyboard input.
  An app-owned x64 Windows demo provides click, text and saved-note checks. See
  [desktop use and validation](windows-desktop.md).
- Creating an external visionOS simulator failed with a CoreSimulator permission
  error. No simulator execution is claimed; host Metal checks did execute.
- StikDebug is installed. Opening Vision Pro **Settings → General → Remote
  Devices** exposed `_remotepairing-manual-pairing._tcp`. Upstream idevice_pair
  1.1.0 now sees the headset and validates its RemotePairing record. With explicit
  user approval, it sent the record to StikDebug; the device file listing confirms
  `Documents/pairingFile.plist` exists and the on-device parser accepts it. After
  LocalDevVPN installation, StikDebug connected through `10.7.0.1:49152` and
  confirmed the developer disk image is mounted. The first desktop request
  attached and verified Madeira's JIT arena; gameplay remains unverified.
- The user installed original Windlands. Its launcher selection was disabled
  because the Valve client was missing. The installed update exposes **Prepare
  Valve client** directly in the game's panel and selects the game after success.
  The Valve client and its dependent files are now confirmed installed.
  Actual gameplay remains unverified.

Build logs live in `/Volumes/XRDev/build/WineVisionVR/logs`. The original pipeline
logs are `app-build.log` and `app-guest-build.log`; the verified repair logs are
`crypto-refresh-prepare.log`, `crypto-refresh-ntdll.log`, `crypto-refresh-dxmt.log`,
`crypto-refresh-receipts.log` and `crypto-refresh-stage.log`. The latest signed
build is `wine-closure-app-build.log`; installation succeeded in
`wine-closure-app-install-retry.json` after an earlier 60-second timeout. The
installed bundle URL contains `3F5372B2-F4F7-4B9E-AFA1-06C5593441C8`.
`/Volumes/XRDev/build/WineVisionVR/wine-closure-built-app.json` records the latest
executable/framework hashes, receipt hashes and source identity.
`wine-closure-built-source.patch` and `wine-closure-built-source-changes.tar.gz`
preserve the uncommitted sources and local signing configuration. Earlier
`desktop-*`, `nls-*`, and `fonts-*` snapshots describe their respective older
builds. No changes have been pushed.

The latest guest rebuild adds the missing crypto provider and its transitive
Windows dependencies. Static imports, delay imports and export forwarders pass
across 93 binaries. This does not establish dynamic-loading or runtime success.
The resource receipt and stage now preserve `.drv` files such as `winspool.drv`.
See [dependency regression and retry behavior](windows-vr-local-testing.md#windows-dll-dependency-regression).
The external `retry-windlands.sh` restarts StikDebug and launches installed
Windlands with its remembered option through the normal scripted JIT flow.
The headset must be awake and unlocked for launches; leaving it charging allows
Mac build/log work to continue while physical checks wait.

Fresh preparation compared 33,084 source files against the preserved patched
tree, with no differences apart from the three generated source receipts.
The latest desktop source comparison is recorded under
`/Volumes/XRDev/build/WineVisionVR/desktop-refresh-source-comparison.json`.
Only named generated caches and hash-verified unchanged artifacts were preserved;
the earlier crypto change rebuilt ntdll; the desktop change rebuilt the modern
graphics closure while preserving the hash-verified unchanged native archives.
All build/stage receipts came from the normal tools. The prior runtime and staged
resources remain in `runtime-final2-before-desktop` and
`staged-resources-before-desktop` under `/Volumes/XRDev/build/WineVisionVR`.

With resources now verified, use the app-only driver for Xcode build/signing
retries. Do not start a second copy while it is running:

```sh
bash /Volumes/XRDev/build/WineVisionVR/build-app-only.sh
```

The full `build-app.sh` records the first-pass component/stage/app pipeline, with
`guest` starting at the guest build. Its modern graphics builder requires fresh
output paths, so do not rerun that stage over the completed artifacts. Changes
to fingerprinted native inputs require fresh source/profile preparation and
affected binary/receipt/resource rebuilds before another app link. The app-only
driver is the incremental app/Swift development path against an already verified
runtime stage; it does not perform that native refresh. It performs the same
final bundle/signing checks. Neither driver installs or launches the app. After
successful verification, installation uses the actual paired device identifier
from `xcrun devicectl list devices`:

```sh
xcrun devicectl device install app --device '<PAIRED-HEADSET-IDENTIFIER>' \
  '/Volumes/XRDev/build/WineVisionVR/artifacts/xcode-derived/Build/Products/Release-xros/WineVision VR.app'
```

## Repeat local correctness checks

Run from the repository root after sourcing the environment:

```sh
python3 windows-vr-tools/test_local.py \
  --build /Volumes/XRDev/build/WineVisionVR/checks \
  --dxmt-source /Volumes/XRDev/build/WineVisionVR/runtime-final2/dxmt \
  --opencomposite-source /Volumes/XRDev/build/WineVisionVR/artifacts/opencomposite-mingw/_deps/opencomposite-cross-src \
  --madeira-source /Volumes/XRDev/src/WineVisionVR/third-party/madeira
```

This creates fresh logs and `results.json` under `checks`; it does not launch
Wine or a game. The Madeira argument must be the clean pinned checkout, because
its regression applies patches in temporary copies. See
[local testing](windows-vr-local-testing.md) for optional simulator checks and
the scope of host/component results.

## First Windlands run and benchmark

Tilt Brush (Steam AppID **327140**) is also a requested target. Its verified
public metadata selects `tiltbrush.exe`, Windows 64-bit, SteamVR launch key `0`,
without additional arguments. The [Tilt Brush test profile](windows-vr-benchmark.md#tilt-brush-test-profile)
records the input, sketch-saving and performance checks. It has not been launched
on the headset; paired controller hardware still needs confirmation.

The selected title is **original Windlands, Steam AppID 428370**. After JIT
pairing is completed and the game is installed through the owning Steam account,
select **SteamVR / OpenVR · Windlands_Win_x64.exe**, launch option **5**, with its
default arguments. The launcher now prefers this route over the Oculus entry
using the same executable. The offline test verifies selection, not gameplay.

First verify both-eye rendering, head tracking, audio and controller/grappling
input. Preserve startup failures as compatibility evidence. Only after a
successful run should the same warmed, repeatable scene be used for a baseline
and candidate comparison. See the complete
[Windlands benchmark procedure](windows-vr-benchmark.md) for metadata, warmup,
scene selection and interpretation.

Use this machine's app identifier when copying logs; it differs from the default
identifier in the general benchmark document:

```sh
mkdir -p /Volumes/XRDev/build/WineVisionVR/benchmarks/windlands-baseline-01
cp windows-vr-tools/benchmark_run.example.json \
  /Volumes/XRDev/build/WineVisionVR/benchmarks/windlands-baseline-01/run.json
# Fill every run.json field with the actual run configuration before analysis.
xcrun devicectl device copy from \
  --device '<PAIRED-HEADSET-IDENTIFIER>' \
  --domain-type appDataContainer \
  --domain-identifier com.philipanderson.WineVisionVR \
  --source Documents/launcher-log.txt \
  --destination /Volumes/XRDev/build/WineVisionVR/benchmarks/windlands-baseline-01/launcher-log.txt
```

Retain `Documents/madeira-log.txt` as well for launch failures. The times below
are examples; replace them with the actual logged scene boundaries:

```sh
python3 windows-vr-tools/benchmark_frames.py summarize \
  /Volumes/XRDev/build/WineVisionVR/benchmarks/windlands-baseline-01/launcher-log.txt \
  --metadata /Volumes/XRDev/build/WineVisionVR/benchmarks/windlands-baseline-01/run.json \
  --start 14:20:00.000 --end 14:21:40.000 \
  --output /Volumes/XRDev/build/WineVisionVR/benchmarks/windlands-baseline-01/summary.json \
  --markdown /Volumes/XRDev/build/WineVisionVR/benchmarks/windlands-baseline-01/summary.md

python3 windows-vr-tools/benchmark_frames.py compare \
  /Volumes/XRDev/build/WineVisionVR/benchmarks/windlands-baseline-01/summary.json \
  /Volumes/XRDev/build/WineVisionVR/benchmarks/windlands-candidate-01/summary.json \
  --output /Volumes/XRDev/build/WineVisionVR/benchmarks/windlands-comparison.json \
  --markdown /Volumes/XRDev/build/WineVisionVR/benchmarks/windlands-comparison.md
```

Create the candidate capture and metadata independently before comparing. Fresh
image transfers and display reprojection are separate metrics. Host synthetic
timings, metadata lookup and a successful build cannot establish a headset FPS
gain; repeated matched physical runs are still required.

## Evening unattended checks and runtime repair

The actual visionOS 27 simulator passed all five probes: compositor, frame
ownership, GPU statistics, presentation shaders and audio policy. CoreSimulator
denied cache writes on the external volume, so the supported 4K device type was
created in Apple's normal device set. That temporary test device was shut down
and deleted after testing to recover internal storage; all reports remain on
XRDev. These probes do not execute Wine/FEX or prove game compatibility.

`overnight-tests/correctness/results.json` records 18 host/component checks
passing before the final PSAPI/alias changes. The later packaging run passes
45 tests, including the missing-PSAPI regression. The expanded source-repair
test runs the actual patched alias routines under ASan/UBSan in default,
explicit per-process, empty-value and legacy modes. The native Wine rebuild
compiled all 37 units successfully.

The main Windlands EXE, nine native Unity/VR DLL files and three Steam client
DLLs were inspected locally. With PSAPI included, their static imports resolve
against the packaged system farm and their installed sibling DLLs. Dynamic
library names, CLR assembly requirements and runtime behavior remain separate
checks. These owned binaries are outside the repository and source archives.

The alias repair backports upstream commits
[c4e3c121](https://github.com/willfaust/Madeira/commit/c4e3c121041088fa4aaa107762c9fe4ec1251b4e)
and [ce2e1f11](https://github.com/willfaust/Madeira/commit/ce2e1f11e69f510355f9ee4f1f1af9234b0e4cd7),
with their production-code regression, as patch `0009`. A comparison of 33,084
fresh profile source files found only the intended `virtual_ios.c` and host
alias-test differences. Unchanged caches and outputs were hash-verified; ntdll
and the modern graphics closure were rebuilt and normal receipts/stages
regenerated. The old runtime is `runtime-final2-before-process-alias`.
The previous installed PSAPI build is preserved in
`overnight-tests/psapi-installed-app.app`, with identity in `psapi-built-app.json`.

The October 15 alias repair build/install reports are
`overnight-tests/process-alias-app-build.log` and
`overnight-tests/process-alias-install.json`; installed bundle URL UUID is
`29077E63-2031-43F6-8886-47C9B50AAE77`. The external restart driver now force-quits
only WineVision before a diagnostic retry because a live Wine session can
ignore graceful termination. It should be used only for an intentional test
restart, since unsaved Windows work is discarded.


## OpenComposite writable session repair, October 16

`black-screen-oct16/madeira.log` captures the read-only `bin/applist.json` failure
and modal error text. `WindowsVRRuntimePlugin.mm` now copies OpenComposite into
the unique session folder and makes that folder and `bin` owner-writable; the
DLL bytes and source bundle stay unchanged. The OpenXR DLL mapping stays a
symlink. Existing session folders are never overwritten or reused.

`Tests/test_guest_runtime_mapping.py` compiles the production helper under
ASan/UBSan. A real read-only source fixture reproduces EACCES with the previous
symlink; the copied runtime accepts settings writes, preserves source/DLL bytes,
rejects overwrites and isolates sessions. It does not execute a Windows DLL.

The fresh profile comparison covers 33,084 identical runtime source files and
identifies only the changed host plugin input. Hash-verified unchanged Wine
outputs were preserved; modern DXMT and the app were rebuilt with normal
receipts. `runtime-final2-before-opencomposite-write` and
`black-screen-oct16/alias-installed-app.app` preserve the prior candidate.
Build and regression logs are in `black-screen-oct16/`. The new installed bundle
UUID is `AAA70450-F1E6-43EE-830C-22E4C0609776`; the physical retest reaches OpenXR session creation and first frame begin.
`repaired-unity-error.log` records a later access violation in the Unity player
(guest RIP `0x137348057`), with zero submitted game images.

A minimal mixed MSVC/MinGW compiler probe reproduces their different ordering
of the receiver and hidden result pointer for C++ virtual matrix returns.
Patch `0007-mingw-msvc-aggregate-return.patch` generates explicit outward
aggregate-return thunks while native internal/FnTable calls bypass that outward
vtable. The production-generator regression links an actual MSVC caller with
a MinGW implementation: unbridged calls report the wrong receiver; the bridge
preserves both matrix sizes, the receiver canary and qualified internal calls.
That test runs under macOS Wine/Rosetta, not headset FEX. The OpenComposite
package and full signed Release app build pass. All 45 Python packaging tests
pass. The device became unavailable before installation, so physical validation
of the ABI bridge remains pending. Identity/source snapshots are
`msabi-built-app.json` and `msabi-built-source-changes.tar.gz`; build reports
are `black-screen-oct16/msabi-*.log`.

The app UI now offers a confirmed force-quit control after an exit request or
when a restart is required. Wine/FEX remains limited to one session per process;
force quitting discards unsaved guest work. This UI change is in the verified build awaiting installation.


### ABI cleanup follow-up

The initial bridge installed as `A01E57A5-0047-43D0-882E-3B0B637E9480` got past
the prior Unity matrix-pointer fault but crashed during OpenComposite's initial
shutdown. Its return address `vrclient_x64.dll + 0x24847` resolves to
`CVRSystem_012::Delete()`. The generated outward table includes OpenVR API
slots, while `delete this` dispatches the derived destructor through additional
native slots. The corrected generator records the native table and restores it
before deletion. The expanded host regression destroys the bridged object
through its secondary base and confirms complete destruction exactly once.
The corrected signed build is installed as
`AD4E2E27-53B7-404A-A898-23B3E857E359`. The foreground StikDebug launch timed
out and `devicectl device info lockState` reports `passcodeRequired: true`;
there is no corrected-build guest run yet. Source/binary identity is in
`msabi-cleanup-built-app.json`. The user confirmed the unchanged force-quit
UI closes the app after End session and confirmation.

The external retry driver now refreshes the existing Xcode pairing if process
discovery fails, then retries once. It does not unpair the headset or replace
StikDebug's pairing record. This recovered the October 16 stale connection while
the headset was already awake.


The corrected cleanup candidate subsequently launched with JIT and started
Windlands. OpenXR target queries and instance creation returned
`XR_ERROR_RUNTIME_FAILURE (-2)`, with zero submitted VR images. The app process
remained present, but its logs stopped while the headset later reported
`passcodeRequired: true`; foreground restoration timed out. This run does not
establish that the cleanup path is repaired on-device, nor prove why the targets
became unavailable. A continuously awake/foreground retest is required before
making another runtime change. Logs use `black-screen-oct16/msabi-cleanup-*`.


### Continuously awake retest and session-stop repair

With the headset continuously worn, stereo targets remain available and the
cleanup candidate reaches OpenComposite's switch to the game's real graphics
binding. It requests session exit with a startup frame begun; the runtime
rejects `xrEndSession` with `XR_ERROR_CALL_ORDER_INVALID`, captured in
`active-opencomposite.log`. Native tracking continues at that point and no
matrix-pointer/cleanup crash is captured. Zero VR images are submitted.

The [OpenXR session-end contract](https://registry.khronos.org/OpenXR/specs/1.0/man/html/xrEndSession.html)
allows ending a running STOPPING session without finishing that frame. The
repair discards only the outstanding frame token, wakes frame waiters and queues
IDLE before EXITING/READY; it does not invent a rendered/submitted frame. Early
ends return `XR_ERROR_SESSION_NOT_STOPPING` with state unchanged. The actual
production transition regression passes ASan/UBSan, including restart. The
x64 OpenXR DLL rebuild passes; the full signed app build and bundle checks pass. It is installed as
`8B0052BC-EAE7-4928-A1FC-11E0D26AC661`, with current identity/source snapshots
in `session-stop-built-app.json` and `session-stop-built-source-changes.tar.gz`.
Physical retest is pending.


### Producer-format and Unity allocation compatibility

The installed session-stop candidate completes the startup-session shutdown,
queues IDLE/EXITING, creates a fresh session with the game's graphics binding,
and reaches swapchain creation. It then rejects the requested format with -26
(`XR_ERROR_SWAPCHAIN_FORMAT_UNSUPPORTED`); there are still zero VR images.
`session-stop-live-opencomposite.log` captures both successful transitions and
that next blocker.

The renderer now publishes RGBA8 sRGB game targets independently of the BGRA
display. The existing spatial pass performs the conversion without an added
pass; snapshots keep the source format. Producer extents align upward to 64
pixels after scale (1888 becomes 1920), allowing Unity's 3840-wide stereo
allocation while retaining strict eye-region checks. OpenComposite normally
copies the full stereo allocation and applies the submitted bounds in projection
subrects; absence of its creation-time Bounds log does not imply the game
submitted no bounds. Actual headset cropping remains to be checked.

Parallel read-only source/GPU reviews found no blocker. The complete host GPU
batch passes 8192 compared pixels with zero color/depth difference, plus queue,
lease, geometry, statistics and sanitizer checks. The fresh-profile audit finds
33084 identical runtime source files and only the compositor bridge integration
input changed. Normal receipt-backed DXMT/app rebuild is in progress; no frame
rate or gameplay claim is made.


### RGBA physical retest and input synchronization blocker

The RGBA/aligned candidate installed as
`03B8D995-37B9-43E6-862A-4EC2E65AFD7E` completes session recreation and allocates
both 3840x1792 swapchains. It then aborts `xrSyncActions` with
`XR_ERROR_VALIDATION_FAILURE`: OpenComposite activates its internal action set
once for the left hand and once for the right, but the runtime rejects any
repeated action-set handle. The user confirms the view remains blank and native
counters show zero game frames. The producer change has not established
successful cropping/presentation because input initialization aborts first.
Evidence: `rgba-live-opencomposite.log`, `rgba-live-launcher.log`, identity
`rgba-producer-built-app.json`. A targeted multi-subaction synchronization
repair/test is in progress; no gameplay or FPS improvement is claimed.


### Multi-subaction input repair

The OpenXR action contract allows the same action set to appear with distinct
left/right subaction paths. `SyncActions` now unions a per-set hand mask, merges
exact duplicate pairs idempotently and handles `XR_NULL_PATH` as a wildcard in
either order. Invalid handles, attachment or undeclared paths fail before active
session state changes. Snapshot/pose queries honor the union; explicitly requested
haptics remain isolated to their requested hand. The expanded production-code
input regression passes ASan/UBSan, including controller-read failure and invalid
second-entry transaction checks. Only the OpenXR DLL source and its input test
change for this repair. Fresh baseline8/profile/app build is in progress; the
last physical result remains blank with zero submitted game frames.


### Action-lifetime build and evidence (preceding candidate)

The preceding input-sync candidate installed as
`63A4E617-C1E3-49F9-803B-2531A0010EF0` passed the earlier synchronization blocker
but retained invalid action handles after temporary action-set destruction.
The action-lifetime repair removes child action handles and suggested bindings
when their set is destroyed; independently owned action spaces remain valid until
their own destruction. It adds bounded target/frame rejection diagnostics without
relaxing the existing geometry or validation guards.

Actual completed ASan/UBSan production-code lifetime and input regressions passed.
Raw logs are `black-screen-oct16/action-lifetime-test.log` and
`action-lifetime-input-test.log`; `action-lifetime-test-result.json` records their
commands, successful exits and tested source hashes. These host tests do not run
Windows or a headset game.

The real x64 OpenXR DLL rebuilt successfully. Fresh baseline9/profile preparation
compared 33,084 files with no source differences, with only the OpenXR host
integration fingerprint changed and the DXMT source tree unchanged. Prior native
and guest outputs were hash-verified before preservation. Normal DXMT closure
rebuild, native/guest receipts and resource staging completed; Release Xcode build,
94-binary PE import closure, graphics validation, strict signing and provisioning
checks all passed. The packaged OpenXR DLL matches the built DLL at SHA256
`0f99e7631a389baec1f14074ef7b6c78da1b2fbddd7963947dad78367021a015`.

Evidence is under `/Volumes/XRDev/build/WineVisionVR/black-screen-oct16`:
`action-lifetime-openxr-build.log`, `action-lifetime-source-comparison.json`,
`action-lifetime-restored-outputs.json` and `action-lifetime-app-build.log`.
Current source/binary identity is recorded in
`/Volumes/XRDev/build/WineVisionVR/action-lifetime-built-app.json`; its source
patch and archive preserve the build's uncommitted source state. The preceding
profile remains in `runtime-final2-before-action-lifetime` and signed app in
`black-screen-oct16/input-sync-installed-app.app`. Installation of the current
candidate succeeded; actual headset image submission remains pending, with zero
game images verified so far.


### Bounds-binding build and built-in VR scene

The action-lifetime physical run passed input restart but rejected a negative
height rectangle: offset (0, 1792), extent (1920, -1792), from a 3840x1792 stereo
allocation. The OpenComposite D3D11 adapter now applies valid inverted bounds in
its crop/flip shader and submits positive eye-local rectangles. The OpenXR binding
repair checks live-session attachment rather than retaining the destroyed
session's state. CPU sanitizer regressions and a 32-pixel host GPU crop/flip check
passed; these are host component checks, not a headset gameplay result.

The genuine OpenComposite and OpenXR DLLs were rebuilt, followed by fresh
baseline10/profile preparation, a 33,084-file equivalence audit, verified output
preservation, normal DXMT closure/receipts and resource staging. The final signed
Release app includes **Built-in VR test scene**, an app-owned x64 executable of
about 105 KB. It needs no Steam installation or purchased game. Its host test
covers the production vertex/bounds math under ASan/UBSan; compilation and import
inspection passed. That scope does not establish complete Windows/GPU rendering.
The scene uses an approximate fixed 64 mm eye separation.

The normal mode uses two separate eye textures. The developer launch options are
`--vr-smoke-test` for normal mode and
`--vr-smoke-test --inverted-bounds` for a shared stereo texture with inverted
vertical bounds, exercising the Windlands crop/flip path. These arguments belong
after the `devicectl process launch` command's `--` separator. The normal launcher
also provides the built-in scene selection and **Play** action.

Build/audit logs use `black-screen-oct16/bounds-binding-*`; scene host evidence is
`black-screen-oct16/vr-smoke-build-result.json` and `vr-smoke-imports.json`.
`/Volumes/XRDev/build/WineVisionVR/bounds-binding-built-app.json` records the signed
candidate identity. It installed as `D1F2F513-F53D-4BE1-AA00-4CD2A3437CB4`.
The preceding app/profile remain in `action-lifetime-installed-app.app` under the
log directory and `runtime-final2-before-bounds-binding`. Physical rendering is
pending, with zero confirmed game images and no VR performance claim.


### Current scene-discovery build: normal VR scene verified on headset

The normal built-in VR scene now works on the physical Vision Pro, confirmed by
the user. The scene needed a private-prefix OpenXR registry registration: its
Windows token has high integrity (`0x3000`), so the loader ignores
`XR_RUNTIME_JSON` even when present. The scene-only helper temporarily registers
the runtime in its private prefix and restores the previous registry type and
bytes. A real host registry regression passed, including prior `REG_BINARY`
values. The baseline10 bounds-binding runtime and current DXMT paths are unchanged.

`black-screen-oct16/vr-smoke-discovery-late-scene.log` records repeated successful
submissions. The accompanying `vr-smoke-discovery-late-launcher.log` reaches 4,049
submitted guest frames with `hasFrame=true` and `matchesTarget=true`: each
1920x1792 RGBA producer image presents to an 1888x1792 BGRA display target.
Captured short windows report approximately 88–89.8 transfer frames per second
with a 90 Hz display, and zero GPU command failures. These are measurements of
this tiny scene during the captured run, not Windlands performance, a before/after
speedup or a long thermal/sustained benchmark.

The signed app installed as `6A6FCEDB-1D24-456C-AA1A-1D0B2A062296`; its identity
is recorded in `/Volumes/XRDev/build/WineVisionVR/vr-smoke-discovery-built-app.json`.
The normal scene establishes real Windows/Wine/FEX, OpenVR/OpenXR and headset
presentation execution. The inverted-bounds mode subsequently passed its physical retest. Windlands
gameplay was verified in the later lifecycle candidate described below.


### Windlands reaches menu and introduction; presentation interruption

A scoped launch trial with `OPENSSL_ia32cap=0` reached the actual Windlands menu,
controller selection and introduction. The user has now confirmed both Sense
controllers are connected. The launch trial is evidence of progress through these
screens, not proof of sustained gameplay or that the effective proprietary
Steam child environment has been independently inspected.

`black-screen-oct16/windlands-software-crypto-late-launcher.log` and the related
working/final logs capture 5,093 submitted guest frames, `hasFrame=true`,
`matchesTarget=true`, approximately 88–89 new/transfer frames per second in the
latest short windows at a 90 Hz display, and zero GPU command failures. This is
short-run Windlands menu/introduction evidence; no comparative speedup, long
thermal benchmark or full gameplay claim follows from it.

At 21:52:43 the immersive layer renderer became invalidated and its render task
ended. Captured Wine/wineserver and native CPU activity continued for more than
62 seconds afterward, without the audited fatal markers. The cause is unconfirmed:
the logs establish a presentation lifecycle interruption, not a demonstrated
new game crash or process termination. See
`black-screen-oct16/windlands-presentation-invalidation-audit.json` and
`openssl-cap-environment-audit.json` for the evidence and limits.

The installed identity remains `6A6FCEDB-1D24-456C-AA1A-1D0B2A062296` at this
recording. The subsequent app-only lifecycle candidate and its physical result are recorded
below. Baseline10 runtime/source paths remain unchanged.


### Current Windlands lifecycle candidate: level and controls verified

The signed candidate installed as `064F66F7-17BE-4C93-A404-E58032067C17` saves
`OPENSSL_ia32cap=0` only for Windlands and adds presentation lifecycle diagnostics.
Its identity/source snapshot is
`/Volumes/XRDev/build/WineVisionVR/windlands-lifecycle-built-app.json`.
An ordinary retry used the saved launch setting without an injected CoreDevice
environment. The user confirmed “Level starts and controls work” and then
“seems to be working”. This establishes actual Windlands gameplay and controller
operation in this run.

`black-screen-oct16/windlands-lifecycle-followup-launcher.log` captures both
controller roles connected and tracked, a right-stick value of -1.0, 1,834
submitted guest frames and zero GPU command failures. Short windows report
47.1–48.6 new frames per second with an 89–89.6 Hz display. These samples describe
this run; long-session stability, thermal behavior and an A/B speedup remain
unverified. The baseline10 runtime and current DXMT build/stage paths are unchanged.
Both normal and inverted built-in VR scenes have passed physical testing.
