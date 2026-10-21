"""Build a deterministic, conflict-detecting catalog across decoded T5 zones."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .hermes_adapter import GRAPH_DATA, validate_bundle
from .io_utils import json_text, write_new_file


SCHEMA = "talos_t5_asset_catalog"
SCHEMA_VERSION = 1


class T5CatalogError(ValueError):
    """Decoded zones cannot form an unambiguous source asset catalog."""


def _fingerprint(
    document: dict[str, Any],
    graph: bytes,
    root: int,
    cache: dict[int, str],
    active: set[int] | None = None,
) -> str:
    """Merkle-hash a graph closure independent of bundle-local node numbering."""
    if root in cache:
        return cache[root]
    if active is None:
        active = set()
    nodes = document["graph"]["nodes"]
    node = nodes[root]
    if root in active:
        # Cycles are represented by target semantics, never by local node number.
        marker = {
            "cycle": True,
            "kind": node["kind"],
            "type_index": node.get("type_index"),
            "type_name": node.get("type_name"),
        }
        return hashlib.sha256(
            json.dumps(marker, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    active.add(root)
    digest = hashlib.sha256()
    identity = {
        "kind": node["kind"],
        "type_index": node.get("type_index"),
        "type_name": node.get("type_name"),
        "element_bytes": node.get("element_bytes"),
        "chunks": len(node["chunks"]),
    }
    digest.update(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode())
    for chunk in node["chunks"]:
        start, size = chunk["data_offset"], chunk["data_bytes"]
        digest.update(size.to_bytes(8, "little"))
        digest.update(graph[start : start + size])
        for link in chunk["links"]:
            target = link.get("target")
            normalized = {"offset": link["offset"], "kind": link["kind"], "target": None}
            if target is not None:
                normalized["target"] = {
                    "fingerprint": _fingerprint(
                        document, graph, target["node"], cache, active
                    ),
                    "chunk": target["chunk"],
                    "offset": target["offset"],
                }
            digest.update(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode())
    active.remove(root)
    result = digest.hexdigest()
    cache[root] = result
    return result


def build_catalog(bundles: list[Path], output: Path) -> dict[str, Any]:
    if not bundles:
        raise T5CatalogError("at least one decoded T5 bundle is required")
    output = Path(output)
    if output.exists():
        raise T5CatalogError(f"output already exists: {output}")

    sources = []
    identities: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    unnamed = []
    edge_types: defaultdict[tuple[str, str], int] = defaultdict(int)
    for source_index, bundle_value in enumerate(bundles):
        bundle = Path(bundle_value)
        document, inventory = validate_bundle(bundle)
        graph = (bundle / GRAPH_DATA).read_bytes()
        source = {
            "index": source_index,
            "bundle": str(bundle),
            "file": document["source_file"],
            "graph_sha256": hashlib.sha256(graph).hexdigest(),
            "inventory": inventory,
        }
        sources.append(source)
        loaded = document["loaded_assets"]
        fingerprints: dict[int, str] = {}
        for asset in loaded:
            root = asset["root_node"]
            if root is None:
                raise T5CatalogError(
                    f"{document['source_file']} loaded asset {asset['index']} has no graph root"
                )
            if root not in fingerprints:
                fingerprints[root] = _fingerprint(document, graph, root, fingerprints)
            fingerprint = fingerprints[root]
            root_chunks = document["graph"]["nodes"][root]["chunks"]
            occurrence = {
                "source": source_index,
                "loaded_asset_index": asset["index"],
                "root_asset_index": asset["root_asset_index"],
                "parent_loaded_asset_index": asset["parent_loaded_asset_index"],
                "depth": asset["depth"],
                "root_node": root,
                "fingerprint": fingerprint,
                "root_bytes": sum(chunk["data_bytes"] for chunk in root_chunks),
                "root_links": sum(len(chunk["links"]) for chunk in root_chunks),
            }
            name = asset["name"]
            if name is None:
                unnamed.append({"type_name": asset["type_name"], **occurrence})
            else:
                identities[(asset["type_name"], name)].append(occurrence)
            parent = asset["parent_loaded_asset_index"]
            if parent is not None:
                edge_types[(loaded[parent]["type_name"], asset["type_name"])] += 1

    records = []
    conflicts = []
    duplicates = 0
    for (type_name, name), occurrences in sorted(identities.items()):
        fingerprints = sorted({item["fingerprint"] for item in occurrences})
        status = "unique"
        if len(occurrences) > 1:
            duplicates += 1
            status = "identical_duplicate" if len(fingerprints) == 1 else "conflict"
        record = {
            "type_name": type_name,
            "name": name,
            "status": status,
            "fingerprints": fingerprints,
            "occurrences": occurrences,
        }
        records.append(record)
        if status == "conflict":
            conflicts.append({"type_name": type_name, "name": name, "fingerprints": fingerprints})

    result = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "sources": sources,
        "summary": {
            "sources": len(sources),
            "named_identities": len(records),
            "unnamed_occurrences": len(unnamed),
            "duplicate_identities": duplicates,
            "conflicting_identities": len(conflicts),
        },
        "dependency_edge_types": [
            {"parent_type": parent, "child_type": child, "count": count}
            for (parent, child), count in sorted(edge_types.items())
        ],
        "assets": records,
        "unnamed_assets": unnamed,
        "conflicts": conflicts,
    }
    write_new_file(output, json_text(result).encode("utf-8"))
    return {"status": "t5_asset_catalog_written", "output": str(output), **result["summary"]}
