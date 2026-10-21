"""Bounded input and exclusive output for native fastfile work."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_bounded(path: Path, maximum: int) -> bytes:
    if path.stat().st_size > maximum:
        raise ValueError(f"input exceeds the configured {maximum}-byte limit: {path}")
    with path.open("rb") as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError(f"input exceeds the configured {maximum}-byte limit: {path}")
    return data


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def write_new_file(path: Path, data: bytes) -> None:
    """Never replace an existing file, including when a write fails."""
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
