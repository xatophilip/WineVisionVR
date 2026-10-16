// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 WineVision VR contributors
// Adapted from SwiftSteam at 48f976429c189f8396e23d251d8a82f43c705922.
// See third-party/steam-native/COPYING and LICENSE-EXCEPTION.md.

import Foundation
import SwiftUI

struct SteamLibraryEntry: Identifiable, Sendable {
    let game: SteamOwnedGame
    var id: Int { game.id }
}

@MainActor
final class SteamLibraryModel: ObservableObject {
    static let shared = SteamLibraryModel()

    @Published private(set) var signedIn = SteamSignIn.isSignedIn
    @Published private(set) var accountName = SteamSignIn.accountName
    @Published private(set) var games: [SteamLibraryEntry] = []
    @Published private(set) var isLoadingLibrary = false
    @Published private(set) var installedIDs: Set<Int> = []
    @Published private(set) var progress: [Int: SteamDownloadProgress] = [:]
    @Published private(set) var activeDownloads: Set<Int> = []
    @Published private(set) var pausedDownloads: Set<Int> = []
    /// Waiting app IDs in the order selected; the single active install is separate.
    @Published private(set) var queuedDownloads: [Int] = []
    @Published private(set) var downloadErrors: [Int: String] = [:]
    @Published private(set) var isPreparingValveClient = false
    @Published private(set) var valveClientPreparationStatus: String?
    /// Set by the app while a Wine/runtime launch or accepted session is active.
    @Published var runtimeBusy = false {
        didSet {
            guard runtimeBusy != oldValue else { return }
            if runtimeBusy {
                Task { @MainActor in
                    guard self.runtimeBusy, !self.sessionReservedForLaunch else { return }
                    await self.prepareForLaunch()
                }
            } else if !sessionReservedForLaunch {
                resumeAfterLaunchFailure()
            }
        }
    }
    @Published var error: String?

    /// The app launcher receives a validated installed record after the CM
    /// session has logged off and its socket has closed.
    var onPlaySelected: ((DockGame, UInt32) -> Void)?

    private let session = SteamSession()
    private lazy var fetcher = SteamLibraryFetcher(session: session)
    private lazy var downloader = DepotDownloader(session: session)
    private var downloadTasks: [Int: Task<Void, Never>] = [:]
    private var downloadTokens: [Int: UUID] = [:]
    private var sessionReservedForLaunch = false
    private var accountGeneration = 0
    private var suspendingDownloads = 0
    private var resumeWhenDownloadsStop = false
    private var reloadLibraryWhenIdle = false
    private var queueAccount: String?
    private var repairDownloads: Set<Int> = []

    private struct SavedDownloadQueue: Codable {
        let pending: [Int]
        let paused: [Int]
        let repairs: [Int]
    }

    private static func queueKey(_ account: String) -> String {
        let normalized = account.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return "SteamLibrary.downloadQueue.v1." + Data(normalized.utf8).base64EncodedString()
    }

    private func persistDownloadQueue() {
        guard let account = queueAccount else { return }
        // Only app IDs are saved. Authentication stays in Steam's Keychain store.
        let active = activeDownloads.sorted().filter { !pausedDownloads.contains($0) }
        let pending = (active + queuedDownloads).reduce(into: [Int]()) { result, id in
            if !result.contains(id) { result.append(id) }
        }
        let saved = SavedDownloadQueue(pending: pending, paused: pausedDownloads.sorted(), repairs: repairDownloads.sorted())
        if let data = try? JSONEncoder().encode(saved) {
            UserDefaults.standard.set(data, forKey: Self.queueKey(account))
        }
    }

    private func restoreDownloadQueue(account: String) {
        guard queueAccount != account else { return }
        queueAccount = account
        let owned = Set(games.map(\.id))
        guard let data = UserDefaults.standard.data(forKey: Self.queueKey(account)),
              let saved = try? JSONDecoder().decode(SavedDownloadQueue.self, from: data) else {
            persistDownloadQueue()
            return
        }
        pausedDownloads = Set(saved.paused).intersection(owned)
        repairDownloads = Set(saved.repairs).intersection(owned)
        queuedDownloads = saved.pending.reduce(into: [Int]()) { result, id in
            guard id > 0, owned.contains(id), !pausedDownloads.contains(id), !result.contains(id) else { return }
            // A process may have closed after writing the complete appmanifest.
            // Explicit update/repair requests must still run for installed games.
            let partial = DepotDownloader.hasPartialDownload(appID: UInt32(id), steamApps: SteamInstallPaths.steamApps(drive: MadeiraDock.drive))
            if !installedIDs.contains(id) || partial || repairDownloads.contains(id) { result.append(id) }
        }
        repairDownloads.formIntersection(Set(queuedDownloads).union(pausedDownloads))
        persistDownloadQueue()
    }
    private var signInObserver: NSObjectProtocol?

