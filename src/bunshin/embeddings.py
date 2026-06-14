"""Local embedding generation using FastEmbed (ONNX-based, no torch required).

Uses sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
(118M params, 384 dimensions, multilingual incl. Japanese, ~220MB ONNX).
"""
from typing import Iterable, Iterator, Optional

import numpy as np
from fastembed import TextEmbedding


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSIONS = 384
MAX_CHARS = 2000  # truncate very long content to avoid wasted compute


_model: Optional[TextEmbedding] = None


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL_NAME)
    return _model


def _truncate(text: str) -> str:
    return text[:MAX_CHARS] if len(text) > MAX_CHARS else text


def embed_passages(texts: Iterable[str]) -> Iterator[np.ndarray]:
    """Embed documents for storage."""
    model = get_model()
    truncated = [_truncate(t) for t in texts]
    yield from model.embed(truncated)


def embed_query(text: str) -> np.ndarray:
    """Embed a query for search."""
    model = get_model()
    return next(iter(model.embed([_truncate(text)])))
