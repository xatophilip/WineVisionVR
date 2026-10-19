import Foundation

/// Defaults must reach Wine even when the app uses the preserved native plugin.
/// Explicit process/manifest overrides remain available for controlled comparisons.
enum WindowsVRTranslationEnvironment {
    static let defaults: [String: String] = [
        "FEX_MULTIBLOCK": "1",
        // A compilation-size candidate; validate against the upstream 5000 default.
        "FEX_MAXINST": "512",
        "FEX_SILENTLOG": "1",
        // Keep the experimental cache launcher opt-in. A headset startup
        // regression exposed missing per-child Wine GDI state with the wrapper.
        // Explicit environment overrides still allow controlled comparisons.
        "FEX_ENABLECODECACHINGWIP": "0",
        "FEX_ENABLELAZYCODECACHINGWIP": "0",
        "FEX_ENABLECODECACHEVALIDATION": "0",
        // A first fatal fault can otherwise synchronously write a 640 MiB
        // sparse JIT image. Keep compact fault logs; opt in to full dumps.
        "MADEIRA_JIT_DUMP": "0"
    ]

    static func applyDefaults() {
        for (name, value) in defaults where getenv(name) == nil {
            setenv(name, value, 0)
        }
    }
}
