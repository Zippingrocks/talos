"""Synthetic source-output and malformed-input tests; no game assets included."""

import copy
import math
import unittest

from talos.radiant import MapValidationError, render_map, validate_map


def example_map():
    """A synthetic 64-unit cube, with inward-normal point winding."""
    planes = [
        [[0, 0, 0], [64, 0, 0], [64, 64, 0]],
        [[0, 0, 64], [64, 64, 64], [64, 0, 64]],
        [[0, 0, 0], [64, 0, 64], [64, 0, 0]],
        [[0, 64, 0], [64, 64, 0], [64, 64, 64]],
        [[0, 0, 0], [0, 64, 0], [0, 64, 64]],
        [[64, 0, 0], [64, 0, 64], [64, 64, 0]],
    ]
    return {
        "schema_version": 1,
        "source_game": "bo1",
        "target_game": "bo3",
        "map_name": "zm_talos_test",
        "entities": [
            {
                "properties": {"classname": "worldspawn", "message": "Synthetic fixture"},
                "brushes": [
                    {
                        "faces": [
                            {
                                "points": points,
                                "material": "caulk",
                                "texture": [64, 64, 0, 0, 0, 0],
                                "lightmap": {
                                    "material": "lightmap_gray",
                                    "texture": [16384, 16384, 0, 0, 0, 0],
                                },
                            }
                            for points in planes
                        ]
                    }
                ],
            },
            {
                "properties": {
                    "classname": "info_player_start",
                    "origin": "32 32 96",
                    "angles": "0 90 0",
                },
                "brushes": [],
            },
        ],
    }


