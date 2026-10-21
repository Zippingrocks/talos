import json
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from talos.hermes_adapter import HermesAdapterError, decode_with_hermes, validate_bundle


def write_bundle(path: Path, *, source_file: str = "map.ff", source_bytes: int = 12) -> None:
    path.mkdir()
    graph = bytes(20)
    (path / "graph.bin").write_bytes(graph)
    layout = b'{"game":"T5"}'
    (path / "t5-layout.json").write_bytes(layout)
    manifest = {
        "schema": "hermes_t5_zone_graph",
        "schema_version": 1,
        "source_game": "black_ops_1",
        "source_profile": "pc_unsigned_iwffu100_v473",
        "source_file": source_file,
        "fastfile": {
            "magic": "IWffu100",
            "version": 473,
            "file_bytes": source_bytes,
            "padding_bytes": 0,
            "decompressed_zone_bytes": 64,
        },
        "xfile": {"declared_zone_size": 64, "external_size": 0, "block_sizes": {}},
        "walk": {
            "stream_bytes_consumed": 64,
            "block_used": {},
            "unlinked_back_references": 0,
            "complete": True,
        },
        "layout": {"file": "t5-layout.json", "bytes": len(layout)},
        "graph_data": {"file": "graph.bin", "bytes": len(graph)},
        "script_strings": [None, "tag_origin"],
        "assets": [
            {
                "index": 0,
                "type_index": 36,
                "type_name": "rawfile",
                "struct_name": "RawFile",
                "root_node": 1,
                "name": "maps/example.gsc",
                "reachable_nodes": 1,
                "dependency_asset_indices": [],
            }
        ],
        "graph": {
            "external_size": 0,
            "script_strings_node": None,
            "asset_table_node": 0,
            "nodes": [
                {
                    "id": 0,
                    "kind": "asset_table",
                    "chunks": [
                        {
                            "index": 0,
                            "data_offset": 0,
                            "data_bytes": 8,
                            "links": [
                                {
                                    "offset": 4,
                                    "kind": "inline",
                                    "target": {"node": 1, "chunk": 0, "offset": 0},
                                }
                            ],
                        }
                    ],
                },
                {
                    "id": 1,
                    "kind": "struct",
                    "type_index": 100,
                    "type_name": "RawFile",
                    "chunks": [
                        {"index": 0, "data_offset": 8, "data_bytes": 12, "links": []}
                    ],
                },
            ],
        },
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class HermesBundleTests(unittest.TestCase):
    def test_validates_lossless_graph_extents_links_and_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            write_bundle(bundle)
            document, inventory = validate_bundle(bundle)
            self.assertEqual(document["assets"][0]["name"], "maps/example.gsc")
            self.assertEqual(inventory["assets"], 1)
            self.assertEqual(inventory["asset_types"], {"rawfile": 1})
            self.assertEqual(inventory["nodes"], 2)
            self.assertEqual(inventory["links"], 1)
            self.assertEqual(inventory["graph_bytes"], 20)

    def test_rejects_a_pointer_outside_the_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            write_bundle(bundle)
            path = bundle / "manifest.json"
            manifest = json.loads(path.read_text())
            manifest["graph"]["nodes"][0]["chunks"][0]["links"][0]["target"]["node"] = 9
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(HermesAdapterError, "outside"):
                validate_bundle(bundle)

    def test_decode_invokes_hermes_validates_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "map.ff"
            source.write_bytes(b"IWffu100" + struct.pack("<I", 473))
            hermes = root / "hermes.exe"
            hermes.write_bytes(b"fixture")
            output = root / "decoded"

            def fake_run(command, **kwargs):
                self.assertEqual(command[1], "export-talos")
                write_bundle(Path(command[-1]), source_file=source.name, source_bytes=source.stat().st_size)
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch("talos.hermes_adapter.subprocess.run", side_effect=fake_run):
                report = decode_with_hermes(source, hermes, output)
            self.assertEqual(report["status"], "source_decoded")
            self.assertEqual(report["source_inventory"]["assets"], 1)
            self.assertTrue((output / "report.json").is_file())
            with self.assertRaisesRegex(HermesAdapterError, "already exists"):
                decode_with_hermes(source, hermes, output)


if __name__ == "__main__":
    unittest.main()
