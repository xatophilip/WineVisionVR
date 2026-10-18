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

Headset launch, sustained performance, keyboard input and audio still require
verification in the combined main app. The last captured Steam attempt reported
client error 19/update-wait before DOSBox execution. A subsequent read finds
StateFlags 36 (Fully Installed + Files Missing); Steam content_log records the
earlier failed attempt to launch the absent optional tombub.exe. The existing
normal Steam update/repair path must verify the installed depot and complete
its install record before retrying. The app must not hand-edit an appmanifest
to bypass it.

For repeatable developer repair checks, the explicit diagnostic launch argument
`--steam-repair-test=224960` opens the normal Steam library and requests its
existing Update / Repair operation for this owned, installed game. Diagnostic
logging records only the app ID and numeric status. It does not launch Wine or
forge installation state. Success is tied to the actual normal installer
completion; existing queue entries and user account checks are preserved.
