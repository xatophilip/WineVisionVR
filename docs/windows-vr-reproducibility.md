# Rebuild and run handoff — 17 October 2026

## What is saved, and what has been verified

The functional source changes, dependency pins, integration patches, Wine DLL
module list, Steam host patch, build/stage tools, diagnostics and tests are
checked in on `codex/local-build-and-benchmarks` in
<https://github.com/xatophilip/WineVisionVR>. Windlands and Job Simulator were
confirmed working on an M2 Vision Pro, visionOS 27.2, with PS VR2 Sense controllers.
See [current game results](windows-vr-local-testing.md#current-game-status--17-october-2026).

**A fresh clone has not yet been shown to recreate the exact working native
runtime.** The tested app is a composite: current Swift frontend, three preserved
known-working native frameworks, six newly built ARM64EC Wine DLLs and a rebuilt
x64 Steam host. Its receipts distinguish inherited binaries from newly built
resources. Do not describe its successful gameplay as validation of a fresh full
source rebuild, or of the experimental 32-bit build.

The audit matched all 70 frontend/package/ABI source files recorded in the tested
app's assembly manifest against the committed checkout, with no differences.
The six DLLs (`dwmapi`, `wsock32`, `avrt`, `vcruntime140`, `msvcp140`, `mmdevapi`)
are in `build_wine_guest_resources.sh` and enforced by `stage_resources.py`.
`build_steam_dock.sh` applies the tracked bounded-launch-arguments patch, and
`assemble_runtime.sh` invokes it. These fixes do not depend on an uncommitted
modification to a downloaded source checkout.

The exact XRDev assembly scripts are preserved as source in
[`windows-vr-tools/local-checkpoints/2026-10-17`](../windows-vr-tools/local-checkpoints/2026-10-17/README.md).
They are historical, machine-specific recipes, not a portable one-command build.
They require their external input snapshots and perform signing/mutations when
run; their README and manifest describe those inputs. Do not run them merely to
inspect the checkpoint.

For a change-by-change explanation and exact dependency pins, see
[what this fork added](windows-vr-fork-changes.md). Key retained binary/receipt
hashes are recorded in [the runtime inventory](windows-vr-runtime-inventory.json).

## Required inputs outside Git

| Input | How to obtain or regenerate it |
|---|---|
| Full Xcode 27, visionOS 27 SDK and Metal Toolchain | Install Xcode; select its developer directory. Use `xcodebuild -downloadComponent MetalToolchain` if absent. |
| Git, Python 3, CMake 3.28+, Ninja, Meson, XcodeGen, Bison 3 | Install on the build Mac; place Bison 3 ahead of Apple's Bison on `PATH`. |
| Pinned LLVM-MinGW 20260421 UCRT macOS universal | Download/extract the release linked in the [tooling recipe](../windows-vr-tools/README.md#assembly-order); verify its documented SHA-256. |
| Madeira, Wine, FEX, DXMT, OpenXR/OpenVR/OpenComposite, FreeType sources | Acquire with `fetch_sources.py`; `sources.lock.json` and recursive submodule gitlinks select revisions. Their licenses are retained/staged. |
| Clean Wine prefix archive and provenance | Generate with the pinned host Wine and `create_prefix_snapshot.sh`, as below. Do not copy a used Steam/game prefix. |
| Apple signing identity and development profile | Use your own Xcode team, certificate/private key and paired headset. The profile must allow debugging/JIT and the increased-memory entitlement. |
| JIT helper and pairing | Install/prepare StikDebug and LocalDevVPN on your headset; complete your own RemotePairing. |
| Owned games | Sign into your own Steam account in WineVision; prepare the Valve client and download games there. |
| Exact previously working native binaries | Retained on XRDev for the checkpoint route below. A clean full source build is the alternative, but equivalent headset behavior still needs testing. |

Generated apps/frameworks/DLLs, source caches, toolchains, Xcode projects and
build logs are not committed. Neither are Steam credentials, pairing records,
private signing keys/profiles or game files. Machine-local `.local*` signing
specs are ignored; the example below recreates their configuration without
another developer's identity.

## Clean source build using the modern profile

This is the tracked full-build route. It may need build repairs and headset
validation before it is equivalent to the retained working package. Allow ample
external storage and time for LLVM, Wine and DXMT compilation. Use fresh source
and build paths; do not overwrite the working XRDev profile or resource stage.

```sh
git clone --branch codex/local-build-and-benchmarks \
  https://github.com/xatophilip/WineVisionVR.git
cd WineVisionVR
export DEVELOPER_DIR="$(xcode-select -p)"
export WVR_WORK="/absolute/path/to/new-winevision-build"
export AVPPLAY_SOURCE_CACHE_ROOT="$WVR_WORK/source-cache"
export AVPPLAY_LLVM_MINGW_ROOT="/absolute/path/to/llvm-mingw-20260421-ucrt-macos-universal"
export AVPPLAY_MADEIRA_SOURCE_ROOT="$AVPPLAY_SOURCE_CACHE_ROOT/madeira"
export AVPPLAY_DEVELOPMENT_TEAM="YOUR_TEAM_ID"
export AVPPLAY_BUILD_JOBS=4
python3 windows-vr-tools/fetch_sources.py \
  --cache-root "$AVPPLAY_SOURCE_CACHE_ROOT" --include-d3d12-experimental
```

Create the clean prefix once. The x86-64 host runs through Rosetta on Apple
silicon; install Apple's Rosetta if it is not available. This stage executes
Wine to initialize a clean prefix, not a game:

```sh
AVPPLAY_PREFIX_BUILD_ROOT="$WVR_WORK/prefix-tools-arm64" \
  AVPPLAY_PREFIX_HOST_ARCH=arm64 AVPPLAY_PREFIX_TOOLS_ONLY=1 \
  bash windows-vr-tools/build_prefix_wine_host.sh
export AVPPLAY_PREFIX_BUILD_ROOT="$WVR_WORK/prefix-host-x86_64"
export AVPPLAY_PREFIX_NATIVE_WINE_TOOLS="$WVR_WORK/prefix-tools-arm64/build"
AVPPLAY_PREFIX_HOST_ARCH=x86_64 AVPPLAY_PREFIX_TOOLS_ONLY=0 \
  bash windows-vr-tools/build_prefix_wine_host.sh
export AVPPLAY_PREFIX_WINE_BUILD_ROOT="$AVPPLAY_PREFIX_BUILD_ROOT/build"
export AVPPLAY_PREFIX_WINE_BIN="$AVPPLAY_PREFIX_WINE_BUILD_ROOT/loader/wine"
export AVPPLAY_PREFIX_WINEBOOT_BIN="$AVPPLAY_PREFIX_WINE_BUILD_ROOT/wineboot"
export AVPPLAY_PREFIX_OUTPUT_ROOT="$AVPPLAY_PREFIX_BUILD_ROOT/artifact"
WINEDLLOVERRIDES="winemac.drv,mscoree,mshtml=" \
  bash windows-vr-tools/create_prefix_snapshot.sh
export AVPPLAY_WINE_PREFIX_TEMPLATE="$AVPPLAY_PREFIX_OUTPUT_ROOT/prefix-template.tar.gz"
export AVPPLAY_WINE_PREFIX_PROVENANCE="$AVPPLAY_PREFIX_OUTPUT_ROOT/prefix-template-provenance.json"
```

Choose the **modern** graphics profile explicitly. The ordinary assembler defaults
to legacy DXMT; that default is not the confirmed working package's profile.
The modern profile name includes D3D12, but Windlands and Job Simulator were
validated through D3D11/OpenVR; it does not establish D3D12 game compatibility.
Keep experimental x86 disabled:

```sh
export AVPPLAY_ALLOW_RUNTIME_BUILD=1
export AVPPLAY_BUILD_WINE_PE=1
export AVPPLAY_ENABLE_D3D12=1
export AVPPLAY_ENABLE_X86=0
export AVPPLAY_RUNTIME_SOURCE="$WVR_WORK/runtime-baseline"
export AVPPLAY_D3D12_PROFILE_SOURCE="$WVR_WORK/runtime-modern"
export AVPPLAY_BUILD_ROOT="$WVR_WORK/artifacts"
export AVPPLAY_LLVM_TOOLCHAINS_ROOT="$WVR_WORK/llvm-toolchains"
bash windows-vr-tools/assemble_runtime.sh
```

The assembler builds Debug, stages runtime/guest resources with matching receipts
and builds the app. The current generic spec uses
`org.avpplay.visionos-windows-vr`; an existing installation with a different bundle
ID has separate data, games and sign-in. For your own ID, benchmark diagnostics
or a Release development build, use an ignored local override after assembly:

```sh
export WVR_BUNDLE_IDENTIFIER="com.example.WineVisionVR"
python3 - <<'PY'
import json, os, pathlib, plistlib
root = pathlib.Path('visionos-windows-vr')
entitlements = plistlib.loads((root/'Resources/VisionOSWindowsVR.entitlements').read_bytes())
entitlements['get-task-allow'] = True
(root/'.local.development.entitlements').write_bytes(plistlib.dumps(entitlements))
spec = {'include': ['project.benchmark.yml'], 'targets': {'VisionOSWindowsVR': {
    'settings': {'base': {
        'PRODUCT_BUNDLE_IDENTIFIER': os.environ['WVR_BUNDLE_IDENTIFIER'],
        'DEVELOPMENT_TEAM': os.environ['AVPPLAY_DEVELOPMENT_TEAM'],
        'CODE_SIGN_ENTITLEMENTS': '.local.development.entitlements'}}}}}
(root/'.local.development.yml').write_text(json.dumps(spec, indent=2)+'\n')
PY
# Assembly prepared the modern overlay; manual generation must select that overlay.
export AVPPLAY_RUNTIME_SOURCE="$AVPPLAY_D3D12_PROFILE_SOURCE"
export AVPPLAY_DXMT_LINK_FLAG="-Wl,-force_load,\"$AVPPLAY_RUNTIME_SOURCE/app/Madeira/libdxmt_d3d12_combined.a\""
xcodegen generate --spec visionos-windows-vr/.local.development.yml \
  --project visionos-windows-vr
xcodebuild -project visionos-windows-vr/VisionOSWindowsVR.xcodeproj \
  -scheme VisionOSWindowsVR -configuration Release \
  -destination 'generic/platform=visionOS' \
  -derivedDataPath "$AVPPLAY_BUILD_ROOT/xcode-derived" \
  -allowProvisioningUpdates DEVELOPMENT_TEAM="$AVPPLAY_DEVELOPMENT_TEAM" \
  CODE_SIGN_STYLE=Automatic 'CODE_SIGN_IDENTITY=Apple Development' \
  AVPPLAY_DXMT_LINK_FLAG="$AVPPLAY_DXMT_LINK_FLAG" build
export WVR_APP="$AVPPLAY_BUILD_ROOT/xcode-derived/Build/Products/Release-xros/WineVision VR.app"
bash windows-vr-tools/verify_wine_bundle.sh "$WVR_APP"
python3 windows-vr-tools/verify_development_app.py "$WVR_APP" \
  --bundle-id "$WVR_BUNDLE_IDENTIFIER" --team-id "$AVPPLAY_DEVELOPMENT_TEAM" --benchmark
```

These bundle checks establish signature/profile/resource correctness, not JIT or
gameplay. `project.prebuilt.yml` is another historical build route: it expects a
runtime under `dist` and rebuilds other native frameworks. It is **not** the exact
three-framework-preserving assembly used for the confirmed games.

## Retained working checkpoint on this Mac

Do not delete these until a fresh source-built replacement passes the same games:

- Current tested app:
  `/Volumes/XRDev/build/WineVisionVR/artifacts-modern-single-option-game-compat/WineVision VR.app`
- Its frontend build, spec, audits and products:
  `/Volumes/XRDev/build/WineVisionVR/artifacts-modern-single-option/`
- Original known-working three-framework/resource input:
  `/Volumes/XRDev/build/WineVisionVR/black-screen-oct16/working-windlands-queue.app`
- Six-DLL/Steam-host source build, overlay, imports/ordinal checks and provenance:
  `/Volumes/XRDev/build/WineVisionVR/game-dll-compat/`
- Prepared modern Wine/DXMT sources:
  `/Volumes/XRDev/build/WineVisionVR/runtime-final2/`
- Prefix host/template/provenance:
  `/Volumes/XRDev/build/WineVisionVR/prefix-host-x86_64/`

The tested app executable UUID is `FF26154C-9A14-3681-B78F-420221BBC4BC`.
It embeds `WineVisionAssemblyAudit.json`, current native/guest/resource receipts,
`Runtime/AVPPLAY_PE_OVERLAY_PROVENANCE.json` and historical receipts under
`Runtime/HistoricalProvenance`. Those binary-dependent records remain with the
artifacts; the source-only checkpoint manifest records the helper scripts.
A separate backup of these external build artifacts is still needed if recovery
of the exact tested package after losing XRDev is required. Git alone does not
preserve that package.

## Installation and acceptance checks

1. Use `xcrun devicectl list devices` to find your own paired Vision Pro. Keep it
   awake and unlocked. Install the chosen verified app with
   `xcrun devicectl device install app --device '<DEVICE-ID>' "$WVR_APP"`.
2. Finish StikDebug RemotePairing using your own Mac/headset. If pairing discovery
   is absent, keep **Settings → General → Remote Devices** open on the headset.
   Import the validated pairing record locally into StikDebug. Connect LocalDevVPN
   and allow local network access. Pairing records are credentials: keep them out
   of Git and public bug reports.
3. Open WineVision directly and use its **Play** flow, which supplies Madeira's
   JIT script to StikDebug. StikDebug's separate app-list start is not equivalent.
4. In WineVision, sign into Steam, **Prepare Valve client**, and download the
   owned game. For original Windlands (428370), use the x64 **SteamVR/OpenVR**
   option 5. Job Simulator (448280) uses its sole launch option 0. Turn on both
   PS VR2 Sense controllers and confirm both are connected/tracked.
5. Confirm both-eye rendering, head tracking, audio, level start and controller
   interaction. Save **Export test sessions** after testing. Follow the
   [benchmark procedure](windows-vr-benchmark.md) for sustained/matched FPS tests.
6. Between games, end the session and use **Force quit app**, then reopen when a
   fresh Wine process is required. This discards unsaved Windows work.

The remaining reproducibility acceptance gate is a complete build in new paths
from this branch, followed by these physical Windlands and Job Simulator checks.
No such clean rebuild or new headset run was performed during this documentation
audit. Historical failure notes in older handoff files remain for investigation;
this page is the current build/recovery handoff.
