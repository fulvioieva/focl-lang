"""Tests for focl.freshness — per-module content-hash stamps (offline)."""

from __future__ import annotations

import os
from pathlib import Path

from focl import freshness, index


def _project(tmp_path: Path) -> Path:
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "A.py").write_text("def a(): ...\n", encoding="utf-8")
    (tmp_path / "B.py").write_text("def b(): ...\n", encoding="utf-8")
    return tmp_path


_MAP = """\
# FOCL file for project: demo

# src: svc/A.py
MOD a
  a()

# src: B.py
MOD b
  b()
"""


class TestHash:
    def test_line_endings_do_not_matter(self, tmp_path: Path) -> None:
        lf = tmp_path / "lf.py"
        crlf = tmp_path / "crlf.py"
        lf.write_bytes(b"x = 1\ny = 2\n")
        crlf.write_bytes(b"x = 1\r\ny = 2\r\n")
        assert freshness.file_hash(lf) == freshness.file_hash(crlf)

    def test_content_change_changes_hash(self, tmp_path: Path) -> None:
        f = tmp_path / "f.py"
        f.write_text("a\n", encoding="utf-8")
        h1 = freshness.file_hash(f)
        f.write_text("b\n", encoding="utf-8")
        os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 10**9))
        assert freshness.file_hash(f) != h1


class TestStamp:
    def test_stamp_all_blocks(self, tmp_path: Path) -> None:
        root = _project(tmp_path)
        stamped = freshness.stamp(_MAP, root)
        hashes = index.module_hashes(stamped)
        assert hashes["svc/A.py"] == freshness.file_hash(root / "svc" / "A.py")
        assert hashes["B.py"] == freshness.file_hash(root / "B.py")
        # Paths (and therefore lookups) are unchanged by the stamp.
        assert index.module_paths(stamped) == ["svc/A.py", "B.py"]
        assert "MOD a" in index.get_module(stamped, "svc/A.py")

    def test_stamp_is_idempotent(self, tmp_path: Path) -> None:
        root = _project(tmp_path)
        once = freshness.stamp(_MAP, root)
        assert freshness.stamp(once, root) == once

    def test_unknown_paths_left_unstamped(self, tmp_path: Path) -> None:
        root = _project(tmp_path)
        content = "# src: nowhere/X.py\nMOD x\n"
        assert freshness.stamp(content, root) == content

    def test_backslash_paths_resolve(self, tmp_path: Path) -> None:
        root = _project(tmp_path)
        stamped = freshness.stamp("# src: svc\\A.py\nMOD a\n", root)
        assert index.module_hashes(stamped)["svc\\A.py"] is not None

    def test_stamp_block_forces_path(self) -> None:
        out = freshness.stamp_block("# src: wrong.py\nMOD a\n", "svc/A.py", "abcdef123456")
        assert out.splitlines()[0] == "# src: svc/A.py @h:abcdef123456"
        assert "MOD a" in out

    def test_stamp_block_adds_missing_marker(self) -> None:
        out = freshness.stamp_block("MOD a\n", "svc/A.py", "abcdef123456")
        assert out.startswith("# src: svc/A.py @h:abcdef123456\nMOD a")


class TestStatus:
    def test_fresh_changed_deleted_unverified(self, tmp_path: Path) -> None:
        root = _project(tmp_path)
        stamped = freshness.stamp(_MAP, root) + "\n# src: legacy.py\nMOD l\n"
        (root / "svc" / "A.py").write_text("def a(): return 1\n", encoding="utf-8")
        (root / "B.py").unlink()
        status = freshness.module_status(stamped, root)
        assert status == {
            "svc/A.py": freshness.CHANGED,
            "B.py": freshness.DELETED,
            "legacy.py": freshness.UNVERIFIED,
        }

    def test_status_subset(self, tmp_path: Path) -> None:
        root = _project(tmp_path)
        stamped = freshness.stamp(_MAP, root)
        assert freshness.module_status(stamped, root, ["B.py"]) == {"B.py": freshness.FRESH}


class TestCheck:
    def test_up_to_date(self, tmp_path: Path) -> None:
        root = _project(tmp_path)
        stamped = freshness.stamp(_MAP, root)
        files = [root / "svc" / "A.py", root / "B.py"]
        report = freshness.check(stamped, root, files)
        assert report.tracked and not report.stale
        assert report.fresh == 2

    def test_reports_changed_and_new(self, tmp_path: Path) -> None:
        root = _project(tmp_path)
        stamped = freshness.stamp(_MAP, root)
        focl_mtime = (root / "B.py").stat().st_mtime
        (root / "B.py").write_text("def b(): return 2\n", encoding="utf-8")
        new = root / "C.py"
        new.write_text("def c(): ...\n", encoding="utf-8")
        future = focl_mtime + 100
        os.utime(new, (future, future))
        report = freshness.check(stamped, root, [root / "svc" / "A.py", root / "B.py", new],
                                 focl_mtime=focl_mtime)
        assert report.changed == ["B.py"]
        assert report.added == ["C.py"]
        assert report.stale_paths == ["B.py", "C.py"]

    def test_unmapped_files_older_than_map_are_not_new(self, tmp_path: Path) -> None:
        root = _project(tmp_path)
        stamped = freshness.stamp(_MAP, root)
        old = root / "trivial.py"
        old.write_text("\n", encoding="utf-8")
        report = freshness.check(stamped, root, [old], focl_mtime=old.stat().st_mtime + 100)
        assert report.added == []

    def test_unstamped_map_is_not_tracked(self, tmp_path: Path) -> None:
        root = _project(tmp_path)
        report = freshness.check(_MAP, root, [])
        assert not report.tracked
        assert report.unverified == ["svc/A.py", "B.py"]
