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
