# Integration findings

## Intended ownership

| Component | Responsibility |
| --- | --- |
| Hermes source adapter | Decode the original BO1 container/zone/assets and preserve source identities and dependencies. |
| Talos map IR | Hold explicit, validated map data independently of either engine. |
| BO3 source backend | Translate that data into BO3 Radiant, material/model source assets, and zone inputs. |
| BO3 Mod Tools | Compile/link a complete target project; game testing establishes fidelity. |

The useful marriage is the BO1-reading half and the BO3-output half. Hermes's WaW
writer and Damocles's BO4 reader are not needed for this direction. There is no
reason to invent a BO1 → WaW → BO3 intermediate binary conversion.

## Donor audit

The repositories were checked on October 20, 2026 (America/Los_Angeles).

### Damocles

Audited commit: [`ae16724f4b6a93dbc3f1f731bce47fc4736215b2`](https://github.com/Zippingrocks/Damocles/commit/ae16724f4b6a93dbc3f1f731bce47fc4736215b2).
Only `main` was returned by the connected branch inventory.

- [`src/pipeline.rs`](https://github.com/Zippingrocks/Damocles/blob/ae16724f4b6a93dbc3f1f731bce47fc4736215b2/src/pipeline.rs)
  plans BO3 Mod Tools source generation, marks the target-source stage blocked,
  and unconditionally stops conversion at the unmet T8 container stage.
- [`src/ir.rs`](https://github.com/Zippingrocks/Damocles/blob/ae16724f4b6a93dbc3f1f731bce47fc4736215b2/src/ir.rs)
  contains asset metadata with T8/T7-specific validation, not recovered map
  geometry.
- [`docs/ARCHITECTURE.md`](https://github.com/Zippingrocks/Damocles/blob/ae16724f4b6a93dbc3f1f731bce47fc4736215b2/docs/ARCHITECTURE.md)
  supplies the target strategy: source export followed by the official linker.

This revision contributes architecture and accounting rules, not a working BO3
backend. A more advanced local or unpushed revision should be compared before
duplicating any existing implementation.

### Hermes

`Zippingrocks/Hermes` was not available through the connected GitHub account, and
the account's repository inventory did not contain a Hermes project. This does
not rule out a local checkout or a repository with another owner/name.

[Damocles's findings](https://github.com/Zippingrocks/Damocles/blob/ae16724f4b6a93dbc3f1f731bce47fc4736215b2/docs/FINDINGS.md)
record a local Hermes revision `d25cda930903e2c6041736fe0f523c4bd2dcf4f9` and the
modules `src/game.rs`, `src/fastfile.rs`, `src/zone.rs`, and `tools/zonecode.py`.
Those are leads, not an independently verified Hermes API. Its current source,
license, decoded asset structures, and usable export interface remain to be
inspected. No third-party project sharing the name was substituted.

## Independently verified format references

### Unsigned BO1 PC container

OpenAssetTools commit [`06a121f7cf6658ea3989b3478b6275ce8c1c7b6d`](https://github.com/Laupetin/OpenAssetTools/commit/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d):

| Fact used by Talos | Primary source |
| --- | --- |
| `IWffu100`, version `473` | [ZoneConstantsT5.h](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneCommon/Game/T5/ZoneConstantsT5.h) |
| Eight magic bytes and 32-bit version | [ZoneTypes.h](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/Common/Zone/ZoneTypes.h) |
| Little-endian PC profile, seven blocks, inflate after header | [ZoneLoaderFactoryT5.cpp](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneLoading/Game/T5/ZoneLoaderFactoryT5.cpp) |
| Two initial unsigned size fields | [StepLoadZoneSizes.cpp](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneLoading/Loading/Steps/StepLoadZoneSizes.cpp) |
| Block-size loading and order | [StepAllocXBlocks.cpp](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/ZoneLoading/Loading/Steps/StepAllocXBlocks.cpp), [T5_Assets.h](https://github.com/Laupetin/OpenAssetTools/blob/06a121f7cf6658ea3989b3478b6275ce8c1c7b6d/src/Common/Game/T5/T5_Assets.h) |

Talos independently implements these layout facts in Python. It does not vendor
OpenAssetTools code, claim support for its entire asset reader, or treat declared
allocation sizes as trusted allocations. Strict single-stream/trailing-byte
rejection is a Talos support boundary; it is not a claim that every authentic
file must have that exact padding behavior.

### BO3 Radiant text

- [Native BO3 source example](https://github.com/kelson8/bo3-Zombies-Test-Map/blob/b20ca20b1b043276b6797513f51ffb10c77faea2/prefabs/stairs1.map)
  establishes `iwmap 4`, entities, GUIDs, and the observed brush-face syntax.
- Corvid's [face writer](https://github.com/KILLTUBE/corvid/blob/99b9ff7f47704725aee850d3936e20b565e613a0/modules/CoDMap/Face.py)
  and [map writer](https://github.com/KILLTUBE/corvid/blob/99b9ff7f47704725aee850d3936e20b565e613a0/modules/CoDMap/Map.py)
  independently corroborate the two six-value face records and output without
  mandatory generated GUIDs.

These sources inform syntax only. No third-party code or original map geometry
is copied into Talos; fixtures are newly authored. Compiler acceptance and visual
fidelity still require the official tools and real source/target comparisons.

## Remaining executable stages

1. **Connect the real Hermes decoder.** Pin its actual repository/revision,
   inspect license and schemas, decode a locally supplied BO1 map, and populate
   supported IR fields with an exhaustive unsupported-asset report.
2. **Recover and preserve actual map content.** Resolve geometry, collision,
   placements, material/image dependencies, entities, lighting data and scripts.
   Add IR versions for data the current brush/entity subset cannot represent.
3. **Translate BO1 assets and behaviors for BO3.** Names alone are insufficient;
   emit usable material/model inputs and explicit gameplay/script adaptations.
4. **Build a complete BO3 project.** Add validated GDT/zone sources and a linker
   invocation based on an installed Mod Tools toolchain, then capture compiler
   diagnostics and output identities.
5. **Measure fidelity on a real map.** Compare positions, material appearance,
   collision, spawn behavior and scripts. Record compiler/runtime results
   independently of synthetic unit-test results.

This update completes the supported container reader and the source-map
import/IR/export slice. It leaves the unimplemented asset-decoding and target
build stages explicit rather than inventing a successful `.ff` conversion.
