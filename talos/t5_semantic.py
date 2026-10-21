"""Lift a validated Hermes allocation graph into a typed, versioned T5 asset IR.

The allocation graph remains the lossless binary authority.  This module adds the
meaning needed by converters: typed allocations, field values, pointer ownership,
asset identities, and explicit byte-coverage accounting.  It never guesses a
member when the embedded T5 layout cannot prove one.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .hermes_adapter import GRAPH_DATA, LAYOUT, validate_bundle
from .io_utils import json_text, write_new_file


SCHEMA = "talos_t5_semantic_ir"
SCHEMA_VERSION = 1


class T5SemanticError(ValueError):
    """The graph is valid but cannot be lifted under the declared T5 layout."""


_PRIMITIVES: dict[tuple[str, int], str] = {
    ("char", 1): "b",
    ("signed char", 1): "b",
    ("byte", 1): "B",
    ("unsigned char", 1): "B",
    ("short", 2): "h",
    ("unsigned short", 2): "H",
    ("int", 4): "i",
    ("unsigned int", 4): "I",
    ("uint", 4): "I",
    ("long", 4): "i",
    ("unsigned long", 4): "I",
    ("float", 4): "f",
    ("double", 8): "d",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise T5SemanticError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise T5SemanticError(f"{path.name} must contain a JSON object")
    return value


def _finite(value: float) -> float | str:
    if math.isfinite(value):
        return value
    if math.isnan(value):
        return "nan"
    return "inf" if value > 0 else "-inf"


def _primitive_value(data: bytes, tname: str, size: int) -> int | float | str | None:
    code = _PRIMITIVES.get((tname, size))
    if code is None or len(data) != size:
        return None
    value = struct.unpack("<" + code, data)[0]
    return _finite(value) if isinstance(value, float) else value


def _fixed_array_count(member: dict[str, Any]) -> int | None:
    count = 1
    for modifier in member.get("mods", []):
        if "p" in modifier:
            return None
        amount = modifier.get("a")
        if not isinstance(amount, int) or amount < 0:
            return None
        count *= amount
    return count


def _field_value(data: bytes, member: dict[str, Any]) -> tuple[bool, Any]:
    """Decode only layout-proven scalar leaves; retain everything else by reference."""
    count = _fixed_array_count(member)
    sizes = member.get("sizes", [])
    if count is None or not sizes or not isinstance(sizes[0], int):
        return False, None
    total = sizes[0]
    if total < 0 or len(data) != total or count == 0:
        return False, None
    if member.get("type") is not None:
        return False, None
    if total % count:
        return False, None
    element_size = total // count
    values = [
        _primitive_value(data[i * element_size : (i + 1) * element_size], member.get("tname", ""), element_size)
        for i in range(count)
    ]
    if any(value is None for value in values):
        return False, None
    return True, values[0] if count == 1 else values


def _member_for_offset(layout_type: dict[str, Any], offset: int) -> dict[str, Any] | None:
    matches = []
    for member in layout_type.get("members", []):
        start = member.get("offset")
        sizes = member.get("sizes", [])
        if isinstance(start, int) and sizes and isinstance(sizes[0], int):
            if start <= offset < start + sizes[0]:
                matches.append(member)
    # Unions can intentionally provide several interpretations.  Do not guess.
    return matches[0] if len(matches) == 1 else None


def _inline_elements(
    document: dict[str, Any],
    graph: bytes,
    types: list[dict[str, Any]],
    member: dict[str, Any],
    raw: bytes,
    absolute_offset: int,
    links: dict[int, dict[str, Any]],
    depth: int = 0,
) -> dict[str, Any] | None:
    type_index = member.get("type")
    count = _fixed_array_count(member)
    if not isinstance(type_index, int) or count is None:
        return None
    if type_index >= len(types) or depth >= 64:
        raise T5SemanticError("embedded T5 structure nesting is invalid")
    layout_type = types[type_index]
    size = layout_type.get("size")
    if not isinstance(size, int) or size < 0 or len(raw) != size * count:
        return None
    elements = []
    for element_index in range(count):
        element_data = raw[element_index * size : (element_index + 1) * size]
        element_base = absolute_offset + element_index * size
        fields = []
        for child in layout_type.get("members", []):
            offset = child.get("offset")
            sizes = child.get("sizes", [])
            if not isinstance(offset, int) or not sizes or not isinstance(sizes[0], int):
                continue
            child_size = sizes[0]
            child_raw = element_data[offset : offset + child_size]
            decoded, value = _field_value(child_raw, child)
            entry: dict[str, Any] = {
                "name": child.get("name", ""),
                "offset": offset,
                "absolute_offset": element_base + offset,
                "bytes": child_size,
                "base_type": child.get("tname"),
                "type_index": child.get("type"),
                "modifiers": child.get("mods", []),
                "raw_hex": child_raw.hex(),
                "value_status": "decoded" if decoded else "retained_raw",
            }
            if decoded:
                entry["value"] = value
            link = links.get(element_base + offset)
            if link is not None:
                entry["link"] = link
                target = _target(link)
                if child.get("string") and target is not None:
                    string_data = _node_bytes(document, graph, target["node"], target["chunk"])
                    text = _decode_c_string(string_data[target["offset"] :])
                    entry["string"] = text
                    entry["string_encoding"] = "utf-8" if text is not None else "binary"
            nested = _inline_elements(
                document,
                graph,
                types,
                child,
                child_raw,
                element_base + offset,
                links,
                depth + 1,
            )
            if nested is not None:
                entry["inline"] = nested
            fields.append(entry)
        elements.append({"index": element_index, "fields": fields})
    return {
        "type_index": type_index,
        "type_name": layout_type.get("name"),
        "union": bool(layout_type.get("union")),
        "elements": elements,
    }


def _target(link: dict[str, Any]) -> dict[str, int] | None:
    target = link.get("target")
    return target if isinstance(target, dict) else None


def _node_bytes(document: dict[str, Any], graph: bytes, node_id: int, chunk_id: int = 0) -> bytes:
    chunk = document["graph"]["nodes"][node_id]["chunks"][chunk_id]
    start, size = chunk["data_offset"], chunk["data_bytes"]
    return graph[start : start + size]


def _decode_c_string(data: bytes) -> str | None:
    value = data.split(b"\0", 1)[0]
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _root_fields(
    document: dict[str, Any],
    graph: bytes,
    types: list[dict[str, Any]],
    layout_type: dict[str, Any],
    node_id: int,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    node = document["graph"]["nodes"][node_id]
    if not node["chunks"]:
        raise T5SemanticError(f"root node {node_id} has no chunks")
    data = _node_bytes(document, graph, node_id)
    declared_size = layout_type.get("size")
    if not isinstance(declared_size, int) or len(data) < declared_size:
        raise T5SemanticError(
            f"root node {node_id} has {len(data)} bytes, smaller than {layout_type.get('name')} size {declared_size}"
        )
    links = {link["offset"]: link for link in node["chunks"][0]["links"]}
    fields = []
    used_ranges: dict[int, dict[str, Any]] = {}
    for member in layout_type.get("members", []):
        offset = member.get("offset")
        sizes = member.get("sizes", [])
        if not isinstance(offset, int) or not sizes or not isinstance(sizes[0], int):
            continue
        size = sizes[0]
        raw = data[offset : offset + size]
        decoded, value = _field_value(raw, member)
        entry: dict[str, Any] = {
            "name": member.get("name", ""),
            "offset": offset,
            "bytes": size,
            "base_type": member.get("tname"),
            "type_index": member.get("type"),
            "modifiers": member.get("mods", []),
            "raw_hex": raw.hex(),
            "value_status": "decoded" if decoded else "retained_raw",
        }
        if decoded:
            entry["value"] = value
        link = links.get(offset)
        if link is not None:
            entry["link"] = link
            target = _target(link)
            if member.get("string") and target is not None:
                string_data = _node_bytes(document, graph, target["node"], target["chunk"])
                text = _decode_c_string(string_data[target["offset"] :])
                entry["string"] = text
                entry["string_encoding"] = "utf-8" if text is not None else "binary"
        nested = _inline_elements(document, graph, types, member, raw, offset, links)
        if nested is not None:
            entry["inline"] = nested
        fields.append(entry)
        for byte_offset in range(offset, min(offset + size, declared_size)):
            used_ranges[byte_offset] = entry
    return fields, used_ranges


def _field(fields: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for field in fields:
        if field["name"] == name:
            return field
    raise T5SemanticError(f"T5 layout is missing required member {name}")


def _linked_bytes(document: dict[str, Any], graph: bytes, field: dict[str, Any]) -> bytes | None:
    link = field.get("link")
    target = _target(link) if isinstance(link, dict) else None
    if target is None:
        return None
    data = _node_bytes(document, graph, target["node"], target["chunk"])
    return data[target["offset"] :]


def _payload(data: bytes, expected: int | None = None, *, textual: bool = False) -> dict[str, Any]:
    if expected is not None:
        if expected < 0 or expected > len(data):
            raise T5SemanticError(
                f"linked payload has {len(data)} bytes but its T5 extent requires {expected}"
            )
        data = data[:expected]
    result: dict[str, Any] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if textual:
        value = data[:-1] if data.endswith(b"\0") else data
        try:
            result["text"] = value.decode("utf-8")
            result["encoding"] = "utf-8"
        except UnicodeDecodeError:
            result["encoding"] = "binary"
    return result


def _entity_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        if text[index] in "{}":
            tokens.append(text[index])
            index += 1
            continue
        if text[index] != '"':
            raise T5SemanticError(f"MapEnts contains an unquoted token at character {index}")
        index += 1
        value = []
        while index < len(text) and text[index] != '"':
            value.append(text[index])
            index += 1
        if index >= len(text):
            raise T5SemanticError("MapEnts contains an unterminated quoted string")
        index += 1
        tokens.append("".join(value))
    return tokens


def _entities(text: str) -> list[list[list[str]]]:
    tokens = _entity_tokens(text)
    result: list[list[list[str]]] = []
    index = 0
    while index < len(tokens):
        if tokens[index] != "{":
            raise T5SemanticError("MapEnts entity does not begin with an opening brace")
        index += 1
        pairs: list[list[str]] = []
        while index < len(tokens) and tokens[index] != "}":
            # A quoted value may itself be "{" or "}".  Token position, not
            # token spelling, distinguishes it from the structural delimiter.
            if index + 1 >= len(tokens):
                raise T5SemanticError("MapEnts entity has an incomplete key/value pair")
            pairs.append([tokens[index], tokens[index + 1]])
            index += 2
        if index >= len(tokens):
            raise T5SemanticError("MapEnts entity has no closing brace")
        index += 1
        result.append(pairs)
    return result


def _string_table(
    document: dict[str, Any], graph: bytes, fields: list[dict[str, Any]]
) -> dict[str, Any]:
    columns = _field(fields, "columnCount").get("value")
    rows = _field(fields, "rowCount").get("value")
    if not isinstance(columns, int) or not isinstance(rows, int) or columns < 0 or rows < 0:
        raise T5SemanticError("StringTable dimensions are not valid non-negative integers")
    count = columns * rows
    values_field = _field(fields, "values")
    link = values_field.get("link")
    target = _target(link) if isinstance(link, dict) else None
    if target is None:
        if count:
            raise T5SemanticError("non-empty StringTable has no values allocation")
        cells = []
    else:
        node = document["graph"]["nodes"][target["node"]]
        chunk = node["chunks"][target["chunk"]]
        raw = _node_bytes(document, graph, target["node"], target["chunk"])[target["offset"] :]
        required = count * 8
        if len(raw) < required:
            raise T5SemanticError("StringTable values allocation is truncated")
        links = {item["offset"] - target["offset"]: item for item in chunk["links"]}
        cells = []
        for cell_index in range(count):
            offset = cell_index * 8
            cell_link = links.get(offset)
            cell_target = _target(cell_link) if cell_link is not None else None
            text = None
            encoding = "null"
            if cell_target is not None:
                string_data = _node_bytes(
                    document, graph, cell_target["node"], cell_target["chunk"]
                )[cell_target["offset"] :]
                text = _decode_c_string(string_data)
                encoding = "utf-8" if text is not None else "binary"
            cells.append(
                {
                    "row": cell_index // columns if columns else 0,
                    "column": cell_index % columns if columns else 0,
                    "string": text,
                    "encoding": encoding,
                    "hash": struct.unpack_from("<i", raw, offset + 4)[0],
                }
            )
    index_data = _linked_bytes(document, graph, _field(fields, "cellIndex"))
    indices = None
    if index_data is not None:
        required = count * 2
        if len(index_data) < required:
            raise T5SemanticError("StringTable cell index allocation is truncated")
        indices = list(struct.unpack_from(f"<{count}h", index_data)) if count else []
    return {"kind": "string_table", "columns": columns, "rows": rows, "cells": cells, "cell_index": indices}


def _script_string(document: dict[str, Any], index: int) -> str | None:
    strings = document["script_strings"]
    if index < 0 or index >= len(strings):
        raise T5SemanticError(f"script string index {index} is outside the zone string table")
    value = strings[index]
    if value is not None and not isinstance(value, str):
        raise T5SemanticError(f"script string index {index} is not text or null")
    return value


def _script_string_array(
    document: dict[str, Any], graph: bytes, field: dict[str, Any], count: int
) -> list[dict[str, Any]]:
    data = _linked_bytes(document, graph, field)
    if data is None:
        if count:
            raise T5SemanticError(f"{field['name']} has {count} script strings but no allocation")
        return []
    if len(data) < count * 2:
        raise T5SemanticError(f"{field['name']} script string array is truncated")
    result = []
    for position in range(count):
        index = struct.unpack_from("<H", data, position * 2)[0]
        result.append({"index": index, "string": _script_string(document, index)})
    return result


def _specialization(
    document: dict[str, Any], graph: bytes, struct_name: str, fields: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if struct_name == "RawFile":
        length = _field(fields, "len").get("value")
        if not isinstance(length, int) or length < 0:
            raise T5SemanticError("RawFile length is not a non-negative integer")
        data = _linked_bytes(document, graph, _field(fields, "buffer"))
        return {
            "kind": "raw_file",
            "length": length,
            "payload": None if data is None else _payload(data, length + 1, textual=True),
        }
    if struct_name == "MapEnts":
        length = _field(fields, "numEntityChars").get("value")
        if not isinstance(length, int) or length < 0:
            raise T5SemanticError("MapEnts length is not a non-negative integer")
        data = _linked_bytes(document, graph, _field(fields, "entityString"))
        payload = None if data is None else _payload(data, length, textual=True)
        result: dict[str, Any] = {"kind": "map_entities", "length": length, "payload": payload}
        if payload is not None and payload.get("encoding") == "utf-8":
            result["entities"] = _entities(payload["text"])
        return result
    if struct_name == "StringTable":
        return _string_table(document, graph, fields)
    if struct_name == "LoadedSound":
        sound = _field(fields, "sound").get("inline")
        if not isinstance(sound, dict) or not sound.get("elements"):
            raise T5SemanticError("LoadedSound has no inline snd_asset metadata")
        metadata_fields = sound["elements"][0]["fields"]
        data_size = _field(metadata_fields, "data_size").get("value")
        if not isinstance(data_size, int) or data_size < 0:
            raise T5SemanticError("LoadedSound data size is invalid")
        data = _linked_bytes(document, graph, _field(metadata_fields, "data"))
        metadata = {
            name: _field(metadata_fields, name).get("value")
            for name in (
                "version", "frame_count", "frame_rate", "channel_count", "header_size",
                "block_size", "buffer_size", "format", "channel_flags", "flags",
                "seek_table_count", "data_size",
            )
        }
        return {
            "kind": "loaded_sound",
            "name": _field(fields, "name").get("string"),
            "metadata": metadata,
            "payload": None if data is None else _payload(data, data_size),
        }
    if struct_name == "PrimedSound":
        size = _field(fields, "size").get("value")
        if not isinstance(size, int) or size < 0:
            raise T5SemanticError("PrimedSound size is invalid")
        data = _linked_bytes(document, graph, _field(fields, "buffer"))
        return {
            "kind": "primed_sound",
            "name": _field(fields, "name").get("string"),
            "payload": None if data is None else _payload(data, size),
        }
    if struct_name == "StreamedSound":
        return {
            "kind": "streamed_sound",
            "filename": _field(fields, "filename").get("string"),
            "primed_sound_link": _field(fields, "primeSnd").get("link"),
        }
    if struct_name == "XModel":
        count = _field(fields, "numBones").get("value")
        if not isinstance(count, int) or count < 0:
            raise T5SemanticError("XModel numBones is invalid")
        return {
            "kind": "xmodel",
            "bone_names": _script_string_array(
                document, graph, _field(fields, "boneNames"), count
            ),
        }
    if struct_name == "XAnimParts":
        counts = _field(fields, "boneCount").get("value")
        notify_count = _field(fields, "notifyCount").get("value")
        if not isinstance(counts, list) or len(counts) <= 9 or not isinstance(counts[9], int):
            raise T5SemanticError("XAnimParts boneCount[9] is invalid")
        if not isinstance(notify_count, int) or notify_count < 0:
            raise T5SemanticError("XAnimParts notifyCount is invalid")
        notify_data = _linked_bytes(document, graph, _field(fields, "notify"))
        notifications = []
        if notify_data is None:
            if notify_count:
                raise T5SemanticError("XAnimParts notifications have no allocation")
        else:
            if len(notify_data) < notify_count * 8:
                raise T5SemanticError("XAnimParts notification array is truncated")
            for position in range(notify_count):
                index = struct.unpack_from("<H", notify_data, position * 8)[0]
                notifications.append(
                    {
                        "index": index,
                        "name": _script_string(document, index),
                        "time": _finite(struct.unpack_from("<f", notify_data, position * 8 + 4)[0]),
                    }
                )
        return {
            "kind": "xanim",
            "bone_names": _script_string_array(
                document, graph, _field(fields, "names"), counts[9]
            ),
            "notifications": notifications,
        }
    return None


def _typed_nodes(
    document: dict[str, Any], layout: dict[str, Any], graph: bytes
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    types = layout["types"]
    result = []
    coverage = {"typed_nodes": 0, "opaque_nodes": 0, "typed_bytes": 0, "opaque_bytes": 0}
    for node in document["graph"]["nodes"]:
        kind = node["kind"]
        chunks = node["chunks"]
        total = sum(chunk["data_bytes"] for chunk in chunks)
        entry: dict[str, Any] = {
            "id": node["id"],
            "kind": kind,
            "type_name": node.get("type_name"),
            "type_index": node.get("type_index"),
            "chunks": [
                {
                    "index": chunk["index"],
                    "data_offset": chunk["data_offset"],
                    "data_bytes": chunk["data_bytes"],
                    "links": chunk["links"],
                }
                for chunk in chunks
            ],
        }
        if kind == "struct":
            type_index = node.get("type_index")
            if not isinstance(type_index, int) or type_index >= len(types):
                raise T5SemanticError(f"node {node['id']} has invalid T5 type index")
            size = types[type_index]["size"]
            entry["element_bytes"] = size
            entry["chunk_element_counts"] = [
                chunk["data_bytes"] // size if size and chunk["data_bytes"] % size == 0 else None
                for chunk in chunks
            ]
            # Some semantic map data is embedded under another root (notably MapEnts
            # inside clipMap_t).  Promote it wherever the graph proves its type.
            semantic_node_types = {
                "MapEnts", "LoadedSound", "PrimedSound", "StreamedSound",
                "SoundFile", "snd_alias_t", "snd_alias_list_t",
            }
            if types[type_index]["name"] in semantic_node_types and chunks and chunks[0]["data_bytes"] >= size:
                fields, _ = _root_fields(document, graph, types, types[type_index], node["id"])
                entry["fields"] = fields
                entry["semantic"] = _specialization(
                    document, graph, types[type_index]["name"], fields
                )
            coverage["typed_nodes"] += 1
            coverage["typed_bytes"] += total
        elif kind == "scalar":
            size = node.get("element_bytes")
            entry["element_bytes"] = size
            entry["chunk_element_counts"] = [
                chunk["data_bytes"] // size if size and chunk["data_bytes"] % size == 0 else None
                for chunk in chunks
            ]
            coverage["typed_nodes"] += 1
            coverage["typed_bytes"] += total
        elif kind == "string":
            entry["encoding"] = "nul_terminated_bytes"
            coverage["typed_nodes"] += 1
            coverage["typed_bytes"] += total
        else:
            coverage["opaque_nodes"] += 1
            coverage["opaque_bytes"] += total
        result.append(entry)
    return result, coverage


def _loaded_asset_records(
    document: dict[str, Any], layout: dict[str, Any], graph: bytes
) -> list[dict[str, Any]]:
    types = layout["types"]
    result = []
    for source in document["loaded_assets"]:
        root = source["root_node"]
        if root is None:
            raise T5SemanticError(f"loaded asset {source['index']} has no graph allocation")
        node = document["graph"]["nodes"][root]
        type_index = node.get("type_index")
        if node.get("kind") != "struct" or not isinstance(type_index, int):
            raise T5SemanticError(f"loaded asset {source['index']} root is not a typed struct")
        layout_type = types[type_index]
        if layout_type.get("name") != source["struct_name"]:
            raise T5SemanticError(f"loaded asset {source['index']} root type disagrees with its manifest")
        fields, covered = _root_fields(document, graph, types, layout_type, root)
        record = dict(source)
        record["root"] = {
            "layout_type_index": type_index,
            "layout_type_name": layout_type["name"],
            "declared_bytes": layout_type["size"],
            "fields": fields,
            "field_covered_bytes": len(covered),
            "uncovered_byte_offsets": [
                offset for offset in range(layout_type["size"]) if offset not in covered
            ],
        }
        specialized = _specialization(document, graph, layout_type["name"], fields)
        if specialized is not None:
            record["semantic"] = specialized
        result.append(record)
    return result


def _walk_fields(fields: list[dict[str, Any]]):
    for field in fields:
        yield field
        inline = field.get("inline")
        if isinstance(inline, dict):
            for element in inline.get("elements", []):
                yield from _walk_fields(element.get("fields", []))


def _asset_field_coverage(assets: list[dict[str, Any]]) -> dict[str, Any]:
    total: Counter[str] = Counter()
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    for asset in assets:
        root = asset["root"]
        counters = Counter(
            {
                "assets": 1,
                "declared_root_bytes": root["declared_bytes"],
                "covered_root_bytes": root["field_covered_bytes"],
                "padding_root_bytes": len(root["uncovered_byte_offsets"]),
            }
        )
        for field in _walk_fields(root["fields"]):
            counters["field_instances"] += 1
            counters["decoded_values" if field["value_status"] == "decoded" else "retained_raw_values"] += 1
            if "link" in field:
                counters["linked_fields"] += 1
            if "inline" in field:
                counters["inline_structures"] += 1
        total.update(counters)
        by_type[asset["type_name"]].update(counters)
    return {
        "all_loaded_assets": dict(sorted(total.items())),
        "by_type": {name: dict(sorted(values.items())) for name, values in sorted(by_type.items())},
    }


def lift_bundle(bundle: Path, output: Path) -> dict[str, Any]:
    """Create a new semantic index from a validated Hermes/Talos source bundle."""
    bundle, output = Path(bundle), Path(output)
    if output.exists():
        raise T5SemanticError(f"output already exists: {output}")
    document, inventory = validate_bundle(bundle)
    layout = _read_json(bundle / LAYOUT)
    if layout.get("game") != "T5" or not isinstance(layout.get("types"), list):
        raise T5SemanticError("embedded layout is not a T5 type specification")
    graph = (bundle / GRAPH_DATA).read_bytes()
    typed_nodes, coverage = _typed_nodes(document, layout, graph)
    loaded_assets = _loaded_asset_records(document, layout, graph)
    field_coverage = _asset_field_coverage(loaded_assets)
    types = layout["types"]
    assets = []
    for asset in document["assets"]:
        root = asset.get("root_node")
        record = {
            "index": asset["index"],
            "type_index": asset["type_index"],
            "type_name": asset["type_name"],
            "struct_name": asset.get("struct_name"),
            "name": asset.get("name"),
            "root_node": root,
            "dependency_asset_indices": asset["dependency_asset_indices"],
            "reachable_nodes": asset["reachable_nodes"],
            "status": "typed" if root is not None and asset.get("struct_name") else "reference_only",
        }
        if root is not None and asset.get("struct_name"):
            node = document["graph"]["nodes"][root]
            type_index = node.get("type_index")
            if node.get("kind") != "struct" or not isinstance(type_index, int):
                raise T5SemanticError(f"asset {asset['index']} root is not a typed struct")
            layout_type = types[type_index]
            if layout_type.get("name") != asset["struct_name"]:
                raise T5SemanticError(f"asset {asset['index']} root type disagrees with its manifest")
            fields, covered = _root_fields(document, graph, types, layout_type, root)
            record["root"] = {
                "layout_type_index": type_index,
                "layout_type_name": layout_type["name"],
                "declared_bytes": layout_type["size"],
                "fields": fields,
                "field_covered_bytes": len(covered),
                "uncovered_byte_offsets": [
                    offset for offset in range(layout_type["size"]) if offset not in covered
                ],
            }
            specialized = _specialization(document, graph, layout_type["name"], fields)
            if specialized is not None:
                record["semantic"] = specialized
        assets.append(record)

    result = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "schema": document["schema"],
            "schema_version": document["schema_version"],
            "game": document["source_game"],
            "profile": document["source_profile"],
            "file": document["source_file"],
            "graph_sha256": hashlib.sha256(graph).hexdigest(),
        },
        "contract": {
            "binary_authority": GRAPH_DATA,
            "layout_authority": LAYOUT,
            "endianness": "little",
            "pointer_bytes": 4,
            "uninterpreted_data_policy": "retained_by_exact_graph_reference",
            "target_game_data": False,
        },
        "inventory": inventory,
        "coverage": coverage,
        "semantic_member_coverage": field_coverage,
        "assets": assets,
        "loaded_assets": loaded_assets,
        "nodes": typed_nodes,
    }
    write_new_file(output, json_text(result).encode("utf-8"))
    return {
        "status": "t5_semantic_ir_written",
        "output": str(output),
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "assets": len(assets),
        "coverage": coverage,
        "semantic_member_coverage": field_coverage["all_loaded_assets"],
    }
