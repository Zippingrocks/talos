# Talos

**Goal: direct Black Ops 1 `.ff` → Black Ops 3 `.ff` conversion.**

Talos is being built to combine Hermes's BO1 input knowledge with reusable BO3
binary output knowledge from Damocles. The conversion path is:

**BO1 fastfile → T5 zone/asset decoding → BO1-to-BO3 asset conversion → native T7
zone serialization → BO3 fastfile.**

The user requires a direct binary converter. Radiant, `.map` interchange, source
export, and Mod Tools compilation are outside this conversion path. An internal
asset representation can connect the two binary formats; it must preserve the
data needed to serialize the destination assets.

## Current implementation

**Talos currently inspects and unpacks one BO1 container profile. It does not yet
decode complete map assets or write BO3 fastfiles.**

| Stage | Status |
| --- | --- |
| BO1 container inspection | Implemented for unsigned, little-endian PC `IWffu100`, version `473`; reports SHA-256, file size, and support status. |
| BO1 bounded decompression | Implemented for one complete zlib stream; reads the 36-byte XFile size header. |
| T5 asset decoding and dependency recovery | Not implemented. |
| BO1-to-BO3 asset conversion | Not implemented. |
| Native T7 zone serialization and `.ff` writing | Not implemented. |
| End-to-end map validation | Not performed. |

Unpacking returns serialized **BO1** zone bytes. It does not convert their asset
layouts, pointers, dependencies, or behavior into BO3 data. No `convert` command
is currently available.

## Run the available commands

Requires **Python 3.10 or newer**, with no third-party runtime dependencies. Run
from the repository directory. On Windows use `py -3`; on Linux/macOS use
`python3`.

```powershell
py -3 -m talos inspect "C:\Games\Black Ops\zone\english\your_map.ff"
py -3 -m talos unpack "C:\Games\Black Ops\zone\english\your_map.ff" --output local/your_map.zone.bin --max-output-mib 256
```

`inspect` validates the supported header profile only. `unpack` validates
compression and the availability of the XFile size header, writes a diagnostic
zone dump, and reports `assets_decoded: false`. The dump is an input to further
binary-format work, not a BO3 output file. Existing output paths are not
overwritten.

Signed/encrypted files, console profiles, other versions, concatenated zlib
streams, and trailing padding are outside this initial support boundary.

## Integration and next work

Hermes's BO1 reader is the intended input donor; a verified native BO3 writer is
the intended output donor. Talos owns the translation between their asset
representations. BO1 data should reach the BO3 conversion stage directly without
first being lowered into WaW assets.

The immediate work is to connect a verified T5 zone/asset reader, establish the
target T7 binary layouts and serialization rules, then implement asset conversion
with dependency checks. See [the binary pipeline](docs/BINARY_PIPELINE.md) and
[integration evidence](docs/INTEGRATION.md).

The source-export detour introduced in
[`18e6332`](https://github.com/Zippingrocks/talos/commit/18e633239da42e873d6688089c0c5f517d2c2eeb)
is superseded and removed from the active pipeline. Its code remains recoverable
in Git history; it is not the architecture to continue.

## Verification

```powershell
py -3 -m unittest discover -s tests -v
```

The retained tests exercise synthetic BO1 containers, malformed input, bounded
decompression, header reporting, and output handling. Synthetic container tests
do not establish retail-map decoding or BO3 compatibility. No successful BO1
map-to-BO3-fastfile conversion is claimed by this revision.
