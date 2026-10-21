"""Validate and invoke Hermes's lossless BO1 zone-graph exporter."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from . import __version__
from .fastfile import MAGIC, VERSION, FastfileError
from .io_utils import json_text, write_new_file


SCHEMA = "hermes_t5_zone_graph"
SCHEMA_VERSION = 2
MANIFEST = "manifest.json"
GRAPH_DATA = "graph.bin"
LAYOUT = "t5-layout.json"
MAX_MANIFEST_BYTES = 512 * 1024 * 1024
MAX_LAYOUT_BYTES = 16 * 1024 * 1024


class HermesAdapterError(ValueError):
    """Hermes failed or its bundle cannot be trusted as the declared T5 graph."""


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HermesAdapterError(f"{label} must be an integer >= {minimum}")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HermesAdapterError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise HermesAdapterError(f"{label} must be an array")
    return value


def _read_json(path: Path, maximum: int) -> Any:
    size = path.stat().st_size
    if size > maximum:
        raise HermesAdapterError(f"{path.name} exceeds the {maximum}-byte validation limit")
    pairs_seen: list[str] = []

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                pairs_seen.append(key)
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HermesAdapterError(f"cannot read {path.name}: {exc}") from exc
    if pairs_seen:
        raise HermesAdapterError(f"{path.name} contains duplicate JSON key: {pairs_seen[0]}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _location(value: Any, label: str, chunks: list[list[int]]) -> None:
    value = _object(value, label)
    if set(value) != {"node", "chunk", "offset"}:
        raise HermesAdapterError(f"{label} has unknown or missing location members")
    node = _integer(value["node"], f"{label}.node")
    chunk = _integer(value["chunk"], f"{label}.chunk")
    offset = _integer(value["offset"], f"{label}.offset")
    if node >= len(chunks) or chunk >= len(chunks[node]):
        raise HermesAdapterError(f"{label} points outside the decoded graph")
    if offset > chunks[node][chunk]:
        raise HermesAdapterError(f"{label} points past its target chunk")


def validate_bundle(bundle: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a complete Hermes T5 bundle and return its document and inventory."""
    bundle = Path(bundle)
    if not bundle.is_dir():
        raise HermesAdapterError(f"Hermes bundle is not a directory: {bundle}")
    expected_files = {MANIFEST, GRAPH_DATA, LAYOUT}
    optional_files = {"report.json"}
    actual_files = {path.name for path in bundle.iterdir() if path.is_file()}
    if not expected_files.issubset(actual_files) or actual_files - expected_files - optional_files:
        raise HermesAdapterError(
            "Hermes bundle must contain "
            + ", ".join(sorted(expected_files))
            + " and only recognized Talos metadata; found "
            + (", ".join(sorted(actual_files)) or "no files")
        )
    document = _object(_read_json(bundle / MANIFEST, MAX_MANIFEST_BYTES), "manifest")
    required = {
        "schema", "schema_version", "source_game", "source_profile", "source_file",
        "fastfile", "xfile", "walk", "layout", "graph_data", "script_strings",
        "assets", "loaded_assets", "graph",
    }
    if set(document) != required:
        raise HermesAdapterError("manifest has unknown or missing top-level members")
    if document["schema"] != SCHEMA or document["schema_version"] != SCHEMA_VERSION:
        raise HermesAdapterError("unsupported Hermes T5 graph schema")
    if document["source_game"] != "black_ops_1":
        raise HermesAdapterError("Hermes bundle is not a Black Ops 1 source graph")
    if document["source_profile"] != "pc_unsigned_iwffu100_v473":
        raise HermesAdapterError("Hermes bundle has an unsupported BO1 source profile")

    fastfile = _object(document["fastfile"], "fastfile")
    if fastfile.get("magic") != MAGIC.decode("ascii") or fastfile.get("version") != VERSION:
        raise HermesAdapterError("Hermes bundle does not identify IWffu100 version 473")
    for key in ("file_bytes", "padding_bytes", "decompressed_zone_bytes"):
        _integer(fastfile.get(key), f"fastfile.{key}")

    walked = _object(document["walk"], "walk")
    if walked.get("complete") is not True:
        raise HermesAdapterError("Hermes did not consume the complete BO1 zone stream")
    if walked.get("unlinked_back_references") != 0:
        raise HermesAdapterError("Hermes left unresolved BO1 back-references")

    layout_ref = _object(document["layout"], "layout")
    graph_ref = _object(document["graph_data"], "graph_data")
    if layout_ref.get("file") != LAYOUT or graph_ref.get("file") != GRAPH_DATA:
        raise HermesAdapterError("bundle file references are not the schema-defined filenames")
    if _integer(layout_ref.get("bytes"), "layout.bytes") != (bundle / LAYOUT).stat().st_size:
        raise HermesAdapterError("T5 layout byte count does not match its file")
    graph_bytes = (bundle / GRAPH_DATA).stat().st_size
    if _integer(graph_ref.get("bytes"), "graph_data.bytes") != graph_bytes:
        raise HermesAdapterError("graph data byte count does not match graph.bin")
    layout = _object(_read_json(bundle / LAYOUT, MAX_LAYOUT_BYTES), "T5 layout")
    if layout.get("game") not in ("T5", "t5"):
        raise HermesAdapterError("layout is not Hermes's T5 specification")

    graph = _object(document["graph"], "graph")
    nodes = _array(graph.get("nodes"), "graph.nodes")
    chunk_lengths: list[list[int]] = []
    next_data_offset = 0
    allowed_kinds = {"struct", "scalar", "string", "pointers", "asset_table", "slot"}
    for node_id, raw_node in enumerate(nodes):
        node = _object(raw_node, f"graph.nodes[{node_id}]")
        if node.get("id") != node_id:
            raise HermesAdapterError("graph node IDs must be contiguous and ordered")
        if node.get("kind") not in allowed_kinds:
            raise HermesAdapterError(f"graph node {node_id} has an unsupported kind")
        chunks = _array(node.get("chunks"), f"graph.nodes[{node_id}].chunks")
        lengths = []
        for chunk_id, raw_chunk in enumerate(chunks):
            chunk = _object(raw_chunk, f"graph.nodes[{node_id}].chunks[{chunk_id}]")
            if chunk.get("index") != chunk_id:
                raise HermesAdapterError("graph chunk IDs must be contiguous and ordered")
            offset = _integer(chunk.get("data_offset"), "chunk.data_offset")
            length = _integer(chunk.get("data_bytes"), "chunk.data_bytes")
            if offset != next_data_offset:
                raise HermesAdapterError("graph chunk data must cover graph.bin contiguously")
            next_data_offset += length
            lengths.append(length)
        chunk_lengths.append(lengths)
    if next_data_offset != graph_bytes:
        raise HermesAdapterError("graph chunk extents do not cover graph.bin exactly")

    link_count = 0
    for node_id, node in enumerate(nodes):
        for chunk_id, chunk in enumerate(node["chunks"]):
            previous = -1
            for link_id, raw_link in enumerate(_array(chunk.get("links"), "chunk.links")):
                link = _object(raw_link, f"node {node_id} chunk {chunk_id} link {link_id}")
                offset = _integer(link.get("offset"), "link.offset")
                if offset <= previous or offset + 4 > chunk_lengths[node_id][chunk_id]:
                    raise HermesAdapterError("link offsets must be ordered pointer locations inside their chunk")
                previous = offset
                kind = link.get("kind")
                if kind not in {"inline", "insert", "ref", "alias_field", "alias_slot", "shared"}:
                    raise HermesAdapterError("graph link has an unsupported kind")
                target = link.get("target")
                if target is None:
                    if kind not in {"inline", "insert"}:
                        raise HermesAdapterError("only inline/insert runtime links may have a null target")
                else:
                    _location(target, "link.target", chunk_lengths)
                link_count += 1

    assets = _array(document["assets"], "assets")
    types: Counter[str] = Counter()
    for index, raw_asset in enumerate(assets):
        asset = _object(raw_asset, f"assets[{index}]")
        if asset.get("index") != index:
            raise HermesAdapterError("asset indices must be contiguous and ordered")
        _integer(asset.get("type_index"), "asset.type_index")
        if not isinstance(asset.get("type_name"), str) or not asset["type_name"]:
            raise HermesAdapterError("asset.type_name must be a non-empty string")
        types[asset["type_name"]] += 1
        root = asset.get("root_node")
        if root is not None and _integer(root, "asset.root_node") >= len(nodes):
            raise HermesAdapterError("asset root points outside the decoded graph")
        for dependency in _array(asset.get("dependency_asset_indices"), "asset dependencies"):
            if _integer(dependency, "asset dependency") >= len(assets) or dependency == index:
                raise HermesAdapterError("asset dependency index is invalid")

    loaded_assets = _array(document.get("loaded_assets"), "loaded_assets")
    loaded_types: Counter[str] = Counter()
    for index, raw_asset in enumerate(loaded_assets):
        asset = _object(raw_asset, f"loaded_assets[{index}]")
        if asset.get("index") != index:
            raise HermesAdapterError("loaded asset indices must be contiguous and ordered")
        root_index = _integer(asset.get("root_asset_index"), "loaded asset root_asset_index")
        if root_index >= len(assets):
            raise HermesAdapterError("loaded asset root index is invalid")
        depth = _integer(asset.get("depth"), "loaded asset depth")
        parent = asset.get("parent_loaded_asset_index")
        if parent is None:
            if depth != 0:
                raise HermesAdapterError("nested loaded asset has no parent")
        else:
            parent = _integer(parent, "loaded asset parent_loaded_asset_index")
            if parent >= index:
                raise HermesAdapterError("loaded asset parent must precede its child")
            parent_depth = loaded_assets[parent].get("depth")
            if not isinstance(parent_depth, int) or depth != parent_depth + 1:
                raise HermesAdapterError("loaded asset depth does not follow its parent")
        type_name = asset.get("type_name")
        if not isinstance(type_name, str) or not type_name:
            raise HermesAdapterError("loaded asset type_name must be a non-empty string")
        if asset.get("struct_name") != type_name:
            raise HermesAdapterError("loaded asset struct_name must match type_name")
        name = asset.get("name")
        if name is not None and not isinstance(name, str):
            raise HermesAdapterError("loaded asset name must be a string or null")
        root = asset.get("root_node")
        if root is not None and _integer(root, "loaded asset root_node") >= len(nodes):
            raise HermesAdapterError("loaded asset root points outside the decoded graph")
        start = _integer(asset.get("stream_start"), "loaded asset stream_start")
        end = _integer(asset.get("stream_end"), "loaded asset stream_end")
        if end < start or end > document["fastfile"]["decompressed_zone_bytes"]:
            raise HermesAdapterError("loaded asset stream extent is invalid")
        loaded_types[type_name] += 1

    return document, {
        "assets": len(assets),
        "asset_types": dict(sorted(types.items())),
        "loaded_assets": len(loaded_assets),
        "loaded_asset_types": dict(sorted(loaded_types.items())),
        "script_strings": len(_array(document["script_strings"], "script_strings")),
        "nodes": len(nodes),
        "chunks": sum(len(node["chunks"]) for node in nodes),
        "links": link_count,
        "graph_bytes": graph_bytes,
    }


