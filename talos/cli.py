"""CLI for implemented stages of direct BO1-to-BO3 binary conversion."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .fastfile import inspect_fastfile, unpack_fastfile
from .hermes_adapter import decode_with_hermes
from .io_utils import json_text, read_bounded, write_new_file


MIB = 1024 * 1024


def positive_int(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="talos",
        description=(
            "Direct BO1-to-BO3 binary fastfile conversion foundation. "
            "Implemented: BO1 inspection, unpacking, and lossless Hermes T5 graph decode. "
            "Semantic conversion and native BO3 fastfile writing are not implemented yet."
        ),
    )
    root.add_argument("--version", action="version", version=f"Talos {__version__}")
    commands = root.add_subparsers(dest="command", required=True)

    for command in ("inspect", "unpack"):
        sub = commands.add_parser(command, help=f"{command} a supported unsigned PC BO1 fastfile")
        sub.add_argument("input", type=Path)
        sub.add_argument("--max-input-mib", type=positive_int, default=512)
        if command == "unpack":
            sub.add_argument("--output", type=Path, required=True, help="new diagnostic T5 zone file")
            sub.add_argument("--max-output-mib", type=positive_int, default=256)

    sub = commands.add_parser("decode", help="decode a BO1 fastfile through Hermes into lossless T5 graph IR")
    sub.add_argument("input", type=Path)
    sub.add_argument("--hermes", type=Path, required=True, help="Hermes executable with export-talos support")
    sub.add_argument("--output", type=Path, required=True, help="new Talos T5 binary-source bundle")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "decode":
            report = decode_with_hermes(args.input, args.hermes, args.output)
            print(json_text(report), end="")
            return 0
        data = read_bounded(args.input, args.max_input_mib * MIB)
        if args.command == "inspect":
            report = inspect_fastfile(data)
            print(json_text(report), end="")
            return 0 if report["supported"] else 2
        payload, report = unpack_fastfile(data, max_output_bytes=args.max_output_mib * MIB)
        write_new_file(args.output, payload)
        report["output"] = str(args.output)
        print(json_text(report), end="")
        return 0
    except (OSError, ValueError, OverflowError) as exc:
        print(f"talos: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
