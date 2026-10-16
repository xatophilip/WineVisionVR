"""Offline packaging regressions. Fixtures contain no Wine or game binaries."""
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sanitize_prefix_snapshot as sanitizer
import stage_resources as stage
import resource_receipt as receipt
import verify_wine_imports as imports
from verify_source_checkout import verify_source_checkout


class PrefixTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.source = self.root / "source.tar.gz"

    def archive(self, extra=(), layout="prefix/"):
        entries = [(layout + "system.reg", b"registry"),
                   (layout + "user.reg", b"registry"),
                   (layout + "drive_c/windows/system32", None), *extra]
        with tarfile.open(self.source, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            for name, value in entries:
                member = tarfile.TarInfo(name)
                if isinstance(value, tarfile.TarInfo):
                    member = value
                elif value is None:
                    member.type = tarfile.DIRTYPE
                else:
                    member.size = len(value)
                archive.addfile(member, io.BytesIO(value) if isinstance(value, bytes) else None)

    def test_root_and_upstream_layouts(self):
        for layout in ("", "prefix/"):
            with self.subTest(layout=layout):
                self.archive(layout=layout)
                stage.validate_prefix_archive(self.source)

    def test_rejects_links_collisions_and_file_ancestors(self):
        link = tarfile.TarInfo("prefix/drive_c/host")
        link.type, link.linkname = tarfile.SYMTYPE, "/unreadable/host/path"
        cases = [
            ([('prefix/drive_c/host', link)], "symlinks"),
            ([('prefix/SYSTEM.REG', b"other")], "case-colliding"),
            ([('prefix/data', b"file"), ('prefix/data/child', b"file")], "file used as a directory"),
            ([('prefix/../escape', b"file")], "unsafe path"),
        ]
        for entries, reason in cases:
            with self.subTest(reason=reason):
                self.archive(entries)
                with self.assertRaisesRegex(SystemExit, reason):
                    stage.validate_prefix_archive(self.source)

    def test_member_cap_stops_iteration_before_remaining_headers(self):
        self.archive([(f"prefix/item{i}", b"") for i in range(10)])
        original = tarfile.open(self.source, "r:gz")
        self.addCleanup(original.close)

        class LimitedReader:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def getmembers(self): raise AssertionError("Must not materialize the full archive")
            def __iter__(self):
                for count, entry in enumerate(original, 1):
                    if count > 4:
                        raise AssertionError("Read past the enforced member cap")
                    yield entry

        with patch.object(stage, "MAX_ARCHIVE_MEMBERS", 3), patch.object(stage.tarfile, "open", return_value=LimitedReader()):
            with self.assertRaisesRegex(SystemExit, "too many archive members"):
                stage.validate_prefix_archive(self.source)

    def test_oversized_header_rejected_without_reading_declared_body(self):
        member = tarfile.TarInfo("prefix/huge")
        member.size = 1025
        with gzip.open(self.source, "wb") as stream:
            stream.write(member.tobuf(format=tarfile.USTAR_FORMAT))
        with patch.object(stage, "MAX_ARCHIVE_FILE", 1024):
            with self.assertRaisesRegex(SystemExit, "oversized file"):
                stage.validate_prefix_archive(self.source)

    def test_cumulative_size_limit(self):
        self.archive()
        with patch.object(stage, "MAX_ARCHIVE_UNPACKED", 10):
            with self.assertRaisesRegex(SystemExit, "maximum uncompressed size"):
                stage.validate_prefix_archive(self.source)

    def test_sanitizer_preserves_registry_and_never_follows_host_links(self):
        name = "prefix/drive_c/users/madeira/Documents"
        link = tarfile.TarInfo(name)
        link.type, link.linkname = tarfile.SYMTYPE, "/unreadable/host/Documents"
        self.archive([(name, link), ("prefix/._system.reg", b"host metadata")])
        output, receipt = self.root / "portable.tar.gz", self.root / "receipt.json"
        with patch.object(Path, "read_bytes", side_effect=AssertionError("Archive hashing must stream")):
            sanitizer.sanitize(self.source, output, receipt)
        stage.validate_prefix_archive(output)
        with tarfile.open(output, "r:gz") as archive:
            self.assertEqual(archive.extractfile("prefix/system.reg").read(), b"registry")
            self.assertTrue(archive.getmember(name).isdir())
            self.assertNotIn("prefix/._system.reg", archive.getnames())
            self.assertTrue(all(not item.pax_headers for item in archive))
        value = json.loads(receipt.read_text())
        self.assertEqual(value["removedLinkNames"], [name])
        self.assertEqual(value["portableArchiveSha256"], sanitizer.sha256_file(output))

    def test_receipt_publication_failure_rolls_back_archive_and_temp_file(self):
        self.archive()
        output, receipt = self.root / "portable.tar.gz", self.root / "receipt.json"
        with patch.object(sanitizer.os, "link", side_effect=PermissionError("fixture")):
            with self.assertRaises(PermissionError):
                sanitizer.sanitize(self.source, output, receipt)
        self.assertFalse(output.exists())
        self.assertFalse(receipt.exists())
        self.assertEqual(list(self.root.glob(".prefix-receipt-*")), [])

    def test_existing_or_dangling_receipt_is_preserved(self):
        self.archive()
        output, receipt = self.root / "portable.tar.gz", self.root / "receipt.json"
        receipt.symlink_to("missing-target")
        with self.assertRaisesRegex(SystemExit, "fresh portable"):
            sanitizer.sanitize(self.source, output, receipt)
        self.assertTrue(receipt.is_symlink())
        self.assertFalse(output.exists())

    def test_racing_output_writer_is_not_deleted(self):
        self.archive()
        output, receipt = self.root / "portable.tar.gz", self.root / "receipt.json"
        original_open = Path.open

        def racing_open(path, *args, **kwargs):
            if path == output and args == ("xb",):
                with original_open(path, "wb") as stream:
                    stream.write(b"other writer")
                raise FileExistsError("other writer won the race")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", racing_open):
            with self.assertRaises(FileExistsError):
                sanitizer.sanitize(self.source, output, receipt)
        self.assertEqual(output.read_bytes(), b"other writer")


class DriverPackagingTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.source = self.root / "source"
        for name in ("aarch64-windows", "arm64ec-windows", "nls", "legal"):
            (self.source / name).mkdir(parents=True)
        (self.source / "arm64ec-windows/winspool.drv").write_bytes(b"PE driver fixture")

    def test_guest_receipt_hashes_driver_modules(self):
        files = receipt.guest_resource_files(self.source)
        self.assertEqual(files["arm64ec-windows/winspool.drv"],
                         receipt.sha256_file(self.source / "arm64ec-windows/winspool.drv"))

    def test_stage_keeps_required_driver_module(self):
        destination = self.root / "stage"
        destination.mkdir()
        with patch.object(stage, "REQUIRED_BUILTINS", set()), \
             patch.object(stage, "ARM64EC_REQUIRED_BUILTINS", {"winspool.drv"}):
            stage.copy_builtins(self.source, destination)
        self.assertEqual((destination / "arm64ec-windows/winspool.drv").read_bytes(), b"PE driver fixture")


class X86PackagingTests(unittest.TestCase):
    """Exercise fail-closed opt-in copying, architecture and dependency receipts."""
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.source = self.root / "source"
        for farm, machine in (("aarch64-windows", 0xAA64), ("arm64ec-windows", 0xA641), ("i386-windows", 0x14C)):
            names = (stage.I386_REQUIRED_BUILTINS if machine == 0x14C else stage.REQUIRED_BUILTINS) | ({"d3d11.dll", "winemetal.dll"} | stage.ARM64EC_REQUIRED_BUILTINS if machine == 0xA641 else set())
            if machine == 0xAA64:
                names |= stage.WOW64_REQUIRED_BUILTINS
            for name in names:
                self.pe(self.source / farm / name, machine)
        for directory in ("legal", "nls"):
            path = self.source / directory / "fixture"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"resource")
        self.guest = self.root / "WindowsVR"
        for relative, machine in (("Guest/x64/OpenComposite/bin/vrclient_x64.dll", 0x8664),
                                  ("Guest/x64/wvr_openxr.dll", 0x8664),
                                  ("Guest/x86/OpenComposite/bin/vrclient.dll", 0x14C),
                                  ("Guest/x86/wvr_openxr.dll", 0x14C)):
            self.pe(self.guest / relative, machine)

    def pe(self, path, machine):
        data = bytearray(512)
        data[:2] = b"MZ"
        data[0x3C:0x40] = (0x40).to_bytes(4, "little")
        data[0x40:0x44] = b"PE\0\0"
        data[0x44:0x46] = machine.to_bytes(2, "little")
        data[0x54:0x56] = (240).to_bytes(2, "little")
        data[0x58:0x5A] = (0x10B if machine == 0x14C else 0x20B).to_bytes(2, "little")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_default_ignores_unused_source_farm_but_rejects_copying_x86_guests(self):
        (self.source / "i386-windows/kernel32.dll").write_bytes(b"unused unvalidated source")
        stage.validate_wine_resources(self.source)
        self.assertFalse(any(name.startswith("i386-windows/") for name in receipt.guest_resource_files(self.source)))
        target = self.root / "default-stage"
        target.mkdir()
        stage.copy_builtins(self.source, target)
        self.assertFalse((target / "i386-windows").exists())
        with self.assertRaisesRegex(SystemExit, "requires --enable-x86"):
            stage.validate_guest_tree(self.guest)

    def test_opt_in_copies_and_hashes_complete_i386_farm(self):
        stage.validate_wine_resources(self.source, True)
        stage.validate_guest_tree(self.guest, True)
        self.pe(self.source / "i386-windows/codec.acm", 0x14C)
        self.pe(self.source / "i386-windows/notepad.exe", 0x14C)
        (self.source / "i386-windows/stdole2.tlb").write_bytes(b"type library data")
        stage.validate_wine_resources(self.source, True)
        target = self.root / "staged"
        target.mkdir()
        stage.copy_builtins(self.source, target, True)
        self.assertEqual(receipt.guest_resource_files(target, True), receipt.guest_resource_files(self.source, True))
        self.assertIn("i386-windows/kernel32.dll", receipt.guest_resource_files(target, True))
        (target / "i386-windows/kernel32.dll").write_bytes(b"changed")
        with self.assertRaisesRegex(SystemExit, "i386 PE"):
            receipt.guest_resource_files(target, True)

    def test_opt_in_rejects_missing_core_and_wrong_machine(self):
        path = self.source / "i386-windows/kernel32.dll"
        path.unlink()
        with self.assertRaisesRegex(SystemExit, "missing required files"):
            stage.validate_wine_resources(self.source, True)
        self.pe(path, 0x8664)
        with self.assertRaisesRegex(SystemExit, "i386 PE"):
            stage.validate_wine_resources(self.source, True)
        self.pe(path, 0x14C)

    def test_guest_pair_rejects_incomplete_and_mismatched_architecture(self):
        path = self.guest / "Guest/x86/wvr_openxr.dll"
        path.unlink()
        with self.assertRaisesRegex(SystemExit, "regular file"):
            stage.validate_guest_tree(self.guest, True)
        self.pe(path, 0x8664)
        with self.assertRaisesRegex(SystemExit, "i386 PE"):
            stage.validate_guest_tree(self.guest, True)
        path.write_bytes(b"not a PE")
        with self.assertRaisesRegex(SystemExit, "i386 PE"):
            stage.validate_guest_tree(self.guest, True)

    def test_wow64_receipt_binds_actual_arm64_build_bytes(self):
        built = self.pe(self.root / "runtime/FEX/build-wow64/Bin/libwow64fex.dll", 0xAA64)
        packaged = self.pe(self.source / "aarch64-windows/xtajit.dll", 0xAA64)
        result = receipt.fex_wow64_build(self.root / "runtime", self.source)
        self.assertEqual(result["sha256"], receipt.sha256_file(built))
        packaged.write_bytes(packaged.read_bytes() + b"stale")
        with self.assertRaisesRegex(SystemExit, "differs"):
            receipt.fex_wow64_build(self.root / "runtime", self.source)
        self.pe(packaged, 0x14C)
        with self.assertRaisesRegex(SystemExit, "ARM64 PE"):
            receipt.fex_wow64_build(self.root / "runtime", self.source)

    def test_modern_native_dxmt_profile_cannot_be_mixed_with_wow64(self):
        marker = self.root / "runtime/AVPPLAY_D3D12_SOURCE_PROVENANCE.json"
        marker.parent.mkdir()
        marker.write_text("{}")
        with self.assertRaisesRegex(SystemExit, "legacy Madeira"):
            receipt.fex_wow64_build(self.root / "runtime", self.source)
        marker.unlink()
        native = self.root / "runtime/build/ntdll-unix/virtual_ios.c"
        native.parent.mkdir(parents=True)
        native.write_text("#define WVR_DXMT_D3D12_PROFILE 1\n")
        with self.assertRaisesRegex(SystemExit, "legacy Madeira"):
            receipt.fex_wow64_build(self.root / "runtime", self.source)

    def test_i386_imports_cover_guest_bridges_and_export_forwarders(self):
        core = self.source / "i386-windows/kernel32.dll"
        bridge = self.guest / "Guest/x86/wvr_openxr.dll"
        tools = {"llvm-readobj": "readobj", "llvm-objdump": "objdump"}
        def inspect(command, **kwargs):
            if command[0] == "readobj":
                return "  Name: KERNEL32.dll\n  Name: missing-delay.dll\n" if command[-1] == str(bridge) else ""
            return "  Export forwarded (forwarded to absent.Function)" if command[-1] == str(core) else ""
        with patch.object(imports.subprocess, "check_output", side_effect=inspect):
            missing = imports.inspect_closure([core], tools, [bridge], "i386", True)
        self.assertEqual(missing, {"absent.dll": ["kernel32.dll"], "missing-delay.dll": ["wvr_openxr.dll"]})
        self.pe(bridge, 0x8664)
        with patch.object(imports.subprocess, "check_output", return_value=""):
            with self.assertRaisesRegex(ValueError, "expected i386"):
                imports.inspect_closure([core], tools, [bridge], "i386", True)

    def test_guest_shared_cxx_and_duplicate_module_are_rejected(self):
        bridge = self.guest / "Guest/x86/wvr_openxr.dll"
        tools = {"llvm-readobj": "readobj", "llvm-objdump": "objdump"}
        with patch.object(imports.subprocess, "check_output", return_value="  Name: libc++.dll\n"):
            with self.assertRaisesRegex(ValueError, r"shared C\+\+"):
                imports.inspect_closure([], tools, [bridge], "i386", True)
        with patch.object(imports.subprocess, "check_output", return_value=""):
            with self.assertRaisesRegex(ValueError, "duplicate/case-colliding"):
                imports.inspect_closure([bridge], tools, [bridge], "i386", True)


class SourcePinTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git(self.source, "init", "--quiet")
        (self.source / "source.c").write_text("original\n")
        self.commit(self.source)
        self.revision = self.git(self.source, "rev-parse", "HEAD")

    def git(self, source, *args):
        return subprocess.check_output([
            "git", "-c", "user.name=Offline Fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always",
            "-C", str(source), *args], text=True, stderr=subprocess.PIPE).strip()

    def commit(self, source):
        self.git(source, "add", ".")
        self.git(source, "commit", "--quiet", "-m", "fixture")

    def test_clean_pin_is_accepted_and_wrong_revision_rejected(self):
        verify_source_checkout(self.source, self.revision)
        with self.assertRaisesRegex(SystemExit, "revision"):
            verify_source_checkout(self.source, "0" * 40)

    def test_tracked_and_untracked_source_changes_rejected(self):
        (self.source / "source.c").write_text("modified\n")
        with self.assertRaisesRegex(SystemExit, "local or submodule changes"):
            verify_source_checkout(self.source, self.revision)
        self.git(self.source, "checkout", "--", "source.c")
        (self.source / "new.c").write_text("untracked\n")
        with self.assertRaisesRegex(SystemExit, "local or submodule changes"):
            verify_source_checkout(self.source, self.revision)

    def test_dirty_wrong_revision_and_uninitialized_submodules_rejected(self):
        dependency = self.root / "dependency"
        dependency.mkdir()
        self.git(dependency, "init", "--quiet")
        (dependency / "dep.c").write_text("original\n")
        self.commit(dependency)
        self.git(self.source, "submodule", "add", "--quiet", str(dependency), "dependency")
        self.commit(self.source)
        revision = self.git(self.source, "rev-parse", "HEAD")
        verify_source_checkout(self.source, revision)
        submodule = self.source / "dependency"
        (submodule / "dep.c").write_text("modified\n")
        with self.assertRaises(SystemExit): verify_source_checkout(self.source, revision)
        self.commit(submodule)
        with self.assertRaises(SystemExit): verify_source_checkout(self.source, revision)
        self.git(self.source, "submodule", "deinit", "--force", "dependency")
        with self.assertRaisesRegex(SystemExit, "uninitialized"):
            verify_source_checkout(self.source, revision)


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.path = Path(self.scratch.name) / "synthetic.dll"

    def image(self, machine=0x8664, metadata_version=None, metadata_va=None):
        # A header-only PE fixture: one data section and no executable code.
        data = bytearray(0x800)
        def number(offset, value, width):
            data[offset:offset + width] = value.to_bytes(width, "little")
        data[:2] = b"MZ"
        number(0x3C, 0x40, 4)
        data[0x40:0x44] = b"PE\0\0"
        number(0x44, machine, 2)
        number(0x46, 1, 2)
        number(0x54, 240, 2)
        optional = 0x58
        number(optional, 0x20B, 2)
        number(optional + 24, 0x180000000, 8)
        number(optional + 56, 0x2000, 4)
        number(optional + 60, 0x400, 4)
        number(optional + 108, 16, 4)
        section = optional + 240
        number(section + 8, 0x400, 4)
        number(section + 12, 0x1000, 4)
        number(section + 16, 0x400, 4)
        number(section + 20, 0x400, 4)
        if metadata_version is not None:
            number(optional + 112 + 10 * 8, 0x1000, 4)
            number(optional + 116 + 10 * 8, 0xD0, 4)
            number(0x400, 0xD0, 4)
            number(0x400 + 0xC8, metadata_va if metadata_va is not None else 0x180001200, 8)
            number(0x600, metadata_version, 4)
        self.path.write_bytes(data)

    def test_plain_x64_and_raw_arm64ec_are_distinguished(self):
        self.image()
        self.assertEqual(stage.pe_machine(self.path), 0x8664)
        self.assertFalse(stage.is_arm64ec_pe(self.path))
        self.image(machine=0xA641)
        self.assertTrue(stage.is_arm64ec_pe(self.path))

    def test_amd64_with_valid_chpe_is_arm64ec_not_plain_x64(self):
        for version in (1, 2):
            self.image(metadata_version=version)
            self.assertEqual(stage.pe_machine(self.path), 0x8664)
            self.assertTrue(stage.is_arm64ec_pe(self.path))
            self.assertFalse(stage._is_x64_pe(self.path))

    def test_invalid_or_unmapped_chpe_metadata_is_not_accepted(self):
        self.image(metadata_version=3)
        self.assertFalse(stage.is_arm64ec_pe(self.path))
        self.image(metadata_version=1, metadata_va=0x180002000)
        self.assertFalse(stage.is_arm64ec_pe(self.path))


if __name__ == "__main__":
    unittest.main()
