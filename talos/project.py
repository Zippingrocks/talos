"""Build an honest, inspectable BO3 source bundle, never a pretend fastfile."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from . import __version__
from .radiant import render_map, validate_map


class ProjectError(ValueError):
    """The requested source export cannot be completed without losing data."""


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_material_map(mapping: Any) -> dict[str, str]:
    if not isinstance(mapping, dict):
        raise ProjectError("material map must be a JSON object of source name to target name")
    for source, target in mapping.items():
        if not isinstance(source, str) or not source or not isinstance(target, str) or not target:
            raise ProjectError("material mappings must have non-empty string keys and values")
        if any(char.isspace() for char in source + target):
            raise ProjectError("material names must not contain whitespace")
    return mapping


def map_materials(document: dict, mapping: dict[str, str] | None) -> dict:
    """Return a copy. A supplied mapping must account for every brush material."""
    validate_map(document)
    result = copy.deepcopy(document)
    if mapping is None:
        return result
    validate_material_map(mapping)
    missing = set()
    for entity in result["entities"]:
        for brush in entity.get("brushes", []):
            for face in brush["faces"]:
                material = face["material"]
                if material not in mapping:
                    missing.add(material)
                else:
                    face["material"] = mapping[material]
    if missing:
        raise ProjectError("material map is incomplete; missing: " + ", ".join(sorted(missing)))
    validate_map(result)
    return result


def inventory(document: dict) -> dict:
    materials: set[str] = set()
    lightmaps: set[str] = set()
    model_references = []
    brushes = faces = 0
    for index, entity in enumerate(document["entities"]):
        props = entity["properties"]
        for key in ("model", "xmodel", "skyboxmodel"):
            if key in props:
                model_references.append({"entity": index, "property": key, "value": props[key]})
        for brush in entity.get("brushes", []):
            brushes += 1
            for face in brush["faces"]:
                faces += 1
                materials.add(face["material"])
                lightmaps.add(face["lightmap"]["material"])
    return {
        "entities": len(document["entities"]),
        "brushes": brushes,
        "faces": faces,
        "materials": sorted(materials),
        "lightmap_materials": sorted(lightmaps),
        "model_references": model_references,
    }


def write_new_file(path: Path, data: bytes) -> None:
    """Exclusive creation; an existing file is never replaced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with path.open("xb") as handle:
            created = True
            handle.write(data)
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise


def export_project(
    document: dict,
    output: Path,
    *,
    source: dict,
    material_map: dict[str, str] | None = None,
) -> dict:
    """Export a new directory with a .map, normalized IR, and conversion report.

    All source validation and rendering happen before output creation. Materials,
    model assets, script behavior, compiler acceptance and game runtime behavior
    remain explicit unverified dependencies. This function does not run a linker.
    """
    target = map_materials(document, material_map)
    name = target["map_name"]
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name):
        raise ProjectError("map_name must be a lowercase safe filename (1-64 letters, digits or underscores)")
    map_bytes = render_map(target).encode("utf-8")
    ir_bytes = json_text(target).encode("utf-8")
    relative_map = f"map_source/{name}.map"
    report = {
        "schema_version": 1,
        "tool": {"name": "Talos", "version": __version__},
        "status": "source_exported",
        "source": source,
        "direction": {"source_game": "bo1", "target_game": "bo3"},
        "source_game_identification": "declared_by_caller_not_proven_by_iwmap_header",
        "source_inventory": inventory(document),
        "target_inventory": inventory(target),
        "material_mapping": material_map,
        "validation": {
            "ir_schema": "passed",
            "radiant_text_generation": "passed",
            "brush_volume_and_topology": "not_verified",
            "target_assets": "not_verified",
            "entity_semantics": "not_converted",
            "bo3_mod_tools_compile": "not_run",
            "bo3_runtime": "not_run",
        },
        "fastfile_written": False,
        "outputs": [
            {"path": relative_map, "bytes": len(map_bytes), "sha256": digest(map_bytes)},
            {"path": "map-ir.json", "bytes": len(ir_bytes), "sha256": digest(ir_bytes)},
        ],
        "remaining_work": [
            "Decode BO1 zone assets into this IR using a verified Hermes adapter.",
            "Convert or provide every referenced material, image, model and script.",
            "Review preserved entity properties for BO3 behavior and gameplay setup.",
            "Compile a complete BO3 Mod Tools project and validate it in game.",
        ],
    }
    report_bytes = json_text(report).encode("utf-8")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()  # Exclusive: do not overwrite a prior export or user directory.
    try:
        write_new_file(output / relative_map, map_bytes)
        write_new_file(output / "map-ir.json", ir_bytes)
        write_new_file(output / "report.json", report_bytes)
    except BaseException:
        shutil.rmtree(output)
        raise
    return report
