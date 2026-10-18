# 32-bit stock CSP prefix migration

The r14 Audioshield capture progressed past the recovered unaligned exchange, completed Mono reload and initialized OpenVR. It then logged `CryptographicException: Couldn't access random source` with `0x80090017` (`NTE_PROV_TYPE_NOT_DEF`). The copied prefix contained native crypto defaults but no corresponding 32-bit defaults. In this pinned Wine, these keys are redirected into Wow6432Node; there is no Crypto-specific shared-key exception.

An owned guest32 CryptoAPI probe reproduced the same failure in the verified stock template: default and explicit32 registry opens failed, explicit64 opens succeeded, and default provider types 1 and 24 both returned `0x80090017`. Genuine guest32 `rsaenh!DllRegisterServer`, with its actual ATL100 registrar available, created the stock defaults and made acquisition and random generation succeed. This establishes the registry/API defect; it does not prove the RNG error was the sole cause of the later Unity raised exception.

## Production behavior

`WindowsVRRuntimePlugin.mm` invokes `WindowsVRPrefixCrypto.h` after seeding and checking the prefix, before starting any wineserver or guest. It applies whenever the signed bundle contains an i386 `rsaenh.dll`, including a 64-bit Steam parent which will later launch a 32-bit child. An active Wine process/server prevents the migration.

The helper performs an **offline append**, not an on-device `DllRegisterServer` call. Its six stock provider records and provider types 001, 012 and 024 match the pinned Wine `dlls/rsaenh/rsaenh.rgs` and actual genuine registration output. The provider image path is the complete stock Windows path `C:\windows\system32\rsaenh.dll`, resolved through the guest32 filesystem view. No new guest module, wrapper, registry reset or launch mode is introduced.

The entire 32-bit `Software\Wow6432Node\Microsoft\Cryptography\Defaults` subtree must be absent. Any existing root or descendant, including an incomplete or custom provider configuration, is preserved without modification. Names are decoded using Wine-compatible key escapes and compared without ASCII case sensitivity. A lookalike `DefaultsBackup` key does not count as the defaults subtree. This gate also makes the migration idempotent.

Foundation resolves only the trusted Documents and signed bundle resource bases. The helper opens those bases directly, then walks relative descendants with `openat` and `O_NOFOLLOW`; it never needs to open `/`, `/private` or `/var` ancestors. It refuses prefix/hive/resource symlinks, hard-linked hives, nonregular files, invalid UTF-8 or embedded NULs, malformed section names, non-win64 hives, and input or resulting hives above 16 MiB. Nonblocking file opens ensure a FIFO cannot hang startup. The bundled provider must be a bounded regular i386 PE DLL.

The writer preserves all original hive bytes and appends only the stock records. It copies file metadata and permissions, holds a nonblocking exclusive lock, writes an exclusive same-directory temporary file, flushes it, verifies the original inode/content are unchanged, then renames atomically. Errors before publication remove the temporary file. The native64 defaults, unrelated registry data, `.update-timestamp`, credentials, saves and game files are not rewritten. Existing custom32 defaults require separate diagnosis rather than a forced stock overwrite.

## Validation

The ordinary local contract compiles and runs the actual helper under ASan/UBSan:

```sh
python3 windows-runtime-plugin/Tests/test_prefix_crypto_migration.py \
  --runtime-source /absolute/prepared/runtime-modern \
  --provider /absolute/app/Runtime/i386-windows/rsaenh.dll \
  --build /absolute/external/output
```

`--registered-hive` optionally compares an owned genuine guest32 registration output. The 34 cases cover absent/existing/custom defaults, exact size bounds, malformed/Win32 hives, module validation, symlinks/FIFOs, ancestor-open denial, flush/rename errors, concurrent content changes and temporary cleanup. All nine stock records are compared to the actual pinned resource. `test_local.py` runs this contract when prepared source, a genuine provider and Xcode are available, otherwise reports a dependency skip. `AVPPLAY_PREFIX_CRYPTO_PROVIDER` can specify the provider. It does not start Wine.

A separate fresh isolated MacWine execution applies the actual production helper, without invoking DLL registration, then runs genuine guest32 `CryptAcquireContext` and `CryptGenRandom`. The final helper changes both defaults from `0x80090017` to success, and the explicit enhanced provider also succeeds. A second helper call preserves the existing tree. The verified host runtime remains unchanged.

Final evidence is under `/Volumes/XRDev/build/WineVisionVR/crypto-provider-oct18/`: `migration-contract/prefix-crypto-qla1z9hg/result.json`, `actual-migration-api-final-result.json`, and `independent-review/xros-syntax-final-result.json`. These prove production helper behavior, the real MacWine API result and whole-source visionOS SDK syntax. A newly signed app and physical Audioshield startup remain separate validation steps.
