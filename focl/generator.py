"""FOCL generator: compresses a codebase into .focl format via an LLM.

For large codebases, the generator shards the project into chunks that each
fit within the model's context window, compresses each shard separately,
and merges the results into a single .focl file.

The actual LLM call is delegated to :mod:`focl.providers`, so the same
generation logic works against Anthropic or any OpenRouter model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import __version__, index
from .analyzer import ProjectInfo, build_context, wrap_file
from .providers import LLMConfig, estimate_tokens, generate_text
from .sharder import (
    DEFAULT_SHARD_BUDGET,
    ShardingResult,
    build_shard_context,
    shard_project,
)

_MAX_OUTPUT_TOKENS = 16_000

# Threshold below which we skip sharding and send the whole codebase in a
# single call. Sharding adds overhead (multiple API calls, merge step), so
# it's only worth it for projects that would exceed a single call's budget.
_SINGLE_CALL_THRESHOLD = 60_000

_SYSTEM_PROMPT = """\
You are FOCL Generator — an expert at compressing software codebases into FOCL \
(Focus Compressed Language), an AI-native representation that minimises tokens \
while preserving every architectural and behavioural detail an AI assistant needs \
to reason about, modify, or extend the codebase.

FOCL grammar rules:
- Use blocks: CONFIG, SECURITY, JWT, ERRORS, ENUM, ENTITY, DTO/REC/REQ, REPO, SERVICE, CTRL
- Inside blocks use compressed primitives:
    OWNED_FETCH(repo, by=field)   — ownership-scoped query
    TRANSITION(from->to, guard?)  — state machine transition
    SILENT_GUARD(condition)       — security/auth guard that throws silently
    FILTER_*(field, op)           — query filter shorthand
    PAGE(field)                   — paginated result
    PRESIGN_URL(bucket, key, ttl) — S3/storage presigned URL
    PATCH(entity, fields[])       — partial update
    PARSE_ENUM(raw, type)         — safe enum parsing
    OTP_FLOW(channel, ttl)        — OTP send/verify cycle
    ISSUE_SESSION(subject, roles) — JWT/session issuance
- Annotate each top-level block with its source file as a comment:
    # src: path/to/File.java
- Omit: boilerplate constructors, getters/setters, logger declarations, \
  trivial mappers, framework annotations that are obvious from context.
- Keep: every business rule, validation, error code, ownership check, \
  state guard, external integration endpoint, and config key.
