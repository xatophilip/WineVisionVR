# Downloads when Vision Pro is removed

Steam CDN chunk downloads use a stable, app-owned background URLSession. Its
network transfers can continue independently while visionOS suspends WineVision.
The app reconnects the same session through its application delegate, including
system relaunches for transfer events. It preserves completed encrypted chunks
before the delegate's temporary file expires; normal depot decryption, checksum
validation, writes and journal updates still happen before installation succeeds.

This is best-effort continuation, not unlimited execution while the headset is
off. The downloader submits up to eight chunks at a time. visionOS controls wakeups
and CPU time to verify/install them, enqueue more chunks and start the next game.
It may delay this work until the headset is used again. Keep Vision Pro powered,
connected to Wi-Fi and with enough free space. Force quitting, powering off or
losing connectivity can stop transfers. No silent-audio or unrelated background
mode is used to prevent suspension.

The app requests a finite background execution allowance to finish current
verification/checkpoint work. Expiration saves the game queue and releases the
allowance without cancelling system-owned transfers. Temporary encrypted results
are disposable, excluded from backup and bounded to seven days/256 MiB; they
contain neither decrypted game data nor depot keys. The system owns the signed
network requests; their authorization queries are not logged or used in cache
filenames. Existing chunk journals and verified on-disk chunks retain completed
installation progress if the process is lost.

A download interrupted by a transient connection error after leaving the
foreground is requeued first, with one automatic retry when the app returns.
An explicit pause, a runtime launch reservation, sign-out and account isolation
remain authoritative. Permanent errors remain visible; retries do not loop.

Tests exercise the production FIFO/lifecycle code and the real URLSession delegate
transport against a local HTTP fixture, including cancellation, failures, cached
result reuse and simulated relaunch. A signed visionOS build checks the actual
application delegate and platform APIs. Physical headset-off throughput and wakeup
policy must still be measured on the target device; compilation or a host HTTP
fixture is not evidence of an entire game completing with the headset off.

Apple references: [background transfers](https://developer.apple.com/documentation/foundation/downloading-files-in-the-background)
and [finite background execution](https://developer.apple.com/documentation/uikit/extending-your-app-s-background-execution-time).
