# Flat-game error review — 17 October 2026

## Tomb Raider I (Steam 224960)

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
