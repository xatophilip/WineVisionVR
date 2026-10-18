# Wine WMIC package

Tilt Brush's captured 18 October player log reports `wmic.exe bios get serialnumber`
failing with file not found during `App.Awake`. The current ARM64EC farm lacks
both WMIC and its WMI provider, while the pinned Wine source implements this path.

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