- Format output as plain text FOCL — no markdown, no fences, no explanation.
- Start directly with the first block (e.g. CONFIG{...}).
"""

_SHARD_USER_PREFIX = (
    "This is shard {idx} of {total} from project '{project}' "
    "({lang}{fw_suffix}).\n"
    "Shard label: {label}\n"
    "Files in this shard: {file_count}\n\n"
    "Convert ONLY the files below into FOCL. Apply maximum compression.\n"
    "Do not reference files from other shards. Output FOCL only.\n\n"
)


def generate(info: ProjectInfo,
             api_key: str | None = None,
             shard_budget: int = DEFAULT_SHARD_BUDGET,
             use_api_counter: bool = False,
             progress: Callable[[str], None] | None = None,
             config: LLMConfig | None = None) -> str:
    """Call the configured LLM and return the .focl content.

    For small codebases, sends a single request. For large ones, shards
    the project and merges the results.

    Args:
        info: ProjectInfo from analyzer.detect()
        api_key: API key (used when no config is supplied; falls back to the
            provider's env var)
        shard_budget: Max estimated tokens per shard (default 80K)
        use_api_counter: Use the provider's exact token counter for sizing
        progress: Optional callback invoked with human-readable status messages
        config: Provider/model configuration. Defaults to Anthropic.

    Returns:
        The complete .focl file content as a string.
    """
    config = config or LLMConfig(api_key=api_key)
    config.require_api_key()  # fail fast before doing any work

    # Decide between single-call and sharded compression based on a quick
    # estimate of the full context.
    full_context = build_context(info)
    estimated_tokens = estimate_tokens(full_context)

    if estimated_tokens <= _SINGLE_CALL_THRESHOLD:
        _notify(progress, f"Single-call compression ({estimated_tokens:,} est. tokens)")
        return _compress_single(config, info, full_context)

    # Sharded path
    _notify(progress, f"Codebase is large ({estimated_tokens:,} est. tokens) — sharding")
    result = shard_project(
        info, budget=shard_budget,
        use_api_counter=use_api_counter, config=config,
    )
    _notify(progress, f"Split into {len(result.shards)} shards")

    if result.oversize_files:
        names = ", ".join(f.name for f in result.oversize_files[:3])
        extra = f" (+{len(result.oversize_files) - 3})" if len(result.oversize_files) > 3 else ""
        _notify(progress, f"Warning: {len(result.oversize_files)} file(s) exceed budget alone: {names}{extra}")

    return _compress_sharded(config, info, result, progress)


def update(focl_path: Path, changed_files: list[Path], root: Path,
           api_key: str | None = None,
           config: LLMConfig | None = None) -> str:
    """Patch an existing .focl file given a list of changed source files.

    Surgical by default: each changed file's FOCL block (located by its
    ``# src:`` annotation) is regenerated and spliced back in place — the rest
    of the file is left byte-for-byte unchanged, and only the changed files are
    sent to the model. Deleted files drop their block; new files append one.

    Falls back to a whole-file rewrite when the existing ``.focl`` carries no
    ``# src:`` annotations to target.
    """
    config = config or LLMConfig(api_key=api_key)
    config.require_api_key()

    existing = focl_path.read_text(encoding="utf-8")

    if not index.module_paths(existing):
        return _update_whole(config, existing, changed_files, root)

    replacements: dict[str, str] = {}
    deletions: list[str] = []
    for f in changed_files:
        rel = _rel_path(f, root)
        if not f.exists():
            deletions.append(rel)
            continue
        content = f.read_text(encoding="utf-8", errors="replace")
        replacements[rel] = _compress_file_block(config, rel, content)

    return index.splice_blocks(existing, replacements, deletions)


def _rel_path(f: Path, root: Path) -> str:
    """Forward-slashed path of ``f`` relative to ``root`` (falls back to name)."""
    try:
        return str(f.relative_to(root)).replace("\\", "/")
    except ValueError:
        return f.name


def _compress_file_block(config: LLMConfig, rel_path: str, content: str) -> str:
    """Regenerate the FOCL block for a single source file."""
    user_message = (
        "Convert ONLY the single source file below into one FOCL block.\n"
        f"Begin the block with `# src: {rel_path}` exactly.\n"
        "Apply maximum compression. Output FOCL only — no fences, no other files.\n\n"
        + wrap_file(rel_path, content)
    )
    block = _invoke(config, user_message)
    if not block.lstrip().startswith("# src:"):
        block = f"# src: {rel_path}\n{block}"
    return block


def _update_whole(config: LLMConfig, existing: str,
                  changed_files: list[Path], root: Path) -> str:
    """Whole-file rewrite fallback for .focl files without `# src:` blocks."""
    changed_content_parts: list[str] = []
    for f in changed_files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            changed_content_parts.append(wrap_file(_rel_path(f, root), content))
        except OSError:
            changed_content_parts.append(f"=== {f.name} === [DELETED]")

    changed_content = "\n\n".join(changed_content_parts)
    user_message = (
        "Below is the current .focl file, followed by the updated source files.\n"
        "Update only the affected parts and keep everything else unchanged.\n"
        "Output the complete updated .focl file only.\n\n"
        f"## Current .focl\n{existing}\n\n"
        f"## Changed files\n{changed_content}"
    )
    return _invoke(config, user_message)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _compress_single(config: LLMConfig,
                     info: ProjectInfo,
                     context: str) -> str:
    user_message = (
        f"Project: {info.root.name}\n"
        f"Language: {info.language}"
        + (f" / {info.framework}" if info.framework else "")
        + f"\nFiles: {len(info.files)}\n\n"
        "Convert the entire codebase below into a single FOCL file. "
        "Apply maximum compression. Output FOCL only.\n\n"
        f"{context}"
    )
    return _invoke(config, user_message)


def _compress_sharded(config: LLMConfig,
                      info: ProjectInfo,
                      result: ShardingResult,
                      progress: Callable[[str], None] | None) -> str:
    fw_suffix = f"/{info.framework}" if info.framework else ""
    compressed_shards: list[str] = []
    total = len(result.shards)

    for i, shard in enumerate(result.shards, start=1):
        _notify(
            progress,
            f"Shard {i}/{total} [{shard.label}] — {shard.file_count} files, "
            f"{shard.token_estimate:,} est. tokens"
        )
        shard_context = build_shard_context(shard, info.root)
        user_message = _SHARD_USER_PREFIX.format(
            idx=i,
            total=total,
            project=info.root.name,
            lang=info.language,
            fw_suffix=fw_suffix,
            label=shard.label,
            file_count=shard.file_count,
        ) + shard_context

        compressed = _invoke(config, user_message)
        compressed_shards.append(
            f"# ── shard {i}/{total}: {shard.label} "
            f"({shard.file_count} files) ──\n{compressed}"
        )

    header = (
        f"# FOCL file for project: {info.root.name}\n"
        f"# Language: {info.language}{fw_suffix}\n"
        f"# Source files: {len(info.files)} in {total} shards\n"
        f"# Generated by focl v{__version__} ({config.provider}: {config.model})\n"
    )
    return header + "\n\n" + "\n\n".join(compressed_shards)


def _invoke(config: LLMConfig, user_message: str) -> str:
    """Invoke the configured model and return its text output."""
    return generate_text(config, _SYSTEM_PROMPT, user_message, _MAX_OUTPUT_TOKENS)
