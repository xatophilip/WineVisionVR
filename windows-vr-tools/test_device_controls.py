#!/usr/bin/env python3
"""Run installed WineVision direct32/mixed32 diagnostic gates; never install an app.

Use only after the owner selects a signed package and its successful install
receipt. JIT stays on the app's existing StikDebug path. Raw evidence stays local.
"""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import struct
import subprocess
import time
from urllib.parse import unquote, urlparse
import uuid

BUNDLE = 'com.philipanderson.WineVisionVR'
PHASES = [('direct', 'DirectChildControl', 'direct-child-result.json'),
          ('mixed', 'MixedArchitectureChild', 'mixed-child-result.json')]
FINAL = dict(fixture='mixed-architecture-child-v1', pointerBits=32, callbacks=1,
             firstStatus=0, secondStatus=0, vehCalls=1, contextFlags=65599,
             contextI386=1, contextStackValid=1, exceptionValid=1, continuedAfterRaise=1, exitCode=0)
PARENT_PASS = ('PASS: x64 parent -> i386 child, RtlRunOnce callback once, VEH once, '
               'i386 context/stack, resumed after RaiseException, fresh markers, child exit 0')
LAUNCHER_ARCHIVES = tuple(f'launcher.previous-{n}.txt' for n in (3, 2, 1))
MAX_LAUNCHER_BYTES = 8 * 1024 * 1024
COPY_ATTEMPTS = 3
COPY_RETRY_LIMIT = 4
COPY_SOCKET_REASON = ('The file service client failed to read data from the network socket '
                      'because the socket was closed unexpectedly.')
BEFORE = dict(fixture='mixed-architecture-child-v1', stage='beforeRaiseException',
              pointerBits=32, callbacks=1, exceptionCode=0xe0425648)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


class ControlError(Exception):
    pass


class BoundaryError(ControlError):
    """Stop all further remote work after a transport/tool failure."""


@dataclass
class Result:
    document: dict
    code: int = 0
    timed_out: bool = False
    stderr: str = ''

    @property
    def success(self):
        info = self.document.get('info') if isinstance(self.document, dict) else None
        return self.code == 0 and not self.timed_out and isinstance(info, dict) and info.get('outcome') == 'success'

    @property
    def timeout(self):
        info = self.document.get('info') if isinstance(self.document, dict) else None
        outcome = info.get('outcome') if isinstance(info, dict) else None
        error = self.document.get('error') if isinstance(self.document, dict) else None
        error = error if isinstance(error, dict) else {}
        cli_timeout = (self.code == 2 and outcome in ('failed', 'failure') and
                       error.get('domain') == 'ArgumentParserInternal.ExitCode' and error.get('code') == 2 and
                       re.search(r'^ERROR: Command timeout of [0-9]+(?:\.[0-9]+)? seconds exceeded\. '
                                 r'Assuming command got stuck and aborting\.\r?$', self.stderr, re.MULTILINE))
        return bool(self.timed_out or outcome == 'timeout' or cli_timeout)


def transient_copy(result):
    # Observed CoreDevice copy-from failure only; no recursive/domain-only match.
    try:
        info, error = result.document['info'], result.document['error']
        underlying = error['userInfo']['NSUnderlyingError']['error']
        return (not result.timed_out and type(result.code) is int and result.code != 0 and
                info['outcome'] == 'failed' and info['commandType'] == 'devicectl.device.copy.from' and
                error['domain'] == 'com.apple.dt.CoreDeviceError' and type(error['code']) is int and error['code'] == 7000 and
                underlying['domain'] == 'NSPOSIXErrorDomain' and type(underlying['code']) is int and underlying['code'] == 60 and
                underlying['userInfo']['NSLocalizedFailureReason']['string'] == COPY_SOCKET_REASON)
    except (KeyError, TypeError):
        return False


