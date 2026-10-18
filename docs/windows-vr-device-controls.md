# Bounded headset diagnostic controls

After installing a verified diagnostic WineVision package, the host runner can wait for the wearer and run the existing direct32 SEH control followed by the identical child launched from its x64 parent. It never installs an app or changes runtime, game, Steam, pairing or lock settings.

Start the command, then put on the headset and keep it worn. Tests begin when `devicectl` explicitly reports `passcodeRequired=false` and `unlockedSinceBoot=true`. There is no need to return to the Mac to send a readiness reply. The default unlock wait is 180 seconds and each diagnostic phase has a separate 120-second deadline.

```sh
source /Volumes/XRDev/build/WineVisionVR/child-loader-oct18-r6/env.sh
python3 windows-vr-tools/test_device_controls.py \
  --device DEVICE-UUID \
  --verified-app /absolute/path/to/verified-app-complete.json \
  --install-receipt /absolute/path/to/successful-device-install.json \
  --output /Volumes/XRDev/build/WineVisionVR/device-controls-new-run \
  --unlock-timeout 180 --phase-timeout 120
```

`--command-timeout` accepts fractional host budgets, but devicectl receives positive integer seconds rounded down. The host deadline has no added grace; a phase with less than one second remaining stops without another device command.

The output directory must be new and on an external `/Volumes` volume; its `tmp` directory becomes the host command's `TMPDIR`. The package receipt is an explicit path and must identify the diagnostic WineVision app, a verified signature and the matching executable SHA. Before any device action the runner performs bounded local deep/strict signature verification and, when supplied, compares every package file against the SHA-bound complete audit ledger. The installation receipt must identify the same device and bundle. Local app/executable/plugin UUIDs, a complete package hash ledger and fixture PE hashes are recorded. The installed bundle URL, actual launch PID and runtime plugin UUID bind device observations to that selected package; the runner does not claim a remotely calculated whole-app hash.

Each phase launches only `com.philipanderson.WineVisionVR`, with `--terminate-existing --activate` and the existing diagnostic arguments. The app requests its normal StikDebug JIT helper. A launch command timeout is preserved and may be recovered by finding one new process with the exact installed executable; launch is never blindly repeated. This also handles the CLI’s failed/code2 result only when its preserved stderr contains the exact command-timeout message; generic argument failures are not treated as timeouts.

A phase passes only with fresh before/final marker metadata relative to both its baseline and launch time, exact SEH fields, copied executable hashes matching the signed package, current PID/bundle/plugin UUID runtime evidence, launcher JIT/runtime acceptance and Wine exit zero after that runtime identity. Mixed additionally requires the current parent’s exact `CHILD_EXIT code=0 beforeStage=1` and complete parent PASS line, proving its wait/exit/marker verification returned. Both child PEs must be byte-identical. Stale markers, old exit lines, wrong UUIDs, incomplete results and transport failures cannot produce a pass. Unknown lock/file schemas fail closed. Host/device wall-clock skew must be within the bounded `--clock-skew` allowance (default two seconds).

If normal launcher rotation splits JIT proof, the runner can read only the three existing `launcher.previous-N.txt` slots. Each participating file must have fresh phase metadata, a bounded size and stable metadata/size across its copy; files are combined oldest first and the exact current PID handoff, debugger attachment and runtime acceptance must remain in order before another handoff. Stale archives cannot supply proof. Raw archive copies and metadata are retained.

Only read-only `copy from` can retry the observed structured file-service failure: failed `devicectl.device.copy.from`, CoreDevice error 7000, nested POSIX error 60 and the exact socket-closed reason. It has at most three attempts per copy, four retries across the whole run, one/two-second backoff and the existing phase deadline. Every raw result remains; each attempt writes an isolated temporary file and only a successful transfer is published. Failed partial files are removed, even when they contain plausible complete proof. Launch, terminate, timeouts and unrecognized/malformed transport errors are never retried. Exhausting retry/deadline budgets stops further remote work.

Failure stops the sequence; direct failure prevents mixed launch. Raw command JSON/stdout/stderr, per-poll current launcher/runtime copies, copied proof files and `result.json` remain in the output directory. Only the reverified PID/executable launched by this runner is terminated at cleanup; after an unrecovered transport failure no further remote commands are sent. `--keep-app-open` leaves the owned app open for inspection. No other process is killed. Desktop/GDI and interactive controller testing are outside this runner.

Development tests execute the actual orchestrator and transport logic against deterministic fake boundaries, without a headset:

```sh
python3 windows-vr-tools/tests/test_device_controls.py \
  --build /Volumes/XRDev/build/WineVisionVR/device-controls-contract
```

Add `--cli-help` to the development test command to verify the installed CLI accepts integer timeout tokens and rejects `20.0`, using only `devicectl --help` with no device selection.

The host tool and documentation can change independently of the frozen runtime/app build. Passing fake tests establishes runner behavior, not headset/runtime success.
