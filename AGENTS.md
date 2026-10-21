# Working on Talos

## Binding project direction

The user's explicit goal is **direct BO1 `.ff` → BO3 `.ff` conversion**. Read
`README.md`, `docs/BINARY_PIPELINE.md`, and `docs/INTEGRATION.md` before changing
the architecture. This user constraint takes precedence over donor plans and
earlier repository documentation.

- Keep the path binary: T5 container/zone decoding, asset conversion, native T7
  zone serialization, and BO3 container output.
- Do not introduce Radiant, `.map` interchange, source export, Mod Tools
  compilation, or manual map re-authoring as the conversion path. The source
  detour in commit `18e6332` is superseded; do not restore it as a fallback.
- Use Hermes for verified BO1 decoding knowledge and Damocles for verified BO3
  binary knowledge where available. Inspect exact donor revisions and actual
  implementations before adopting code. A donor's different architecture does
  not redefine Talos.

## Implementation rules

- Separate container parsing, T5 asset decoding, conversion policy, native T7
  serialization, and target container writing. An internal asset representation
  must retain source identities, dependencies, and required semantics.
- Pin primary evidence for binary layouts, asset IDs, alignments, pointers,
  fixups, compression, and target loading rules. Do not guess missing details.
- Do not relabel a decompressed BO1 zone as BO3 output or treat a rewritten
  header as asset conversion. Unsupported assets and unresolved required
  dependencies are explicit errors.
- Current support is unsigned PC `IWffu100` version `473` inspection and bounded
  unpacking through the XFile size header. Keep unimplemented stages visible in
  documentation and CLI output; do not invent a working conversion command.
- Record source and output identities. Distinguish container checks, decoded
  assets, successful target serialization, loader acceptance, and game fidelity.
- Add focused regression tests for format/behavior changes. Run
  `python -m unittest discover -s tests -v` before publishing implementation work.
- Preserve the no-overwrite rule. Keep game archives, extracted content,
  generated output, and proprietary inputs out of commits.
