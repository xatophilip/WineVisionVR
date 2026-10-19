#!/usr/bin/env python3
"""Compile the production Swift composer and execute its actual upstream script.

Pass the immutable packaged madeira-jit.js with --upstream; no substitute script
or text rewrite is used. Node's mocked debugserver checks real stop-loop behavior.
"""
from pathlib import Path
import argparse, hashlib, json, shutil, subprocess, tempfile

ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser()
p.add_argument('--upstream', required=True, type=Path)
p.add_argument('--build', type=Path)
p.add_argument('--source-root', type=Path, default=ROOT)
a = p.parse_args()
source = a.source_root / 'Sources/MadeiraDebuggerScript.swift'
coordinator = a.source_root / 'Sources/JITCoordinator.swift'
probe_source = a.source_root / 'Sources/MadeiraDebuggerSignalProbe.c'
source_paths = [source, coordinator, probe_source, Path(__file__).resolve()]
def source_hashes():
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
before_hashes = source_hashes()
coordinator_text = coordinator.read_text()
assert 'let script = MadeiraDebuggerScript.compose(upstream: try Data(contentsOf: scriptURL), softwareExceptionsSafe: softwareSafe)' in coordinator_text
assert 'URLQueryItem(name: "script-data", value: script.base64EncodedString())' in coordinator_text
script_loading = coordinator_text.split('let script = ', 1)[1].split('var components = URLComponents()', 1)[0]
assert script_loading.strip() == 'MadeiraDebuggerScript.compose(upstream: try Data(contentsOf: scriptURL), softwareExceptionsSafe: softwareSafe)', 'Coordinator rewrites the composed script'
upstream = a.upstream.resolve()
assert upstream.is_file()
node = shutil.which('node')
assert node, 'Node is required to execute the production JavaScript'
build = a.build or Path(tempfile.mkdtemp(prefix='wvr-debugger-policy-'))
build.mkdir(parents=True, exist_ok=True)

