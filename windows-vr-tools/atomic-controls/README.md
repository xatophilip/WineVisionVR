# Owned i386 atomic controls

`atomic32.exe CASE TOKEN` runs exactly one case in its current writable directory.
`parent64.exe CHILD_PATH CASE TOKEN` launches that same i386 child from Win64,
waits at most 20 seconds, and verifies its exit and markers. Use a new directory
and an alphanumeric/underscore/hyphen token of at most 64 characters. Existing
markers are refused; none are overwritten or deleted.

Cases are `rw-aligned`, `rw-unaligned`, `rwx-aligned`, `rwx-unaligned`, and
`rwx-unaligned-execute`. Each allocates 1 MiB and calls the real kernel32 export
obtained with `GetProcAddress("InterlockedExchange")`. The counter is at offset
0x208 or 0x207. The executable variant first calls a small owned x86 return stub
on the same page. It does not execute game code or load Mono.

Three create-new JSON markers distinguish preparation, return from the optional
stub/before the exchange, and return after the exchange. Results include pointer
width, child PID, protection, offset, token, old/new values, a 64-byte canary check,
and exit status. Success requires old 0x11223344, new 0x55667788, intact surrounding
bytes, and exit 0. The parent also checks the child is WoW64. A timeout terminates
only its own child and is a failure.

The deliberately unaligned cases exercise the x86 LOCK XCHG behavior seen in the
Audioshield trace. They do not assert that Win32 documents unaligned Interlocked
API arguments as portable or generally supported. Mac Wine success proves the
owned PE protocol and observed x86 semantics; it cannot reproduce or validate an
iOS/FEX SMC/RWX-alias fix.

Run `python3 windows-vr-tools/test_atomic_wine.py --help` for the opt-in Mac runner.
It requires the pinned toolchain, an existing verified Wine/FreeType build, and a
stock prefix template with its expected SHA256. Every direct/mixed case receives
a separate isolated prefix and token; all output must be external to this source
folder. Bulk temporary data stays in the supplied external build directory. No
Steam account, game assets, user prefix, installation, or device calls are used.

On 18 October 2026 all ten direct/mixed local cases passed under the existing
verified Mac Wine WoW64 host. Both binaries also rejected reuse of a completed
case token with exit 4 and preserved the existing markers. Device/FEX execution
remains a separate control owned by the device operator. This helper is not part
of the normal app resource graph unless explicitly staged in a later diagnostic.
