import Foundation

/// Configure debugserver before the unchanged upstream script attaches. LLVM's
/// QSetIgnoredExceptions handler rejects this policy after attachment (E35).
/// Breakpoints stay intercepted for Madeira's debugger-mediated JIT protocol.
enum MadeiraDebuggerScript {
    private static let prelude = #"""
    // WineVision pre-attach exception policy; upstream fallback remains intact.
    {
        let wvrPolicyResponse = '';
        try {
            wvrPolicyResponse = send_command('QSetIgnoredExceptions:EXC_BAD_ACCESS|EXC_BAD_INSTRUCTION');
        } catch (_) {
            // Older helpers may reject the packet; keep the upstream stop loop.
        }
        let wvrPolicyAccepted = wvrPolicyResponse === 'OK';
        log('WineVision JIT: pre-attach exception policy ' +
            (wvrPolicyAccepted ? 'accepted' : 'refused; upstream fallback retained'));
    }

    """#

    static func compose(upstream: Data) -> Data {
        var script = Data(prelude.utf8)
        script.append(upstream)
        return script
    }
}
