# Binary integration evidence

## Binding direction

Talos is a direct BO1-to-BO3 binary fastfile converter. Its stages are T5
container/asset decode, semantic conversion, native T7 zone serialization, and
BO3 container output. Radiant, `.map` files, source export, and Mod Tools
compilation are not part of this path.

## Donor audit

### Damocles

Audited commit:
[`ae16724f4b6a93dbc3f1f731bce47fc4736215b2`](https://github.com/Zippingrocks/Damocles/commit/ae16724f4b6a93dbc3f1f731bce47fc4736215b2).

Its `src/pipeline.rs` stops at an unmet container-decoding stage and its
`src/ir.rs` holds T8/T7-oriented asset metadata. That snapshot contains no native
T7 writer ready to transplant. A newer Damocles revision must be audited before
duplicating any BO3 binary implementation.

### Hermes

Integrated source:
[`KingslayerKyle/Hermes` commit `8dfb9653428ae562f9f9396a05bf8370959a7e56`](https://github.com/KingslayerKyle/Hermes/commit/8dfb9653428ae562f9f9396a05bf8370959a7e56).

Hermes supplies the implemented T5 container reader, generated T5 type/load
layout, complete loader walk, allocation graph, resolved pointer topology, asset
roots, and script strings. `hermes export-talos` publishes schema
`hermes_t5_zone_graph` version 2, documented in
[T5_ZONE_GRAPH.md](T5_ZONE_GRAPH.md).

Talos validates every file, graph extent, link location, target location, asset
root, and dependency index before accepting the bundle. No WaW output is used;
the exact decoded BO1 graph remains available to the future T7 converter.

## Independently verified BO1 container facts

Talos's narrow container reader uses primary format evidence from
OpenAssetTools commit
[`06a121f7cf6658ea3989b3478b6275ce8c1c7b6d`](https://github.com/Laupetin/OpenAssetTools/commit/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d):

| Fact | Primary source |
| --- | --- |
| `IWffu100`, version `473` | [ZoneConstantsT5.h](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneCommon/Game/T5/ZoneConstantsT5.h) |
| Eight-byte magic and 32-bit version | [ZoneTypes.h](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/Common/Zone/ZoneTypes.h) |
| Little-endian PC profile, seven blocks, inflate after header | [ZoneLoaderFactoryT5.cpp](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneLoading/Game/T5/ZoneLoaderFactoryT5.cpp) |
| Initial size fields | [StepLoadZoneSizes.cpp](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneLoading/Loading/Steps/StepLoadZoneSizes.cpp) |
| Block sizes and order | [StepAllocXBlocks.cpp](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneLoading/Game/T5/ZoneLoaderFactoryT5.cpp), [T5_Assets.h](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/Common/Game/T5/T5_Assets.h) |

No OpenAssetTools implementation is vendored. Declared sizes are reported and
checked against Hermes's loader accounting; they are never trusted as unchecked
allocations.

## Retail source-decode evidence

On October 20, 2026, the integrated command decoded an installed PC
`zombie_theater.ff` with SHA-256
`970db88bb5ae9aa1d3875cdbd55d43212f22ee55096ce251f596d4a38a776786`.
Hermes consumed the complete zone, matched its block reservations, and reported
zero unlinked back-references. Talos independently validated 908 assets, 68,870
nodes, 75,315 chunks, 169,490 links, 789 script strings, and 111,197,324 graph
bytes. Proprietary output is not committed.

## Remaining binary stages

1. Extend type-specific semantic policies from the implemented lossless T5 IR
   while retaining every raw member and explicit dependency edge.
2. Establish primary evidence for native T7 asset IDs, structures, alignment,
   pointer/fixup encoding, zone blocks, compression, and container framing.
3. Translate render worlds, collision, placements, materials/images, entities,
   lighting/visibility, models/animation, sound, FX, scripts, and gameplay.
4. Serialize and independently read back a native T7 zone; agreement with the
   writer's own assumptions is insufficient.
5. Establish BO3 loader acceptance and then measure map and gameplay fidelity.

The source-export detour introduced in `18e6332` is superseded and removed from
the active tree. No successful BO1-to-BO3 fastfile conversion is claimed yet.
