# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FOCL ("Focus Compressed Language") is a CLI that compresses an entire codebase into a single `.focl` file — a compact, AI-native representation that preserves architecture and business logic while using ~70–80% fewer tokens. It does this by sending source code to an LLM with a FOCL grammar prompt; it is not a parser/compiler and there is no local FOCL grammar implementation. The original source is never modified. The LLM provider is pluggable — Anthropic (default) or any OpenRouter model — via `focl/providers.py`.

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

Any command that compresses requires an API key — `ANTHROPIC_API_KEY` (default provider) or `OPENROUTER_API_KEY` (with `--provider openrouter`), or `--api-key`. `init`/`sync`/`watch`/`stats` accept `--provider {anthropic,openrouter}`, `--model`, `--base-url`. `focl plan` and the test suite run fully offline.

## Architecture

The pipeline flows in one direction across small single-purpose modules in `focl/`:

1. **`analyzer.py`** — `detect(root)` walks the tree, prunes ignored dirs/extensions, skips files over `_MAX_FILE_BYTES` (200 KB), and returns a `ProjectInfo` dataclass (language, framework, file list, sizes, skipped files). Language/framework are inferred from marker files (`pom.xml`, `package.json`, `pyproject.toml`, …) in `_LANG_RULES`. `build_context(info)` concatenates all sources into one `=== relpath ===\n<content>` blob — this delimiter format is the universal interchange shape used everywhere.

2. **`providers.py`** — The LLM abstraction and the **only** module that imports a vendor SDK. Holds `LLMConfig` (provider, model, api_key, base_url; resolves per-provider defaults and the right `*_API_KEY` env var), `generate_text()` (branches Anthropic `messages.stream` + adaptive thinking vs OpenRouter OpenAI-compatible `chat.completions`), `count_tokens()` (exact only on Anthropic, else estimate), and `estimate_tokens()` (chars / `_CHARS_PER_TOKEN` = 3.0). `openai` is an optional dep (`pip install -e ".[openrouter]"`), imported lazily with a friendly error.

3. **`sharder.py`** — Large projects can't fit in one API call. `shard_project()` groups files by top-level directory, then bin-packs each group (first-fit decreasing) into shards under a token `budget` (`DEFAULT_SHARD_BUDGET = 80_000`). A file exceeding the budget alone becomes its own `oversize` shard. Token counting delegates to `providers.count_tokens`/`estimate_tokens` (re-exported as `_estimate_tokens` for tests).

4. **`generator.py`** — Orchestrates compression. `generate()` estimates total size; if under `_SINGLE_CALL_THRESHOLD` (60K) it compresses in one call, otherwise it shards, compresses each shard, and merges with a header. `update()` powers `watch` — it sends the existing `.focl` plus changed files and asks the model to patch only the affected blocks (located by `# src:` annotations). All calls go through `_invoke()` → `providers.generate_text()`. The FOCL grammar lives entirely in `_SYSTEM_PROMPT` here; the actual LLM call is in `providers.py`.

5. **`metrics.py`** — `measure()` / `measure_from_paths()` compute token- and byte-based compression stats into `CompressionMetrics`. Token counts reuse `providers.count_tokens` / `estimate_tokens` so estimates stay consistent across the codebase.

6. **`watcher.py`** — `watch()` uses watchdog with a debounced handler that coalesces rapid events. It deliberately ignores `.focl` files (to avoid self-triggered rebuild loops) and reuses the analyzer's ignore sets. On change it calls back into `generator.update()`.

7. **`cli.py`** — Click command group wiring the above together with `rich` for progress/tables. The shared `--provider/--model/--api-key/--base-url` options are applied via the `_llm_options` decorator and turned into an `LLMConfig` by `_build_config`. Note `watch` is defined as `watch_cmd` and registered with `name="watch"` (the name avoids shadowing the imported `watch` function).

### Key cross-module conventions

- **`ProjectInfo` and the `=== relpath ===` block format** are the shared contracts; analyzer produces them (`wrap_file`), generator/sharder/metrics consume them.
- **`LLMConfig` is threaded everywhere** an LLM call or token count happens (`generate`, `update`, `shard_project`, `measure`). Functions still accept a legacy `api_key=` for convenience but build a default Anthropic config from it.
- **Token counting is centralized** in `providers.count_tokens` / `estimate_tokens`. Reuse these rather than re-deriving estimates, so all reported numbers stay consistent.
- **Model/provider and grammar:** model defaults live in `providers.DEFAULT_MODELS`; the FOCL grammar is `generator._SYSTEM_PROMPT`. Changing FOCL output means editing `_SYSTEM_PROMPT`, not adding parser code. Adding a provider only touches `providers.py`.

## Testing notes

Tests cover the offline machinery only (analyzer, sharder, metrics estimates, watcher, `cli plan`); they do **not** call or mock the LLM generation API, so `generator`/`providers.generate_text` behaviour is untested. Fixtures in `tests/conftest.py` build minimal throwaway projects (Spring Boot, Python, ignored-files, oversize-file) under `tmp_path`. CI runs the suite on Python 3.10–3.12 across Linux/macOS/Windows.

## Versioning

The version is duplicated in `focl/__init__.py` (`__version__`) and `pyproject.toml` — keep them in sync when releasing. The generated sharded-file header reads `__version__` and the provider/model used.
