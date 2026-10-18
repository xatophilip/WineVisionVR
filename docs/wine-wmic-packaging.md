# Wine WMIC package

Tilt Brush's captured 18 October player log reports `wmic.exe bios get serialnumber`
failing with file not found during `App.Awake`. The captured package lacked
WMIC and its WMI provider; the pinned Wine source implements this path.

`build_wine_guest_resources.sh` enables and builds Wine's ARM64EC `wmic.exe`
program and `wbemprox.dll` from the same prepared Wine tree. WMIC's `bios` alias
selects `Win32_BIOS` through `CLSID_WbemLocator`, an in-process COM provider,
`ROOT\CIMV2`, and WQL. No replacement WMIC executable or custom query response is
introduced. The build checks these roots' static PE imports, delay imports and
export forwarders against the packaged farm, including their transitive providers.

The existing validated prefix template registers WbemLocator at
`C:\windows\system32\wbem\wbemprox.dll`; Wine's PATH includes that directory.
Madeira's existing `WineProcessBridge.m` links these flat farm files into the
appropriate `system32\wbem` directory. Packaging needs no registry or bridge edit.
Only the ARM64EC package used by this x64 game is extended here.

The upstream `fill_bios` implementation queries `GetSystemFirmwareTable` for
several BIOS fields, but `SerialNumber` is its existing literal `Serial number`.
That placeholder is preserved and is **not a physical hardware identifier**.
Whether it satisfies this application's expectations remains untested.

`test_wine_wmic_provider.py` runs actual WMIC alias lookup and BIOS provider
population under ASan/UBSan, with firmware/table/SMBIOS boundaries mocked. It also
executes the production program target/copy loop with make/strip mocked and checks
the existing prefix's COM registration when a prefix template is supplied. It
neither runs Wine nor establishes COM activation on the headset. The normal guest
build must produce the real binaries and pass its PE closure check before staging.

Tilt Brush also reports trust failures and unsupported animated-logo video, and
later managed null references. Packaging WMIC addresses the observed missing
process; it does not establish that loading or gameplay succeeds. No certificate
validation, game file, account data, or hardware identity behavior is changed.


## Staging and the r5 composite package

Both `stage_resources.py` and `resource_receipt.py` explicitly allow `wmic.exe`.
Building the program alone is insufficient: the original staging policy excluded
unlisted executables even when they existed in the compiled farm. The WMI
contract exercises the actual `copy_builtins` and `guest_resource_files` functions
against fresh PE resources, checking exact WMIC/provider hashes and retaining the
exclusion of unrelated ARM64EC executables.

The 18 October r5 runtime was built normally from commit `6aa5f44`, with fresh
baseline/modern profiles and native/guest archives. Its original staging omitted
WMIC. The final app therefore preserves those original runtime receipts verbatim
and adds the exact freshly built WMIC PE as an explicit resource overlay. A
separate `Runtime/AVPPLAY_WMI_RESOURCE_OVERLAY.json` records its raw build target,
strip tool/output hashes, baseline and app commits, and the 62-provider static
import/forwarder closure. The final app also carries the exact locally executed
mixed/direct SEH diagnostic payloads and their separate fixture build receipt.
Prior test result markers are excluded.

The composite audit validates the inherited runtime using its frozen build tools
and binds the newer app/packaging snapshot separately. It proves that the only
changes in the two staging modules are the WMIC allowlist additions. Those files
are included in modern integration fingerprints, so the old modern receipt is
not represented as a build of the newer packaging snapshot. Neither the original
native nor guest receipt is edited or regenerated to make that claim. Future
fresh builds use the corrected normal staging policy directly.

These checks prove packaging and provenance. They do not prove headset COM/WQL
query execution or successful Tilt Brush loading.

## Actual local COM query control — 18 October 2026

A separate APFS clone of the validated local Mac Wine build executed the real
Win64 `wmic.exe bios get serialnumber`, using normal stock WbemLocator COM
registration, `ROOT\CIMV2`, and the actual `SELECT serialnumber FROM Win32_BIOS`
provider path. It exited 0 and returned `SerialNumber` / `Serial number`. The
value remains Wine's upstream placeholder, **not a physical hardware identifier**.
No provider, firmware or query boundary was mocked. The checked WMIC/provider
sources are byte-identical to the prepared r5 sources.

The scratch build added same-source WMIC, wbemprox, winspool and compstui targets
with at most two jobs. A first activation failed because compstui was absent;
that attempt is retained alongside the successful second fresh-prefix query.
Both prefixes used the verified stock registry template; fresh prefix bootstrap
was not tested. All 5,022 baseline validated-host build files and checked source
files remained unchanged. No user prefix or device was involved.

All 30 local eager PE provider names are present in the final r5 ARM64EC
62-provider closure, including `winspool.drv` and `compstui.dll`; all 62 packaged
files match their recorded hashes. No missing EC PE provider was found. Mac
native/Unix backends differ from visionOS, so this result does not establish
headset COM activation, other WMI queries, or game acceptance.

The external evidence is
`/Volumes/XRDev/build/WineVisionVR/local-wmic-oct18/actual-wmic-query-receipt.json`,
with raw failed/successful attempts and `final-r5-provider-comparison.json`
alongside it. This documentation follow-up is separate from the frozen r6 app
source snapshot `9c5e214`; it changes no app or runtime build inputs.
