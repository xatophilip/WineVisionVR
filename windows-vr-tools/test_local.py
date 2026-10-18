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
    parser.add_argument('--dxmt-wow64-source', type=Path,
                        help='prepared legacy DXMT tree for shifted-window WOW64 VR transport checks')
    parser.add_argument('--opencomposite-source', type=Path,
                        help='OpenComposite source with this repository\'s patches applied')
    parser.add_argument('--madeira-source', type=Path,
                        help='clean pinned Madeira checkout (default: third-party/madeira); not the patched overlay')
    parser.add_argument('--runtime-source', type=Path,
                        help='prepared Madeira overlay for child-GDI/JIT tests (or AVPPLAY_RUNTIME_SOURCE)')
    parser.add_argument('--dxmt-modern-wow64-source', type=Path,
                        help='modern DXMT with WOW64 patch 0025 (or AVPPLAY_D3D12_PROFILE_SOURCE/dxmt)')
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
    run('session-diagnostics', [python, 'visionos-windows-vr/Tests/Contracts/test_session_diagnostics.py',
                                 '--build', build / 'session-diagnostics'])
    run('guest-session-health', [python, 'visionos-windows-vr/Tests/Contracts/test_guest_session_health.py',
                                   '--build', build / 'guest-session-health'])
    run('guest-startup-watchdog', [python, 'visionos-windows-vr/Tests/Contracts/test_guest_startup_watchdog.py',
                                    '--build', build / 'guest-startup-watchdog'])
    run('controller-anchor-lifecycle', [python, 'visionos-windows-vr/Tests/Contracts/test_controller_anchor_lifecycle.py',
                                         '--build', build / 'controller-anchor-lifecycle'])
    run('tracking-startup', [python, 'visionos-windows-vr/Tests/Contracts/test_tracking_startup.py',
                              '--build', build / 'tracking-startup'])
    run('vr-registration', [python, 'visionos-windows-vr/Tests/Contracts/test_vr_registration.py'])
    run('vr-registration-architecture', [python, 'visionos-windows-vr/Tests/Contracts/test_vr_registration_architecture.py',
                                           '--build', build / 'vr-registration-architecture'])
    run('steam-launch-selection', [python, 'visionos-windows-vr/Tests/Contracts/test_steam_launch_selection.py'])
    run('steam-dosbox-compatibility', [python, 'visionos-windows-vr/Tests/Contracts/test_steam_dosbox_compatibility.py',
                                        '--build', build / 'steam-dosbox-compatibility'])
    run('steam-lab-compatibility', [python, 'visionos-windows-vr/Tests/Contracts/test_steam_lab_compatibility.py',
                                     '--build', build / 'steam-lab-compatibility'])
    run('steam-guest-architecture', [python, 'visionos-windows-vr/Tests/Contracts/test_steam_guest_architecture.py',
                                     '--build', build / 'steam-guest-architecture'])
    run('steam-download-queue', [python, 'visionos-windows-vr/Tests/Contracts/test_steam_download_queue.py',
                                  '--build', build / 'steam-download-queue'])
    run('steam-diagnostic-repair', [python, 'visionos-windows-vr/Tests/Contracts/test_steam_diagnostic_repair.py',
                                     '--build', build / 'steam-diagnostic-repair'])
    run('steam-background-transfers', [python, 'visionos-windows-vr/Tests/Contracts/test_steam_background_transfers.py',
                                      '--build', build / 'steam-background-transfers'])
    run('steam-download-sizes', [python, 'visionos-windows-vr/Tests/Contracts/test_steam_download_sizes.py',
                                  '--build', build / 'steam-download-sizes'])
    run('graphics-profile-link', [python, 'windows-runtime-plugin/Tests/test_graphics_profile_link.py',
                                  '--build', build / 'graphics-profile-link'])
    if env.get('AVPPLAY_LLVM_MINGW_ROOT') and (Path(env['AVPPLAY_LLVM_MINGW_ROOT']) / 'bin/i686-w64-mingw32-clang').is_file():
        run('desktop-demo-selection', [python, 'visionos-windows-vr/Tests/Contracts/test_desktop_demo_selection.py',
                                      '--build', build / 'desktop-demo-selection'])
        run('mixed-child-selection', [python, 'visionos-windows-vr/Tests/Contracts/test_mixed_child_selection.py',
                                     '--build', build / 'mixed-child-selection'])
    else:
        skip('desktop-demo-selection', 'Set AVPPLAY_LLVM_MINGW_ROOT to compile real x64/i386 fixture executables')
        skip('mixed-child-selection', 'Set AVPPLAY_LLVM_MINGW_ROOT to compile real x64/i386 fixture executables')
    run('desktop-input', [python, 'visionos-windows-vr/Tests/Contracts/test_desktop_input.py',
                          '--build', build / 'desktop-input'])
    run('desktop-gamepad', [python, 'visionos-windows-vr/Tests/Contracts/test_desktop_gamepad.py',
                            '--build', build / 'desktop-gamepad'])
    run('return-to-vr', [python, 'visionos-windows-vr/Tests/Contracts/test_return_to_vr.py',
                         '--build', build / 'return-to-vr'])
    run('compositor-task-retirement', [python, 'visionos-windows-vr/Tests/Contracts/test_compositor_task_retirement.py',
                                      '--build', build / 'compositor-task-retirement'])
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
                                      '-framework', 'QuartzCore',
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

    runtime_source = args.runtime_source or env.get('AVPPLAY_RUNTIME_SOURCE')
    if runtime_source:
        runtime_source = Path(runtime_source).expanduser().resolve()
        run('wow64-smc-atomic', [python, 'windows-runtime-plugin/Tests/test_wow64_smc_atomic.py',
                                  '--runtime-source', runtime_source,
                                  '--build', build / 'wow64-smc-atomic'])
        run('wine-cache-topology', [python, 'windows-runtime-plugin/Tests/test_wine_cache_topology.py',
                                    '--runtime-source', runtime_source,
                                    '--build', build / 'wine-cache-topology'])
        run('child-gdi-publication', [python, 'windows-runtime-plugin/Tests/test_child_gdi_publication.py',
                                      '--runtime-source', runtime_source,
                                      '--build', build / 'child-gdi-publication'])
        run('window-parent-cache', [python, 'windows-runtime-plugin/Tests/test_window_parent_cache.py',
                                      '--runtime-source', runtime_source,
                                      '--build', build / 'window-parent-cache'])
        run('mouse-activation', [python, 'windows-runtime-plugin/Tests/test_mouse_activation.py',
                                   '--runtime-source', runtime_source,
                                   '--build', build / 'mouse-activation'])
        run('jit-pool-arbitration', [python, 'windows-vr-openxr/tests/test_jit_pool_arbitration.py',
                                     '--runtime-source', runtime_source,
                                     '--output-dir', build / 'jit-pool-arbitration'])
    else:
        skip('child-gdi-publication', '--runtime-source or AVPPLAY_RUNTIME_SOURCE not supplied; requires prepared Madeira')
        skip('window-parent-cache', '--runtime-source or AVPPLAY_RUNTIME_SOURCE not supplied; requires prepared Madeira')
        skip('mouse-activation', '--runtime-source or AVPPLAY_RUNTIME_SOURCE not supplied; requires prepared Madeira')
        skip('jit-pool-arbitration', '--runtime-source or AVPPLAY_RUNTIME_SOURCE not supplied; requires prepared Madeira')

    if runtime_source:
        run('native-child-bootstrap', [python, 'windows-runtime-plugin/Tests/test_native_child_bootstrap.py',
                                       '--runtime-source', runtime_source,
                                       '--build', build / 'native-child-bootstrap'])
    else:
        skip('native-child-bootstrap', 'Requires prepared pinned Madeira source')

    if runtime_source and all((runtime_source / "app/Madeira" / name).is_file() for name in
                              ("aarch64-windows/wow64.dll", "arm64ec-windows/ntdll.dll")):
        run('native-arm64-import-redirection', [python, 'windows-runtime-plugin/Tests/test_native_arm64_import_redirection.py',
                                               '--runtime-source', runtime_source,
                                               '--build', build / 'native-arm64-import-redirection'])
    else:
        skip('native-arm64-import-redirection', 'Requires prepared runtime with app/Madeira ARM64 wow64 and ARM64EC ntdll PE fixtures')

    if runtime_source and (runtime_source / 'wine/programs/wmic/main.c').is_file():
        run('wine-wmic-provider', [python, 'windows-runtime-plugin/Tests/test_wine_wmic_provider.py',
                                   '--runtime-source', runtime_source,
                                   '--build', build / 'wine-wmic-provider'])
    else:
        skip('wine-wmic-provider', 'Requires prepared pinned Wine WMIC and wbemprox source')

    xinput_modules = ("xinput1_3.dll", "xinput1_4.dll", "xinput9_1_0.dll")
    if runtime_source and (runtime_source / 'wine/dlls/xinput1_3/main.c').is_file() and all(
            (runtime_source / 'app/Madeira/arm64ec-windows' / name).is_file() for name in xinput_modules):
        run('wine-xinput-packaging', [python, 'windows-runtime-plugin/Tests/test_wine_xinput_packaging.py',
                                     '--runtime-source', runtime_source,
                                     '--build', build / 'wine-xinput-packaging'])
    else:
        skip('wine-xinput-packaging', 'Requires prepared Wine source and genuine ARM64EC XInput PE fixtures')

    modern_source = args.dxmt_modern_wow64_source
    if modern_source is None and env.get('AVPPLAY_D3D12_PROFILE_SOURCE'):
        modern_source = Path(env['AVPPLAY_D3D12_PROFILE_SOURCE']) / 'dxmt'
    if modern_source:
        modern_source = Path(modern_source).expanduser().resolve()
        run('dxmt-wine-log-safety', [python, 'windows-vr-openxr/tests/test_dxmt_wine_log_safety.py',
                                      '--dxmt-source', modern_source,
                                      '--output-dir', build / 'dxmt-wine-log-safety'])
        run('modern-wow64-transport', [python, 'windows-vr-openxr/tests/test_modern_wow64_transport.py',
                                       '--dxmt-source', modern_source,
                                       '--output-dir', build / 'modern-wow64-transport'])
        mingw = env.get('AVPPLAY_LLVM_MINGW_ROOT')
        if mingw and (Path(mingw) / 'bin/i686-w64-mingw32-clang').is_file():
            run('modern-wow64-layout', [python, 'windows-vr-openxr/tests/test_modern_wow64_layout.py',
                                        '--dxmt-source', modern_source, '--llvm-mingw-root', mingw,
                                        '--build', build / 'modern-wow64-layout'])
        else:
            skip('modern-wow64-layout', 'Set AVPPLAY_LLVM_MINGW_ROOT to compare actual i386 and visionOS record layouts')
    else:
        skip('dxmt-wine-log-safety', '--dxmt-modern-wow64-source or AVPPLAY_D3D12_PROFILE_SOURCE not supplied')
        skip('modern-wow64-transport', '--dxmt-modern-wow64-source or AVPPLAY_D3D12_PROFILE_SOURCE not supplied')
        skip('modern-wow64-layout', '--dxmt-modern-wow64-source or AVPPLAY_D3D12_PROFILE_SOURCE not supplied')

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

    if args.dxmt_wow64_source:
        run('wow64-vr-pointers', [python, 'windows-vr-openxr/tests/test_wow64_wvr_pointers.py',
                                  '--source', args.dxmt_wow64_source.expanduser().resolve(),
                                  '--build', build / 'wow64-vr-pointers'])
    else:
        skip('wow64-vr-pointers', '--dxmt-wow64-source not supplied; requires legacy WOW64 DXMT')

    if args.opencomposite_source:
        run('opencomposite-base-mip', [python, 'windows-vr-openvr/tests/test_base_mip_swapchain.py',
                                       '--source', args.opencomposite_source.expanduser().resolve(),
                                       '--build', build / 'opencomposite-base-mip'])
        run('inverted-eye-bounds', [python, 'windows-vr-openvr/tests/test_inverted_bounds.py',
                                    args.opencomposite_source.expanduser().resolve(),
                                    '--build', build / 'inverted-eye-bounds'])
        run('logger-lifetime', [python, 'windows-vr-openvr/tests/test_logger_lifetime.py',
                                args.opencomposite_source.expanduser().resolve()])
    else:
        skip('logger-lifetime', '--opencomposite-source not supplied; requires the patched overlay')
        skip('opencomposite-base-mip', '--opencomposite-source not supplied; requires the pinned overlay and LLVM-MinGW headers')

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
