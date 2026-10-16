from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_wine_imports import dependencies, missing_dependencies, I386_KERNEL32_UNSUPPORTED_WIN16_EXPORTS


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


    def test_explicit_cpl_exe16_and_arbitrary_extensions_are_preserved(self):
        self.assertEqual(dependencies("", "one (forwarded to bthprops.cpl.BluetoothEnableDiscovery)\n"
                                          "two (forwarded to krnl386.exe16.MapSL)\n"
                                          "three (forwarded to codec.acm.ExportedFunction)"),
                         {"bthprops.cpl", "krnl386.exe16", "codec.acm"})
        self.assertEqual(missing_dependencies({"irprops.cpl": dependencies("", "one (forwarded to bthprops.cpl.Function)")},
                                              {"irprops.cpl", "bthprops.cpl"}), {})

    def test_known_private_win16_forwarders_are_explicitly_reported_only_on_i386_kernel32(self):
        unsupported = []
        exports = "one (forwarded to krnl386.exe16.MapSL)\ntwo (forwarded to kernelbase.Sleep)"
        names = dependencies("", exports, importer="KERNEL32.dll", machine="i386", unsupported_forwarders=unsupported)
        self.assertEqual(names, {"kernelbase.dll"})
        self.assertEqual([item["target"] for item in unsupported], ["krnl386.exe16.MapSL"])
        self.assertIn("16-bit execution is unsupported", unsupported[0]["reason"])
        self.assertEqual(len(I386_KERNEL32_UNSUPPORTED_WIN16_EXPORTS), 141)

    def test_direct_import_to_unsupported_module_is_never_exempted(self):
        names = dependencies("  Name: krnl386.exe16\n", "one (forwarded to krnl386.exe16.MapSL)",
                             importer="kernel32.dll", machine="i386")
        self.assertEqual(missing_dependencies({"kernel32.dll": names}, {"kernel32.dll"}),
                         {"krnl386.exe16": ["kernel32.dll"]})

    def test_unknown_exports_other_modules_and_other_architectures_are_not_exempted(self):
        known = "one (forwarded to krnl386.exe16.MapSL)"
        for importer, machine in (("user32.dll", "i386"), ("kernel32.dll", "arm64"), ("kernel32.dll", None)):
            with self.subTest(importer=importer, machine=machine):
                self.assertEqual(dependencies("", known, importer=importer, machine=machine), {"krnl386.exe16"})
        self.assertEqual(dependencies("", "one (forwarded to krnl386.exe16.Unreviewed32BitExport)",
                                      importer="kernel32.dll", machine="i386"), {"krnl386.exe16"})
        self.assertEqual(dependencies("", "one (forwarded to krnl386.exe16.mapsl)",
                                      importer="kernel32.dll", machine="i386"), {"krnl386.exe16"})
