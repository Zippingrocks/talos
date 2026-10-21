import contextlib
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
from talos.map_source import parse_map
from talos.project import export_project, map_materials


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "synthetic_brush.map"
MATERIALS = ROOT / "examples" / "materials.json"


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main([str(arg) for arg in args])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_convert_map_preserves_geometry_and_has_honest_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "converted"
            code, stdout, stderr = self.run_cli(
                "convert-map", FIXTURE, "--name", "zm_talos_test", "--material-map", MATERIALS,
                "--output", output,
            )
            self.assertEqual(code, 0, stderr)
            report = json.loads(stdout)
            self.assertEqual(report, json.loads((output / "report.json").read_text()))
            self.assertEqual(report["status"], "source_exported")
            self.assertFalse(report["fastfile_written"])
            self.assertEqual(report["validation"]["bo3_mod_tools_compile"], "not_run")
            self.assertEqual(report["source_inventory"]["materials"], ["bo1_demo_brick"])
            self.assertEqual(report["target_inventory"]["materials"], ["caulk"])
            self.assertEqual(report["target_inventory"]["faces"], 6)
            exported = parse_map((output / "map_source/zm_talos_test.map").read_text(), map_name="zm_talos_test")
            original = parse_map(FIXTURE.read_text(), map_name="zm_talos_test")
            self.assertEqual(exported, map_materials(original, {"bo1_demo_brick": "caulk"}))

    def test_material_mapping_is_complete_and_failure_leaves_no_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            material_map = directory / "materials.json"
            material_map.write_text('{}')
            output = directory / "out"
            code, _, stderr = self.run_cli("convert-map", FIXTURE, "--name", "zm_talos", "--material-map", material_map, "--output", output)
            self.assertEqual(code, 2)
            self.assertIn("missing", stderr)
            self.assertFalse(output.exists())

    def test_export_never_overwrites_existing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("user data")
            code, _, _ = self.run_cli("convert-map", FIXTURE, "--name", "zm_talos", "--output", output)
            self.assertEqual(code, 2)
            self.assertEqual(sentinel.read_text(), "user data")
            self.assertEqual(list(output.iterdir()), [sentinel])

    def test_import_then_export_preserves_entity_properties(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            ir = directory / "map.json"
            code, _, stderr = self.run_cli("import-map", FIXTURE, "--name", "zm_talos", "--output", ir)
            self.assertEqual(code, 0, stderr)
            output = directory / "out"
            code, _, stderr = self.run_cli("export-map", ir, "--output", output)
            self.assertEqual(code, 0, stderr)
            doc = json.loads((output / "map-ir.json").read_text())
            self.assertEqual(doc["entities"][1]["properties"]["targetname"], "talos_fixture_marker")

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            mapping = directory / "mapping.json"
            mapping.write_text('{"bo1_demo_brick":"caulk","bo1_demo_brick":"clip"}')
            code, _, stderr = self.run_cli("convert-map", FIXTURE, "--name", "zm_talos", "--material-map", mapping, "--output", directory / "out")
            self.assertEqual(code, 2)
            self.assertIn("duplicate JSON key", stderr)

    def test_direct_ir_cannot_bypass_prefab_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            doc = parse_map(FIXTURE.read_text(), map_name="zm_talos")
            doc["entities"].append({"properties": {"classname": "misc_prefab", "model": "prefabs/unconverted.map"}, "brushes": []})
            source = directory / "map.json"
            source.write_text(json.dumps(doc))
            output = directory / "out"
            code, _, stderr = self.run_cli("export-map", source, "--output", output)
            self.assertEqual(code, 2)
            self.assertIn("prefab", stderr)
            self.assertFalse(output.exists())

    def test_deeply_nested_json_fails_cleanly_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "map.json"
            source.write_text("[" * 20000 + "0" + "]" * 20000)
            output = directory / "out"
            code, _, stderr = self.run_cli("export-map", source, "--output", output)
            self.assertEqual(code, 2)
            self.assertIn("depth", stderr)
            self.assertFalse(output.exists())

    def test_skybox_model_is_reported_as_unconverted_dependency(self):
        doc = parse_map(FIXTURE.read_text(), map_name="zm_talos")
        doc["entities"][0]["properties"]["skyboxmodel"] = "source_sky_model"
        with tempfile.TemporaryDirectory() as directory:
            report = export_project(doc, Path(directory) / "out", source={"kind": "test"})
            self.assertIn(
                {"entity": 0, "property": "skyboxmodel", "value": "source_sky_model"},
                report["target_inventory"]["model_references"],
            )
            self.assertEqual(report["validation"]["target_assets"], "not_verified")

    def test_direct_json_numbers_cannot_underflow_or_round_silently(self):
        for token in ("1e-500", "0.1234567890123456789012345", "NaN", "Infinity"):
            with self.subTest(token=token), tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                doc = parse_map(FIXTURE.read_text(), map_name="zm_talos")
                doc["entities"][0]["brushes"][0]["faces"][0]["texture"][2] = "TEST_NUMERIC_TOKEN"
                source = directory / "map.json"
                source.write_text(json.dumps(doc).replace('"TEST_NUMERIC_TOKEN"', token))
                output = directory / "out"
                code, _, stderr = self.run_cli("export-map", source, "--output", output)
                self.assertEqual(code, 2)
                self.assertTrue(any(word in stderr for word in ("underflow", "precision", "finite")), stderr)
                self.assertFalse(output.exists())

    def test_unpack_writes_zone_and_cannot_replace_it(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            zone = struct.pack("<9I", *([0] * 9)) + b"synthetic serialized zone bytes"
            source = directory / "test.ff"
            source.write_bytes(b"IWffu100" + struct.pack("<I", 473) + zlib.compress(zone))
            target = directory / "test.zone.bin"
            code, stdout, stderr = self.run_cli("unpack", source, "--output", target)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(target.read_bytes(), zone)
            self.assertFalse(json.loads(stdout)["assets_decoded"])
            code, _, _ = self.run_cli("unpack", source, "--output", target)
            self.assertEqual(code, 2)
            self.assertEqual(target.read_bytes(), zone)

    def test_unsupported_profile_has_nonzero_inspection_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown.ff"
            path.write_bytes(b"TAff0100" + struct.pack("<I", 473) + b"unsupported")
            code, stdout, _ = self.run_cli("inspect", path)
            self.assertEqual(code, 2)
            self.assertFalse(json.loads(stdout)["supported"])

    def test_output_is_deterministic(self):
        document = parse_map(FIXTURE.read_text(), map_name="zm_talos")
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "one", Path(directory) / "two"
            report1 = export_project(document, first, source={"kind": "test"})
            report2 = export_project(document, second, source={"kind": "test"})
            self.assertEqual(report1, report2)
            for path in ("map_source/zm_talos.map", "map-ir.json", "report.json"):
                self.assertEqual((first / path).read_bytes(), (second / path).read_bytes())

    def test_module_entrypoint(self):
        result = subprocess.run([sys.executable, "-m", "talos", "--version"], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Talos 0.1.0")


if __name__ == "__main__":
    unittest.main()
