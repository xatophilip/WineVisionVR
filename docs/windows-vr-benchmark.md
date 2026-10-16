# Reproducible headset performance checks

Use `windows-vr-tools/benchmark_frames.py` to summarize captured launcher logs
and compare baseline/candidate runs. It uses only Python's standard library and
does not install anything or launch a game. **Windlands** and **Tilt Brush** are
the requested test titles; both still need verified headset compatibility and
performance runs.
Do not substitute historical Moss or Moss: Book II results for a Windlands baseline.

## Windlands launch setup

Use **original Windlands, Steam AppID 428370**. Its
[official Steam listing](https://store.steampowered.com/app/428370/Windlands/)
lists DirectX 11 and SteamVR/Oculus PC for Windows; the macOS build does not
support VR. The existing Steam game profile selects Direct3D 11 through Wine/FEX,
with OpenComposite supplying the SteamVR/OpenVR route into the native OpenXR
bridge. That is the intended route to test, not proof of compatibility.

An anonymous request to Valve's public product-info service on October 15, 2026
returned the following launch entries. See the
[captured metadata fixture](../visionos-windows-vr/Tests/Contracts/fixtures/windlands-public-appinfo.json),
change number **39716201**, public build **24798177**. The request obtained no
user credentials and downloaded no game files.

| Route | Steam launch key | Windows executable | Publisher launch arguments |
|---|---:|---|---|
| **SteamVR / OpenVR — select this** | **5** | `Windlands_Win_x64.exe` | None |
| Oculus PC | 4 | `Windlands_Win_x64.exe` | `-vrmode Oculus -oculus` |
| Desktop, VR disabled | 1 | `Windlands_Win_x64.exe` | `-vrmode None -desktop` |

Valve declares all three entries Windows **64-bit**; the separate desktop key 0
is x86. This is publisher metadata, not a PE-header inspection: the actual game
binary has not been downloaded or checked. The 64-bit Windows depot is 428372,
and its installed build ID must be recorded from the completed installation,
since public metadata can change.

In WineVision VR's **Steam library**, sign in with the owning account, choose
**Prepare Valve client**, and download Windlands's Windows build to the headset.
After installation, choose **SteamVR / OpenVR · Windlands_Win_x64.exe** from its
launch menu, then **Launch game**. The launcher now prefers SteamVR over Oculus
when both use the same installed executable; other VR choices show their launch
arguments so they are distinguishable. Keep the SteamVR entry's default
arguments initially. Do not select the desktop entry, which explicitly disables
VR, or the Oculus entry for this OpenComposite test.

JIT must be enabled for that session. The current user has deferred JIT pairing,
so the first physical Windlands run remains pending. Once available, check the
main menu, head tracking, both-eye rendering, sound and grappling/controller
inputs before establishing a fixed-route FPS baseline. A launch failure should
retain `launcher-log.txt` and `madeira-log.txt`; do not treat it as a zero-FPS
performance comparison. Steam launch selection is covered by the offline test
below, but neither it nor the metadata lookup tests actual game execution.

## Tilt Brush test profile

**Tilt Brush, Steam AppID 327140**, is an additional requested VR target. Its
[official listing](https://store.steampowered.com/app/327140/Tilt_Brush/) specifies
SteamVR and tracked-controller support. Google's
[published input actions](https://github.com/googlevr/tilt-brush/blob/master/actions.json)
include mandatory pose and analog-trigger actions, with grip, menu, directional
and button inputs used by the controller bindings.

An anonymous Valve product-info request on October 15, 2026 returned change
**39795199**, `vrsupport=openvr`, and this single Windows launch entry:

| Field | Test configuration |
|---|---|
| Steam launch key | `0` |
| Executable | `tiltbrush.exe` |
| Declared architecture | Windows 64-bit |
| Launch type / publisher arguments | `vr` / none |
| Install directory | `Tilt Brush` |
| Initial graphics / render scale | Existing D3D11 Steam profile / 100% |

The raw public response is preserved locally at
`/Volumes/XRDev/build/WineVisionVR/tilt-brush-metadata/tilt-brush-appinfo.json`.
Metadata was fetched without account credentials or game downloads; the installed
binary, graphics behavior and compatibility have not been checked. This is a
test configuration, not a supported-game declaration. The existing SteamVR
launch selector already covers this entry; no app rebuild is required merely
to select it from the Steam library after installation.

After JIT pairing, install the Windows version through the owning Steam account
and select its SteamVR/OpenVR entry. Before performance capture, verify both
tracked controllers, brush-tip alignment, trigger-controlled stroke creation,
palette/brush selection, grip actions and haptics where available. Confirm that
a sketch can be saved, closed and reopened. The current controller adapter reads
paired spatial accessories/controllers and does not supply bare-hand drawing
controls; the user's controller hardware is not yet confirmed.

Use a saved, repeatable sketch and the same strokes/viewpoint for each run.
Measure an empty canvas separately from a dense sketch with animated or
transparent brushes. Keep Tilt Brush run metadata and results separate from
Windlands, with the actual installed build, binary identity and eye dimensions.
Preserve both launcher and Madeira logs if it fails to launch or accept input.
JIT pairing remains deferred, and no Tilt Brush execution or FPS is claimed.

## Capture a controlled run

1. Build/install the baseline with `WVRDiagnostics=true` and
   `WVRFrameCapture=false` in the app's actual `Info.plist`. Diagnostics otherwise
   produce no performance file; frame capture adds expensive texture readbacks.
   Use the same optimized build configuration and instrumentation for both runs.
2. Copy `windows-vr-tools/benchmark_run.example.json` to a run-specific JSON file
   and fill every field, including actual eye dimensions, game version, profile,
   settings and installed binary identity. The source currently uses uniform eye
   textures; do not infer a panel-resolution percentage from those dimensions.
   Record the commit and installed executable SHA-256 as `build_id`; uncommitted
   edits require a saved diff as part of the run evidence too.
3. Enable JIT, launch Windlands on the headset, and first establish that rendering,
   tracking, input and audio work. Choose a repeatable save/checkpoint and route.
   Keep settings, eye dimensions and headset conditions fixed. Record a cold-start
   run separately from warmed shader/pipeline caches. Do not compare the two.
4. For sustained measurement, allow startup/shader compilation to settle, then
   record at least 90 seconds in the same scene. Note the scene start/end in the
   launcher's `HH:mm:ss.SSS` clock; the tool discards a 10-second warmup by default
   and requires at least 60 seconds of complete subsequent reporting windows.
   Keep menus, loading, taking off the headset and suspensions outside that range.
   Record visible stutter, audio issues and thermal progression separately.
5. Copy the log immediately after each run. It is bounded to 512 KiB and can rotate;
   it can also contain earlier sessions. Preserve a distinct file for each run.

### Build with explicit diagnostics

After preparing the runtime and staged resources as described in the
[build instructions](../windows-vr-tools/README.md), select the benchmark overlay
instead of `project.yml` for project generation. It includes the same source
project and changes only the two diagnostic plist properties:

```sh
export AVPPLAY_RUNTIME_SOURCE=/absolute/path/to/prepared/runtime-source
xcodegen generate --spec visionos-windows-vr/project.benchmark.yml
xcodebuild -project visionos-windows-vr/VisionOSWindowsVR.xcodeproj \
  -scheme VisionOSWindowsVR -configuration Release \
  -destination 'generic/platform=visionOS' \
  -derivedDataPath /absolute/path/to/benchmark-derived-data \
  DEVELOPMENT_TEAM='<YOUR-TEAM-ID>' -allowProvisioningUpdates build
```

Keep other profile-specific environment/build settings required by your existing
build, such as `AVPPLAY_DXMT_LINK_FLAG`, unchanged. The overlay generates the usual
`VisionOSWindowsVR.xcodeproj` and scheme. Regenerate from `project.yml` to return
to the normal diagnostics-off build. The separate preserved-runtime
`project.prebuilt.yml` currently enables diagnostics in both configurations;
Release alone does not disable them.

The overlay uses literal YAML **booleans**, which XcodeGen writes as plist
booleans. Do not replace them with quoted strings or blindly use an
`INFOPLIST_KEY_WVRDiagnostics=YES` build-setting string: Swift reads these keys
using `as? Bool`. Verify the final built app before installation:

```sh
python3 - '/absolute/path/to/benchmark-derived-data/Build/Products/Release-xros/WineVision VR.app/Info.plist' <<'PY'
import plistlib, sys
with open(sys.argv[1], 'rb') as stream:
    info = plistlib.load(stream)
assert info.get('WVRDiagnostics') is True, 'WVRDiagnostics must be a plist boolean true'
assert info.get('WVRFrameCapture') is False, 'WVRFrameCapture must be a plist boolean false'
print('Benchmark diagnostics enabled; full-frame captures disabled')
PY
```

These diagnostics are **not free**: they enable GPU completion timing callbacks,
bounded bridge tracing, launcher file writes, startup monitoring and periodic
compositor/controller reporting. The current code has no separate lightweight
benchmark mode. Compare builds with this identical instrumentation enabled, and
do a separate visual/stability smoke test with diagnostics off before treating
results as representative of an ordinary release. Frame capture remains disabled
because it adds a separate full-frame GPU readback cost. Metadata records both
switches so the comparison refuses incompatible runs.

Run the following from the repository root, replacing the device identifier and
output paths. `--device` must name the headset used for this run. The bundle ID is
the project's existing app identifier.

```sh
mkdir -p .build-benchmarks/windlands-baseline-01
xcrun devicectl device copy from \
  --device '<PAIRED-HEADSET-IDENTIFIER>' \
  --domain-type appDataContainer \
  --domain-identifier org.avpplay.visionos-windows-vr \
  --source Documents/launcher-log.txt \
  --destination .build-benchmarks/windlands-baseline-01/launcher-log.txt
```

Retain `Documents/madeira-log.txt` too when diagnosing startup/game failures.
Device availability and successful file copying are separate from successful
game rendering. A blank or non-starting game is a compatibility failure, not an
FPS result.

## Summarize and compare

The clock values below are examples; replace them with the actual scene interval.
Use `--warmup-seconds 0` only if the selected start is already fully warmed up.
The first log report is always excluded because its window start is unknown.
Only complete windows starting after the warmup boundary are retained.

```sh
python3 windows-vr-tools/benchmark_frames.py summarize \
  .build-benchmarks/windlands-baseline-01/launcher-log.txt \
  --metadata .build-benchmarks/windlands-baseline-01/run.json \
  --start 14:20:00.000 --end 14:21:40.000 \
  --output .build-benchmarks/windlands-baseline-01/summary.json \
  --markdown .build-benchmarks/windlands-baseline-01/summary.md
```

Repeat with the candidate build and a separate `run_id`, log and metadata file.
Change only the optimization under test. Then compare:

```sh
python3 windows-vr-tools/benchmark_frames.py compare \
  .build-benchmarks/windlands-baseline-01/summary.json \
  .build-benchmarks/windlands-candidate-01/summary.json \
  --output .build-benchmarks/windlands-comparison.json \
  --markdown .build-benchmarks/windlands-comparison.md
```

Both commands save reports even when comparison is blocked. Exit status **0**
means the report has no comparison blockers; **2** means an inconclusive report
or a command/input error (inspect the output and stderr). A comparable report is
not a performance pass. Repeat in **A/B/B/A** order to check repeatability and
thermal/order effects. Retain all raw logs, source/build identity, run metadata
and observations; do not cherry-pick a faster scene window after seeing results.

Comparison refuses to endorse different games, scene routes, resolution,
settings, cache/thermal start, devices or OS versions. It also flags missing
metadata, short runs, durations differing by more than 10%, diagnostic frame
capture, counter resets, GPU errors, renderer lifecycle transitions, log gaps
over 10 seconds and reuse of the same capture. Gaps are retained in the report,
so removing a stalled interval cannot silently improve its statistics.

## What the metrics mean

| Report metric | Meaning and limits |
|---|---|
| `fresh_transfer_fps` | Newly encoded stereo snapshot copies per reporting window. Tracks fresh-image transfers separately from reprojection; it does not prove GPU completion, simulation rate or delivery of every guest submission. |
| `display_submission_fps` | Presentation command-buffer submissions. Cached-frame rotational reprojection and clears are included. It does not prove new game frames or completed display scanout. |
| `reported_window_median_transfer_interval_ms` | Median of fresh-transfer intervals reported within each window. |
| `reported_window_p95_transfer_interval_ms` | The runtime's reported p95 for each window. The report summarizes those window values; it does not reconstruct an overall per-frame p95 or p99. |
| `mean_cpu_encode_ms` | Mean CPU time in the native presentation encoding path; not total game or process CPU time. |
| `snapshot_read_write_mib_s` | Estimated copy read/write bytes from dimensions, not measured memory-bus bandwidth. |
| `*_window_mean_gpu_ms`, `*_window_mean_queue_ms` | Recent per-command-buffer execution/queue means by guest, snapshot and presentation stage; not per-frame totals or utilization. |

The JSON retains selected records, line numbers, selection boundaries, the log
SHA-256 and operator-supplied metadata. The Markdown tables summarize **windows**
using their unweighted mean/median/range, not inferred individual frame samples.
The runtime caps stored transfer intervals at 512 per window, rounds FPS values
to one decimal place, and does not report frame p99. GPU window means have no
sample counts: they cannot be pooled or summed into GPU frame time; zero may
mean no timed command buffers. GPU means before the `| window` section are
cumulative and deliberately excluded from comparisons.

There is no generated-frame counter because scene-motion frame generation is
not implemented. None of these metrics establish latency, thermal stability,
memory usage, audio quality or a new game's compatibility. Observe those on the
headset and preserve their separate evidence.

## Tune render quality after compatibility is established

The launcher's **Spatial render scale** defaults to **100%** and supports
50–100% in 5% steps. It changes the guest eye texture dimensions; the compositor
still presents at its full drawable size, using bilinear upscaling. Apply a new
value before launching a fresh game session and record the actual eye dimensions
from that run. Desktop `MADEIRA_SCREEN_W` / `MADEIRA_SCREEN_H` settings do not
control these VR eye textures.

Start with the same warmed Windlands scene at **100%, 85%, then 75%**. The latter
two have approximately 72% and 56% of the original pixel area, respectively,
before dimension rounding. This reduces rendering work at a visual-quality
cost; it is not a promised FPS gain. Record image readability, grappling/input
response, stutter and fresh-transfer rates for each setting, and repeat the
100% run to check for thermal or order effects.

Summarize these captures independently: `compare` intentionally rejects
different resolutions/settings as a controlled code-performance comparison.
Choose an acceptable quality setting, then hold it fixed for an A/B/B/A test of
any source optimization. The current app does not expose guest foveated
rendering, temporal MetalFX upscaling, generated frames or a refresh-rate knob.
Those are not existing switches to enable for this test.

## Offline regression checks

```sh
python3 -m unittest discover -s windows-vr-tools/tests -p test_benchmark_frames.py -v
python3 visionos-windows-vr/Tests/Contracts/test_steam_launch_selection.py
```

The synthetic fixtures cover separate fresh/display rates, warmup boundaries,
midnight rollover, missing/invalid metrics, zero/absent interval samples, stalls,
GPU errors/resets, comparison mismatches and the CLI's saved artifacts. Their
numbers are test input, not a measured headset result. For native CPU/Metal
correctness, also use `windows-vr-tools/test_fps_batch.py` with full Xcode selected;
see [the FPS batch](windows-vr-fps-batch.md) for its scope.
