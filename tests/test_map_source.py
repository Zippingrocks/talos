"""Original synthetic source-map fixtures; no game assets are included."""

import unittest

from talos.map_source import MapSourceError, parse_map


# A six-plane 64-unit cube, authored for this test. Points are outward wound.
CUBE_MAP = '''iwmap 4
// entity 0
{
"classname" "worldspawn"
"message" "Synthetic Talos brush"
// brush 0
{
( 0 0 64 ) ( 64 0 64 ) ( 64 64 64 ) source/stone 64 128 7 -8 15 0 lightmap_gray 16384 16384 0 0 0 0
( 64 64 0 ) ( 64 0 0 ) ( 0 0 0 ) source/stone 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0
( 0 0 0 ) ( 64 0 0 ) ( 64 0 64 ) source/stone 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0
( 64 0 0 ) ( 64 64 0 ) ( 64 64 64 ) source/stone 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0
( 64 64 0 ) ( 0 64 0 ) ( 0 64 64 ) source/stone 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0
( 0 64 0 ) ( 0 0 0 ) ( 0 0 64 ) source/stone 64 64 0 0 0 0 lightmap_gray 16384 16384 0 0 0 0
}
}
// entity 1
{
"classname" "info_player_start"
"origin" "128 128 64"
"angles" "0 90 0"
}
'''


