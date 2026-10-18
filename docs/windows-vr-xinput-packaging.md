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
