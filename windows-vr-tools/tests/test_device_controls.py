#!/usr/bin/env python3
"""Exercise the production host orchestrator against a deterministic fake device.
No debugger, headset, Wine, credentials, or real app is accessed.
Optional --cli-help checks only the installed devicectl argument parser.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
import subprocess
from pathlib import Path
import plistlib
import struct
import sys
import tempfile
from types import SimpleNamespace
import uuid

spec = importlib.util.spec_from_file_location('device_controls', Path(__file__).resolve().parents[1]/'test_device_controls.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
DEVICE = '00000000-0000-0000-0000-000000000001'
REMOTE = '/private/var/containers/Bundle/Application/OWNED/WineVisionVR.app'
APP_UUID = '11111111-1111-1111-1111-111111111111'
PLUGIN_UUID = '22222222-2222-2222-2222-222222222222'


class Clock:
    def __init__(self): self.tick = 0
    def monotonic(self): return self.tick
    def time(self): return 1792328400 + self.tick
    def sleep(self, seconds): self.tick += seconds


def macho(identity):
    return struct.pack('<IIIIIIIIII', 0xfeedfacf, 0x100000c, 0, 2, 1, 24, 0, 0, 0x1b, 24) + uuid.UUID(identity).bytes


def pe(machine):
    data = bytearray(128)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 64)
    data[64:68] = b'PE\0\0'
    struct.pack_into('<H', data, 68, machine)
    return data


def setup(directory):
    app = directory/'WineVisionVR.app'
    (app/'Frameworks/WindowsRuntimePlugin.framework').mkdir(parents=True)
    (app/'Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier=m.BUNDLE, CFBundleExecutable='WineVisionVR', WVRDiagnostics=True)))
    (app/'WineVisionVR').write_bytes(macho(APP_UUID))
    (app/'resource.bin').write_bytes(b'owned-resource')
    (app/'Frameworks/WindowsRuntimePlugin.framework/WindowsRuntimePlugin').write_bytes(macho(PLUGIN_UUID))
    for variant in ('direct', 'mixed'):
        path = app/'MixedArchitectureChild'/variant
        path.mkdir(parents=True)
        (path/'child32.exe').write_bytes(pe(0x14c))
        if variant == 'mixed': (path/'parent64.exe').write_bytes(pe(0x8664))
    verified, install = directory/'verified.json', directory/'install.json'
    ledger=directory/'audit-files.json'
    m.save(ledger,{p.relative_to(app).as_posix():m.sha(p) for p in app.rglob('*') if p.is_file()})
    m.save(verified, dict(app=str(app), bundleID=m.BUNDLE, signatureVerified=True, executableSha256=m.sha(app/'WineVisionVR'), appFilesLedger=dict(path=str(ledger),sha256=m.sha(ledger))))
    m.save(install, dict(info=dict(outcome='success'), result=dict(deviceIdentifier=DEVICE, installedApplications=[dict(bundleID=m.BUNDLE, installationURL='file://'+REMOTE+'/')])))
    return app, verified, install


class FakeDevice:
    def __init__(self, clock, output, app, mode):
        self.clock, self.output, self.app, self.mode = clock, output, app, mode
        self.calls, self.launches, self.variant = [], [], None
        self.pid, self.launched, self.lock_calls = 90, None, 0
        self.disconnected = False

    def row(self, name, data, old=False):
        modified = self.clock.time()-100 if old else self.launched
        return dict(name=name, relativePath=name,
                    metadata=dict(lastModDate=datetime.fromtimestamp(modified, timezone.utc).isoformat(), size=len(data)),
                    resources=dict(isSymbolicLink=False, isDirectory=False, isReadable=True))

    def marker_data(self, name):
        value = m.BEFORE if name.endswith('.before-seh.json') else m.FINAL
        if self.mode == 'bad-marker' and not name.endswith('.before-seh.json'):
            value = dict(value, continuedAfterRaise=0)
        return (json.dumps(value)+'\n').encode()

    def ready(self):
        return self.launched is not None and self.clock.time()-self.launched >= 3

    def log(self, name):
        if self.variant is None: return b'prior session\n'
        if name in ('launcher-log.txt', *m.LAUNCHER_ARCHIVES):
            handoff=f'12:00:00 [notice] JIT: handed the script to stikdebug for pid {self.pid}; waiting for a debugger\n'
            attached='12:00:01 [notice] JIT: debugger attached after 1 seconds\n'
            accepted='12:00:01 [notice] Launch: runtime accepted the launch\n'
            if self.mode in ('rotation','stale-archive','rotation-other-pid','archive-changed'):
                if name=='launcher-log.txt':return accepted.encode()
                if name=='launcher.previous-1.txt':
                    extra=('12:00:00 [notice] JIT: handed the script to stikdebug for pid 777; waiting for a debugger\n'
                           if self.mode=='rotation-other-pid' else '')
                    return (('prior game log\n'*150000)+handoff+extra+attached).encode()
                return b'old unrelated archive\n'
            return (f'12:00:00 [notice] JIT: handed the script to stikdebug for pid {self.pid}; waiting for a debugger\n'
                    '12:00:01 [notice] JIT: debugger attached after 1 seconds\n'
                    '12:00:01 [notice] Launch: runtime accepted the launch\n').encode()
        identity = '33333333-3333-3333-3333-333333333333' if self.mode == 'wrong-uuid' else PLUGIN_UUID
        text = f'ml989: running image {REMOTE}/Frameworks/WindowsRuntimePlugin.framework/WindowsRuntimePlugin base=0x100 pid={self.pid} LC_UUID={identity}\n'
        if self.mode == 'stale-exit':
            text = '[WineProc] Wine exited with code 0 (caught by longjmp)\n' + text
        elif self.ready():
            if self.variant=='mixed' and self.mode!='child-only-exit':
                text += 'CHILD_EXIT code=0 beforeStage=1\n'+m.PARENT_PASS+'\n'
            text += '[WineProc] Wine exited with code 0 (caught by longjmp)\n'
        return text.encode()

    def call(self, arguments, tag, timeout, trailing=()):
        assert not self.disconnected, 'No further device calls after disconnection'
        assert timeout > 0
        assert arguments[-2:] == ['--device', DEVICE]
        self.calls.append((list(arguments), tuple(trailing)))
        self.clock.tick += .02
        operation = arguments[1:3]
        result = {}
        outcome, code, stderr = 'success', 0, ''
        if operation == ['info', 'lockState']:
            self.lock_calls += 1
            locked = self.mode == 'locked' or (self.mode == 'unlock-later' and self.lock_calls < 3)
            result = dict(passcodeRequired=locked, unlockedSinceBoot=True)
        elif operation == ['info', 'apps']:
            assert '--bundle-id' in arguments and arguments[arguments.index('--bundle-id')+1] == m.BUNDLE
            result = dict(apps=[dict(bundleIdentifier=m.BUNDLE, url='file://'+REMOTE+'/')])
        elif operation == ['info', 'processes']:
            rows = [] if self.pid is None else [dict(processIdentifier=self.pid, executable='file://'+REMOTE+'/WineVisionVR')]
            # An unrelated app must never be chosen or terminated.
            rows.append(dict(processIdentifier=777, executable='file:///other/Other.app/Other'))
            result = dict(runningProcesses=rows)
        elif operation == ['process', 'launch']:
            assert tuple(trailing) in ((m.BUNDLE, '--mixed-architecture-child-test', '--direct-child-control'),
                                (m.BUNDLE, '--mixed-architecture-child-test'))
            assert '--terminate-existing' in arguments and '--activate' in arguments
            self.variant = 'direct' if '--direct-child-control' in trailing else 'mixed'
            self.launches.append(self.variant)
            if self.mode == 'timeout-no-start':
                self.variant = None
                outcome, code = 'timeout', 1
            else:
                self.pid += 1
                self.launched = self.clock.time()
                if self.mode == 'timeout-started': outcome, code = 'timeout', 1
                elif self.mode in ('cli-timeout-started','cli-invalid-arguments'):
                    outcome,code='failed',2
                    stderr=('ERROR: Command timeout of 30.0 seconds exceeded. Assuming command got stuck and aborting.'
                            if self.mode=='cli-timeout-started' else 'ERROR: Invalid argument supplied.')
                else: result = dict(process=dict(processIdentifier=self.pid, executable='file://'+REMOTE+'/WineVisionVR'))
        elif operation == ['process', 'terminate']:
            assert arguments[arguments.index('--pid')+1] == str(self.pid)
            assert self.pid != 777
            self.pid = None
        elif operation == ['info', 'files']:
            assert '--no-recurse' in arguments
            assert arguments[arguments.index('--domain-identifier')+1] == m.BUNDLE
            subdir = arguments[arguments.index('--subdirectory')+1]
            if self.mode == 'disconnect' and self.variant and self.ready():
                self.disconnected = True
                outcome, code = 'failure', 1
            elif subdir == 'Documents':
                names=['launcher-log.txt','madeira-log.txt']
                if self.mode in ('rotation','stale-archive','rotation-other-pid','archive-changed'):names.extend(m.LAUNCHER_ARCHIVES)
                result = dict(files=[self.row(n, self.log(n), old=self.variant is None or self.mode == 'stale-logs' or
                                              n in m.LAUNCHER_ARCHIVES and (n!='launcher.previous-1.txt' or self.mode=='stale-archive'))
                                     for n in names])
                if self.mode=='archive-changed' and tag=='launcher-archive-after':
                    next(r for r in result['files'] if r['name']=='launcher.previous-1.txt')['metadata']['size']+=1
            else:
                variant = 'direct' if subdir.endswith('DirectChildControl') else 'mixed'
                marker = 'direct-child-result.json' if variant == 'direct' else 'mixed-child-result.json'
                # Baseline stale PASS files deliberately remain in the fake.
                # A real selector normally deletes them; acceptance must not rely on it.
                result = dict(files=[self.row(n, self.marker_data(n), old=variant != self.variant or self.mode == 'stale')
                                     for n in (marker, marker+'.before-seh.json')])
        elif operation == ['copy', 'from']:
            assert arguments[arguments.index('--domain-identifier')+1] == m.BUNDLE
            source = arguments[arguments.index('--source')+1]
            destination = Path(arguments[arguments.index('--destination')+1])
            if source in tuple('Documents/'+n for n in ('launcher-log.txt','madeira-log.txt',*m.LAUNCHER_ARCHIVES)):
                data = self.log(Path(source).name)
            elif source.endswith('.exe'):
                data = (self.app/'MixedArchitectureChild'/self.variant/Path(source).name).read_bytes()
                if self.mode == 'wrong-pe': data += b'wrong'
            else: data = self.marker_data(Path(source).name)
            destination.write_bytes(data)
        else: raise AssertionError(arguments)
        document = dict(info=dict(outcome=outcome), result=result)
        if self.disconnected: document['error'] = dict(domain='CoreDeviceDisconnected', code=1)
        if code==2:document['error']=dict(domain='ArgumentParserInternal.ExitCode',code=2)
        m.save(self.output/'raw'/f'{len(self.calls):04d}-{tag}.json', document)
        return m.Result(document, code, False, stderr)


def case(build, mode, expected):
    directory = build/mode
    directory.mkdir()
    app, verified, install = setup(directory)
    output = directory/'output'
    (output/'raw').mkdir(parents=True)
    (output/'tmp').mkdir()
    clock = Clock()
    c = SimpleNamespace(output=output, verified_app=verified, install_receipt=install, device=DEVICE,
                        unlock_timeout=5, phase_timeout=12, command_timeout=2, poll_interval=1,
                        clock_skew=2, keep_app_open=False)
    fake = FakeDevice(clock, output, app, mode)
    if mode=='mutated-resource':
        (app/'resource.bin').write_bytes(b'changed-after-audit')
        try:m.Controls(c,fake,clock)
        except m.ControlError as error:assert 'audit ledger' in str(error)
        else:raise AssertionError('Mutated resources accepted')
        assert not fake.calls
        print('PASS resource audit mismatch refuses all device actions')
        return
    controls = m.Controls(c, fake, clock)
    assert controls.run() is expected, (mode, controls.report)
    report = json.loads((output/'result.json').read_text())
    assert report['passed'] is expected
    if expected:
        assert fake.launches == ['direct', 'mixed']
        assert len(report['phases']) == 2 and all(p['passed'] for p in report['phases'])
        assert all(p['proof']['wineExitCode'] == 0 for p in report['phases'])
        assert fake.pid is None, 'Successful runner closes only its owned app'
    else:
        if mode=='child-only-exit':
            assert fake.launches==['direct','mixed'] and report['phases'][0]['passed'] and not report['phases'][1]['passed']
        else:assert len(fake.launches) <= 1, 'Direct failure must prevent mixed launch'
    if mode in ('timeout-started','cli-timeout-started'):
        assert all(p['launchCommandTimedOut'] for p in report['phases'])
    if mode=='rotation':
        assert all(list((output/p).glob('capture-*/launcher.previous-1.txt')) for p in ('direct','mixed'))
        assert all(p['proof']['launcherProofFiles']==['launcher.previous-1.txt','launcher-log.txt'] for p in report['phases'])
    if mode == 'locked': assert not fake.launches
    if mode == 'disconnect': assert controls.transport_failed and fake.pid is not None
    assert any((output/'raw').iterdir())
    print('PASS fake devicectl:', mode)


def transport_contract(build):
    output=build/'transport'
    (output/'raw').mkdir(parents=True)
    (output/'tmp').mkdir()
    original=m.subprocess.run
    old=os.environ.get('DEVICECTL_CHILD_PRIVATE')
    os.environ['DEVICECTL_CHILD_PRIVATE']='not-forwarded'
    try:
        boundary=m.Devicectl(output)
        def success(command,**kwargs):
            assert command[:2]==['xcrun','devicectl']
            assert command.index('--json-output')<command.index(m.BUNDLE)
            assert command.index('--timeout')<command.index(m.BUNDLE)
            assert command[command.index('--timeout')+1]=='3'
            assert 0 < kwargs['timeout'] <= 3
            assert kwargs['env']['TMPDIR']==str(output/'tmp')
            assert not any(k.startswith('DEVICECTL_CHILD_') for k in kwargs['env'])
            m.save(Path(command[command.index('--json-output')+1]),dict(info=dict(outcome='success'),result={}))
            return SimpleNamespace(returncode=0)
        m.subprocess.run=success
        result=boundary.call(['device','process','launch','--device',DEVICE],'launch',3,[m.BUNDLE,'--mixed-architecture-child-test'])
        assert result.success
        budgets=[]
        def integer_timeout(command,**kwargs):
            token=command[command.index('--timeout')+1]
            assert token.isdecimal() and int(token)>0
            # A real devicectl parser rejects '20.0' before producing JSON.
            assert int(token)==budgets[-1][0]
            assert 0 < kwargs['timeout'] <= budgets[-1][1]
            m.save(Path(command[command.index('--json-output')+1]),dict(info=dict(outcome='success'),result={}))
            return SimpleNamespace(returncode=0)
        m.subprocess.run=integer_timeout
        budgets.append((20,20.0))
        assert boundary.call(['device','info','lockState','--device',DEVICE],'float-config',20.0).success
        # Exercise the actual orchestrator's min(config, fractional phase remainder).
        controls=object.__new__(m.Controls)
        controls.c=SimpleNamespace(device=DEVICE,command_timeout=20.0)
        controls.clock=Clock()
        controls.boundary=boundary
        controls.transport_failed=False
        budgets.append((2,2.9))
        assert controls.call(['info','lockState'],'fractional-remainder',2.9).success
        sequence=boundary.sequence
        for budget in (0.99,0,-1,float('inf'),float('nan')):
            try:boundary.call(['device','info','lockState','--device',DEVICE],'expired',budget)
            except m.ControlError:pass
            else:raise AssertionError('Invalid/subsecond budget issued a device command')
        try:controls.call(['info','lockState'],'expired-phase',0.99)
        except m.ControlError:pass
        else:raise AssertionError('Subsecond phase issued a device command')
        assert boundary.sequence==sequence
        def timeout(command,**kwargs): raise subprocess.TimeoutExpired(command,kwargs['timeout'])
        m.subprocess.run=timeout
        result=boundary.call(['device','info','lockState','--device',DEVICE],'timeout',3)
        assert result.timeout and not result.success
        def cli_timeout(command,**kwargs):
            kwargs['stderr'].write(b'ERROR: Command timeout of 30 seconds exceeded. Assuming command got stuck and aborting.\r\n')
            m.save(Path(command[command.index('--json-output')+1]),dict(info=dict(outcome='failed'),error=dict(domain='ArgumentParserInternal.ExitCode',code=2)))
            return SimpleNamespace(returncode=2)
        m.subprocess.run=cli_timeout
        result=boundary.call(['device','process','launch','--device',DEVICE],'cli-timeout',3,[m.BUNDLE,'--mixed-architecture-child-test'])
        assert result.timeout and not result.success
        def syntax_error(command,**kwargs):
            kwargs['stderr'].write(b'ERROR: Invalid argument supplied.\n')
            m.save(Path(command[command.index('--json-output')+1]),dict(info=dict(outcome='failed'),error=dict(domain='ArgumentParserInternal.ExitCode',code=2)))
            return SimpleNamespace(returncode=2)
        m.subprocess.run=syntax_error
        result=boundary.call(['device','process','launch','--device',DEVICE],'syntax-error',3,[m.BUNDLE])
        assert not result.timeout and not result.success
        def missing(command,**kwargs): raise OSError('test unavailable command')
        m.subprocess.run=missing
        result=boundary.call(['device','info','lockState','--device',DEVICE],'missing',3)
        assert not result.success and result.document['error']['domain']=='HostOSError'
        assert len(list((output/'raw').glob('*.command.json')))==7
    finally:
        m.subprocess.run=original
        if old is None:os.environ.pop('DEVICECTL_CHILD_PRIVATE',None)
        else:os.environ['DEVICECTL_CHILD_PRIVATE']=old
    print('PASS production transport: exact argv, bounded timeout, externalTMPDIR, launch env isolation and raw failure records')


def cli_help_contract(build):
    # --help exits in the argument parser; no device is named or queried.
    for token, expected in (('20',0),('2',0),('20.0',64)):
        command=['xcrun','devicectl','--timeout',token,'--help']
        result=subprocess.run(command,capture_output=True,text=True,timeout=10,check=False)
        m.save(build/('cli-help-'+token+'.json'),dict(command=command,returnCode=result.returncode,
               stdout=result.stdout,stderr=result.stderr))
        assert result.returncode==expected, (command,result.returncode,result.stderr)
        text=result.stdout+result.stderr
        assert '--timeout <seconds>' in text
        if expected:assert "The value '20.0' is invalid" in text
    print('PASS real devicectl --help parser only: integer seconds accepted; float token rejected')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', required=True, type=Path)
    p.add_argument('--cli-help', action='store_true', help='Check real local devicectl --help parsing only; no device calls')
    a = p.parse_args()
    a.build.mkdir(parents=True, exist_ok=True)
    build = Path(tempfile.mkdtemp(prefix='device-controls-contract-', dir=a.build.resolve()))
    if a.cli_help: cli_help_contract(build)
    transport_contract(build)
    m.verify_local_signature=lambda app,tmpdir=None:dict(scope='deterministic fake signing boundary',returnCode=0)
    for mode, expected in [('success', True), ('unlock-later', True), ('rotation',True),
                           ('stale-archive',False),('rotation-other-pid',False),('archive-changed',False),('stale', False),
                           ('stale-logs', False), ('stale-exit', False), ('timeout-started', True),
                           ('cli-timeout-started',True),('cli-invalid-arguments',False),('child-only-exit',False),('mutated-resource',False), ('timeout-no-start', False),
                           ('disconnect', False), ('locked', False), ('wrong-uuid', False),
                           ('wrong-pe', False), ('bad-marker', False)]:
        case(build, mode, expected)
    print('PASS: production orchestrator, fake boundary only; artifacts:', build)


if __name__ == '__main__': main()
