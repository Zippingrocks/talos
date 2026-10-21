# Semantic T5 asset IR

`python -m talos lift <decoded-bundle> --output <new.json>` writes schema
`talos_t5_semantic_ir`, version 1. It is a typed source index for direct binary
conversion, not a BO3 artifact.

## Authorities

The adjacent Hermes `graph.bin` remains the exact byte authority and
`t5-layout.json` remains the layout authority. The semantic file records their
identity and never substitutes inferred bytes. All offsets are little-endian PC
T5 offsets and the pointer width is four bytes.

Every graph node is classified. Struct and scalar nodes record their proven
element size and a per-chunk element count when the extent divides exactly.
String allocations are marked as NUL-terminated byte sequences. Loader-only
objects such as slots and the asset table are deliberately marked opaque while
their exact graph extents and links remain available.

Every root asset retains its source type/index/name, root node, dependency asset
indices, and reachability count. Every loaded root or nested asset additionally
retains its owning root, exact parent asset, depth and stream extent. For typed assets, every declared top-level
member records its offset, size, base type, modifiers, exact source bytes and
pointer link. Proven primitive scalars and fixed primitive arrays also receive a
decoded value. Strings are decoded as UTF-8 only when a layout string member has
a resolved graph target. Unions and unsupported encodings are never guessed.

## Coverage meaning

`typed_bytes + opaque_bytes` equals the complete graph byte count. This is
allocation-level typing, not a claim that every member has a BO3 conversion.
Root `field_covered_bytes` and `uncovered_byte_offsets` make structure padding
or incomplete layout coverage explicit. Values marked `retained_raw` require a
type-specific decoder or conversion policy before target serialization.

The converter must resolve required dependencies across the map and companion
zones. A single map fastfile is not necessarily a self-contained asset closure.
`talos catalog` accepts one or more validated bundles, records the exact
parent/child asset edges, and computes Merkle fingerprints over asset graph
closures. Matching identities with distinct fingerprints are explicit
conflicts; identical duplicates are safe to deduplicate.

Streamed BO1 images may live outside the fastfile. `talos payloads` resolves
every loaded `GfxImage` name against IWD image members case-insensitively,
records sizes and CRC32 metadata, detects conflicting duplicate sources, and can
cryptographically hash matched IWI bytes. Names carrying runtime, generated, or
engine prefixes remain explicit non-file signals rather than fabricated paths.
The same command reads `StreamedSound` filenames from typed graph nodes and
resolves them against IWD members. `LoadedSound` and `PrimedSound` nodes retain
their exact in-graph payload extents and SHA-256 identities in semantic IR.
