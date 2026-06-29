"""Tests for focl.generator.update — surgical patching orchestration.

The LLM call is stubbed so the splice/fallback logic is exercised offline.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import focl.generator as gen

_FOCL = """\
# FOCL file for project: demo

# src: a.py
MOD a
  do()

# src: b.py
MOD b
  go()
"""


def _fake_generate_text(config, system, user, max_tokens):
    """Echo back a block annotated with the rel path found in the prompt."""
    m = re.search(r"=== (\S+) ===", user)  # the wrap_file delimiter
    rel = m.group(1) if m else "unknown"
    return f"# src: {rel}\nMOD {rel} STUBBED"


@pytest.fixture
def stub_llm(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    calls: list[str] = []

    def spy(config, system, user, max_tokens):
        calls.append(user)
        return _fake_generate_text(config, system, user, max_tokens)

    monkeypatch.setattr(gen, "generate_text", spy)
    return calls


def _write_focl(tmp_path: Path) -> Path:
    f = tmp_path / "demo.focl"
    f.write_text(_FOCL, encoding="utf-8")
    return f


class TestSurgicalUpdate:
    def test_replaces_only_changed_block(self, tmp_path: Path, stub_llm) -> None:
        focl = _write_focl(tmp_path)
        (tmp_path / "a.py").write_text("def do(): ...\n")
        result = gen.update(focl, [tmp_path / "a.py"], tmp_path)

        assert "MOD a.py STUBBED" in result      # a.py regenerated
        assert "MOD b\n  go()" in result          # b.py untouched
        assert "project: demo" in result          # preamble preserved
        assert len(stub_llm) == 1                  # only the changed file sent

    def test_deleted_file_drops_block_without_api_call(
        self, tmp_path: Path, stub_llm
    ) -> None:
        focl = _write_focl(tmp_path)
        # b.py does not exist on disk -> treated as deleted
        result = gen.update(focl, [tmp_path / "b.py"], tmp_path)
        assert "MOD b" not in result
        assert "MOD a" in result
        assert len(stub_llm) == 0                  # nothing regenerated

    def test_new_file_is_appended(self, tmp_path: Path, stub_llm) -> None:
        focl = _write_focl(tmp_path)
        (tmp_path / "c.py").write_text("def c(): ...\n")
        result = gen.update(focl, [tmp_path / "c.py"], tmp_path)
        from focl import index
        assert "c.py" in index.module_paths(result)
        assert "MOD a" in result and "MOD b" in result


class TestFallback:
    def test_whole_file_rewrite_when_no_src_blocks(
        self, tmp_path: Path, stub_llm
    ) -> None:
        focl = tmp_path / "demo.focl"
        focl.write_text("SERVICE X\n  do()\n", encoding="utf-8")  # no `# src:`
        (tmp_path / "a.py").write_text("def do(): ...\n")
        result = gen.update(focl, [tmp_path / "a.py"], tmp_path)
        # Fallback returns the model output directly (one call), not a splice.
        assert "STUBBED" in result
        assert len(stub_llm) == 1
