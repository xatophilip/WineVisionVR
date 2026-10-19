import Foundation
import WindowsVRCore

/// Observations of this attempt, not a declaration that a game is playable.
/// Visible time excludes leaving/pausing the immersive view.
struct GuestSessionHealth: Sendable {
    enum Failure: Equatable, Sendable {
        case rendering
        case guestExit(UInt32)
        case repeatedFault
        case compatibilityDialog
        case rendererInitialization
    }
    enum Notice: Equatable, Sendable {
        case noFrames, stalledFrames, reportedFailure(Failure)

        var isFailure: Bool {
            if case .reportedFailure = self { return true }
            return false
        }
        var title: String {
            switch self {
            case .noFrames: return L("Still waiting for the game", "Warte weiterhin auf das Spiel")
            case .stalledFrames: return L("The game is not sending new VR frames", "Das Spiel sendet keine neuen VR-Bilder")
            case .reportedFailure(.compatibilityDialog): return L("The game stopped on a compatibility error", "Das Spiel wurde durch einen Kompatibilitätsfehler angehalten")
            case .reportedFailure(.rendererInitialization): return L("The game could not initialize its renderer", "Das Spiel konnte seinen Renderer nicht initialisieren")
            case .reportedFailure(.rendering): return L("VR rendering reported an error", "Das VR-Rendering meldet einen Fehler")
            case .reportedFailure(.guestExit): return L("The game ended with an error", "Das Spiel wurde mit einem Fehler beendet")
            case .reportedFailure(.repeatedFault): return L("The runtime reported a fatal error", "Die Laufzeit meldet einen schwerwiegenden Fehler")
            }
        }
        var detail: String {
            switch self {
            case .noFrames:
                return L("No VR frame has been observed for 35 seconds. The game may still be loading or waiting for input. You can wait or end the session.",
                         "Seit 35 Sekunden wurde kein VR-Bild empfangen. Das Spiel lädt möglicherweise noch oder wartet auf eine Eingabe. Du kannst warten oder die Sitzung beenden.")
            case .stalledFrames:
                return L("No new VR frame has been observed for 45 seconds. Loading, a game pause or an error may be responsible; this does not confirm a crash.",
                         "Seit 45 Sekunden wurde kein neues VR-Bild empfangen. Laden, eine Spielpause oder ein Fehler kann die Ursache sein; ein Absturz ist damit nicht bestätigt.")
            case .reportedFailure(.compatibilityDialog):
                return L("OpenComposite opened a fatal error dialog inside Windows. The game cannot continue loading. End the session and reopen the app to retry; its logs are saved.",
                         "OpenComposite hat in Windows einen schwerwiegenden Fehlerdialog geöffnet. Das Spiel kann nicht weiterladen. Beende die Sitzung und öffne die App erneut; die Protokolle wurden gespeichert.")
            case .reportedFailure(.rendererInitialization):
                return L("The Windows game opened a fatal RenderDeviceMgr001 initialization dialog. Loading cannot continue. End the session; its logs are saved for diagnosis.",
                         "Das Windows-Spiel hat einen schwerwiegenden RenderDeviceMgr001-Initialisierungsdialog geöffnet. Das Laden kann nicht fortgesetzt werden. Beende die Sitzung; die Protokolle wurden zur Diagnose gespeichert.")
            case .reportedFailure(.guestExit(let code)):
                return L("The current game reported exit code \(code). End this session, then close and reopen the app to try again. Its logs are saved.",
                         "Das aktuelle Spiel meldete den Exit-Code \(code). Beende diese Sitzung und öffne die App erneut, um es noch einmal zu versuchen. Die Protokolle wurden gespeichert.")
            case .reportedFailure:
                return L("An error was recorded in this session. You can end the session and reopen the app to retry. Returning to VR does not relaunch the game.",
                         "In dieser Sitzung wurde ein Fehler aufgezeichnet. Du kannst die Sitzung beenden und die App für einen neuen Versuch erneut öffnen. Zurück zu VR startet das Spiel nicht neu.")
            }
        }
    }

    private var lastTime: Double
    private var lastFrames: UInt64
    private var hasFrame = false
    private var visibleTime = 0.0
    private var lastProgressTime = 0.0
    private var wasVisible = false
    private(set) var notice: Notice?

    init(now: Double, initialFrames: UInt64 = 0) {
        lastTime = now
        lastFrames = initialFrames
    }

    mutating func update(now: Double, frames: UInt64?, visible: Bool,
                         running: Bool, failure: Failure? = nil) -> Notice? {
        guard running else {
            notice = nil
            lastTime = now
            wasVisible = false
            return nil
        }
        let delta = max(0, now - lastTime)
        if visible && wasVisible { visibleTime += delta }
        if visible && !wasVisible { lastProgressTime = visibleTime }
        lastTime = now
        wasVisible = visible
        var advanced = false
        if let frames {
            advanced = frames > lastFrames || (frames < lastFrames && frames > 0)
            lastFrames = frames
        }
        if advanced {
            hasFrame = true
            lastProgressTime = visibleTime
            notice = nil
        }
        if let failure {
            notice = .reportedFailure(failure)
        } else if visible, notice?.isFailure != true {
            let waiting = visibleTime - lastProgressTime
            if !hasFrame && waiting >= 35 { notice = .noFrames }
            else if hasFrame && waiting >= 45 { notice = .stalledFrames }
            else { notice = nil }
        } else if !visible, notice?.isFailure != true {
            notice = nil
        }
        return notice
    }
}

