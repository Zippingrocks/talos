"""Validate Talos map IR and emit the supported BO3 Radiant ``iwmap 4`` subset.

This module writes source .map text, not a T7 fastfile or a playable BO3 project.
It preserves ordered brush-plane points, both six-number texture records, and
entity properties. It does not translate shaders, create assets, remap entity
classes, rebuild lighting, prove brush closure, or invoke the BO3 tools.

Syntax was checked against original public BO3 map source:
  https://github.com/kelson8/bo3-Zombies-Test-Map/blob/b20ca20b1b043276b6797513f51ffb10c77faea2/prefabs/stairs1.map
  blob: 0ad2052f7b09dcc31b707747b63eb878afb065df
and the author's BO3-capable converter source:
  https://github.com/KILLTUBE/corvid/blob/99b9ff7f47704725aee850d3936e20b565e613a0/modules/CoDMap/Face.py
  https://github.com/KILLTUBE/corvid/blob/99b9ff7f47704725aee850d3936e20b565e613a0/modules/CoDMap/Map.py
These establish ``iwmap 4`` and the face syntax, including the two six-number
records. No third-party source or map geometry is copied into this module.

The six-number records are deliberately positional. We preserve supplied values
instead of inventing the meaning of undocumented flags. GUIDs are optional and
preserved when supplied. Unknown IR members (including patches and models),
unsupported string escapes, non-finite numbers and degenerate planes are errors.
An entity's external ``model`` property can be serialized as a reference; that
does not convert or validate the referenced model asset.

The numeric and size caps below are Talos input-validation policies, NOT claimed
BO3 engine limits. Acceptance by Radiant/the official compiler remains untested.
"""

from __future__ import annotations

from decimal import Decimal
import math
import re
from typing import Any


SCHEMA_VERSION = 1
MAX_ABS_NUMBER = 1_000_000_000
MAX_STRING_LENGTH = 16_384
_MAP_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_MATERIAL = re.compile(r"[A-Za-z0-9_$][A-Za-z0-9_./$-]*\Z")
_UUID = re.compile(
    r"(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\Z"
)


class MapValidationError(ValueError):
    """A map contains invalid or currently unsupported source data."""


def _fail(path: str, reason: str) -> None:
    raise MapValidationError(f"{path}: {reason}")


def _object(
    value: Any, path: str, required: set[str], optional: set[str] | None = None
) -> dict:
    if not isinstance(value, dict):
        _fail(path, "expected an object")
    if any(not isinstance(key, str) for key in value):
        _fail(path, "object keys must be strings")
    allowed = required | (optional or set())
    extra = set(value) - allowed
    if extra:
        _fail(path, f"unsupported fields: {', '.join(sorted(extra))}")
    missing = required - set(value)
    if missing:
        _fail(path, f"missing fields: {', '.join(sorted(missing))}")
    return value


def _array(value: Any, path: str, length: int | None = None) -> list:
    if not isinstance(value, list):
        _fail(path, "expected an array")
    if length is not None and len(value) != length:
        _fail(path, f"expected exactly {length} values")
    return value


def _number(value: Any, path: str) -> int | float:
    if type(value) not in (int, float):
        _fail(path, "expected an integer or float, not a boolean or string")
    if isinstance(value, float) and not math.isfinite(value):
        _fail(path, "number must be finite")
    if abs(value) > MAX_ABS_NUMBER:
        _fail(path, f"number exceeds Talos policy bound +/-{MAX_ABS_NUMBER}")
    return value


def _string(value: Any, path: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str):
        _fail(path, "expected a string")
    if nonempty and not value:
        _fail(path, "string must not be empty")
    if len(value) > MAX_STRING_LENGTH:
        _fail(path, f"string exceeds Talos policy length {MAX_STRING_LENGTH}")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        _fail(path, "control characters are unsupported")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        _fail(path, "unpaired Unicode surrogates cannot be written as UTF-8")
    if '"' in value or "\\" in value:
        _fail(path, "quoted-string escapes are not supported")
    return value


def _material(value: Any, path: str) -> str:
    name = _string(value, path, nonempty=True)
    if not _MATERIAL.fullmatch(name) or "//" in name:
        _fail(path, "expected one unquoted material token")
    return name


def _guid(value: Any, path: str) -> str:
    if not isinstance(value, str):
        _fail(path, "GUID must be a string")
    raw = value[1:-1] if value.startswith("{") and value.endswith("}") else value
    if not _UUID.fullmatch(raw):
        _fail(path, "expected a UUID, optionally enclosed in braces")
    return "{" + raw + "}"


def _mapping(value: Any, path: str) -> None:
    for index, number in enumerate(_array(value, path, 6)):
        _number(number, f"{path}[{index}]")


def _face(value: Any, path: str) -> None:
    face = _object(value, path, {"points", "material", "texture", "lightmap"})
    points = _array(face["points"], f"{path}.points", 3)
    for point_index, point in enumerate(points):
        for axis, coordinate in enumerate(
            _array(point, f"{path}.points[{point_index}]", 3)
        ):
            _number(coordinate, f"{path}.points[{point_index}][{axis}]")

    # Preserve winding exactly. A triplet defines a plane, not necessarily three
    # vertices on the final clipped polygon, so no polygon containment is assumed.
    edge_a = [points[1][i] - points[0][i] for i in range(3)]
    edge_b = [points[2][i] - points[0][i] for i in range(3)]
    normal = [
        edge_a[1] * edge_b[2] - edge_a[2] * edge_b[1],
        edge_a[2] * edge_b[0] - edge_a[0] * edge_b[2],
        edge_a[0] * edge_b[1] - edge_a[1] * edge_b[0],
    ]
    if math.hypot(*normal) == 0:
        _fail(f"{path}.points", "degenerate plane: coincident or collinear points")

    _material(face["material"], f"{path}.material")
    _mapping(face["texture"], f"{path}.texture")
    lightmap = _object(face["lightmap"], f"{path}.lightmap", {"material", "texture"})
    _material(lightmap["material"], f"{path}.lightmap.material")
    _mapping(lightmap["texture"], f"{path}.lightmap.texture")


