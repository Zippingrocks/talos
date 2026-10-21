import json
import tempfile
import unittest
from pathlib import Path

from talos.t5_catalog import T5CatalogError, _fingerprint, build_catalog
from tests.test_hermes_adapter import write_bundle


class T5CatalogTests(unittest.TestCase):
    def test_fingerprint_ignores_serialized_pointer_values_and_link_encoding(self):
        nodes = [
            {"id": 0, "kind": "struct", "type_index": 0, "type_name": "Root", "chunks": [
                {"index": 0, "data_offset": 0, "data_bytes": 4, "links": [
                    {"offset": 0, "kind": "inline", "target": {"node": 1, "chunk": 0, "offset": 0}}
                ]}
            ]},
            {"id": 1, "kind": "string", "chunks": [
                {"index": 0, "data_offset": 4, "data_bytes": 2, "links": []}
            ]},
        ]
        first = {"graph": {"nodes": nodes}}
        second = json.loads(json.dumps(first))
        second["graph"]["nodes"][0]["chunks"][0]["links"][0]["kind"] = "ref"
        self.assertEqual(
            _fingerprint(first, b"\xff\xff\xff\xffx\0", 0, {}),
            _fingerprint(second, b"\x11\x22\x33\x44x\0", 0, {}),
        )

    def test_fingerprint_canonicalizes_zone_local_script_string_indices(self):
        document = {"graph": {"nodes": [{
            "id": 0, "kind": "scalar", "chunks": [
                {"index": 0, "data_offset": 0, "data_bytes": 2, "links": []}
            ],
        }]}}
        rules = {(0, 0): [(0, 2, 1)]}
        first = _fingerprint(
            document, b"\x01\x00", 0, {}, script_rules=rules,
            script_strings=[None, "tag_weapon"],
        )
        same = _fingerprint(
            document, b"\x02\x00", 0, {}, script_rules=rules,
            script_strings=[None, "other", "tag_weapon"],
        )
        different = _fingerprint(
            document, b"\x01\x00", 0, {}, script_rules=rules,
            script_strings=[None, "tag_origin"],
        )
        self.assertEqual(first, same)
        self.assertNotEqual(first, different)

    def test_identical_assets_across_zones_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first", root / "second"
            write_bundle(first, source_file="first.ff")
            write_bundle(second, source_file="second.ff")
            output = root / "catalog.json"
            report = build_catalog([first, second], output)
            document = json.loads(output.read_text())
            self.assertEqual(report["duplicate_identities"], 1)
            self.assertEqual(report["conflicting_identities"], 0)
            self.assertEqual(document["assets"][0]["status"], "identical_duplicate")
            with self.assertRaisesRegex(T5CatalogError, "already exists"):
                build_catalog([first], output)

    def test_same_identity_with_different_graph_is_a_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first", root / "second"
            write_bundle(first, source_file="first.ff")
            write_bundle(second, source_file="second.ff")
            graph = bytearray((second / "graph.bin").read_bytes())
            graph[-1] ^= 1
            (second / "graph.bin").write_bytes(graph)
            output = root / "catalog.json"
            report = build_catalog([first, second], output)
            self.assertEqual(report["conflicting_identities"], 1)
            document = json.loads(output.read_text())
            self.assertEqual(document["conflicts"][0]["name"], "maps/example.gsc")


if __name__ == "__main__":
    unittest.main()
