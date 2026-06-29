# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FOCL ("Focus Compressed Language") is a CLI that compresses an entire codebase into a single `.focl` file — a compact, AI-native representation that preserves architecture and business logic while using ~70–80% fewer tokens. It does this by sending source code to the Anthropic API with a FOCL grammar prompt; it is not a parser/compiler and there is no local FOCL grammar implementation. The original source is never modified.

## Commands

```bash
pip install -e ".[dev]"          # install with dev deps (pytest, pytest-cov, ruff)

pytest tests/ -v --tb=short      # run the full test suite (matches CI)
pytest tests/test_sharder.py     # run one test file
pytest tests/test_sharder.py::test_name -v   # run a single test

ruff check focl/                 # lint (CI lints focl/ only, line-length 100)
```

The CLI itself (entry point `focl = focl.cli:main`):

```bash
focl init [path]     # analyse a codebase and generate <project>.focl  (--force to overwrite)
focl sync [path]     # full regeneration from scratch
focl watch [path]    # watch sources and incrementally patch the .focl
focl stats [path]    # show compression metrics for an existing .focl
focl plan [path]     # preview the sharding plan WITHOUT calling the API (offline, free)
```

Any command that compresses requires an Anthropic API key via `ANTHROPIC_API_KEY` or `--api-key`. `focl plan` and the test suite run fully offline.

## Architecture

The pipeline flows in one direction across small single-purpose modules in `focl/`:

1. **`analyzer.py`** — `detect(root)` walks the tree, prunes ignored dirs/extensions, skips files over `_MAX_FILE_BYTES` (200 KB), and returns a `ProjectInfo` dataclass (language, framework, file list, sizes, skipped files). Language/framework are inferred from marker files (`pom.xml`, `package.json`, `pyproject.toml`, …) in `_LANG_RULES`. `build_context(info)` concatenates all sources into one `=== relpath ===\n<content>` blob — this delimiter format is the universal interchange shape used everywhere.

2. **`sharder.py`** — Large projects can't fit in one API call. `shard_project()` groups files by top-level directory, then bin-packs each group (first-fit decreasing) into shards under a token `budget` (`DEFAULT_SHARD_BUDGET = 80_000`). A file exceeding the budget alone becomes its own `oversize` shard. Token counting goes through `count_tokens()` which calls the Anthropic `count_tokens` API when a key is present and falls back to `_estimate_tokens()` (chars / `_CHARS_PER_TOKEN` = 3.0) offline.

3. **`generator.py`** — The only module that performs paid API generation. `generate()` estimates total size; if under `_SINGLE_CALL_THRESHOLD` (60K) it compresses in one call, otherwise it shards, compresses each shard, and merges with a header. `update()` powers `watch` — it sends the existing `.focl` plus changed files and asks the model to patch only the affected blocks (located by `# src:` annotations). All calls go through `_invoke()`, which streams (`messages.stream` with adaptive thinking) and concatenates text blocks. The FOCL grammar lives entirely in `_SYSTEM_PROMPT` here.

4. **`metrics.py`** — `measure()` / `measure_from_paths()` compute token- and byte-based compression stats into `CompressionMetrics`. Token counts reuse `sharder.count_tokens` / `_estimate_tokens` so estimates stay consistent across the codebase.

5. **`watcher.py`** — `watch()` uses watchdog with a debounced handler that coalesces rapid events. It deliberately ignores `.focl` files (to avoid self-triggered rebuild loops) and reuses the analyzer's ignore sets. On change it calls back into `generator.update()`.

6. **`cli.py`** — Click command group wiring the above together with `rich` for progress/tables. Note `watch` is defined as `watch_cmd` and registered with `name="watch"`.

### Key cross-module conventions

- **`ProjectInfo` and the `=== relpath ===` block format** are the shared contracts; analyzer produces them, generator/sharder/metrics consume them.
- **Token counting is centralized** in `sharder.count_tokens` / `_estimate_tokens`. Reuse these rather than re-deriving estimates, so all reported numbers stay consistent.
- **The model and grammar** are constants in `generator.py` (`_MODEL`, `_SYSTEM_PROMPT`) and `sharder.py` (`count_tokens` default model). Changing FOCL output means editing `_SYSTEM_PROMPT`, not adding parser code.

## Testing notes

Tests cover the offline machinery only (analyzer, sharder, metrics estimates, watcher, `cli plan`); they do **not** call or mock the Anthropic generation API, so `generator._invoke`/`generate` API behaviour is untested. Fixtures in `tests/conftest.py` build minimal throwaway projects (Spring Boot, Python, ignored-files, oversize-file) under `tmp_path`. CI runs the suite on Python 3.10–3.12 across Linux/macOS/Windows.

## Versioning

The version is duplicated in `focl/__init__.py` (`__version__`) and `pyproject.toml` — keep them in sync when releasing. (There is also a stale `focl v0.1.0` string in `generator._compress_sharded`'s header.)
