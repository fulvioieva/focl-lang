"""Tests for focl.validator and the `focl validate` command (offline)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from focl.cli import main
from focl.validator import validate

_VALID = """\
# FOCL file for project: demo
# Language: java

# src: services/UserService.java
SERVICE UserService
  OWNED_FETCH(User, by=id)
  PERSIST User

# src: controllers/UserController.java
CTRL UserController
  PAGE Booking FILTER_EQ(status)
"""


class TestValidate:
    def test_clean_file_is_ok(self) -> None:
        res = validate(_VALID)
        assert res.ok
        assert res.errors == []
        assert res.warnings == []
        assert res.stats["modules"] == 2

    def test_empty_file_errors(self) -> None:
        res = validate("   \n")
        assert not res.ok
        assert any("empty" in e.lower() for e in res.errors)

    def test_code_fences_error(self) -> None:
        res = validate("```focl\n# src: a.py\nMOD a\n```\n")
        assert not res.ok
        assert any("fence" in e.lower() for e in res.errors)

    def test_empty_block_errors(self) -> None:
        content = "# src: a.py\n# src: b.py\nMOD b\n  go()\n"
        res = validate(content)
        assert not res.ok
        assert any("a.py" in e for e in res.errors)

    def test_src_without_path_errors(self) -> None:
        res = validate("# src:\nMOD a\n  x()\n")
        assert not res.ok
        assert any("no path" in e.lower() for e in res.errors)

    def test_no_annotations_warns_but_ok(self) -> None:
        res = validate("SERVICE X\n  do()\n")
        assert res.ok  # warnings don't fail
        assert any("no `# src:`" in w.lower() for w in res.warnings)

    def test_duplicate_paths_warn(self) -> None:
        content = (
            "# src: a.py\nMOD a\n  x()\n\n"
            "# src: a.py\nMOD a2\n  y()\n"
        )
        res = validate(content)
        assert any("duplicate" in w.lower() for w in res.warnings)

    def test_primitive_histogram(self) -> None:
        res = validate(_VALID)
        prims = res.stats["primitives"]
        assert prims.get("OWNED_FETCH") == 1
        assert prims.get("PERSIST") == 1
        assert "FILTER*" in prims  # FILTER_ prefix rendered as FILTER*


class TestValidateCLI:
    def test_valid_exits_zero(self, tmp_java_project: Path) -> None:
        focl = tmp_java_project / (tmp_java_project.name + ".focl")
        focl.write_text(_VALID, encoding="utf-8")
        result = CliRunner().invoke(main, ["validate", str(tmp_java_project)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_fenced_exits_nonzero(self, tmp_java_project: Path) -> None:
        focl = tmp_java_project / (tmp_java_project.name + ".focl")
        focl.write_text("```\n# src: a\nMOD a\n```\n", encoding="utf-8")
        result = CliRunner().invoke(main, ["validate", str(tmp_java_project)])
        assert result.exit_code == 1
        assert "invalid" in result.output.lower()

    def test_strict_fails_on_warning(self, tmp_java_project: Path) -> None:
        focl = tmp_java_project / (tmp_java_project.name + ".focl")
        focl.write_text("SERVICE X\n  do()\n", encoding="utf-8")  # no `# src:` -> warning
        ok = CliRunner().invoke(main, ["validate", str(tmp_java_project)])
        strict = CliRunner().invoke(main, ["validate", str(tmp_java_project), "--strict"])
        assert ok.exit_code == 0
        assert strict.exit_code == 1

    def test_missing_file(self, tmp_java_project: Path) -> None:
        result = CliRunner().invoke(main, ["validate", str(tmp_java_project)])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