SIGNAL_PROBE = r'''
#include <assert.h>
#include <signal.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
int wvr_debugger_signal_probe_eligible(void);
int wvr_debugger_signal_probe_run(void);
static void custom(int n) {(void)n;}
int main(void) {
 struct sigaction original1, original2, action={0}, observed;
 sigset_t original_mask, mask;
 assert(sigaction(SIGUSR1,NULL,&original1)==0);
 assert(sigaction(SIGUSR2,NULL,&original2)==0);
 assert(pthread_sigmask(SIG_SETMASK,NULL,&original_mask)==0);
 sigemptyset(&mask); assert(pthread_sigmask(SIG_SETMASK,&mask,NULL)==0);
 sigemptyset(&action.sa_mask); action.sa_handler=SIG_DFL;
 assert(sigaction(SIGUSR1,&action,NULL)==0); assert(sigaction(SIGUSR2,&action,NULL)==0);
 assert(wvr_debugger_signal_probe_eligible()==1);
 action.sa_handler=custom; action.sa_flags=SA_RESTART;
 assert(sigaction(SIGUSR1,&action,NULL)==0);
 assert(wvr_debugger_signal_probe_eligible()==0); assert(wvr_debugger_signal_probe_run()==1);
 assert(sigaction(SIGUSR1,NULL,&observed)==0 && observed.sa_handler==custom && (observed.sa_flags&SA_RESTART));
 action.sa_handler=SIG_DFL; assert(sigaction(SIGUSR1,&action,NULL)==0);
 sigaddset(&mask,SIGUSR2); assert(pthread_sigmask(SIG_SETMASK,&mask,NULL)==0);
 assert(wvr_debugger_signal_probe_eligible()==0); assert(wvr_debugger_signal_probe_run()==1);
 assert(pthread_sigmask(SIG_SETMASK,NULL,&mask)==0 && sigismember(&mask,SIGUSR2)==1);
 sigdelset(&mask,SIGUSR2); assert(pthread_sigmask(SIG_SETMASK,&mask,NULL)==0);
 action.sa_handler=SIG_IGN; action.sa_flags=SA_RESTART; sigaddset(&action.sa_mask,SIGTERM);
 assert(sigaction(SIGUSR1,&action,NULL)==0); assert(sigaction(SIGUSR2,&action,NULL)==0);
 assert(wvr_debugger_signal_probe_run()==0);
 assert(sigaction(SIGUSR1,NULL,&observed)==0 && observed.sa_handler==SIG_IGN && (observed.sa_flags&SA_RESTART) && sigismember(&observed.sa_mask,SIGTERM)==1);
 assert(sigaction(SIGUSR2,NULL,&observed)==0 && observed.sa_handler==SIG_IGN && (observed.sa_flags&SA_RESTART) && sigismember(&observed.sa_mask,SIGTERM)==1);
 assert(pthread_sigmask(SIG_SETMASK,NULL,&mask)==0 && sigismember(&mask,SIGUSR1)==0 && sigismember(&mask,SIGUSR2)==0);
 assert(sigaction(SIGUSR1,&original1,NULL)==0); assert(sigaction(SIGUSR2,&original2,NULL)==0);
 assert(pthread_sigmask(SIG_SETMASK,&original_mask,NULL)==0);
 puts("actual Darwin SIGUSR1/SIGUSR2 delivered; custom/masked refused; full dispositions/mask preserved");
}
'''
TASK_PORT_PROBE = r'''
import Foundation
import Darwin
assert(MadeiraDebuggerScript.softwareExceptionsAreSafe())
var port = mach_port_t()
assert(mach_port_allocate(mach_task_self_, mach_port_right_t(MACH_PORT_RIGHT_RECEIVE), &port) == KERN_SUCCESS)
assert(mach_port_insert_right(mach_task_self_, port, port, mach_msg_type_name_t(MACH_MSG_TYPE_MAKE_SEND)) == KERN_SUCCESS)
assert(task_set_exception_ports(mach_task_self_, exception_mask_t(EXC_MASK_SOFTWARE), port, EXCEPTION_DEFAULT, THREAD_STATE_NONE) == KERN_SUCCESS)
var before = mach_port_urefs_t()
assert(mach_port_get_refs(mach_task_self_, port, mach_port_right_t(MACH_PORT_RIGHT_SEND), &before) == KERN_SUCCESS)
for _ in 0..<5 { assert(!MadeiraDebuggerScript.softwareExceptionsAreSafe()) }
var after = mach_port_urefs_t()
assert(mach_port_get_refs(mach_task_self_, port, mach_port_right_t(MACH_PORT_RIGHT_SEND), &after) == KERN_SUCCESS)
assert(before == after, "Exception snapshot leaked send rights")
assert(task_set_exception_ports(mach_task_self_, exception_mask_t(EXC_MASK_SOFTWARE), mach_port_t(MACH_PORT_NULL), EXCEPTION_DEFAULT, THREAD_STATE_NONE) == KERN_SUCCESS)
assert(mach_port_deallocate(mach_task_self_, port) == KERN_SUCCESS)
assert(mach_port_mod_refs(mach_task_self_, port, mach_port_right_t(MACH_PORT_RIGHT_RECEIVE), -1) == KERN_SUCCESS)
assert(MadeiraDebuggerScript.softwareExceptionsAreSafe())
print("actual Darwin exception snapshot: NULL allows, custom port refuses, send rights unchanged")
'''

