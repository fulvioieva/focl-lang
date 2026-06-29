"""Index a generated ``.focl`` file by its ``# src:`` annotations.

The generator annotates every top-level block with a ``# src: path/to/File``
comment (see ``generator._SYSTEM_PROMPT``). This module turns that flat text
back into a ``{source_path: focl_block}`` mapping, which is the keystone for:

- the MCP server (serve a single module's compressed block on demand), and
- future surgical patching in ``generator.update()``.

Parsing is intentionally forgiving: anything before the first ``# src:`` marker
is treated as the file header/preamble, and each marker starts a new block that
runs until the next marker.
"""

from __future__ import annotations

_SRC_MARKER = "# src:"


def _src_path(line: str) -> str | None:
    """Return the path from a ``# src: <path>`` line, else None."""
    stripped = line.strip()
    if stripped.startswith(_SRC_MARKER):
        return stripped[len(_SRC_MARKER):].strip() or None
    return None


def header(content: str) -> str:
    """The preamble: everything before the first ``# src:`` block."""
    lines: list[str] = []
    for line in content.splitlines():
        if _src_path(line) is not None:
            break
        lines.append(line)
    return "\n".join(lines).strip()


def parse_focl_blocks(content: str) -> dict[str, str]:
    """Map each annotated source path to its FOCL block text.

    Blocks for a repeated path are concatenated. Lines before the first
    ``# src:`` marker are ignored here (see :func:`header`).
    """
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in content.splitlines():
        path = _src_path(line)
        if path is not None:
            current = path
            blocks.setdefault(current, [])
        if current is not None:
            blocks[current].append(line)
    return {p: "\n".join(lines).strip() for p, lines in blocks.items()}


def module_paths(content: str) -> list[str]:
    """Ordered, de-duplicated list of source paths present in the .focl."""
    seen: list[str] = []
    for line in content.splitlines():
        path = _src_path(line)
        if path is not None and path not in seen:
            seen.append(path)
    return seen


def get_module(content: str, path: str) -> str | None:
    """Return the FOCL block for ``path``.

    Falls back to a unique suffix match so callers can pass a short relative
    path (e.g. ``UserService.java``) and still hit ``src/.../UserService.java``.
    """
    blocks = parse_focl_blocks(content)
    if path in blocks:
        return blocks[path]
    norm = path.replace("\\", "/")
    matches = [
        block for key, block in blocks.items()
        if key.replace("\\", "/").endswith(norm)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def overview(content: str) -> str:
    """A compact orientation string: header + the list of available modules."""
    paths = module_paths(content)
    head = header(content)

    parts: list[str] = []
    if head:
        parts.append(head)

    if paths:
        listing = "\n".join(f"  - {p}" for p in paths)
        parts.append(
            f"Modules ({len(paths)}):\n{listing}\n\n"
            "Call focl_module(path) to fetch a module's compressed block."
        )
    else:
        # No `# src:` annotations — hand back the whole thing as the overview.
        parts.append(
            "No `# src:` module annotations found; the full .focl follows.\n\n"
            + content.strip()
        )
    return "\n\n".join(parts).strip()
