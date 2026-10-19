# ARM64EC Visual C++ 2013 runtime

Tilt Brush 23.3 reaches its painting state, but starting a brush in the October 19, 2026 R16 test failed to load its native `TiltBrushCpp.dll`. This is a separate issue from the debugger startup delay.

The captured Unity log first reports `DllNotFoundException: TiltBrushCpp` in the matrix/bounds helper called by `Batch` and `QuadStripBrush`. Wine supplies the more specific cause: loading `MSVCR120.dll`, imported by `TiltBrushCpp.dll`, returns `c000007b` (`STATUS_INVALID_IMAGE_FORMAT`). The subsequent 3,517 `NullReferenceException` entries are follow-on brush failures. Earlier unsupported animated-logo video and HTTP 502 errors do not explain this dependency failure. No shader failure precedes it in the capture. Rendering continued until the app entered background; the capture does not establish a spontaneous host crash.

## Architecture gap

R16 includes `Runtime/aarch64-windows/msvcr120.dll` (machine `0xaa64`, no CHPE metadata) and its i386 equivalent, but no ARM64EC equivalent. The selected Steam/Tilt Brush session uses the ARM64EC farm. Madeira's existing bridge fills non-colliding system32 names from the other ARM64 farm, so a missing ARM64EC CRT can resolve to an incompatible pure ARM64 DLL.

The packaged ARM64 DLL is 1,245,184 bytes, SHA-256 `01447ee5cf8c39abf4540d9e68eff32a797535e1be4c5b67a37fb96c1701f0a4`. These are package facts. Reading the device's system32 leaf failed because CoreDevice refused its symlink (`openat` POSIX 62, `ELOOP`); its bytes and target were not independently copied. The failed transfer is not evidence that the DLL is absent. App-local shadowing has not been excluded by a successful device file read.

## Build from source

The normal `windows-vr-tools/build_wine_guest_resources.sh` ARM64EC module list now includes both `msvcr120` and `msvcp120`, alongside the existing VC2012 CRTs. Use the documented prepared, pinned Madeira overlay and LLVM-MinGW toolchain; the normal recipe builds and stages the genuine Wine targets:

```sh
AVPPLAY_ALLOW_RUNTIME_BUILD=1 AVPPLAY_BUILD_WINE_PE=1 \
AVPPLAY_RUNTIME_SOURCE=/absolute/path/to/prepared-madeira-overlay \
AVPPLAY_LLVM_MINGW_ROOT=/absolute/path/to/llvm-mingw-20260421-ucrt-macos-universal \
AVPPLAY_BUILD_JOBS=4 \
bash windows-vr-tools/build_wine_guest_resources.sh
```

For a targeted compile in a separate, already configured ARM64EC Wine tree, the actual targets are:

```sh
make -C /absolute/path/to/isolated-wine/build-arm64ec -j4 \
  dlls/msvcr120/arm64ec-windows/msvcr120.dll \
  dlls/msvcp120/arm64ec-windows/msvcp120.dll
```

A direct target compile alone does not stage, sign or install an app. Do not modify frozen build trees or copy pure ARM64/i386 DLLs into the ARM64EC farm. Use normal assembly and package validation after building the missing guest resources; keep the native runtime archives and their provenance distinct from these newly built guest DLLs.

## Local validation completed

An isolated APFS clone of the pinned Wine source/build inputs at application source commit `a4af9f0c31b3cf54b426e430116b6a8958007943` compiled both real targets successfully. Its original source/build inputs remained unchanged. This was a guest-module compile; the native runtime was not rebuilt.

Both DLLs report raw PE machine `0x8664` with valid CHPE version 2 metadata, identifying them as ARM64EC. The audit resolved all 339 direct mandatory/delay imported symbols, including their export forwarders, against the exact existing ARM64EC package and the two new modules. This checks architecture and symbol availability, not execution or Tilt Brush gameplay.

| Module | Build output bytes | SHA-256 |
| --- | ---: | --- |
| msvcr120.dll | 4,063,232 | `443c1dd4cafa94f99640ab77172b335ca3bea24403b301480d69f93013e0b6e6` |
| msvcp120.dll | 3,735,552 | `74774d10f7dacf2f0e6b870bb0670cb137e89ab5535df18e9cf0cd56c79c6ac1` |

The full local evidence is retained outside Git in `/Volumes/XRDev/build/WineVisionVR/vc2013-oct19/`: `build-inputs.json`, `build-result.json`, and `guest-modules-audit.json` (audit SHA-256 `ae3081bfcd869b0f9c642e92bc91a658a3296a3965c851001e02c3b3789e0b33`). Stripping or staging changes artifact hashes and must receive its own binding.

After packaging, retest a brush stroke on Vision Pro and verify that the `MSVCR120.dll` bad-format, native plugin load and resulting brush null exceptions disappear. The successful compile and import audit do not yet prove that result.

## Combined signed package checkpoint

The actual device plugin was subsequently retrieved successfully after using the installed directory capitalization `TiltBrush_Data`. All 26 imports (17 from MSVCR120 and nine from kernel32) resolve against the genuine new CRT and existing ARM64EC package. The previous failed system32 symlink read remains preserved; this does not retroactively claim that leaf was copied.

The signed r18 package from a08e0a25126dc831b696b4515ad0027a658f9b7e passes canonical new guest-receipt generation, fresh transactional resource staging and full package validation. Only the two new guest DLLs and their newly generated closure/asset receipts differ in the resource payload. The existing native archives are unchanged; host code matches the preceding guarded-signal build. Raw build hashes above are not reused as stripped/staged DLL hashes: the r18 pipeline records and verifies each stage separately.

The r18 installation attempt fails when the headset becomes unreachable. Matching DLLs are therefore not yet a verified headset drawing repair. Evidence: compatibility-vc2013-oct19-r18/verified-app-complete.json, SHA-256 0f0f578aa390e7c645911f28cb1e3d4a983d841e76f33fec082d9d51c3d4e0e5, plus its successful and failed command receipts.
