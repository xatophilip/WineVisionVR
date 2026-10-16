#!/usr/bin/env python3
"""Run local correctness checks without Wine, a game, or a paired headset.

All requested checks run even when an earlier check fails. Build products, module
caches, temporary files, logs and a machine-readable report go under --build.
Game/headset FPS is deliberately outside this runner's scope.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', required=True, type=Path,
                        help='scratch/output directory, preferably on a volume with ample space')
    parser.add_argument('--dxmt-source', type=Path,
                        help='DXMT source with this repository\'s patches applied')
    parser.add_argument('--opencomposite-source', type=Path,
                        help='OpenComposite source with this repository\'s patches applied')
    parser.add_argument('--madeira-source', type=Path,
                        help='clean pinned Madeira checkout (default: third-party/madeira); not the patched overlay')
    parser.add_argument('--simulator', metavar='UDID',
                        help='also run GPU/audio probes on an already booted visionOS 27 simulator')
    parser.add_argument('--skip-visionos-build', action='store_true',
                        help='omit WindowsVRMetal and native bridge device-SDK builds')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    build = args.build.expanduser().resolve()
    for name in ('logs', 'tmp', 'module-cache', 'swift-cache'):
        (build / name).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(TMPDIR=str(build / 'tmp'),
               CLANG_MODULE_CACHE_PATH=str(build / 'module-cache'),
               SWIFTPM_MODULECACHE_OVERRIDE=str(build / 'module-cache'),
               PYTHONDONTWRITEBYTECODE='1')
    # Use Apple's compiler/Swift shims, which honor DEVELOPER_DIR and select the
    # host SDK. A guest build environment may otherwise pick LLVM-MinGW, while
    # calling the Xcode compiler directly can miss the host SDK's C++ headers.
    env['PATH'] = '/usr/bin' + os.pathsep + env.get('PATH', '')
    results = []
    python = sys.executable

    def run(name, command, cwd=root):
        command = [str(item) for item in command]
        log = build / 'logs' / (name + '.log')
        start = time.monotonic()
        entry = dict(name=name, command=command, cwd=str(cwd), log=str(log))
        with log.open('w') as stream:
            try:
                result = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=1200)
                entry.update(status='pass' if result.returncode == 0 else 'fail',
                             exitCode=result.returncode)
            except (OSError, subprocess.TimeoutExpired) as error:
                stream.write('\nRunner error: ' + str(error) + '\n')
                entry.update(status='fail', error=str(error))
        entry['seconds'] = round(time.monotonic() - start, 3)
        results.append(entry)
        print(f'{name}: {entry["status"]} ({log})', flush=True)

    def skip(name, reason):
        results.append(dict(name=name, status='skipped', reason=reason))
        print(f'{name}: skipped ({reason})', flush=True)

    run('packaging', [python, '-m', 'unittest', 'discover', '-s',
                      'windows-vr-tools/tests', '-v'])
    run('vr-registration', [python, 'visionos-windows-vr/Tests/Contracts/test_vr_registration.py'])
    run('steam-launch-selection', [python, 'visionos-windows-vr/Tests/Contracts/test_steam_launch_selection.py'])
    run('steam-download-queue', [python, 'visionos-windows-vr/Tests/Contracts/test_steam_download_queue.py',
                                  '--build', build / 'steam-download-queue'])
    run('desktop-launch-contract', [python, 'windows-runtime-plugin/Tests/test_desktop_contract.py',
                                    '--build', build / 'desktop-contract'])
    run('guest-runtime-mapping', [python, 'windows-runtime-plugin/Tests/test_guest_runtime_mapping.py',
                                  '--build', build / 'guest-runtime-mapping'])
    run('swift-core', ['swift', 'test', '--package-path', root / 'windows-vr',
                       '--scratch-path', build / 'swift', '--cache-path', build / 'swift-cache'])
    run('host-metal', [python, 'windows-vr-tools/test_fps_batch.py', '--build', build / 'host-metal'])

    if not args.skip_visionos_build:
        run('metal-visionos', ['xcodebuild', '-scheme', 'WindowsVRMetal', '-destination',
                              'generic/platform=visionOS', '-derivedDataPath', build / 'metal-derived',
                              'CODE_SIGNING_ALLOWED=NO', 'build'], root / 'windows-vr-metal')
        run('native-bridge-visionos', ['xcrun', '--sdk', 'xros', 'clang++', '-target',
                                      'arm64-apple-xros27.0', '-std=c++20', '-fobjc-arc',
                                      '-dynamiclib', '-DWVR_SOURCE_AIR_WRITER=0', '-I',
                                      root / 'windows-vr-native/include',
                                      *sorted((root / 'windows-vr-native/Sources').glob('*.mm')),
                                      '-framework', 'Foundation', '-framework', 'Metal',
                                      '-framework', 'AVFAudio', '-framework', 'CoreFoundation',
                                      '-o', build / 'libWindowsVRNativeBridge.dylib'])
    else:
        skip('metal-visionos', '--skip-visionos-build specified')
        skip('native-bridge-visionos', '--skip-visionos-build specified')

    if (root / 'third-party/openxr/include/openxr/openxr.h').is_file():
        run('input-contract', [python, 'windows-vr-openxr/tests/test_input_contract.py'])
        run('action-lifetime', [python, 'windows-vr-openxr/tests/test_action_lifetime.py'])
        run('session-stop', [python, 'windows-vr-openxr/tests/test_session_stop.py',
                             '--build', build / 'session-stop'])
    else:
        skip('input-contract', 'fetch the pinned third-party OpenXR headers first')
        skip('action-lifetime', 'fetch the pinned third-party OpenXR headers first')

    madeira = (args.madeira_source or root / 'third-party/madeira').expanduser().resolve()
    if args.madeira_source or (madeira / 'wine/dlls/ntdll/unix/system.c').is_file():
        run('runtime-source-repairs', [python, 'windows-runtime-plugin/Tests/test_source_runtime_repairs.py',
                                      '--source', madeira])
    else:
        skip('runtime-source-repairs', 'fetch the clean pinned Madeira checkout first')

    if args.dxmt_source:
        source = args.dxmt_source.expanduser().resolve()
        for name, flags in [('event_signal_ordering', []), ('event_flush_coalescing', ['--completed-cache']),
                            ('query_publication', []), ('query_efficiency', []),
                            ('vr_encoder_boundaries', []), ('query_publication', ['--tsan']),
                            ('query_efficiency', ['--asan'])]:
            label = name.replace('_', '-') + ''.join(flags)
            run(label, [python, f'windows-vr-openxr/tests/test_{name}.py', source, *flags])
    else:
        skip('dxmt-regressions', '--dxmt-source not supplied; requires the patched overlay')

    if args.opencomposite_source:
        run('inverted-eye-bounds', [python, 'windows-vr-openvr/tests/test_inverted_bounds.py',
                                    args.opencomposite_source.expanduser().resolve(),
                                    '--build', build / 'inverted-eye-bounds'])
        run('logger-lifetime', [python, 'windows-vr-openvr/tests/test_logger_lifetime.py',
                                args.opencomposite_source.expanduser().resolve()])
    else:
        skip('logger-lifetime', '--opencomposite-source not supplied; requires the patched overlay')

    if args.simulator:
        for name in ('compositor', 'frame_transfer', 'gpu_statistics', 'presentation', 'audio_session'):
            run('simulator-' + name.replace('_', '-'),
                ['bash', f'windows-vr-tools/test_simulator_{name}.sh', args.simulator])
    else:
        skip('simulator', '--simulator not supplied; host Metal tests still exercise real GPU work')

    def git(*arguments):
        return subprocess.check_output(['git', *arguments], cwd=root, text=True).strip()

    files = ['visionos-windows-vr/Sources/Rendering/WindowsVRCompositorScene.swift',
             'windows-vr-native/Sources/WindowsVRCompositorBridge.mm',
             'windows-vr-native/Sources/WindowsVRMetalDiagnostics.mm',
             'windows-vr-tools/test_local.py']
    files += ['windows-runtime-plugin/WindowsVRRuntimePlugin.mm',
              'windows-vr/Sources/WindowsVRCore/WindowsGameManifest.swift',
              'windows-vr/Sources/WindowsVRCore/WindowsDesktopKeyboard.swift',
              'visionos-windows-vr/Sources/Desktop/WindowsDesktopView.swift']
    report = dict(schemaVersion=1, recordedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  scope='Host CPU/Metal and optional simulator correctness; no game or headset FPS',
                  revision=git('rev-parse', 'HEAD'), dirtyStatus=git('status', '--short'),
                  system=platform.platform(), machine=platform.machine(),
                  developerDirectory=env.get('DEVELOPER_DIR'),
                  sourceSHA256={name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files},
                  checks=results)
    report_path = build / 'results.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    failures = sum(item['status'] == 'fail' for item in results)
    print(f'Report: {report_path}; {failures} failed checks', flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
