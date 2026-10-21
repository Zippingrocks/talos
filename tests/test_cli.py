"""Native fastfile CLI checks using original synthetic byte streams only."""

import contextlib
import hashlib
import io
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from talos.cli import main


ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024


def make_fastfile(payload=None, *, magic=b"IWffu100", version=473):
    if payload is None:
        payload = struct.pack("<9I", *([0] * 9)) + b"synthetic serialized zone bytes"
    return magic + struct.pack("<I", version) + zlib.compress(payload)


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = main([str(arg) for arg in args])
            except SystemExit as exc:
                code = exc.code
        return code, stdout.getvalue(), stderr.getvalue()

    def test_inspect_reports_header_only_without_claiming_asset_decode(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.ff"
            data = b"IWffu100" + struct.pack("<I", 473) + b"not a zlib stream"
            source.write_bytes(data)
            code, stdout, stderr = self.run_cli("inspect", source)
            self.assertEqual(code, 0, stderr)
            report = json.loads(stdout)
            self.assertTrue(report["supported"])
            self.assertEqual(report["profile"], "bo1_pc_unsigned_473")
            self.assertEqual(report["validation"], "header_only")
            self.assertFalse(report["assets_decoded"])
            self.assertFalse(report["target_fastfile_written"])
            self.assertEqual(report["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(report["file_bytes"], len(data))
            self.assertEqual(source.read_bytes(), data)

    def test_unpack_writes_zone_and_cannot_replace_it(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            zone = struct.pack("<9I", *([0] * 9)) + b"synthetic serialized zone bytes"
            source = directory / "test.ff"
            source.write_bytes(make_fastfile(zone))
            target = directory / "nested" / "test.zone.bin"
            code, stdout, stderr = self.run_cli("unpack", source, "--output", target)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(target.read_bytes(), zone)
            report = json.loads(stdout)
            self.assertFalse(report["assets_decoded"])
            self.assertFalse(report["target_fastfile_written"])
            self.assertEqual(report["validation"], "zlib_and_xfile_header")
            self.assertEqual(report["payload_sha256"], hashlib.sha256(zone).hexdigest())
            self.assertEqual(report["output"], str(target))
            code, _, stderr = self.run_cli("unpack", source, "--output", target)
            self.assertEqual(code, 2)
            self.assertIn("error", stderr)
            self.assertEqual(target.read_bytes(), zone)

    def test_unpack_cannot_replace_its_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "test.ff"
            data = make_fastfile()
            source.write_bytes(data)
            code, _, stderr = self.run_cli("unpack", source, "--output", source)
            self.assertEqual(code, 2)
            self.assertIn("error", stderr)
            self.assertEqual(source.read_bytes(), data)

    def test_unsupported_profile_has_nonzero_inspection_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown.ff"
            path.write_bytes(b"TAff0100" + struct.pack("<I", 473) + b"unsupported")
            code, stdout, _ = self.run_cli("inspect", path)
            self.assertEqual(code, 2)
            report = json.loads(stdout)
            self.assertFalse(report["supported"])
            self.assertFalse(report["assets_decoded"])
            self.assertIsNone(report["header_bytes"])

    def test_invalid_inputs_leave_no_output_or_output_parent(self):
        good = make_fastfile()
        cases = {
            "short_header": b"IWffu100",
            "truncated_zlib": good[:-2],
            "corrupt_checksum": good[:-1] + bytes([good[-1] ^ 1]),
            "incomplete_xfile": make_fastfile(bytes(35)),
            "trailing_data": good + b"unexpected trailing bytes",
            "wrong_version": make_fastfile(version=468),
            "unknown_magic": make_fastfile(magic=b"TAff0100"),
        }
        for name, data in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                source = directory / "invalid.ff"
                source.write_bytes(data)
                target = directory / "new_output" / "zone.bin"
                code, stdout, stderr = self.run_cli("unpack", source, "--output", target)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("talos: error:", stderr)
                self.assertFalse(target.parent.exists())
                self.assertEqual(source.read_bytes(), data)

    def test_output_limit_accepts_boundary_and_rejects_oversize_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "test.ff"
            target = directory / "exact.zone.bin"
            source.write_bytes(make_fastfile(bytes(MIB)))
            code, _, stderr = self.run_cli("unpack", source, "--output", target, "--max-output-mib", "1")
            self.assertEqual(code, 0, stderr)
            self.assertEqual(target.stat().st_size, MIB)
            source.write_bytes(make_fastfile(bytes(MIB + 1)))
            rejected = directory / "oversize.zone.bin"
            code, stdout, stderr = self.run_cli("unpack", source, "--output", rejected, "--max-output-mib", "1")
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("output limit", stderr)
            self.assertFalse(rejected.exists())

    def test_input_limit_applies_to_inspection_and_unpack(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "large.ff"
            prefix = b"IWffu100" + struct.pack("<I", 473)
            source.write_bytes(prefix + bytes(MIB - len(prefix)))
            code, stdout, stderr = self.run_cli("inspect", source, "--max-input-mib", "1")
            self.assertEqual(code, 0, stderr)
            self.assertEqual(json.loads(stdout)["file_bytes"], MIB)
            with source.open("ab") as handle:
                handle.write(b"x")
            for command in ("inspect", "unpack"):
                with self.subTest(command=command):
                    target = directory / "not_created.zone.bin"
                    args = [command, source, "--max-input-mib", "1"]
                    if command == "unpack":
                        args += ["--output", target]
                    code, stdout, stderr = self.run_cli(*args)
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("input exceeds", stderr)
                    self.assertFalse(target.exists())

    def test_invalid_limits_are_clean_argument_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "test.ff"
            source.write_bytes(make_fastfile())
            for option, value in (
                ("--max-input-mib", "0"),
                ("--max-input-mib", "-1"),
                ("--max-output-mib", "0"),
                ("--max-output-mib", "-1"),
                ("--max-output-mib", "invalid"),
            ):
                with self.subTest(option=option, value=value):
                    target = directory / "not_created.zone.bin"
                    code, stdout, stderr = self.run_cli("unpack", source, "--output", target, option, value)
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, "")
                    self.assertIn("error", stderr)
                    self.assertFalse(target.exists())

    def test_missing_file_fails_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            target = directory / "new_output" / "zone.bin"
            code, stdout, stderr = self.run_cli("unpack", directory / "missing.ff", "--output", target)
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("error", stderr)
            self.assertFalse(target.parent.exists())

    def test_module_entrypoint(self):
        result = subprocess.run([sys.executable, "-m", "talos", "--version"], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Talos 0.1.0")

    def test_help_exposes_only_implemented_native_stages(self):
        code, stdout, stderr = self.run_cli("--help")
        self.assertEqual(code, 0, stderr)
        self.assertIn("inspect", stdout)
        self.assertIn("unpack", stdout)
        self.assertNotIn("convert-map", stdout)
        self.assertNotIn("import-map", stdout)
        self.assertNotIn("export-map", stdout)


if __name__ == "__main__":
    unittest.main()
