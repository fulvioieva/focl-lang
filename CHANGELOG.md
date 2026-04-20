# Changelog

All notable changes to FOCL are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
FOCL uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Versioning convention

| Level | When to bump | Example trigger |
|---|---|---|
| PATCH `0.1.x` | Bug fix, test fix, docs, CI | Fix Windows CRLF in tests |
| MINOR `0.x.0` | New feature, backward-compatible | New `focl validate` command |
| MAJOR `x.0.0` | Breaking change to `.focl` format or CLI API | Grammar syntax change |
| `1.0.0` | Stable grammar + verified round-trip + 10+ real benchmarks | — |

---

## [Unreleased]

### Planned
- `focl validate` — verify `.focl` file structure and primitive usage
- `focl decompile` — reconstruct source from `.focl` (round-trip proof)
- Surgical patch in `update()` — patch only blocks affected by changed files
- File → FOCL block mapping parser (`# src:` annotation index)
- Externalise system prompts to `focl/prompts/` as loadable resources

---

## [0.1.2] — 2026-04-20

### Fixed
- **Windows CRLF byte-count mismatch** in `tests/test_metrics.py`
  (`TestMeasureFromPaths.test_reads_focl_from_disk`): `write_text()` on Windows
  converts `\n` to `\r\n`, inflating `stat().st_size` by 1 byte per newline.
  Test now compares `focl_bytes` against `len(content.encode("utf-8"))` for
  cross-platform consistency. Affected CI job: Python 3.11 / Windows.

---

## [0.1.1] — 2026-04-20

### Fixed
- **Missing `focl/metrics.py`** — module was generated and validated locally
  but not committed to the repository. `focl/cli.py` and
  `tests/test_metrics.py` both import from it, causing `ModuleNotFoundError`
  in CI on all platforms.

### Added
- `focl/metrics.py` added to repository.

---

## [0.1.0] — 2026-04-20

Initial public release.

### Added

#### Core package

- **`focl/analyzer.py`** — language/framework detection (Java/Spring Boot,
  Kotlin, TypeScript, JavaScript, Python, Go, Ruby, PHP, C#) and source file
  collection with ignore rules for `node_modules`, `.venv`, build artefacts,
  and binary extensions. `ProjectInfo.skipped_files` tracks files excluded
  due to size limit with human-readable reason string.

- **`focl/sharder.py`** — token-aware sharding for large codebases.
  Groups files by top-level directory, applies first-fit decreasing bin-packing
  to respect a configurable per-shard token budget (default 80 K). Files
  exceeding the budget alone become isolated shards labelled `:oversize`.
  Token counting via Anthropic `count_tokens` API (exact) or character-based
  heuristic (offline, ~3 chars/token).

- **`focl/generator.py`** — compression engine. Single-call path for projects
  under 60 K estimated tokens; sharded path with per-shard compression and
  header merge for larger projects. Uses Claude Opus 4.7 with adaptive
  thinking. System prompt instructs model to annotate each block with
  `# src: path/to/file` for future surgical patching.

- **`focl/metrics.py`** — token-accurate compression measurement.
  `CompressionMetrics` dataclass exposes `token_ratio`, `token_saving_pct`,
  `byte_ratio`, `byte_saving_pct`. Supports exact (API) and estimated
  (offline) modes.

- **`focl/watcher.py`** — file system watcher with debounce. Filters
  `.focl` files from change events to prevent infinite update loops.
  Handles `on_moved` events for rename/refactoring workflows.

- **`focl/cli.py`** — Click-based CLI with five commands:
  - `focl init` — analyse codebase and generate `.focl`
  - `focl sync` — full regeneration from scratch
  - `focl watch` — incremental update on file changes
  - `focl stats` — compression statistics (token + byte metrics)
  - `focl plan` — preview sharding plan without API calls

  Options: `--shard-budget`, `--exact-tokens`, `--force`, `--debounce`.
  Skipped-files warning shown at startup when files exceed size limit.

#### FOCL grammar — initial primitive set

| Primitive | Replaces |
|---|---|
| `ENTITY … FROM … WITH` | Constructor + field assignment |
| `OWNED_FETCH` | findById + ownership check + 404 |
| `TRANSITION` | State-machine transition + guard |
| `SILENT_GUARD` | Auth/permission check + 403 |
| `PAGE` | Paginated query + sort + filter + DTO |
| `PERSIST` | Repository save + flush |
| `NOTIFY` | Event/notification dispatch |
| `MAP` | DTO/ViewModel mapping |
| `PATCH` | Partial entity update (non-null fields) |
| `UPLOAD` | File upload to object storage |
| `INJECT` | Dependency injection declarations |

#### Supported languages

Java · Kotlin · TypeScript · JavaScript · Python · Go · Ruby · PHP · C#

#### Test suite

52 tests across 5 modules, 0 failures. CI matrix: Python 3.10 / 3.11 / 3.12
× Ubuntu / macOS / Windows. Separate ruff lint job.

| File | Tests | Coverage |
|---|---|---|
| `test_analyzer.py` | 16 | Language detection, file collection, `skipped_files` |
| `test_sharder.py` | 13 | Bin-packing, budget enforcement, oversize at two levels |
| `test_metrics.py` | 8 | Metrics properties, `measure()`, edge cases |
| `test_watcher.py` | 9 | Event filtering, debounce coalescing |
| `test_cli.py` | 6 | CLI smoke tests (`plan`, `stats`, help, version) |

#### Documentation

- `README.md` — before/after example, primitive table, token savings table,
  roadmap, contributing guide
- `docs/WHITEPAPER.md` — problem statement, methodology, empirical results,
  grammar specification, implications
- `CONTRIBUTING.md` — primitive proposal process, language support guide,
  benchmark contribution format, development setup
- `CHANGELOG.md` — this file
- `LICENSE` — Apache 2.0

### Fixed (pre-release)

- `pyproject.toml`: `build-backend` corrected from non-existent
  `"setuptools.backends.legacy:build"` to `"setuptools.build_meta"`.
  `pip install -e .` was failing on all platforms.
- `focl/watcher.py`: `.focl` files excluded from change detection to prevent
  infinite update loop when the output file lives inside the watched tree.
- `focl/generator.py`: removed unused `Shard` import (ruff F401).
- `focl/cli.py`: removed extraneous `f` prefix on string without placeholders
  (ruff F541).

---

## How to release a new version

### 1. Update version in `pyproject.toml` and `focl/__init__.py`

```python
# focl/__init__.py
__version__ = "0.1.3"  # bump here
```

```toml
# pyproject.toml
[project]
version = "0.1.3"      # and here
```

### 2. Update CHANGELOG.md

Move items from `[Unreleased]` to a new dated section:

```markdown
## [0.1.3] — 2026-05-01

### Added
- ...

### Fixed
- ...
```

### 3. Commit, tag, push

```bash
git add focl/__init__.py pyproject.toml CHANGELOG.md
git commit -m "chore: release v0.1.3"
git tag -a v0.1.3 -m "Release v0.1.3"
git push origin main --tags
```

### 4. Create GitHub Release

Go to **Releases → Draft a new release**, select the tag `v0.1.3`, paste the
relevant CHANGELOG section as the release body, publish.

### 5. (Optional) Publish to PyPI

```bash
pip install build twine
python -m build
twine upload dist/*
```

---

*This project adheres to [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).*