def missing_file(document):
    if isinstance(document, dict):
        if ((document.get('domain') == 'NSPOSIXErrorDomain' and document.get('code') == 2) or
            (document.get('domain') == 'NSCocoaErrorDomain' and document.get('code') in (4, 260))):
            return True
        return any(missing_file(v) for v in document.values())
    return isinstance(document, list) and any(missing_file(v) for v in document)


class Devicectl:
    def __init__(self, output):
        self.output, self.sequence = Path(output), 0
        self.env = dict(os.environ, TMPDIR=str(self.output / 'tmp'))
        # Host environment must not accidentally become an app launch profile.
        self.env = {k: v for k, v in self.env.items() if not k.startswith('DEVICECTL_CHILD_')}

    def call(self, arguments, tag, timeout, trailing=()):
        # devicectl accepts integer seconds, whereas phase budgets are fractional.
        # Never round up or add host grace beyond the caller's remaining budget.
        if not math.isfinite(timeout) or timeout < 1:
            raise ControlError('Less than one second remains for devicectl')
        deadline = time.monotonic() + timeout
        self.sequence += 1
        stem = self.output / 'raw' / f'{self.sequence:04d}-{tag}'
        target = stem.with_suffix('.json')
        command = ['xcrun', 'devicectl', *arguments, '--timeout', str(math.floor(timeout)),
                   '--json-output', str(target), *trailing]
        started = time.time()
        timed_out, code, host_error = False, None, None
        with stem.with_suffix('.stdout').open('wb') as out, stem.with_suffix('.stderr').open('wb') as err:
            try:
                remaining = deadline - time.monotonic()
                if remaining < 1:
                    raise ControlError('Less than one second remains for devicectl')
                code = subprocess.run(command, env=self.env, stdout=out, stderr=err,
                                      timeout=remaining, check=False).returncode
            except subprocess.TimeoutExpired:
                # Only the host command is stopped; never blindly repeat launch.
                timed_out, code = True, -1
            except OSError as error:
                code, host_error = -1, str(error)
        try:
            document = json.loads(target.read_text())
        except (OSError, ValueError):
            document = {}
        if host_error:
            document = dict(info=dict(outcome='failure'), error=dict(domain='HostOSError', description=host_error))
            save(target, document)
        save(stem.with_suffix('.command.json'), dict(command=command, startedUTC=started,
             returnCode=code, timedOut=timed_out))
        return Result(document, code, timed_out, stem.with_suffix('.stderr').read_text(errors='replace'))


def macho_uuid(path):
    data = Path(path).read_bytes()
    if len(data) < 32 or struct.unpack_from('<II', data)[0:2] != (0xfeedfacf, 0x100000c):
        raise ControlError(f'Expected thin arm64 Mach-O: {path}')
    offset, found = 32, []
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, offset)
        if size < 8 or offset + size > len(data):
            raise ControlError('Invalid Mach-O load command')
        if command == 0x1b and size == 24:
            found.append(str(uuid.UUID(bytes=data[offset+8:offset+24])).upper())
        offset += size
    if len(found) != 1:
        raise ControlError(f'Expected one LC_UUID: {path}')
    return found[0]


def machine(path):
    data = Path(path).read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[:2] != b'MZ' or data[pe:pe+4] != b'PE\0\0':
        raise ControlError('Invalid fixture PE')
    return struct.unpack_from('<H', data, pe+4)[0]


def verify_local_signature(app, tmpdir=None):
    command = ['/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2', str(app)]
    env = dict(os.environ)
    if tmpdir is not None:
        env['TMPDIR'] = str(tmpdir)
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ControlError('Local signature verification did not complete: '+str(error)) from error
    if result.returncode:
        raise ControlError('Local deep codesign verification failed; refusing device actions')
    return dict(command=command, returnCode=0, stdout=result.stdout, stderr=result.stderr)


