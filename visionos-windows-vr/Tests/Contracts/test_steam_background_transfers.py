#!/usr/bin/env python3
"""Exercise the production Steam chunk transport against a local HTTP server.

The host uses an injected ephemeral URLSession because macOS background sessions
require an application launch service. Request registration, delegate callbacks,
file preservation, caching and cancellation are the production implementation.
No Steam account, CDN, Wine runtime or headset is needed. This does not establish
that visionOS will grant unlimited background execution time.
"""
import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Sources/Steam/SwiftSteam/Content/SteamBackgroundTransfers.swift"

PROBE = r'''
import Foundation

struct ProbeFailure: Error { let message: String }
func check(_ condition: Bool, _ message: String) throws {
    if !condition { throw ProbeFailure(message: message) }
}
func payload(_ path: String) -> Data { Data(("encrypted-fixture:" + path).utf8) }
func path(_ digit: String) -> String { "/depot/1/chunk/" + String(repeating: digit, count: 40) }
func files(_ directory: URL) throws -> [URL] {
    try FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)
        .filter { $0.pathExtension == "chunk" }
}
func counts(_ base: URL) async throws -> [String: Int] {
    let (data, response) = try await URLSession.shared.data(from: base.appendingPathComponent("stats"))
    try check((response as? HTTPURLResponse)?.statusCode == 200, "Fixture statistics unavailable")
    return try JSONDecoder().decode([String: Int].self, from: data)
}
func count(_ base: URL, _ path: String) async throws -> Int { try await counts(base)[path] ?? 0 }
func waitForRequest(_ base: URL, _ path: String) async throws {
    for _ in 0..<500 {
        if try await count(base, path) > 0 { return }
        try await Task.sleep(for: .milliseconds(5))
    }
    throw ProbeFailure(message: "Network request was never submitted")
}
func request(_ base: URL, _ path: String, token: String = "first-secret-token") -> URL {
    URL(string: base.absoluteString + path + "?auth=" + token)!
}
func transport(_ cache: URL) -> SteamBackgroundTransfers {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.urlCache = nil
    configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
    configuration.timeoutIntervalForRequest = 5
    configuration.timeoutIntervalForResource = 10
    return SteamBackgroundTransfers(configuration: configuration, cacheDirectory: cache,
                                    identifier: "WineVisionVR.TransportProbe." + UUID().uuidString)
}
func expectCancellation(_ task: Task<Data, Error>) async throws {
    do {
        _ = try await task.value
        throw ProbeFailure(message: "Cancelled transfer returned successful data")
    } catch is CancellationError {
        // The public async API must preserve structured cancellation.
    }
}

@main struct BackgroundTransferProbe {
    static func main() async throws {
        // An unresolved continuation must fail this test even if a task-group
        // timeout would itself get stuck waiting for that continuation.
        DispatchQueue.global().asyncAfter(deadline: .now() + 40) {
            fatalError("Transport test timed out: a continuation may not have completed")
        }
        let base = URL(string: CommandLine.arguments[1])!
        let root = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)

        let successCache = root.appendingPathComponent("success", isDirectory: true)
        let success = transport(successCache)
        success.prepare()
        let successPath = path("1")
        let original = request(base, successPath)
        let bytes = try await success.data(for: original)
        try check(bytes == payload(successPath), "200 response must deliver the preserved chunk bytes")
        let stored = try files(successCache)
        try check(stored.count == 1, "Completed downloaded file must persist after URLSession deletes its temporary file")
        try check(try Data(contentsOf: stored[0]) == bytes, "Preserved chunk must contain the entire HTTP payload")
        try check(!stored[0].lastPathComponent.contains("secret"), "Cache filenames must not expose authorization tokens")
        let reused = try await success.data(for: request(base, successPath, token: "changed-secret-token"))
        try check(reused == bytes, "Changed authorization query must reuse the same chunk")
        try check(try await count(base, successPath) == 1, "A verified cached encrypted chunk must not be fetched twice")
        let relaunched = transport(successCache)
        let relaunchedData = try await relaunched.data(for: request(base, successPath, token: "third-token"))
        let countAfterRelaunch = try await count(base, successPath)
        try check(relaunchedData == bytes && countAfterRelaunch == 1,
                  "A fresh transport session must recover payload files written by the prior session")
        print("PASS: 200 delivery, temporary-file preservation, token-independent reuse and new-session cache recovery")

        let failureCache = root.appendingPathComponent("http-failure", isDirectory: true)
        let failed = transport(failureCache)
        let failurePath = path("2")
        for token in ["first", "second"] {
            do {
                _ = try await failed.data(for: request(base, failurePath, token: token))
                throw ProbeFailure(message: "HTTP 500 must not complete successfully")
            } catch is ProbeFailure { throw ProbeFailure(message: "HTTP 500 was accepted") }
            catch { /* Expected server rejection. */ }
        }
        try check(try files(failureCache).isEmpty, "HTTP errors must not be preserved as successful chunks")
        try check(try await count(base, failurePath) == 2, "HTTP failure must leave the URL retryable")
        print("PASS: HTTP 500 rejection, no successful cache entry and retry")

        let immediateTransport = transport(root.appendingPathComponent("startup-cancellation", isDirectory: true))
        let immediatePath = path("7")
        let immediatelyCancelled = Task<Data, Error> {
            try await immediateTransport.data(for: request(base, immediatePath))
        }
        immediatelyCancelled.cancel()
        try await expectCancellation(immediatelyCancelled)
        let afterStartupCancellation = try await immediateTransport.data(for: request(base, immediatePath))
        try check(afterStartupCancellation == payload(immediatePath), "Cancellation during session startup must not hang or poison a later request")

        let cancelled = transport(root.appendingPathComponent("cancelled", isDirectory: true))
        let preCancelledPath = path("6")
        let before = Task<Data, Error> {
            withUnsafeCurrentTask { $0?.cancel() }
            return try await cancelled.data(for: request(base, preCancelledPath))
        }
        try await expectCancellation(before)
        try check(try await count(base, preCancelledPath) == 0, "A previously cancelled caller must not submit a network task")
        let afterPreCancellation = try await cancelled.data(for: request(base, preCancelledPath))
        try check(afterPreCancellation == payload(preCancelledPath), "Cancellation before registration must leave the URL usable")

        let duringPath = path("3")
        let during = Task<Data, Error> { try await cancelled.data(for: request(base, duringPath)) }
        try await waitForRequest(base, duringPath)
        during.cancel()
        try await expectCancellation(during)
        let afterCancellation = try await cancelled.data(for: request(base, duringPath, token: "retry-token"))
        try check(afterCancellation == payload(duringPath), "A URL cancelled during transfer must be immediately retryable")
        try check(try await count(base, duringPath) == 2, "Cancellation must not leave a stale task registration")
        // Let the first HTTP handler finish and exercise any late completion.
        try await Task.sleep(for: .milliseconds(1800))
        let afterLateCallback = try await cancelled.data(for: request(base, duringPath))
        try check(afterLateCallback == afterCancellation, "A late cancelled callback must not overwrite the successful retry")
        print("PASS: cancellation before and during network, retry and late delegate completion")

        let shared = transport(root.appendingPathComponent("shared", isDirectory: true))
        let sharedPath = path("4")
        let first = Task<Data, Error> { try await shared.data(for: request(base, sharedPath)) }
        try await waitForRequest(base, sharedPath)
        let second = Task<Data, Error> { try await shared.data(for: request(base, sharedPath, token: "second-caller")) }
        try await Task.sleep(for: .milliseconds(50))
        first.cancel()
        try await expectCancellation(first)
        let sharedData = try await second.value
        try check(sharedData == payload(sharedPath), "Cancelling one duplicate caller must preserve another caller's transfer")
        try check(try await count(base, sharedPath) == 1, "Simultaneous callers must share one network transfer")
        print("PASS: duplicate callers share a transfer and cancellation completes only its caller")

        let corruptCache = root.appendingPathComponent("corrupt", isDirectory: true)
        let corrupt = transport(corruptCache)
        let corruptPath = path("5")
        let corruptURL = request(base, corruptPath)
        let correct = try await corrupt.data(for: corruptURL)
        let corruptFiles = try files(corruptCache)
        try check(corruptFiles.count == 1, "Corruption fixture must have one preserved payload")
        try Data("corrupt-encrypted-bytes".utf8).write(to: corruptFiles[0])
        let badBytes = try await corrupt.data(for: corruptURL)
        try check(badBytes != correct, "Transport must leave chunk integrity validation to the depot decryptor")
        corrupt.removeCachedData(for: request(base, corruptPath, token: "replacement-token"))
        try check(try files(corruptCache).isEmpty, "Caller rejection must remove the corrupt chunk regardless of authorization query")
        let repaired = try await corrupt.data(for: corruptURL)
        let countAfterRepair = try await count(base, corruptPath)
        try check(repaired == correct && countAfterRepair == 2,
                  "Removing rejected cache data must fetch a clean replacement")
        corrupt.removeCachedData(for: corruptURL)
        try check(try files(corruptCache).isEmpty, "Successfully installed chunk must be removable")
        print("PASS: caller-detected cache corruption, eviction and clean refetch")
        print("PASS: production SteamBackgroundTransfers real HTTP contract suite")
    }
}
'''


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), FixtureHandler)
        self.requests = Counter()
        self.request_lock = threading.Lock()


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/stats":
            with self.server.request_lock:
                body = json.dumps(dict(self.server.requests)).encode()
            code = 200
        elif path.startswith("/depot/1/chunk/"):
            with self.server.request_lock:
                self.server.requests[path] += 1
                ordinal = self.server.requests[path]
            digit = path.rsplit("/", 1)[-1][0]
            if digit == "3" and ordinal == 1:
                time.sleep(1.5)
            elif digit in ("4", "7"):
                time.sleep(0.5)
            code = 500 if digit == "2" else 200
            body = ("server-error" if code != 200 else "encrypted-fixture:" + path).encode()
        else:
            code, body = 404, b"fixture-not-found"
        try:
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Expected when the production caller cancels its transfer.


def run(build):
    build.mkdir(parents=True, exist_ok=True)
    probe = build / "BackgroundTransferProbe.swift"
    probe.write_text(PROBE)
    executable = build / "background-transfer-probe"
    subprocess.run([
        "xcrun", "--sdk", "macosx", "swiftc", "-parse-as-library", "-O", "-swift-version", "6",
        "-module-cache-path", str(build / "cache"), str(SOURCE), str(probe), "-o", str(executable),
    ], check=True)
    server = FixtureServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="payloads-", dir=build) as scratch:
            subprocess.run([str(executable), "http://127.0.0.1:" + str(server.server_port), scratch], check=True, timeout=50)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, help="retain compiled probe and compiler cache here")
    args = parser.parse_args()
    if args.build:
        run(args.build.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="wvr-background-transfers-") as scratch:
            run(Path(scratch))


if __name__ == "__main__":
    main()
