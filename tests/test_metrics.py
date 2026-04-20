"""Tests for focl.metrics — compression measurement in tokens and bytes."""

from __future__ import annotations

from pathlib import Path

from focl.analyzer import detect
from focl.metrics import CompressionMetrics, measure, measure_from_paths


class TestCompressionMetricsProperties:
    def test_token_ratio_computation(self) -> None:
        m = CompressionMetrics(
            source_tokens=1000, focl_tokens=200,
            source_bytes=5000, focl_bytes=1000, exact=False,
        )
        assert m.token_ratio == 5.0
        assert m.token_saving_pct == 80.0

    def test_byte_ratio_computation(self) -> None:
        m = CompressionMetrics(
            source_tokens=1000, focl_tokens=200,
            source_bytes=5000, focl_bytes=1000, exact=False,
        )
        assert m.byte_ratio == 5.0
        assert m.byte_saving_pct == 80.0

    def test_zero_focl_tokens_handled(self) -> None:
        """Edge case: empty FOCL shouldn't crash the ratio computation."""
        m = CompressionMetrics(
            source_tokens=1000, focl_tokens=0,
            source_bytes=1000, focl_bytes=0, exact=False,
        )
        assert m.token_ratio == 0.0
        assert m.byte_ratio == 0.0

    def test_zero_source_handled(self) -> None:
        """Edge case: empty source shouldn't divide by zero in saving pct."""
        m = CompressionMetrics(
            source_tokens=0, focl_tokens=100,
            source_bytes=0, focl_bytes=100, exact=False,
        )
        assert m.token_saving_pct == 0.0
        assert m.byte_saving_pct == 0.0


class TestMeasure:
    def test_measure_returns_positive_counts(
        self, tmp_java_project: Path
    ) -> None:
        info = detect(tmp_java_project)
        fake_focl = "SERVICE X { ACTION do -> DTO }\n"
        m = measure(info, fake_focl, exact=False)
        assert m.source_tokens > 0
        assert m.focl_tokens > 0
        assert m.source_bytes > 0
        assert m.focl_bytes > 0

    def test_measure_compressed_is_smaller(
        self, tmp_java_project: Path
    ) -> None:
        info = detect(tmp_java_project)
        # A trivially tiny FOCL should be smaller than the source
        tiny_focl = "S"
        m = measure(info, tiny_focl, exact=False)
        assert m.focl_tokens < m.source_tokens
        assert m.token_saving_pct > 0

    def test_measure_marks_estimate(self, tmp_java_project: Path) -> None:
        info = detect(tmp_java_project)
        m = measure(info, "SERVICE X\n", exact=False)
        assert m.exact is False


class TestMeasureFromPaths:
    def test_reads_focl_from_disk(
        self, tmp_java_project: Path, tmp_path: Path
    ) -> None:
        info = detect(tmp_java_project)
        focl_file = tmp_path / "out.focl"
        focl_file.write_text("SERVICE UserService\n  ACTION get -> UserDTO\n")
        m = measure_from_paths(info, focl_file, exact=False)
        assert m.focl_tokens > 0
        assert m.focl_bytes == focl_file.stat().st_size
