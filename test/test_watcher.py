"""Tests for focl.watcher — change filtering (.focl exclusion, ignored dirs)."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

from watchdog.events import FileSystemEvent

from focl.watcher import _Handler


def _make_event(path: str, is_directory: bool = False) -> FileSystemEvent:
    ev = FileSystemEvent(path)
    ev.is_directory = is_directory
    return ev


class TestHandlerFiltering:
    """_Handler should filter non-source events before queuing them."""

    def _make_handler(self, root: Path, callback) -> _Handler:
        return _Handler(root, debounce_seconds=0.01, callback=callback)

    def test_ignores_focl_files(self, tmp_path: Path) -> None:
        """Writing to a .focl file must never trigger a rebuild — otherwise
        the watcher would loop endlessly when it writes its own output."""
        cb = MagicMock()
        h = self._make_handler(tmp_path, cb)
        h.on_modified(_make_event(str(tmp_path / "project.focl")))
        # No timer should have been scheduled
        assert h._timer is None
        cb.assert_not_called()

    def test_ignores_binary_extensions(self, tmp_path: Path) -> None:
        cb = MagicMock()
        h = self._make_handler(tmp_path, cb)
        h.on_modified(_make_event(str(tmp_path / "logo.png")))
        assert h._timer is None
        cb.assert_not_called()

    def test_ignores_paths_in_node_modules(self, tmp_path: Path) -> None:
        cb = MagicMock()
        h = self._make_handler(tmp_path, cb)
        target = tmp_path / "node_modules" / "lib" / "index.js"
        h.on_modified(_make_event(str(target)))
        assert h._timer is None
        cb.assert_not_called()

    def test_ignores_paths_in_venv(self, tmp_path: Path) -> None:
        cb = MagicMock()
        h = self._make_handler(tmp_path, cb)
        target = tmp_path / ".venv" / "lib" / "mod.py"
        h.on_modified(_make_event(str(target)))
        assert h._timer is None
        cb.assert_not_called()

    def test_ignores_directory_events(self, tmp_path: Path) -> None:
        cb = MagicMock()
        h = self._make_handler(tmp_path, cb)
        h.on_modified(_make_event(str(tmp_path / "src"), is_directory=True))
        assert h._timer is None
        cb.assert_not_called()

    def test_ignores_unknown_extensions(self, tmp_path: Path) -> None:
        cb = MagicMock()
        h = self._make_handler(tmp_path, cb)
        h.on_modified(_make_event(str(tmp_path / "notes.txt")))
        assert h._timer is None
        cb.assert_not_called()


class TestHandlerAcceptance:
    """_Handler should queue legitimate source file events."""

    def _make_handler(self, root: Path, callback) -> _Handler:
        return _Handler(root, debounce_seconds=0.01, callback=callback)

    def test_java_file_is_queued(self, tmp_path: Path) -> None:
        cb = MagicMock()
        h = self._make_handler(tmp_path, cb)
        target = tmp_path / "src" / "UserService.java"
        h.on_modified(_make_event(str(target)))
        assert target in h._pending
        assert h._timer is not None
        # Cleanup: wait briefly for the debounce timer to fire
        h._timer.cancel()

    def test_python_file_is_queued(self, tmp_path: Path) -> None:
        cb = MagicMock()
        h = self._make_handler(tmp_path, cb)
        target = tmp_path / "demo" / "service.py"
        h.on_modified(_make_event(str(target)))
        assert target in h._pending
        h._timer.cancel()

    def test_debounce_coalesces_rapid_events(self, tmp_path: Path) -> None:
        """Multiple rapid events should fire the callback exactly once."""
        fired = threading.Event()
        received: list[list[Path]] = []

        def callback(paths: list[Path]) -> None:
            received.append(paths)
            fired.set()

        h = _Handler(tmp_path, debounce_seconds=0.05, callback=callback)
        for i in range(5):
            h.on_modified(_make_event(str(tmp_path / f"Svc{i}.java")))

        # Wait for the debounced callback
        assert fired.wait(timeout=2.0), "callback was never fired"
        # Should have been called once with all 5 paths
        assert len(received) == 1
        assert len(received[0]) == 5
