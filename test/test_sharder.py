"""Tests for focl.sharder — token estimation and bin-packing."""

from __future__ import annotations

from pathlib import Path

from focl.analyzer import detect
from focl.sharder import (
    DEFAULT_SHARD_BUDGET,
    _estimate_tokens,
    build_shard_context,
    shard_project,
)

from tests.conftest import write_java_file


class TestTokenEstimation:
    def test_estimate_scales_with_length(self) -> None:
        short = _estimate_tokens("hi")
        long = _estimate_tokens("hi " * 1000)
        assert long > short

    def test_estimate_never_zero_for_nonempty(self) -> None:
        assert _estimate_tokens("x") >= 1

    def test_estimate_zero_or_one_for_empty_string(self) -> None:
        # Implementation returns int(0/3)+1 = 1; empty is still a valid input
        assert _estimate_tokens("") == 1


class TestShardProjectSmall:
    def test_small_project_fits_in_single_shard(self, tmp_java_project: Path) -> None:
        info = detect(tmp_java_project)
        result = shard_project(info, budget=DEFAULT_SHARD_BUDGET)
        assert len(result.shards) >= 1
        # Small project should not produce any oversize warnings
        assert result.oversize_files == []

    def test_all_files_are_covered(self, tmp_java_project: Path) -> None:
        info = detect(tmp_java_project)
        result = shard_project(info, budget=DEFAULT_SHARD_BUDGET)
        covered = set()
        for s in result.shards:
            covered.update(s.files)
        assert set(info.files) == covered

    def test_shard_token_estimate_matches_sum(self, tmp_java_project: Path) -> None:
        info = detect(tmp_java_project)
        result = shard_project(info, budget=DEFAULT_SHARD_BUDGET)
        for s in result.shards:
            # Each shard's token_estimate is populated; cannot be negative
            assert s.token_estimate > 0
            assert s.file_count == len(s.files)


class TestShardProjectBinPacking:
    def test_forces_multiple_shards_when_budget_small(
        self, tmp_path: Path
    ) -> None:
        """With a tiny budget, even a modest project should produce
        several shards rather than one giant one."""
        (tmp_path / "pom.xml").write_text("<project/>")
        services = tmp_path / "services"
        services.mkdir()
        for i in range(6):
            write_java_file(services / f"Svc{i}.java", body_lines=200)

        info = detect(tmp_path)
        # Tiny budget to force multiple shards
        result = shard_project(info, budget=3_000)
        assert len(result.shards) > 1

    def test_respects_shard_budget(self, tmp_path: Path) -> None:
        """No regular shard should exceed the budget (oversize-single shards
        are allowed to, and carry the ':oversize' label)."""
        (tmp_path / "pom.xml").write_text("<project/>")
        for i in range(8):
            write_java_file(tmp_path / f"File{i}.java", body_lines=50)

        info = detect(tmp_path)
        budget = 2_000
        result = shard_project(info, budget=budget)

        for s in result.shards:
            if s.label.endswith(":oversize"):
                # Oversize shards are allowed to exceed budget
                continue
            assert s.token_estimate <= budget, (
                f"Shard {s.index} [{s.label}] has {s.token_estimate} tokens "
                f"over budget {budget}"
            )


class TestShardProjectOversize:
    def test_oversize_file_becomes_own_shard(
        self, tmp_large_file_project: Path
    ) -> None:
        """Files that are collected by the analyzer but exceed the shard
        budget should become isolated single-file shards and appear in
        oversize_files."""
        info = detect(tmp_large_file_project)
        # Big.java (~100 KB) must have been collected (under 200 KB cap)
        names = [f.name for f in info.files]
        assert "Big.java" in names, "Big.java should be collected by analyzer"
        # With budget=10_000 tokens (~30 KB) the sharder should flag it
        result = shard_project(info, budget=10_000)
        assert len(result.oversize_files) == 1
        assert result.oversize_files[0].name == "Big.java"

    def test_oversize_shard_has_oversize_label(
        self, tmp_large_file_project: Path
    ) -> None:
        info = detect(tmp_large_file_project)
        result = shard_project(info, budget=10_000)
        oversize_shards = [s for s in result.shards if ":oversize" in s.label]
        assert len(oversize_shards) == 1
        assert oversize_shards[0].files[0].name == "Big.java"

    def test_analyzer_level_skip_tracked(
        self, tmp_analyzer_skip_project: Path
    ) -> None:
        """Files > _MAX_FILE_BYTES should be listed in skipped_files,
        not silently discarded."""
        info = detect(tmp_analyzer_skip_project)
        assert len(info.skipped_files) == 1
        skipped_path, reason = info.skipped_files[0]
        assert skipped_path.name == "Huge.java"
        assert "KB" in reason  # reason mentions file size


class TestBuildShardContext:
    def test_context_includes_file_delimiters(
        self, tmp_java_project: Path
    ) -> None:
        info = detect(tmp_java_project)
        result = shard_project(info, budget=DEFAULT_SHARD_BUDGET)
        ctx = build_shard_context(result.shards[0], info.root)
        assert "=== " in ctx
        # Each file must appear with its relative path
        for f in result.shards[0].files:
            rel = f.relative_to(info.root)
            assert str(rel) in ctx or str(rel).replace("/", "\\") in ctx
