import Foundation
import GameController

/// Pure Windows-key mapping shared by the latest-state sampler and host checks.
/// Either Sense stick moves; either hand can supply the listed buttons.
enum WindowsDesktopGamepadMapping {
    static let stickThreshold: Float = 0.4

    static func keys(pressed: (String) -> Bool, axis: (String) -> Float?,
                     stick: (String) -> (Float, Float)?) -> Set<Int32> {
        var keys: Set<Int32> = []
        func button(_ aliases: [String], key: Int32) {
            if aliases.contains(where: pressed) { keys.insert(key) }
        }
        // Match the physical keyboard mapper's left modifier VKs, so the
        // shared held-source union cannot release a still-held physical key.
        button(["Trigger", "Left Trigger", "Right Trigger"], key: 0xA2)
        button(["Primary Button", "Button A", "Button X"], key: 0xA4)
        button(["Secondary Button", "Button B", "Button Y"], key: 0x20)
        button(["Grip Button", "Grip", "Tip", "Left Shoulder", "Right Shoulder"], key: 0xA0)
        button([GCInputButtonMenu, GCInputButtonOptions, GCInputButtonShare], key: 0x1B)
        button(["Thumbstick Button", "Left Thumbstick Button", "Right Thumbstick Button"], key: 0x0D)
        for name in ["Thumbstick", "Left Thumbstick", "Right Thumbstick"] {
            let values = stick(name) ?? (axis(name + " X Axis") ?? 0, axis(name + " Y Axis") ?? 0)
            if values.0.isFinite {
                if values.0 >= stickThreshold { keys.insert(0x27) }
                if values.0 <= -stickThreshold { keys.insert(0x25) }
            }
            if values.1.isFinite {
                if values.1 >= stickThreshold { keys.insert(0x26) }
                if values.1 <= -stickThreshold { keys.insert(0x28) }
            }
        }
        return keys
    }

    static func allowed(supported: Bool, enabled: Bool, accepted: Bool, stopping: Bool,
                        stopRequested: Bool, requiresRestart: Bool, sceneActive: Bool) -> Bool {
        supported && enabled && accepted && !stopping && !stopRequested && !requiresRestart && sceneActive
    }
}

/// Flat-window buttons need GameController only. No world sensing, ARKit session,
/// immersive space, synthetic poses or VR provider state is involved.
@MainActor
@available(visionOS 27.0, *)
final class WindowsDesktopGamepad {
    private var generation: UInt64 = 0

    func run(enabled: Bool, apply: @escaping @MainActor (Set<Int32>) -> Void) async {
        generation &+= 1
        let current = generation
        guard enabled else { apply([]); return }
        defer { if generation == current { apply([]) } }
        while !Task.isCancelled && generation == current {
            apply(Self.currentKeys())
            try? await Task.sleep(for: .milliseconds(16))
        }
    }

    private static func currentKeys() -> Set<Int32> {
        var devices: [any GCDevice] = GCSpatialAccessory.spatialAccessories
        let identifiers = Set(devices.map { ObjectIdentifier($0 as AnyObject) })
        devices.append(contentsOf: GCController.controllers().filter {
            $0.productCategory == GCProductCategorySpatialController && !identifiers.contains(ObjectIdentifier($0))
        })
        var keys: Set<Int32> = []
        for device in devices {
            let input: (any GCDevicePhysicalInput)?
            if let accessory = device as? GCSpatialAccessory { input = accessory.input }
            else { input = (device as? GCController)?.input }
            guard let input else { continue }
            // Empty transition queues do not release held buttons: sample the
            // complete latest state, exactly as the immersive input adapter does.
            let snapshot = input.capture()
            keys.formUnion(WindowsDesktopGamepadMapping.keys(
                pressed: { snapshot.buttons[$0]?.pressedInput.isPressed == true },
                axis: { snapshot.axes[$0]?.absoluteInput?.value },
                stick: { name in
                    guard let value = snapshot.dpads[name] else { return nil }
                    return (value.xAxis.value, value.yAxis.value)
                }))
        }
        // Missing/disconnected devices contribute no keys on this sample.
        return keys
    }
}
