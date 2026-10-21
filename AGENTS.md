# Working on Talos

The goal is faithful BO1-to-BO3 map conversion, preserving content and reporting
every unsupported dependency. Read README.md and docs/INTEGRATION.md first.

- Keep BO1 decoding, the versioned IR, and BO3 output separate. Reuse verified
  donor implementations once their actual source and interfaces are available.
- Pin primary format evidence. Never infer engine layouts from names alone.
- Do not relabel a decompressed BO1 zone as a BO3 fastfile, treat header rewriting
  as asset conversion, or report synthetic fixtures as retail map validation.
- Preserve geometry, texture records, entity data and dependencies. Reject
  unsupported source structures until the IR/writer can represent them.
- Reports must distinguish source export, asset conversion, compilation, and
  in-game validation. Keep missing stages visible in README and command output.
- Add focused regression tests for real format/behavior changes. Run
  `python -m unittest discover -s tests -v` before publishing implementation work.
- Keep generated output and locally supplied game archives out of commits.
- Maintain the no-overwrite rule for user-selected output paths.
