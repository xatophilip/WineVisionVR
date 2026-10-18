// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 WineVision VR contributors

import Foundation

/// Opt-in Unity 5.6 quality diagnostic, using CyberThreat's existing Fastest
/// preset. This does not change game assets, preferences or normal launches.
enum SteamCyberThreatCompatibility {
    static let appID = 516590
    static let diagnosticFlag = "--cyberthreat-low-memory-test"
    static let qualityArguments = "-screen-quality Fastest"

    static func arguments(appID: Int, base: String?, enabled: Bool,
                          processArguments: [String]) -> String? {
        guard enabled, appID == Self.appID,
              processArguments.contains(diagnosticFlag) else { return base }
        // Inspect tokens without rewriting the original Windows command line.
        // Malformed quoting also preserves the caller's text unchanged.
        guard let tokens = tokens(base ?? ""),
              !tokens.contains(where: {
                  let option = $0.lowercased()
                  return option == "-screen-quality" || option.hasPrefix("-screen-quality=")
              }) else { return base }
        guard let base, !base.isEmpty else { return qualityArguments }
        return base + " " + qualityArguments
    }

    private static func tokens(_ command: String) -> [String]? {
        let characters = Array(command)
        var index = 0
        var result: [String] = []
        while index < characters.count {
            while index < characters.count && (characters[index] == " " || characters[index] == "\t") { index += 1 }
            if index == characters.count { break }
            var token = ""
            var quoted = false
            while index < characters.count {
                let character = characters[index]
                if !quoted && (character == " " || character == "\t") { break }
                if character == "\\" {
                    var slashes = 0
                    while index < characters.count && characters[index] == "\\" { slashes += 1; index += 1 }
                    if index < characters.count && characters[index] == "\"" {
                        token += String(repeating: "\\", count: slashes / 2)
                        if slashes % 2 == 1 { token.append("\""); index += 1 }
                        else { quoted.toggle(); index += 1 }
                    } else { token += String(repeating: "\\", count: slashes) }
                } else if character == "\"" {
                    if quoted && index + 1 < characters.count && characters[index + 1] == "\"" {
                        token.append("\""); index += 2
                    } else { quoted.toggle(); index += 1 }
                } else { token.append(character); index += 1 }
            }
            guard !quoted else { return nil }
            result.append(token)
        }
        return result
    }
}
