// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 WineVision VR contributors

import Foundation

/// Valve's Lab Renderer supports these public launch switches. Its adaptive
/// quality otherwise grows the double-wide atlas beyond this runtime's current
/// supported eye/atlas sizes. Keep the game's source textures and files intact.
enum SteamLabCompatibility {
    static let appID = 450390
    static let fixedQualityArguments = "-noaq -aqmaxscale 1"

    static func arguments(appID: Int, base: String?) -> String? {
        guard appID == Self.appID else { return base }
        guard let base, !base.isEmpty else { return fixedQualityArguments }
        // Preserve explicit arguments byte-for-byte and before our defaults:
        // ValveCamera.GetCommandLineArgValue uses the first matching option.
        // Duplicate noaq flags are harmless; avoid parsing/requoting user text.
        if base == fixedQualityArguments || base.hasSuffix(" " + fixedQualityArguments) { return base }
        return base + " " + fixedQualityArguments
    }
}
