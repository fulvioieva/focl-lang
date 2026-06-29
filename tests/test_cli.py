"""Smoke tests for focl.cli — exercise commands without hitting the API."""

from __future__ import annotations

import os
from pathlib import Path

from click.testing import CliRunner

from focl.cli import (
    _CLAUDE_END,
    _CLAUDE_START,
    _merge_mcp_json,
    _merge_settings_hook,
    _upsert_claude_pointer,
    main,
)


class TestCliBasics:
    def test_help_works(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "FOCL" in result.output

    def test_version_works(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "focl" in result.output.lower()


class TestCliPlan:
    """`focl plan` runs entirely offline — no API calls."""

    def test_plan_on_java_project(self, tmp_java_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["plan", str(tmp_java_project)])
        assert result.exit_code == 0
        assert "java" in result.output.lower()

    def test_plan_on_missing_dir(self, tmp_path: Path) -> None:
        runner = CliRunner()
        bogus = tmp_path / "does_not_exist"
        result = runner.invoke(main, ["plan", str(bogus)])
        assert result.exit_code != 0

    def test_plan_honors_shard_budget(self, tmp_java_project: Path) -> None:
        runner = CliRunner()
        # Very small budget so sharding kicks in
        result = runner.invoke(
            main, ["plan", str(tmp_java_project), "--shard-budget", "500"]
        )
        assert result.exit_code == 0


class TestCliStats:
    """`focl stats` runs offline when no API key is needed for estimates."""

    def test_stats_without_focl_file(self, tmp_java_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["stats", str(tmp_java_project)])
        assert result.exit_code == 0
        # Should complain that no .focl was found
        assert "not found" in result.output.lower() or "focl init" in result.output

    def test_stats_with_existing_focl(self, tmp_java_project: Path) -> None:
        # Create a fake .focl beside the project
        focl = tmp_java_project / (tmp_java_project.name + ".focl")
        focl.write_text("SERVICE UserService\n  ACTION get -> UserDTO\n")

        runner = CliRunner()
        result = runner.invoke(main, ["stats", str(tmp_java_project)])
        assert result.exit_code == 0
        # Should show compression info
        low = result.output.lower()
        assert "token" in low or "ratio" in low


class TestClaudePointer:
    """`_upsert_claude_pointer` manages a sentinel-delimited block idempotently."""

    def test_creates_block_when_no_file(self) -> None:
        out = _upsert_claude_pointer(None, "demo.focl")
        assert _CLAUDE_START in out
        assert _CLAUDE_END in out
        assert "demo.focl" in out

    def test_appends_to_existing_content(self) -> None:
        existing = "# CLAUDE.md\n\nSome existing guidance.\n"
        out = _upsert_claude_pointer(existing, "demo.focl")
        # Original content is preserved, the block is appended once.
        assert existing.strip() in out
        assert out.count(_CLAUDE_START) == 1
        assert out.count(_CLAUDE_END) == 1

    def test_replaces_block_in_place_idempotently(self) -> None:
        once = _upsert_claude_pointer("# CLAUDE.md\n\nGuidance.\n", "old.focl")
        twice = _upsert_claude_pointer(once, "new.focl")
        # Exactly one managed block, refreshed to the new filename.
        assert twice.count(_CLAUDE_START) == 1
        assert twice.count(_CLAUDE_END) == 1
        assert "new.focl" in twice
        assert "old.focl" not in twice
        # Surrounding content survives.
        assert "Guidance." in twice

    def test_replace_is_stable_on_repeat(self) -> None:
        once = _upsert_claude_pointer(None, "demo.focl")
        twice = _upsert_claude_pointer(once, "demo.focl")
        assert once == twice


class TestScaffoldMerge:
    """Pure JSON-merge helpers used by `focl claude-setup`."""

    def test_mcp_json_registers_focl_server(self) -> None:
        out = _merge_mcp_json(None)
        assert out["mcpServers"]["focl"]["command"] == "focl"
        assert out["mcpServers"]["focl"]["args"] == ["mcp", "."]

    def test_mcp_json_preserves_other_servers(self) -> None:
        existing = {"mcpServers": {"other": {"command": "x"}}}
        out = _merge_mcp_json(existing)
        assert "other" in out["mcpServers"]
        assert "focl" in out["mcpServers"]
        # Does not mutate the input.
        assert "focl" not in existing["mcpServers"]

    def test_settings_hook_added_once(self) -> None:
        once = _merge_settings_hook(None)
        twice = _merge_settings_hook(once)
        starts = twice["hooks"]["SessionStart"]
        focl_hooks = [
            h for entry in starts for h in entry["hooks"]
            if "focl check" in h["command"]
        ]
        assert len(focl_hooks) == 1

    def test_settings_hook_preserves_existing_hooks(self) -> None:
        existing = {"hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": "echo hi"}]}
        ]}}
        out = _merge_settings_hook(existing)
        commands = [
            h["command"] for entry in out["hooks"]["SessionStart"]
            for h in entry["hooks"]
        ]
        assert "echo hi" in commands
        assert any("focl check" in c for c in commands)


class TestCheck:
    """`focl check` is offline — compares source vs .focl mtimes."""

    def test_missing_focl(self, tmp_java_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["check", str(tmp_java_project)])
        assert result.exit_code == 0
        assert "missing" in result.output.lower()

    def test_up_to_date(self, tmp_java_project: Path) -> None:
        focl = tmp_java_project / (tmp_java_project.name + ".focl")
        focl.write_text("SERVICE X\n", encoding="utf-8")  # newer than sources
        runner = CliRunner()
        result = runner.invoke(main, ["check", str(tmp_java_project)])
        assert result.exit_code == 0
        assert "up to date" in result.output.lower()

    def test_stale_when_source_newer(self, tmp_java_project: Path) -> None:
        focl = tmp_java_project / (tmp_java_project.name + ".focl")
        focl.write_text("SERVICE X\n", encoding="utf-8")
        # Make a source file newer than the .focl.
        src = tmp_java_project / "services" / "UserService.java"
        future = focl.stat().st_mtime + 100
        os.utime(src, (future, future))
        runner = CliRunner()
        result = runner.invoke(main, ["check", str(tmp_java_project)])
        assert result.exit_code == 0
        assert "stale" in result.output.lower()


class TestClaudeSetup:
    def test_dry_run_writes_nothing(self, tmp_java_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["claude-setup", str(tmp_java_project), "--dry-run"])
        assert result.exit_code == 0
        assert "would write" in result.output.lower()
        assert not (tmp_java_project / ".mcp.json").exists()
        assert not (tmp_java_project / ".claude" / "settings.json").exists()

    def test_writes_integration_files(self, tmp_java_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["claude-setup", str(tmp_java_project)])
        assert result.exit_code == 0
        assert (tmp_java_project / ".mcp.json").exists()
        assert (tmp_java_project / ".claude" / "settings.json").exists()
        assert (tmp_java_project / ".claude" / "skills" / "focl" / "SKILL.md").exists()
        assert (tmp_java_project / "CLAUDE.md").exists()

    def test_rerun_is_idempotent(self, tmp_java_project: Path) -> None:
        runner = CliRunner()
        runner.invoke(main, ["claude-setup", str(tmp_java_project)])
        before = (tmp_java_project / ".mcp.json").read_text(encoding="utf-8")
        runner.invoke(main, ["claude-setup", str(tmp_java_project)])
        after = (tmp_java_project / ".mcp.json").read_text(encoding="utf-8")
        assert before == after


class TestMcpCommand:
    def test_errors_without_focl_file(self, tmp_java_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["mcp", str(tmp_java_project)])
        assert result.exit_code != 0
