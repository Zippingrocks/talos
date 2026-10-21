"""Dependency-free CLI for the supported Talos conversion stages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .fastfile import inspect_fastfile, unpack_fastfile
from .map_source import parse_map
from .numeric import parse_float_token
from .project import digest, export_project, json_text, validate_material_map, write_new_file


MIB = 1024 * 1024


def positive_int(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return result


def read_bounded(path: Path, maximum: int) -> bytes:
    if path.stat().st_size > maximum:
        raise ValueError(f"input exceeds the configured {maximum}-byte limit: {path}")
    with path.open("rb") as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError(f"input exceeds the configured {maximum}-byte limit: {path}")
    return data


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(data: bytes) -> object:
    return json.loads(
        data.decode("utf-8-sig"),
        object_pairs_hook=reject_duplicate_keys,
        parse_float=parse_float_token,
        parse_constant=parse_float_token,
    )


def load_material_map(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    return validate_material_map(load_json(read_bounded(path, 16 * MIB)))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="talos",
        description="BO1 fastfile inspection and BO3 brush/entity source export. No BO3 fastfile writer yet.",
    )
    root.add_argument("--version", action="version", version=f"Talos {__version__}")
    commands = root.add_subparsers(dest="command", required=True)

    for command in ("inspect", "unpack"):
        sub = commands.add_parser(command, help=f"{command} a supported unsigned PC BO1 fastfile")
        sub.add_argument("input", type=Path)
        sub.add_argument("--max-input-mib", type=positive_int, default=512)
        if command == "unpack":
            sub.add_argument("--output", type=Path, required=True, help="new raw zone file (not a map or target fastfile)")
            sub.add_argument("--max-output-mib", type=positive_int, default=256)

    for command in ("import-map", "convert-map"):
        sub = commands.add_parser(command, help="read the supported iwmap 4 brush/entity source subset")
        sub.add_argument("input", type=Path)
        sub.add_argument("--name", required=True, help="target map name, for example zm_talos_test")
        sub.add_argument("--output", type=Path, required=True)
        sub.add_argument("--material-map", type=Path, help="JSON object mapping every source brush material to a target name")
        sub.add_argument("--max-input-mib", type=positive_int, default=64)

    sub = commands.add_parser("export-map", help="emit a BO3 source bundle from Talos map IR v1")
    sub.add_argument("input", type=Path)
    sub.add_argument("--output", type=Path, required=True, help="new output directory")
    sub.add_argument("--material-map", type=Path)
    sub.add_argument("--max-input-mib", type=positive_int, default=64)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        data = read_bounded(args.input, args.max_input_mib * MIB)
        if args.command == "inspect":
            report = inspect_fastfile(data)
            print(json_text(report), end="")
            return 0 if report["supported"] else 2
        if args.command == "unpack":
            payload, report = unpack_fastfile(data, max_output_bytes=args.max_output_mib * MIB)
            write_new_file(args.output, payload)
            report["output"] = str(args.output)
            print(json_text(report), end="")
            return 0

        material_map = load_material_map(args.material_map)
        if args.command in ("import-map", "convert-map"):
            # Remapping happens once, at import only for import-map; source and
            # target inventories remain distinct in the convert-map report.
            document = parse_map(
                data.decode("utf-8-sig"),
                map_name=args.name,
                material_map=material_map if args.command == "import-map" else None,
            )
            source_kind = "radiant_source"
        else:
            document = load_json(data)
            source_kind = "talos_map_ir"

        if args.command == "import-map":
            write_new_file(args.output, json_text(document).encode("utf-8"))
            print(json_text({"status": "ir_imported", "output": str(args.output), "fastfile_written": False}), end="")
            return 0

        report = export_project(
            document,
            args.output,
            source={"kind": source_kind, "filename": args.input.name, "sha256": digest(data), "bytes": len(data)},
            material_map=material_map,
        )
        print(json_text(report), end="")
        return 0
    except RecursionError:
        print("talos: error: input nesting exceeds the supported parser depth", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(f"talos: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
