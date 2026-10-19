import Foundation
import Darwin

@_silgen_name("wvr_debugger_signal_probe_eligible")
private func debuggerSignalProbeEligible() -> Int32
@_silgen_name("wvr_debugger_signal_probe_run")
func debuggerSignalProbeRun() -> Int32

/// Configure debugserver before the unchanged upstream script attaches. LLVM's
/// QSetIgnoredExceptions handler rejects this policy after attachment (E35).
/// Breakpoints stay intercepted for Madeira's debugger-mediated JIT protocol.
enum MadeiraDebuggerScript {
    private static let prelude = #"""
    // WineVision pre-attach exception policy; upstream fallback remains intact.
    {
        let wvrPolicyResponse = '';
        try {
            wvrPolicyResponse = send_command('QSetIgnoredExceptions:EXC_BAD_ACCESS|EXC_BAD_INSTRUCTION__WVR_SOFTWARE_POLICY__');
        } catch (_) {
            // Older helpers may reject the packet; keep the upstream stop loop.
        }
        let wvrPolicyAccepted = wvrPolicyResponse === 'OK';
        log('WineVision JIT: pre-attach exception policy ' +
            (wvrPolicyAccepted ? 'accepted' : 'refused; upstream fallback retained'));
    }

    """#

    static func softwareExceptionsAreSafe() -> Bool {
        guard debuggerSignalProbeEligible() == 1 else { return false }
        let capacity = Int(EXC_TYPES_COUNT)
        var masks = [exception_mask_t](repeating: 0, count: capacity)
        var ports = [mach_port_t](repeating: 0, count: capacity)
        var behaviors = [exception_behavior_t](repeating: 0, count: capacity)
        var flavors = [thread_state_flavor_t](repeating: 0, count: capacity)
        var count = mach_msg_type_number_t(capacity)
        let result = masks.withUnsafeMutableBufferPointer { m in
            ports.withUnsafeMutableBufferPointer { p in
                behaviors.withUnsafeMutableBufferPointer { b in
                    flavors.withUnsafeMutableBufferPointer { f in
                        task_get_exception_ports(mach_task_self_, exception_mask_t(EXC_MASK_SOFTWARE),
                            m.baseAddress!, &count, p.baseAddress!, b.baseAddress!, f.baseAddress!)
                    }
                }
            }
        }
        let returned = ports.prefix(min(Int(count), capacity))
        defer {
            for port in returned where port != MACH_PORT_NULL {
                mach_port_deallocate(mach_task_self_, port)
            }
        }
        return result == KERN_SUCCESS && Int(count) <= capacity && returned.allSatisfy { $0 == MACH_PORT_NULL }
    }

    static func compose(upstream: Data, softwareExceptionsSafe: Bool = false) -> Data {
        let policy = prelude.replacingOccurrences(of: "__WVR_SOFTWARE_POLICY__",
            with: softwareExceptionsSafe ? "|EXC_SOFTWARE" : "")
        var script = Data(policy.utf8)
        script.append(upstream)
        return script
    }
}
