"""Local embedding generation using FastEmbed (ONNX-based, no torch required).

Uses intfloat/multilingual-e5-large (560M params, 1024 dimensions,
strong multilingual incl. Japanese, ~2.2 GB ONNX). E5 models need
'passage: ' / 'query: ' prefixes — handled automatically below.

Override via environment variable: BUNSHIN_EMBEDDING_MODEL
"""
import os
from typing import Iterable, Iterator, Optional

import numpy as np
from fastembed import TextEmbedding


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


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL_NAME)
    return _model


def _truncate(text: str) -> str:
    return text[:MAX_CHARS] if len(text) > MAX_CHARS else text


def embed_passages(texts: Iterable[str]) -> Iterator[np.ndarray]:
    """Embed documents for storage. E5 family needs 'passage:' prefix."""
    model = get_model()
    if _USES_E5_PREFIX:
        prepared = [f"passage: {_truncate(t)}" for t in texts]
    else:
        prepared = [_truncate(t) for t in texts]
    yield from model.embed(prepared)


def embed_query(text: str) -> np.ndarray:
    """Embed a query for search. E5 family needs 'query:' prefix."""
    model = get_model()
    if _USES_E5_PREFIX:
        prepared = f"query: {_truncate(text)}"
    else:
        prepared = _truncate(text)
    return next(iter(model.embed([prepared])))
