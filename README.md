# Talos

**Goal: direct Black Ops 1 `.ff` → Black Ops 3 `.ff` conversion.**

Talos combines Hermes's BO1 input knowledge with reusable BO3 binary output
knowledge from Damocles. The required conversion path is:

**BO1 fastfile → T5 zone/asset decoding → BO1-to-BO3 asset conversion → native T7
zone serialization → BO3 fastfile.**

Radiant, `.map` interchange, source export, and Mod Tools compilation are outside
this converter. The internal representation must preserve everything required to
serialize native destination assets.

## Current implementation

Talos now invokes Hermes to decode a complete supported BO1 zone into a lossless,
validated T5 allocation graph. It does **not** yet translate those asset semantics
or write a BO3 fastfile.

| Stage | Status |
| --- | --- |
| BO1 container inspection | Implemented for unsigned little-endian PC `IWffu100`, version `473`; reports SHA-256, size, and explicit support status. |
| BO1 bounded decompression | Implemented for one complete zlib stream and the 36-byte XFile size header. |
| T5 allocation graph | Implemented through Hermes: every allocation byte, pointer link, root asset, script string and the exact T5 layout are retained and independently validated. |
| Semantic T5 asset IR | Implemented as a lossless typed index over the Hermes graph: typed allocation extents, root fields and values, pointer ownership, asset identity/dependencies, and explicit byte coverage. Type-specific BO1-to-BO3 policies remain future work. |
| BO1-to-BO3 asset conversion | Not implemented. |
| Native T7 zone serialization and `.ff` writing | Not implemented. |
| End-to-end BO3 validation | Not performed. |

The semantic IR is still BO1 data. It is not relabeled or reported as BO3
output, and no `convert` command exists yet.

## Commands

Requires Python 3.10 or newer with no third-party runtime dependencies.

```powershell
py -3 -m talos inspect "C:\Games\Black Ops\zone\english\your_map.ff"
py -3 -m talos unpack "C:\Games\Black Ops\zone\english\your_map.ff" --output local\your_map.zone.bin --max-output-mib 256
```

`inspect` validates only the supported header profile. `unpack` validates
compression and writes diagnostic serialized T5 zone bytes. Neither command
decodes assets or produces a target artifact.

To decode the complete T5 asset graph, build
[Hermes](https://github.com/KingslayerKyle/Hermes) and run:

```powershell
py -3 -m talos decode "C:\Games\Black Ops\zone\Common\zombie_theater.ff" `
  --hermes "C:\Tools\Hermes\hermes.exe" `
  --output local\zombie_theater-t5

py -3 -m talos lift local\zombie_theater-t5 `
  --output local\zombie_theater-t5-semantic.json

py -3 -m talos catalog local\zombie_theater-t5 local\common-t5 `
  --output local\zombie-source-catalog.json

py -3 -m talos payloads local\zombie_theater-t5 `
  --iwd-root "C:\Games\Black Ops" `
  --output local\zombie-image-payloads.json
```

The no-overwrite decode output contains `manifest.json`, `graph.bin`,
`t5-layout.json`, and `report.json`. Talos rejects incomplete walks, mismatched
block accounting, unresolved pointers, malformed binary extents, and out-of-range
links. `lift` writes a separate, no-overwrite semantic index while retaining
`graph.bin` as the exact binary authority. See [the T5 graph contract](docs/T5_ZONE_GRAPH.md)
and [semantic T5 IR contract](docs/T5_SEMANTIC_IR.md).
`catalog` fingerprints complete asset graph closures independently of local node
numbers, deduplicates matching identities across zones, and reports conflicting
definitions instead of silently choosing one.
`payloads` inventories all loaded `GfxImage` identities against BO1 IWD central
directories, distinguishes exact matches, identical duplicate sources,
conflicting sources and non-matches, and can SHA-256 matching IWI payloads with
`--hash-matches`. Runtime (`*`), generated (`,`) and engine (`$`) name signals
are reported but never treated as guessed files. `--iwd-root` accepts either the
BO1 install directory or its direct `main` IWD directory and rejects a scan that
finds no archives.

Signed/encrypted files, console profiles, and other versions remain outside this
support boundary.

## Integration and next work

The lossless graph and typed semantic index are the implemented BO1 boundary
between Hermes and Talos. Talos must next establish verified T7 layouts and
pointer/fixup rules, translate dependencies, and serialize native BO3 zones and
containers. BO1 data never passes through WaW.

See [the binary pipeline](docs/BINARY_PIPELINE.md) and
[integration evidence](docs/INTEGRATION.md). The source-export detour from
[`18e6332`](https://github.com/Zippingrocks/talos/commit/18e633239da42e873d6688089c0c5f517d2c2eeb)
is superseded and remains only in Git history.

## Verification

```powershell
py -3 -m unittest discover -s tests -v
```

The suite covers container corruption and limits, graph extents and pointer
targets, deterministic inventories, subprocess failure, and no-overwrite rules.
A local retail validation on October 20, 2026 decoded `zombie_theater.ff`
completely: 908 root assets, 3,628 total loaded assets, 68,870 graph nodes,
75,315 chunks, 169,490 links, 789 script strings, and 111,197,324 allocation
bytes. The semantic pass also decoded 2,794 map entities and all 1,546 cells of
the map StringTable, retained all 326 embedded loaded-sound payloads (7,005,264
bytes), and found exact IWD members for all 26 streamed sounds. Of 1,318 image
identities, 1,240 had exact IWD matches; all 78 non-matches carried explicit
runtime/generated/engine prefixes, and no ordinary filename was missing. The
source SHA-256 was
`970db88bb5ae9aa1d3875cdbd55d43212f22ee55096ce251f596d4a38a776786`.

The broader retail matrix covers 33 SP, Zombies, MP, UI, patch and localized
zones: 31,898 roots, 61,910 loaded assets, 1,239,816 nodes, 4,090,024 links, and
1,312,661,494 allocation bytes. It exercised 31 of T5's 32 unique loadable asset
structures; the declared but unobserved `PackIndex` path has a synthetic semantic
fixture. See [the retail validation matrix](docs/T5_RETAIL_VALIDATION.md).

That proves the source-decode boundary for those installed files. It does not prove
semantic conversion, native T7 serialization, BO3 loader acceptance, or gameplay
fidelity; those stages remain explicitly unimplemented.
