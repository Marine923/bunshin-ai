"""Import image files: EXIF metadata + (optional) macOS Vision OCR.

Walks a directory tree for JPEG/PNG/HEIC/TIFF files, extracts EXIF
(date taken, GPS, camera), runs macOS Vision OCR (Japanese + English)
when the swift toolchain is available, and stores each photo as a
bunshin record with source='photo'.

The OCR helper is a tiny swift program we compile once and cache at
~/.bunshin/bin/bunshin-ocr. Falls back to EXIF-only on Linux or when
swift is missing.
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from bunshin.storage import insert_record


SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff"}

SKIP_DIRS = {
    "node_modules", ".git", ".venv", "__pycache__",
    ".cache", ".Trash", ".bunshin",
    # Photos.app library — needs Full Disk Access and is a separate ingest
    "Photos Library.photoslibrary",
}

MAX_IMAGE_SIZE = 30 * 1024 * 1024  # 30 MB


def find_images(root: Path) -> Iterable[Path]:
    """Walk a directory tree, yielding image files."""
    if root.is_file():
        if root.suffix.lower() in SUPPORTED_EXTS:
            yield root
        return
    if not root.is_dir():
        return
    try:
        for entry in root.iterdir():
            if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                continue
            if entry.is_dir():
                yield from find_images(entry)
            elif entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTS:
                try:
                    if entry.stat().st_size <= MAX_IMAGE_SIZE:
                        yield entry
                except OSError:
                    continue
    except (OSError, PermissionError):
        return


def _gps_to_decimal(coord, ref) -> Optional[float]:
    """Convert EXIF GPS (degrees, minutes, seconds) to decimal."""
    if not coord:
        return None
    try:
        d, m, s = float(coord[0]), float(coord[1]), float(coord[2])
        val = d + m / 60 + s / 3600
        if ref in ("S", "W"):
            val = -val
        return round(val, 6)
    except Exception:
        return None


def extract_exif(path: Path) -> dict:
    """Read EXIF tags from an image. Returns {date, gps, camera}."""
    try:
        from PIL import Image, ExifTags
    except ImportError:
        return {}
    try:
        img = Image.open(path)
    except Exception:
        return {}
    out: dict = {}
    try:
        exif_raw = img.getexif()
        if not exif_raw:
            return out
        tags = {ExifTags.TAGS.get(k, k): v for k, v in exif_raw.items()}

        date_str = tags.get("DateTimeOriginal") or tags.get("DateTime")
        if isinstance(date_str, str):
            try:
                dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                out["date"] = int(dt.timestamp())
            except ValueError:
                pass

        make = (tags.get("Make") or "").strip()
        model = (tags.get("Model") or "").strip()
        if make or model:
            out["camera"] = f"{make} {model}".strip()

        try:
            gps_ifd = exif_raw.get_ifd(ExifTags.IFD.GPSInfo)
        except (AttributeError, KeyError):
            gps_ifd = {}
        if gps_ifd:
            lat = _gps_to_decimal(gps_ifd.get(2), gps_ifd.get(1))
            lon = _gps_to_decimal(gps_ifd.get(4), gps_ifd.get(3))
            if lat is not None and lon is not None:
                out["gps"] = {"lat": lat, "lon": lon}
    except Exception:
        pass
    return out


# Swift program that takes image paths and prints `path\tOCR_text\n` per
# image, with newlines/tabs in the OCR text escaped. Compiled once to
# ~/.bunshin/bin/bunshin-ocr so the per-image cost is just process spawn.
_OCR_SWIFT_SOURCE = r'''
import Vision
import Cocoa
import Foundation

func ocrFile(_ path: String) -> String {
    let url = URL(fileURLWithPath: path)
    guard let image = NSImage(contentsOf: url),
          let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return ""
    }
    var output: [String] = []
    let request = VNRecognizeTextRequest { request, error in
        guard let obs = request.results as? [VNRecognizedTextObservation] else { return }
        for o in obs {
            if let candidate = o.topCandidates(1).first {
                output.append(candidate.string)
            }
        }
    }
    request.recognitionLanguages = ["ja-JP", "en-US"]
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    do {
        try handler.perform([request])
    } catch {
        return ""
    }
    return output.joined(separator: "\n")
}

for arg in CommandLine.arguments.dropFirst() {
    let text = ocrFile(arg)
    let escaped = text
        .replacingOccurrences(of: "\\", with: "\\\\")
        .replacingOccurrences(of: "\n", with: "\\n")
        .replacingOccurrences(of: "\t", with: "\\t")
    print("\(arg)\t\(escaped)")
}
'''


def ensure_ocr_binary() -> Optional[Path]:
    """Compile the swift OCR helper once. Cached at ~/.bunshin/bin/bunshin-ocr."""
    binary = Path.home() / ".bunshin" / "bin" / "bunshin-ocr"
    if binary.exists() and binary.stat().st_size > 0:
        return binary
    swiftc = shutil.which("swiftc") or shutil.which("xcrun")
    if not swiftc:
        return None
    binary.parent.mkdir(parents=True, exist_ok=True)
    source = binary.parent / "ocr_source.swift"
    source.write_text(_OCR_SWIFT_SOURCE)
    try:
        if "xcrun" in swiftc:
            cmd = [swiftc, "swiftc", str(source), "-o", str(binary)]
        else:
            cmd = [swiftc, str(source), "-o", str(binary)]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode == 0 and binary.exists():
            return binary
        return None
    except Exception:
        return None


def ocr_batch(paths: list[Path]) -> dict[str, str]:
    """OCR several images at once via the cached swift binary."""
    binary = ensure_ocr_binary()
    if not binary or not paths:
        return {}
    try:
        # Process up to N images per spawn to keep memory bounded.
        BATCH_SIZE = 8
        results: dict[str, str] = {}
        for i in range(0, len(paths), BATCH_SIZE):
            batch = paths[i:i + BATCH_SIZE]
            result = subprocess.run(
                [str(binary)] + [str(p) for p in batch],
                capture_output=True,
                text=True,
                timeout=max(60, len(batch) * 30),
            )
            for line in result.stdout.splitlines():
                if "\t" not in line:
                    continue
                p, escaped = line.split("\t", 1)
                # Reverse the swift-side escaping.
                text = (
                    escaped
                    .replace("\\n", "\n")
                    .replace("\\t", "\t")
                    .replace("\\\\", "\\")
                ).strip()
                results[p] = text
        return results
    except Exception:
        return {}


def _get_last_mtime(conn: sqlite3.Connection, path_str: str) -> Optional[int]:
    cur = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (f"photo_mtime:{path_str}",),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _set_last_mtime(conn: sqlite3.Connection, path_str: str, mtime: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
        (f"photo_mtime:{path_str}", str(mtime)),
    )


def import_photos(
    conn: sqlite3.Connection,
    root: Path,
    skip_ocr: bool = False,
    verbose: bool = False,
) -> dict:
    """Import images under root with EXIF + optional Vision OCR.

    Returns: scanned, imported, unchanged, with_gps, with_ocr, failed.
    """
    try:
        from bunshin.storage import load_vec_extension
        load_vec_extension(conn)
    except Exception:
        pass

    stats = {
        "scanned": 0,
        "imported": 0,
        "unchanged": 0,
        "with_gps": 0,
        "with_ocr": 0,
        "failed": 0,
    }

    # First pass: collect images that actually need processing.
    fresh: list[tuple[Path, int, dict]] = []
    for path in find_images(root):
        stats["scanned"] += 1
        try:
            mtime = int(path.stat().st_mtime)
        except OSError:
            stats["failed"] += 1
            continue
        last = _get_last_mtime(conn, str(path))
        if last is not None and last >= mtime:
            stats["unchanged"] += 1
            continue
        exif = extract_exif(path)
        fresh.append((path, mtime, exif))

    # OCR pass: only on images we'll actually persist.
    ocr_results: dict[str, str] = {}
    if not skip_ocr and fresh:
        ocr_results = ocr_batch([p for p, _, _ in fresh])

    for path, mtime, exif in fresh:
        path_str = str(path)
        ocr_text = ocr_results.get(path_str, "")
        if ocr_text:
            stats["with_ocr"] += 1

        if exif.get("gps"):
            stats["with_gps"] += 1

        ts = exif.get("date") or mtime
        date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        header_parts = ["[photo]", date_str]
        if exif.get("gps"):
            g = exif["gps"]
            header_parts.append(f"({g['lat']:.4f},{g['lon']:.4f})")
        if exif.get("camera"):
            header_parts.append(exif["camera"])
        header_parts.append(path.name)
        header = " ".join(header_parts)

        body = ocr_text or "(no text recognized)"
        content = f"{header}\n{body}".strip()

        rid = insert_record(
            conn,
            source="photo",
            timestamp=ts,
            content=content,
            source_id=path_str,
            metadata={
                "path": path_str,
                "name": path.name,
                "date": exif.get("date"),
                "gps": exif.get("gps"),
                "camera": exif.get("camera"),
                "ocr_chars": len(ocr_text),
            },
            file_path=path_str,
        )
        if rid:
            stats["imported"] += 1
            _set_last_mtime(conn, path_str, mtime)
            conn.commit()
            if verbose:
                print(f"Imported: {path.name} (OCR {len(ocr_text)} chars)")

    return stats
