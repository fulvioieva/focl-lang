"""Tests for focl.mcp_server — only run when the optional `mcp` extra is present."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="MCP server requires the optional [mcp] extra")

from focl.mcp_server import build_server  # noqa: E402


def test_build_server_constructs(tmp_path: Path) -> None:
    focl = tmp_path / "demo.focl"
    focl.write_text("# src: A.java\nSERVICE A\n", encoding="utf-8")
    server = build_server(focl)
    # FastMCP instance exposes a name; tools registered without raising.
    assert server is not None
    assert getattr(server, "name", "focl") == "focl"
