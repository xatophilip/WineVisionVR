// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 WineVision VR contributors

import Foundation

/// The Steam Tomb Raider I DOSBox package uses SDL 1 and a 3dfx renderer by
/// default. Keep its installed files intact and pass a separate software-renderer
/// configuration to Valve's normal launch request. Tested with the bundled SVN
/// DOSBox; this is not a global SDL setting or a replacement game engine.
enum SteamDOSBoxCompatibility {
    static let appID = 224960
    static let relativeConfiguration = "AVPPlaySteam/Compatibility/224960/software.conf"
    static let settings = """
    [sdl]
    fullscreen=false
    output=surface
    autolock=false
    [render]
    scaler=normal2x
    [glide]
    glide=false
    [ne2000]
    ne2000=false

    """

    static func supports(appID: Int, executable: String?) -> Bool {
        guard appID == Self.appID, let executable else { return false }
        let normalized = executable.replacingOccurrences(of: "\\", with: "/")
        return ["dosbox.exe", "./dosbox.exe"].contains(normalized.lowercased())
    }

    /// Writes only the app-owned settings file. The original game/configuration
    /// files and appmanifest remain untouched. Missing/ambiguous software content
    /// fails before Steam credentials are handed over rather than guessing a DOS
    /// short name. Other games and optional native Tomb Raider launchers are nil.
    static func prepare(game: DockGame, option: SteamLaunchOption?, drive: URL) throws -> String? {
        if game.id == appID, option == nil {
            throw DockError.message("Refresh Tomb Raider in the Steam library and select its DOSBox launch option before retrying.")
        }
        guard supports(appID: game.id, executable: option?.executable) else { return nil }
        guard let option,
              SteamInstalledExecutable.resolve(option.executable, game: game, drive: drive) != nil,
              SteamInstalledExecutable.resolve("dosboxTRWindowed.conf", game: game, drive: drive) != nil,
              SteamInstalledExecutable.resolve("GAME.DAT", game: game, drive: drive) != nil,
              let software = SteamInstalledExecutable.resolve("TOMBRAID/TOMBno3Dfx.EXE", game: game, drive: drive) else {
            throw DockError.message("Tomb Raider's bundled DOSBox/software-renderer files are incomplete. Verify or repair the game in Steam.")
        }
        // This package's actual DOS DIR reports TOMBNO~1.EXE. A competing long
        // name or an explicit short-name file could change that mapping.
        let entries = try FileManager.default.contentsOfDirectory(at: software.deletingLastPathComponent(),
                                                                  includingPropertiesForKeys: nil)
        let candidates = entries.filter { $0.lastPathComponent.uppercased().hasPrefix("TOMBNO") }
        guard candidates.count == 1,
              candidates[0].lastPathComponent.caseInsensitiveCompare("TOMBno3Dfx.EXE") == .orderedSame else {
            throw DockError.message("Tomb Raider's software executable has an ambiguous DOS short name. Restore the original Steam game files before retrying.")
        }
        let manager = FileManager.default
        var folder = drive.resolvingSymlinksInPath().standardizedFileURL
        for component in ["AVPPlaySteam", "Compatibility", "224960"] {
            folder.appendPathComponent(component, isDirectory: true)
            let values = try? folder.resourceValues(forKeys: [.isSymbolicLinkKey, .isDirectoryKey])
            guard values?.isSymbolicLink != true, values?.isDirectory != false else {
                throw DockError.message("The DOSBox compatibility folder is unsafe.")
            }
            if values == nil { try manager.createDirectory(at: folder, withIntermediateDirectories: false) }
        }
        let configuration = folder.appendingPathComponent("software.conf")
        let values = try? configuration.resourceValues(forKeys: [.isSymbolicLinkKey, .isRegularFileKey])
        guard values?.isSymbolicLink != true, values?.isRegularFile != false else {
            throw DockError.message("The DOSBox compatibility configuration is unsafe.")
        }
        try Data(settings.utf8).write(to: configuration, options: .atomic)
        // DOSBox appends every config's [autoexec]. Suppress those sections and
        // supply the proven commands once, after Steam's vendor -conf arguments.
        // Steam supplies this option's working directory, the installed game root.
        let path = "C:\\" + relativeConfiguration.replacingOccurrences(of: "/", with: "\\")
        return "-conf \"\(path)\" -noautoexec -c \"mount C .\" -c \"imgmount d GAME.DAT -t iso -fs iso\" -c \"C:\" -c \"cd TOMBRAID\" -c \"TOMBNO~1.EXE\""
    }
}
