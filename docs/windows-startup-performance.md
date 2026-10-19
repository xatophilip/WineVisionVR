# Startup performance investigation (2026-10-19)

The user confirms Windlands reaches a visible menu/game and works in the installed r15b build, but startup is slow. Current logs bind plugin A978C539-3048-364A-81CB-BC4D855B5E5D. This is a loading regression, not a failed-launch compatibility result.

## Measured baseline

Native PID 1561 accepted launch at 13:32:38.648. Wineserver started at 13:32:54.732, Steam reached entitled-launch readiness at 13:33:05.636, and its launch request succeeded at 13:33:07.267. No VR frames had arrived by 13:33:09.703. Presentation and thread logging then nearly stop for about 54 seconds; first positive capture has 318 completed VR frames at 13:34:08.867. Another launch reproduces a roughly 53-second pause. Two launcher windows correspond to one native WineVision process, not two Wine runtimes.

StikDebug's independent log attributes the initial pause to preparing the 640 MiB JIT arena: 40960 page writes served and verified in 10.75 seconds, plus about five seconds before the serve begins. Its implementation already batches 512 commands and bulk-reads replies. Skipping page preparation, increasing batches blindly or caching prepared addresses would risk correctness and is not part of this change.

The later 54-second pause is not yet causally attributed. High-frequency debugger exception servicing is a testable candidate; successful startup does not establish smooth performance afterward.

## App-owned debugger policy correction

The upstream script sends its ignored-exception request after vAttach, where Apple's debugserver returns E35. It also uses a semicolon where debugserver expects a pipe delimiter. Both failures are confirmed by the captured helper log and the primary LLVM implementation:
https://github.com/llvm/llvm-project/blob/main/lldb/tools/debugserver/source/RNBRemote.cpp#L2162

MadeiraDebuggerScript composes a small policy prelude before the unchanged upstream script. It requests only EXC_BAD_ACCESS|EXC_BAD_INSTRUCTION before attachment, records one accepted/refused status and preserves the existing script on unsupported/throwing helpers. Native JIT breakpoints remain intercepted. EXC_SOFTWARE is deliberately excluded: changing routine signal routing needs a separate real signal-delivery test, despite the potential performance benefit. No native Wine/FEX binary, JIT allocator, arena bounds or failure guard changes.

The production Swift composer and actual packaged JavaScript are executed in a controlled protocol harness. Thirty-six scenario/mode comparisons cover accepted/refused/empty/throwing policy responses, JIT allocation, modern and legacy BRK, original software signals, raw faults, resource advisories and repeated-fault termination. The upstream suffix and subsequent protocol behavior match the baseline exactly. This proves composition/protocol preservation; headset loading time must still be measured.

## DOSBox / Tomb Raider

The user also reports poor DOSBox performance. This path translates the Windows emulator and emulates the DOS CPU inside it. Existing actual local logs already show cycles=auto switching to max 100%; simply setting cycles=max would not remove this cost. The resolved auto CPU decoder is not proven by those logs, so neither a guessed fixed-cycle limit nor an unmeasured forced CPU core is introduced.

The app-owned Tomb Raider compatibility profile changes scaler=normal2x to scaler=none, retaining surface output and Glide disabled. This removes an optional CPU scaling pass and leaves final flat-display scaling to the host. Existing title/level captures are already 640x480, so the scaler may be bypassed in some modes; no fourfold speedup is claimed. The vendor game/configuration files, saves, Steam account and launch command remain unchanged. Actual adapter and pinned Wine CommandLineToArgvW contracts pass; local rendering/input and headset performance remain separate gates.

Evidence is retained externally under headset-oct19-windlands-startup and startup-policy-oct19. Neither the debugger policy correction nor the scaler change is claimed to have improved headset timing until the new build is measured.

## Physical r16 result and guarded signal follow-up

The signed r16 app (source bd1973764760751f9836fac328eb28d99dbf5bcf, app UUID DFE2BA30-1FA0-31A1-AC20-041B255CC6C8) installs successfully. StikDebug confirms the pre-attach two-exception policy is accepted. Windlands emits two loading frames about 30 seconds after runtime acceptance, but then repeats a 54.664-second whole-process pause. Sustained rendering resumes about 90 seconds after runtime acceptance. The user reports a glitched loading screen, then a working game. The two early frames are not game readiness; the main startup delay is NOT fixed by the two-exception change.

The helper log records at least 500 routine soft-signal stops during that startup. A guarded follow-up additionally permits SOFTWARE exceptions to retain the original kernel delivery path only if a fresh pre-attach query proves that all existing task SOFTWARE exception ports are null, both SIGUSR1/SIGUSR2 dispositions are default or ignore, and neither signal is blocked on the requesting thread. Query failure or an existing port/custom handler/mask preserves the conservative two-exception policy. Every acquired port send right is released. BREAKPOINT is never included in the ignored mask.

