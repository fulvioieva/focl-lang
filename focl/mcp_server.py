"""A Model Context Protocol (MCP) server that exposes a project's ``.focl`` map.

Run via ``focl mcp [path]``. It lets an MCP client (e.g. Claude Code) pull the
*compressed* representation of the codebase on demand instead of reading whole
source files:

- tool ``focl_overview`` — the file header plus the list of modules
- tool ``focl_list_modules`` — source paths with token size and freshness
- tool ``focl_module(path)`` — the compressed block for one source file
- tool ``focl_modules(paths)`` — several blocks in one call
- tool ``focl_search(query)`` — "where does X happen": matching lines by module
- resource ``focl://project`` — the full ``.focl`` text

Modules whose source changed since their block was generated (per the ``@h:``
stamps, see :mod:`focl.freshness`) are flagged STALE, so the client knows to
read the real file instead of trusting the map.

All tools re-read the ``.focl`` from disk on every call, so edits made by
``focl sync`` / ``focl watch`` are picked up live.

``mcp`` is an optional dependency: ``pip install -e ".[mcp]"``.
The tool bodies are plain functions (``overview_text`` …) so they can be
tested without an MCP client.
"""

from __future__ import annotations

from pathlib import Path

from . import freshness, index
from .providers import estimate_tokens

_SEARCH_LIMIT = 50


def _stale_note(path: str, state: str) -> str:
    if state == freshness.DELETED:
        return (f"[STALE] {path} no longer exists - this block describes "
                "deleted code.\n")
    return (f"[STALE] {path} changed since this block was generated - read the "
            "source file for its current behaviour (or run `focl sync`).\n")


def overview_text(content: str, root: Path) -> str:
    return index.overview(content, freshness.module_status(content, root))


def list_modules(content: str, root: Path) -> list[dict]:
    blocks = index.parse_focl_blocks(content)
    status = freshness.module_status(content, root)
    return [
        {
            "path": p,
            "tokens": estimate_tokens(blocks.get(p, "")),
            "status": status.get(p, freshness.UNVERIFIED),
        }
        for p in index.module_paths(content)
    ]


def _resolve_key(content: str, path: str) -> str | None:
    """The exact module key for ``path`` (exact or unique-suffix match)."""
    paths = index.module_paths(content)
    if path in paths:
        return path
    norm = path.replace("\\", "/")
    matches = [p for p in paths if p.replace("\\", "/").endswith(norm)]
    return matches[0] if len(matches) == 1 else None


def module_text(content: str, root: Path, path: str) -> str:
    key = _resolve_key(content, path)
    block = index.get_module(content, key) if key else None
    if block is None:
        available = ", ".join(index.module_paths(content)[:20])
        return f"No module found for '{path}'. Available: {available}"
    state = freshness.module_status(content, root, [key]).get(key)
    if state in (freshness.CHANGED, freshness.DELETED):
        return _stale_note(key, state) + block
    return block


def modules_text(content: str, root: Path, paths: list[str]) -> str:
    return "\n\n".join(module_text(content, root, p) for p in paths)


def search_text(content: str, root: Path, query: str,
                limit: int = _SEARCH_LIMIT) -> str:
    hits = index.search(content, query, limit=limit)
    if not hits:
        return f"No matches for '{query}' in the FOCL map."
    stale = {
        p for p, st in freshness.module_status(content, root).items()
        if st in (freshness.CHANGED, freshness.DELETED)
    }
    lines: list[str] = []
    current: object = object()
    for path, line in hits:
        if path != current:
            current = path
            label = path or "(header)"
            lines.append(f"{label}{' [STALE]' if path in stale else ''}:")
        lines.append(f"  {line}")
    if len(hits) >= limit:
        lines.append(f"(first {limit} matches — refine the query for more)")
    return "\n".join(lines)


def read_map(focl_path: Path) -> str | None:
    """The map's text, or None when it doesn't exist (yet)."""
    try:
        return focl_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def missing_map_text(focl_path: Path) -> str:
    return (
        f"No FOCL map ({focl_path.name}) in this project yet, so there is "
        "nothing to query - read the source files directly. To create one, run "
        "`focl init` in the project root (it calls an LLM, so ask the user "
        "first); these tools pick it up immediately."
    )


def build_server(focl_path: Path, root: Path | None = None):
    """Construct (but do not run) the FastMCP server for ``focl_path``.

    ``root`` is the source tree the map describes (default: the ``.focl``'s
    directory); it's used to detect stale modules.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "The MCP server requires the 'mcp' package. "
            "Install it with: pip install 'focl[mcp]'"
        ) from e

    root = root or focl_path.parent
    server = FastMCP("focl")

    def _read() -> str | None:
        return read_map(focl_path)

    @server.tool()
    def focl_overview() -> str:
        """Return the codebase header and the list of modules (stale ones flagged)."""
        content = _read()
        return missing_map_text(focl_path) if content is None else overview_text(content, root)

    @server.tool()
    def focl_list_modules() -> list[dict]:
        """Return each module's source path, estimated token size, and freshness
        status (fresh / changed / deleted / unverified)."""
        content = _read()
        return [] if content is None else list_modules(content, root)

    @server.tool()
    def focl_module(path: str) -> str:
        """Return the compressed FOCL block for a single source file. Accepts a
        full path or a unique suffix (e.g. 'UserService.java')."""
        content = _read()
        return missing_map_text(focl_path) if content is None else module_text(content, root, path)

    @server.tool()
    def focl_modules(paths: list[str]) -> str:
        """Return the compressed FOCL blocks for several source files at once."""
        content = _read()
        return (missing_map_text(focl_path) if content is None
                else modules_text(content, root, paths))

    @server.tool()
    def focl_search(query: str) -> str:
        """Find where something happens: case-insensitive substring search over
        the compressed map, returning matching lines grouped by source file.
        Cheaper than grepping the source. Matches module paths too."""
        content = _read()
        return (missing_map_text(focl_path) if content is None
                else search_text(content, root, query))

    @server.resource("focl://project")
    def focl_resource() -> str:
        """The full .focl file."""
        content = _read()
        return missing_map_text(focl_path) if content is None else content

    return server


def serve(focl_path: Path, root: Path | None = None) -> None:
    """Run the MCP server over stdio (blocks until the client disconnects)."""
    build_server(focl_path, root).run()
