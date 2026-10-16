from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_wine_imports import dependencies, missing_dependencies


class ImportClosureTests(unittest.TestCase):
    def test_crypto_forwarder_and_normal_import_are_both_dependencies(self):
        names = dependencies("Import {\n  Name: KERNEL32.dll\n}\n",
                             "SystemFunction036 (forwarded to cryptbase.SystemFunction036)")
        self.assertEqual(names, {"kernel32.dll", "cryptbase.dll"})

    def test_missing_forwarded_provider_is_reported_with_importer(self):
        graph = {"advapi32.dll": {"kernel32.dll", "cryptbase.dll"}}
        self.assertEqual(missing_dependencies(graph, {"advapi32.dll", "kernel32.dll"}),
                         {"cryptbase.dll": ["advapi32.dll"]})

    def test_explicit_dll_and_driver_extensions_are_preserved(self):
        self.assertEqual(dependencies("", "one (forwarded to KERNEL32.dll.Sleep)\ntwo (forwarded to winspool.drv.OpenPrinterW)"),
                         {"kernel32.dll", "winspool.drv"})

    def test_api_sets_are_virtual_and_complete_closure_passes(self):
        graph = {"app.exe": {"api-ms-win-core-libraryloader-l1-2-0.dll", "kernel32.dll"}}
        self.assertEqual(missing_dependencies(graph, {"app.exe", "kernel32.dll"}), {})
