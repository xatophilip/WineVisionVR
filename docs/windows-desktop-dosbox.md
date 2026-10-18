# Steam Tomb Raider I through its bundled DOSBox

The 18 October local test runs the user-owned Steam app 224960 package with its
original 32-bit Windows DOSBox SVN under the same pinned Wine 11.4 source used
by this project. DOSBox native screenshots establish the title menu and the
Caves level; targeted keys start New Game, move Lara and open the inventory.
This is a local Wine/gameplay control, not a Vision Pro performance or audio
result. No game data or binaries are included in Git.

The default vendor configuration requests Direct3D/Glide. The validated fallback
uses SDL 1's `windib` driver, `output=surface`, `scaler=normal2x`, windowed mode,
`autolock=false`, `glide=false` and `ne2000=false`. The vendor software executable
is `TOMBRAID/TOMBno3Dfx.EXE`; its actual DOS directory alias is `TOMBNO~1.EXE`.
Passing the long filename to DOSBox produces an illegal-command error instead
of starting the game.

`SteamDOSBoxCompatibility.swift` applies only to app 224960's root DOSBox launch
option. It verifies the required installed files and an unambiguous software
filename, then writes a small settings file to the app-owned prefix path
`C:\AVPPlaySteam\Compatibility\224960\software.conf`. Existing game files,
vendor configuration files, saves and Steam installation records are preserved.
Optional native Tomb Raider launchers and other applications are unchanged.

Additional DOSBox configuration files append their `[autoexec]` sections; they
do not replace the vendor commands. A controlled execution confirmed both
sections run. The compatibility arguments therefore add the settings file with
`-conf`, suppress configuration autoexec with `-noautoexec`, then supply each
command once with `-c`: mount C at the current game root, mount GAME.DAT as the
CD image, switch to C, enter TOMBRAID and run TOMBNO~1.EXE. Valve's normal Steam
launch request retains the selected option and its working directory. These
arguments remain subject to the existing 2047-byte launch-host bound. They do
not override a Steam refusal or mark an incomplete install as complete.

The SDL environment setting is limited to this app and DOSBox option. It is not
appropriate as a global setting for SDL 2/3 games. The desktop monitor defaults
to 1280×720; Tomb Raider retains its original 4:3 game image.

The flat Tomb Raider window includes a scoped **Sense controls** toggle. Either
stick moves/turns; trigger is action, primary button is jump, secondary button
draws weapons, grip walks, menu/options opens inventory, and stick click
confirms a menu. Disconnecting, disabling the toggle, leaving the window, or
ending the session releases held controller keys. Other flat applications and
the existing VR controller path are unchanged. Local mapping/input contracts
and the visionOS SDK typecheck pass; Sense input in the actual headset game
still requires verification.

A paired keyboard also provides original controls: arrows move/turn, Ctrl is action,
Alt is jump, Shift walks, Space draws weapons, and Escape opens the inventory.
Enter confirms menus. Physical key down/up events are supported by the desktop
view; the visionOS text keyboard is primarily for text entry. The text keyboard does not replace held game-controller movement.

Headset gameplay, sustained performance, Sense/keyboard input and audio still
require verification in the combined main app. Earlier Steam attempts reported
client error 19/update-wait before DOSBox execution, with StateFlags 36
(Fully Installed + Files Missing) and an absent optional tombub.exe.

On 18 October, the installed r6 main app completed the normal Steam Update /
Repair operation for app 224960 (diagnostic status 14, then 0). A fresh device
manifest read confirmed StateFlags 4 (Fully Installed); the repaired game root
contains DOSBox, its vendor configurations, GAME.DAT and GAME.GOG. No appmanifest
was hand-edited. The first repair attempt was interrupted when another VR launch
made the runtime busy; the subsequent uninterrupted repair completed.

The following Tomb Raider launch request failed in visionOS's app-opening
service (CoreDevice 10002 / FBSOpenApplicationService error 5), after which
Xcode reported the headset unavailable. The user subsequently confirmed that
the headset battery had run out and it was restarting. This is not evidence
that DOSBox or Tomb Raider executed or crashed on the headset. Preserve that distinction when
reporting compatibility. The local build evidence directory contains
tomb-repair-retry-monitor/result.json, tomb-repair-success/ and
tomb-dosbox-launch.json; raw device evidence is not committed.

For repeatable developer repair checks, the explicit diagnostic launch argument
`--steam-repair-test=224960` opens the normal Steam library and requests its
existing Update / Repair operation for this owned, installed game. Diagnostic
logging records only the app ID and numeric status. It does not launch Wine or
forge installation state. Success is tied to the actual normal installer
completion; existing queue entries and user account checks are preserved.

## Opt-in local integration and provider controls

`windows-vr-tools/test_tomb_dosbox_wine.py --help` describes the opt-in macOS
integration runner. Supply a pristine owned game directory, an external build
directory, the pinned MinGW toolchain, the verified local Wine/FreeType build,
and the stock prefix template with its SHA256. The runner rejects output inside
the game directory before writing anything, rejects game symlinks, clones the
game into a fresh isolated prefix, and checks every original file afterwards.
It never uses a Steam account or the installed application's prefix.

The runner compiles the production compatibility helper, executable resolver,
scoped environment, complete controller-to-VK mapping, and held-key transition
method. It uses real GameController SDK button constants with scripted controller
states. An owned Win64 parent starts the original bundled x86 DOSBox using the
production settings and flattened command line; targeted Win32 keys go only to
that child's SDL window. Physical controller sampling and the visionOS native
key sink remain outside this local test.

Capture selection is required: `--capture-method native` uses DOSBox's Ctrl+F5
screenshots. Ctrl is also Tomb Raider's action/confirmation key, so these images
cannot establish menu confirmation or inventory closure solely from mapped
input. Checkpoint names describe requests, not visual assertions. The experimental
`--capture-method gdi` reads only the owned child window; its initial actual test
returned an all-black image and was rejected, rather than accepted as game pixels.

The 18 October forward-first run used unchanged vendor `core=auto` and the
production software settings. It reached the title, opening movie and Caves.
Images show running into the open corridor, standing after the forward key was
released, and a subsequent turn with camera settling after release. The owned
protocol completed with no held keys; all 136 original game files were unchanged.
Visual review is separate from the runner's bounded protocol result:
`harnessPassed` does not automatically mean gameplay passed. No headset, physical
Sense, audio, frame-rate or fresh-prefix-initialization result is implied.

Earlier isolated launches intermittently faulted before the first mapped input.
A bare DOSBox prompt and paired normal/auto core controls also ran successfully;
there is no established core-setting fix. Raw failures are retained separately.
`windows-vr-tools/test_dosbox_provider_wine.py --help` provides narrower genuine
QPC and SDL controls: direct x86 and Win64-parent launches, main/worker QPC loops,
SDL timer callbacks, and video/joystick/audio initialization. The final atomic
SDL probe passed all eight cases; QPC main/worker controls passed directly and
through the parent. Those results do not establish audio playback or explain
the intermittent game-startup fault. `--verify-receipts` only revalidates preserved
execution hashes and results; it does not execute a new test.
