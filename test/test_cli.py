"""Smoke tests for focl.cli — exercise commands without hitting the API."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

import focl.cli as cli_module
from focl.cli import main


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
