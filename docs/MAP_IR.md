# Talos map IR v1

This is a small, strict boundary for the implemented brush/entity source path.
It is not yet a complete representation of all BO1 assets. Unknown members are
rejected so that an adapter cannot appear to preserve data the writer drops.

## Root and entities

The root has exactly `schema_version`, `source_game`, `target_game`, `map_name`,
and `entities`:

| Member | Contract |
| --- | --- |
| `schema_version` | Integer `1` (a boolean is not accepted). |
| `source_game` | String `bo1`, a caller declaration. |
| `target_game` | String `bo3`. |
| `map_name` | Lowercase ASCII identifier matching `[a-z][a-z0-9_]{0,63}`. |
| `entities` | Nonempty ordered array; the first and only worldspawn comes first. |

Each entity requires `properties`, a string-to-string object, and `brushes`, an
ordered array which may be empty for point entities. `classname` must be present
and nonempty. An optional `guid` is a UUID, with or without braces. GUID spelling
and case are retained; output adds braces when absent.

Entity properties are preserved without claiming they implement equivalent BO3
behavior. External `model`, `xmodel`, and `skyboxmodel` references are listed in
reports. Unexpanded prefabs (`misc_prefab*` or model paths ending in `.map`) are
rejected by the shared validator, including when JSON is supplied directly.

## Brushes and faces

Each brush requires `faces`, with an optional `guid`. A brush needs at least four
faces. A face has exactly these fields:

```json
{
  "points": [[0, 0, 0], [128, 0, 0], [128, 128, 0]],
  "material": "caulk",
  "texture": [128, 128, 0, 0, 0, 0],
  "lightmap": {
    "material": "lightmap_gray",
    "texture": [16384, 16384, 0, 0, 0, 0]
  }
}
```

This fragment describes one plane, not a complete brush. The three ordered
points define a plane and need not be vertices of the final clipped polygon.
Point order is retained to preserve winding. Both six-number records are kept
positionally; Talos does not guess undocumented texture-flag meanings.

See [the complete synthetic map](../examples/synthetic_brush.map). Generate its
complete IR with `python -m talos import-map ... --name zm_talos_test --output ...`.

## Validation limits

- Numbers are finite Python integers/floats, with absolute value at most `1e9`.
  Text and JSON import reject underflow and decimal precision that would change
  when re-emitted from this representation. Equivalent spellings such as
  `0.10` and `1e-1` are accepted. The bound is a Talos resource/data policy, not a
  claimed engine limit.
- Plane points must be distinct/non-collinear. This does **not** prove the whole
  brush is closed, bounded, convex, correctly wound, or accepted by the compiler.
- Property strings have a 16,384-character policy limit. Control characters,
  unpaired surrogates, quotes and backslashes are rejected until target escape
  semantics are established.
- Material names must fit the supported unquoted token grammar. Names are not
  evidence that their target assets exist.
- Patches, meshes, standalone layer/flag directives, and structured model data
  are not represented. The importer rejects them rather than simplifying them.
- Input files are bounded by CLI size limits. Malformed/duplicate-key JSON and
  excessive nesting fail without creating an export directory.

## Export reporting

The exporter copies the IR before applying optional material mappings. Source and
target inventories are separate. If a material-map JSON is supplied, it must
explicitly name a target for every source brush material; identity mappings are
allowed. Lightmap records are preserved without this remapping.

Reports distinguish schema/text generation from unresolved target assets,
entity semantics, topology checks, Mod Tools compilation and game validation.
`source_exported` only certifies the supported source files were written.
`fastfile_written` remains `false` in this version.
