"""Smoke tests for focl.cli — exercise commands without hitting the API."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from focl.cli import (
    _CLAUDE_END,
    _CLAUDE_START,
    _HOOK_COMMAND,
    MCP_PREFIX_PLUGIN,
    _enabled_focl_plugin,
    _merge_mcp_json,
    _merge_settings_hook,
    _render_agent,
    _render_skill,
    _upsert_claude_pointer,
    main,
)

_REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch) -> Path:
    """Keep the real ~/.claude/settings.json (enabled plugins) out of the tests."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


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
    def test_starts_without_focl_file(self, tmp_java_project: Path, monkeypatch) -> None:
        # The plugin registers the server in every project: a missing map must
        # not make it fail, only warn on stderr (stdout is the JSON-RPC channel).
        import focl.cli as cli_mod
        served: list[Path] = []
        monkeypatch.setattr(cli_mod, "mcp_serve", lambda out, root: served.append(out))
        result = CliRunner().invoke(main, ["mcp", str(tmp_java_project)])
        assert result.exit_code == 0
        assert len(served) == 1
        assert "not found yet" in result.stderr


class TestHookAndSkillSingleSource:
    """The plugin and `claude-setup` must ship the same hook and skill."""

    def test_plugin_hook_matches_claude_setup(self) -> None:
        hooks = json.loads((_REPO / "plugin" / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        commands = [h["command"] for e in hooks["hooks"]["SessionStart"] for h in e["hooks"]]
        assert commands == [_HOOK_COMMAND]

    def test_plugin_skill_matches_package_asset(self) -> None:
        plugin_skill = (_REPO / "plugin" / "skills" / "focl" / "SKILL.md").read_text(
            encoding="utf-8")
        assert plugin_skill == _render_skill(), (
            "plugin/skills/focl/SKILL.md drifted from focl/assets/SKILL.md - "
            "edit the asset and copy it over"
        )

    def test_plugin_agent_matches_template(self) -> None:
        plugin_agent = (_REPO / "plugin" / "agents" / "focl-explorer.md").read_text(
            encoding="utf-8")
        assert plugin_agent == _render_agent(MCP_PREFIX_PLUGIN), (
            "plugin/agents/focl-explorer.md drifted from focl/assets/focl-explorer.md - "
            "regenerate it with _render_agent(MCP_PREFIX_PLUGIN)"
        )

    def test_agent_prefixes(self) -> None:
        project = _render_agent()
        assert '"mcp__focl__focl_search"' in project
        assert "{{MCP}}" not in project
        assert '"mcp__plugin_focl_focl__focl_search"' in _render_agent(MCP_PREFIX_PLUGIN)

    def test_hook_command_is_hook_mode_with_fallback(self) -> None:
        assert _HOOK_COMMAND.startswith("focl check --hook || echo ")

    def test_legacy_hook_upgraded_in_place(self) -> None:
        existing = {"hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": "focl check"}]}
        ]}}
        out = _merge_settings_hook(existing)
        commands = [h["command"] for e in out["hooks"]["SessionStart"] for h in e["hooks"]]
        assert commands == [_HOOK_COMMAND]


class TestCheckHookMode:
    def test_silent_without_map(self, tmp_java_project: Path) -> None:
        result = CliRunner().invoke(main, ["check", str(tmp_java_project), "--hook"])
        assert result.exit_code == 0
        assert result.output == ""

    def test_reports_with_map(self, tmp_java_project: Path) -> None:
        focl = tmp_java_project / (tmp_java_project.name + ".focl")
        focl.write_text("SERVICE X\n", encoding="utf-8")
        result = CliRunner().invoke(main, ["check", str(tmp_java_project), "--hook"])
        assert "up to date" in result.output.lower()


class TestPluginAwareSetup:
    def _enable(self, settings: Path, value: bool = True) -> None:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"enabledPlugins": {"focl@focl-lang": value}}),
                            encoding="utf-8")

    def test_detects_user_level_plugin(self, tmp_java_project: Path,
                                       _isolated_home: Path) -> None:
        self._enable(_isolated_home / ".claude" / "settings.json")
        assert _enabled_focl_plugin(tmp_java_project) == (
            _isolated_home / ".claude" / "settings.json")

    def test_detects_project_local_plugin(self, tmp_java_project: Path) -> None:
        self._enable(tmp_java_project / ".claude" / "settings.local.json")
        assert _enabled_focl_plugin(tmp_java_project) is not None

    def test_disabled_or_other_plugins_ignored(self, tmp_java_project: Path,
                                               _isolated_home: Path) -> None:
        self._enable(_isolated_home / ".claude" / "settings.json", value=False)
        assert _enabled_focl_plugin(tmp_java_project) is None
        (_isolated_home / ".claude" / "settings.json").write_text(
            json.dumps({"enabledPlugins": {"foclx@m": True}}), encoding="utf-8")
        assert _enabled_focl_plugin(tmp_java_project) is None

    def test_setup_writes_only_pointer_when_plugin_enabled(
        self, tmp_java_project: Path, _isolated_home: Path
    ) -> None:
        self._enable(_isolated_home / ".claude" / "settings.json")
        result = CliRunner().invoke(main, ["claude-setup", str(tmp_java_project)])
        assert result.exit_code == 0
        assert "plugin is enabled" in result.output
        assert (tmp_java_project / "CLAUDE.md").exists()
        assert not (tmp_java_project / ".mcp.json").exists()
        assert not (tmp_java_project / ".claude" / "skills").exists()

    def test_warns_about_duplicate_standalone_files(
        self, tmp_java_project: Path, _isolated_home: Path
    ) -> None:
        CliRunner().invoke(main, ["claude-setup", str(tmp_java_project)])  # standalone
        self._enable(_isolated_home / ".claude" / "settings.json")
        result = CliRunner().invoke(main, ["claude-setup", str(tmp_java_project)])
        flat = " ".join(result.output.split())
        assert "duplicate the plugin" in flat
        assert ".mcp.json (focl MCP server)" in flat
        assert ".claude/settings.json (focl check hook)" in flat
        assert ".claude/agents/focl-explorer.md" in flat

    def test_standalone_flag_overrides(self, tmp_java_project: Path,
                                       _isolated_home: Path) -> None:
        self._enable(_isolated_home / ".claude" / "settings.json")
        result = CliRunner().invoke(main, ["claude-setup", str(tmp_java_project),
                                           "--standalone"])
        assert result.exit_code == 0
        assert (tmp_java_project / ".mcp.json").exists()
        skill = tmp_java_project / ".claude" / "skills" / "focl" / "SKILL.md"
        assert skill.read_text(encoding="utf-8") == _render_skill()
        agent = tmp_java_project / ".claude" / "agents" / "focl-explorer.md"
        assert agent.read_text(encoding="utf-8") == _render_agent()  # project prefix


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
