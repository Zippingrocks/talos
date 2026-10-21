# Talos

**Black Ops 1 → Black Ops 3 map conversion.**

Talos is the bridge between BO1 extraction and BO3 source generation. The intended
pipeline combines Hermes's BO1 knowledge with the BO3 target strategy used by
Damocles: recover source assets, translate them through an explicit intermediate
representation, then build the destination map with BO3 Mod Tools.

**Current status:** an executable first foundation: a verified BO1 container
reader and a brush/entity source-map conversion path. **Talos does not yet convert
a retail BO1 `.ff` into a playable BO3 `.ff`.** Decompressing a zone is separate
from decoding its assets; emitting Radiant text is separate from compiling and
testing the target map.

## What works now

| Stage | Implemented behavior |
| --- | --- |
| BO1 inspection | Identifies the unsigned PC `IWffu100`, version `473` profile; records SHA-256, size, and explicit support status. |
| BO1 decompression | Validates one complete zlib stream with a bounded output size and reads the 36-byte XFile size header. |
| Source-map import | Reads the supported `iwmap 4` brush/entity subset into Talos map IR v1. |
| BO3 source emission | Writes `.map` source with ordered plane points, both texture records, entity properties, and optional GUIDs preserved. |
| Material mapping | Applies explicit source-to-target brush-material names. A supplied map must cover every source material. |
| Conversion accounting | Writes deterministic IR and JSON reports with source/output hashes, asset references, and outstanding validation. |

Unknown structures, unsupported geometry, malformed input, and incomplete
material mappings produce errors. Existing output files/directories are never
overwritten.

## Run it

Requires **Python 3.10 or newer**. There are no third-party Python runtime
dependencies. Run these commands from the repository directory. On Windows use
`py -3`; on Linux/macOS substitute `python3`.

### Try the source conversion

```powershell
py -3 -m talos convert-map examples/synthetic_brush.map --name zm_talos_test --material-map examples/materials.json --output build/zm_talos_test
```

The example is authored synthetic data: one six-plane brush and a marker entity.
Its material mapping intentionally replaces the invented `bo1_demo_brick` name
with `caulk`. It demonstrates geometry preservation and explicit mapping, not
retail-game fidelity or a playable Zombies map.

The new output directory contains:

| File | Purpose |
| --- | --- |
| `map_source/zm_talos_test.map` | Generated Radiant source. This is a staging location, not an installed BO3 project. |
| `map-ir.json` | The exact target map data used by the writer. |
| `report.json` | Source/output identities, inventories, and validation state. |

The report says `status: source_exported`, `fastfile_written: false`, and
`bo3_mod_tools_compile: not_run`. Material-name remapping does not convert the
referenced images, shaders, or model assets.

### Inspect and unpack a supported BO1 fastfile

```powershell
py -3 -m talos inspect "C:\Games\Black Ops\zone\english\your_map.ff"
py -3 -m talos unpack "C:\Games\Black Ops\zone\english\your_map.ff" --output local/your_map.zone.bin --max-output-mib 256
```

`inspect` checks the header only. `unpack` verifies compression and size-header
availability; its result is serialized BO1 zone data with `assets_decoded: false`.
Neither command extracts a playable map. Signed/encrypted files, console files,
other versions, concatenated streams, and trailing padding are outside this
initial profile. Unknown profiles return exit code `2` with an explicit reason.

### Use the intermediate boundary

```powershell
py -3 -m talos import-map examples/synthetic_brush.map --name zm_talos_test --output local/zm_talos_test.json
py -3 -m talos export-map local/zm_talos_test.json --material-map examples/materials.json --output build/zm_talos_from_ir
```

See [the map IR contract](docs/MAP_IR.md) for the boundary a future Hermes adapter
must populate. An `iwmap 4` header is shared across tools; selecting this BO1
pipeline declares the source game rather than detecting it from that header.

## How Hermes and Damocles fit

The architecture is **BO1 reader → Talos IR → BO3 writer**, with reusable donor
code behind the input/output boundaries. It should not require an intermediate
WaW conversion: lowering BO1 data to WaW first could discard information the BO3
target can use.

The accessible `Zippingrocks/Damocles` revision
`ae16724f4b6a93dbc3f1f731bce47fc4736215b2` contains a Rust foundation and an explicit
BO3 source-output plan; its conversion function still stops at an unmet input
gate. It has no implemented BO3 emitter to transplant at that revision. Its audit
mentions a local Hermes revision, but the working Hermes source was not present
in the connected repositories. Accordingly, this update implements independent,
documented pieces and does not claim that either donor was fully integrated.

See [integration findings and next work](docs/INTEGRATION.md) for pinned source
evidence, the donor revision check, and the remaining stages.

## Verification

```powershell
py -3 -m unittest discover -s tests -v
```

Tests cover container corruption and output limits, supported source-map
roundtrips, geometry/texture/property preservation, strict unsupported-input
rejection, dependency reports, deterministic output, and no-overwrite behavior.
All fixtures are synthetic. GitHub Actions runs the suite on Windows and Ubuntu
with Python 3.10 and 3.12.

No retail BO1 map has been decoded or validated end to end by this revision, and
the generated source has not yet been opened or compiled in BO3 Mod Tools.
