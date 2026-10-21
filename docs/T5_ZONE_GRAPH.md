# Hermes T5 zone graph v1

Talos uses Hermes as its authoritative Black Ops 1 decoder. The boundary is a
lossless source bundle, not a WaW fastfile and not a claim that the assets have
already been converted to BO3.

Run:

```powershell
python -m talos decode "C:\Games\Black Ops\zone\your_map.ff" `
  --hermes "C:\Tools\Hermes\hermes.exe" `
  --output local\your_map-t5
```

Talos asks Hermes to walk the entire unsigned PC `IWffu100` version `473` zone.
The command fails unless Hermes consumes every decompressed byte, reproduces the
seven XFile block reservations, and resolves every back-reference.

## Bundle files

| File | Contract |
| --- | --- |
| `manifest.json` | Versioned asset inventory, source metadata, graph topology, chunk extents and pointer links. |
| `graph.bin` | Every byte in every decoded allocation, concatenated in node/chunk order. Nothing is text-encoded or discarded. |
| `t5-layout.json` | The exact generated T5 type/member/load specification Hermes used to walk the zone. |
| `report.json` | Talos source identity, hashes, inventory and explicit remaining target work. Added only after validation. |

The manifest schema identifier is `hermes_t5_zone_graph`, version `1`. Node and
asset IDs are zero-based, contiguous and ordered. Each chunk names a byte extent
inside `graph.bin`; the extents must cover that file exactly with no overlap or
gap. Every pointer location and target is validated against those extents.

Link kinds preserve T5 loader semantics:

- `inline` is a following allocation; a null target represents runtime storage;
- `insert` is a following allocation with an insert slot;
- `ref` targets data loaded earlier;
- `alias_field` follows a previously loaded pointer field;
- `alias_slot` follows an insert slot;
- `shared` marks data laid out once and referenced thereafter.

Each root asset records its T5 type index/name, layout struct, root node, decoded
name when available, reachable-node count, and references to other root assets.
The original asset-table order and script-string indices are retained.

## What this proves

A validated bundle proves that Hermes decoded a complete supported T5 zone into
an internally consistent allocation graph without dropping opaque bytes. It
gives target work a pinned layout and exact pointer topology instead of forcing
Damocles to rediscover BO1 serialization.

It does **not** prove that a BO1 asset has a BO3 equivalent. The next Talos IR
version must lift supported root assets into semantic records for worlds,
collision, materials, images, models, animation, sound, FX, scripts and gameplay.
Unsupported fields and dependencies must remain visible. Only the official BO3
Mod Tools linker produces a BO3 fastfile, and only in-game testing establishes
runtime fidelity.
