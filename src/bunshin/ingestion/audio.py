"""Transcribe audio files (voice memos, calls, meetings) into bunshin memory.

Tries multiple backends so the user can pick what fits their setup:

  1. faster-whisper (PyPI)        — pure Python, no extra system deps,
                                    accurate, ~200 MB + model
  2. openai-whisper (PyPI)        — reference impl, needs torch (~1 GB)
  3. whisper-cpp / whisper binary — `brew install whisper-cpp`, tiny

Each backend transcribes to plain text and gets stored as a `manual` note
with the audio path in metadata.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional


SUPPORTED_EXTS = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".webm", ".mp4", ".mov"}


def detect_backend() -> Optional[str]:
    """Return the first available backend or None."""
    try:
        import faster_whisper  # noqa: F401
        return "faster-whisper"
    except ImportError:
        pass
    try:
        import whisper  # type: ignore  # noqa: F401
        return "openai-whisper"
    except ImportError:
        pass
    for binary in ("whisper-cpp", "whisper-cli", "whisper.cpp", "whisper"):
        if shutil.which(binary):
            return f"binary:{binary}"
    return None


def _transcribe_faster_whisper(path: Path, model_name: str, language: Optional[str]) -> str:
    from faster_whisper import WhisperModel
    # 'auto' detects compute device. CPU works everywhere; CoreML/CUDA opt-in.
    model = WhisperModel(model_name, device="auto", compute_type="auto")
    segments, _info = model.transcribe(
        str(path),
        language=language,
        vad_filter=True,
    )
    return "\n".join(seg.text.strip() for seg in segments if seg.text and seg.text.strip())


def _transcribe_openai_whisper(path: Path, model_name: str, language: Optional[str]) -> str:
    import whisper  # type: ignore
    model = whisper.load_model(model_name)
    result = model.transcribe(str(path), language=language)
    return (result.get("text") or "").strip()


def _transcribe_binary(binary: str, path: Path, model_name: str, language: Optional[str]) -> str:
    """Generic shell-out for whisper.cpp-family binaries.

    Different distributions of whisper-cpp expose slightly different flags;
    this tries a couple of common shapes.
    """
    candidates: list[list[str]] = [
        [binary, "-l", language or "auto", "-m", f"models/ggml-{model_name}.bin", "-otxt", str(path)],
        [binary, "--language", language or "auto", "--model", model_name, str(path)],
        [binary, str(path)],
    ]
    last_err = ""
    for cmd in candidates:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if r.returncode == 0:
                return (r.stdout or "").strip()
            last_err = r.stderr.strip()[:300]
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            last_err = str(e)
    raise RuntimeError(f"All whisper-cpp invocations failed; last error: {last_err}")


def transcribe(
    path: Path,
    model_name: str = "small",
    language: Optional[str] = None,
) -> dict:
    """Transcribe `path` to text using whichever backend is available.

    Returns: {"text": str, "backend": str, "model": str, "error": Optional[str]}
    """
    out: dict = {"text": "", "backend": None, "model": model_name, "error": None}
    if not path.exists():
        out["error"] = f"file not found: {path}"
        return out
    if path.suffix.lower() not in SUPPORTED_EXTS:
        out["error"] = f"unsupported extension: {path.suffix}"
        return out

    backend = detect_backend()
    if not backend:
        out["error"] = (
            "No transcription backend installed.\n"
            "Install one of:\n"
            "  pip install faster-whisper   # recommended (small, accurate)\n"
            "  pip install openai-whisper   # reference (needs torch)\n"
            "  brew install whisper-cpp     # Apple-Silicon native, tiny\n"
        )
        return out

    out["backend"] = backend
    try:
        if backend == "faster-whisper":
            out["text"] = _transcribe_faster_whisper(path, model_name, language)
        elif backend == "openai-whisper":
            out["text"] = _transcribe_openai_whisper(path, model_name, language)
        elif backend.startswith("binary:"):
            out["text"] = _transcribe_binary(backend.split(":", 1)[1], path, model_name, language)
    except Exception as e:
        out["error"] = str(e)
    return out
