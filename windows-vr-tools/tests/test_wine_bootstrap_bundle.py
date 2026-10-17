"""Check the loader paths that failed during the first physical desktop launch."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

VERIFY = Path(__file__).resolve().parents[1] / "verify_wine_bundle.sh"


class WineBootstrapBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name) / "WineVision VR.app"
        for arch in ("aarch64-windows", "arm64ec-windows"):
            for filename in ("ntdll.dll", "apisetschema.dll"):
                for prefix in (self.app, self.app / "Runtime"):
                    path = prefix / arch / filename
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes((arch + filename).encode())
        nls = self.app / "Runtime/nls"
        nls.mkdir()
        for filename in ("normnfc.nls", "locale.nls", "l_intl.nls", "c_1252.nls"):
            (nls / filename).write_bytes((filename + " table").encode())
        fonts = self.app / "fonts"
        fonts.mkdir()
        for filename in ("tahoma.ttf", "tahomabd.ttf", "ms_sans_serif.ttf", "system.ttf"):
            (fonts / filename).write_bytes(b"font fixture")
        for filename in ("crypt32.dll", "cryptbase.dll", "rsaenh.dll", "psapi.dll", "imm32.dll"):
            (self.app / "Runtime/arm64ec-windows" / filename).write_bytes(b"crypto fixture")

    def verify(self, x86=False):
        # These fixtures explicitly model a 64-bit-only package. A developer's
        # experimental build environment must not change the selected contract.
        env = {**os.environ, "AVPPLAY_ENABLE_X86": "1" if x86 else "0"}
        return subprocess.run(["bash", str(VERIFY), str(self.app)],
                              capture_output=True, text=True, env=env)

    def copy_loader_tables(self):
        shutil.copytree(self.app / "Runtime/nls", self.app / "nls")

    def test_x86_opt_in_requires_actual_i386_bootstrap(self):
        self.copy_loader_tables()
        result = self.verify(x86=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("i386-windows/ntdll.dll", result.stderr)

    def test_runtime_only_tables_reproduce_failed_packaging(self):
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("loader NLS table", result.stderr)

    def test_complete_matching_tables_pass(self):
        self.copy_loader_tables()
        self.assertEqual(self.verify().returncode, 0)

    def test_missing_codepage_at_loader_path_fails(self):
        self.copy_loader_tables()
        (self.app / "nls/c_1252.nls").unlink()
        self.assertNotEqual(self.verify().returncode, 0)

    def test_corrupted_case_table_fails(self):
        self.copy_loader_tables()
        (self.app / "nls/l_intl.nls").write_bytes(b"wrong table")
        self.assertNotEqual(self.verify().returncode, 0)

    def test_missing_ui_font_fails(self):
        self.copy_loader_tables()
        (self.app / "fonts/tahoma.ttf").unlink()
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing Wine UI font", result.stderr)

    def test_missing_crypto_provider_fails(self):
        self.copy_loader_tables()
        (self.app / "Runtime/arm64ec-windows/rsaenh.dll").unlink()
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CryptoAPI provider dependency", result.stderr)

    def test_missing_steam_process_library_fails(self):
        self.copy_loader_tables()
        (self.app / "Runtime/arm64ec-windows/psapi.dll").unlink()
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("psapi.dll", result.stderr)


if __name__ == "__main__":
    unittest.main()
