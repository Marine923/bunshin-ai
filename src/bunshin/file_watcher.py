"""Real-time file watching for bunshin.

Uses watchdog to monitor a directory tree and re-ingest any file that
changes (or a new file that appears) — without waiting for the hourly
update job. Useful when the user edits a markdown file and wants the
new content searchable immediately.

Design notes:
  - Debounces by `idle_seconds` (default 3) per path: a series of saves
    in quick succession is collapsed into one re-ingest.
  - Uses watchdog's PatternMatchingEventHandler to filter by extension.
  - Each batch opens its own sqlite connection (watchdog runs callbacks
    on a worker thread, so we don't share the main thread's conn).
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

from bunshin.ingestion.files import DEFAULT_EXTENSIONS, import_files
from bunshin.storage import init_db


try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


class _DebounceWorker:
    """Coalesces per-path events: only re-imports after `idle_seconds` of quiet."""

    def __init__(
        self,
        db_path: Path,
        root: Path,
        extensions: set[str],
        idle_seconds: float = 3.0,
        on_import: Optional[Callable[[dict], None]] = None,
    ):
        self.db_path = db_path
        self.root = root
        self.extensions = extensions
        self.idle_seconds = idle_seconds
        self.on_import = on_import
        self._pending: dict[Path, float] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def schedule(self, path: Path) -> None:
        with self._lock:
            self._pending[path] = time.monotonic() + self.idle_seconds

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            due: list[Path] = []
            with self._lock:
                for p, when in list(self._pending.items()):
                    if when <= now:
                        due.append(p)
                        self._pending.pop(p, None)
            if due:
                self._import_batch(due)
            time.sleep(0.5)

    def _import_batch(self, paths: list[Path]) -> None:
        try:
            conn = init_db(self.db_path)
        except sqlite3.Error:
            return
        try:
            for p in paths:
                if not p.exists() or p.suffix.lower() not in self.extensions:
                    continue
                # Re-use the batch importer pointed at the single file.
                stats = import_files(conn, p, extensions=self.extensions, force=True)
                if self.on_import:
                    self.on_import({"path": str(p), **stats})
        finally:
            conn.close()


if WATCHDOG_AVAILABLE:
    class _Handler(FileSystemEventHandler):
        def __init__(self, worker: _DebounceWorker):
            self.worker = worker

        def on_modified(self, event):
            if event.is_directory:
                return
            self.worker.schedule(Path(event.src_path))

        def on_created(self, event):
            if event.is_directory:
                return
            self.worker.schedule(Path(event.src_path))

        def on_moved(self, event):
            if event.is_directory:
                return
            self.worker.schedule(Path(event.dest_path))


def start_watcher(
    db_path: Path,
    root: Path,
    extensions: Optional[set[str]] = None,
    idle_seconds: float = 3.0,
    on_import: Optional[Callable[[dict], None]] = None,
):
    """Start watching `root`. Returns a stop() callable.

    Raises ImportError if watchdog isn't installed.
    """
    if not WATCHDOG_AVAILABLE:
        raise ImportError("watchdog is required: pip install watchdog")
    extensions = extensions or DEFAULT_EXTENSIONS
    worker = _DebounceWorker(
        db_path=db_path,
        root=root,
        extensions=extensions,
        idle_seconds=idle_seconds,
        on_import=on_import,
    )
    observer = Observer()
    observer.schedule(_Handler(worker), str(root), recursive=True)
    observer.start()

    def stop():
        observer.stop()
        observer.join(timeout=2.0)
        worker.stop()

    return stop
