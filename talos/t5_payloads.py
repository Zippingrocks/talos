"""Resolve external BO1 image payloads referenced by decoded T5 zones."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from .hermes_adapter import GRAPH_DATA, LAYOUT, validate_bundle
from .io_utils import json_text, write_new_file
from .t5_semantic import _field, _root_fields


SCHEMA = "talos_t5_payload_index"
SCHEMA_VERSION = 1


class T5PayloadError(ValueError):
    """External T5 payload sources are missing, corrupt, or ambiguous."""


def _resolve_iwd_root(path: Path) -> tuple[Path, list[Path]]:
    """Accept either BO1's install directory or its direct IWD directory."""
    if not path.is_dir():
        raise T5PayloadError(f"IWD root is not a directory: {path}")
    candidates = [path]
    main = path / "main"
    if main.is_dir():
        candidates.append(main)
    for candidate in candidates:
        archives = sorted(candidate.glob("*.iwd"), key=lambda item: item.name.casefold())
        if archives:
            return candidate, archives
    raise T5PayloadError(
        f"no IWD archives found in {path} or its main subdirectory; "
        "pass a BO1 install directory or the directory containing iw_*.iwd"
    )


def _sha256_member(archive: Path, member: str) -> str:
    digest = hashlib.sha256()
    try:
        with zipfile.ZipFile(archive) as package, package.open(member) as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        raise T5PayloadError(f"cannot hash {member} in {archive}: {exc}") from exc
    return digest.hexdigest()


def index_image_payloads(
    bundle: Path, iwd_root: Path, output: Path, *, hash_matches: bool = False
) -> dict[str, Any]:
    bundle, iwd_root, output = Path(bundle), Path(iwd_root), Path(output)
    if output.exists():
        raise T5PayloadError(f"output already exists: {output}")
    iwd_root, archives = _resolve_iwd_root(iwd_root)
    document, _ = validate_bundle(bundle)
    graph = (bundle / GRAPH_DATA).read_bytes()
    layout = json.loads((bundle / LAYOUT).read_text(encoding="utf-8-sig"))
    types = layout["types"]
    image_assets = [asset for asset in document["loaded_assets"] if asset["type_name"] == "GfxImage"]
    by_name: dict[str, list[int]] = defaultdict(list)
    original_names: dict[str, str] = {}
    for asset in image_assets:
        name = asset["name"]
        if name is None:
            continue
        key = name.casefold()
        by_name[key].append(asset["index"])
        original_names.setdefault(key, name)

    matches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sound_paths: dict[str, list[int]] = defaultdict(list)
    original_sound_paths: dict[str, str] = {}
    for node in document["graph"]["nodes"]:
        if node.get("type_name") != "StreamedSound":
            continue
        type_index = node["type_index"]
        fields, _ = _root_fields(document, graph, types, types[type_index], node["id"])
        filename = _field(fields, "filename").get("string")
        if filename:
            normalized = filename.replace("\\", "/")
            key = normalized.casefold()
            sound_paths[key].append(node["id"])
            original_sound_paths.setdefault(key, filename)
    sound_matches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for archive in archives:
        try:
            with zipfile.ZipFile(archive) as package:
                for info in package.infolist():
                    normalized = info.filename.replace("\\", "/")
                    folded = normalized.casefold()
                    if not folded.startswith("images/") or not folded.endswith(".iwi"):
                        key = None
                    else:
                        key = folded[len("images/") : -len(".iwi")]
                    record: dict[str, Any] = {
                        "archive": archive.name,
                        "member": info.filename,
                        "uncompressed_bytes": info.file_size,
                        "compressed_bytes": info.compress_size,
                        "crc32": f"{info.CRC:08x}",
                    }
                    if key in by_name:
                        if hash_matches:
                            record["sha256"] = _sha256_member(archive, info.filename)
                        matches[key].append(record)
                    if folded in sound_paths:
                        sound_record = dict(record)
                        if hash_matches and "sha256" not in sound_record:
                            sound_record["sha256"] = _sha256_member(archive, info.filename)
                        sound_matches[folded].append(sound_record)
        except (OSError, zipfile.BadZipFile) as exc:
            raise T5PayloadError(f"cannot index {archive}: {exc}") from exc

    images = []
    conflicting = 0
    duplicate = 0
    resolved = 0
    unmatched_without_special_prefix = 0
    for key in sorted(by_name):
        candidates = matches.get(key, [])
        signatures = {
            (
                candidate["uncompressed_bytes"],
                candidate["crc32"],
                candidate.get("sha256"),
            )
            for candidate in candidates
        }
        if not candidates:
            status = "no_exact_iwd_match"
            if not original_names[key].startswith(("*", ",", "$")):
                unmatched_without_special_prefix += 1
        elif len(signatures) > 1:
            status = "conflicting_iwd_matches"
            conflicting += 1
        elif len(candidates) > 1:
            status = "identical_iwd_duplicates"
            duplicate += 1
            resolved += 1
        else:
            status = "resolved"
            resolved += 1
        images.append(
            {
                "name": original_names[key],
                "loaded_asset_indices": by_name[key],
                "status": status,
                "name_signals": {
                    "runtime_prefix": original_names[key].startswith("*"),
                    "generated_prefix": original_names[key].startswith(","),
                    "engine_prefix": original_names[key].startswith("$"),
                },
                "candidates": candidates,
            }
        )

    sounds = []
    resolved_sounds = 0
    conflicting_sounds = 0
    for key in sorted(sound_paths):
        candidates = sound_matches.get(key, [])
        signatures = {
            (item["uncompressed_bytes"], item["crc32"], item.get("sha256"))
            for item in candidates
        }
        if not candidates:
            status = "no_exact_iwd_match"
        elif len(signatures) > 1:
            status = "conflicting_iwd_matches"
            conflicting_sounds += 1
        elif len(candidates) > 1:
            status = "identical_iwd_duplicates"
            resolved_sounds += 1
        else:
            status = "resolved"
            resolved_sounds += 1
        sounds.append(
            {
                "filename": original_sound_paths[key],
                "streamed_sound_node_ids": sound_paths[key],
                "status": status,
                "candidates": candidates,
            }
        )

    result = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "source_file": document["source_file"],
        "iwd_root": str(iwd_root),
        "hash_matches": hash_matches,
        "summary": {
            "archives": len(archives),
            "image_identities": len(images),
            "resolved": resolved,
            "unresolved": len(images) - resolved,
            "identical_duplicate_sources": duplicate,
            "conflicting_sources": conflicting,
            "unmatched_without_special_prefix": unmatched_without_special_prefix,
            "streamed_sound_identities": len(sounds),
            "resolved_streamed_sounds": resolved_sounds,
            "unresolved_streamed_sounds": len(sounds) - resolved_sounds,
            "conflicting_streamed_sound_sources": conflicting_sounds,
        },
        "images": images,
        "streamed_sounds": sounds,
    }
    write_new_file(output, json_text(result).encode("utf-8"))
    return {"status": "t5_payload_index_written", "output": str(output), **result["summary"]}