HELD_SIGNAL_PROBE = r'''
#include <assert.h>
#include <signal.h>
#include <pthread.h>
#include <stdio.h>
int wvr_debugger_signal_probe_run(void);
int wvr_held_pthread_kill(pthread_t thread, int signal_number) {
    (void)thread; (void)signal_number; return 0;
}
int main(void) {
    struct sigaction action={0}, observed;
    sigset_t mask;
    sigemptyset(&mask); assert(pthread_sigmask(SIG_SETMASK,&mask,NULL)==0);
    action.sa_handler=SIG_DFL; sigemptyset(&action.sa_mask);
    assert(sigaction(SIGUSR1,&action,NULL)==0); assert(sigaction(SIGUSR2,&action,NULL)==0);
    assert(wvr_debugger_signal_probe_run()==4);
    assert(sigaction(SIGUSR1,NULL,&observed)==0 && observed.sa_handler!=SIG_DFL && observed.sa_handler!=SIG_IGN);
    assert(sigaction(SIGUSR2,NULL,&observed)==0 && observed.sa_handler!=SIG_DFL && observed.sa_handler!=SIG_IGN);
    // Simulate late delivery after the timeout: retained handlers are benign.
    assert(pthread_kill(pthread_self(),SIGUSR1)==0); assert(pthread_kill(pthread_self(),SIGUSR2)==0);
    puts("held signal fails closed; late SIGUSR1/SIGUSR2 delivery remains benign");
}
'''
main = build / 'main.swift'
main.write_text('''import Foundation
let upstream = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
let composed = MadeiraDebuggerScript.compose(upstream: upstream, softwareExceptionsSafe: CommandLine.arguments.count > 3)
try composed.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
''')
subprocess.run(['clang', '-c', str(probe_source), '-o', str(build / 'probe.o')], check=True)
subprocess.run(['swiftc', str(source), str(main), str(build / 'probe.o'), '-o', str(build / 'compose')], check=True)
composed = build / 'composed.js'
subprocess.run([str(build / 'compose'), str(upstream), str(composed)], check=True)
assert composed.read_bytes().endswith(upstream.read_bytes()), 'Upstream bytes changed'
prelude = composed.read_bytes()[:-len(upstream.read_bytes())]
assert b'EXC_SOFTWARE' not in prelude and b'EXC_BREAKPOINT' not in prelude
harness = build / 'harness.js'
harness.write_text(r'''
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const upstream=fs.readFileSync(process.argv[2],'utf8');
const composed=fs.readFileSync(process.argv[3],'utf8');
const policy='QSetIgnoredExceptions:EXC_BAD_ACCESS|EXC_BAD_INSTRUCTION'+(process.argv[4]==='software'?'|EXC_SOFTWARE':'');
const le=n=>{let h=BigInt(n).toString(16).padStart(16,'0');return h.match(/../g).reverse().join('');};
const stop=(metype,medata=[],x16=0,x0=0,x1=0)=>'T05thread:1;20:'+le(4096)+';10:'+le(x16)+';00:'+le(x0)+';01:'+le(x1)+';metype:'+metype.toString(16)+';'+medata.map(x=>'medata:'+x.toString(16)+';').join('');
function run(script, scenario, mode){
 let attached=false, commands=[], logs=[], prepares=[], stops=scenario.stops.slice();
 const context={get_pid:()=>123,log:x=>logs.push(x),prepare_memory_region:(addr,size)=>{prepares.push([String(addr),String(size)]);return true;},send_command:cmd=>{
 commands.push(cmd);
 if(cmd===policy){assert(!attached,'policy must precede attachment');if(mode==='throw')throw new Error('unsupported');return mode==='accepted'?'OK':mode==='refused'?'E35':'';}
 if(cmd.startsWith('vAttach;')){attached=true;return 'T05';}
 if(cmd.startsWith('QSetIgnoredExceptions:'))return 'E35'; // unchanged legacy post-attach packet
 if(cmd.startsWith('QPassSignals:'))return 'OK';
 if(cmd==='c')return stops.shift()||'W00';
 if(cmd.startsWith('vCont;C')||/^C[0-9a-f]+$/.test(cmd))return scenario.forwardRejected?'':(stops.shift()||'W00');
 if(cmd.startsWith('m'))return scenario.instruction||'00000000';
 if(cmd.startsWith('_M'))return '2000';
 if(cmd.startsWith('P')||cmd==='D'||cmd==='k')return 'OK';
 throw new Error('unexpected command '+cmd);
 }};
 vm.runInNewContext(script,context,{timeout:2000});
 return {commands,logs,prepares};
}
const scenarios=[
 {name:'exit',stops:['W00']},
 {name:'modern-prepare',stops:[stop(6,[],1,0,4096)],instruction:le((0xd4200000|(0xf00d<<5))>>>0).slice(0,8)},
 {name:'modern-detach',stops:[stop(6)],instruction:le((0xd4200000|(0xf00d<<5))>>>0).slice(0,8)},
 {name:'legacy-prepare',stops:[stop(6,[],0,8192)],instruction:le((0xd4200000|(0x69<<5))>>>0).slice(0,8)},
 {name:'soft-signal-original-signo',stops:[stop(5,[0x10003,30])]},
 {name:'raw-bad-access',stops:[stop(1,[1])]},
 {name:'non-brk-breakpoint',stops:[stop(6)]},
 {name:'resource-advisory',stops:[stop(11,[4096])]},
 {name:'undeliverable-fault',stops:Array(8).fill(stop(1,[1])),forwardRejected:true},
];
for(const scenario of scenarios){
 const baseline=run(upstream,scenario,'accepted');
 for(const mode of ['accepted','refused','unsupported','throw']){
 const actual=run(composed,scenario,mode);
 assert.strictEqual(actual.commands[0],policy);
 assert.deepStrictEqual(actual.commands.slice(1),baseline.commands,scenario.name+': fallback/BRK commands changed');
 assert.deepStrictEqual(actual.prepares,baseline.prepares);
 const extra=actual.logs.filter(x=>x.startsWith('WineVision JIT:'));
 assert.strictEqual(extra.length,1);assert(extra[0].length<140);
 assert(extra[0].includes(mode==='accepted'?'accepted':'refused'));
 }
 if(scenario.name==='modern-prepare')assert.deepStrictEqual(baseline.prepares,[['8192','4096']]);
 if(scenario.name==='legacy-prepare')assert.deepStrictEqual(baseline.prepares,[['8192','8192']]);
 if(scenario.name==='soft-signal-original-signo')assert(baseline.commands.includes('vCont;C1e:1;c'));
 if(scenario.name==='raw-bad-access')assert(baseline.commands.includes('vCont;C0b:1;c'));
 if(scenario.name==='non-brk-breakpoint')assert(baseline.commands.includes('vCont;C05:1;c'));
 if(scenario.name==='resource-advisory')assert(!baseline.commands.some(x=>x.startsWith('vCont;C')));
 if(scenario.name==='undeliverable-fault')assert(baseline.commands.includes('k'));
}
console.log(JSON.stringify({passed:true,scenarios:scenarios.length,modes:4,upstreamUnmodified:true}));
''')
results = []
for policy in ['conservative', 'software']:
    if policy == 'software':
        subprocess.run([str(build / 'compose'), str(upstream), str(composed), 'software'], check=True)
        assert composed.read_bytes().endswith(upstream.read_bytes())
    result = subprocess.run([node, str(harness), str(upstream), str(composed), policy], check=True, capture_output=True, text=True)
    results.append(json.loads(result.stdout))
