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


from focl import freshness  # noqa: E402
from focl import mcp_server as ms  # noqa: E402


def _setup(tmp_path: Path) -> tuple[str, Path]:
    (tmp_path / "A.java").write_text("class A {}\n", encoding="utf-8")
    (tmp_path / "B.java").write_text("class B {}\n", encoding="utf-8")
    content = freshness.stamp(
        "# FOCL file for project: demo\n\n"
        "# src: A.java\nSERVICE A\n  OWNED_FETCH(repo, by=owner)\n\n"
        "# src: B.java\nSERVICE B\n  PAGE(created)\n",
        tmp_path,
    )
    return content, tmp_path


def test_module_fresh_has_no_marker(tmp_path: Path) -> None:
    content, root = _setup(tmp_path)
    out = ms.module_text(content, root, "A.java")
    assert out.startswith("# src: A.java @h:")
    assert "STALE" not in out


def test_module_changed_is_flagged(tmp_path: Path) -> None:
    content, root = _setup(tmp_path)
    (root / "A.java").write_text("class A { int x; }\n", encoding="utf-8")
    out = ms.module_text(content, root, "A.java")
    assert out.startswith("[STALE] A.java changed")
    assert "SERVICE A" in out


def test_module_deleted_is_flagged(tmp_path: Path) -> None:
    content, root = _setup(tmp_path)
    (root / "B.java").unlink()
    assert "no longer exists" in ms.module_text(content, root, "B.java")


def test_module_unknown(tmp_path: Path) -> None:
    content, root = _setup(tmp_path)
    assert "No module found" in ms.module_text(content, root, "Nope.java")


def test_modules_batch(tmp_path: Path) -> None:
    content, root = _setup(tmp_path)
    out = ms.modules_text(content, root, ["A.java", "B.java"])
    assert "SERVICE A" in out and "SERVICE B" in out


def test_list_modules_has_tokens_and_status(tmp_path: Path) -> None:
    content, root = _setup(tmp_path)
    (root / "B.java").write_text("class B { }\n", encoding="utf-8")
    rows = ms.list_modules(content, root)
    assert [r["path"] for r in rows] == ["A.java", "B.java"]
    assert rows[0]["status"] == "fresh" and rows[1]["status"] == "changed"
    assert all(r["tokens"] > 0 for r in rows)


def test_search_groups_and_flags(tmp_path: Path) -> None:
    content, root = _setup(tmp_path)
    (root / "B.java").write_text("class B { }\n", encoding="utf-8")
    out = ms.search_text(content, root, "service")
    assert "A.java:\n  SERVICE A" in out
    assert "B.java [STALE]:\n  SERVICE B" in out
    assert "No matches" in ms.search_text(content, root, "zzz")


def test_overview_flags_stale(tmp_path: Path) -> None:
    content, root = _setup(tmp_path)
    (root / "A.java").write_text("class A { int y; }\n", encoding="utf-8")
    ov = ms.overview_text(content, root)
    assert "A.java [STALE: changed]" in ov
    assert "focl_search" in ov