def validate_map(document: dict) -> None:
    """Check supported IR without mutating it; raise with a precise member path.

    The required root members are schema_version=1, source_game='bo1',
    target_game='bo3', map_name, and entities. Each entity has properties and
    brushes, each brush has faces, and GUIDs are optional on either. A face has
    three ordered points, material, a six-number texture array, and lightmap
    containing its own material and six-number texture array.

    Validation checks safe serialization and nondegenerate individual planes.
    It does not prove a brush is bounded/convex or an entity/material exists in
    BO3. The caller must account for target dependencies and semantic mappings.
    """
    doc = _object(
        document,
        "map",
        {"schema_version", "source_game", "target_game", "map_name", "entities"},
    )
    if type(doc["schema_version"]) is not int or doc["schema_version"] != SCHEMA_VERSION:
        _fail("map.schema_version", f"expected {SCHEMA_VERSION}")
    if doc["source_game"] != "bo1":
        _fail("map.source_game", "expected 'bo1'")
    if doc["target_game"] != "bo3":
        _fail("map.target_game", "expected 'bo3'")
    if not isinstance(doc["map_name"], str) or not _MAP_NAME.fullmatch(doc["map_name"]):
        _fail("map.map_name", "expected a 1-64 character lowercase ASCII identifier starting with a letter")

    entities = _array(doc["entities"], "map.entities")
    if not entities:
        _fail("map.entities", "at least one entity (worldspawn) is required")
    for entity_index, value in enumerate(entities):
        path = f"map.entities[{entity_index}]"
        entity = _object(value, path, {"properties", "brushes"}, {"guid"})
        if "guid" in entity:
            _guid(entity["guid"], f"{path}.guid")
        properties = entity["properties"]
        if not isinstance(properties, dict):
            _fail(f"{path}.properties", "expected a string-to-string object")
        for key, value in properties.items():
            _string(key, f"{path}.properties key", nonempty=True)
            _string(value, f"{path}.properties[{key!r}]")
        classname = properties.get("classname")
        if not isinstance(classname, str) or not classname.strip():
            _fail(f"{path}.properties.classname", "a nonempty classname is required")
        if classname.lower().startswith("misc_prefab") or properties.get("model", "").lower().endswith(".map"):
            _fail(f"{path}.properties", "prefab references require expansion and are not supported")
        if entity_index == 0 and classname != "worldspawn":
            _fail(f"{path}.properties.classname", "first entity must be worldspawn")
        if entity_index > 0 and classname == "worldspawn":
            _fail(f"{path}.properties.classname", "worldspawn must occur exactly once")

        for brush_index, value in enumerate(_array(entity["brushes"], f"{path}.brushes")):
            brush_path = f"{path}.brushes[{brush_index}]"
            brush = _object(value, brush_path, {"faces"}, {"guid"})
            if "guid" in brush:
                _guid(brush["guid"], f"{brush_path}.guid")
            faces = _array(brush["faces"], f"{brush_path}.faces")
            if len(faces) < 4:
                _fail(f"{brush_path}.faces", "a solid brush needs at least four planes")
            for face_index, face in enumerate(faces):
                _face(face, f"{brush_path}.faces[{face_index}]")


def _format_number(value: int | float) -> str:
    # Decimal expansion avoids assuming the target accepts exponent notation.
    # str(float) is Python's shortest round-trippable representation.
    if value == 0:
        return "0"
    if isinstance(value, int):
        return str(value)
    result = format(Decimal(str(value)), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def _numbers(values: list) -> str:
    return " ".join(_format_number(value) for value in values)


def render_map(document: dict) -> str:
    """Return deterministic BO3-oriented ``iwmap 4`` source, or raise.

    No file is created and no default properties, materials or texture values
    are inserted. Entity/brush/face order and face point winding are preserved.
    Property keys are sorted for repeatable output, with classname first.
    """
    validate_map(document)
    lines = ["iwmap 4"]
    for entity_index, entity in enumerate(document["entities"]):
        lines.extend([f"// entity {entity_index}", "{"])
        if "guid" in entity:
            lines.append(f'guid "{_guid(entity["guid"], "guid")}"')
        properties = entity["properties"]
        for key in sorted(properties, key=lambda key: (key != "classname", key)):
            lines.append(f'"{key}" "{properties[key]}"')
        for brush_index, brush in enumerate(entity["brushes"]):
            lines.extend([f"// brush {brush_index}", "{"])
            if "guid" in brush:
                lines.append(f' guid "{_guid(brush["guid"], "guid")}"')
            for face in brush["faces"]:
                points = " ".join(f"( {_numbers(point)} )" for point in face["points"])
                lightmap = face["lightmap"]
                lines.append(
                    f' {points} {face["material"]} {_numbers(face["texture"])} '
                    f'{lightmap["material"]} {_numbers(lightmap["texture"])}'
                )
            lines.append("}")
        lines.append("}")
    return "\n".join(lines) + "\n"