This distinction follows Apple's kern_sig.c/exception.c BSD signal path, which retains the original signal number when no task SOFTWARE port exists. It must not be generalized to arbitrary existing exception handlers. The app does not change those handlers or the underlying native runtime.

An explicit --jit-signal-self-test is provided for a fresh process before any Wine launch. A tiny C handler only updates volatile sig_atomic_t flags. The diagnostic sends SIGUSR1 and SIGUSR2 to its own thread, confirms delivery, and restores the entire previous sigactions/mask. It is never run during an ordinary game launch. Unconfirmed delivery leaves benign handlers installed and latches a visible restart-required failure, preventing Wine startup or retries in that process; it does not restore a default handler while a signal may still be pending. The in-process polling deadline cannot bound a debugger's whole-task stop.

Actual local Darwin tests cover both real signals, custom/blocked eligibility rejection, complete action/mask preservation, real owned exception-port installation/restoration and send-right balance. A controlled held-signal test exercises the actual C failure path and real late delivery into retained benign handlers. Both policy choices execute the actual upstream JavaScript in 72 scenario/mode comparisons. These host tests do not establish physical signal delivery or a faster game start: the signed build must run its explicit signal diagnostic and real JIT cube before a new Windlands/The Lab timing comparison.

The user also confirms Tilt Brush accepted drawing in r16, then stopped. Its last capture shows about 31–38 new frames/s before the app backgrounds and the renderer is invalidated at 13:57:45. Repeated guest exceptions are retained for diagnosis; whether the view closed by user action or on its own remains unconfirmed. This is partial drawing evidence, not a stable-session pass.

## Physical r18 retest

The later installed combined package from `a08e0a25126dc831b696b4515ad0027a658f9b7e` passes the explicit real signal diagnostic in a verified fresh PID 605: result 0, SOFTWARE policy eligible true. Its cube produces stereo frames with zero sampled GPU failures and about 89.9 new frames/s. The native JIT breakpoint/arena path also executes. This supersedes the earlier locked/unreachable test checkpoint.

Fresh Windlands PID 611 accepts runtime launch at 18:56:10.452, with 65 submitted frames sampled at 18:56:25.353 (14.901 s), 320 at 18:56:30.364 and 1,636 at 18:56:50.387. The user confirms the menu/game is visible. The old roughly 54-second gap does not appear. Do not report this as an exact 15-second menu load: it is the upper bound for the first positive sampled frame counter. The r16 reference had two loading frames around 30 s and sustained game rendering around 90 s. This is one comparative run, without repeated cold/warm cache controls.

Tilt Brush reaches Standard and paints according to the user, but its display handoff remains jerky despite ongoing guest completion. In one five-second window, 222 guest frames complete and no new frames are acquired for display. The three-slot queue stays full and frames are dropped. A queue-overflow/readiness issue is under investigation; this installed package does not include that proposed repair. User-reported wraparound behavior is also unresolved.

Raw successful and failed command receipts and logs remain in `/Volumes/XRDev/build/WineVisionVR/headset-oct19-r18-retest`. Only successful nonempty captures support these measurements.

## Bounded frame-handoff repair, locally tested

Tilt Brush's captured producer latency exceeds three frame submissions: around 61 ms queued plus 12 ms GPU time at about 44 frames/s. The previous three-slot queue could discard every frame before its producer event signaled. Acquisition correctly refuses unfinished work, so simply waiting on the display thread would stall head tracking.

The queue now retains up to the existing six-ticket completion-window capacity. The outstanding-ticket bound remains six. A full pending window applies the existing nonfatal backpressure before allocating a ticket; it no longer drops the oldest unfinished frame to make room. This preserves bounded resource ownership, producer readiness checks, texture leases and ordered consumer completion. No field-of-view or projection matrix change is included.

The regression uses the actual production Objective-C++ bridge with real Metal textures/events and GPU command buffers. With the exact prior bridge, a frame finishing after the fourth submission has already been evicted and the test fails. The new bridge passes that case, full-window recovery, both V1/V2 APIs, out-of-order lease release, pause and stale-generation rejection. Existing compositor checks and the completion-window test (720 orders plus duplicate and boundary cases) also pass.

Reproduce on a Metal-capable Mac:

```sh
python3 windows-vr-tools/test_compositor_backpressure.py --build /path/to/fresh/external/test-output
```

The runner can accept an immutable prior bridge source with `--baseline-source` to verify the expected original failure. Captured evidence is under `/Volumes/XRDev/build/WineVisionVR/compositor-backpressure-oct19/reviewed-contract/result.json`. Production bridge syntax/type checking against the actual visionOS 27 SDK also passes (`reviewed-contract/visionos-syntax-result.json`). These checks establish the queue repair locally; they do not prove headset frame rate or resolve the user-reported missing scene when turning the head. The installed r18 app does not yet contain the queue patch.
