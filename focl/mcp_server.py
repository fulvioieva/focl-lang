"""A Model Context Protocol (MCP) server that exposes a project's ``.focl`` map.

Run via ``focl mcp [path]``. It lets an MCP client (e.g. Claude Code) pull the
*compressed* representation of the codebase on demand instead of reading whole
source files:

- tool ``focl_overview`` — the file header plus the list of modules
- tool ``focl_list_modules`` — just the source paths
- tool ``focl_module(path)`` — the compressed block for one source file
- resource ``focl://project`` — the full ``.focl`` text

All tools re-read the ``.focl`` from disk on every call, so edits made by
``focl sync`` / ``focl watch`` (or the freshness hook) are picked up live.

``mcp`` is an optional dependency: ``pip install -e ".[mcp]"``.
"""

from __future__ import annotations

from pathlib import Path

from . import index


def build_server(focl_path: Path):
    """Construct (but do not run) the FastMCP server for ``focl_path``."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise RuntimeError(
            "The MCP server requires the 'mcp' package. "
            "Install it with: pip install 'focl[mcp]'"
        ) from e

    server = FastMCP("focl")

    def _read() -> str:
        return focl_path.read_text(encoding="utf-8")

    @server.tool()
    def focl_overview() -> str:
        """Return the codebase header and the list of available modules."""
        return index.overview(_read())

    @server.tool()
    def focl_list_modules() -> list[str]:
        """Return the source file paths captured in the .focl map."""
        return index.module_paths(_read())

    @server.tool()
    def focl_module(path: str) -> str:
        """Return the compressed FOCL block for a single source file."""
        block = index.get_module(_read(), path)
        if block is None:
            available = ", ".join(index.module_paths(_read())[:20])
            return f"No module found for '{path}'. Available: {available}"
        return block

    @server.resource("focl://project")
    def focl_resource() -> str:
        """The full .focl file."""
        return _read()

    return server


def serve(focl_path: Path) -> None:
    """Run the MCP server over stdio (blocks until the client disconnects)."""
    build_server(focl_path).run()