class RadiantTests(unittest.TestCase):
    def test_emits_verified_face_structure_and_preserves_entities(self):
        document = example_map()
        text = render_map(document)
        self.assertTrue(text.startswith('iwmap 4\n// entity 0\n{\n"classname" "worldspawn"\n'))
        self.assertIn(
            " ( 0 0 0 ) ( 64 0 0 ) ( 64 64 0 ) caulk 64 64 0 0 0 0 "
            "lightmap_gray 16384 16384 0 0 0 0\n",
            text,
        )
        self.assertEqual(text.count("// entity "), 2)
        self.assertEqual(text.count("// brush "), 1)
        self.assertEqual(text.count("lightmap_gray"), 6)
        self.assertIn('"origin" "32 32 96"', text)
        self.assertIn('"angles" "0 90 0"', text)

    def test_texture_parameters_and_winding_are_not_reset(self):
        document = example_map()
        face = document["entities"][0]["brushes"][0]["faces"][0]
        face["texture"] = [128.5, 64, -3.25, 17, 90, 4]
        face["lightmap"]["texture"] = [8192, 4096, 5, -6, 45, 2]
        original = copy.deepcopy(document)
        text = render_map(document)
        self.assertIn(
            "( 0 0 0 ) ( 64 0 0 ) ( 64 64 0 ) caulk 128.5 64 -3.25 17 90 4 "
            "lightmap_gray 8192 4096 5 -6 45 2",
            text,
        )
        self.assertEqual(document, original)

    def test_deterministic_regardless_of_property_insertion_order(self):
        first = example_map()
        second = copy.deepcopy(first)
        for entity in second["entities"]:
            entity["properties"] = dict(reversed(list(entity["properties"].items())))
        self.assertEqual(render_map(first), render_map(second))

    def test_guid_preserved_and_optional(self):
        document = example_map()
        entity_guid = "{12345678-1234-abcd-ABCD-123456789012}"
        brush_guid = "87654321-4321-4321-4321-210987654321"
        document["entities"][0]["guid"] = entity_guid
        document["entities"][0]["brushes"][0]["guid"] = brush_guid
        text = render_map(document)
        self.assertIn(f'guid "{entity_guid}"', text)
        self.assertIn(f'guid "{{{brush_guid}}}"', text)
        self.assertNotIn("guid", render_map(example_map()))

    def test_decimal_numbers_do_not_lose_precision_or_use_exponents(self):
        document = example_map()
        face = document["entities"][0]["brushes"][0]["faces"][0]
        face["texture"] = [64.0, 64, -0.0, 1e-8, 0.12345678901234567, 0]
        text = render_map(document)
        self.assertIn("caulk 64 64 0 0.00000001 0.12345678901234566 0", text)

    def test_nonfinite_bool_and_oversized_numbers_fail_with_location(self):
        for bad in (math.nan, math.inf, -math.inf, True, "5", 1_000_000_001):
            with self.subTest(bad=bad):
                document = example_map()
                document["entities"][0]["brushes"][0]["faces"][0]["points"][0][0] = bad
                with self.assertRaisesRegex(MapValidationError, r"faces\[0\].points\[0\]\[0\]"):
                    render_map(document)

    def test_degenerate_plane_fails(self):
        for points in ([[0, 0, 0]] * 3, [[0, 0, 0], [1, 1, 1], [2, 2, 2]]):
            with self.subTest(points=points):
                document = example_map()
                document["entities"][0]["brushes"][0]["faces"][0]["points"] = points
                with self.assertRaisesRegex(MapValidationError, "degenerate plane"):
                    validate_map(document)

    def test_unknown_fields_are_never_dropped(self):
        for location, field in (("root", "models"), ("entity", "patches"), ("brush", "contents"), ("face", "smoothing")):
            with self.subTest(location=location):
                document = example_map()
                target = document
                if location != "root":
                    target = document["entities"][0]
                if location in ("brush", "face"):
                    target = target["brushes"][0]
                if location == "face":
                    target = target["faces"][0]
                target[field] = []
                with self.assertRaisesRegex(MapValidationError, "unsupported fields"):
                    render_map(document)

    def test_missing_lightmap_and_bad_texture_width_fail(self):
        document = example_map()
        del document["entities"][0]["brushes"][0]["faces"][0]["lightmap"]
        with self.assertRaisesRegex(MapValidationError, "missing fields: lightmap"):
            validate_map(document)
        document = example_map()
        document["entities"][0]["brushes"][0]["faces"][0]["texture"] = [64, 64, 0]
        with self.assertRaisesRegex(MapValidationError, "exactly 6"):
            validate_map(document)

    def test_worldspawn_and_direction_are_required(self):
        mutations = [
            lambda doc: doc.update(source_game="bo4"),
            lambda doc: doc.update(target_game="waw"),
            lambda doc: doc.update(schema_version=True),
            lambda doc: doc.update(entities=[]),
            lambda doc: doc["entities"].reverse(),
            lambda doc: doc["entities"][1]["properties"].update(classname="worldspawn"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                document = example_map()
                mutate(document)
                with self.assertRaises(MapValidationError):
                    validate_map(document)

    def test_injection_and_unsupported_escapes_fail(self):
        for bad in ('bad"value', "bad\nvalue", "bad\x00value", "bad\\value"):
            with self.subTest(bad=bad):
                document = example_map()
                document["entities"][0]["properties"]["message"] = bad
                with self.assertRaises(MapValidationError):
                    render_map(document)
        for bad in ("caulk material", "caulk//comment", "caulk\n}"):
            with self.subTest(bad=bad):
                document = example_map()
                document["entities"][0]["brushes"][0]["faces"][0]["material"] = bad
                with self.assertRaises(MapValidationError):
                    render_map(document)

    def test_invalid_guid_and_insufficient_faces_fail(self):
        document = example_map()
        document["entities"][0]["guid"] = "not-a-uuid"
        with self.assertRaisesRegex(MapValidationError, "UUID"):
            validate_map(document)
        document = example_map()
        document["entities"][0]["brushes"][0]["faces"] = document["entities"][0]["brushes"][0]["faces"][:3]
        with self.assertRaisesRegex(MapValidationError, "at least four"):
            validate_map(document)

    def test_referenced_model_is_preserved_without_claiming_conversion(self):
        document = example_map()
        document["entities"][1]["properties"].update(classname="misc_model", model="example_model")
        self.assertIn('"model" "example_model"', render_map(document))

    def test_direct_ir_rejects_unexpanded_prefab_references(self):
        for properties in (
            {"classname": "misc_prefab"},
            {"classname": "MiSc_PrEfAb_variant"},
            {"classname": "misc_model", "model": "prefabs/room.map"},
            {"classname": "misc_model", "model": "prefabs/room.MAP"},
        ):
            with self.subTest(properties=properties):
                document = example_map()
                document["entities"][1]["properties"].update(properties)
                with self.assertRaisesRegex(MapValidationError, "prefab references require expansion"):
                    render_map(document)

    def test_map_names_match_lowercase_project_filename_policy(self):
        for name in ("Zm_talos", "zm_Talos", "DEMO", "1demo", "zm-demo"):
            with self.subTest(name=name):
                document = example_map()
                document["map_name"] = name
                with self.assertRaisesRegex(MapValidationError, "map.map_name"):
                    validate_map(document)


if __name__ == "__main__":
    unittest.main()
