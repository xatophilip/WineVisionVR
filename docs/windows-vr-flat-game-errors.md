# Game error reviews

## 18 October 2026 — unified main-app capture

The unified main app retains the existing Steam login and installed library; the
user confirmed both after the in-place update. Its runtime build ID begins
`05dca43b3dcd`. The earlier captures below describe older packages, not the
current state of 32-bit support.

| Attempt (British Summer Time) | Evidence and next step |
|---|---|
| CyberThreat, 11:41 | Captured before the unified update, on runtime `5b87d3e724b0`. The actual x64 game starts at 11:43:36; Steam reports success, and OpenXR becomes active at 11:43:40. A Mono code-backpatch fault is explicitly handled and resumed. No stereo end-frame is recorded before the capture ends around 11:43:46; repeated thread-wake reports do not establish a root cause. No post-update CyberThreat attempt was captured. Its Unity 5.6.3f1 player log was subsequently retrieved: D3D11 level 11.1 and OpenVR initialize, with missing XInput DLL warnings but no logged fatal exception. A longer current-build retest is needed; patch 0015 has no demonstrated connection to this x64 attempt. |
| Audioshield, 11:45 | Steam authentication and entitlement checks succeed. Its 32-bit child fails before guest frames: native ARM64 `wow64!Wow64LdrpInitialize` calls an x64 `RtlRunOnceExecuteOnce` thunk through ARM64EC ntdll. Patch 0015 redirects native ARM64 importers to the native target while preserving x64 importers. Before/after production-code tests with the actual shipped PE metadata pass; a new device build is still required. Secondary exception-reporting faults are not the initial cause. |
| Tomb Raider I, 11:46 | Steam option 1 reports client error 19 with update waits/retries. The later install record is StateFlags 36 (Files Missing), and Steam content_log identifies the earlier absent tombub.exe attempt. Normal depot verification/repair is required; this does not prove DOSBox ran. The unified package now includes the experimentally validated 32-bit desktop/VR runtime, so the old missing-runtime blocker below no longer describes this build. The bundled DOSBox now reaches its menu and Caves level in the isolated local Wine control with working keyboard input; see [the recipe and remaining headset checks](windows-desktop-dosbox.md). Vision Pro launch/gameplay remain unverified. |
| Tilt Brush, 11:49 | Unity initializes Direct3D11 and OpenVR; the compositor records 714 submitted guest frames. The actual Unity player log reports a missing `wmic.exe` in `App.Awake`, followed by repeated managed pointer-update null references. Both controllers are disconnected/untracked in this capture. Wine WMIC/provider packaging is being repaired; success in Tilt Brush is not yet established. Certificate trust and unsupported animated-logo media errors are separate findings and remain unresolved. |

The desktop display defaults are now 1280×720 in source, including the Wine
monitor environment and the initial desktop surface. Geometry/environment
contracts passed locally. This change has not yet been verified on the headset.

Testing different applications is useful when attempts are sequential and their
visible outcome is recorded: it distinguishes CPU/child-startup, desktop input,
graphics, controller, audio and application-specific requirements. Logs can
contain harmless or caught errors, so an error count alone is not a compatibility
result. Preserve the per-attempt journal and actual player log, and repeat a
known working app after a runtime change. The owned x64/x86 desktop, CPU, VR and
mixed-parent/child fixtures provide narrower controls than another large game.

No game files, Steam installation state or authentication checks were changed
during this review. Raw game logs and user content remain outside Git.

## 17 October 2026 — historical flat-game review

### Tomb Raider I (Steam 224960)

Reviewed the headset's captured per-attempt journals, launcher/runtime logs,
Valve's local binary product-info cache, installed app manifest and game folder.
No game content, account identifiers or credentials are included in this report.
The installed app was left unchanged during collection.

| Evidence | Finding |
|---|---|
| Steam option 3: `tombub.exe` | File is absent from the installed game. Steam reported launch error 28, "could not find the game's executable." |
| Steam option 2: `tombati.exe` | Also absent; it should not be offered as an installed launch choice. |
| Steam options 0/1: `DOSBox.exe`, with fullscreen/windowed configurations | The actual installed file is `dosbox.exe`. The app's case-sensitive file-existence and PE checks miss this otherwise valid Windows-style filename. |
| Installed DOSBox PE header | Machine 0x014c: 32-bit x86. The current modern runtime package has experimental x86 disabled. Correcting launch selection alone cannot make this engine run. |
| Earlier option 0 attempt | Steam reported error 19 and repeated update-wait attempts. This is a separate observed client/install state, not proof that a Windows game process ran. |

The filename/selection repair resolves installed executables using Windows-style
case matching inside the game folder, checks regular files and refuses path or
symlink escapes and ambiguous fallback matches. Both the launch menu and PE
architecture check use the same resolved file, so a missing optional launcher is
not offered and a differently cased 32-bit executable is identified before JIT.

Tomb Raider I is **not confirmed working** in this build. Its bundled DOSBox still
needs supported 32-bit execution, or a separately validated compatible engine.
The current experimental 32-bit profile is isolated from the modern graphics
profile and is not a drop-in setting for the working Windlands build. No alternate
engine was downloaded or substituted, and game files were not modified.

The prior attempt using the missing option may also require a normal verified
Update / repair before Steam clears its update-wait state. Do not hand-edit an
appmanifest to claim a complete install. Even a successful repair does not remove
the 32-bit runtime requirement.

Only Tomb Raider I appears as a flat-game attempt in the captured recent session
batch. Tilt Brush and Space Pirate Trainer entries in the same batch are VR cases
and must be investigated separately. After this review, the signed Release containing the selection repair, background
transfers and the disabled-by-default experimental cache launcher was installed
and opened on the headset. Games and saved data were retained. The source build
is `84663b7`; the app UUID is `772767BC-4724-3F1A-96DE-FDE41E4B334B`.

Three targeted contracts passed: installed launch selection/path safety, queue
handoff validation, and PE architecture inspection. The host volume is case
insensitive, so a physical two-case-file ambiguity fixture was skipped; the
production matching function was tested directly with ambiguous candidates.
The signed visionOS build and bundle/profile checks also passed. A requested
automatic Tomb Raider preflight reused an already-running app process, so it
did not establish the new error behavior on the headset. Tomb Raider gameplay
remains unvalidated and blocked by the known 32-bit requirement.


## Latest Tilt Brush attempt, 18 October 2026

The `232A90B4` session began at 12:27:58.950 BST using the still-installed r4
runtime `05dca43b`. By 12:29:01 it recorded 529 submitted and 528 completed guest
frames, with an approximately ten-second interval without a new guest frame.
Both controllers were connected and tracked. The missing-WMIC error persisted;
the player log recorded 575 managed null references (574 pointer updates and one
SketchCatalog). These were handled/passed through and do not establish a fatal
crash. The sampled audio source windows reported mean absolute amplitude 0, peak 0
and no clipped samples; no underrun or overload was logged. The reported
clicking remains unexplained. Home returned to normal after the app exited. Tilt Brush was not
retried, and this capture does not test the newer r5 package.