class MapSourceTests(unittest.TestCase):
    def parse(self, text=CUBE_MAP, **kwargs):
        return parse_map(text, map_name="zm_talos_test", **kwargs)

    def test_preserves_geometry_properties_and_both_texture_records(self):
        document = self.parse()
        self.assertEqual(document["source_game"], "bo1")
        self.assertEqual(document["target_game"], "bo3")
        self.assertEqual(len(document["entities"]), 2)
        self.assertEqual(document["entities"][1]["properties"]["origin"], "128 128 64")
        faces = document["entities"][0]["brushes"][0]["faces"]
        self.assertEqual(len(faces), 6)
        self.assertEqual(faces[0]["points"], [[0, 0, 64], [64, 0, 64], [64, 64, 64]])
        self.assertEqual(faces[0]["texture"], [64, 128, 7, -8, 15, 0])
        self.assertEqual(faces[0]["lightmap"], {"material": "lightmap_gray", "texture": [16384, 16384, 0, 0, 0, 0]})

    def test_material_remap_is_complete_and_does_not_change_lightmap(self):
        document = self.parse(material_map={"source/stone": "caulk"})
        for face in document["entities"][0]["brushes"][0]["faces"]:
            self.assertEqual(face["material"], "caulk")
            self.assertEqual(face["lightmap"]["material"], "lightmap_gray")
        with self.assertRaisesRegex(MapSourceError, "no explicit material mapping"):
            self.parse(material_map={})

    def test_excess_decimal_precision_is_not_silently_rounded(self):
        source = CUBE_MAP.replace("64 128 7 -8 15 0", "64 128 0.1234567890123456789012345 -8 15 0", 1)
        with self.assertRaisesRegex(MapSourceError, "precision"):
            self.parse(source)
        source = CUBE_MAP.replace("64 128 7 -8 15 0", "64 128 0.1000 -8 15 0", 1)
        self.assertEqual(self.parse(source)["entities"][0]["brushes"][0]["faces"][0]["texture"][2], 0.1)

    def test_guid_metadata_is_preserved(self):
        entity_guid = "{11111111-2222-3333-4444-555555555555}"
        brush_guid = "{66666666-7777-8888-9999-AAAAAAAAAAAA}"
        source = CUBE_MAP.replace('"classname" "worldspawn"', f'guid "{entity_guid}"\n"classname" "worldspawn"')
        source = source.replace("// brush 0\n{", f'// brush 0\n{{\nguid "{brush_guid}"')
        result = self.parse(source)
        self.assertEqual(result["entities"][0]["guid"], entity_guid)
        self.assertEqual(result["entities"][0]["brushes"][0]["guid"], brush_guid)

    def test_comments_bom_and_windows_newlines(self):
        source = "\ufeff/* synthetic fixture */\n" + CUBE_MAP.replace("\n", "\r\n") + "// eof"
        self.assertEqual(self.parse(source), self.parse())

    def test_escaped_values_are_rejected_until_target_string_syntax_is_verified(self):
        source = CUBE_MAP.replace('"Synthetic Talos brush"', r'"say \"go\" and \\ path"')
        with self.assertRaisesRegex(MapSourceError, "quoted-string escapes are not supported"):
            self.parse(source)

    def test_render_parse_preserves_supported_data(self):
        from talos.radiant import render_map
        original = self.parse(material_map={"source/stone": "caulk"})
        self.assertEqual(self.parse(render_map(original)), original)

    def test_patch_mesh_and_flags_are_explicit_errors(self):
        for construct in ("patchDef2", "mesh", "flags ACTIVE"):
            with self.subTest(construct=construct):
                source = CUBE_MAP.replace("// brush 0\n{", "// brush 0\n{\n" + construct)
                with self.assertRaisesRegex(MapSourceError, "unsupported brush construct"):
                    self.parse(source)

    def test_prefab_reference_is_not_silently_kept(self):
        for source in (
            CUBE_MAP.replace('"info_player_start"', '"misc_prefab"'),
            CUBE_MAP.replace('"angles" "0 90 0"', '"model" "prefabs/room.map"'),
        ):
            with self.subTest(source=source[-100:]):
                with self.assertRaisesRegex(MapSourceError, "prefab references"):
                    self.parse(source)

    def test_rejects_duplicate_properties_and_guids(self):
        with self.assertRaisesRegex(MapSourceError, "duplicate entity property"):
            self.parse(CUBE_MAP.replace('"classname" "worldspawn"', '"classname" "worldspawn"\n"classname" "light"'))
        with self.assertRaisesRegex(MapSourceError, "duplicate entity guid"):
            self.parse(CUBE_MAP.replace('"classname" "worldspawn"', 'guid "first"\nguid "second"\n"classname" "worldspawn"'))

    def test_malformed_or_trailing_data_never_disappears(self):
        sources = (
            CUBE_MAP + "garbage",
            CUBE_MAP + "/* unfinished",
            CUBE_MAP.replace('"Synthetic Talos brush"', '"unterminated'),
            CUBE_MAP.replace('"Synthetic Talos brush"', '"line\\nline"'),
            CUBE_MAP.replace("iwmap 4", "iwmap 3"),
            CUBE_MAP.replace("( 0 0 64 )", "( nan 0 64 )", 1),
            CUBE_MAP.replace("( 0 0 64 )", "( 1e999 0 64 )", 1),
            CUBE_MAP.replace("( 0 0 64 )", "( " + "9" * 1000 + " 0 64 )", 1),
            CUBE_MAP.replace("( 0 0 64 )", "( 0 0 64 7 )", 1),
            CUBE_MAP.rstrip()[:-1],
        )
        for source in sources:
            with self.subTest(source=source[:50]):
                with self.assertRaises(MapSourceError):
                    self.parse(source)

    def test_semantic_validation_runs_after_parse(self):
        with self.assertRaises(MapSourceError):
            self.parse(CUBE_MAP.replace('"worldspawn"', '"light"'))
        with self.assertRaises(MapSourceError):
            self.parse(CUBE_MAP.replace("( 0 0 64 ) ( 64 0 64 ) ( 64 64 64 )", "( 0 0 0 ) ( 1 1 1 ) ( 2 2 2 )", 1))

    def test_nonzero_numeric_underflow_is_rejected_without_rejecting_zero(self):
        # A texture parameter can underflow without making a plane degenerate;
        # parsing must catch the information loss before target validation.
        for value in ("1e-500", "-1e-999"):
            with self.subTest(value=value):
                source = CUBE_MAP.replace("source/stone 64 128", f"source/stone {value} 128", 1)
                with self.assertRaisesRegex(MapSourceError, "nonzero number underflows"):
                    self.parse(source)
        for value in ("0e-500", "-0e-999", "0.0"):
            with self.subTest(value=value):
                source = CUBE_MAP.replace("source/stone 64 128", f"source/stone {value} 128", 1)
                document = self.parse(source)
                self.assertEqual(document["entities"][0]["brushes"][0]["faces"][0]["texture"][0], 0)


if __name__ == "__main__":
    unittest.main()
