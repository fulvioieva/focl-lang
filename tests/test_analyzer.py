"""Tests for focl.analyzer — language detection and file collection."""

from __future__ import annotations

from pathlib import Path

from focl.analyzer import _collect_files, _detect_language, build_context, detect


class TestLanguageDetection:
    def test_detects_spring_boot_from_pom(self, tmp_java_project: Path) -> None:
        lang, fw = _detect_language(tmp_java_project)
        assert lang == "java"
        assert fw == "spring-boot"

    def test_detects_python_from_pyproject(self, tmp_python_project: Path) -> None:
        lang, fw = _detect_language(tmp_python_project)
        assert lang == "python"

    def test_detects_typescript_from_package_json(
        self, tmp_project_with_ignored: Path
    ) -> None:
        lang, fw = _detect_language(tmp_project_with_ignored)
        assert lang == "typescript"

    def test_returns_unknown_for_empty_dir(self, tmp_path: Path) -> None:
        lang, fw = _detect_language(tmp_path)
        assert lang == "unknown"
        assert fw is None

    def test_no_spring_boot_without_keyword(self, tmp_path: Path) -> None:
        """A pom.xml that lacks the literal 'spring-boot' keyword should
        fall back to plain java framework, not spring-boot."""
        (tmp_path / "pom.xml").write_text(
            "<project><groupId>org.springframework.boot</groupId></project>"
        )
        lang, fw = _detect_language(tmp_path)
        assert lang == "java"
        assert fw == "java"  # no 'spring-boot' hyphen → falls back


class TestFileCollection:
    def test_collects_source_files(self, tmp_java_project: Path) -> None:
        info = detect(tmp_java_project)
        names = sorted(f.name for f in info.files)
        assert "UserService.java" in names
        assert "UserController.java" in names
        assert "pom.xml" in names

    def test_ignores_node_modules(self, tmp_project_with_ignored: Path) -> None:
        info = detect(tmp_project_with_ignored)
        # Use relative paths: absolute paths include pytest's temp dir name
        # (e.g. test_ignores_node_modules0) which contains "node_modules"
        rel_paths = [str(f.relative_to(tmp_project_with_ignored)) for f in info.files]
        assert not any(p.startswith("node_modules") for p in rel_paths)

    def test_ignores_venv(self, tmp_project_with_ignored: Path) -> None:
        info = detect(tmp_project_with_ignored)
        rel_paths = [str(f.relative_to(tmp_project_with_ignored)) for f in info.files]
        assert not any(p.startswith(".venv") for p in rel_paths)

    def test_ignores_binary_extensions(self, tmp_project_with_ignored: Path) -> None:
        info = detect(tmp_project_with_ignored)
        names = [f.name for f in info.files]
        assert "logo.png" not in names
        assert "archive.zip" not in names

    def test_collects_index_ts(self, tmp_project_with_ignored: Path) -> None:
        info = detect(tmp_project_with_ignored)
        names = [f.name for f in info.files]
        assert "index.ts" in names

    def test_total_bytes_nonzero(self, tmp_java_project: Path) -> None:
        info = detect(tmp_java_project)
        assert info.total_bytes > 0

    def test_files_are_sorted(self, tmp_java_project: Path) -> None:
        info = detect(tmp_java_project)
        paths = [str(f) for f in info.files]
        assert paths == sorted(paths)

    def test_skipped_files_reported(self, tmp_analyzer_skip_project: Path) -> None:
        """Files that exceed _MAX_FILE_BYTES should appear in skipped_files
        rather than being silently dropped."""
        info = detect(tmp_analyzer_skip_project)
        assert len(info.skipped_files) == 1
        path, reason = info.skipped_files[0]
        assert path.name == "Huge.java"
        assert "KB" in reason

    def test_skipped_files_not_in_collected(
        self, tmp_analyzer_skip_project: Path
    ) -> None:
        """A skipped file must not also appear in info.files."""
        info = detect(tmp_analyzer_skip_project)
        collected_names = {f.name for f in info.files}
        skipped_names = {p.name for p, _ in info.skipped_files}
        assert not collected_names & skipped_names


class TestBuildContext:
    def test_build_context_wraps_files_with_delimiters(
        self, tmp_java_project: Path
    ) -> None:
        info = detect(tmp_java_project)
        ctx = build_context(info)
        assert "=== " in ctx
        assert "UserService.java" in ctx
        assert "public class UserService" in ctx

    def test_build_context_uses_relative_paths(
        self, tmp_java_project: Path
    ) -> None:
        info = detect(tmp_java_project)
        ctx = build_context(info)
        # Should see relative path like "services/UserService.java", not absolute
        assert str(tmp_java_project) not in ctx
        assert "services/UserService.java" in ctx or "services\\UserService.java" in ctx
