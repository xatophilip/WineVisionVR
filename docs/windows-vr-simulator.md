# visionOS Simulator checks

## Current automated regression run (2026-10-18)

The current source at `1d8bbbeeebf65358ae502ed05a82921881730c67` was compiled
and executed in a fresh visionOS 27.0 simulator (24M5316i), using the matching
Xcode 27 beta 3 SDK. All five standard native suites passed: compositor,
frame transfer, GPU statistics, production presentation shaders, and audio
session policy. They execute real native code with synthetic inputs, not a
Windows game. Raw logs, script hashes and timings are retained in
`/Volumes/XRDev/build/WineVisionVR/simulator-regression-oct18/probe-results.json`.

The additional guest-foveation probe exits 1 at its initial capability check:
`FAIL: VRR device available`. The simulator reports no support for a
single-layer rasterization-rate map; no later foveation assertions execute.
The original nonzero result remains in the receipt, whose `allPassed` is false
for the six-probe experiment. This is not recorded as a foveation pass or a game
failure. [Apple describes Simulator's foveation limitation](https://developer.apple.com/videos/play/wwdc2023/10089/).

The five standard probes are already included in
`windows-vr-tools/test_local.py --simulator SIMULATOR_UDID --build EXTERNAL_DIRECTORY`.
Set `DEVELOPER_DIR` to the matching Xcode installation and `TMPDIR` to an
external temporary directory, and boot the selected simulator first. The
visionOS 27 runtime requires device type
`com.apple.CoreSimulator.SimDeviceType.Apple-Vision-Pro-4K`; the older
2732×2048 device type is incompatible. This run's isolated simulator UUID is
`7A4EAAEB-0F88-4991-A98D-24977C9B41A1`. Its data uses Apple's default device
directory because CoreSimulator denied creation in the external device set.
It is shut down after testing and can be booted for future runs.

These checks are useful before deployment but do not verify StikDebug/JIT,
FEX execution, real game loading, actual Sense tracking or sustained headset
performance. The historical launcher UI smoke test below is a separate result;
it was not rerun as part of these native probes.

The production `WindowsVRCompositorBridge.mm` was compiled against the visionOS
27 Simulator SDK and executed in the installed arm64 Vision Pro simulator on
2026-10-13. It used actual Metal textures, command buffers and shared events,
with synthetic producer frames. The checks passed:

- Distinct left/right GPU clears and pixel readback, plus readiness signaling.
- Queue overflow, newest-frame acquisition and ordered ticket completion.
- Texture ownership and an acquired lease surviving pause.
- Empty-queue behavior and rejection of an old target generation.
- V2 stereo texture-array slices and cropped eye geometry; V1 correctly refuses
  those frames without losing them.

Run again with a booted simulator:

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  bash windows-vr-tools/test_simulator_compositor.sh booted
```

Pass a specific simulator UDID instead of `booted` when several are running.
The script retains its executable and result log in a fresh temporary directory.
[Results and source hashes](windows-vr-simulator-results.json) record this run.

The original device runtime is rejected by Simulator as a `visionOS` binary.
An isolated experimental profile now loads successfully: copies of the native
frameworks are retagged for Simulator, WindowsVRMetal is compiled against the
Simulator SDK, and the unused MetalFX load dependency becomes optional. The
preparation tool refuses this adjustment if the runtime imports MetalFX symbols.
It neither installs a fake MetalFX implementation nor changes device artifacts.
Retagging enables an experiment; it does not prove device code is fully compatible.

The full launcher also passed an Xcode UI test: it launched, displayed the Steam
library button and enabled it (one test, zero failures). This test does not open
Steam, authenticate an account or start a game.

Reproduce the experimental profile with a device-built app and a Simulator-built
Metal dylib (use new output paths):

```sh
python3 windows-vr-tools/prepare_simulator_frameworks.py \
  /path/to/device.app/Frameworks /path/to/libWindowsVRMetal.dylib /tmp/simulator-frameworks
ruby windows-vr-tools/generate_simulator_project.rb \
  /tmp/simulator-frameworks /tmp/simulator-project.yml
mkdir -p /tmp/simulator-project
xcodegen generate --spec /tmp/simulator-project.yml --project /tmp/simulator-project
xcodebuild -project /tmp/simulator-project/VisionOSWindowsVRSimulatorExperiment.xcodeproj \
  -scheme SimulatorLauncher -destination 'platform=visionOS Simulator,id=SIMULATOR_UDID' \
  CODE_SIGNING_ALLOWED=NO ARCHS=arm64 ONLY_ACTIVE_ARCH=YES test
```

The generated profile reads the existing prebuilt project's source/resource
layout and uses a separate bundle identifier. The Metal Swift package builds for
the selected SDK. The framework preparation tool additionally needs that package's
Simulator dylib to supply the standalone runtime probe's dependencies.

`SimulatorRuntimeProbe.mm` and `SimulatorWindowsGuest.c` provide a separate
Windows startup experiment. `simulator_jit_debugger.py` attaches LLDB only to that
probe's executable and implements its memory preparation requests using the
actual debugger. It never claims JIT readiness without preparation and does not
change the production launcher's debugger checks. Windows execution is still
under investigation; no successful guest execution is claimed here.

These tests do not establish game rendering, audio timing, immersive compositor
output or headset performance. Simulator uses the Mac GPU with a different feature
set; see [Apple's Simulator Metal documentation](https://developer.apple.com/documentation/metal/developing-metal-apps-that-run-in-simulator).
