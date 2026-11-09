"""Tests for focl.providers — offline (subprocess / SDK calls are stubbed)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from focl import providers
from focl.providers import CLAUDE_CODE, LLMConfig


@pytest.fixture
def claude_on_path(monkeypatch) -> str:
    exe = "/usr/local/bin/claude"
    monkeypatch.setattr(providers.shutil, "which", lambda name: exe if name == "claude" else None)
    return exe


class TestConfig:
    def test_claude_code_is_a_provider(self) -> None:
        assert CLAUDE_CODE in providers.PROVIDERS
        assert LLMConfig(provider=CLAUDE_CODE).model == "opus"

    def test_claude_code_needs_no_api_key(self, claude_on_path, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert LLMConfig(provider=CLAUDE_CODE).require_api_key() == ""

    def test_missing_cli_is_explained(self, monkeypatch) -> None:
        monkeypatch.setattr(providers.shutil, "which", lambda name: None)
        with pytest.raises(RuntimeError, match="Claude Code CLI"):
            LLMConfig(provider=CLAUDE_CODE).require_api_key()

    def test_anthropic_still_requires_key(self, monkeypatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            LLMConfig().require_api_key()

    def test_token_count_is_estimated(self) -> None:
        cfg = LLMConfig(provider=CLAUDE_CODE)
        text = "x" * 300
        assert providers.count_tokens(cfg, text, use_api_counter=True) == (
            providers.estimate_tokens(text))


class TestCommand:
    def test_isolating_flags(self, tmp_path: Path) -> None:
        cmd = providers._claude_code_command(
            "claude", LLMConfig(provider=CLAUDE_CODE, model="sonnet"), tmp_path / "s.txt")
        assert cmd[:4] == ["claude", "-p", "--model", "sonnet"]
        assert cmd[cmd.index("--system-prompt-file") + 1] == str(tmp_path / "s.txt")
        assert cmd[cmd.index("--output-format") + 1] == "json"
        assert cmd[cmd.index("--tools") + 1] == ""          # no tools at all
        assert cmd[cmd.index("--setting-sources") + 1] == ""  # no hooks/plugins
        for flag in ("--strict-mcp-config", "--disable-slash-commands",
                     "--no-session-persistence"):
            assert flag in cmd
        # --bare would force API-key auth and break subscription logins.
        assert "--bare" not in cmd


class TestParse:
    def test_success(self) -> None:
        out = json.dumps({"type": "result", "is_error": False, "result": "  FOCL  "})
        assert providers._parse_claude_code_output(0, out, "") == "FOCL"

    def test_reported_error(self) -> None:
        out = json.dumps({"is_error": True, "result": "There's an issue with the model"})
        with pytest.raises(RuntimeError, match="issue with the model"):
            providers._parse_claude_code_output(1, out, "")

    def test_non_json_uses_stderr(self) -> None:
        with pytest.raises(RuntimeError, match="not logged in"):
            providers._parse_claude_code_output(1, "", "Error: not logged in")

    def test_nonzero_exit_without_flag_is_error(self) -> None:
        out = json.dumps({"is_error": False, "result": "partial"})
        with pytest.raises(RuntimeError):
            providers._parse_claude_code_output(2, out, "boom")


class TestGenerate:
    def test_runs_claude_with_stdin_system_file_and_env(
        self, claude_on_path, monkeypatch
    ) -> None:
        seen: dict = {}

        def fake_run(cmd, **kw):
            sys_file = Path(cmd[cmd.index("--system-prompt-file") + 1])
            seen.update(cmd=cmd, kw=kw, system=sys_file.read_text(encoding="utf-8"))
            return subprocess.CompletedProcess(
                cmd, 0, json.dumps({"is_error": False, "result": "SERVICE A"}), "")

        monkeypatch.setattr(providers.subprocess, "run", fake_run)
        out = providers.generate_text(
            LLMConfig(provider=CLAUDE_CODE), "SYS PROMPT", "=== a.py ===\ncode", 1234)

        assert out == "SERVICE A"
        assert seen["cmd"][0] == claude_on_path
        assert seen["system"] == "SYS PROMPT"
        assert seen["kw"]["input"] == "=== a.py ===\ncode"   # via stdin, not argv
        assert seen["kw"]["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "1234"
        assert Path(seen["kw"]["cwd"]).name.startswith("focl-cc-")  # empty temp dir
        assert not Path(seen["kw"]["cwd"]).exists()                  # cleaned up

    def test_timeout_is_explained(self, claude_on_path, monkeypatch) -> None:
        def fake_run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])

        monkeypatch.setattr(providers.subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="did not answer"):
            providers.generate_text(LLMConfig(provider=CLAUDE_CODE), "s", "u", 10)
