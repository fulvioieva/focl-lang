"""Smoke tests for focl.cli — exercise commands without hitting the API."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
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


class TestCheckPerModule:
    """Maps with `@h:` stamps get an exact per-module freshness report."""

    def _stamped_map(self, root: Path) -> Path:
        from focl import freshness
        focl = root / (root.name + ".focl")
        content = "# src: services/UserService.java\nSERVICE UserService\n  get()\n"
        focl.write_text(freshness.stamp(content, root), encoding="utf-8")
        return focl

    def test_up_to_date_counts_verified(self, tmp_java_project: Path) -> None:
        self._stamped_map(tmp_java_project)
        result = CliRunner().invoke(main, ["check", str(tmp_java_project)])
        assert result.exit_code == 0
        assert "up to date" in result.output.lower()
        assert "1 modules verified" in " ".join(result.output.split())  # rich wraps

    def test_lists_changed_module(self, tmp_java_project: Path) -> None:
        self._stamped_map(tmp_java_project)
        src = tmp_java_project / "services" / "UserService.java"
        src.write_text(src.read_text(encoding="utf-8") + "\n// edit\n", encoding="utf-8")
        result = CliRunner().invoke(main, ["check", str(tmp_java_project)])
        assert result.exit_code == 0
        assert "stale" in result.output.lower()
        assert "changed" in result.output
        assert "services/UserService.java" in result.output

    def test_survives_mtime_noise(self, tmp_java_project: Path) -> None:
        # A checkout that bumps mtimes without changing content is NOT stale.
        focl = self._stamped_map(tmp_java_project)
        src = tmp_java_project / "services" / "UserService.java"
        future = focl.stat().st_mtime + 100
        os.utime(src, (future, future))
        result = CliRunner().invoke(main, ["check", str(tmp_java_project)])
        assert "up to date" in result.output.lower()

    def test_legacy_map_suggests_regeneration(self, tmp_java_project: Path) -> None:
        focl = tmp_java_project / (tmp_java_project.name + ".focl")
        focl.write_text("# src: services/UserService.java\nSERVICE X\n", encoding="utf-8")
        result = CliRunner().invoke(main, ["check", str(tmp_java_project)])
        assert "no per-module hashes" in result.output


class TestSyncChanged:
    """`focl sync --changed` regenerates only stale modules (LLM stubbed)."""

    @pytest.fixture
    def llm_calls(self, monkeypatch) -> list[str]:
        import focl.generator as gen
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        calls: list[str] = []

        def fake(config, system, user, max_tokens):
            calls.append(user)
            rel = re.search(r"=== (\S+) ===", user).group(1)
            return f"# src: {rel}\nREGENERATED {rel}"

        monkeypatch.setattr(gen, "generate_text", fake)
        return calls

    def _setup(self, root: Path) -> Path:
        from focl import freshness
        (root / "keep.py").write_text("def keep(): ...\n", encoding="utf-8")
        (root / "edit.py").write_text("def edit(): ...\n", encoding="utf-8")
        (root / "gone.py").write_text("def gone(): ...\n", encoding="utf-8")
        focl = root / (root.name + ".focl")
        content = (
            "# FOCL file for project: demo\n\n"
            "# src: keep.py\nMOD keep\n\n"
            "# src: edit.py\nMOD edit\n\n"
            "# src: gone.py\nMOD gone\n"
        )
        focl.write_text(freshness.stamp(content, root), encoding="utf-8")
        return focl

    def test_regenerates_only_stale_modules(self, tmp_python_project: Path,
                                            llm_calls: list[str]) -> None:
        from focl import freshness, index
        root = tmp_python_project
        focl = self._setup(root)
        before_keep = index.get_module(focl.read_text(encoding="utf-8"), "keep.py")

        (root / "edit.py").write_text("def edit(): return 1\n", encoding="utf-8")
        (root / "gone.py").unlink()
        new = root / "fresh.py"
        new.write_text("def fresh(): ...\n", encoding="utf-8")
        future = focl.stat().st_mtime + 100
        os.utime(new, (future, future))

        result = CliRunner().invoke(main, ["sync", str(root), "--changed"])
        assert result.exit_code == 0, result.output
        out = focl.read_text(encoding="utf-8")

        assert len(llm_calls) == 2                       # edit.py + fresh.py only
        assert index.get_module(out, "keep.py") == before_keep
        assert "REGENERATED edit.py" in out
        assert "REGENERATED fresh.py" in out
        assert "gone.py" not in index.module_paths(out)
        # Regenerated blocks are stamped, so the map is now fully fresh.
        report = freshness.check(out, root, [root / "keep.py", root / "edit.py", new],
                                 focl_mtime=focl.stat().st_mtime)
        assert not report.stale

    def test_nothing_to_do_makes_no_call(self, tmp_python_project: Path,
                                         llm_calls: list[str]) -> None:
        self._setup(tmp_python_project)
        result = CliRunner().invoke(main, ["sync", str(tmp_python_project), "--changed"])
        assert result.exit_code == 0
        assert "nothing to do" in result.output.lower()
        assert llm_calls == []

    def test_dry_run_lists_and_writes_nothing(self, tmp_python_project: Path,
                                              llm_calls: list[str]) -> None:
        root = tmp_python_project
        focl = self._setup(root)
        before = focl.read_text(encoding="utf-8")
        (root / "edit.py").write_text("def edit(): return 2\n", encoding="utf-8")
        result = CliRunner().invoke(main, ["sync", str(root), "--changed", "--dry-run"])
        assert result.exit_code == 0
        assert "edit.py" in result.output
        assert "Would update" in result.output
        assert focl.read_text(encoding="utf-8") == before
        assert llm_calls == []

    def test_unstamped_map_refuses(self, tmp_python_project: Path,
                                   llm_calls: list[str]) -> None:
        focl = tmp_python_project / (tmp_python_project.name + ".focl")
        focl.write_text("# src: demo/service.py\nMOD s\n", encoding="utf-8")
        result = CliRunner().invoke(main, ["sync", str(tmp_python_project), "--changed"])
        assert result.exit_code == 1
        assert "no per-module hashes" in " ".join(result.output.split())
        assert llm_calls == []

    def test_missing_map(self, tmp_python_project: Path, llm_calls: list[str]) -> None:
        result = CliRunner().invoke(main, ["sync", str(tmp_python_project), "--changed"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_dry_run_requires_changed(self, tmp_python_project: Path) -> None:
        result = CliRunner().invoke(main, ["sync", str(tmp_python_project), "--dry-run"])
        assert result.exit_code == 2
