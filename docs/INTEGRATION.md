# Integration evidence

## Required ownership

Talos must convert **BO1 `.ff` directly into BO3 `.ff`**. The user confirmed this
binary architecture; it supersedes the earlier source-export implementation and
any conflicting donor plan.

| Component | Responsibility |
| --- | --- |
| BO1 input adapter | Decode T5 containers, zones, asset records, and dependencies; reuse verified Hermes knowledge. |
| Talos conversion layer | Preserve source meaning and translate each supported asset into its BO3 counterpart. |
| Native BO3 serializer | Write T7 asset layouts, zone structures, references, and fixups using verified binary rules; reuse relevant Damocles code when available. |
| BO3 container writer | Package the serialized target zone into the supported BO3 `.ff` profile. |
| Validation | Check source/target inventories, target binary structure, loader acceptance, and runtime fidelity separately. |

Hermes's WaW writer and Damocles's BO4 reader are not the halves needed here.
Talos should preserve BO1 data directly for its BO3 target. It does not use
Radiant, `.map` interchange, source export, or Mod Tools compilation as a bridge.

## Accessible donor snapshots

The connected repositories were inspected on October 20, 2026
(America/Los_Angeles).

### Damocles

The accessible revision was
[`ae16724f4b6a93dbc3f1f731bce47fc4736215b2`](https://github.com/Zippingrocks/Damocles/commit/ae16724f4b6a93dbc3f1f731bce47fc4736215b2).
Its [pipeline](https://github.com/Zippingrocks/Damocles/blob/ae16724f4b6a93dbc3f1f731bce47fc4736215b2/src/pipeline.rs)
stops at an unmet container-decoding stage, and its
[IR](https://github.com/Zippingrocks/Damocles/blob/ae16724f4b6a93dbc3f1f731bce47fc4736215b2/src/ir.rs)
holds asset metadata. That snapshot contains no native T7 writer to integrate.
Its source-output plan is not authority for Talos. Compare any more advanced
donor revision before duplicating its existing binary implementation.

### Hermes

The working Hermes source was not available in the connected repository
inventory. [Damocles's findings](https://github.com/Zippingrocks/Damocles/blob/ae16724f4b6a93dbc3f1f731bce47fc4736215b2/docs/FINDINGS.md)
identify revision `d25cda930903e2c6041736fe0f523c4bd2dcf4f9` and modules
`src/game.rs`, `src/fastfile.rs`, `src/zone.rs`, and `tools/zonecode.py`.
These identify the intended decoder for a future adapter; they do not establish
its current API. No unrelated project sharing the name was substituted.

## Verified BO1 container facts

Talos independently implements a narrow container reader using these primary
references from OpenAssetTools commit
[`06a121f7cf6658ea3989b3478b6275ce8c1c7b6d`](https://github.com/Laupetin/OpenAssetTools/commit/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d):

| Fact used by Talos | Primary source |
| --- | --- |
| `IWffu100`, version `473` | [ZoneConstantsT5.h](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneCommon/Game/T5/ZoneConstantsT5.h) |
| Eight magic bytes and 32-bit version | [ZoneTypes.h](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/Common/Zone/ZoneTypes.h) |
| Little-endian PC profile, seven blocks, inflate after header | [ZoneLoaderFactoryT5.cpp](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneLoading/Game/T5/ZoneLoaderFactoryT5.cpp) |
| Two initial unsigned size fields | [StepLoadZoneSizes.cpp](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneLoading/Loading/Steps/StepLoadZoneSizes.cpp) |
| Block-size loading and order | [StepAllocXBlocks.cpp](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneLoading/Loading/Steps/StepAllocXBlocks.cpp), [T5_Assets.h](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/Common/Game/T5/T5_Assets.h) |

No OpenAssetTools implementation is vendored. The current reader records the
XFile allocation sizes without trusting them as allocations or equating them to
the input length. Strict single-stream and trailing-byte rejection define
Talos's supported profile, not a rule asserted for every authentic fastfile.

## Correction history and next integration

Commit [`18e6332`](https://github.com/Zippingrocks/talos/commit/18e633239da42e873d6688089c0c5f517d2c2eeb)
introduced a source-export detour. That path is superseded and removed from the
active tree; the historical implementation remains recoverable through Git.

The retained implementation ends after container unpacking and XFile header
inspection. The next binary stages are documented in
[BINARY_PIPELINE.md](BINARY_PIPELINE.md). Neither a complete Hermes adapter nor a
native BO3 writer is currently integrated, and no successful fastfile conversion
is claimed.
