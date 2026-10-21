# Direct binary conversion pipeline

## Contract

Talos's input is a supported **BO1 `.ff`** and its intended output is a supported
**BO3 `.ff`** containing translated native map assets. Conversion must decode the
source assets and serialize their destination equivalents. Renaming files,
changing version bytes, or recompressing an unchanged T5 zone does not satisfy
this contract.

The required stages are:

| Stage | Required work | Current state |
| --- | --- | --- |
| T5 container | Identify the source profile, validate compression, and recover serialized zone bytes. | Implemented only for unsigned little-endian PC `IWffu100` version `473`. |
| T5 zone and assets | Read stream/block organization, asset records, names, references, and payloads with bounds checks. | Only the 36-byte XFile size header is read; asset decoding is unimplemented. |
| Asset conversion | Translate supported BO1 asset semantics and dependencies into BO3 representations. | Unimplemented. |
| Native T7 zone serialization | Emit verified BO3 structures, asset tables, alignment, pointer/reference encoding, and fixups. | Unimplemented. |
| BO3 container | Write the required target header, compression/framing, and other verified container fields. | Unimplemented. |
| End-to-end validation | Verify output structure and dependency closure, establish target loader acceptance, and compare map fidelity. | Not performed. |

Radiant, `.map` interchange, source export, and Mod Tools compilation are not
stages of this converter. No target format constant or binary layout is implied
by this design table; each needs evidence before implementation.

## Input boundary that exists today

`talos.fastfile.inspect_fastfile` reports a header profile and file identity.
`talos.fastfile.unpack_fastfile` bounds decompressed output, validates one zlib
stream, and exposes the XFile size fields plus remaining serialized bytes.
Both explicitly retain `assets_decoded: false`.

The diagnostic `.zone.bin` produced by `unpack` remains BO1 data. It is not a
target artifact and must not be reported or distributed as a converted `.ff`.
The supported profile and primary references are recorded in
[INTEGRATION.md](INTEGRATION.md).

## Internal asset boundary to implement

A versioned internal representation may connect the decoder and converter. It
must retain asset type and identity, source provenance, resolved and unresolved
dependencies, decoded payloads, and conversion decisions. It must represent
native asset meaning rather than restrict maps to an editor brush format.

Required map coverage includes render-world data, collision, placed models,
materials and images, entities, lighting/visibility data, and the relevant
scripts and other dependencies. Each asset type needs explicit T5 decoding,
conversion, and T7 serialization support. Unresolved required assets stop a
claimed complete conversion; they are not silently dropped or replaced.

There is currently no implemented binary asset IR schema or public adapter API.
The former brush/entity JSON contract is removed. New schema and adapter
contracts should follow the actual donor structures and verified target needs.

## Evidence and completion criteria

For every supported asset class, retain reproducible source identities, bounds
checks, dependency inventories, documented conversion rules, and target
serialization tests. A serializer must be checked against independently
established T7 layouts or a separate reader; agreeing with its own assumptions is
insufficient.

A successful container write and a successful map conversion are separate
claims. Before claiming a converted map works, verify that its native BO3 data
loads and that required geometry, collision, assets, entities, and behavior are
preserved or explicitly accounted for. Record binary validation and runtime
results independently of synthetic unit tests.
