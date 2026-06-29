# FOCL — Claude Code plugin

Read your codebase through a token-compressed [FOCL](https://github.com/fulvioieva/focl-lang)
map instead of the raw source, directly inside Claude Code.

## What it adds

| Component | What it does |
|---|---|
| **MCP server** (`focl`) | Tools `focl_overview`, `focl_list_modules`, `focl_module(path)` and the `focl://project` resource — pull the *compressed* representation on demand. |
| **Skill** (`focl`) | Tells Claude to consult the map for architecture/overview questions before reading source. |
| **Commands** | `/focl:focl-sync` (regenerate the map), `/focl:focl-decompile` (round-trip back to source). |
| **Hook** | `SessionStart` runs `focl check` and reports if the map is stale. |

## Prerequisites

The plugin is the Claude Code glue; the engine is the `focl` CLI:

```bash
pip install "focl[mcp]"
focl init .          # generate <project>.focl (needs ANTHROPIC_API_KEY or OPENROUTER_API_KEY)
```

## Install

```text
/plugin marketplace add fulvioieva/focl-lang
/plugin install focl@focl-lang
```

Then restart Claude Code so the MCP server and SessionStart hook load.

The MCP server runs `focl mcp .` against your current project, re-reading the
`.focl` on every call — so edits from `focl sync` / `focl watch` show up live.