/// Reads only newly written, bounded chunks of the app-owned current runtime log.
/// PID, file identity, launch-time modification and an initial byte baseline
/// exclude earlier attempts. Generic DLL lookup warnings are never fatal evidence.
actor GuestSessionLogMonitor {
    static let maximumReadBytes = 256 * 1024
    private let url: URL
    private let expectedPID: Int32
    private let expectedExecutable: String?
    private let startedAt: Date
    private var identity: String?
    private var offset: UInt64 = 0
    private var pending = ""
    private var currentPID = false
    private var gameThreads: Set<String> = []

    init(url: URL, expectedPID: Int32, expectedExecutable: String?, startedAt: Date = Date()) {
        self.url = url
        self.expectedPID = expectedPID
        self.expectedExecutable = expectedExecutable?.replacingOccurrences(of: "\\", with: "/")
            .split(separator: "/").last.map { String($0).lowercased() }
        self.startedAt = startedAt
        if let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
           attributes[.type] as? FileAttributeType == .typeRegular {
            identity = Self.fileIdentity(attributes)
            offset = (attributes[.size] as? NSNumber)?.uint64Value ?? 0
        }
    }

    private static func fileIdentity(_ attributes: [FileAttributeKey: Any]) -> String {
        "\((attributes[.systemNumber] as? NSNumber)?.uint64Value ?? 0):\((attributes[.systemFileNumber] as? NSNumber)?.uint64Value ?? 0)"
    }

    func currentGameWasObserved() -> Bool { currentPID && !gameThreads.isEmpty }

    func sample() -> GuestSessionHealth.Failure? {
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
              attributes[.type] as? FileAttributeType == .typeRegular,
              let modified = attributes[.modificationDate] as? Date,
              modified >= startedAt,
              let bytes = (attributes[.size] as? NSNumber)?.uint64Value else { return nil }
        let nextIdentity = Self.fileIdentity(attributes)
        if identity != nextIdentity || bytes < offset {
            identity = nextIdentity
            offset = 0
            pending = ""
            currentPID = false
            gameThreads.removeAll()
        }
        guard bytes > offset, let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }
        do {
            try handle.seek(toOffset: offset)
            guard let data = try handle.read(upToCount: Self.maximumReadBytes), !data.isEmpty else { return nil }
            offset += UInt64(data.count)
            let text = pending + String(decoding: data, as: UTF8.self)
            var lines = text.components(separatedBy: "\n")
            pending = String((lines.popLast() ?? "").suffix(4096))
            var failure: GuestSessionHealth.Failure?
            for line in lines {
                if line.contains("running image "), line.contains("/WindowsRuntimePlugin.framework/WindowsRuntimePlugin "),
                   line.contains(" LC_UUID="),
                   let range = line.range(of: " pid=") {
                    let value = line[range.upperBound...].prefix { $0.isNumber }
                    let matches = Int32(value) == expectedPID
                    if !matches || !currentPID { gameThreads.removeAll() }
                    currentPID = matches
                }
                guard currentPID else { continue }
                let content: String
                if line.first == "[", let prefix = line.range(of: "] ") {
                    content = String(line[prefix.upperBound...])
                } else { content = line }
                let parts = content.split(whereSeparator: { $0.isWhitespace })
                if let expectedExecutable, parts.count >= 5, parts[0] == "D",
                   parts[2] == "Load", parts[3] == "module",
                   let moduleStart = content.range(of: " Load module ")?.upperBound,
                   let moduleEnd = content.range(of: " (", range: moduleStart..<content.endIndex)?.lowerBound,
                   content[moduleStart..<moduleEnd].lowercased() == expectedExecutable,
                   let thread = UInt32(parts[1], radix: 16) {
                    gameThreads.insert(String(thread, radix: 16))
                }
                // Exact runtime window-title evidence, after this native process and
                // current game have been identified. A generic OC warning is not fatal.
                if !gameThreads.isEmpty, line.hasPrefix("[win-name] "),
                   line.contains("text=\"OpenComposite Error - info in log\"") {
                    failure = .compatibilityDialog
                } else if !gameThreads.isEmpty, line.hasPrefix("[win-name] "),
                          line.contains("text=\"CAppSystemDict::LoadSystemAndDependencies():"),
                          line.contains("Error in Connect() of interface 'RenderDeviceMgr001'!") {
                    failure = .rendererInitialization
                } else if line.contains("[redeliv] terminating process") {
                    failure = .repeatedFault
                } else if line.contains("Cannot create DX texture swap chain: err ") {
                    failure = .rendering
                } else if line.contains(":err:process:NtTerminateProcess "),
                          line.contains("NtTerminateProcess(handle=0x0, exit_code=0x"),
                          let threadEnd = content.firstIndex(of: ":"),
                          let thread = UInt32(content[..<threadEnd], radix: 16),
                          gameThreads.contains(String(thread, radix: 16)),
                          let codeStart = line.range(of: "exit_code=0x")?.upperBound {
                    let code = line[codeStart...].prefix { $0.isHexDigit }
                    if let number = UInt32(code, radix: 16), number != 0 { failure = .guestExit(number) }
                }
            }
            return failure
        } catch { return nil }
    }
}
