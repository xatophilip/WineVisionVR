# Optional XInput DLLs for x64 Unity applications

The captured CyberThreat and Tilt Brush Unity player logs both try
`XInput1_3.dll`, then `XInput9_1_0.dll`, and warn that neither is available.
The signed r6 package contains the i386 versions but no ARM64EC versions.
The applications continue through input initialization and OpenVR startup, so
these warnings do not establish the cause of either game's loading stall.

The normal guest recipe now builds the genuine pinned Wine ARM64EC
`xinput1_3`, `xinput1_4`, and `xinput9_1_0` targets. The source/staged-farm
validators require all three as valid ARM64EC PEs. Existing DLL staging and
`guest_resource_files` include their exact hashes without a new allowlist or
receipt exception.

All three are necessary: Wine's 9.1.0 implementation dynamically loads
`xinput1_4.dll` from system32 and resolves its state, capabilities and vibration
entry points. A static PE-import check alone does not see that dependency.
The 1.3 and 1.4 targets compile the existing shared implementation, including
Madeira's host gamepad snapshot path. No controller state or game-specific
implementation is fabricated.

## Focused verification

`test_wine_xinput_packaging.py` executes the normal recipe's real module
invocation and pinned target/copy loop with only make/strip mocked. It checks
actual production resource validation, copying and receipt enumeration against
the genuine PEs; removing each module must fail validation and staging. It
checks all PE imports/forwarders and required exports, plus the dynamic 9.1.0
dependency. Its ASan/UBSan harness compiles the production host-state, state-query
and fallback-loader methods. The platform snapshot, HID discovery and loader
boundaries are mocked, including absent library/export cases. No-controller
queries return `ERROR_DEVICE_NOT_CONNECTED`; invalid indices or null state
return `ERROR_BAD_ARGUMENTS`.

```sh
python3 windows-runtime-plugin/Tests/test_wine_xinput_packaging.py \
  --runtime-source /absolute/path/to/prepared-runtime \
  --resource-source /absolute/path/to/compiled-Madeira-farm \
  --build /absolute/path/to/new-external-contract-output
```

The check is also registered in test_local.py when the prepared runtime has
all three genuine ARM64EC PE fixtures; source-only runs report an explicit skip.

On 18 October 2026, the three real ARM64EC targets compiled with the r6 pinned
LLVM-MinGW toolchain and normal `build/wine-pe/build-modules.sh`, using two jobs
in a private APFS clone. The focused contract passed with a 105-PE closure.
This targeted build inherited other clone outputs and is compile/test evidence,
not new deployment provenance.

A supplementary owned probe executed the exact signed-r6 i386 versions under the
verified local Mac Wine host in a new isolated template prefix. All three DLLs
loaded, required exports resolved, all twelve module/index queries reported
disconnected controllers, invalid/null queries returned the expected errors, and
the probe exited zero. The source and staged module hashes remained unchanged.
This is i386 host execution, not execution of the new ARM64EC DLLs, FEX, or
physical controller input. Fresh prefix bootstrap was not tested.

External evidence is under
`/Volumes/XRDev/build/WineVisionVR/xinput-oct18`: `arm64ec-build.log`,
`contract-final/contract-receipt.json` and `mac-probe-result.json`, with the
owned probe source, runner and raw outputs alongside them.

The guest recipe and staging policy are modern-profile integration fingerprint
inputs. A normal fresh baseline/modern build and matching native/guest/staging
receipts are required for the next package under the current model. The r6
artifact and its receipts remain unchanged; the private three-target build does
not relabel them. Game loading, VR rendering and actual controller behavior
remain unverified by these checks.

## Normal fresh signed r7 package

The subsequent full baseline/modern pipeline completed on 18 October 2026 from
app/runtime source `f60825a3f97854b2a2de82d99fc6cd3e1b53c05d`. It rebuilt native,
guest and graphics outputs normally, with no compiled-runtime reuse or resource
overlay. All three new genuine ARM64EC DLL hashes agree between the normal
source guest receipt, packaged Runtime farm and production-method contract.
The complete audit validates 19 native archives, 998 source guest payloads and
1,121 packaged files, plus the original main-app signing identity/profile and
deep strict signature.

The real r7 resources passed the 105-PE XInput closure, dynamic-fallback, required
exports, production staging/copy/ledger, each-missing-DLL negative checks and
production-method ASan/UBSan contract. Retained native-child, native-import and
WMIC production contracts also passed with the fresh outputs. These are
compile/package and host contract results, not execution of ARM64EC XInput on
the headset or proof that a game now loads.

The signed app UUID is `EB1AD993-6EE1-3FCC-900E-FC2727A2EFE3`; its runtime plugin
UUID is `1BF91AF5-E9CC-3D61-A265-B6583A082A5A`. External receipts are under
`/Volumes/XRDev/build/WineVisionVR/xinput-oct18-r7`: `build-inputs.json`,
`verified-app-complete.json`, `artifact-handoff.json`, `validation/result.json`,
`validation/app-files.json` and `validation/xinput-production-packaging/contract-receipt.json`.
The completed rich app audit SHA-256 is
`99f242d933dc49b669664fa1d99547c8a5fb4aa6c057bfbaea17d528a1830eed`.
The battery-depleted headset was not used for the r7 build/audit; installation
and device/game acceptance remain pending.

All six exact r7 packaged Windows-PE controls also passed under the verified
local Mac Wine/Rosetta host in new isolated template prefixes: x64/i386 GDI
(input/edit/button/save/load/UTF-8), x64/i386 CPU arithmetic/event, and direct
i386/mixed x64-parent SEH with continuation and exit zero. Before and after
execution, the runner verified the rich app audit, input/source archive hashes,
all 1,121 app files, seven exact packaged PE hashes, executable/plugin UUIDs and
hashes, profile and deep strict signature. No packaged bytes changed. These
checks execute Windows fixtures on the Mac; they do not execute the r7
visionOS/FEX/ARM64EC runtime or measure headset FPS.

The first local run failed the i386 fixture's exact-one-click assertion after
an additional counted click; the trace also records the accepted injected pair.
That failed result remains preserved. An unchanged fresh-prefix retry passed all
six controls. Its results, exact app binding and linked original failure are in
`/Volumes/XRDev/build/WineVisionVR/final-r7-local-controls-oct18-retry1/`:
`final-six-local-result.json`, `signed-app-fixture-binding.json` and
`final-audit-link.json`. The separate packaging unit suite passed all 68 tests;
its log and result are in `host-final-oct18/` beside the other build evidence.
