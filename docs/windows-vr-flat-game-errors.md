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
and must be investigated separately. The background-download update remains built
and held for installation at the user's request while these errors are reviewed.
