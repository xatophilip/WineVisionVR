import Foundation
import XCTest
@testable import WindowsVRCore

final class ContractsTests: XCTestCase {
    private func manifest(path: String = "Game/bin/game.exe", environment: [String: String] = [:]) throws -> WindowsGameManifest {
        try WindowsGameManifest(id: "example", title: "Example", executableRelativePath: path,
                                backend: .windowsWineFEX, graphics: .direct3D12,
                                launchArguments: ["-vr"], environment: environment, schemaVersion: 1)
    }

    func testManifestRoundTripAndLegacyEnvironmentDefault() throws {
        let original = try manifest()
        let data = try JSONEncoder().encode(original)
        XCTAssertEqual(try JSONDecoder().decode(WindowsGameManifest.self, from: data), original)
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        json.removeValue(forKey: "environment")
        json.removeValue(forKey: "presentation")
        let legacy = try JSONSerialization.data(withJSONObject: json)
        XCTAssertEqual(try JSONDecoder().decode(WindowsGameManifest.self, from: legacy).environment, [:])
        XCTAssertEqual(try JSONDecoder().decode(WindowsGameManifest.self, from: legacy).presentation, .immersiveVR)
    }

    func testWrappedGameArchitectureSurvivesManifestAndProfile() throws {
        let selected = try WindowsGameManifest(id: "steam.shared", title: "32-bit Steam game",
            executableRelativePath: "dockhost.exe", backend: .windowsWineFEX,
            graphics: .direct3D11, launchArguments: [], guestArchitecture: .x86, schemaVersion: 1)
        XCTAssertEqual(try JSONDecoder().decode(WindowsGameManifest.self,
            from: JSONEncoder().encode(selected)).guestArchitecture, .x86)
        let profile = try WindowsVRLaunchProfile(name: "VR", backend: .windowsWineFEX,
            graphics: .direct3D11, launchArguments: [])
        XCTAssertEqual(try profile.applying(to: selected).guestArchitecture, .x86)
        XCTAssertNil(try manifest().guestArchitecture)
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(selected)) as? [String: Any])
        json["guestArchitecture"] = "unsupported"
        XCTAssertThrowsError(try JSONDecoder().decode(WindowsGameManifest.self,
            from: JSONSerialization.data(withJSONObject: json)))
    }

    func testWindowsAndPOSIXPathEscapesRejected() throws {
        for path in ["../game.exe", "bin/../game.exe", "C:game.exe", "C:\\game.exe", "/game.exe",
                     "\\\\server\\game.exe", "bin//game.exe", "bin\\..\\game.exe", "game\0.exe"] {
            XCTAssertThrowsError(try manifest(path: path), path)
        }
        XCTAssertNoThrow(try manifest(path: "Game\\bin\\game.exe"))
    }

    func testReservedRuntimeEnvironmentCannotBeOverridden() {
        for key in ["HOME", "WINEPREFIX", "WINEDLLPATH", "XR_RUNTIME_JSON", "WINEDLLOVERRIDES",
                    "DYLD_INSERT_LIBRARIES", "WINE_IOS_JIT_BASE", "MADEIRA_RUNTIME", "bad=name"] {
            XCTAssertThrowsError(try manifest(environment: [key: "value"]), key)
        }
        XCTAssertNoThrow(try manifest(environment: ["GAME_LANGUAGE": "en"]))
    }

    func testInvalidDecodedManifestCannotBypassValidation() throws {
        let data = try JSONEncoder().encode(manifest())
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        json["executableRelativePath"] = "../game.exe"
        XCTAssertThrowsError(try JSONDecoder().decode(WindowsGameManifest.self,
                                                     from: JSONSerialization.data(withJSONObject: json)))
        json["executableRelativePath"] = "game.exe"
        json["schemaVersion"] = 2
        XCTAssertThrowsError(try JSONDecoder().decode(WindowsGameManifest.self,
                                                     from: JSONSerialization.data(withJSONObject: json)))
    }

    func testLaunchProfileLegacyScaleAndInvalidDecodedScale() throws {
        let profile = try WindowsVRLaunchProfile(name: " Stereo ", backend: .windowsWineFEX,
                                                 graphics: .direct3D11, launchArguments: [])
        XCTAssertEqual(profile.name, "Stereo")
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(profile)) as? [String: Any])
        json.removeValue(forKey: "renderScale")
        let legacy = try JSONDecoder().decode(WindowsVRLaunchProfile.self,
                                              from: JSONSerialization.data(withJSONObject: json))
        XCTAssertEqual(legacy.renderScale, 1)
        json["renderScale"] = 1.1
        XCTAssertThrowsError(try JSONDecoder().decode(WindowsVRLaunchProfile.self,
                                                     from: JSONSerialization.data(withJSONObject: json)))
    }

    func testProfileEnvironmentRevalidatedWhenApplied() throws {
        var profile = try WindowsVRLaunchProfile(name: "Stereo", backend: .windowsWineFEX,
                                                 graphics: .direct3D11, launchArguments: [])
        profile.environment = ["WINEPREFIX": "override"]
        XCTAssertThrowsError(try profile.applying(to: manifest()))
    }

    func testDesktopModeRoundTripProfileAndLegacyCapabilities() throws {
        let desktop = try WindowsVRLaunchProfile(name: "Desktop", backend: .windowsWineFEX,
            graphics: .direct3D11, launchArguments: [], presentation: .desktop)
        let applied = try desktop.applying(to: manifest())
        XCTAssertEqual(applied.presentation, .desktop)
        XCTAssertEqual(try JSONDecoder().decode(WindowsGameManifest.self,
            from: JSONEncoder().encode(applied)).presentation, .desktop)
        XCTAssertTrue(WindowsPresentationMode.immersiveVR.isSupported(by: nil))
        XCTAssertFalse(WindowsPresentationMode.desktop.isSupported(by: nil))
        XCTAssertFalse(WindowsPresentationMode.desktop.isSupported(by: 1))
        XCTAssertTrue(WindowsPresentationMode.desktop.isSupported(by: 3))
        var profileJSON = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(desktop)) as? [String: Any])
        profileJSON.removeValue(forKey: "presentation")
        XCTAssertEqual(try JSONDecoder().decode(WindowsVRLaunchProfile.self,
            from: JSONSerialization.data(withJSONObject: profileJSON)).presentation, .immersiveVR)
        var manifestJSON = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(applied)) as? [String: Any])
        manifestJSON["presentation"] = "unknown-display-mode"
        XCTAssertThrowsError(try JSONDecoder().decode(WindowsGameManifest.self,
            from: JSONSerialization.data(withJSONObject: manifestJSON)))
    }

    func testDesktopKeyboardPrintableRangeAndHardwareKeys() {
        for value in UInt8(32)...UInt8(126) {
            XCTAssertNotNil(WindowsDesktopKeyboard.stroke(for: Character(UnicodeScalar(value))))
        }
        XCTAssertNil(WindowsDesktopKeyboard.stroke(for: "é"))
        XCTAssertNil(WindowsDesktopKeyboard.stroke(for: "🙂"))
        XCTAssertEqual(WindowsDesktopKeyboard.stroke(for: "A")?.key, 0x41)
        XCTAssertEqual(WindowsDesktopKeyboard.stroke(for: "A")?.shift, true)
        XCTAssertEqual(WindowsDesktopKeyboard.stroke(for: "a")?.shift, false)
        XCTAssertEqual(WindowsDesktopKeyboard.stroke(for: "\\")?.key, 0xDC)
        XCTAssertEqual(WindowsDesktopKeyboard.stroke(for: "\n")?.key, 0x0D)
        XCTAssertEqual(WindowsDesktopKeyboard.virtualKey(hidUsage: 0x04), 0x41)
        XCTAssertEqual(WindowsDesktopKeyboard.virtualKey(hidUsage: 0x1D), 0x5A)
        XCTAssertEqual(WindowsDesktopKeyboard.virtualKey(hidUsage: 0x52), 0x26)
        XCTAssertEqual(WindowsDesktopKeyboard.virtualKey(hidUsage: 0xE5), 0xA1)
        XCTAssertNil(WindowsDesktopKeyboard.virtualKey(hidUsage: 0))
    }

    func testStereoEyeAssignmentAndTemporalMetadata() throws {
        let left = PerEyeFrameMetadata(eye: .left, size: .init(width: 1024, height: 1024))
        let right = PerEyeFrameMetadata(eye: .right, size: .init(width: 1024, height: 1024))
        XCTAssertNoThrow(try WindowsVRFrameMetadata(leftEye: left, rightEye: right).validate())
        XCTAssertThrowsError(try WindowsVRFrameMetadata(leftEye: right, rightEye: left).validate())
        let depth = PerEyeFrameMetadata(eye: .left, size: left.size,
                                       depth: .init(encoding: .linearMeters, nearMeters: 1, farMeters: 0.5))
        XCTAssertThrowsError(try depth.validate())
        let motion = PerEyeFrameMetadata(eye: .left, size: left.size,
                                         motion: .init(coordinateSpace: .pixels, frameDeltaSeconds: .nan))
        XCTAssertThrowsError(try motion.validate())
    }

    func testDiagnosticExportOmitsEnvironmentValuesAndMakesNoPerformanceClaim() throws {
        let request = WindowsVRRequestedProfile(gameID: "example", gameTitle: "Example", profileID: nil,
                                                profileName: "Default", backend: .windowsWineFEX,
                                                graphics: .direct3D11, executableRelativePath: "game.exe",
                                                launchArguments: [], environment: ["GAME_LANGUAGE": "private-fixture"])
        let report = WindowsVRCompatibilityReport(deviceModel: "fixture", operatingSystemName: "fixture",
                                                  operatingSystemVersion: "0", operatingSystemBuildDescription: "fixture",
                                                  requestedProfile: request, runtimePluginAvailable: false,
                                                  wineStatus: .init(stateCode: nil, state: "not started", detail: nil),
                                                  compositorCounters: nil, capabilities: [])
        let json = String(decoding: try report.encodedJSON(), as: UTF8.self)
        XCTAssertTrue(json.contains("GAME_LANGUAGE"))
        XCTAssertFalse(json.contains("private-fixture"))
        XCTAssertTrue(report.unmeasuredMetrics.allSatisfy { $0.value == L("unknown / not measured", "unbekannt / nicht gemessen") })
        XCTAssertFalse(WindowsVRUpscalerOptions(mapDLSSSuperResolutionToMetalFXTemporalScaling: true).frameGenerationEnabled)
        XCTAssertFalse(WindowsVRUpscalerOptions().foveationEnabled)
    }
}
