"""Shard a codebase into chunks that fit within the model's context window.

Large projects cannot be compressed in a single API call — they exceed the
input token limit and degrade response quality. The sharder groups related
files into shards that each stay under a configurable token budget.

Strategy:
- Files are grouped by top-level directory (module/package boundary).
- Within a module, files are bin-packed into shards using a first-fit
  decreasing heuristic based on estimated token count.
- If a single file exceeds the shard budget, it becomes its own shard
  (with a warning). Truly giant files should be split by the caller.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from .analyzer import ProjectInfo

# Default budget per shard: conservative to leave room for system prompt,
# instructions, and model output. Opus 4.7 accepts 1M input tokens, but
# quality and latency degrade well before that.
DEFAULT_SHARD_BUDGET = 80_000

# Characters-per-token heuristic used when the tokenizer is unavailable.
# Source code averages ~3.5 chars/token with the Claude tokenizer; we use
# 3.0 to stay conservative and avoid underestimation.
_CHARS_PER_TOKEN = 3.0


@dataclass
class Shard:
    """A group of files to be compressed together in a single API call."""
    index: int
    label: str                       # e.g. "service" or "controller" or "root"
    files: list[Path] = field(default_factory=list)
    token_estimate: int = 0

    @property
    def file_count(self) -> int:
        return len(self.files)


@dataclass
class ShardingResult:
    shards: list[Shard]
    total_tokens: int
    oversize_files: list[Path]       # files that alone exceed the budget


def count_tokens(text: str, api_key: str | None = None,
                 model: str = "claude-opus-4-7") -> int:
    """Count tokens using the Anthropic API when possible, else estimate.

    The API call is cheap (free, does not charge as a generation) but adds
    latency. Fall back to a character-based heuristic if the call fails
    or no API key is available.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return _estimate_tokens(text)
    try:
        client = anthropic.Anthropic(api_key=key)
        result = client.messages.count_tokens(
            model=model,
            messages=[{"role": "user", "content": text}],
        )
        return int(result.input_tokens)
    except Exception:
        return _estimate_tokens(text)


def _estimate_tokens(text: str) -> int:
    """Fast offline estimate of token count based on character length."""
    return int(len(text) / _CHARS_PER_TOKEN) + 1


def shard_project(info: ProjectInfo,
                  budget: int = DEFAULT_SHARD_BUDGET,
                  use_api_counter: bool = False,
                  api_key: str | None = None) -> ShardingResult:
    """Split the project files into shards respecting the token budget.

    Args:
        info: ProjectInfo from analyzer.detect()
        budget: Max estimated tokens per shard (default 80K)
        use_api_counter: If True, use the Anthropic count_tokens API for
            exact counts (slower, requires API key). Otherwise use a
            character-based estimate (fast, offline).
        api_key: Anthropic API key (only used when use_api_counter=True)

    Returns:
        ShardingResult with a list of shards and diagnostic info.
    """
    # Group files by top-level sub-directory relative to project root.
    # Files directly at root go into the "root" group.
    groups: dict[str, list[tuple[Path, str, int]]] = {}
    total_tokens = 0
    oversize: list[Path] = []

    for f in info.files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel = f.relative_to(info.root)
        parts = rel.parts
        group_key = parts[0] if len(parts) > 1 else "root"

        wrapped = f"=== {rel} ===\n{content}"
        if use_api_counter:
            tokens = count_tokens(wrapped, api_key=api_key)
        else:
            tokens = _estimate_tokens(wrapped)

        total_tokens += tokens

        if tokens > budget:
            oversize.append(f)

        groups.setdefault(group_key, []).append((f, wrapped, tokens))

    # Bin-pack each group using first-fit decreasing.
    shards: list[Shard] = []
    shard_index = 0

    for group_key, entries in sorted(groups.items()):
        # Sort entries by token count descending for better packing
        entries.sort(key=lambda e: e[2], reverse=True)

        current = Shard(index=shard_index, label=group_key)
        shard_index += 1

        for path, _wrapped, tokens in entries:
            if tokens > budget:
                # Oversize file: emit as its own shard, then continue.
                if current.files:
                    shards.append(current)
                    current = Shard(index=shard_index, label=group_key)
                    shard_index += 1
                lone = Shard(index=shard_index, label=f"{group_key}:oversize")
                shard_index += 1
                lone.files.append(path)
                lone.token_estimate = tokens
                shards.append(lone)
                continue

            if current.token_estimate + tokens > budget and current.files:
                shards.append(current)
                current = Shard(index=shard_index, label=group_key)
                shard_index += 1

            current.files.append(path)
            current.token_estimate += tokens

        if current.files:
            shards.append(current)

    return ShardingResult(
        shards=shards,
        total_tokens=total_tokens,
        oversize_files=oversize,
    )


def build_shard_context(shard: Shard, root: Path) -> str:
    """Build the text context for a single shard (files concatenated)."""
    parts: list[str] = []
    for f in shard.files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = f.relative_to(root)
        parts.append(f"=== {rel} ===\n{content}")
    return "\n\n".join(parts)
