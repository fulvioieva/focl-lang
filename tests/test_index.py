"""Tests for focl.index — parsing a .focl file by its `# src:` annotations."""

from __future__ import annotations

from focl import index

_SAMPLE = """\
# FOCL file for project: demo
# Language: java

# src: services/UserService.java
SERVICE UserService
  INJECT UserRepo
  ACTION get(id) -> UserDTO

# src: controllers/UserController.java
CTRL UserController
  GET /users -> PAGE
"""


class TestParsing:
    def test_header_is_preamble(self) -> None:
        h = index.header(_SAMPLE)
        assert "project: demo" in h
        assert "# src:" not in h

    def test_module_paths_ordered_unique(self) -> None:
        assert index.module_paths(_SAMPLE) == [
            "services/UserService.java",
            "controllers/UserController.java",
        ]

    def test_parse_blocks_keyed_by_path(self) -> None:
        blocks = index.parse_focl_blocks(_SAMPLE)
        assert set(blocks) == {
            "services/UserService.java",
            "controllers/UserController.java",
        }
        svc = blocks["services/UserService.java"]
        assert "SERVICE UserService" in svc
        assert "# src: services/UserService.java" in svc
        # Block stops at the next marker.
        assert "UserController" not in svc

    def test_get_module_exact(self) -> None:
        block = index.get_module(_SAMPLE, "controllers/UserController.java")
        assert block is not None and "CTRL UserController" in block

    def test_get_module_suffix_match(self) -> None:
        # A short relative path resolves via unique-suffix matching.
        block = index.get_module(_SAMPLE, "UserService.java")
        assert block is not None and "SERVICE UserService" in block

    def test_get_module_unknown_returns_none(self) -> None:
        assert index.get_module(_SAMPLE, "nope/Missing.java") is None

    def test_overview_lists_modules(self) -> None:
        ov = index.overview(_SAMPLE)
        assert "services/UserService.java" in ov
        assert "controllers/UserController.java" in ov
        assert "focl_module(" in ov


class TestNoAnnotations:
    def test_module_paths_empty(self) -> None:
        assert index.module_paths("SERVICE X\n  ACTION do -> DTO\n") == []

    def test_overview_falls_back_to_full_content(self) -> None:
        content = "SERVICE X\n  ACTION do -> DTO\n"
        ov = index.overview(content)
        assert "No `# src:`" in ov
        assert "SERVICE X" in ov