receipt = dict(results[0], policyChoices=2, policyResults=results)
signal_main = build / 'signal-probe.c'
signal_main.write_text(SIGNAL_PROBE)
subprocess.run(['clang', str(probe_source), str(signal_main), '-o', str(build / 'signal-probe')], check=True)
signal_result = subprocess.run([str(build / 'signal-probe')], check=True, capture_output=True, text=True)
main.write_text(TASK_PORT_PROBE)
subprocess.run(['swiftc', str(source), str(main), str(build / 'probe.o'), '-o', str(build / 'task-port-probe')], check=True)
port_result = subprocess.run([str(build / 'task-port-probe')], check=True, capture_output=True, text=True)
held_main = build / 'held-signal-probe.c'
held_main.write_text(HELD_SIGNAL_PROBE)
subprocess.run(['clang', '-Dpthread_kill=wvr_held_pthread_kill', '-c', str(probe_source), '-o', str(build / 'held-probe.o')], check=True)
subprocess.run(['clang', str(held_main), str(build / 'held-probe.o'), '-o', str(build / 'held-signal-probe')], check=True)
held_result = subprocess.run([str(build / 'held-signal-probe')], check=True, capture_output=True, text=True)
receipt.update({'heldSignalFailure': held_result.stdout.strip()})
receipt.update({'actualDarwinSignalProbe': signal_result.stdout.strip(), 'actualDarwinExceptionPorts': port_result.stdout.strip()})
assert before_hashes == source_hashes(), 'Production/test sources changed during execution'
receipt.update({'sourceHashes': before_hashes, 'sourcesUnchanged': True, 'coordinatorUsesProductionComposer': True})
receipt.update({'upstreamSha256': hashlib.sha256(upstream.read_bytes()).hexdigest(), 'composerSha256': hashlib.sha256(source.read_bytes()).hexdigest()})
(build / 'result.json').write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps(receipt, indent=2))
