"""Cross-encoder reranker for the hybrid-search second pass.

Hybrid search (vector + FTS5) gives us a wide top-K list that includes
plausible noise. A cross-encoder reranker takes (query, candidate) pairs
and scores them with a model that has seen both texts together, which is
far more accurate than the bi-encoder embedding similarity used during
the candidate fetch.

We use `jinaai/jina-reranker-v2-base-multilingual` because Bunshin
records are predominantly Japanese + English and Jina v2 is one of the
few small (1.1 GB) cross-encoders that handles both well.
"""
from __future__ import annotations

import gc
import threading
import time
import warnings
from typing import Any, Optional

DEFAULT_MODEL = "jinaai/jina-reranker-v2-base-multilingual"

# Idle-unload: drop the rerank model from memory after this many seconds
# of no rerank calls. Reviewer 10 measured fastembed + reranker
# co-resident at 11.9 GB — on 8 GB Macs this swaps heavily. Keeping the
# reranker live only while actively in use brings idle RSS from ~12 GB
# back down to ~3 GB (fastembed-only) or ~200 MB (cold).
RERANK_IDLE_TTL_SEC = 600

_reranker: Optional[Any] = None
_reranker_last_used: float = 0.0
_reranker_lock = threading.Lock()


def _get_reranker():
    """Lazy-initialize the cross-encoder so module import stays cheap."""
    global _reranker, _reranker_last_used
    with _reranker_lock:
        _reranker_last_used = time.time()
        if _reranker is not None:
            return _reranker
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
        except ImportError:
            return None
        try:
            # Silence the "model card not found" notice fastembed emits.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                _reranker = TextCrossEncoder(model_name=DEFAULT_MODEL)
            return _reranker
        except Exception:
            return None


def maybe_unload_idle() -> bool:
    """If the reranker hasn't been used in RERANK_IDLE_TTL_SEC seconds,
    drop it. Called by the periodic idle-GC thread in server.py. Returns
    True if the model was unloaded."""
    global _reranker, _reranker_last_used
    with _reranker_lock:
        if _reranker is None:
            return False
        if time.time() - _reranker_last_used < RERANK_IDLE_TTL_SEC:
            return False
        _reranker = None
    gc.collect()
    return True


def rerank(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: Optional[int] = None,
    content_field: str = "content",
) -> list[dict[str, Any]]:
    """Re-score `candidates` by cross-encoding each (query, candidate.content)
    pair, then sort descending by score.

    Returns the input candidates with an added `rerank_score` key. If the
    model isn't available, candidates are returned unchanged.
    """
    if not candidates:
        return candidates
    model = _get_reranker()
    if model is None:
        # No reranker available — still honor the top_k trim so callers
        # don't accidentally surface our wider candidate pool.
        return candidates[:top_k] if top_k else candidates

    docs = [(c.get(content_field) or "")[:2048] for c in candidates]
    try:
        scores = list(model.rerank(query, docs))
    except Exception:
        return candidates[:top_k] if top_k else candidates
    if len(scores) != len(candidates):
        return candidates[:top_k] if top_k else candidates

    for c, s in zip(candidates, scores):
        # Keep prior score components if present.
        sc = c.setdefault("score_components", {})
        sc["rerank"] = float(s)
        c["rerank_score"] = float(s)

    candidates.sort(key=lambda c: -c.get("rerank_score", 0.0))
    if top_k is not None:
        candidates = candidates[:top_k]
    return candidates


def warmup() -> bool:
    """Load the model now (used by long-running services to avoid the
    first-request latency hit). Returns True if loaded, False otherwise."""
    return _get_reranker() is not None