def package_identity(verified_path, install_path, device, tmpdir=None):
    verified, install = json.loads(Path(verified_path).read_text()), json.loads(Path(install_path).read_text())
    app = Path(verified['app']).resolve()
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    if (verified.get('signatureVerified') is not True or verified.get('passed') is False or
        verified.get('bundleID') != BUNDLE or info.get('CFBundleIdentifier') != BUNDLE or
        info.get('CFBundleExecutable') != 'WineVisionVR' or info.get('WVRDiagnostics') is not True):
        raise ControlError('Requires the verified diagnostic WineVision package')
    local_signature = verify_local_signature(app, tmpdir)
    executable = app / 'WineVisionVR'
    if sha(executable) != verified.get('executableSha256'):
        raise ControlError('Verified executable SHA does not match local package')
    if install.get('info', {}).get('outcome') != 'success' or install.get('result', {}).get('deviceIdentifier') != device:
        raise ControlError('Requires a successful installation receipt for this exact device')
    installed = [a for a in install['result'].get('installedApplications', []) if a.get('bundleID') == BUNDLE]
    if len(installed) != 1:
        raise ControlError('Installation receipt does not identify exactly one WineVision app')
    url = urlparse(installed[0]['installationURL'])
    remote = unquote(url.path).rstrip('/')
    if url.scheme != 'file' or url.netloc or PurePosixPath(remote).name != 'WineVisionVR.app':
        raise ControlError('Unexpected installed app URL')
    plugin = app / 'Frameworks/WindowsRuntimePlugin.framework/WindowsRuntimePlugin'
    ledger = {}
    for p in sorted(app.rglob('*')):
        if p.is_symlink():
            if not p.resolve().is_relative_to(app):
                raise ControlError('External symlink in selected package')
            ledger[p.relative_to(app).as_posix()] = {'link': os.readlink(p), 'sha256': sha(p) if p.is_file() else None}
        elif p.is_file():
            ledger[p.relative_to(app).as_posix()] = {'sha256': sha(p), 'bytes': p.stat().st_size}
    audit = verified.get('appFilesLedger')
    if audit:
        audit_path = Path(audit['path'])
        if sha(audit_path) != audit['sha256']:
            raise ControlError('Complete app audit ledger SHA mismatch')
        expected_files = json.loads(audit_path.read_text())
        actual_files = {name: row['sha256'] for name, row in ledger.items() if row.get('sha256')}
        if expected_files != actual_files:
            raise ControlError('Local package resources differ from complete audit ledger')
    for name, digest in verified.get('ownedPEsSha256', {}).items():
        if not (app/name).resolve().is_relative_to(app) or sha(app/name) != digest:
            raise ControlError('Audited owned PE hash mismatch')
    fixture_hashes = {}
    for variant in ('direct', 'mixed'):
        for name in (['child32.exe'] if variant == 'direct' else ['parent64.exe', 'child32.exe']):
            path = app / 'MixedArchitectureChild' / variant / name
            if machine(path) != (0x14c if name == 'child32.exe' else 0x8664):
                raise ControlError('Incorrect packaged fixture architecture')
            fixture_hashes[variant + '/' + name] = sha(path)
    if fixture_hashes['direct/child32.exe'] != fixture_hashes['mixed/child32.exe']:
        raise ControlError('Direct and mixed child controls must be byte-identical')
    return dict(app=str(app), bundleID=BUNDLE, installedBundle=remote,
                remoteExecutable=remote + '/WineVisionVR', appUUID=macho_uuid(executable),
                executableSha256=sha(executable), pluginUUID=macho_uuid(plugin), pluginSha256=sha(plugin),
                appTreeSha256=hashlib.sha256(json.dumps(ledger, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                appFiles=ledger, fixtureSha256=fixture_hashes,
                localSignatureVerification=local_signature, completeAuditLedgerVerified=bool(audit),
                verifiedReceiptSha256=sha(verified_path), installationReceiptSha256=sha(install_path))


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def metadata(document, subdirectory):
    result = {}
    for row in document.get('result', {}).get('files', []):
        name = row.get('name')
        if row.get('relativePath') not in (name, subdirectory + '/' + str(name)):
            continue
        result[name] = row
    return result


def fresh(row, prior, started, now, skew):
    if not row or row.get('resources', {}).get('isSymbolicLink') is not False or row.get('resources', {}).get('isDirectory') is not False:
        return False
    modified = timestamp(row['metadata']['lastModDate'])
    return (started - skew <= modified <= now + skew and
            (prior is None or modified > timestamp(prior['metadata']['lastModDate'])))


def exact_marker(path, expected):
    got = json.loads(Path(path).read_text())
    return got == expected and all(type(got[k]) is type(v) for k, v in expected.items())


class Controls:
    def __init__(self, config, boundary=None, clock=time):
        self.c, self.clock = config, clock
        self.output = Path(config.output)
        self.boundary = boundary or Devicectl(self.output)
        self.identity = package_identity(config.verified_app, config.install_receipt, config.device, self.output/'tmp')
        self.owned_pid, self.transport_failed = None, False
        self.copy_retries = 0
        self.report = dict(scope='Installed owned diagnostic controls only; no game/interactive-controller claims',
                           package=self.identity, phases=[], passed=False)

    def call(self, args, tag, deadline, trailing=(), missing=False, launch=False, copy_read=False):
        remaining = deadline - self.clock.monotonic()
        if remaining < 1:
            raise ControlError('Less than one second remains before phase deadline')
        result = self.boundary.call(['device', *args, '--device', self.c.device], tag,
                                   min(self.c.command_timeout, remaining), trailing)
        if (result.success or (missing and missing_file(result.document)) or (launch and result.timeout) or
            (copy_read and args[:2] == ['copy', 'from'] and transient_copy(result))):
            return result
        self.transport_failed = True
        raise BoundaryError(f'devicectl failed at {tag}; raw result preserved')

    def processes(self, deadline, tag):
        doc = self.call(['info', 'processes'], tag, deadline).document
        return {p['processIdentifier'] for p in doc.get('result', {}).get('runningProcesses', [])
                if unquote(urlparse(p.get('executable', '')).path) == self.identity['remoteExecutable']}

    def listing(self, subdir, deadline, tag):
        result = self.call(['info', 'files', '--domain-type', 'appDataContainer', '--domain-identifier', BUNDLE,
                            '--subdirectory', subdir, '--no-recurse'], tag, deadline, missing=True)
        return metadata(result.document, subdir) if result.success else {}

    def copy(self, remote, destination, deadline, tag, optional=False):
        destination = Path(destination)
        for attempt in range(1, COPY_ATTEMPTS + 1):
            # Publish only a successful attempt. A truncated transfer, including
            # a plausible complete marker followed by a socket error, is never proof.
            staging = destination.with_name('.'+destination.name+'.copy-'+uuid.uuid4().hex+'.partial')
            try:
                result = self.call(['copy', 'from', '--domain-type', 'appDataContainer', '--domain-identifier', BUNDLE,
                                    '--source', remote, '--destination', str(staging)],
                                   tag if attempt == 1 else tag+'-retry-'+str(attempt), deadline,
                                   missing=optional, copy_read=True)
                if not transient_copy(result):
                    if attempt > 1:
                        self.transport_failed = False
                    if result.success:
                        if staging.is_symlink() or not staging.is_file():
                            raise ControlError('Copy did not produce a regular owned staging file')
                        staging.replace(destination)
                    return result.success
                self.transport_failed = True
            finally:
                staging.unlink(missing_ok=True)
            delay = attempt  # One then two seconds; never extend the phase.
            if (attempt == COPY_ATTEMPTS or self.copy_retries >= COPY_RETRY_LIMIT or
                deadline - self.clock.monotonic() < delay + 1):
                raise BoundaryError(f'devicectl copy retry budget exhausted at {tag}; raw results preserved')
            self.copy_retries += 1
            self.report.setdefault('copyRetries', []).append(dict(source=remote, tag=tag,
                        nextAttempt=attempt+1, backoffSeconds=delay, totalRetries=self.copy_retries))
            self.clock.sleep(delay)

    def wait_unlocked(self, deadline, label):
        while True:
            result = self.call(['info', 'lockState'], label + '-lock', deadline).document.get('result', {})
            if result.get('passcodeRequired') is False and result.get('unlockedSinceBoot') is True:
                return
            if type(result.get('passcodeRequired')) is not bool or type(result.get('unlockedSinceBoot')) is not bool:
                raise ControlError('Unknown lock-state schema; refusing launch')
            print('Waiting for the headset to report unlocked...', flush=True)
            self.clock.sleep(min(self.c.poll_interval, max(0, deadline-self.clock.monotonic())))

    def logs(self, directory, deadline):
        result = {}
        for key, remote in [('launcher', 'Documents/launcher-log.txt'), ('runtime', 'Documents/madeira-log.txt')]:
            path = directory / (key + '.txt')
            if self.copy(remote, path, deadline, key + '-copy', optional=True):
                result[key] = path.read_text(errors='replace')
        return result

    def archived_launcher(self, logs, directory, deadline, prior, started):
        # LaunchLog.swift rotates three slots, oldest first. Never consume an
        # old slot merely because its contents contain a plausible JIT message.
        before = self.listing('Documents', deadline, 'launcher-archive-before')
        names = [n for n in (*LAUNCHER_ARCHIVES, 'launcher-log.txt')
                 if fresh(before.get(n), prior.get(n), started, self.clock.time(), self.c.clock_skew)]
        if 'launcher-log.txt' not in names or not any(n in names for n in LAUNCHER_ARCHIVES):
            return logs
        chunks = []
        for name in names:
            size = before[name]['metadata']['size']
            if type(size) is not int or not 0 < size <= MAX_LAUNCHER_BYTES:
                return logs
            path = directory / name
            if not self.copy('Documents/'+name, path, deadline, 'launcher-archive-copy', optional=True):
                return logs
            if path.stat().st_size != size:
                return logs
            chunks.append(path.read_text(errors='replace'))
        after = self.listing('Documents', deadline, 'launcher-archive-after')
        if any(after.get(n) != before[n] for n in names):
            return logs
        save(directory/'launcher-archive-metadata.json', {n: before[n] for n in names})
        return dict(logs, launcher='\n'.join(chunks), launcherArchives={n: before[n] for n in names})

    def proof(self, logs, pid, variant):
        runtime, launcher = logs.get('runtime', ''), logs.get('launcher', '')
        identities = list(re.finditer(r'ml989: running image (.+?) base=0x[0-9a-fA-F]+ pid=(\d+) LC_UUID=([0-9A-Fa-f-]+)', runtime))
        expected = self.identity['installedBundle'] + '/Frameworks/WindowsRuntimePlugin.framework/WindowsRuntimePlugin'
        own = [r for r in identities if int(r.group(2)) == pid]
        if not own:
            return None
        if any(r.group(1) != expected or r.group(3).upper() != self.identity['pluginUUID'] for r in own):
            raise ControlError('Runtime PID/bundle/plugin UUID does not match selected installed package')
        matches = list(re.finditer(r'JIT: handed the script to (?:stikdebug|stikjit) for pid '+str(pid)+r';', launcher))
        if not matches:
            return None
        tail = launcher[matches[-1].end():]
        # Unlabelled attach/accept lines belong only to this handoff, never a
        # subsequent launch reconstructed from another rotated file.
        tail = re.split(r'JIT: handed the script to (?:stikdebug|stikjit) for pid ', tail, maxsplit=1)[0]
        attached, accepted = tail.find('JIT: debugger attached after '), tail.find('Launch: runtime accepted the launch')
        if attached < 0 or accepted < attached:
            return None
        runtime = runtime[own[-1].end():]
        exits = re.findall(r'\[WineProc\] Wine exited with code (-?\d+)', runtime)
        if exits and any(int(v) != 0 for v in exits):
            raise ControlError('Current Wine runtime exited nonzero')
        if '[redeliv] terminating process' in runtime or re.search(r'\[thread-trace\] (?:exit|abort)\([1-9]', tail):
            raise ControlError('Current runtime reports fatal termination')
        parent_verified = ('CHILD_EXIT code=0 beforeStage=1' in runtime.splitlines() and
                           PARENT_PASS in runtime.splitlines())
        if variant == 'mixed' and not parent_verified:
            return None
        return dict(nativePID=pid, runtimePluginUUID=self.identity['pluginUUID'], wineExitCode=0,
                    launcherProofFiles=list(logs.get('launcherArchives', {'launcher-log.txt': None})),
                    parentWaitAndExitVerified=parent_verified if variant == 'mixed' else None) if exits else None

    def phase(self, variant, folder, marker):
        directory = self.output / variant
        directory.mkdir()
        deadline = self.clock.monotonic() + self.c.phase_timeout
        self.wait_unlocked(deadline, variant)
        subdir = 'Documents/WindowsVR/Apps/' + folder
        prior = self.listing(subdir, deadline, variant + '-prior')
        prior_logs = self.listing('Documents', deadline, variant + '-prior-logs')
        previous_pids = self.processes(deadline, variant + '-prior-processes')
        row = dict(phase=variant, passed=False, priorMarkers={n: prior.get(n) for n in (marker, marker+'.before-seh.json')})
        self.report['phases'].append(row)
        started = self.clock.time()
        row['startedUTC'] = datetime.fromtimestamp(started, timezone.utc).isoformat()
        arguments = ['--mixed-architecture-child-test'] + (['--direct-child-control'] if variant == 'direct' else [])
        launch = self.call(['process', 'launch', '--terminate-existing', '--activate'], variant+'-launch', deadline,
                           trailing=[BUNDLE, *arguments], launch=True)
        process = launch.document.get('result', {}).get('process', {})
        pid = process.get('processIdentifier')
        if pid is not None and unquote(urlparse(process.get('executable', '')).path) != self.identity['remoteExecutable']:
            raise ControlError('Launch returned a different executable')
        if pid is None and launch.timeout:
            # A timeout can follow a successful start. Recover one new exact
            # executable PID, preserving the failed launch result, never retry.
            candidates = self.processes(deadline, variant+'-timeout-processes') - previous_pids
            if len(candidates) == 1:
                pid = candidates.pop()
        if type(pid) is not int or pid <= 0 or pid in previous_pids:
            raise ControlError('No unambiguous fresh launch PID; launch was not repeated')
        self.owned_pid = pid
        row.update(nativePID=pid, launchCommandTimedOut=launch.timeout)
        attempt = 0
        while self.clock.monotonic() < deadline:
            attempt += 1
            capture = directory / f'capture-{attempt:03d}'
            capture.mkdir()
            current = self.listing(subdir, deadline, variant+'-files')
            logs = self.logs(capture, deadline)
            proof = self.proof(logs, pid, variant)
            if not proof and f'pid={pid} LC_UUID=' in logs.get('runtime', ''):
                logs = self.archived_launcher(logs, capture, deadline, prior_logs, started)
                proof = self.proof(logs, pid, variant)
            names = (marker+'.before-seh.json', marker)
            if proof and all(fresh(current.get(n), prior.get(n), started, self.clock.time(), self.c.clock_skew) for n in names):
                for n in (*names, 'child32.exe', *(['parent64.exe'] if variant == 'mixed' else [])):
                    self.copy(subdir+'/'+n, capture/n, deadline, variant+'-fixture-copy')
                after = self.listing(subdir, deadline, variant+'-files-after-copy')
                stable = all(after.get(n) == current.get(n) and (capture/n).stat().st_size == current[n]['metadata']['size'] for n in names)
                documents = self.listing('Documents', deadline, variant+'-logs-metadata')
                logs_fresh = all(fresh(documents.get(n), prior_logs.get(n), started, self.clock.time(), self.c.clock_skew)
                                 for n in ('launcher-log.txt', 'madeira-log.txt'))
                archives_stable = all(documents.get(n) == metadata for n, metadata in logs.get('launcherArchives', {}).items())
                if stable and logs_fresh and archives_stable:
                    if not exact_marker(capture/names[0], BEFORE) or not exact_marker(capture/names[1], FINAL):
                        raise ControlError('Fresh fixture marker reports invalid/incomplete SEH result')
                    for n in ('child32.exe', *(['parent64.exe'] if variant == 'mixed' else [])):
                        if sha(capture/n) != self.identity['fixtureSha256'][variant+'/'+n]:
                            raise ControlError('Remote fixture differs from signed packaged PE')
                    row.update(passed=True, proof=proof, markers={n: after[n] for n in names},
                               capture=str(capture), evidenceSha256={p.name: sha(p) for p in capture.iterdir() if p.is_file()})
                    print(f'{variant}: PASS (PID {pid}, fresh SEH markers, Wine exit 0)', flush=True)
                    return
            self.clock.sleep(min(self.c.poll_interval, max(0, deadline-self.clock.monotonic())))
        raise ControlError(f'{variant}: bounded wait ended without fresh complete proof')

    def run(self):
        try:
            initial = self.clock.monotonic() + self.c.unlock_timeout
            self.wait_unlocked(initial, 'initial')
            apps = self.call(['info', 'apps', '--bundle-id', BUNDLE], 'installed-app',
                             self.clock.monotonic()+self.c.command_timeout*2).document
            rows = apps.get('result', {}).get('apps', [])
            if len(rows) != 1 or rows[0].get('bundleIdentifier') != BUNDLE or unquote(urlparse(rows[0].get('url', '')).path).rstrip('/') != self.identity['installedBundle']:
                raise ControlError('Installed app does not match selected install receipt')
            for phase in PHASES:
                self.phase(*phase)
            self.report['passed'] = True
        except (ControlError, KeyError, ValueError, OSError, struct.error) as error:
            self.report['error'] = str(error)
            print('STOP: '+str(error), flush=True)
        finally:
            # Only stop the exact PID/executable we launched. Never kill by
            # process name, touch StikDebug, or send more commands after failure
            # of the transport. Evidence is already copied before termination.
            if self.owned_pid and not self.transport_failed and not self.c.keep_app_open:
                try:
                    deadline = self.clock.monotonic() + self.c.command_timeout*2
                    if self.owned_pid in self.processes(deadline, 'cleanup-processes'):
                        self.call(['process', 'terminate', '--pid', str(self.owned_pid)], 'cleanup-owned-app', deadline)
                except ControlError as error:
                    self.report['cleanupError'] = str(error)
                    self.report['passed'] = False
            save(self.output/'result.json', self.report)
        return self.report['passed']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device', required=True)
    p.add_argument('--verified-app', required=True, type=Path)
    p.add_argument('--install-receipt', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path, help='New external output directory; TMPDIR is created inside')
    p.add_argument('--unlock-timeout', type=float, default=180)
    p.add_argument('--phase-timeout', type=float, default=120)
    p.add_argument('--command-timeout', type=float, default=10)
    p.add_argument('--poll-interval', type=float, default=2)
    p.add_argument('--clock-skew', type=float, default=2, help='Maximum host/device wall-clock skew in seconds')
    p.add_argument('--keep-app-open', action='store_true')
    c = p.parse_args()
    if any(not 0 < v <= 600 for v in (c.unlock_timeout, c.phase_timeout, c.command_timeout, c.poll_interval)) or not 0 <= c.clock_skew <= 5:
        p.error('Deadlines/poll must be positive and bounded; clock skew must be0–5s')
    if not c.output.is_absolute() or c.output.exists() or not str(c.output.resolve()).startswith('/Volumes/'):
        p.error('--output must be a new absolute directory on an external /Volumes volume')
    c.output.mkdir(parents=True)
    for name in ('tmp', 'raw'):
        (c.output/name).mkdir()
    try:
        runner = Controls(c)
        return 0 if runner.run() else 1
    except (ControlError, KeyError, ValueError, OSError, struct.error) as error:
        save(c.output/'result.json', dict(passed=False, error=str(error), deviceActionsStarted=False))
        print('STOP: '+str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
