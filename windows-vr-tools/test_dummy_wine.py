#!/usr/bin/env python3
"""Execute owned 64/32-bit fixtures with isolated Wine prefixes and bounded waits.
No installation, user Wine prefix, VR session, or device access is performed.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import tarfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stop_prefix(server, env):
    # WINEPREFIX scopes this server request; never use a global process kill.
    subprocess.run([str(server), '-k'], env=env, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=10, check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wine-build', type=Path, required=True)
    parser.add_argument('--wine-source', type=Path, required=True)
    parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--freetype-lib', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=60)
    parser.add_argument('--prefix-template', type=Path)
    parser.add_argument('--template-sha256')
    args = parser.parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path) and not value.is_absolute():
            parser.error(f'{key} must be absolute')
    wine = args.wine_build / 'loader/wine'
    server = args.wine_build / 'server/wineserver'
    for binary in (wine, server):
        if not binary.is_file():
            parser.error(f'missing {binary}')
    if args.prefix_template and sha(args.prefix_template) != args.template_sha256:
        parser.error('prefix template SHA256 mismatch')
    now = datetime.datetime.now(datetime.timezone.utc)
    run = args.output_root / ('execution-' + now.strftime('%Y%m%dT%H%M%SZ'))
    run.mkdir(parents=True, exist_ok=False)
    tmp = run / 'tmp'
    tmp.mkdir()
    report = {'createdAtUTC': now.isoformat(), 'wine': str(wine),
              'wineSha256': sha(wine), 'freetypeLibrary': str(args.freetype_lib),
              'freetypeSha256': sha(args.freetype_lib), 'tests': {},
              'scope': 'Local Mac Wine GDI and CPU checks only; no visionOS/FEX or OpenVR rendering validation.',
              'prefixTemplate': str(args.prefix_template) if args.prefix_template else None,
              'prefixTemplateSha256': args.template_sha256,
              'freshPrefixInitializationTested': not bool(args.prefix_template),
              'templatePolicy': 'Verified stock registry/directories; update timestamp set to same-source wine.inf mtime to skip optional INF reinstall. No template DLLs or host links.' if args.prefix_template else None}
    try:
        for arch, bits in [('x64', 64), ('x86', 32)]:
            work = run / arch
            work.mkdir()
            prefix = work / 'prefix'
            if args.prefix_template:
                with tarfile.open(args.prefix_template) as archive:
                    for member in archive.getmembers():
                        path = Path(member.name)
                        if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'prefix' or member.issym() or member.islnk():
                            raise ValueError('unsafe prefix template member: ' + member.name)
                        if path.suffix.lower() in ['.dll', '.exe', '.drv', '.sys']:
                            raise ValueError('template contains runtime binary: ' + member.name)
                    archive.extractall(path=work)
                (prefix / '.update-timestamp').write_text(str(int((args.wine_build / 'loader/wine.inf').stat().st_mtime)) + '\n')
                (prefix / 'drive_c/windows/syswow64').mkdir(exist_ok=True)
            fonts = prefix / 'drive_c/windows/Fonts'
            fonts.mkdir(parents=True, exist_ok=True)
            for font in (args.wine_source / 'fonts').glob('*.ttf'):
                shutil.copy2(font, fonts / font.name)
            installed = []
            for machine, systemdir in [('x86_64', 'system32'), ('i386', 'syswow64')]:
                for source in args.wine_build.glob('**/' + machine + '-windows/*'):
                    if not source.is_file() or source.suffix.lower() not in ['.dll', '.exe', '.drv', '.sys', '.cpl', '.ax', '.ocx', '.acm']:
                        continue
                    destination = prefix / 'drive_c/windows' / systemdir
                    if source.suffix.lower() == '.sys':
                        destination = destination / 'drivers'
                    destination.mkdir(parents=True, exist_ok=True)
                    destination = destination / source.name
                    shutil.copy2(source, destination)
                    installed.append({'source': str(source), 'destination': str(destination), 'sha256': sha(destination)})
            desktop = work / 'desktop-demo.exe'
            cpu = work / 'vr-smoke.exe'
            shutil.copy2(args.fixture_root / arch / desktop.name, desktop)
            shutil.copy2(args.fixture_root / ('vr-' + arch) / cpu.name, cpu)
            env = dict(os.environ, TMPDIR=str(tmp), WINEPREFIX=str(prefix),
                       WINEARCH='win64', WINELOADER=str(wine), WINESERVER=str(server), WINEDLLPATH=str(args.wine_build / 'dlls'), WINEDLLOVERRIDES='mscoree,mshtml=d',
                       WINEDEBUG='+timestamp,+pid,+loaddll',
                       DYLD_FALLBACK_LIBRARY_PATH=str(args.freetype_lib.parent))
            entry = {'pointerBitsExpected': bits, 'prefix': str(prefix),
                     'fontCount': len(list(fonts.glob('*.ttf'))), 'installedPEModules': installed,
                     'desktopSha256': sha(desktop), 'cpuSha256': sha(cpu),
                     'prefixUpdateTimestamp': (prefix / '.update-timestamp').read_text() if args.prefix_template else None}
            report['tests'][arch] = entry
            process = None
            try:
                log = work / 'desktop-wine.log'
                command = [str(wine), str(desktop), '--self-test', '--trace-input']
                entry['desktopCommand'] = command
                result = work / 'demo-selftest-result.txt'
                with log.open('wb') as output:
                    process = subprocess.Popen(command, cwd=work, env=env,
                                               stdout=output, stderr=subprocess.STDOUT)
                    start = time.monotonic()
                    while time.monotonic() - start < args.timeout:
                        if (result.exists() and result.read_bytes().endswith(b'\n')) or process.poll() is not None:
                            break
                        time.sleep(0.2)
                    entry['desktopElapsedSeconds'] = round(time.monotonic() - start, 2)
                    entry['desktopExitBeforeCleanup'] = process.poll()
                    entry['desktopTimedOut'] = not result.exists() and process.poll() is None
                    entry['desktopResult'] = result.read_text() if result.exists() else None
                    expected = f'PASS GDI desktop self-test pointerBits={bits} '
                    entry['desktopPassed'] = bool(entry['desktopResult'] and entry['desktopResult'].startswith(expected)
                                                  and all(f'{key}=1' in entry['desktopResult'] for key in
                                                          ['SendInput', 'edit', 'button', 'save', 'load', 'UTF8roundtrip']))
                if process.poll() is None:
                    with (work / 'desktop-vmmap.txt').open('wb') as mapping:
                        try:
                            subprocess.run(['/usr/bin/vmmap', '-w', str(process.pid)], stdout=mapping, stderr=subprocess.STDOUT, timeout=8, check=False)
                        except subprocess.TimeoutExpired:
                            pass
                stop_prefix(server, env)
                process.wait(timeout=10)
                entry['desktopWineLogSha256'] = sha(log)
                # The CPU mode exits itself and never loads an OpenVR runtime.
                cpu_command = [str(wine), str(cpu), '--cpu-self-test']
                entry['cpuCommand'] = cpu_command
                with (work / 'cpu-wine.log').open('wb') as output:
                    try:
                        completed = subprocess.run(cpu_command, cwd=work, env=env,
                                                   stdout=output, stderr=subprocess.STDOUT,
                                                   timeout=args.timeout, check=False)
                        entry['cpuExitCode'] = completed.returncode
                    except subprocess.TimeoutExpired:
                        entry['cpuTimedOut'] = True
                cpu_result = prefix / 'drive_c/vr-smoke.log'
                entry['cpuResult'] = cpu_result.read_text() if cpu_result.exists() else None
                entry['cpuPassed'] = bool(entry.get('cpuExitCode') == 0 and entry['cpuResult'] and
                                           f'CPU SELF TEST PASS pointerBits={bits} arithmetic=0xf0d18bc8 event=signaled' in entry['cpuResult'])
                print(json.dumps({'architecture': arch, 'desktopPassed': entry['desktopPassed'],
                                  'desktopResult': entry['desktopResult'], 'cpuPassed': entry['cpuPassed'],
                                  'cpuResult': entry['cpuResult']}), flush=True)
            finally:
                stop_prefix(server, env)
                if process is not None and process.poll() is None:
                    process.wait(timeout=10)
    finally:
        report['passed'] = len(report['tests']) == 2 and all(t.get('desktopPassed') and t.get('cpuPassed') for t in report['tests'].values())
        (run / 'execution-receipt.json').write_text(json.dumps(report, indent=2) + '\n')
        print(run / 'execution-receipt.json', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
