# Recent game failures and local fixes — 19 October 2026

Deployment update: the combined r20 build from fac9df59 was subsequently built
from source, signed, independently package-verified and installed in place on
Vision Pro. The investigation below records the pre-deployment findings; no new
r20 gameplay pass is claimed. See [current status](windows-vr-status.md).

## Scope and installed baseline

Reviewed the newest 20 retained session journals, current/rotated runtime logs,
launcher counters, and Fantastic Contraption's own Player.log. Evidence was
copied from the paired headset without launching or interrupting another game.
The installed r19 package remains unchanged. Space Pirate Trainer, Tilt Brush,
Windlands and Job Simulator retain their user-confirmed PASS results on r19;
the source changes below are not new headset passes.

## Fantastic Contraption (PID 881)

The first positive sampled frame counter is 306 at 19:35:27.788. The following
window reaches about 85.8 fresh transfers/s, then counters stop at 734 submitted,
718 acquired and 16 dropped. They remain unchanged for over 45 seconds. All
2,331 guest GPU commands have completed, with no captured GPU failures and no
queued frames. Head tracking and host presentation continue. This is a guest
execution stall, not the previously repaired Tilt Brush frame queue congestion.

The runtime contains eight successful OVRPlugin image mappings of about
26.8 MiB each, followed by failed imports of MSVFW32.dll, AVIFIL32.dll and
AVICAP32.dll. The next image cannot fit in the bounded JIT pool. Execution
preparation fails, yet loading proceeds into TLS; the next unhandled write
fault remains the main thread's sampled PC. Player.log independently reports
OVRPlugin dependencies could not be loaded and DllNotFoundException.

Two repairs address distinct parts of that sequence:

- The normal guest resource recipe builds the three genuine ARM64EC Wine video
  libraries. An isolated source compile passes CHPE/architecture and complete
  import/export-forwarder checks: 250 direct and 9,215 recursive symbols resolve.
  See [video dependencies](windows-video-runtime.md).
- Native overlay 0020 returns failed executable preparation through Wine's
  existing image-load cleanup before registration/imports/TLS. It preserves
  process-lifetime quarantine of published code; it does not enlarge the pool
  or reuse potentially live mappings.

The native regression executes the actual protection tail with injected
allocation/protection failures. The old source incorrectly reports success in
five cases; the patch passes, including non-iOS behavior and errno preservation.
Its caller/TLS counters model the inspected caller boundary; this is not a full
Wine loader or headset execution test. The native archive must be rebuilt.

## The Lab (PID 856)

The game renders briefly with sound, then stops at 677 submissions / 641
acquisitions with an empty queue and all 3,844 guest GPU commands complete.
The runtime records a hidden fatal OpenComposite dialog identifying
TriggerHapticVibrationAction. The original numeric OpenXR result was not retained.
Six preceding geometry stream-output errors are observations, not a proven cause.

Local haptic repairs:

- OpenXR returns the specified positive SESSION_NOT_FOCUSED result without
  output when unfocused. Valid actions without a bound output device can succeed
  without vibration. Invalid handles, types, paths, parameters and actual bridge
  failures remain errors.
- OpenComposite overlay 0013 converts seconds to signed 64-bit nanoseconds.
  Its original 32-bit cast overflows at a three-second request under UBSan.
  The patch rejects nonfinite, negative and unrepresentable durations before
  conversion; valid zero, hand restriction and XR failure handling are retained.
- Bounded failure diagnostics record operation, phase, numeric XR result and
  relevant duration/transport error. Successful calls produce no extra trace.

Actual-function input and OC tests pass under ASan/UBSan. Genuine Windows
OpenXR targets compile and link for ARM64EC, x64 and x86. These fixes address
confirmed defects around the failing path; they do not establish which defect
caused the original Lab error or establish a gameplay pass.

