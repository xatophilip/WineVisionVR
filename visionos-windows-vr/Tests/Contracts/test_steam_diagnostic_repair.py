#!/usr/bin/env python3
"""Run the complete production Steam repair/FIFO model against deterministic I/O.

Uses the existing queue contract's fake network/storage shell. No account,
credentials, network, installed game, Wine, manifest mutation or device access.
"""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('queue_contract', Path(__file__).with_name('test_steam_download_queue.py'))
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)
PROBE = r'''
@MainActor extension SteamLibraryModel {
    func fixtureWrongQueueAccount() { queueAccount = "different-account" }
}
@main struct DiagnosticRepairProbe {
    @MainActor static func main() async {
        defer { UserDefaults(suiteName: CommandLine.arguments[1])!.removePersistentDomain(forName: CommandLine.arguments[1]) }
        let target = 224960
        func entry(_ id: Int) -> SteamLibraryEntry { SteamLibraryEntry(game: SteamOwnedGame(SteamAppInfo(appID: UInt32(id)))) }
        func fixture(_ name: String) async -> SteamLibraryModel {
            Backend.reset(); Backend.owned = [UInt32(target), 1, 2]; Backend.installed = [target]
            return await SteamLibraryModel.fixture(name)
        }
        func settle(_ model: SteamLibraryModel) async { await model.signOut(); check(Backend.running.isEmpty, "teardown must await real fake-installer cancellation") }

        var model = await fixture("repair-refusals")
        var logs: [String] = []
        var result = await model.diagnosticRepairInstalledGame(appID: target, log: { logs.append($0) })
        check(result == .disabled && Backend.starts.isEmpty, "diagnostics must be explicitly enabled")
        result = await model.diagnosticRepairInstalledGame(appID: -1, diagnosticsEnabled: true)
        check(result == .invalidAppID, "invalid app ID must not enter FIFO")
        result = await model.diagnosticRepairInstalledGame(appID: 99, diagnosticsEnabled: true)
        check(result == .notOwned, "unowned app must never download")
        result = await model.diagnosticRepairInstalledGame(appID: 1, diagnosticsEnabled: true)
        check(result == .notInstalled, "diagnostic is repair of already-installed games only")
        model.runtimeBusy = true
        result = await model.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true)
        check(result == .runtimeBusy && Backend.starts.isEmpty, "runtime-busy request must not enqueue")
        await settle(model)
        result = await model.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true)
        check(result == .signedOut, "signed-out request must not consume session")

        Backend.reset(); Backend.owned = [UInt32(target), 1, 2]; Backend.installed = [target]
        model = await SteamLibraryModel.fixture("repair-initial-refresh", connect: false)
        Backend.fetchHeld = true
        let initialModel = model
        let initial = Task { @MainActor in await initialModel.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true, timeout: 3) }
        await eventually("diagnostic owns initial bounded metadata load") { model.isLoadingLibrary }
        check(Backend.starts.isEmpty, "initial metadata race cannot enqueue repair or pretend account changed")
        Backend.fetchHeld = false
        await eventually("initial refresh allows legitimate repair") { Backend.starts == [target] }
        Backend.outcomes[target] = true
        result = await initial.value
        check(result == .completed, "first-load queueAccount race must wait for metadata then complete actual repair")
        await settle(model)

        Backend.reset(); Backend.owned = [UInt32(target)]; Backend.installed = [target]
        model = await SteamLibraryModel.fixture("repair-initial-timeout", connect: false)
        Backend.fetchHeld = true
        result = await model.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true, timeout: 0.15)
        check(result == .timedOut && model.isLoadingLibrary && Backend.starts.isEmpty, "same deadline includes initial metadata without cancelling normal library load")
        Backend.fetchHeld = false
        await eventually("normal initial refresh survives diagnostic timeout") { !model.isLoadingLibrary }
        check(Backend.starts.isEmpty, "timed-out metadata preparation cannot enqueue later")
        await settle(model)

        Backend.reset(); Backend.owned = [UInt32(target)]; Backend.installed = [target]
        model = await SteamLibraryModel.fixture("repair-join-refresh", connect: false)
        Backend.fetchHeld = true
        let refreshModel = model
        let normalRefresh = Task { @MainActor in await refreshModel.fixtureConnect() }
        await eventually("normal metadata refresh already active") { model.isLoadingLibrary }
        result = await model.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true, timeout: 0.15)
        check(result == .timedOut && model.isLoadingLibrary, "diagnostic timeout must not cancel another normal refresh")
        Backend.fetchHeld = false; await normalRefresh.value
        check(Backend.starts.isEmpty && model.games.count == 1, "joined normal refresh finishes without a late repair")
        await settle(model)

        model = await fixture("repair-no-op-account")
        model.fixtureWrongQueueAccount()
        result = await model.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true)
        check(result == .accountChanged && Backend.starts.isEmpty, "download's account-mismatch no-op cannot report success")
        await settle(model)

        model = await fixture("repair-duplicate")
        model.download(entry(1)); model.download(entry(target)); model.download(entry(2))
        await eventually("normal FIFO begins") { Backend.starts == [1] }
        result = await model.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true)
        check(result == .alreadyRequested && model.queuedDownloads == [target, 2], "existing normal repair is refused without consuming/reordering queue")
        await settle(model)

        model = await fixture("repair-completion")
        model.download(entry(1))
        await eventually("preceding normal download starts") { Backend.starts == [1] }
        logs = []
        let completionModel = model
        let completion = Task { @MainActor in await completionModel.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true, timeout: 3, log: { logs.append($0) }) }
        await eventually("diagnostic queued behind normal download") { model.queuedDownloads == [target] }
        model.download(entry(2))
        check(model.queuedDownloads == [target, 2] && model.installedIDs.contains(target), "installed ID alone cannot complete the new repair")
        check(logs.count == 1 && logs[0].hasSuffix("status=14"), "only started status before actual installer completion")
        Backend.outcomes[1] = true
        await eventually("diagnostic uses actual shared installer") { Backend.starts == [1, target] }
        check(logs.count == 1, "starting installer is not completion")
        Backend.outcomes[target] = true
        result = await completion.value
        check(result == .completed && logs.last?.hasSuffix("status=0") == true, "only successful installer return completes repair")
        await eventually("following normal download preserved") { Backend.starts == [1, target, 2] }
        Backend.outcomes[2] = true
        await eventually("normal queue drains") { model.activeDownloads.isEmpty }
        check(Backend.maximumRunning == 1, "repair must use existing single-installer FIFO")
        check(logs.allSatisfy { $0.split(separator: " ").count == 2 && $0.hasPrefix("appID=224960 status=") }, "logs contain numeric app/status only")
        await settle(model)

        model = await fixture("repair-failure")
        let failureModel = model
        let failure = Task { @MainActor in await failureModel.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true, timeout: 3) }
        await eventually("failing diagnostic starts") { Backend.starts == [target] }
        model.download(entry(2)); Backend.outcomes[target] = false
        result = await failure.value
        check(result == .failed && model.downloadErrors[target] != nil, "installer error must not be hidden by already-installed ID")
        await eventually("failure retains following normal work") { Backend.starts == [target, 2] }
        Backend.outcomes[2] = true
        await eventually("failure queue drains") { model.activeDownloads.isEmpty }
        await settle(model)

        model = await fixture("repair-waiting-timeout")
        model.download(entry(1))
        await eventually("unrelated normal installer active") { Backend.starts == [1] }
        let waitingModel = model
        let waiting = Task { @MainActor in await waitingModel.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true, timeout: 0.2) }
        await eventually("diagnostic waits behind normal installer") { model.queuedDownloads == [target] }
        model.download(entry(2)); result = await waiting.value
        check(result == .timedOut && Backend.running == [1] && model.queuedDownloads == [2], "waiting timeout removes own entry without cancelling/reordering normal work")
        check(!Backend.cancellationSeen.contains(1), "normal installer must not receive diagnostic cancellation")
        Backend.outcomes[1] = true
        await eventually("normal next preserved after waiting timeout") { Backend.starts == [1, 2] }
        Backend.outcomes[2] = true
        await eventually("waiting-timeout normal FIFO drains") { model.activeDownloads.isEmpty }
        await settle(model)

        model = await fixture("repair-timeout")
        let timeoutModel = model
        let timed = Task { @MainActor in await timeoutModel.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true, timeout: 0.25) }
        await eventually("timeout diagnostic starts") { Backend.starts == [target] }
        model.download(entry(2)); result = await timed.value
        check(result == .timedOut, "unfinished installer has bounded diagnostic wait")
        await eventually("timeout cancels only own installer and preserves FIFO") { Backend.starts == [target, 2] }
        check(Backend.partial.contains(UInt32(target)), "timeout preserves downloader's normal resumable journal")
        Backend.outcomes[2] = true
        await eventually("timeout queue drains") { model.activeDownloads.isEmpty }
        await settle(model)

        model = await fixture("repair-cancel")
        let cancelModel = model
        let cancelled = Task { @MainActor in await cancelModel.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true, timeout: 3) }
        await eventually("cancellable diagnostic starts") { Backend.starts == [target] }
        model.download(entry(2)); cancelled.cancel(); result = await cancelled.value
        check(result == .cancelled, "caller cancellation cannot become success")
        await eventually("cancellation preserves unrelated normal queue") { Backend.starts == [target, 2] }
        Backend.outcomes[2] = true
        await eventually("cancellation queue drains") { model.activeDownloads.isEmpty }
        await settle(model)

        model = await fixture("repair-old-account")
        let accountModel = model
        let changed = Task { @MainActor in await accountModel.diagnosticRepairInstalledGame(appID: target, diagnosticsEnabled: true, timeout: 3) }
        await eventually("old-account diagnostic starts") { Backend.starts == [target] }
        model.download(entry(2)); await model.fixtureAccountChange("repair-new-account")
        result = await changed.value
        check(result == .accountChanged && model.activeDownloads.isEmpty && model.queuedDownloads.isEmpty, "old diagnostic must not alter new account state")
        let key = "SteamLibrary.downloadQueue.v1." + Data("repair-old-account".utf8).base64EncodedString()
        let saved = UserDefaults(suiteName: CommandLine.arguments[1])!.data(forKey: key)!
        let pending = (try! JSONSerialization.jsonObject(with: saved) as! [String: Any])["pending"] as! [Int]
        check(pending.contains(2), "account transition preserves old account's unrelated persisted queue")
        await settle(model)
        print("PASS: production diagnostic normal-repair FIFO completion/failure, no-op refusals, timeout/cancellation, account generation and unrelated-queue preservation")
    }
}
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path)
    args = parser.parse_args()
    source = (ROOT/'Sources/Steam/SteamLibraryModel.swift').read_text().replace('import SwiftUI', '').replace('UserDefaults.standard', 'UserDefaults(suiteName: CommandLine.arguments[1])!')
    view = (ROOT/'Sources/ContentView.swift').read_text()
    branch = view.split('let argument = ProcessInfo.processInfo.arguments.first(where: { $0.hasPrefix("--steam-repair-test=") })', 1)[1].split('} else if LaunchDiagnostics.enabled', 1)[0]
    assert 'showingSteamLibrary = true' in branch and 'diagnosticRepairInstalledGame' in branch and 'LaunchLogFile.append("steam-repair-test", $0)' in branch
    assert 'else if LaunchDiagnostics.enabled, !didStartDesktopSmokeTest,' in view[:view.index('--steam-repair-test=')]
    def run(scratch):
        scratch.mkdir(parents=True, exist_ok=True)
        probe = scratch/'DiagnosticRepairProbe.swift'
        probe.write_text(queue.STUBS + (ROOT/'Sources/Steam/SteamInstalledExecutable.swift').read_text() + source + PROBE)
        executable = scratch/'diagnostic-repair-probe'
        subprocess.run(['xcrun','--sdk','macosx','swiftc','-swift-version','6','-parse-as-library','-O','-module-cache-path',str(scratch/'cache'),str(probe),'-o',str(executable)], check=True)
        subprocess.run([str(executable),'WineVisionVR.DiagnosticRepairTests.'+str(uuid.uuid4()),str(scratch/'drive')], check=True, timeout=30)
    if args.build: run(args.build.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='wvr-diagnostic-repair-') as scratch: run(Path(scratch))
if __name__ == '__main__': main()
