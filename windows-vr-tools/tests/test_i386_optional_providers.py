"""Execute the production optional-provider build function with fake tool I/O.

Fixtures are authored PE headers, not Wine/game binaries. Fake make/strip stand
in for tool execution; production target selection, validation, staging and
provenance code run unchanged.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'windows-vr-tools/build_wine_i386_resources.sh'


class OptionalProviderBuildTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='wvr-i386-providers-')
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name)
        self.runtime = self.base / 'runtime'
        self.farm = self.runtime / 'app/Madeira/i386-windows'
        self.farm.mkdir(parents=True)
        (self.runtime / 'build').mkdir()
        (self.runtime / 'AVPPLAY_SOURCE_PROVENANCE.json').write_text('{"source":"fixture"}')
        self.tools = self.base / 'toolchain/bin'
        self.tools.mkdir(parents=True)
        self.targets = ('dlls/d3d10core/i386-windows/d3d10core.dll', 'dlls/d3d9/i386-windows/d3d9.dll')
        for target in self.targets:
            self.pe(self.runtime / 'wine/build-i386' / target)
        self.modern = ('d3d11.dll', 'd3d12.dll', 'dxgi.dll', 'winemetal.dll')
        for name in self.modern:
            self.pe(self.farm / name)
        self.before = {name: (self.farm / name).read_bytes() for name in self.modern}
        self.executable('make', '''#!/usr/bin/env python3
import json, os, pathlib, sys
pathlib.Path(os.environ['TEST_MAKE_ARGS']).write_text(json.dumps(sys.argv[1:]))
if os.environ.get('TEST_MAKE_FAIL'): raise SystemExit(7)
if os.environ.get('TEST_MAKE_MUTATE'):
    pathlib.Path(os.environ['TEST_MAKE_MUTATE']).write_bytes(b'unwanted overwrite')
''')
        self.executable('i686-w64-mingw32-strip', '''#!/usr/bin/env python3
import pathlib, sys
assert sys.argv[1] == '--strip-debug'
p = pathlib.Path(sys.argv[2]); p.write_bytes(p.read_bytes() + b'-stripped')
''')
        source = SCRIPT.read_text()
        start = source.index('stage_modern_optional_wine_providers() {')
        end = source.index('\n}\n\n', start) + 3
        self.function = source[start:end]
        self.env = dict(os.environ, PATH=str(self.tools) + os.pathsep + os.environ['PATH'],
                        TEST_MAKE_ARGS=str(self.base / 'make-args.json'),
                        TEST_RUNTIME=str(self.runtime), TEST_TOOLCHAIN=str(self.tools.parent))

    def pe(self, path, machine=0x14c):
        data = bytearray(256)
        data[:2] = b'MZ'; data[60:64] = (64).to_bytes(4, 'little')
        data[64:68] = b'PE\0\0'; data[68:70] = machine.to_bytes(2, 'little')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def executable(self, name, source):
        path = self.tools / name
        path.write_text(source); path.chmod(0o755)

    def run_function(self):
        return subprocess.run(['bash', '-c', 'set -euo pipefail\n' + self.function +
                               '\nruntime_root="$TEST_RUNTIME"\nAVPPLAY_LLVM_MINGW_ROOT="$TEST_TOOLCHAIN"\nJOBS=3\nstage_modern_optional_wine_providers\n'],
                              env=self.env, capture_output=True, text=True)

    def test_builds_same_wine_providers_without_touching_modern_graphics(self):
        result = self.run_function()
        self.assertEqual(result.returncode, 0, result.stderr)
        requested = json.loads((self.base / 'make-args.json').read_text())
        self.assertEqual(requested, ['-C', str(self.runtime / 'wine/build-i386'), '-j3', *self.targets])
        report = json.loads((self.runtime / 'build/i386-optional-wine-providers.json').read_text())
        self.assertEqual(report['buildDirectory'], 'wine/build-i386')
        for target, record in zip(self.targets, report['targets']):
            built = (self.runtime / 'wine/build-i386' / target).read_bytes()
            packaged = (self.farm / Path(target).name).read_bytes()
            self.assertEqual(packaged, built + b'-stripped')
            self.assertEqual(record, dict(sourceTarget=target,
                buildSha256=hashlib.sha256(built).hexdigest(), packagedSha256=hashlib.sha256(packaged).hexdigest()))
        self.assertEqual(report['sourceProvenanceSha256'], hashlib.sha256((self.runtime / 'AVPPLAY_SOURCE_PROVENANCE.json').read_bytes()).hexdigest())
        self.assertEqual(self.before, {name: (self.farm / name).read_bytes() for name in self.modern})
        self.assertFalse(list(self.farm.glob('*.tmp')))

    def test_make_failure_does_not_stage_providers_or_publish_success(self):
        self.env['TEST_MAKE_FAIL'] = '1'
        result = self.run_function()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.runtime / 'build/i386-optional-wine-providers.json').exists())
        self.assertFalse((self.farm / 'd3d9.dll').exists())
        self.assertEqual(self.before, {name: (self.farm / name).read_bytes() for name in self.modern})

    def test_rejects_wrong_architecture_before_installing_it(self):
        self.pe(self.runtime / 'wine/build-i386' / self.targets[0], 0x8664)
        result = self.run_function()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('regular i386 build', result.stderr)
        self.assertFalse((self.farm / 'd3d10core.dll').exists())
        self.assertFalse((self.runtime / 'build/i386-optional-wine-providers.json').exists())

    def test_detects_unexpected_modern_graphics_overwrite(self):
        self.env['TEST_MAKE_MUTATE'] = str(self.farm / 'd3d11.dll')
        result = self.run_function()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('changed the modern DXMT graphics closure', result.stderr)
        self.assertFalse((self.runtime / 'build/i386-optional-wine-providers.json').exists())


if __name__ == '__main__':
    unittest.main()
