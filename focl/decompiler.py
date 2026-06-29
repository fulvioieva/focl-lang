"""Reconstruct source code from a ``.focl`` file (the round-trip direction).

FOCL claims to be a *lossless* semantic compression; ``focl decompile`` is the
proof: it asks the model to expand each compressed block back into idiomatic
source. When the ``.focl`` carries ``# src:`` annotations (the normal case),
each block is decompiled into its original path; otherwise the whole file is
reconstructed in one call and split on ``=== path ===`` headers.

The model call is delegated to :mod:`focl.providers`.
"""

from __future__ import annotations

import re
from typing import Callable

from . import index
from .providers import LLMConfig, generate_text

_MAX_OUTPUT_TOKENS = 16_000

_SYSTEM_PROMPT = """\
You are FOCL Decompiler — you reconstruct original source code from FOCL \
(Focus Compressed Language), a compact semantic representation of a codebase.

Given a FOCL block (or file) and the target language, output the full, idiomatic \
source it represents:
- Restore boilerplate the compressor omitted: imports/usings, constructors, \
  getters/setters, framework annotations, dependency-injection wiring, logging — \
  whatever is idiomatic for the language and framework.
- Expand FOCL primitives back into real code (e.g. OWNED_FETCH -> findById + \
  ownership check + 404; PERSIST -> repository save; SILENT_GUARD -> auth check \
  + 403; PAGE -> paginated query + sort + filter + DTO mapping).
- Preserve every business rule, validation, error code, state guard, endpoint, \
  and config key encoded in the FOCL.
- Output ONLY source code — no markdown fences, no commentary.
"""


def detect_language(focl_content: str) -> str | None:
    """Read the target language from a ``# Language: <lang>`` header line."""
    for line in index.header(focl_content).splitlines():
        m = re.match(r"#\s*Language:\s*(.+)", line)
        if m:
            # "java / spring-boot" -> "java"
            return m.group(1).split("/")[0].strip() or None
    return None


def decompile(focl_content: str,
              config: LLMConfig,
              lang: str | None = None,
              progress: Callable[[str], None] | None = None) -> dict[str, str]:
    """Return ``{source_path: reconstructed_code}`` for a ``.focl`` document."""
    language = lang or detect_language(focl_content) or "the original language"
    blocks = index.parse_focl_blocks(focl_content)

    if not blocks:
        return _decompile_whole(focl_content, config, language, progress)

    out: dict[str, str] = {}
    total = len(blocks)
    for i, (path, block) in enumerate(blocks.items(), start=1):
        _notify(progress, f"Decompiling {i}/{total}: {path}")
        out[path] = _decompile_block(config, language, path, block)
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _invoke(config: LLMConfig, user_message: str) -> str:
    return generate_text(config, _SYSTEM_PROMPT, user_message, _MAX_OUTPUT_TOKENS)


def _decompile_block(config: LLMConfig, language: str,
                     src_path: str, block: str) -> str:
    user_message = (
        f"Target language: {language}\n"
        f"Reconstruct the complete source file `{src_path}` from this FOCL block. "
        "Output only the source code for this one file.\n\n"
        f"{block}"
    )
    return _strip_fences(_invoke(config, user_message))


def _decompile_whole(focl_content: str, config: LLMConfig, language: str,
                     progress: Callable[[str], None] | None) -> dict[str, str]:
    _notify(progress, "No `# src:` blocks — reconstructing the whole project")
    user_message = (
        f"Target language: {language}\n"
        "Reconstruct the full source tree from the FOCL below. Output each file "
        "as a header line `=== relative/path.ext ===` immediately followed by "
        "its source code. No fences, no commentary.\n\n"
        f"{focl_content}"
    )
    return _split_files(_invoke(config, user_message))


def _split_files(text: str) -> dict[str, str]:
    """Parse model output laid out as ``=== path ===`` sections into a map."""
    files: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^===\s*(.+?)\s*===$", line)
        if m:
            if current is not None:
                files[current] = "\n".join(lines).strip() + "\n"
            current = m.group(1).strip()
            lines = []
        elif current is not None:
            lines.append(line)
    if current is not None:
        files[current] = "\n".join(lines).strip() + "\n"
    return files


def _strip_fences(text: str) -> str:
    """Remove a wrapping ``` ```lang ... ``` ``` fence if the model added one."""
    stripped = text.strip()
    if stripped.startswith("```"):
        body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if body.rstrip().endswith("```"):
            body = body.rstrip()[: -3]
        return body.strip() + "\n"
    return stripped + "\n" if stripped else ""