def decode_with_hermes(source: Path, hermes: Path, output: Path) -> dict[str, Any]:
    """Run Hermes, validate its complete T5 graph, and publish a new Talos source bundle."""
    source, hermes, output = Path(source), Path(hermes), Path(output)
    if output.exists():
        raise HermesAdapterError(f"output already exists: {output}")
    if not source.is_file():
        raise HermesAdapterError(f"BO1 fastfile does not exist: {source}")
    if not hermes.is_file():
        raise HermesAdapterError(f"Hermes executable does not exist: {hermes}")
    with source.open("rb") as handle:
        prefix = handle.read(12)
    if len(prefix) != 12 or prefix[:8] != MAGIC or int.from_bytes(prefix[8:], "little") != VERSION:
        raise FastfileError("decode requires an unsigned PC BO1 IWffu100 version 473 fastfile")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / f".{output.name}.talos-tmp-{os.getpid()}-{uuid.uuid4().hex}"
    temporary.mkdir()
    bundle = temporary / "bundle"
    try:
        result = subprocess.run(
            [str(hermes), "export-talos", str(source), str(bundle)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise HermesAdapterError(
                f"Hermes T5 decode failed with exit code {result.returncode}"
                + (f": {detail}" if detail else "")
            )
        document, inventory = validate_bundle(bundle)
        if document["source_file"] != source.name:
            raise HermesAdapterError("Hermes source filename does not match the requested fastfile")
        if document["fastfile"]["file_bytes"] != source.stat().st_size:
            raise HermesAdapterError("Hermes source byte count does not match the requested fastfile")
        outputs = []
        for name in (MANIFEST, GRAPH_DATA, LAYOUT):
            path = bundle / name
            outputs.append({"path": name, "bytes": path.stat().st_size, "sha256": _sha256_file(path)})
        report = {
            "schema_version": 1,
            "tool": {"name": "Talos", "version": __version__},
            "status": "source_decoded",
            "direction": {"source_game": "bo1", "target_game": "bo3"},
            "source": {
                "filename": source.name,
                "bytes": source.stat().st_size,
                "sha256": _sha256_file(source),
                "profile": "bo1_pc_unsigned_473",
            },
            "decoder": {"name": "Hermes", "schema": SCHEMA, "schema_version": SCHEMA_VERSION},
            "source_inventory": inventory,
            "validation": {
                "container": "passed_by_hermes",
                "zone_walk": "complete",
                "pointer_graph": "validated",
                "t5_layout": "included",
                "t5_semantic_lift": "available_not_run",
                "bo1_to_bo3_asset_conversion": "not_run",
                "t7_zone_serialization": "not_run",
                "bo3_container_write": "not_run",
                "bo3_runtime": "not_run",
            },
            "fastfile_written": False,
            "outputs": outputs,
            "remaining_work": [
                "Lift the decoded graph with `talos lift` into versioned Talos semantic T5 IR.",
                "Convert BO1 materials, images, models, animation, audio, FX, world and collision data for BO3.",
                "Serialize converted assets into a native T7 zone with verified pointers and fixups.",
                "Write the supported BO3 container profile and validate it independently and in BO3.",
            ],
        }
        write_new_file(bundle / "report.json", json_text(report).encode("utf-8"))
        bundle.rename(output)
        return report
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
