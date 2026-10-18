# WoW64 Mono alias bridge handoff

## Observed failure and integration gap

The signed r13 Audioshield capture on 2026-10-18 reached 32-bit Mono startup and then Unity's crash dialog. The current runtime was native PID 1076 with plugin UUID `A0A454AF-8C4A-3989-B2D9-7D91BC95E49A`. Its native log refused an unaligned `SWPAL w4,w4,[x24]` (`b8e48304`) at guest address `0x7903340207`, despite a live native RW alias. The reconstructed guest exception and Unity `error.log` agree on `kernel32!InterlockedExchange+8`, `LOCK XCHG [edx],eax`, reading guest address `0x03340207`. The copied minidump contains only its 32-byte header, so it provides no additional thread or memory evidence.

The native alias table and the ARM64EC backend's table binding do not initialize the separately linked WoW64 FEX backend. The existing `BTCpuIosSetMonoBridge` export had no caller in Wine's WoW64 loader. Its local bridge pointer therefore remained null, causing the strict 0017 gate to reject even a valid live alias. This is a source-proven missing initialization path consistent with the captured failure; the new build still requires device verification.

## Normal source fix

`0019-wow64-mono-bridge-handoff.patch` adds a private native ARM64 NTDLL getter around the existing `unix_ios_mono_bridge_ptr` Unix-call ordinal. It does not add or renumber an ordinal. Wine's WoW64 loader resolves this getter from native NTDLL and the existing setter from the CPU backend, translates both call targets with the existing JIT-pool helper, and hands over the full 64-bit host pointer after `BTCpuProcessInit` returns, before mapping or initializing guest NTDLL.

Missing optional exports, an unsuccessful getter, and a null result skip the handoff. The existing FEX setter checks the bridge ABI before binding and publishing the table. This patch does not weaken 0017's JIT identity, instruction, alignment, alias-generation, footprint, or PC-advance checks. Unsafe emulation still follows the existing guest exception and cleanup path.

`prepare_runtime.py` includes every normal runtime patch in preparation and its fingerprint, so 0019 needs no overlay or separate binary injection.

## Reproducible host contract

Run on an ARM64 Mac with Xcode command-line tools, using external build and temporary directories:

```sh
TMPDIR=/absolute/external/tmp python3 windows-runtime-plugin/Tests/test_wow64_smc_atomic.py \
  --runtime-source /absolute/prepared/runtime-modern \
  --build /absolute/external/contract-output
```

The contract privately applies 0017 and 0019 to copies of the prepared sources. It compiles the actual native getter, WoW64 initializer, FEX setter, alias resolver, gate, decoder and atomic helpers under ASan/UBSan. Controlled boundaries represent the Unix call and thread/JIT identity. It verifies missing getter/setter, getter error, null pointer and ABI mismatch; a real host pointer above 4 GiB; initialization order and pool translation in the actual loader; then the recorded offset `0x207` exchange, old/new values, PC+4, canaries and 4,000 contended exchanges. The complete reset-function contract also verifies false-result exception reconstruction, context restoration, unlocking and scoped-lock release.

The 2026-10-18 execution passed at:
`/Volumes/XRDev/build/WineVisionVR/atomic-control-oct18/bridge-handoff/smc-atomic-ghnd1jwp/result.json`.

The complete privately patched `signal_arm64.c` and `wow64/syscall.c` translation units also passed syntax-only checks using the actual prepared ARM64 Wine Makefile flags and pinned LLVM-MinGW compiler. The adjacent `wine-syntax-result.json` records commands, source hashes and unchanged original inputs.

These are host production-function and compilation checks. They do not prove a newly linked native runtime, Mach fault delivery, headset execution, or Audioshield gameplay. Preserve r13's captured failure and verify a fresh normal build separately.
