import json
import tempfile
import unittest
from pathlib import Path

from talos.t5_catalog import T5CatalogError, build_catalog
from tests.test_hermes_adapter import write_bundle


class T5CatalogTests(unittest.TestCase):
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
