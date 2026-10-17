# What this fork added to get games working

Recorded 17 October 2026. **Windlands and Job Simulator are user-confirmed working**
on the M2 Vision Pro, visionOS 27.2, with both PS VR2 Sense controllers connected.
This document identifies our additions, their dependencies, and what is saved
outside GitHub. It complements the [rebuild/run handoff](windows-vr-reproducibility.md).

## Runtime and compatibility changes in this branch

| Problem or requirement | Change we made | Checked-in implementation |
|---|---|---|
| Windlands exited around its splash/intro in OpenSSL code | Save `OPENSSL_ia32cap=0` for Windlands only (Steam 428370). The retry reached a level and working controls; the precise CPU dispatch fault is not proven. | `visionos-windows-vr/Sources/LauncherModel.swift`; launch-selection regression |
| Wine startup/Steam imports were incomplete | Build/package CryptoAPI providers, PSAPI and their transitive Wine dependencies; verify the complete PE import closure, NLS tables, loader files and UI fonts. | `windows-vr-tools/build_wine_guest_resources.sh`, `stage_resources.py`, `verify_wine_imports.py`, `verify_wine_bundle.sh`; XcodeGen resource layout |
| Some game imports had only incompatible plain ARM64 providers | Add source-built **ARM64EC** `dwmapi.dll`, `wsock32.dll`, `avrt.dll`, `vcruntime140.dll`, `msvcp140.dll`, `mmdevapi.dll`. Match the audio client's dispatch order to the existing native audio driver. | Wine module list, staging checks, and archived six-DLL overlay finalizers under `windows-vr-tools/local-checkpoints/2026-10-17/` |
| OpenComposite needed writable configuration | Copy its unchanged DLL package into a private writable session directory, rather than exposing only a read-only bundle mapping. | `windows-runtime-plugin/WindowsVRRuntimePlugin.mm`; guest-runtime mapping regression |
| OpenVR virtual calls returned bad aggregate values across compilers | Adapt the x64 MSVC/MinGW aggregate-return ABI. | `windows-vr-openvr/patches/0007-mingw-msvc-aggregate-return.patch`; mixed-compiler regression |
| Inverted eye texture bounds/cropping | Add the D3D11 crop/flip repair and matching transport handling. | `windows-vr-openvr/patches/0008-d3d11-inverted-eye-bounds.patch`; bounds regression; `windows-vr-openxr/` |
| Input restart/action lifetime errors | Repair action-space ownership, live-session attachment checks and synchronization; retain controller discovery/tracking diagnostics. | `windows-vr-openxr/src/WindowsVROpenXR.cpp`; action lifetime/input regressions |
| JIT/source rebuild reliability | Port the 640 MiB JIT pool setting, safe battery-property handling, static GnuTLS backend configuration and per-process executable-memory aliases into source patches. | `windows-runtime-plugin/patches/0006` through `0009`; sanitizer/source-repair regressions |
| Fantastic Contraption selected Oculus fallback instead of OpenVR | Rebuild Steam host with bounded optional launch arguments on initial and retry launches; supply `-vrmode openvr` only for Steam 386690. | `windows-vr-tools/build_steam_dock.sh`, `patches/madeira-dock/0001-bounded-launch-arguments.patch`, `visionos-windows-vr/Sources/Steam/MadeiraDock.swift` |

These repairs have different validation scopes. The Fantastic Contraption changes
cleared its import/OpenVR/audio startup failures, but **did not make it reliably
playable**: it still freezes/crashes. Source-patch tests are not proof that the
retained native binaries were rebuilt from the current checkout. Earlier shader,
query and compositor work inherited from upstream remains part of the runtime;
it is not all newly authored by this fork.

## App and testing additions

- Flat Windows desktop window, pointer/keyboard handling and our own small Win32
  test executable. Text display and typing were observed; not every Win32 control
  or save/load operation has been validated.
- A saved FIFO Steam download queue, pre-download/installed-size estimates, a
  direct Run action when only one Windows launch option exists, and Repair moved
  away from Run.
- End-session handling and an explicit Force quit control for Wine sessions that
  cannot safely restart in the same process.
- Persistent bounded per-attempt session logs and export, Steam-free normal and
  inverted VR smoke scenes, FPS log analysis and host/simulator correctness tools.
- Experimental i386/WOW64 build, ABI and pointer-transport support. This is
  separate from the working modern x64 package; **Audioshield remains unresolved**.
- Build/resource receipt checks and a portable development-signing/JIT prerequisite
  checker, `windows-vr-tools/verify_development_app.py`.

See [test results and remaining failures](windows-vr-local-testing.md) and the
[benchmark procedure](windows-vr-benchmark.md). Google Earth VR still requires an
unsupported OpenGL rendering/VR interop path; adding its missing DLL imports
alone does not resolve that requirement.

## Dependencies downloaded or built outside this Git repository

The following source pins come from the checked-in lock files and the locked
Madeira submodule gitlinks. Fetch through the tracked scripts, not arbitrary
latest versions. The downloaded trees and resulting binaries are ignored.