Primary contracts: [xrApplyHapticFeedback](https://registry.khronos.org/OpenXR/specs/1.1/man/html/xrApplyHapticFeedback.html)
and [xrStopHapticFeedback](https://registry.khronos.org/OpenXR/specs/1.1/man/html/xrStopHapticFeedback.html).

## Earlier failure feedback and retained logs

The host log monitor now recognizes the exact OpenComposite fatal-window title
and the exact fatal renderer-initialization dialog after identifying the
current native process and game. The original Lab, Fantastic and Destinations
captures pass through the production Swift reader with their intended
fatal/nonfatal distinctions. Stale logs, other native PIDs, generic
warnings and normal exits remain excluded. Window traces lack a guest PID:
this is a session-level fatal notice, not proof of which helper opened a dialog.
The host retains the native session for deliberate user recovery; detection
does not automatically quit or restart it.

A separate CRLF bug discarded both bounded samples of long Windows logs:
Swift treats CRLF as a single Character, so searching for a standalone LF failed.
The journal now normalizes CRLF in its bounded samples before discarding partial
lines. A greater-than-64-KiB CRLF fixture fails before the fix and passes afterward,
including a secret crossing the sample boundary, startup/tail retention, source
isolation, symlink rejection and retention/export limits. This prevents a repeat
of the empty 82,336-byte Lab OpenComposite journal. Previously lost text cannot
be reconstructed from that journal.

## Performance conclusions and next validation

These recent stalls should be fixed before reducing rendering quality.
Fantastic briefly sends frames quickly before execution stops; Lab's producer
also stops with GPU work complete. Increasing the JIT arena or lowering eye
resolution would not repair either demonstrated failure.

The newly retained CyberThreat startup journal also records code-buffer
protection failures and an unhandled native exception. It is a candidate for the
native failure-path regression, not a confirmed shared cause or a new pass.
Google Earth VR's unsupported OpenGL route remains separate. Older failed logs
are not treated as regressions of the four currently confirmed working games.

Before deployment, build the native runtime/affected FEX translator with overlays 0020 and 0021, rebuild
OpenComposite with 0013 and all guest architectures, then use normal guest
assembly, fresh asset/provenance receipts, signing and package validation.
Do not replace DLLs in a previously verified app or reuse its resource receipts.
The real avicap32 uses Unix-call integration; actual loading and graceful
unsupported camera queries still need execution checks.

Retest stereo fixtures first, then the four working games, then Lab vibration
and Fantastic Contraption past OVR initialization. Capture cold/warm startup
separately, fresh guest frames versus host reprojection, GPU queue/failure
counters, and several minutes of controls/gameplay. Neither measured startup
improvements nor longer-session reliability are claimed by these local checks.

## Additional live failures captured during review

A refreshed capture records Audioshield PID 933, Tomb Raider PID 972 and
Destinations PID 977 after the initial 20-journal snapshot. Their raw current
and rotated logs are retained under headset-oct19-r19-retest/other-errors-review.

### Tomb Raider / DOSBox

The selected Steam title 224960 opens immersive VR even though the correct
software DOSBox command/configuration is passed to its child. It cannot send
stereo VR frames. The launch selection now forces this known flat title to the
desktop, retaining existing routing for other SteamVR games. The actual Swift
selection rule fails the new regression before the change and passes afterward;
the real pinned Wine command-line parser still preserves the DOSBox arguments.

The same attempt also has thousands of low-level fault records. Correct display
routing alone is not a claim that DOSBox performance or translation faults are
resolved.

### Audioshield and CyberThreat

Audioshield's current x86 modules reach valid two-eye D3D11 targets but encounter
a large fault storm. Five apparent missing ACM codec probes each subsequently
load their genuine bundled provider; more codec downloads are not justified by
those lines. Steam FFmpeg/SDL3 probes also occur in working sessions.

A real FEX Windows helper defect is repaired by native overlay 0021:
VirtualProtect now receives writable old-protection storage and reports nonzero
Win32 BOOL as success. Actual helper tests cover five protection combinations
with success/failure and unchanged error state. The old implementation fails
all ten provider cases; the patch passes under ASan/UBSan. This does not establish
that this defect caused every fault or fix Audioshield gameplay. Rebuild affected
native/ARM64EC translator components through normal recipes before claiming it
is in an app.

CyberThreat's retained fault is more specific: an unaligned eight-byte SWPAL
targets an existing writable alias at offset six within a 16-byte footprint.
The Mach emulator deliberately refuses it. Existing FEX atomic recovery is a
possible route to investigate, but callback delivery and context handling need
proof. No ordinary memcpy-based exchange, alignment-check bypass or speculative
recovery is introduced.

### Destinations

Its current game is steamtours.exe. WineD3D cannot initialize an OpenGL context
for D3D9, and a fatal RenderDeviceMgr001 Connect dialog follows. Both DX11 and
DX9 renderer modules load, so forcing DX11 is not established as a solution.
The health monitor now identifies this exact fatal dialog with stale/PID/game
guards and passes the actual PID 977 capture test. The unsupported graphics
initialization remains unresolved.

### Fault-dump overhead and careful classification

Current Audioshield/DOSBox logs report full 671,088,640-byte JIT dumps, including
two separate dump triggers in Audioshield. Those dumps run synchronously before
the Mach exception reply. The app now defaults the already-supported
MADEIRA_JIT_DUMP switch to zero, retaining compact logs and explicit value-one
opt-in. Production environment-default tests verify both paths; signal handling
is unchanged. This removes optional diagnostic I/O, not the fault itself.

A native "UNHANDLED" line means the Mach handler declined the exception;
downstream handlers can still recover. A single such record is deliberately
excluded from fatal health classification. Fantastic Contraption's real capture
passes that exclusion test and still receives the existing no-progress warning.
Only definite failure evidence such as the exact fatal dialogs, confirmed guest
error exits and repeated-fault termination is classified immediately.

Lab's unbound headset-on-head action is a separate presence-support gap.
Action counters represent reads, not a log line per read. Several skipped
bindings belong to unselected controller profiles. These observations do not
justify hardcoding presence or claiming otherwise working Sense controls fail.

## Reproducing the targeted checks

Use external scratch storage and the pinned prepared sources/toolchain:

```sh
export TMPDIR=/absolute/external/scratch
python3 visionos-windows-vr/Tests/Contracts/test_session_diagnostics.py --build "$TMPDIR/journals"
python3 visionos-windows-vr/Tests/Contracts/test_guest_session_health.py --build "$TMPDIR/health"
python3 windows-vr-openxr/tests/test_input_contract.py
python3 windows-vr-openxr/tests/test_action_lifetime.py
python3 windows-vr-openvr/tests/test_haptic_duration.py --source /path/to/pinned-opencomposite --build "$TMPDIR/oc-duration"
python3 windows-runtime-plugin/Tests/test_wine_image_exec_failure.py --runtime-source /path/to/prepared-madeira --output-dir "$TMPDIR/image-failure"
```

The new overlay tests are also integrated into windows-vr-tools/test_local.py
when its prepared runtime / OpenComposite source options are supplied.
Local evidence is retained externally under failure-review-oct19,
headset-oct19-r19-retest/latest-failures, video-oct19, haptics-openxr-oct19 and
haptic-semantics-oct19. These machine-local paths are evidence, not portable
build dependencies.
