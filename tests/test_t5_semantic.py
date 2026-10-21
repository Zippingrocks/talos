import json
import struct
import tempfile
import unittest
from pathlib import Path

from talos.t5_semantic import (
    T5SemanticError,
    _entities,
    _inline_elements,
    _script_string_array,
    lift_bundle,
)
from tests.test_hermes_adapter import write_bundle


class T5SemanticTests(unittest.TestCase):
    def test_lifts_declared_pack_index_without_retail_fixture(self):
        """T5 declares PackIndex, although sampled PC retail zones do not instantiate it."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            write_bundle(bundle)
            layout_path = bundle / "t5-layout.json"
            layout = json.loads(layout_path.read_text())
            scalar = lambda name, offset: {
                "name": name, "offset": offset, "sizes": [4], "type": None,
                "tname": "unsigned int", "mods": [], "string": False,
            }
            layout["types"] = [
                {
                    "name": "PackIndexHeader", "size": 20,
                    "members": [scalar("magic", 0), scalar("timestamp", 4),
                                scalar("count", 8), scalar("alignment", 12),
                                scalar("data_start", 16)],
                },
                {
                    "name": "PackIndexEntry", "size": 12,
                    "members": [scalar("hash", 0), scalar("offset", 4), scalar("size", 8)],
                },
                {
                    "name": "PackIndex", "size": 28,
                    "members": [
                        {"name": "name", "offset": 0, "sizes": [4, 1], "type": None,
                         "tname": "char", "mods": [{"p": None}], "string": True},
                        {"name": "header", "offset": 4, "sizes": [20], "type": 0,
                         "tname": "PackIndexHeader", "mods": [], "string": False},
                        {"name": "entries", "offset": 24, "sizes": [4, 12], "type": 1,
                         "tname": "PackIndexEntry", "mods": [{"p": {"v": {"off": 8}}}],
                         "string": False},
                    ],
                },
            ]
            layout_path.write_text(json.dumps(layout))
            graph = bytes(8) + struct.pack("<IIIIIII", 0, 0x5041434B, 7, 0, 16, 32, 0)
            (bundle / "graph.bin").write_bytes(graph)
            manifest_path = bundle / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["layout"]["bytes"] = layout_path.stat().st_size
            manifest["graph_data"]["bytes"] = len(graph)
            manifest["assets"][0].update(
                {"type_index": 38, "type_name": "packindex", "struct_name": "PackIndex",
                 "name": "fixture", "reachable_nodes": 1}
            )
            manifest["loaded_assets"][0].update(
                {"type_name": "PackIndex", "struct_name": "PackIndex", "name": "fixture",
                 "stream_end": 28}
            )
            manifest["graph"]["nodes"][1].update(
                {"type_index": 2, "type_name": "PackIndex",
                 "chunks": [{"index": 0, "data_offset": 8, "data_bytes": 28, "links": []}]}
            )
            manifest_path.write_text(json.dumps(manifest))
            output = root / "semantic.json"
            lift_bundle(bundle, output)
            result = json.loads(output.read_text())
            fields = {field["name"]: field for field in result["assets"][0]["root"]["fields"]}
            header_fields = fields["header"]["inline"]["elements"][0]["fields"]
            self.assertEqual(header_fields[0]["value"], 0x5041434B)
            self.assertEqual(header_fields[1]["value"], 7)

    def test_script_string_arrays_resolve_zone_local_indices(self):
        document = {
            "script_strings": [None, "tag_weapon"],
            "graph": {"nodes": [{"chunks": [
                {"data_offset": 0, "data_bytes": 2, "links": []}
            ]}]},
        }
        field = {
            "name": "boneNames",
            "link": {"kind": "inline", "target": {"node": 0, "chunk": 0, "offset": 0}},
        }
        self.assertEqual(
            _script_string_array(document, b"\x01\x00", field, 1),
            [{"index": 1, "string": "tag_weapon"}],
        )
        with self.assertRaisesRegex(T5SemanticError, "outside"):
            _script_string_array(document, b"\x02\x00", field, 1)

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
