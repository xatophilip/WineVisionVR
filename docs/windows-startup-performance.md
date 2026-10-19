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
