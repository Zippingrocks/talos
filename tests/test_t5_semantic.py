import json
import struct
import tempfile
import unittest
from pathlib import Path

from talos.t5_semantic import T5SemanticError, _entities, _inline_elements, lift_bundle
from tests.test_hermes_adapter import write_bundle


class T5SemanticTests(unittest.TestCase):
    def test_recursively_decodes_inline_struct_arrays(self):
        types = [
            {"name": "Pair", "size": 4, "union": False, "members": [
                {"name": "x", "offset": 0, "sizes": [2], "type": None,
                 "tname": "short", "mods": []},
                {"name": "y", "offset": 2, "sizes": [2], "type": None,
                 "tname": "short", "mods": []},
            ]}
        ]
        member = {"type": 0, "tname": "Pair", "mods": [{"a": 2}], "sizes": [8]}
        decoded = _inline_elements({}, b"", types, member, struct.pack("<hhhh", 1, 2, 3, 4), 12, {})
        self.assertEqual(decoded["elements"][0]["fields"][0]["value"], 1)
        self.assertEqual(decoded["elements"][1]["fields"][1]["value"], 4)
        self.assertEqual(decoded["elements"][1]["fields"][0]["absolute_offset"], 16)

    def test_map_entities_preserve_order_duplicates_and_backslashes(self):
        parsed = _entities('{\n"classname" "worldspawn"\n"path" "a\\\\b"\n}\n')
        self.assertEqual(parsed, [[["classname", "worldspawn"], ["path", "a\\\\b"]]])
        with self.assertRaisesRegex(T5SemanticError, "closing brace"):
            _entities('{ "classname" "worldspawn"')

    def test_lifts_root_fields_and_accounts_for_every_graph_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            write_bundle(bundle)
            graph_path = bundle / "graph.bin"
            graph = bytearray(graph_path.read_bytes())
            graph[12:16] = struct.pack("<i", 1234)
            graph_path.write_bytes(graph)
            output = root / "semantic.json"

            report = lift_bundle(bundle, output)
            result = json.loads(output.read_text())

            self.assertEqual(report["status"], "t5_semantic_ir_written")
            self.assertEqual(result["schema"], "talos_t5_semantic_ir")
            self.assertEqual(result["assets"][0]["status"], "typed")
            fields = {field["name"]: field for field in result["assets"][0]["root"]["fields"]}
            self.assertEqual(fields["len"]["value"], 1234)
            self.assertEqual(fields["name"]["value_status"], "retained_raw")
            coverage = result["coverage"]
            self.assertEqual(coverage["typed_bytes"] + coverage["opaque_bytes"], 20)

    def test_accepts_decoded_bundle_report_but_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            write_bundle(bundle)
            (bundle / "report.json").write_text("{}")
            output = root / "semantic.json"
            lift_bundle(bundle, output)
            with self.assertRaisesRegex(T5SemanticError, "already exists"):
                lift_bundle(bundle, output)


if __name__ == "__main__":
    unittest.main()