    private init() {
        signInObserver = NotificationCenter.default.addObserver(
            forName: SteamSignIn.didChange, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in await self?.signInStateChanged() }
        }
        refreshInstalled()
        if signedIn { Task { await connectAndLoad() } }
    }

    func refreshInstalled() {
        let records = MadeiraDock.games(drive: MadeiraDock.drive)
        installedIDs = Set(records.filter(\.installed).map(\.id))
    }

    func refreshLibrary() async {
        guard signedIn else { return }
        await connectAndLoad()
    }

    private func signInStateChanged() async {
        persistDownloadQueue()
        accountGeneration &+= 1
        let generation = accountGeneration
        signedIn = SteamSignIn.isSignedIn
        accountName = SteamSignIn.accountName
        await stopConnectionAndDownloads()
        guard generation == accountGeneration else { return }
        clearAccountDownloadState()
        // Depot keys and owned-depot licenses belong to the old account.
        fetcher = SteamLibraryFetcher(session: session)
        downloader = DepotDownloader(session: session)
        if signedIn {
            session.resume()
            await connectAndLoad()
        }
    }

    private func clearAccountDownloadState() {
        queueAccount = nil
        games = []
        installedIDs = []
        progress = [:]
        activeDownloads = []
        pausedDownloads = []
        queuedDownloads = []
        repairDownloads = []
        downloadErrors = [:]
        if isPreparingValveClient && !runtimeBusy { sessionReservedForLaunch = false }
        isPreparingValveClient = false
        valveClientPreparationStatus = nil
    }

    private func connectAndLoad() async {
        guard !sessionReservedForLaunch, !runtimeBusy, suspendingDownloads == 0 else { return }
        guard !isLoadingLibrary else {
            reloadLibraryWhenIdle = true
            return
        }
        isLoadingLibrary = true
        defer {
            isLoadingLibrary = false
            if reloadLibraryWhenIdle {
                reloadLibraryWhenIdle = false
                Task { await connectAndLoad() }
            } else {
                startNextDownload()
            }
        }
        let generation = accountGeneration
        let libraryFetcher = fetcher
        let account = SteamSignIn.accountName
        guard signedIn, account != nil else { return }
        do {
            try await session.connectAndLogin()
            guard generation == accountGeneration, signedIn, account == SteamSignIn.accountName,
                  !runtimeBusy, !sessionReservedForLaunch else { return }
            let result = try await libraryFetcher.fetchOwnedApps()
            guard generation == accountGeneration, signedIn,
                  account == SteamSignIn.accountName, !sessionReservedForLaunch else { return }
            games = result.map { SteamLibraryEntry(game: SteamOwnedGame($0)) }
                .sorted { $0.game.name.localizedCaseInsensitiveCompare($1.game.name) == .orderedAscending }
            refreshInstalled()
            restoreDownloadQueue(account: account!)
            error = nil
        } catch {
            if generation == accountGeneration, signedIn { self.error = SteamSignIn.message(error) }
        }
    }

    /// Adds another owned game to the FIFO, including while a game is running.
    func download(_ entry: SteamLibraryEntry) {
        guard signedIn, queueAccount == SteamSignIn.accountName,
              games.contains(where: { $0.id == entry.id }), !queuedDownloads.contains(entry.id),
              !activeDownloads.contains(entry.id) || pausedDownloads.contains(entry.id) else { return }
        let appID = entry.id
        downloadErrors.removeValue(forKey: appID)
        pausedDownloads.remove(appID)
        if installedIDs.contains(appID) { repairDownloads.insert(appID) }
        queuedDownloads.append(appID)
        persistDownloadQueue()
        error = nil
        startNextDownload()
    }

    func removeQueued(_ id: Int) {
        queuedDownloads.removeAll { $0 == id }
        repairDownloads.remove(id)
        persistDownloadQueue()
    }

    private func startNextDownload() {
        guard signedIn, !runtimeBusy, !sessionReservedForLaunch,
              !isPreparingValveClient, !isLoadingLibrary, suspendingDownloads == 0,
              downloadTasks.isEmpty, let appID = queuedDownloads.first else { return }
        queuedDownloads.removeFirst()
        activeDownloads.insert(appID)
        persistDownloadQueue()
        let generation = accountGeneration
        let token = UUID()
        downloadTokens[appID] = token
        let task = Task { @MainActor in
            do {
                try Task.checkCancellation()
                try await session.ensureConnected()
                try Task.checkCancellation()
                guard generation == accountGeneration else { throw CancellationError() }
                guard let app = try await fetcher.fetchInstallInfo(appID: UInt32(appID)) else {
                    throw SteamError.depotNotFound(UInt32(appID))
                }
                try Task.checkCancellation()
                guard generation == accountGeneration else { throw CancellationError() }
                let ownedDepots = try await fetcher.ownedDepotIDs()
                try Task.checkCancellation()
                guard generation == accountGeneration else { throw CancellationError() }
                _ = try await downloader.install(app, steamApps: SteamInstallPaths.steamApps(drive: MadeiraDock.drive),
                    ownedDepots: { ownedDepots }) { [weak self] value in
                        Task { @MainActor in
                            guard let self, generation == self.accountGeneration,
                                  self.downloadTokens[appID] == token, self.downloadTasks[appID]?.isCancelled == false,
                                  self.activeDownloads.contains(appID), !self.pausedDownloads.contains(appID) else { return }
                            self.progress[appID] = value
                        }
                    }
                guard generation == accountGeneration else { return }
                refreshInstalled()
                error = nil
                queuedDownloads.removeAll { $0 == appID }
                repairDownloads.remove(appID)
            } catch is CancellationError {
                // Explicit pauses stay paused; launch suspension already requeued its active ID.
            } catch {
                guard generation == accountGeneration else { return }
                if !Task.isCancelled {
                    let message = SteamSignIn.message(error)
                    downloadErrors[appID] = message
                    self.error = message
                }
            }
            guard generation == accountGeneration, downloadTokens[appID] == token else { return }
            activeDownloads.remove(appID)
            if downloadErrors[appID] == nil && !pausedDownloads.contains(appID) {
                progress.removeValue(forKey: appID)
            }
            downloadTasks.removeValue(forKey: appID)
            downloadTokens.removeValue(forKey: appID)
            persistDownloadQueue()
            startNextDownload()
        }
        downloadTasks[appID] = task
    }

    func pause(_ id: Int) {
        guard let task = downloadTasks[id] else { return }
        pausedDownloads.insert(id)
        queuedDownloads.removeAll { $0 == id }
        persistDownloadQueue()
        task.cancel()
    }

    func resume(_ entry: SteamLibraryEntry) { download(entry) }

    private func requeueActiveDownloads() {
        let interrupted = activeDownloads.sorted().filter { !pausedDownloads.contains($0) }
        queuedDownloads = interrupted + queuedDownloads.filter { !interrupted.contains($0) }
        persistDownloadQueue()
    }

    func prepareValveClient() async {
        guard !isPreparingValveClient, !runtimeBusy else { return }
        let preserveLaunchReservation = sessionReservedForLaunch
        isPreparingValveClient = true
        sessionReservedForLaunch = true
        let generation = accountGeneration
        defer {
            if generation == accountGeneration {
                isPreparingValveClient = false
                startNextDownload()
            }
        }
        requeueActiveDownloads()
        await stopConnectionAndDownloads()
        guard generation == accountGeneration else { return }

        // The prefix seeder must not race a native Steam install creating its
        // first steamapps directory. Keep the account disconnected throughout.
        if runtimeBusy {
            error = "Close the active game session before preparing the Valve client."
        } else {
            do {
                try await SteamRuntimeInstaller.shared.prepare(prefix: MadeiraDock.prefix) { [weak self] stage in
                    await MainActor.run {
                        guard let self, generation == self.accountGeneration else { return }
                        self.valveClientPreparationStatus = stage
                    }
                }
                guard generation == accountGeneration else { return }
                valveClientPreparationStatus = nil
                error = nil
            } catch {
                guard generation == accountGeneration else { return }
                valveClientPreparationStatus = nil
                self.error = error.localizedDescription
            }
        }
        sessionReservedForLaunch = preserveLaunchReservation
        if signedIn, !runtimeBusy, !preserveLaunchReservation {
            session.resume()
            await connectAndLoad()
        }
    }

    /// Whether the program a launch option names is really in the game's install folder.
    /// Steam lists every platform's and build type's entry (Moss II VR has a Test build at option 0
    /// that is not installed), and starting a missing program fails with Steam's "could not find
    /// the game's executable" refusal.
    nonisolated static func isInstalled(_ option: SteamLaunchOption, game: DockGame, drive: URL) -> Bool {
        let relative = option.executable.replacingOccurrences(of: "\\", with: "/")
        guard !relative.isEmpty, !relative.hasPrefix("/"), !relative.contains("..") else { return false }
        let folder = drive.appendingPathComponent(game.library + "/common/" + game.installDir, isDirectory: true)
        return FileManager.default.fileExists(atPath: folder.appendingPathComponent(relative).path)
    }

    /// OpenComposite supplies SteamVR/OpenVR. Prefer that route over another VR
    /// runtime (for example Oculus), even when both entries name the same file.
    nonisolated static func preferredVRLaunchOption(_ options: [SteamLaunchOption]) -> SteamLaunchOption? {
        options.first(where: { $0.type.lowercased() == "vr" })
            ?? options.first(where: { $0.type.lowercased() == "othervr" })
    }

    /// The launch option to start by default: installed Windows entries, with
    /// SteamVR first. Returns nil when no Windows executable can be found.
    nonisolated static func preferredLaunchOption(_ options: [SteamLaunchOption], game: DockGame, drive: URL) -> SteamLaunchOption? {
        let windows = options.filter { $0.oslist.isEmpty || $0.oslist.lowercased().contains("windows") }
        let present = windows.filter { isInstalled($0, game: game, drive: drive) }
        return preferredVRLaunchOption(present)
            ?? present.first(where: { $0.type.isEmpty || $0.type == "default" })
            ?? present.first
    }

    func play(_ entry: SteamLibraryEntry, launchOption: UInt32? = nil) async {
        guard !runtimeBusy, signedIn else { return }
        guard !activeDownloads.contains(entry.id),
              !DepotDownloader.hasPartialDownload(appID: UInt32(entry.id), steamApps: SteamInstallPaths.steamApps(drive: MadeiraDock.drive)) else {
            error = "Finish or resume this game's download before selecting it to play."
            return
        }
        await prepareForLaunch()
        refreshInstalled()
        guard let game = MadeiraDock.games(drive: MadeiraDock.drive).first(where: { $0.id == entry.id }) else {
            error = "Steam has not finished installing this game yet."
            resumeAfterLaunchFailure()
            return
        }
        do {
            try MadeiraDock.validate(game, drive: MadeiraDock.drive)
            error = nil
            let options = entry.game.launches ?? []
            let preferred = Self.preferredLaunchOption(options, game: game, drive: MadeiraDock.drive)
                ?? Self.preferredVRLaunchOption(options)
                ?? options.first(where: { $0.type.isEmpty || $0.type == "default" })
                ?? options.first
            guard let onPlaySelected else {
                error = "The WineVision VR launcher is not ready yet."
                resumeAfterLaunchFailure()
                return
            }
            onPlaySelected(game, launchOption ?? preferred?.index ?? 0)
        } catch {
            self.error = error.localizedDescription
            resumeAfterLaunchFailure()
        }
    }

    func signOut() async {
        persistDownloadQueue()
        accountGeneration &+= 1
        let generation = accountGeneration
        signedIn = false
        accountName = nil
        await stopConnectionAndDownloads()
        guard generation == accountGeneration else { return }
        clearAccountDownloadState()
        SteamSignIn.signOut()
    }

    /// Releases the authenticated Steam connection before WineVision VR starts its
    /// Wine session. Waiting downloads and the interrupted active install survive.
    func prepareForLaunch() async {
        sessionReservedForLaunch = true
        requeueActiveDownloads()
        await stopConnectionAndDownloads()
    }

    /// Reconnects after a launch fails or a game session ends.
    func resumeAfterLaunchFailure() {
        guard !runtimeBusy, !isPreparingValveClient else { return }
        sessionReservedForLaunch = false
        guard suspendingDownloads == 0 else {
            resumeWhenDownloadsStop = true
            return
        }
        session.resume()
        if signedIn { Task { await connectAndLoad(); startNextDownload() } }
    }

    private func stopConnectionAndDownloads() async {
        suspendingDownloads += 1
        defer {
            suspendingDownloads -= 1
            if suspendingDownloads == 0 && resumeWhenDownloadsStop {
                resumeWhenDownloadsStop = false
                resumeAfterLaunchFailure()
            }
        }
        let tasks = Array(downloadTasks.values)
        tasks.forEach { $0.cancel() }
        for task in tasks { await task.value }
        downloadTasks.removeAll()
        downloadTokens.removeAll()
        activeDownloads.removeAll()
        await session.suspend()
    }
}
