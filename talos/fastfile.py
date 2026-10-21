"""Read the documented unsigned BO1 PC fastfile container, without decoding assets.

Independent implementation of format facts verified against OpenAssetTools at
06a121f7cf6658ea3989b3478b6275ce8c1c7b6d.  No upstream implementation is vendored.
Primary references (relative to SOURCE_BASE):

* src/Common/Zone/ZoneTypes.h: eight magic bytes and a uint32 version.
* src/ZoneCommon/Game/T5/ZoneConstantsT5.h: IWffu100 and version 473.
* src/ZoneLoading/Game/T5/ZoneLoaderFactoryT5.cpp: little-endian PC/32-bit,
  seven XFile blocks, a zlib processor immediately after the 12-byte header.
* src/ZoneLoading/Loading/Steps/StepLoadZoneSizes.cpp: two uint32 size fields.
* src/ZoneLoading/Loading/Steps/StepAllocXBlocks.cpp and
  src/Common/Game/T5/T5_Assets.h: seven uint32 block sizes and their order.

The size fields describe the loader's allocation/serialization model.  They are
reported, not used as unchecked allocations or asserted to equal file length.
Decompression validates one complete zlib stream and rejects trailing bytes.
This deliberately narrow profile does not support signed/encrypted or console
fastfiles, another BO1 version, asset pointer traversal, or BO3 output.
"""

from __future__ import annotations

import hashlib
import struct
import sys
import zlib
from typing import Any

SOURCE_BASE = (
    "https://github.com/Laupetin/OpenAssetTools/blob/"
    "06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/"
)
SOURCE_URLS = tuple(
    SOURCE_BASE + path
    for path in (
        "src/Common/Zone/ZoneTypes.h",
        "src/ZoneCommon/Game/T5/ZoneConstantsT5.h",
        "src/ZoneLoading/Game/T5/ZoneLoaderFactoryT5.cpp",
        "src/ZoneLoading/Loading/Steps/StepLoadZoneSizes.cpp",
        "src/ZoneLoading/Loading/Steps/StepAllocXBlocks.cpp",
        "src/Common/Game/T5/T5_Assets.h",
    )
)

MAGIC = b"IWffu100"
VERSION = 473
HEADER_BYTES = 12
XFILE_HEADER_BYTES = 36
DEFAULT_MAX_OUTPUT_BYTES = 256 * 1024 * 1024
BLOCK_NAMES = (
    "temp",
    "runtime",
    "large_runtime",
    "physical_runtime",
    "virtual",
    "large",
    "physical",
)
SUPPORT_BOUNDARY = "Unsigned little-endian BO1 PC IWffu100 version 473 only"


class FastfileError(ValueError):
    """The input is unsupported, malformed, or exceeds the output limit."""


def inspect_fastfile(data: bytes) -> dict[str, Any]:
    """Inspect a header without decompressing or declaring assets readable.

    Unknown profiles are returned with ``supported=False`` and a reason.  For
    these inputs, ``version`` is only the little-endian integer in prefix bytes
    8..11; no claim is made about that format's true header or payload layout.
    Inputs shorter than the required 12-byte probe prefix raise FastfileError.
    """
    if not isinstance(data, bytes):
        raise FastfileError("Fastfile input must be bytes")
    if len(data) < HEADER_BYTES:
        raise FastfileError(
            f"Input is too short for a fastfile header probe: {len(data)} bytes; "
            f"need at least {HEADER_BYTES}"
        )

    magic = data[:8]
    version = struct.unpack_from("<I", data, 8)[0]
    supported = magic == MAGIC and version == VERSION
    if magic != MAGIC:
        reason = (
            "Unsupported fastfile magic; signed, encrypted, console, and unknown "
            "containers are not accepted. " + SUPPORT_BOUNDARY
        )
    elif version != VERSION:
        reason = f"Unsupported version {version}. " + SUPPORT_BOUNDARY
    else:
        reason = None

    return {
        "supported": supported,
        "profile": "bo1_pc_unsigned_473" if supported else None,
        "support_boundary": SUPPORT_BOUNDARY,
        "magic": magic.decode("ascii", errors="backslashreplace"),
        "magic_hex": magic.hex(),
        "version": version,
        "sha256": hashlib.sha256(data).hexdigest(),
        "file_bytes": len(data),
        "header_bytes": HEADER_BYTES if supported else None,
        "compressed_bytes": len(data) - HEADER_BYTES if supported else None,
        "compression": "zlib" if supported else None,
        "reason": reason,
        "validation": "header_only",
        "assets_decoded": False,
    }


def unpack_fastfile(
    data: bytes, *, max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
) -> tuple[bytes, dict[str, Any]]:
    """Validate and unpack one supported fastfile into its serialized zone bytes.

    ``max_output_bytes`` bounds decompressed bytes, including the 36-byte XFile
    size header.  At most one extra decompressed byte is requested to detect an
    exceeded limit.  No flush with an unbounded output allocation is used.
    A successful return proves container integrity and availability of the size
    header; it does not prove that the remaining bytes form valid game assets.
    """
    if (
        isinstance(max_output_bytes, bool)
        or not isinstance(max_output_bytes, int)
        or not 1 <= max_output_bytes < sys.maxsize
    ):
        raise FastfileError("max_output_bytes must be a positive bounded integer")

    metadata = inspect_fastfile(data)
    if not metadata["supported"]:
        raise FastfileError(metadata["reason"])

    inflater = zlib.decompressobj()
    try:
        # A memoryview avoids a second full copy of the compressed input.
        payload = inflater.decompress(
            memoryview(data)[HEADER_BYTES:], max_output_bytes + 1
        )
    except zlib.error as exc:
        raise FastfileError(f"Invalid zlib payload: {exc}") from exc

    if len(payload) > max_output_bytes:
        raise FastfileError(
            f"Decompressed payload exceeds the {max_output_bytes}-byte output limit"
        )
    if not inflater.eof:
        raise FastfileError("Truncated or incomplete zlib payload (end marker missing)")
    if inflater.unused_data:
        raise FastfileError(
            f"Trailing data after the zlib stream: {len(inflater.unused_data)} bytes; "
            "concatenated streams and padded containers are not supported"
        )
    if inflater.unconsumed_tail:
        # Normally impossible with a complete stream and the +1 output allowance.
        # Keep the invariant explicit rather than silently accepting a remainder.
        raise FastfileError("The zlib payload was not fully consumed")
    if len(payload) < XFILE_HEADER_BYTES:
        raise FastfileError(
            f"Truncated XFile size header: {len(payload)} decompressed bytes; "
            f"need at least {XFILE_HEADER_BYTES}"
        )

    sizes = struct.unpack_from("<9I", payload)
    metadata.update(
        {
            "validation": "zlib_and_xfile_header",
            "decompressed_bytes": len(payload),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "max_output_bytes": max_output_bytes,
            "xfile": {
                "declared_zone_size": sizes[0],
                "external_size": sizes[1],
                "block_sizes": dict(zip(BLOCK_NAMES, sizes[2:])),
                "allocation_bytes": sum(sizes[2:]),
                "header_bytes": XFILE_HEADER_BYTES,
                "remaining_serialized_bytes": len(payload) - XFILE_HEADER_BYTES,
            },
        }
    )
    return payload, metadata
