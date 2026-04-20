"""Shared pytest fixtures for FOCL tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_java_project(tmp_path: Path) -> Path:
    """A minimal Spring Boot-looking project for language detection tests."""
    # The keyword searched by _detect_spring_framework is "spring-boot"
    # (with hyphen), so the pom.xml must contain that exact string.
    (tmp_path / "pom.xml").write_text(
        "<project><dependencies><dependency>"
        "<groupId>org.spring-boot</groupId>"
        "</dependency></dependencies></project>"
    )
    services = tmp_path / "services"
    services.mkdir()
    (services / "UserService.java").write_text(
        "package com.test.services;\npublic class UserService {\n"
        "  public void doThing() {}\n}\n"
    )
    controllers = tmp_path / "controllers"
    controllers.mkdir()
    (controllers / "UserController.java").write_text(
        "package com.test.controllers;\npublic class UserController {\n"
        "  public void handle() {}\n}\n"
    )
    return tmp_path


@pytest.fixture
def tmp_python_project(tmp_path: Path) -> Path:
    """A minimal Python project with pyproject.toml."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
    )
    pkg = tmp_path / "demo"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "service.py").write_text("def hello(): return 'world'\n")
    return tmp_path


@pytest.fixture
def tmp_project_with_ignored(tmp_path: Path) -> Path:
    """A project with files that should be ignored (node_modules, .venv, binaries)."""
    (tmp_path / "package.json").write_text('{"name": "demo"}')
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.ts").write_text("export const x = 1;\n")

    # These should all be filtered out
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "big.js").write_text("// should be ignored\n")

    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "settings.py").write_text("# should be ignored\n")

    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    (tmp_path / "archive.zip").write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    return tmp_path


@pytest.fixture
def tmp_large_file_project(tmp_path: Path) -> Path:
    """A project with one file that exceeds the shard budget but stays under
    the analyzer's _MAX_FILE_BYTES cap (200 KB) so it is collected and then
    flagged as oversize by the sharder.

    With _estimate_tokens using 3 chars/token, a 100 KB file ≈ 33 K tokens,
    which exceeds the 10 K token shard budget used in these tests.
    """
    (tmp_path / "pom.xml").write_text("<project/>")
    big = tmp_path / "Big.java"
    # ~100 KB: small enough for the analyzer (< 200 KB), big enough for the
    # sharder to flag as oversize when budget=10_000 tokens (≈ 30 KB chars).
    body = "public void method() { /* ... */ }\n" * 2_800
    big.write_text(f"public class Big {{\n{body}}}\n")

    small = tmp_path / "Small.java"
    small.write_text("public class Small {}\n")
    return tmp_path


def write_java_file(path: Path, body_lines: int = 100) -> None:
    """Helper to write a Java file of roughly predictable size."""
    body = "  public void m() { /* noop */ }\n" * body_lines
    path.write_text(
        f"package com.test;\npublic class {path.stem} {{\n{body}}}\n"
    )


@pytest.fixture
def tmp_analyzer_skip_project(tmp_path: Path) -> Path:
    """Project with one file > _MAX_FILE_BYTES (200 KB) so the analyzer
    silently skips it and puts it in skipped_files."""
    (tmp_path / "pom.xml").write_text("<project/>")
    huge = tmp_path / "Huge.java"
    body = "public void m() { /* noop */ }\n" * 7_000  # ~210 KB
    huge.write_text(f"public class Huge {{\n{body}}}\n")
    (tmp_path / "Small.java").write_text("public class Small {}\n")
    return tmp_path
