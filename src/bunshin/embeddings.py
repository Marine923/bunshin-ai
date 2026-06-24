"""Local embedding generation using FastEmbed (ONNX-based, no torch required).

Uses intfloat/multilingual-e5-large (560M params, 1024 dimensions,
strong multilingual incl. Japanese, ~2.2 GB ONNX). E5 models need
'passage: ' / 'query: ' prefixes — handled automatically below.

Override via environment variable: BUNSHIN_EMBEDDING_MODEL
"""
import os
import threading
from typing import Iterable, Iterator, Optional

import numpy as np
from fastembed import TextEmbedding


class EmbedBusyError(RuntimeError):
    """Raised when embed_query times out waiting for the FastEmbed model
    because a long-running backfill is currently using it. Callers
    (notably search.py) should catch this and fall back to BM25 /
    keyword search instead of hanging the user's request for 15+ s."""


# Model registry: name → dimensions. Used by migrations to know
# whether the on-disk vec table matches the configured model.
MODEL_DIMENSIONS = {
    "intfloat/multilingual-e5-large": 1024,
    "intfloat/multilingual-e5-small": 384,
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": 384,
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2": 768,
}

DEFAULT_MODEL = "intfloat/multilingual-e5-large"
MODEL_NAME = os.environ.get("BUNSHIN_EMBEDDING_MODEL", DEFAULT_MODEL)
DIMENSIONS = MODEL_DIMENSIONS.get(MODEL_NAME, 384)

# E5 family needs special instruction prefixes
_USES_E5_PREFIX = "e5" in MODEL_NAME.lower()

MAX_CHARS = 2000  # truncate very long content to avoid wasted compute


_model: Optional[TextEmbedding] = None

# Serialize access to FastEmbed's in-process model. The previous version
# had no lock at all, so a backfill batch in progress would block every
# search/chat embed_query() call until it finished — reviewers measured
# 14.6 s per query (~1400× normal) while 1,500 records were being
# backfilled. The query path now takes the lock with a short timeout
# and raises EmbedBusyError on contention so callers can fall back to
# BM25 instead of hanging the user's request.
_model_lock = threading.Lock()
QUERY_LOCK_TIMEOUT_SEC = 0.8


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL_NAME)
    return _model


def _truncate(text: str) -> str:
    return text[:MAX_CHARS] if len(text) > MAX_CHARS else text


def embed_passages(texts: Iterable[str]) -> Iterator[np.ndarray]:
    """Embed documents for storage. E5 family needs 'passage:' prefix.

    Acquires the model lock for the full batch — this is the
    long-running caller (backfill, ingestion) that the query-side
    timeout was designed to detect.
    """
    model = get_model()
    if _USES_E5_PREFIX:
        prepared = [f"passage: {_truncate(t)}" for t in texts]
    else:
        prepared = [_truncate(t) for t in texts]
    with _model_lock:
        yield from model.embed(prepared)


def embed_query(text: str, *, timeout: float | None = None) -> np.ndarray:
    """Embed a query for search. E5 family needs 'query:' prefix.

    If `timeout` (defaults to QUERY_LOCK_TIMEOUT_SEC) seconds pass
    without acquiring the FastEmbed lock — i.e. a backfill is hogging
    the model — raises EmbedBusyError instead of blocking forever.
    search.py catches this and falls back to keyword (BM25) results
    so the user gets a response in <1 s rather than a 15-second hang.
    """
    model = get_model()
    if _USES_E5_PREFIX:
        prepared = f"query: {_truncate(text)}"
    else:
        prepared = _truncate(text)
    wait = QUERY_LOCK_TIMEOUT_SEC if timeout is None else timeout
    if not _model_lock.acquire(timeout=wait):
        raise EmbedBusyError(
            f"FastEmbed model busy (backfill in progress); "
            f"gave up after {wait:.1f}s"
        )
    try:
        return next(iter(model.embed([prepared])))
    finally:
        _model_lock.release()
