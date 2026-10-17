#!/usr/bin/env python3
"""Exercise the production SteamLibraryModel queue against deterministic fake I/O.

Only SwiftUI's observation shell and external Steam/storage dependencies are
stubbed. The entire production model is compiled unchanged except SwiftUI's
import and redirecting UserDefaults.standard into a fresh test-only suite.
No account, network, game download, Wine, or headset is used.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]

STUBS = r'''
import Foundation
protocol ObservableObject {}
@propertyWrapper struct Published<Value> {
    var wrappedValue: Value
    init(wrappedValue: Value) { self.wrappedValue = wrappedValue }
}
struct SteamLaunchOption: Sendable {
    var executable = "game.exe"
    var index: UInt32? = 0
    var arguments = ""
    var type = "vr"
    var oslist = "windows"
}
struct SteamAppInfo: Sendable {
    var appID: UInt32
    var name: String { "Game \(appID)" }
}
struct SteamOwnedGame: Sendable {
    var id: Int
    var name: String
    var launches: [SteamLaunchOption]? = [SteamLaunchOption()]
    init(_ info: SteamAppInfo) { id = Int(info.appID); name = info.name }
}
struct SteamDownloadProgress: Sendable, Equatable {
    var doneBytes: UInt64 = 0
}
struct DockGame: Sendable {
    var id: Int
    var installed = true
    var library = "steamapps"
    var installDir = "game"
}
enum SteamError: Error {
    case depotNotFound(UInt32), fakeFailure, disconnected, connectionTimeout, noServersAvailable
    case connectionFailed(String)
}
@MainActor enum SteamSignIn {
    static var isSignedIn = false
    static var accountName: String?
    static let didChange = Notification.Name("FakeSteamSignIn")
    static func message(_ error: Error) -> String { String(describing: error) }
    static func signOut() { isSignedIn = false; accountName = nil }
}
@MainActor enum Backend {
    static var owned: [UInt32] = Array(1...20)
    static var installed: Set<Int> = []
    static var partial: Set<UInt32> = []
    static var starts: [Int] = []
    static var running: Set<Int> = []
    static var maximumRunning = 0
    static var outcomes: [Int: Bool] = [:]
    static var failures: [Int: Error] = [:]
    static var callbacks: [Int: (SteamDownloadProgress) -> Void] = [:]
    static var fetchHeld = false
    static var cancellationHeld: Set<Int> = []
    static var cancellationSeen: Set<Int> = []
    static var events: [String] = []
    static func reset() {
        owned = Array(1...20); installed = []; partial = []
        starts = []; running = []; maximumRunning = 0; outcomes = [:]; failures = [:]
        callbacks = [:]; fetchHeld = false; cancellationHeld = []
        cancellationSeen = []; events = []
    }
}
@MainActor final class SteamSession {
    func connectAndLogin() async throws { Backend.events.append("connect") }
    func ensureConnected() async throws { try Task.checkCancellation() }
    func suspend() async { Backend.events.append("suspend"); check(Backend.running.isEmpty, "Suspend must await installer cancellation") }
    func resume() { Backend.events.append("resume") }
}
@MainActor final class SteamLibraryFetcher {
    init(session: SteamSession) {}
    func fetchOwnedApps() async throws -> [SteamAppInfo] {
        let snapshot = Backend.owned
        Backend.events.append("fetch")
        while Backend.fetchHeld { try await Task.sleep(nanoseconds: 1_000_000) }
        return snapshot.map { SteamAppInfo(appID: $0) }
    }
    func fetchInstallInfo(appID: UInt32) async throws -> SteamAppInfo? {
        try Task.checkCancellation()
        return Backend.owned.contains(appID) ? SteamAppInfo(appID: appID) : nil
    }
    func ownedDepotIDs() async throws -> Set<UInt32> { [1] }
}
@MainActor final class DepotDownloader {
    init(session: SteamSession) {}
    static func hasPartialDownload(appID: UInt32, steamApps: URL) -> Bool { Backend.partial.contains(appID) }
    func install(_ app: SteamAppInfo, steamApps: URL,
                 ownedDepots: @escaping () async -> Set<UInt32>?,
                 progress report: @escaping (SteamDownloadProgress) -> Void) async throws -> URL {
        let id = Int(app.appID)
        Backend.starts.append(id); Backend.running.insert(id)
        Backend.maximumRunning = max(Backend.maximumRunning, Backend.running.count)
        Backend.callbacks[id] = report
        Backend.partial.insert(app.appID)
        defer { Backend.running.remove(id) }
        do {
            while Backend.outcomes[id] == nil && Backend.failures[id] == nil { try await Task.sleep(nanoseconds: 1_000_000) }
            try Task.checkCancellation()
        } catch {
            Backend.cancellationSeen.insert(id)
            while Backend.cancellationHeld.contains(id) {
                // Simulate asynchronous teardown which does not finish instantly
                // when cancellation is requested.
                await withCheckedContinuation { continuation in
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.001) { continuation.resume() }
                }
            }
            throw error
        }
        if let failure = Backend.failures.removeValue(forKey: id) { throw failure }
        guard Backend.outcomes.removeValue(forKey: id)! else { throw SteamError.fakeFailure }
        Backend.installed.insert(id); Backend.partial.remove(app.appID)
        return steamApps
    }
}
@MainActor enum MadeiraDock {
    static let drive = URL(fileURLWithPath: CommandLine.arguments[2])
    static let prefix = drive
    static func games(drive: URL) -> [DockGame] { Backend.installed.map { DockGame(id: $0) } }
    static func validate(_ game: DockGame, drive: URL) throws {}
}
enum SteamInstallPaths { static func steamApps(drive: URL) -> URL { drive } }
@MainActor final class SteamRuntimeInstaller {
    static let shared = SteamRuntimeInstaller()
    func prepare(prefix: URL, progress: @escaping (String) async -> Void) async throws { await progress("Preparing") }
}
@MainActor func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}
@MainActor func eventually(_ message: String, _ predicate: () -> Bool) async {
    for _ in 0..<2000 {
        if predicate() { return }
        try? await Task.sleep(nanoseconds: 1_000_000)
    }
    fatalError("Timed out: " + message)
}
@MainActor extension SteamLibraryModel {
    static func fixture(_ account: String, connect: Bool = true) async -> SteamLibraryModel {
        SteamSignIn.isSignedIn = false; SteamSignIn.accountName = nil
        let model = SteamLibraryModel()
        SteamSignIn.isSignedIn = true; SteamSignIn.accountName = account
        model.signedIn = true; model.accountName = account
        if connect { await model.connectAndLoad() }
        return model
    }
    func fixtureConnect() async { await connectAndLoad() }
    func fixtureAccountChange(_ account: String) async {
        SteamSignIn.isSignedIn = true; SteamSignIn.accountName = account
        await signInStateChanged()
    }
}
'''

PROBE = r'''
@main struct QueueProbe {
    @MainActor static func main() async {
        defer { UserDefaults(suiteName: CommandLine.arguments[1])!.removePersistentDomain(forName: CommandLine.arguments[1]) }
        func entry(_ id: Int) -> SteamLibraryEntry { SteamLibraryEntry(game: SteamOwnedGame(SteamAppInfo(appID: UInt32(id)))) }
        Backend.reset()
        let model = await SteamLibraryModel.fixture("fifo")
        model.download(entry(1)); model.download(entry(2)); model.download(entry(3)); model.download(entry(2))
        await eventually("first FIFO download") { Backend.starts == [1] }
        check(model.queuedDownloads == [2, 3], "FIFO enqueue must deduplicate waiting games")
        let finishedCallback = Backend.callbacks[1]!
        finishedCallback(SteamDownloadProgress(doneBytes: 42))
        await eventually("current install publishes progress") { model.progress[1]?.doneBytes == 42 }
        model.removeQueued(2)
        check(model.queuedDownloads == [3], "Remove must preserve remaining order")
        Backend.outcomes[1] = true
        await eventually("next game after success") { Backend.starts == [1, 3] }
        finishedCallback(SteamDownloadProgress(doneBytes: 777))
        try? await Task.sleep(nanoseconds: 5_000_000)
        check(model.progress[1] == nil, "Late completed-task callback must not resurrect progress")
        Backend.outcomes[3] = false
        model.download(entry(4))
        await eventually("next game after failure") { Backend.starts == [1, 3, 4] }
        check(model.downloadErrors[3] != nil, "Failure belongs to the failed game")
        check(model.installedIDs.contains(1), "Successful game installation is refreshed")
        Backend.outcomes[4] = true
        await eventually("FIFO drained") { model.activeDownloads.isEmpty }
        check(Backend.maximumRunning == 1, "Shared downloader must never install two apps concurrently")

        model.download(entry(5)); model.download(entry(6))
        await eventually("pause target started") { Backend.starts.last == 5 }
        Backend.cancellationHeld.insert(5)
        model.pause(5); model.resume(entry(5))
        await eventually("cancellation enters asynchronous teardown") { Backend.cancellationSeen.contains(5) }
        check(Backend.starts.last == 5 && Backend.running == [5], "Resume must wait for cancelled task to fully exit")
        check(model.queuedDownloads == [6, 5], "Immediate resume queues behind existing waiting games")
        Backend.cancellationHeld.remove(5)
        await eventually("next starts after pause cleanup") { Backend.starts.last == 6 }
        Backend.outcomes[6] = true
        await eventually("resumed download eventually starts") { Backend.starts.suffix(2) == [6, 5] }
        Backend.outcomes[5] = true
        await eventually("resumed download complete") { model.activeDownloads.isEmpty }
        check(Backend.maximumRunning == 1, "Pause/resume must preserve single-installer invariant")

        model.download(entry(7)); model.download(entry(8))
        await eventually("explicit pause target") { Backend.starts.last == 7 }
        model.pause(7)
        await eventually("explicit pause allows next game") { Backend.starts.last == 8 }
        check(model.pausedDownloads.contains(7), "Explicit pause remains paused")
        let startsBeforeLaunch = Backend.starts.count
        await model.prepareForLaunch()
        check(model.queuedDownloads == [8] && model.activeDownloads.isEmpty, "Launch reservation requeues interrupted active install")
        model.download(entry(9))
        try? await Task.sleep(nanoseconds: 5_000_000)
        check(Backend.starts.count == startsBeforeLaunch, "Reservation must block queue execution")
        check(model.queuedDownloads == [8, 9], "Queue accepts more games while Steam is reserved for launch")
        model.resumeAfterLaunchFailure()
        await eventually("resume after launch") { Backend.starts.count == startsBeforeLaunch + 1 }
        check(Backend.starts.last == 8, "Interrupted active install keeps first place")
        Backend.outcomes[8] = true
        await eventually("waiting game after launch") { Backend.starts.last == 9 }
        Backend.outcomes[9] = true
        await eventually("launch queue drained") { model.activeDownloads.isEmpty }
        check(model.pausedDownloads.contains(7) && !Backend.starts.suffix(2).contains(7), "Launch resumption must not auto-resume explicit pause")

        model.download(entry(14)); model.download(entry(15))
        await eventually("launch resume race target starts") { Backend.starts.last == 14 }
        Backend.cancellationHeld.insert(14)
        let suspended = Task { await model.prepareForLaunch() }
        await eventually("launch cancellation teardown held") { Backend.cancellationSeen.contains(14) }
        let beforeEarlyResume = Backend.starts.count
        model.resumeAfterLaunchFailure()
        check(Backend.starts.count == beforeEarlyResume, "Early launch failure must wait for suspension to finish")
        Backend.cancellationHeld.remove(14)
        await suspended.value
        await eventually("deferred launch resume reconnects") { Backend.starts.count == beforeEarlyResume + 1 }
        check(Backend.starts.last == 14, "Deferred launch resume preserves interrupted-first order")
        Backend.outcomes[14] = true
        await eventually("deferred queue next") { Backend.starts.last == 15 }
        Backend.outcomes[15] = true
        await eventually("deferred queue drained") { model.activeDownloads.isEmpty }

        model.runtimeBusy = true
        await eventually("runtime reservation established") { Backend.events.last == "suspend" }
        model.download(entry(10)); model.download(entry(11))
        check(model.queuedDownloads == [10, 11], "Busy runtime accepts ordered waiting games")
        let beforeSignout = Backend.starts.count
        await model.signOut()
        check(model.queuedDownloads.isEmpty && model.pausedDownloads.isEmpty, "Signout clears visible old-account queue")
        check(Backend.starts.count == beforeSignout, "Signout must not start waiting games")
        let other = await SteamLibraryModel.fixture("another-account")
        check(other.queuedDownloads.isEmpty && other.pausedDownloads.isEmpty, "Different account must not inherit queue")
        await other.signOut()

        // Restore saved pending and explicit pauses only after the owned library
        // becomes available; a premature row action cannot erase saved state.
        let restored = await SteamLibraryModel.fixture("fifo", connect: false)
        Backend.fetchHeld = true
        let loading = Task { await restored.fixtureConnect() }
        await eventually("library fetch held") { restored.isLoadingLibrary }
        restored.download(entry(12))
        check(restored.queuedDownloads.isEmpty, "Unverified entries before library load must not enqueue")
        Backend.fetchHeld = false
        await loading.value
        await eventually("restored first pending game") { Backend.starts.last == 10 }
        check(restored.queuedDownloads == [11], "Saved FIFO must survive initial fetch")
        check(restored.pausedDownloads == [7], "Explicit pause survives relaunch")
        Backend.outcomes[10] = true
        await eventually("second restored game") { Backend.starts.last == 11 }
        Backend.outcomes[11] = true
        await eventually("restored queue drained") { restored.activeDownloads.isEmpty }

        await restored.fixtureAccountChange("fifo")
        check(restored.pausedDownloads == [7], "Duplicate same-account sign-in must preserve explicit pauses")
        restored.download(entry(12)); restored.download(entry(13))
        await eventually("account switch active target") { Backend.starts.last == 12 }
        let staleCallback = Backend.callbacks[12]!
        Backend.cancellationHeld.insert(12)
        let accountTransition = Task { await restored.fixtureAccountChange("new-account") }
        await eventually("old account install teardown held") { Backend.cancellationSeen.contains(12) }
        restored.download(entry(16))
        check(!restored.queuedDownloads.contains(16), "Stale prior-account row action during teardown must not enter either account queue")
        Backend.cancellationHeld.remove(12)
        await accountTransition.value
        staleCallback(SteamDownloadProgress(doneBytes: 999))
        try? await Task.sleep(nanoseconds: 5_000_000)
        check(restored.progress[12] == nil && restored.downloadErrors[12] == nil,
              "Late prior-account callback must not mutate new account")
        check(restored.activeDownloads.isEmpty && restored.queuedDownloads.isEmpty,
              "Account switch must cancel active install and isolate waiting queue")
        await restored.signOut()

        Backend.owned = [14]
        let switching = await SteamLibraryModel.fixture("old-fetch-account", connect: false)
        Backend.fetchHeld = true
        let oldFetch = Task { await switching.fixtureConnect() }
        await eventually("old account fetch held") { switching.isLoadingLibrary }
        Backend.owned = [15]
        await switching.fixtureAccountChange("replacement-fetch-account")
        Backend.fetchHeld = false
        await oldFetch.value
        await eventually("new account loads after stale fetch finishes") { switching.games.map(\.id) == [15] }
        check(!switching.games.contains(where: { $0.id == 14 }), "Old-account fetch must not overwrite new owned library")
        await switching.signOut()
        Backend.owned = Array(1...20)

        // Simulate saved records from a prior process, including stale installed,
        // duplicate, unowned and partial IDs. Repairs must remain explicit.
        let defaults = UserDefaults(suiteName: CommandLine.arguments[1])!
        let key = "SteamLibrary.downloadQueue.v1." + Data("filtering".utf8).base64EncodedString()
        let saved: [String: Any] = ["pending": [1, 2, 3, 4, 4, 999, -1], "paused": [5, 999], "repairs": [3]]
        defaults.set(try! JSONSerialization.data(withJSONObject: saved), forKey: key)
        Backend.installed = [1, 2, 3]; Backend.partial = [2]
        let filtered = await SteamLibraryModel.fixture("filtering")
        await eventually("restored partial game starts") { Backend.starts.last == 2 }
        check(filtered.queuedDownloads == [3, 4], "Restore skips complete installs, retains partial and explicit repair, deduplicates/filters unowned IDs")
        check(filtered.pausedDownloads == [5], "Restore filters unowned paused IDs")
        await filtered.signOut()
        check(Backend.running.isEmpty && Backend.maximumRunning == 1, "All test tasks are stopped without install overlap")

        // Taking the headset off must leave an active transfer alone. If the
        // system suspends networking, preserve its journal and retry only when
        // the application becomes active again, ahead of later queued games.
        Backend.reset()
        let background = await SteamLibraryModel.fixture("background-retry")
        background.download(entry(17)); background.download(entry(18))
        await eventually("background transfer starts") { Backend.starts == [17] }
        background.applicationActivityChanged(false)
        check(Backend.running == [17], "Background transition must not cancel a healthy active download")
        Backend.failures[17] = URLError(.networkConnectionLost)
        await eventually("suspended transfer preserved") { background.activeDownloads.isEmpty }
        check(background.queuedDownloads == [17, 18], "Suspended active install returns to the front of its queue")
        check(background.downloadErrors[17] == nil && Backend.partial.contains(17), "Transient suspension keeps resumable progress without a permanent error")
        background.applicationActivityChanged(false)
        try? await Task.sleep(nanoseconds: 10_000_000)
        check(Backend.starts == [17], "Inactive recovery must not repeatedly reconnect or retry")
        background.applicationActivityChanged(true)
        await eventually("foreground resumes interrupted install") { Backend.starts == [17, 17] }
        background.applicationActivityChanged(true)
        try? await Task.sleep(nanoseconds: 5_000_000)
        check(Backend.starts == [17, 17] && Backend.maximumRunning == 1, "Repeated active notifications must not duplicate installers")
        Backend.outcomes[17] = true
        await eventually("background recovery preserves waiting game") { Backend.starts == [17, 17, 18] }
        Backend.outcomes[18] = true
        await eventually("background recovered queue drains") { background.activeDownloads.isEmpty }

        background.download(entry(19))
        await eventually("inactive pause target starts") { Backend.starts.last == 19 }
        background.applicationActivityChanged(false)
        background.pause(19)
        await eventually("explicit inactive pause completes") { background.activeDownloads.isEmpty }
        let pausedStarts = Backend.starts.count
        background.applicationActivityChanged(true)
        try? await Task.sleep(nanoseconds: 10_000_000)
        check(background.pausedDownloads.contains(19) && Backend.starts.count == pausedStarts,
              "Foreground recovery must never override an explicit pause")

        background.download(entry(20))
        await eventually("permanent background failure target starts") { Backend.starts.last == 20 }
        background.applicationActivityChanged(false)
        Backend.failures[20] = SteamError.fakeFailure
        await eventually("permanent background failure surfaces") { background.downloadErrors[20] != nil && background.activeDownloads.isEmpty }
        let permanentStarts = Backend.starts.count
        background.applicationActivityChanged(true)
        try? await Task.sleep(nanoseconds: 10_000_000)
        check(Backend.starts.count == permanentStarts && background.downloadErrors[20] != nil,
              "Permanent download errors must remain visible and must not auto-retry")
        await background.signOut()

        Backend.reset()
        let retryBudget = await SteamLibraryModel.fixture("background-retry-budget")
        retryBudget.download(entry(3))
        await eventually("bounded recovery target starts") { Backend.starts == [3] }
        retryBudget.applicationActivityChanged(false)
        Backend.failures[3] = URLError(.timedOut)
        await eventually("bounded recovery waits for foreground") { retryBudget.activeDownloads.isEmpty && retryBudget.queuedDownloads == [3] }
        retryBudget.applicationActivityChanged(true)
        await eventually("bounded recovery gets one retry") { Backend.starts == [3, 3] }
        Backend.failures[3] = URLError(.networkConnectionLost)
        await eventually("second failure remains visible") { retryBudget.activeDownloads.isEmpty && retryBudget.downloadErrors[3] != nil }
        retryBudget.applicationActivityChanged(true)
        try? await Task.sleep(nanoseconds: 10_000_000)
        check(Backend.starts == [3, 3], "One background interruption must not create an endless retry loop")
        await retryBudget.signOut()

        Backend.reset()
        let reserved = await SteamLibraryModel.fixture("background-launch-reservation")
        reserved.download(entry(4)); reserved.download(entry(5))
        await eventually("reserved recovery target starts") { Backend.starts == [4] }
        reserved.applicationActivityChanged(false)
        Backend.failures[4] = SteamError.connectionTimeout
        await eventually("reserved recovery waits for foreground") { reserved.activeDownloads.isEmpty && reserved.queuedDownloads == [4, 5] }
        await reserved.prepareForLaunch()
        reserved.applicationActivityChanged(true)
        try? await Task.sleep(nanoseconds: 10_000_000)
        check(Backend.starts == [4] && reserved.queuedDownloads == [4, 5],
              "Foreground recovery must not bypass a game launch's Steam reservation")
        reserved.resumeAfterLaunchFailure()
        await eventually("released reservation resumes interrupted first") { Backend.starts == [4, 4] }
        await reserved.signOut()

        Backend.reset()
        let removed = await SteamLibraryModel.fixture("background-remove-waiting")
        removed.download(entry(6)); removed.download(entry(7))
        await eventually("removable suspended target starts") { Backend.starts == [6] }
        removed.applicationActivityChanged(false)
        Backend.failures[6] = SteamError.noServersAvailable
        await eventually("removable suspended target waits") { removed.activeDownloads.isEmpty && removed.queuedDownloads == [6, 7] }
        removed.removeQueued(6)
        await eventually("removing suspended head unblocks later queued game") { Backend.starts == [6, 7] }
        Backend.outcomes[7] = true
        await eventually("unblocked queue drains") { removed.activeDownloads.isEmpty }
        removed.applicationActivityChanged(true)
        try? await Task.sleep(nanoseconds: 10_000_000)
        check(Backend.starts == [6, 7], "Removed suspended game must not return on foreground")
        await removed.signOut()

        Backend.reset()
        let changedAccount = await SteamLibraryModel.fixture("background-old-account")
        changedAccount.download(entry(1)); changedAccount.download(entry(2))
        await eventually("account-isolation background target starts") { Backend.starts == [1] }
        changedAccount.applicationActivityChanged(false)
        Backend.failures[1] = SteamError.disconnected
        await eventually("old account suspended queue preserved") { changedAccount.activeDownloads.isEmpty && changedAccount.queuedDownloads == [1, 2] }
        await changedAccount.fixtureAccountChange("background-new-account")
        let previousAccountStarts = Backend.starts.count
        changedAccount.applicationActivityChanged(true)
        try? await Task.sleep(nanoseconds: 10_000_000)
        check(changedAccount.activeDownloads.isEmpty && changedAccount.queuedDownloads.isEmpty &&
              Backend.starts.count == previousAccountStarts, "Foreground must not resume a previous account's interrupted download")
        await changedAccount.signOut()
        check(Backend.running.isEmpty && Backend.maximumRunning == 1, "Lifecycle recovery preserves single-installer cleanup")

        Backend.reset()
        Backend.installed = [8]
        let launchModel = await SteamLibraryModel.fixture("installed-launch-handoff")
        let gameFolder = MadeiraDock.drive.appendingPathComponent("steamapps/common/game", isDirectory: true)
        try! FileManager.default.createDirectory(at: gameFolder, withIntermediateDirectories: true)
        let executable = gameFolder.appendingPathComponent("game.exe")
        try! Data([1]).write(to: executable)
        var launchGame = SteamOwnedGame(SteamAppInfo(appID: 8))
        launchGame.launches = [SteamLaunchOption(executable: "GAME.EXE", index: 2),
                               SteamLaunchOption(executable: "missing.exe", index: 3)]
        let launchEntry = SteamLibraryEntry(game: launchGame)
        var handoffs: [(Int, UInt32)] = []
        launchModel.onPlaySelected = { game, option in handoffs.append((game.id, option)) }
        await launchModel.play(launchEntry, launchOption: 3)
        check(handoffs.isEmpty && launchModel.error != nil,
              "An explicitly selected missing executable must fail without handing off to Steam")
        launchModel.download(entry(9))
        await eventually("failed installed selection releases launch reservation") { Backend.starts == [9] }
        Backend.outcomes[9] = true
        await eventually("post-selection-error download drains") { launchModel.activeDownloads.isEmpty }
        await launchModel.play(launchEntry)
        check(handoffs.count == 1 && handoffs[0].0 == 8 && handoffs[0].1 == 2 && launchModel.error == nil,
              "A single installed case-insensitive executable must auto-select its actual option index")
        launchModel.resumeAfterLaunchFailure()
        var missingCatalog = launchGame
        missingCatalog.launches = []
        await launchModel.play(SteamLibraryEntry(game: missingCatalog))
        check(handoffs.count == 1 && launchModel.error?.contains("Refresh the library") == true,
              "Empty launch metadata must request a library refresh without inventing option zero")
        missingCatalog.launches = nil
        await launchModel.play(SteamLibraryEntry(game: missingCatalog))
        check(handoffs.count == 1 && launchModel.error?.contains("Refresh the library") == true,
              "Unavailable launch metadata must request refresh rather than repairing installed files")
        try! FileManager.default.removeItem(at: executable)
        await launchModel.play(launchEntry)
        check(handoffs.count == 1 && launchModel.error?.contains("Update / repair") == true,
              "An executable removed after catalog loading must be rechecked and request repair before handoff")
        await launchModel.signOut()

        print("PASS: production Steam queue FIFO/dedup/remove, completion/failure continuation, pause/resume teardown, launch reservation, persistence/restore filtering, in-flight account fetch replacement, account isolation, current/stale callbacks and bounded background/foreground recovery")
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, help='retain generated Swift probe and compiler cache here')
    args = parser.parse_args()
    model = (ROOT / 'Sources/Steam/SteamLibraryModel.swift').read_text()
    model = model.replace('import SwiftUI', '')
    model = model.replace('UserDefaults.standard', 'UserDefaults(suiteName: CommandLine.arguments[1])!')

    def run(scratch):
        scratch.mkdir(parents=True, exist_ok=True)
        source = scratch / 'QueueProbe.swift'
        resolver = (ROOT / 'Sources/Steam/SteamInstalledExecutable.swift').read_text()
        source.write_text(STUBS + resolver + model + PROBE)
        executable = scratch / 'queue-probe'
        subprocess.run(['xcrun', '--sdk', 'macosx', 'swiftc', '-parse-as-library', '-O',
                        '-module-cache-path', str(scratch / 'cache'), str(source), '-o', str(executable)], check=True)
        import uuid
        subprocess.run([str(executable), 'WineVisionVR.QueueTests.' + str(uuid.uuid4()), str(scratch / 'drive')], check=True, timeout=45)
    if args.build:
        run(args.build.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='wvr-download-queue-') as scratch:
            run(Path(scratch))

if __name__ == '__main__':
    main()
