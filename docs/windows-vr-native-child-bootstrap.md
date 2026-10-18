# Native ARM64 ntdll for an i386 child of an x64 launcher

The native half of an i386 WoW64 process must use the genuine ARM64 ntdll and its native ABI. Patch `0016-wine-i386-child-native-ntdll.patch` gives an i386 child of an ARM64EC session a private ARM64 ntdll, matching the working top-level i386 path.

## Device evidence on 18 October 2026

The r5 headset direct control ran the owned i386 child through `RtlRunOnce`, a private continuable exception, its vectored handler and continuation. Its fresh marker reported one callback, one handler, valid i386 context/stack, `contextFlags=65599`, continuation and exit zero. The identical child launched by the x64 parent produced neither its before-exception nor final marker.

The mixed runtime log first shows the i386 child receiving a copy of the session's EC ntdll at lines 894–897. Its first unhandled fault at lines 1009–1020 executes `0x000000c3` at `ntdll.dll+0x87040`, called from native `libwow64fex.dll+0x1aa994`. The pinned binaries identify these as `ntdll!__chkstk` and the return after `_pei386_runtime_relocator` calls `__chkstk`. The EC export is the x64 `RET` byte `C3`; the genuine ARM64 export is the ARM64 `RET` instruction. The EC metadata has no native redirection for this export. Later faults in the exception dispatcher repeat 2,000 times before host exit 76. The first fault occurs during child bootstrap, before the probe reaches its explicit exception.

These observations support correcting the child's native ntdll choice. Patch 0015 can select a native body when EC metadata supplies one; it cannot provide a native implementation absent from that metadata. Fixed integer/pointer arguments beyond four agree in the pinned compiler's native calling convention, while variadic calls and architecture-specific `CONTEXT` APIs have additional differences. The implementation therefore keeps the native WoW64 closure on its native ABI.

The captured files and compile-only receipts are under the external build directories `child-loader-oct18-r5` and `dosbox-and-game-errors-oct18/native-context-child-draft`. They are local evidence, not repository assets.

## Implementation and preparation

The normal `prepare_runtime.py` recipe discovers the numbered patch and includes its hash in `integrationPatchSha256`.

- Map a private `aarch64-windows/ntdll.dll` before publishing the child's i386 ntdll/init data. Require native machine identity and required exports; install syscall/unix-call/TSD and reverse-JIT hooks. Publish process-owned dispatch entry points without changing the parent's session globals.
- Store `LdrSystemDllInitBlock` with those private entry points. Populate the private native block and its guest copy using guest addresses; use it when initializing the guest thread PC. Both private native and private EC constructors initialize the added field. Skip the session-ntdll clone when a private image already exists.
- Reject AMD64, ARM64EC and ARM64X identities in the native WoW64 loader before Wine's generic other-machine allowance. A normalized ARM64 view remains valid. This makes incompatible shared `system32` modules fail validation and permits the scoped retry through the existing `sysaa64` farm. Preserve i386/ARMNT mapping, COM allowances and the EC-compiled path.

The existing app bridge already stages `sysaa64`; the patch adds no resource directory or game/prefix edits. Native `load_apiset_dll` and the child API-set helper do not access the init-block pointer. The remaining native global references initialize the main session or provide fallback/log reads. WoW64's PE-side init-block pointer is resolved through that process's loaded ntdll.

This changes native `loader_ios.c`, `signal_arm64_ios.c` and `ios_mixed.h`, plus the pure ARM64 PE ntdll loader. A normal fresh native/guest build and its normal receipts are required by the current baseline provenance model. The previous native archive cannot be relabeled as a compilation of these inputs.

## Verification and limits

`test_native_child_bootstrap.py` applies or reverses the actual patch only in test scratch, compiles production mapper/init-data/selection/retry code with ASan/UBSan, and uses the pinned Wine init-block layout. Negative controls reproduce the original parent-block mutation and acceptance of an EC DLL by native WoW64. The checks cover private dispatch/JIT slots, guest addresses, parent preservation, missing exports, relocation, wrong-machine/map failure, selection scope, native WCHAR width, and 224 predicate combinations for each native/EC compilation. Optional real PE checks verify required exports and the unmapped EC `__chkstk` boundary.

```sh
python3 windows-runtime-plugin/Tests/test_native_child_bootstrap.py \
  --runtime-source /absolute/path/to/prepared-runtime \
  --resource-source /absolute/path/to/Runtime \
  --build /absolute/path/to/external-contract-output
```

The test is also registered in `test_local.py`. A source-only overlay reports explicit skips for unavailable PE fixtures.

Both complete changed native translation units and the ARM64 ntdll PE compiled with the pinned XROS 27.0 SDK/LLVM-MinGW in a private APFS clone. An initial Darwin-wide-literal compilation error was corrected with the existing explicit 16-bit WCHAR-array pattern. This compile-only check inherited unchanged archive members and did not produce deployment provenance.

The corrected runtime has not yet passed the headset mixed control. Fresh-package direct and mixed controls, including the handled exception and continuation, remain required. This change establishes no game compatibility or rendering success. Existing broader pseudo-process globals and concurrent child limits remain outside this fix.
