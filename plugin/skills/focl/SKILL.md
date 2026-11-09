---
name: focl
description: Use the compressed FOCL codebase map for architecture, overview, or "where is X" questions before grepping or reading source files. Refresh stale modules with `focl sync --changed`.
---

# FOCL codebase map

This project ships a token-compressed map of its source — a `.focl` file
(typically `<project>.focl`), ~70–80% smaller than the original code.

## When to use it

For questions about **architecture, structure, data flow, or "where does X
happen"**, consult the map first instead of reading whole source files:

- If the **`focl` MCP server** is connected, call `focl_overview` to orient.
  For "where does X happen", call `focl_search(query)` first — it's far
  cheaper than grepping the source. Then `focl_module(path)` (or
  `focl_modules([...])`) for the compressed blocks you need.
- Otherwise, read the `.focl` file directly.

A block prefixed with **`[STALE]`** (or a module listed as stale by the
session-start check) no longer matches its source file: read the real file for
that module instead of trusting the map.

Only drop to the actual source files for **line-level changes** or details the
map doesn't capture (exact formatting, comments, generated code).

## Keeping it fresh

The `SessionStart` hook runs `focl check` and lists exactly which modules are stale.
To refresh just those (one model call per changed file, the rest untouched):

```bash
focl sync --changed            # add --dry-run to preview, no API call
```

A full `focl sync` regenerates the whole map — use it only when asked, or when
`--changed` reports the map has no per-module hashes.

## Requirements

The map and tools are powered by the `focl` CLI: `pip install "focl[mcp]"`.
