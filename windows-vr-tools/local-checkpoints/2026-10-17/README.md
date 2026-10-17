# XRDev assembly checkpoint — 17 October 2026

These are **archival, XRDev-specific helper sources**, copied without modification
from the development volume. They preserve how the app tested with Windlands and
Job Simulator was assembled. They are **not a portable fresh-clone build recipe**
and are not called by the normal runtime assembler. See
[the reproducibility handoff](../../../docs/windows-vr-reproducibility.md) for the
current build status and the supported source-build entry points.

`source-manifest.json` records the original absolute pathname, SHA-256 and byte
count of each saved file. The manifest proves only that these helper sources were
preserved; it is not a receipt for rebuilding the app or evidence that a new
build works on a headset.

## Saved stages

| Saved helper | Purpose and required external inputs |
|---|---|
| `env.sh` | Historical compiler/toolchain, build and source locations on `/Volumes/XRDev`. Sets the modern graphics profile. |
| `verify-local-app.py` | Checks this Mac's development signing, JIT debugging entitlement, increased memory limit, diagnostic settings and JIT script. |
| `artifacts-modern-single-option/assembly-audit.py` | Checks the current Swift/C ABI against the original signed app, preserves its runtime resources, and restores its exact three native frameworks after compatible current-source Metal compilation. |
| `artifacts-modern-single-option/project.yml` | XcodeGen specification for that Swift frontend build. Its contents use JSON syntax, which is also valid YAML. All external paths refer to the original XRDev layout. |
| `artifacts-modern-single-option/build-logged-modern.sh` | Runs the preflight, XcodeGen, Release app build and final signing/bundle checks for that specification. |
| `game-dll-compat/finalize.py` | Stages and validates five newly compiled ARM64EC Wine DLLs against the historical runtime; records actual source/build hashes and recursive imports. |
| `game-dll-compat/validate-ordinals.py` | Checks named and ordinal imports, including forwarded exports, from locally owned Fantastic Contraption and Google Earth binaries. The game binaries are not included. |
| `game-dll-compat/finalize-openvr.py` | Adds the matching ARM64EC `mmdevapi.dll` and rebuilt x64 Steam launch host, validates the inherited native audio dispatch table, and records the six-DLL/host overlay. |
| `artifacts-modern-single-option-game-compat/assemble.py` | Applies the exact six-DLL/host allowlist to the frontend app, preserves historical provenance, writes composite resource checksums, signs the app, and verifies unchanged native framework bytes/signatures. |

The final app was `/Volumes/XRDev/build/WineVisionVR/`
`artifacts-modern-single-option-game-compat/WineVision VR.app`. Its frontend
executable UUID was `FF26154C-9A14-3681-B78F-420221BBC4BC`. Subsequent gameplay
confirmation is recorded in [the testing notes](../../../docs/windows-vr-local-testing.md).
The helpers correctly retain their earlier `gameplayVerified: false` fields:
packaging validation itself does not establish gameplay.

## Inputs that remain outside Git

The exact assembly depends on the signed snapshot at
`/Volumes/XRDev/build/WineVisionVR/black-screen-oct16/working-windlands-queue.app`,
its native frameworks, guest resources and original provenance, the prepared
`runtime-final2` source/build tree, compiled overlay DLLs, the rebuilt Steam
host, generated overlay provenance/check reports, and Xcode/LLVM-MinGW/build
caches. None of those generated files is included here. The finalizers consume
existing Wine build products; they do not compile the DLLs themselves.

The six modules (`dwmapi`, `wsock32`, `avrt`, `vcruntime140`, `msvcp140`,
`mmdevapi`) are required by the tracked
[`build_wine_guest_resources.sh`](../../build_wine_guest_resources.sh). The
tracked [`build_steam_dock.sh`](../../build_steam_dock.sh) applies the bounded
launch-argument patch and builds the Steam host. Those portable source-build
steps remain the normal implementation; these archived scripts explain the
specific assembly used for headset testing.

No pairing records, account tokens, credentials, private signing keys,
provisioning profiles, game binaries, runtime binaries or user logs are copied
here. The scripts do contain this development Mac's public bundle identifier,
team identifier and signing certificate fingerprint, because their checks and
signing commands used those identifiers. They do not grant signing access.

## Before reusing a helper

Do not run the archived helpers directly from this directory. They contain
absolute paths and write, copy, remove and sign files in their original build
locations. Some refuse existing output rather than replacing it. Merely moving
these files into Git does not make their paths portable or restore their inputs.
For another machine, first adapt a separate copy to new isolated output paths,
provide matching verified inputs, use that machine's own signing identity/team
and entitlement file, and review every write location. Keep the original known
working app and frameworks intact. A clean source rebuild still requires its
own bundle checks and physical headset gameplay retest.
