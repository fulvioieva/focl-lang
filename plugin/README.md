# FOCL — Claude Code plugin

Read your codebase through a token-compressed [FOCL](https://github.com/fulvioieva/focl-lang)
map instead of the raw source, directly inside Claude Code.

## What it adds

| Component | What it does |
|---|---|
| **MCP server** (`focl`) | Tools `focl_overview`, `focl_list_modules`, `focl_module(path)`, `focl_modules(paths)`, `focl_search(query)` and the `focl://project` resource — pull the *compressed* representation on demand; modules whose source changed are flagged `[STALE]`. |
| **Skill** (`focl`) | Tells Claude to consult the map for architecture/overview questions before reading source. |
| **Subagent** (`focl-explorer`) | Answers broad architecture / "where does X happen" questions from the map in its own context, returning only the answer and the source paths. Limited to the FOCL MCP tools plus read-only `Read`/`Grep`/`Glob` (for stale modules). |
| **Commands** | `/focl:focl-sync` (regenerate the map), `/focl:focl-decompile` (round-trip back to source). |
| **Hook** | `SessionStart` runs `focl check --hook` and lists which modules are stale (silent in projects without a map). |

The plugin is safe to enable globally: in projects with no `.focl` the hook stays
silent and the MCP server starts anyway, answering that there's no map yet.

Don't combine it with `focl claude-setup` in the same project — that would
register the MCP server and the hook twice. `claude-setup` detects the enabled
plugin and then writes only the `CLAUDE.md` pointer.

## Does it help?

`evals/` holds a `claude plugin eval` suite that runs each question with and
without the plugin and compares quality and cost — see
[`evals/README.md`](evals/README.md) for how to run it and the first results.

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
