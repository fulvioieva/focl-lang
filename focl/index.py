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


def _norm(path: str | None) -> str | None:
    return None if path is None else path.replace("\\", "/")


def split_segments(content: str) -> list[tuple[str | None, str]]:
    """Split a .focl into ordered ``(src_path | None, raw_text)`` segments.

    The first segment (path ``None``) is the preamble; each ``# src:`` line
    starts a new segment that runs until the next marker. Joining the texts
    reproduces ``content`` byte-for-byte, so segments are safe to splice.
    """
    segments: list[tuple[str | None, str]] = []
    cur_path: str | None = None
    cur: list[str] = []
    for line in content.splitlines(keepends=True):
        if _src_path(line) is not None:
            segments.append((cur_path, "".join(cur)))
            cur_path = _src_path(line)
            cur = [line]
        else:
            cur.append(line)
    segments.append((cur_path, "".join(cur)))
    return segments


def splice_blocks(content: str,
                  replacements: dict[str, str],
                  deletions: tuple[str, ...] | list[str] = ()) -> str:
    """Return ``content`` with per-module blocks replaced/removed/appended.

    - ``replacements``: ``{source_path: new_block_text}``. A path matching an
      existing ``# src:`` block (after slash normalisation) replaces it in place,
      preserving the original block's trailing whitespace; an unmatched path is
      appended as a new block.
    - ``deletions``: source paths whose blocks are removed.

    Matching is exact on the normalised path — never a suffix match — so a
    surgical update can't clobber the wrong block. The preamble is preserved.
    """
    segments = split_segments(content)
    deletions_n = {_norm(d) for d in deletions}
    repl_n = {_norm(k): v for k, v in replacements.items()}

    out: list[str] = []
    used: set[str | None] = set()
    for path, text in segments:
        pn = _norm(path)
        if pn is not None and pn in deletions_n:
            continue
        if pn is not None and pn in repl_n:
            trailing = text[len(text.rstrip("\n")):] or "\n"
            out.append(repl_n[pn].rstrip("\n") + trailing)
            used.add(pn)
        else:
            out.append(text)

    for pn, block in repl_n.items():
        if pn in used or pn in deletions_n:
            continue
        out.append("\n" + block.strip() + "\n")

    return "".join(out)


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