| Dependency | Pinned revision | Acquisition / source of pin |
|---|---|---|
| madeira | `48f976429c189f8396e23d251d8a82f43c705922` | fetch_sources.py; sources.lock.json |
| openvr | `0924064316de3effbcd1acf1e309182a2deb1c05` | fetch_sources.py; sources.lock.json |
| alvr-visionos | `fb2576a2a4df23a20647e327acc4d8f785da0d77` | tracking reference; not a runtime executable |
| openxr | `f2448a8797c85814aa892efc1ab8707900fbcc78` | fetch_sources.py; sources.lock.json |
| opencomposite | `cff07db75c4823afe93ed7027b03d5f7bc86f164` | fetch_sources.py; sources.lock.json |
| dxmt-d3d12-experimental | `e94c312f5c054263acf261cfa109edf13e757587` | fetch_sources.py; sources.lock.json |
| freetype | `42608f77f20749dd6ddc9e0536788eaad70ea4b5` | fetch_sources.py; sources.lock.json |
| Madeira wine | `257f271cfffed9f22f7987cac53bc00095d092fe` | Recursive submodule of pinned Madeira |
| Madeira FEX | `3bec2ac498bf78156ab47c0c194b0e8cb2849756` | Recursive submodule of pinned Madeira |
| Madeira dxmt (legacy; modern profile uses 3Shain pin above) | `db546ee466ad50ec6463edb5fa183de11db43761` | Recursive submodule of pinned Madeira |
| Madeira madeira-dock | `72558e416a390f3669457930f09a389e54f49556` | Recursive submodule of pinned Madeira |
| Native visionOS LLVM | `8dfdcc7b7bf66834a761bd8de445840ef68e4d1a` | prepare_llvm.sh; llvm.lock.json |

The locked Madeira tree additionally supplies/builds native cryptography,
compression, database, media and font dependencies. Their generated archives are
inputs to the runtime plugin, not separately installed headset apps. Source
preparation/build scripts and receipts record that dependency closure; do not
replace those archives with unrelated macOS/iOS binaries. See
`visionos-windows-vr/project.yml`, `windows-vr-tools/build_runtime.sh` and the
[tooling recipe](../windows-vr-tools/README.md).

External tools/services also required:

- Full Xcode 27 with visionOS 27 SDK and Apple's Metal Toolchain; Git, Python 3,
  CMake 3.28+, Ninja, Meson, XcodeGen, Bison 3; Rosetta for the x86-64 prefix host.
- LLVM-MinGW **20260421 UCRT macOS universal**, archive SHA-256
  `bd85a3975723815cef28dbbd2ca2cb0c926f6b348a12a0453f39f7af273cb3f7`.
  The [tooling recipe](../windows-vr-tools/README.md#assembly-order) links the release.
- Your Apple development signing identity/profile with debugger attachment and
  increased memory permitted; Developer Mode and Xcode pairing on your headset.
- StikDebug with your own validated RemotePairing record, and connected LocalDevVPN.
  Open WineVision and use its Play handoff; its Madeira JIT script is required.
- An owning Steam account, the prepared Valve client, downloaded games, and both
  paired PS VR2 Sense controllers for the confirmed VR setup.

Dependency licenses/notices are retained by the fetch/stage tools. See
[THIRD-PARTY.md](../THIRD-PARTY.md); this note does not replace upstream notices.

## Exact working package: retained on XRDev, not in GitHub

The tested package consists of:

| Part | Where it comes from / where it is saved |
|---|---|
| Current Swift app frontend | Checked-in source; tested executable UUID `FF26154C-9A14-3681-B78F-420221BBC4BC` |
| `WindowsRuntimePlugin.framework`, `WindowsVRNativeBridge.framework`, `WindowsVRMetal.framework` | Preserved signed known-working native frameworks; exact bytes were kept during assembly |
| Six ARM64EC Wine DLLs listed above | Newly compiled Wine resources from the prepared modern source tree; overlaid without replacing native frameworks |
| `arm64ec-windows/dockhost.exe` | Newly compiled **x64** Steam launch host; directory name does not describe this executable's PE architecture |
| Other Wine/FEX/DXMT DLLs, NLS, fonts, clean prefix, VR clients and JIT script | Inherited verified runtime resources with historical receipts and a current composite checksum manifest |

Current app:
`/Volumes/XRDev/build/WineVisionVR/artifacts-modern-single-option-game-compat/WineVision VR.app`.
Its preserved native/resource input is
`/Volumes/XRDev/build/WineVisionVR/black-screen-oct16/working-windlands-queue.app`.
New DLL/host outputs and provenance are under
`/Volumes/XRDev/build/WineVisionVR/game-dll-compat/`.
Prepared modern sources are under
`/Volumes/XRDev/build/WineVisionVR/runtime-final2/`.
The [runtime inventory](windows-vr-runtime-inventory.json) records SHA-256 hashes
of the key binaries and receipt files, so the tested artifacts can be identified
without adding binaries to Git. These hashes identify files; they cannot recover
them if the external drive is lost.

The source-only assembly scripts and their original-path/hash manifest **are
checked in** under
[`windows-vr-tools/local-checkpoints/2026-10-17`](../windows-vr-tools/local-checkpoints/2026-10-17/README.md).
They require retained external inputs; do not run their historical absolute-path
commands against live build folders without adapting an isolated copy.

Games, Steam tokens, pairing records, signing private keys/profiles, toolchain
archives, generated DLLs/frameworks/apps, used prefixes and test logs are not
part of the GitHub check-in. For a fresh build, follow the
[modern-profile rebuild/run instructions](windows-vr-reproducibility.md).
**A full clean rebuild reproducing equivalent headset behavior remains
unverified.** Keep a separate backup of the working app and external inputs until
that acceptance test has passed.
