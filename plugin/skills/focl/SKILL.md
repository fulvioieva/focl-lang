---
name: focl
description: Use the compressed FOCL codebase map for architecture, overview, or "where is X" questions before grepping or reading source files. Refresh it with `focl sync` when stale.
---

# FOCL codebase map

This project ships a token-compressed map of its source — a `.focl` file
(typically `<project>.focl`), ~70–80% smaller than the original code.

## When to use it

For questions about **architecture, structure, data flow, or "where does X
happen"**, consult the map first instead of reading whole source files:

- If the **`focl` MCP server** is connected, call `focl_overview` to orient,
  then `focl_module(path)` for the compressed block of a specific file. Use
  `focl_list_modules` to see what's available.
- Otherwise, read the `.focl` file directly.

Only drop to the actual source files for **line-level changes** or details the
map doesn't capture (exact formatting, comments, generated code).

## Keeping it fresh

The `SessionStart` hook runs `focl check` and will tell you if the map is stale.
When it is — or after significant edits — regenerate it:

```bash
focl sync
```

## Requirements

The map and tools are powered by the `focl` CLI: `pip install "focl[mcp]"`.
