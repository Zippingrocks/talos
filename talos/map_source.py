"""Import the supported text-map subset into Talos's BO1 -> BO3 map IR.

``iwmap 4`` alone does not identify a game. ``source_game='bo1'`` records the
caller's declared source pipeline, not a property detected from the text. This
module does not extract brushes from fastfiles or claim Hermes compatibility.

The syntax is independently implemented from observable Radiant source files:
https://github.com/kelson8/bo3-Zombies-Test-Map/blob/b20ca20b1b043276b6797513f51ffb10c77faea2/prefabs/stairs1.map
Both six-number face texture records are preserved without interpreting them.
Unsupported constructs are rejected, never silently discarded.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from collections.abc import Iterator

from .numeric import parse_float_token


class MapSourceError(ValueError):
    """The source is malformed or outside the supported text-map subset."""


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    line: int
    column: int


_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\Z")
_MAX_TEXT_CHARS = 64 * 1024 * 1024  # Resource policy, not a Radiant format limit.


def _tokens(text: str) -> Iterator[_Token]:
    index = 0
    line = 1
    column = 1
    size = len(text)
    while index < size:
        char = text[index]
        if char.isspace():
            if char == "\n":
                line, column = line + 1, 1
            else:
                column += 1
            index += 1
            continue
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            if end < 0:
                break
            column += end - index
            index = end
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise MapSourceError(f"line {line}, column {column}: unterminated block comment")
            segment = text[index:end + 2]
            count = segment.count("\n")
            if count:
                line += count
                column = len(segment.rsplit("\n", 1)[1]) + 1
            else:
                column += len(segment)
            index = end + 2
            continue
        start_line, start_column = line, column
        if char in "{}()":
            index += 1
            column += 1
            yield _Token(char, char, start_line, start_column)
            continue
        if char == '"':
            index += 1
            column += 1
            value = []
            while index < size and text[index] != '"':
                char = text[index]
                if ord(char) < 32:
                    raise MapSourceError(f"line {line}, column {column}: control character in quoted string")
                if char == "\\":
                    index += 1
                    column += 1
                    if index >= size or text[index] not in ('"', "\\"):
                        raise MapSourceError(f"line {line}, column {column}: unsupported string escape (only \\\" and \\\\ are supported)")
                    char = text[index]
                value.append(char)
                index += 1
                column += 1
            if index >= size:
                raise MapSourceError(f"line {start_line}, column {start_column}: unterminated quoted string")
            index += 1
            column += 1
            yield _Token("string", "".join(value), start_line, start_column)
            continue
        start = index
        while index < size and not text[index].isspace() and text[index] not in '{}()"':
            if text.startswith("//", index) or text.startswith("/*", index):
                break
            if ord(text[index]) < 32:
                raise MapSourceError(f"line {line}, column {column}: invalid control character")
            index += 1
            column += 1
        if index == start:
            raise MapSourceError(f"line {line}, column {column}: invalid token")
        yield _Token("word", text[start:index], start_line, start_column)
    yield _Token("eof", "end of file", line, column)


class _Parser:
    def __init__(self, text: str, material_map: dict[str, str] | None):
        self.stream = iter(_tokens(text))
        self.current = next(self.stream)
        self.material_map = material_map

    def error(self, message: str) -> MapSourceError:
        return MapSourceError(f"line {self.current.line}, column {self.current.column}: {message}")

    def take(self, kind: str, value: str | None = None) -> str:
        token = self.current
        if token.kind != kind or (value is not None and token.value != value):
            expected = repr(value) if value is not None else kind
            raise self.error(f"expected {expected}, found {token.value!r}")
        if kind != "eof":
            self.current = next(self.stream)
        return token.value

    def number(self) -> int | float:
        value = self.current.value
        if self.current.kind != "word" or not _NUMBER.fullmatch(value):
            raise self.error(f"expected a finite decimal number, found {value!r}")
        self.take("word")
        try:
            result = parse_float_token(value) if any(char in value for char in ".eE") else int(value)
        except (ValueError, OverflowError) as exc:
            raise self.error(f"invalid number: {exc}") from exc
        try:
            finite = math.isfinite(result)
        except OverflowError:
            finite = False
        if not finite:
            raise self.error("non-finite numbers are unsupported")
        return result

    def face(self) -> dict:
        points = []
        for _ in range(3):
            self.take("(")
            points.append([self.number() for _ in range(3)])
            self.take(")")
        material = self.take("word")
        if self.material_map is not None:
            if material not in self.material_map:
                raise self.error(f"source material {material!r} has no explicit material mapping")
            material = self.material_map[material]
        texture = [self.number() for _ in range(6)]
        lightmap_material = self.take("word")
        lightmap_texture = [self.number() for _ in range(6)]
        return {
            "points": points,
            "material": material,
            "texture": texture,
            "lightmap": {"material": lightmap_material, "texture": lightmap_texture},
        }

    def brush(self) -> dict:
        self.take("{")
        brush = {"faces": []}
        if self.current.kind == "word" and self.current.value == "guid":
            self.take("word", "guid")
            brush["guid"] = self.take("string")
        while self.current.kind != "}":
            if self.current.kind != "(":
                raise self.error(f"unsupported brush construct {self.current.value!r}; only plane faces are supported (no patches, meshes, or flags)")
            brush["faces"].append(self.face())
        self.take("}")
        return brush

    def entity(self) -> dict:
        self.take("{")
        entity = {"properties": {}, "brushes": []}
        while self.current.kind != "}":
            if self.current.kind == "word" and self.current.value == "guid":
                if "guid" in entity:
                    raise self.error("duplicate entity guid")
                self.take("word", "guid")
                entity["guid"] = self.take("string")
            elif self.current.kind == "string":
                key = self.take("string")
                if key in entity["properties"]:
                    raise self.error(f"duplicate entity property {key!r}")
                entity["properties"][key] = self.take("string")
            elif self.current.kind == "{":
                entity["brushes"].append(self.brush())
            else:
                raise self.error(f"unsupported entity construct {self.current.value!r}")
        self.take("}")
        properties = entity["properties"]
        if properties.get("classname", "").lower().startswith("misc_prefab") or properties.get("model", "").lower().endswith(".map"):
            raise self.error("prefab references require expansion and are not supported")
        return entity

    def parse(self) -> list[dict]:
        self.take("word", "iwmap")
        self.take("word", "4")
        entities = []
        while self.current.kind != "eof":
            entities.append(self.entity())
        return entities


def parse_map(text: str, *, map_name: str, material_map: dict[str, str] | None = None) -> dict:
    """Parse supported iwmap 4 source without dropping unsupported structures.

    Passing ``material_map`` requires an explicit mapping for every *brush*
    material. Omitting it preserves names, which does not prove the materials
    exist in BO3. Lightmap names/records and entity values are preserved verbatim.
    The caller must separately account for unresolved asset dependencies.
    """
    if not isinstance(text, str):
        raise MapSourceError("source map must be text")
    if len(text) > _MAX_TEXT_CHARS:
        raise MapSourceError("source map exceeds the 64 MiB character resource limit")
    if material_map is not None:
        if not isinstance(material_map, dict) or any(not isinstance(key, str) or not isinstance(value, str) or not key or not value for key, value in material_map.items()):
            raise MapSourceError("material_map must map nonempty source material strings to nonempty target material strings")
    document = {
        "schema_version": 1,
        "source_game": "bo1",
        "target_game": "bo3",
        "map_name": map_name,
        "entities": _Parser(text.lstrip("\ufeff"), material_map).parse(),
    }
    from .radiant import MapValidationError, validate_map

    try:
        validate_map(document)
    except MapValidationError as exc:
        raise MapSourceError(str(exc)) from exc
    return document
