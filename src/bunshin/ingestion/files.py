"""Import local files (Markdown, text) into Bunshin storage."""
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from bunshin.storage import insert_record


DEFAULT_EXTENSIONS = {".md", ".markdown", ".txt"}

SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv", "env", "__pycache__",
    ".pytest_cache", ".ruff_cache", "dist", "build", ".next",
    "target", "Pods", ".cache", "site-packages",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 100


def find_files(
    root: Path,
    extensions: set[str] = DEFAULT_EXTENSIONS,
) -> Iterable[Path]:
    """Walk directory tree, yielding files with matching extensions."""
    if root.is_file():
        if root.suffix.lower() in extensions:
            yield root
        return
    if not root.is_dir():
        return
    try:
        for entry in root.iterdir():
            if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                continue
            if entry.is_dir():
                yield from find_files(entry, extensions)
            elif entry.is_file() and entry.suffix.lower() in extensions:
                try:
                    if entry.stat().st_size <= MAX_FILE_SIZE:
                        yield entry
                except OSError:
                    continue
    except (OSError, PermissionError):
        return


def read_text(path: Path) -> Optional[str]:
    """Read text file, trying UTF-8 then Shift-JIS."""
    for encoding in ("utf-8", "cp932"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError:
            return None
    return None


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into chunks, preferring paragraph boundaries."""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Try to break at paragraph (\n\n) within last ~200 chars
            window_start = max(end - 200, start + 100)
            paragraph = text.rfind("\n\n", window_start, end)
            if paragraph != -1:
                end = paragraph + 2
            else:
                # Fall back to single newline
                newline = text.rfind("\n", window_start, end)
                if newline != -1:
                    end = newline + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def delete_file_records(conn: sqlite3.Connection, source_id: str) -> None:
    cursor = conn.execute(
        "SELECT id FROM records WHERE source = 'file' AND source_id = ?",
        (source_id,),
    )
    ids = [row[0] for row in cursor.fetchall()]
    if not ids:
        return
    placeholders = ",".join(["?"] * len(ids))
    try:
        conn.execute(
            f"DELETE FROM records_vec WHERE record_id IN ({placeholders})",
            ids,
        )
    except sqlite3.OperationalError:
        pass
    conn.execute(
        f"DELETE FROM records WHERE id IN ({placeholders})",
        ids,
    )
    conn.commit()


def get_last_mtime(conn: sqlite3.Connection, path_str: str) -> Optional[int]:
    cursor = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (f"file_mtime:{path_str}",),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else None


def set_last_mtime(conn: sqlite3.Connection, path_str: str, mtime: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
        (f"file_mtime:{path_str}", str(mtime)),
    )


def import_files(
    conn: sqlite3.Connection,
    root: Path,
    extensions: Optional[set[str]] = None,
    force: bool = False,
    verbose: bool = False,
) -> dict:
    """Import all matching files under root. Skips files unchanged since last import."""
    try:
        from bunshin.storage import load_vec_extension
        load_vec_extension(conn)
    except Exception:
        pass

    extensions = extensions or DEFAULT_EXTENSIONS
    stats = {
        "files_scanned": 0,
        "files_unchanged": 0,
        "files_reimported": 0,
        "files_failed": 0,
        "chunks_inserted": 0,
    }

    for path in find_files(root, extensions):
        stats["files_scanned"] += 1
        path_str = str(path)
        try:
            current_mtime = int(path.stat().st_mtime)
        except OSError:
            stats["files_failed"] += 1
            continue

        last_mtime = get_last_mtime(conn, path_str)
        if not force and last_mtime is not None and last_mtime >= current_mtime:
            stats["files_unchanged"] += 1
            continue

        text = read_text(path)
        if not text:
            stats["files_failed"] += 1
            continue

        # Re-import: wipe old records for this file
        delete_file_records(conn, path_str)

        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            insert_record(
                conn,
                source="file",
                timestamp=current_mtime,
                content=chunk,
                source_id=path_str,
                metadata={
                    "path": path_str,
                    "name": path.name,
                    "ext": path.suffix.lower(),
                    "chunk_index": i,
                    "chunk_count": len(chunks),
                },
                file_path=path_str,
            )
            stats["chunks_inserted"] += 1

        set_last_mtime(conn, path_str, current_mtime)
        conn.commit()
        stats["files_reimported"] += 1
        if verbose:
            print(f"Imported: {path} ({len(chunks)} chunks)")

    return stats
