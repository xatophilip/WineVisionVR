# Flat Windows apps on Vision Pro

The launcher supports **Desktop window** alongside **Immersive VR**. Desktop
mode uses the existing Wine GDI/Metal compositor in a normal visionOS window.
It does not require an immersive space or install OpenComposite/OpenXR into the
app's prefix. It still needs StikDebug JIT and a debuggable signed build.

Every desktop session starts with a **1280×720 (720p)** virtual Windows monitor,
including Steam games that select desktop mode. The launcher supplies Wine's
`MADEIRA_SCREEN_W/H` before startup; the desktop backing layer and the legacy
Steam virtual-desktop argument helper use the same dimensions. Resizing the
visionOS window scales the presentation and pointer mapping. A guest can still
change its own display mode, which the compositor follows. Immersive VR eye
sizes are configured separately.

## First smoke test

1. Complete RemotePairing and connect StikDebug's developer tunnel. Leave
   LocalDevVPN connected. Open WineVision VR directly; its Play button supplies
   Madeira's script automatically. StikDebug's separate app-list launch does not
   supply that script and is unsuitable for this runtime.
2. In WineVision VR, select **Windows desktop test**, then **Play**.
3. Confirm the Windows window appears. Type into its text field and use
   **Count clicks**. Save a note, end the session, relaunch, and load the note.
4. Check pointer placement after resizing the visionOS window. Test the
   **Keyboard** button, physical keyboard, and the right-click/scroll controls.
5. Use **End session** to request Alt+F4. Complete any Windows save prompt;
   the launcher retains the desktop surface until the guest actually exits.

The bundled demo is an app-owned x64 Win32 program built from
`visionos-windows-vr/Examples/desktop-demo/main.c`. It needs no Steam account.
Selection copies its executable into the app's Documents area, preserves saved
notes, and uses its own Wine prefix. Generated binaries are ignored by Git.

For another Windows app, import its manifest and select **Desktop window**.
Manifests can specify `"presentation": "desktop"`; older manifests default to
`"immersiveVR"`. Known non-VR Steam launch entries choose desktop mode, while
VR and unknown launch entries keep immersive mode. Compatibility varies by app.
Software text entry currently supports US ASCII, Tab and Enter; unsupported
characters produce a visible message.

## Build and verify

```sh
export AVPPLAY_LLVM_MINGW_ROOT=/absolute/path/to/pinned/llvm-mingw
bash windows-vr-tools/build_desktop_demo.sh
swift test --package-path windows-vr
python3 windows-runtime-plugin/Tests/test_desktop_contract.py --help
```

Runtime assembly builds the demo before generating the Xcode project. The demo
builder verifies AMD64 PE architecture and writes a hash receipt. The native
contract test extracts the production parser/readiness and presentation-environment
functions and runs them under Address/Undefined Behavior Sanitizers. It verifies
the actual desktop monitor environment, retained VR sizing and scoped environment
restoration, and executes the legacy Steam argument helper with the shared size.
The local test runner includes it. Add `--runtime-source /path/to/prepared-madeira`
to compile the actual Wine monitor-size reader against the same environment.

On the XRDev Mac, the signed Release build and installation passed on October
15, 2026. The 11 Swift core tests, 32 packaging tests, native desktop contract,
and Steam launch-selection check passed. The first physical launch opened the host desktop surface and StikDebug
verified the entire 640 MiB JIT arena (40,960 pages, zero preparation errors).
Wine then crashed before the demo appeared: native ntdll read NLS tables from
`<bundle>/nls`, while packaging only supplied `Runtime/nls`. The Xcode project
now copies the complete NLS folder to the loader path, and the bundle verifier
requires matching runtime tables there. Four added regression cases bring
packaging coverage to 36 passing tests. The corrected signed build passed;
the NLS retest reached `desktop-demo.exe`, created the titled Win32 window and
child controls, and received pointer movement and mouse-button events. The
window lacked text because the packaged app had no usable Wine UI fonts. The
project now includes the pinned Wine font folder at `<bundle>/fonts`, the native
win32u data path, and the bundle check requires its UI fonts. All 37 packaging
tests and the corrected signed build pass. The later physical retest confirmed
readable button text; typing, saved-note persistence and Windlands/Tilt Brush
gameplay still need verification. Current button/quit failures are recorded below.
Desktop sessions do not report VR compositor counters as desktop FPS.

## Physical test findings

On 18 October, the separate 32-bit desktop fixture passed all six automated
input/edit/save/load/UTF-8 checks, and the user confirmed physical Count clicks
input. Those repairs are included in the unified main app; see
[the 32-bit validation record](windows-vr-modern-32bit.md).

Earlier x64 tests, before those repairs: the font update removed all `select_font` failures and displayed text on the
Windows buttons. Pointer motion and button-up events reach the test app, but
button actions and cooperative Alt+F4 quit failed in that test. The user later
confirmed that the Windows app accepted typing; saving and button actions remain
unverified. A diagnostic demo logs
control IDs and event types to `demo-events.txt`, without recording note text.
The diagnostic app argument `--desktop-smoke-test` selects the demo, enables
surface captures and performs a labelled Win32 `SendInput` probe. That probe
was built but the user switched back to VR before it was exercised.

## User-supplied Notepad target

[Old Win32 Notepad](https://sourceforge.net/projects/old-notepad/) release
1.1.3.0 was downloaded from the project's SourceForge release. The exact file
is 231,424 bytes with SHA-256
`7452918e9d762d4e0e3df7044b6065d130c5b598672436cd3d07a82b93c9e079`.
It is a managed C#/.NET Framework 4.5.2 Windows Forms AnyCPU assembly:
PE machine I386, CLR flags `0x9`, with
the 32-bit-required flag clear. The production executable classifier was
compiled and run under ASan/UBSan against this exact file and rejected it at
the then-current x64 preflight gate. No Notepad guest execution is claimed.
The unified app still lacks a .NET/Mono CLR; native x86 support does not supply it.

The executable and desktop manifest were transferred to
`Documents/WindowsVR/Games/OldNotepad/1.1.3.0-7452918e9d76` in WineVision's own
container. The library title explicitly says `.NET required`. Local inspection,
provenance and the classifier probe are under
`/Volumes/XRDev/build/WineVisionVR/test-apps/old-notepad`. The file is a recorded
compatibility target, not a successful smoke test or a bundled runtime asset.

An unattended Mac comparison ran the exact x64 demo under the source-built
Wine/Rosetta host in an isolated prefix. Its automatic Win32 SendInput probe
produced both button-down and button-up, `BN_CLICKED`, `count=1` and a status
update. This validates the demo's Windows event path on Mac Wine; it does not
validate visionOS touch delivery or WineIOS/FEX input. Reports are under
`/Volumes/XRDev/build/WineVisionVR/overnight-tests/desktop-host-warm-result.json`.

## DOSBox / Tomb Raider I

The app-specific software-renderer launch path and local test evidence are
recorded in [Windows DOSBox / Tomb Raider](windows-desktop-dosbox.md).
