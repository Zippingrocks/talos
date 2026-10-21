import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from talos.t5_payloads import T5PayloadError, index_image_payloads
from tests.test_hermes_adapter import write_bundle


def image_bundle(path: Path, name: str = "example_texture") -> None:
    write_bundle(path)
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    asset = manifest["loaded_assets"][0]
    asset["type_name"] = "GfxImage"
    asset["struct_name"] = "GfxImage"
    asset["name"] = name
    manifest_path.write_text(json.dumps(manifest))


def write_iwd(path: Path, member: str, data: bytes) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, data)


def add_streamed_sound(bundle: Path, filename: str) -> None:
    layout_path = bundle / "t5-layout.json"
    layout = json.loads(layout_path.read_text())
    layout["types"].append(
        {
            "name": "StreamedSound",
            "size": 8,
            "members": [
                {"name": "filename", "offset": 0, "sizes": [4, 1], "type": None,
                 "tname": "char", "mods": [{"p": None}], "string": True},
                {"name": "primeSnd", "offset": 4, "sizes": [4], "type": None,
                 "tname": "void", "mods": [{"p": None}], "string": False},
            ],
        }
    )
    layout_path.write_text(json.dumps(layout))
    graph_path = bundle / "graph.bin"
    graph = graph_path.read_bytes()
    sound_bytes = filename.encode() + b"\0"
    graph_path.write_bytes(graph + bytes(8) + sound_bytes)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["layout"]["bytes"] = layout_path.stat().st_size
    manifest["graph_data"]["bytes"] = graph_path.stat().st_size
    manifest["graph"]["nodes"].extend(
        [
            {
                "id": 2, "kind": "struct", "type_index": 1,
                "type_name": "StreamedSound", "chunks": [
                    {"index": 0, "data_offset": len(graph), "data_bytes": 8, "links": [
                        {"offset": 0, "kind": "inline",
                         "target": {"node": 3, "chunk": 0, "offset": 0}}
                    ]}
                ],
            },
            {
                "id": 3, "kind": "string", "chunks": [
                    {"index": 0, "data_offset": len(graph) + 8,
                     "data_bytes": len(sound_bytes), "links": []}
                ],
            },
        ]
    )
    manifest_path.write_text(json.dumps(manifest))


class T5PayloadTests(unittest.TestCase):
    def test_resolves_case_insensitively_and_hashes_iwi(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, iwds = root / "bundle", root / "main"
            image_bundle(bundle)
            iwds.mkdir()
            write_iwd(iwds / "iw_00.iwd", "Images/Example_Texture.IWI", b"payload")
            output = root / "payloads.json"
            report = index_image_payloads(bundle, iwds, output, hash_matches=True)
            document = json.loads(output.read_text())
            self.assertEqual(report["resolved"], 1)
            self.assertEqual(report["unmatched_without_special_prefix"], 0)
            self.assertEqual(document["images"][0]["status"], "resolved")
            self.assertEqual(len(document["images"][0]["candidates"][0]["sha256"]), 64)
            with self.assertRaisesRegex(T5PayloadError, "already exists"):
                index_image_payloads(bundle, iwds, output)

    def test_accepts_install_root_and_rejects_zero_archive_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, main = root / "bundle", root / "bo1" / "main"
            image_bundle(bundle)
            main.mkdir(parents=True)
            write_iwd(main / "iw_00.iwd", "images/example_texture.iwi", b"payload")
            output = root / "payloads.json"
            report = index_image_payloads(bundle, root / "bo1", output)
            document = json.loads(output.read_text())
            self.assertEqual(report["archives"], 1)
            self.assertEqual(document["iwd_root"], str(main))

            empty = root / "empty"
            empty.mkdir()
            with self.assertRaisesRegex(T5PayloadError, "no IWD archives found"):
                index_image_payloads(bundle, empty, root / "never-written.json")

    def test_reports_conflicting_duplicate_archive_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, iwds = root / "bundle", root / "main"
            image_bundle(bundle)
            iwds.mkdir()
            write_iwd(iwds / "iw_00.iwd", "images/example_texture.iwi", b"one")
            write_iwd(iwds / "iw_01.iwd", "images/example_texture.iwi", b"two")
            output = root / "payloads.json"
            report = index_image_payloads(bundle, iwds, output)
            self.assertEqual(report["conflicting_sources"], 1)
            self.assertEqual(report["resolved"], 0)

    def test_resolves_streamed_sound_filenames_from_graph_nodes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, iwds = root / "bundle", root / "main"
            image_bundle(bundle)
            add_streamed_sound(bundle, r"sound\music\example.wav")
            iwds.mkdir()
            write_iwd(iwds / "iw_00.iwd", "sound/music/example.wav", b"wave")
            output = root / "payloads.json"
            report = index_image_payloads(bundle, iwds, output)
            self.assertEqual(report["streamed_sound_identities"], 1)
            self.assertEqual(report["resolved_streamed_sounds"], 1)


if __name__ == "__main__":
    unittest.main()
