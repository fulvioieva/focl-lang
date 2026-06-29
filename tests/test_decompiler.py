"""Tests for focl.decompiler — round-trip reconstruction orchestration.

The LLM call is stubbed; only parsing/orchestration/writing is exercised.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

import focl.decompiler as dc
from focl.cli import main

_FOCL = """\
# FOCL file for project: demo
# Language: java / spring-boot

# src: services/UserService.java
SERVICE UserService
  OWNED_FETCH(User, by=id)

# src: controllers/UserController.java
CTRL UserController
  GET /users -> PAGE
"""


@pytest.fixture
def stub_llm(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls: list[str] = []

    def spy(config, system, user, max_tokens):
        calls.append(user)
        return "// reconstructed code\n"

    monkeypatch.setattr(dc, "generate_text", spy)
    return calls


class TestDetectLanguage:
    def test_reads_language_header(self) -> None:
        assert dc.detect_language(_FOCL) == "java"

    def test_none_when_absent(self) -> None:
        assert dc.detect_language("SERVICE X\n") is None


class TestDecompilePerModule:
    def test_keys_by_source_path(self, stub_llm) -> None:
        from focl.providers import LLMConfig
        out = dc.decompile(_FOCL, LLMConfig(api_key="k"))
        assert set(out) == {
            "services/UserService.java",
            "controllers/UserController.java",
        }
        assert all(v.strip() for v in out.values())
        assert len(stub_llm) == 2  # one call per module


class TestWholeFallback:
    def test_splits_on_path_headers(self, monkeypatch) -> None:
        from focl.providers import LLMConfig

        def spy(config, system, user, max_tokens):
            return "=== a/X.java ===\nclass X {}\n=== a/Y.java ===\nclass Y {}\n"

        monkeypatch.setattr(dc, "generate_text", spy)
        out = dc.decompile("SERVICE X\n  do()\n", LLMConfig(api_key="k"))
        assert set(out) == {"a/X.java", "a/Y.java"}
        assert "class X {}" in out["a/X.java"]


class TestStripFences:
    def test_removes_fenced_block(self) -> None:
        fenced = "```java\nclass A {}\n```"
        assert dc._strip_fences(fenced).strip() == "class A {}"

    def test_passes_through_plain(self) -> None:
        assert dc._strip_fences("class A {}").strip() == "class A {}"


class TestDecompileCLI:
    def test_writes_files(self, tmp_java_project: Path, stub_llm) -> None:
        focl = tmp_java_project / (tmp_java_project.name + ".focl")
        focl.write_text(_FOCL, encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, ["decompile", str(tmp_java_project)])
        assert result.exit_code == 0, result.output

        out_dir = tmp_java_project / f"{tmp_java_project.name}-decompiled"
        assert (out_dir / "services" / "UserService.java").exists()
        assert (out_dir / "controllers" / "UserController.java").exists()
