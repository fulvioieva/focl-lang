"""Compression metrics measured in actual tokens, not bytes.

Byte-based compression ratios are misleading because the whole point of
FOCL is to save *tokens* in an LLM's context window — and tokenisation is
not proportional to byte count (source code compresses differently from
prose; identifiers vs keywords vs whitespace all tokenise at different
rates).

This module counts tokens using the Anthropic API when available and
falls back to a character-based heuristic otherwise, so metrics work
offline too.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .analyzer import ProjectInfo, build_context
from .sharder import count_tokens


@dataclass
class CompressionMetrics:
    """Token-accurate measurement of a FOCL compression run."""
    source_tokens: int
    focl_tokens: int
    source_bytes: int
    focl_bytes: int
    exact: bool            # True if counted via API, False if estimated

    @property
    def token_ratio(self) -> float:
        """How many times smaller the FOCL version is (e.g. 5.2x)."""
        return self.source_tokens / self.focl_tokens if self.focl_tokens else 0.0

    @property
    def token_saving_pct(self) -> float:
        """Percent of tokens saved, 0-100."""
        if not self.source_tokens:
            return 0.0
        return (1 - self.focl_tokens / self.source_tokens) * 100

    @property
    def byte_ratio(self) -> float:
        return self.source_bytes / self.focl_bytes if self.focl_bytes else 0.0

    @property
    def byte_saving_pct(self) -> float:
        if not self.source_bytes:
            return 0.0
        return (1 - self.focl_bytes / self.source_bytes) * 100


def measure(info: ProjectInfo, focl_content: str,
            api_key: str | None = None,
            exact: bool = False) -> CompressionMetrics:
    """Measure compression for a given codebase and its FOCL output.

    Args:
        info: Project info (source files + total bytes)
        focl_content: The generated .focl text
        api_key: Anthropic API key for exact token counting
        exact: If True, use the Anthropic API for precise counts. This
            costs no generation tokens but does add latency and requires
            a valid API key. If False, use an offline heuristic.

    Returns:
        CompressionMetrics with both token and byte measurements.
    """
    source_text = build_context(info)
    source_bytes = len(source_text.encode("utf-8"))
    focl_bytes = len(focl_content.encode("utf-8"))

    if exact:
        source_tokens = count_tokens(source_text, api_key=api_key)
        focl_tokens = count_tokens(focl_content, api_key=api_key)
    else:
        # Reuse the estimator from sharder so heuristics stay consistent
        from .sharder import _estimate_tokens
        source_tokens = _estimate_tokens(source_text)
        focl_tokens = _estimate_tokens(focl_content)

    return CompressionMetrics(
        source_tokens=source_tokens,
        focl_tokens=focl_tokens,
        source_bytes=source_bytes,
        focl_bytes=focl_bytes,
        exact=exact,
    )


def measure_from_paths(source_info: ProjectInfo,
                       focl_path: Path,
                       api_key: str | None = None,
                       exact: bool = False) -> CompressionMetrics:
    """Convenience wrapper when the .focl file already exists on disk."""
    focl_content = focl_path.read_text(encoding="utf-8")
    return measure(source_info, focl_content, api_key=api_key, exact=exact)
