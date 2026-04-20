"""File system watcher: detects source changes and triggers .focl updates."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .analyzer import _IGNORE_DIRS, _IGNORE_EXTENSIONS, _GENERIC_EXTENSIONS

# Files that must never trigger a rebuild — prevents infinite loops when
# the generated .focl file sits inside the watched directory.
_SELF_EXTENSIONS = {".focl"}


class _Handler(FileSystemEventHandler):
    def __init__(self, root: Path, debounce_seconds: float,
                 callback: Callable[[list[Path]], None]) -> None:
        self._root = root
        self._debounce = debounce_seconds
        self._callback = callback
        self._pending: set[Path] = set()
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_modified(self, event: FileSystemEvent) -> None:
        self._enqueue(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._enqueue(event)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._enqueue(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        # Treat both source and destination as change events
        self._enqueue(event)
        if hasattr(event, "dest_path") and event.dest_path:
            dest_event = FileSystemEvent(event.dest_path)
            dest_event.is_directory = event.is_directory
            self._enqueue(dest_event)

    def _enqueue(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        suffix = path.suffix.lower()

        # Skip the .focl file itself to avoid self-triggered rebuilds
        if suffix in _SELF_EXTENSIONS:
            return
        # Skip ignored binary/artefact extensions
        if suffix in _IGNORE_EXTENSIONS:
            return
        # Only react to source-like extensions
        if suffix not in _GENERIC_EXTENSIONS:
            return
        # Skip paths inside ignored directories (node_modules, .venv, ...)
        for part in path.parts:
            if part in _IGNORE_DIRS:
                return

        # Debounce: coalesce rapid successive events into a single callback
        with self._lock:
            self._pending.add(path)
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            changed = list(self._pending)
            self._pending.clear()
        if changed:
            self._callback(changed)


def watch(root: Path, callback: Callable[[list[Path]], None],
          debounce: float = 2.0) -> None:
    """Block and watch root for source changes; call callback with changed paths.

    The generated `.focl` file is automatically excluded from change detection
    to prevent infinite update loops when it lives inside the watched tree.
    """
    handler = _Handler(root, debounce, callback)
    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()
    try:
        while observer.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
