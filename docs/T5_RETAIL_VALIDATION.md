# T5 retail validation matrix

Talos's BO1 source boundary was validated locally on October 20, 2026 against
33 unsigned PC T5 zones from the installed game. Proprietary bundles and
semantic outputs are intentionally not committed.

## Aggregate evidence

The canonical corpus contains:

- 31,898 root assets and 61,910 root-or-nested loaded assets;
- 1,239,816 allocation nodes and 4,090,024 pointer links;
- 1,312,661,494 bytes in lossless allocation graphs; and
- zero incomplete walks or unresolved loader back-references.

Every bundle passed independent Talos graph validation. Every bundle was then
lifted into typed semantic IR, where `typed_bytes + opaque_bytes` equalled the
complete graph size. External image and streamed-sound identities were checked
against all 58 IWD archives in the BO1 `main` directory. Ordinary image names
had an exact candidate; remaining no-match names used the explicit runtime
(`*`), generated (`,`), or engine (`$`) prefixes. Differing same-name members in
multiple IWDs remain explicit conflicts rather than receiving a guessed
precedence.

## Representative zones

| Zone | Roots | Loaded assets | Graph nodes | Graph bytes | Distinct evidence |
| --- | ---: | ---: | ---: | ---: | --- |
| `common.ff` | 1,676 | 2,093 | 24,268 | 28,684,865 | global SP assets |
| `common_zombie.ff` | 2,693 | 4,018 | 66,982 | 79,661,297 | shared Zombies assets |
| `frontend.ff` | 479 | 1,294 | 35,392 | 55,956,133 | menus and frontend world |
| `code_post_gfx.ff` | 786 | 1,170 | 28,762 | 6,222,381 | DDL, fonts, physics and sound globals |
| `zombie_theater.ff` | 908 | 3,628 | 68,870 | 111,197,324 | complete Kino source graph |
| `zombie_pentagon.ff` | 1,045 | 3,951 | 66,505 | 108,008,989 | Five and `Glasses` |
| `zombie_cosmodrome.ff` | 1,123 | 3,916 | 74,735 | 119,991,270 | Ascension and destructibles |
| `zombie_coast.ff` | 1,181 | 3,503 | 57,342 | 107,468,337 | Call of the Dead |
| `zombie_temple.ff` | 1,326 | 3,860 | 67,913 | 117,429,847 | Shangri-La |
| `zombie_moon.ff` | 1,247 | 3,408 | 61,702 | 113,690,652 | Moon |
| `zombietron.ff` | 2,685 | 6,280 | 103,100 | 159,058,494 | Dead Ops and `XGlobals` |
| `common_mp.ff` | 7,199 | 9,774 | 146,162 | 106,920,038 | largest shared-asset stress case |
| `code_post_gfx_mp.ff` | 664 | 2,024 | 28,800 | 3,840,105 | `EmblemSet` and MP bootstrap data |
| `mp_nuked.ff` | 515 | 2,166 | 43,285 | 78,846,065 | `GameWorldMp` and MP MapEnts |
| `patch_mp.ff` | 527 | 819 | 30,560 | 10,949,451 | real `SndPatch` instance |
| `ui_mp.ff` | 376 | 1,080 | 151,342 | 14,066,602 | dense menu graph |

The aggregate also includes localized common/frontend/post-GFX zones, SP/MP
pre-GFX and patch overlays, `patch_ui_mp`, `ui_viewer_mp`, and all six
`so_narrative*_frontend` zones.

## Asset-structure coverage

Retail evidence exercised 31 of the 32 unique structures named by T5's loadable
asset table: physics presets/constraints, destructibles, animations, models,
materials, technique sets, images, sound banks and patches, clip maps, SP and MP
game worlds, MapEnts, render worlds, lights, fonts, menus, localization, weapons,
sound globals, effects, impact tables, raw files, string tables, XGlobals, DDL,
Glasses, and EmblemSet.

`PackIndex` is declared by the T5 layout but was not instantiated by any sampled
PC retail zone. A synthetic schema-v2 bundle tests its 28-byte root and embedded
`PackIndexHeader` semantic lift. This is loader-supported test coverage, not a
claim that a retail `PackIndex` sample was observed.

## Boundary of the claim

This matrix proves the implemented BO1 input boundary for the listed unsigned
PC version-473 files: container inflation, complete loader walk, exact allocation
bytes, pointer topology, asset hierarchy, script strings, semantic indexing, and
external IWD lookup. It does not prove BO1-to-BO3 semantic translation, native
T7 serialization, BO3 loader acceptance, or gameplay fidelity.
