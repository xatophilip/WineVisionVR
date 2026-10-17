# StikDebug dependency source delta

This separate helper is based on [StikDebug-visionos](https://github.com/rebelancap/StikDebug-visionos)
commit `8a7fc130b033dc1803313269ec3f9388cb63b7c7`, derived from
[StikDebug](https://github.com/StikDebug/StikDebug). Its source and this patch remain
under the included GNU AGPL-3.0 license, separately from WineVision's license.

`full-source-delta.patch` contains the complete local source changes used for the
17 October helper build, including earlier prepared-JIT-arena handling. The new
TCP repair uses nonblocking connect and a monotonic poll deadline, and prevents
timed-out targets entering another synchronous pairing connection. It does not
cancel an already-running pairing call or implement network-change monitoring.
No pairing records, keys, device logs or signing credentials are included.

To reproduce, clone that repository, check out the commit above, and apply this
patch with `git apply /path/to/full-source-delta.patch`. Then run:

```sh
python3 tools/test-tunnel-probe.py --build /external/build/tests
xcodebuild -project StikDebug.xcodeproj -scheme StikDebug \
  -configuration Debug -destination 'generic/platform=visionOS' \
  -derivedDataPath /external/build -allowProvisioningUpdates \
  DEVELOPMENT_TEAM=YOUR_TEAM PRODUCT_BUNDLE_IDENTIFIER=YOUR_BUNDLE_ID \
  CODE_SIGN_STYLE=Automatic 'CODE_SIGN_IDENTITY=Apple Development' build
```

Use Xcode 27 beta 3 or a compatible visionOS SDK and your own signing setup.
The pinned repository already contains the visionOS idevice archive. Applying
the patch was verified to reproduce all four changed Swift files and the test
byte-for-byte. Host checks passed for localhost refusal, held listener and reset,
and an actual pending TCP connect stopped after 0.202 seconds for a 0.2-second
budget. That last reserved-address test explicitly skips if routing rejects it
immediately. Host tests do not establish successful headset pairing or JIT.

The signed helper (UUID `F7CBA423-29ED-3A09-9917-DC8DA6B7872D`) was installed
separately on 17 October. Xcode's subsequent launch request timed out; successful
headset tunnel recovery and debugger attachment still require verification.
