"""Semantic search over Bunshin records.

Two modes:
  - 'vector' (default): pure semantic search via sqlite-vec
  - 'hybrid': combines vector similarity with FTS5 BM25 keyword score —
    much better for exact name/jargon queries while preserving semantic
    fallback. Uses reciprocal rank fusion (RRF) to merge the two lists.
"""
import json
import re
import sqlite3
from typing import Any, Optional

import numpy as np

from bunshin.embeddings import EmbedBusyError, embed_query
from bunshin.storage import init_fts, load_vec_extension


_ORDER_CLAUSES = {
    "relevance": "v.distance ASC",
    "newest": "r.timestamp DESC",
    "oldest": "r.timestamp ASC",
}


def _extract_query_tokens(q: str) -> list[str]:
    """Pull meaningful tokens (>=2 chars) out of a free-text query."""
    tokens = re.findall(r"[\w　-鿿々]+", q)
    return [t for t in tokens if len(t) >= 2]


def _normalize_query(q: str) -> str:
    """Normalize a search query to absorb common notation drift:

    - full-width ASCII → half-width (Ｓｋｙ → Sky)
    - full-width space → ASCII space (　 → space)
    - smart quotes → straight quotes

    Embedding similarity is mostly notation-invariant, but FTS5 BM25
    treats `Ｓｋｙ` and `Sky` as different tokens, so we normalize before
    handing the query to either pass.
    """
    if not q:
        return q
    out_chars = []
    for ch in q:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out_chars.append(chr(code - 0xFEE0))  # FW ASCII → HW
        elif code == 0x3000:
            out_chars.append(" ")               # FW space
        elif ch in '“”„‟':
            out_chars.append('"')
        elif ch in '‘’‚‛':
            out_chars.append("'")
        else:
            out_chars.append(ch)
    return "".join(out_chars).strip()


# Cache for LLM-based query expansions so a repeat query doesn't pay
# the inference cost twice. Keyed by lower-cased + normalized query.
_QUERY_EXPANSION_CACHE: dict[str, list[str]] = {}


def expand_query_with_llm(
    query: str,
    model: Optional[str] = None,
    host: str = "http://localhost:11434",
    timeout: float = 8.0,
    max_variants: int = 5,
) -> list[str]:
    """Ask Ollama for 2–3 reword variants of the query.

    The response is cached in-memory so the second hit on the same query
    is free. Returns an empty list on any failure — callers should fall
    back to the original query.
    """
    key = query.strip().lower()
    if not key:
        return []
    if key in _QUERY_EXPANSION_CACHE:
        return _QUERY_EXPANSION_CACHE[key]
    try:
        from bunshin.chat import check_ollama, pick_model
        import httpx
        ok, available = check_ollama(host)
        if not ok or not available:
            _QUERY_EXPANSION_CACHE[key] = []
            return []
        chosen = model or pick_model(available)
        if not chosen:
            _QUERY_EXPANSION_CACHE[key] = []
            return []
        # v0.10.45 (Honda 100-test G): cross-lingual retrieval was
        # weak because expansion focused on same-language variants
        # only. If the query is English but records are Japanese
        # (or vice versa), we need the LLM to produce translated
        # variants explicitly.
        prompt = (
            "次の検索クエリの言い換えバリエーションを 3-5 個生成してください。\n"
            "重要:\n"
            "- 同義語、関連語、漢字／ひらがな／カタカナの揺れ\n"
            "- **英語クエリの場合は必ず日本語訳を 1 つ以上含める** "
            "(例: 'Iki Gold potato' → '壱岐黄金 じゃがいも')\n"
            "- **日本語クエリの場合は英語訳や英名も 1 つ含める** "
            "(例: '壱岐黄金' → 'Iki Gold')\n"
            "余計な説明はせず、バリエーションだけを 1 行に 1 つ書いてください。\n\n"
            f"検索クエリ: {query}\n\nバリエーション:"
        )
        r = httpx.post(
            f"{host}/api/generate",
            json={
                "model": chosen,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 80},
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            _QUERY_EXPANSION_CACHE[key] = []
            return []
        text = r.json().get("response", "") or ""
        variants: list[str] = []
        for line in text.splitlines():
            v = line.strip().strip("-・*0123456789.) ")
            if not v or len(v) > 80:
                continue
            if v.lower() == key:
                continue
            variants.append(v)
            if len(variants) >= max_variants:
                break
        _QUERY_EXPANSION_CACHE[key] = variants
        return variants
    except Exception:
        _QUERY_EXPANSION_CACHE[key] = []
        return []


def _sanitize_fts_query(q: str) -> str:
    """Convert a free-text query into a safe FTS5 MATCH expression.

    FTS5 has its own syntax (NEAR/AND/OR, double-quoted phrases). To avoid
    syntax errors on user input we extract token-like substrings and join
    them with OR, quoting each. This loses some power but is robust.
    """
    tokens = _extract_query_tokens(q)
    if not tokens:
        return ""
    return " OR ".join(f'"{t.replace(chr(34), "")}"' for t in tokens)


def _fts_search(
    conn: sqlite3.Connection,
    query: str,
    candidate_limit: int,
    min_content_length: int,
    from_ts: Optional[int],
    to_ts: Optional[int],
    sources: Optional[list[str]] = None,
) -> dict[str, dict[str, Any]]:
    """Return {record_id: {bm25_rank, ...}} from FTS5 BM25 scoring.

    Returns an empty dict if FTS5 isn't available or the query degenerates.
    """
    fts_q = _sanitize_fts_query(query)
    if not fts_q:
        return {}
    try:
        init_fts(conn)
        where = ["records_fts MATCH ?", "length(r.content) >= ?"]
        params: list[Any] = [fts_q, min_content_length]
        if from_ts is not None:
            where.append("r.timestamp >= ?")
            params.append(from_ts)
        if to_ts is not None:
            where.append("r.timestamp <= ?")
            params.append(to_ts)
        if sources:
            placeholders = ",".join(["?"] * len(sources))
            where.append(f"r.source IN ({placeholders})")
            params.extend(sources)
        sql = f"""
            SELECT r.id AS record_id, bm25(records_fts) AS bm25_score
            FROM records_fts
            JOIN records r ON r.rowid = records_fts.rowid
            WHERE {' AND '.join(where)}
            ORDER BY bm25_score ASC
            LIMIT ?
        """
        params.append(candidate_limit)
        out = {}
        for rank, row in enumerate(conn.execute(sql, params)):
            rid = row[0]
            out[rid] = {"bm25_rank": rank + 1, "bm25_score": row[1]}
        return out
    except sqlite3.OperationalError:
        return {}


def search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
    min_content_length: int = 20,
    sort: str = "relevance",
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
    max_per_source: int = 1,
    mode: str = "hybrid",
    sources: Optional[list[str]] = None,
    rerank: bool = True,
    expand: bool = False,
) -> list[dict[str, Any]]:
    # Normalize notation (full-width → half-width, etc) so the same query
    # written different ways finds the same records.
    query = _normalize_query(query)
    """Search records by semantic similarity to query.

    sort: "relevance" (default), "newest", or "oldest"
    from_ts / to_ts: optional Unix timestamps to bound the time range
    max_per_source: cap how many chunks come from the same source_id
                    (1 = strict dedup, 0 = no dedup). Each returned record
                    includes `total_in_source` so the UI can hint at more.
    mode: "vector" (semantic only) or "hybrid" (vector + FTS5 BM25 fused
          via reciprocal rank fusion). Hybrid is the default and dominates
          on queries with proper nouns ("Globex Corp", "サンプル素材").

    min_content_length filters out very short messages (greetings, ack,
    "OK", "お願いします", etc.) which tend to be semantic noise.
    """
    load_vec_extension(conn)

    # Original query is kept separately because the cross-encoder rerank
    # at the end should score against the user's literal intent, not the
    # augmented form.
    original_query = query
    if expand:
        variants = expand_query_with_llm(query)
        if variants:
            # Concatenate so both the vector and FTS passes see the extra
            # terms. The embedding model averages contributions; FTS5
            # tokenizes and ORs them.
            query = query + " " + " ".join(variants)

    # Embedding can fail (e.g. fastembed cache corruption, missing model
    # download). When it does, we *must not* return zero results — that
    # silently breaks the entire app. Fall back to keyword-only search so
    # the user at least sees something + a clear error in the log.
    try:
        query_vec = embed_query(query)
        blob = np.asarray(query_vec, dtype=np.float32).tobytes()
        embedding_ok = True
        fallback_reason = None
    except EmbedBusyError as _busy:
        # The embedding model is being held by a long-running backfill
        # batch. Don't make the user wait 15 s for a single query —
        # serve a keyword-only result immediately and let the next
        # search (after backfill finishes) get the full vector pass.
        print(f"[search] {_busy} — keyword fallback for {query!r}", flush=True)
        embedding_ok = False
        fallback_reason = "backfill"
        blob = b""
    except Exception as _emb_exc:
        import traceback
        traceback.print_exc()
        print(
            f"[search] embedding failed ({_emb_exc!r}); falling back to "
            f"keyword-only search for query: {query!r}",
            flush=True,
        )
        embedding_ok = False
        fallback_reason = "error"
        blob = b""

    if not embedding_ok:
        # Pure keyword fallback — LIKE-based, no vec, no rerank. Slower on
        # big DBs but always returns *something* relevant. Apply the
        # same signal_score floor the UI uses so newsletter-noise
        # records ("カレー好きな自由人さんにスキされました！") don't
        # surface in keyword-only mode either.
        from bunshin.settings import get as _get_setting
        _min_signal = int(_get_setting(conn, "min_signal_score") or 0)
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT id, source, content, metadata, timestamp, source_id, "
            "signal_score FROM records "
            "WHERE content LIKE ? AND length(content) >= ? "
            "AND COALESCE(signal_score, 50.0) >= ? "
            "AND COALESCE(user_signal, 0) != -1 "
            + (f"AND source IN ({','.join('?' * len(sources))}) " if sources else "")
            + "ORDER BY signal_score DESC, timestamp DESC LIMIT ?",
            [like, min_content_length, _min_signal]
            + (list(sources) if sources else []) + [limit],
        ).fetchall()
        import json as _json
        results = []
        for row in rows:
            try:
                meta = _json.loads(row[3]) if row[3] else {}
            except Exception:
                meta = {}
            results.append({
                "id": row[0], "source": row[1], "content": row[2],
                "metadata": meta, "timestamp": row[4], "source_id": row[5],
                "signal_score": row[6] or 50.0,
                "distance": 1.0,
                "score_components": {
                    "keyword_fallback": 1.0,
                    "fallback_reason": fallback_reason or "unknown",
                },
            })
        return results

    # Over-fetch from vec so we can post-filter and still hit `limit`
    # even after deduplication collapses chunks.
    fetch_k = max(limit * 8, 200) if max_per_source >= 1 else max(limit * 4, 100)

    where = ["v.embedding MATCH ?", "v.k = ?", "length(r.content) >= ?"]
    params: list[Any] = [blob, fetch_k, min_content_length]

    if from_ts is not None:
        where.append("r.timestamp >= ?")
        params.append(from_ts)
    if to_ts is not None:
        where.append("r.timestamp <= ?")
        params.append(to_ts)
    if sources:
        placeholders = ",".join(["?"] * len(sources))
        where.append(f"r.source IN ({placeholders})")
        params.extend(sources)

    order_clause = _ORDER_CLAUSES.get(sort, _ORDER_CLAUSES["relevance"])

    if max_per_source >= 1:
        # CTE-internal sort: columns are unprefixed once we're past the JOIN
        cte_order = {
            "relevance": "distance ASC",
            "newest": "timestamp DESC",
            "oldest": "timestamp ASC",
        }.get(sort, "distance ASC")

        # Window-functions give us PER-SOURCE rank + per-source count
        # in one round-trip, so we can dedup precisely.
        sql = f"""
            WITH hits AS (
                SELECT v.record_id, v.distance, r.source, r.source_id,
                       r.content, r.timestamp, r.metadata
                FROM records_vec v
                JOIN records r ON r.id = v.record_id
                WHERE {' AND '.join(where)}
            ),
            ranked AS (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY source_id ORDER BY distance ASC) AS rank_in_source,
                       COUNT(*) OVER (PARTITION BY source_id) AS total_in_source
                FROM hits
            )
            SELECT record_id, distance, source, source_id, content, timestamp, metadata,
                   total_in_source
            FROM ranked
            WHERE rank_in_source <= ?
            ORDER BY {cte_order}
            LIMIT ?
        """
        params.extend([max_per_source, limit])
    else:
        sql = f"""
            SELECT v.record_id, v.distance, r.source, r.source_id,
                   r.content, r.timestamp, r.metadata,
                   1 AS total_in_source
            FROM records_vec v
            JOIN records r ON r.id = v.record_id
            WHERE {' AND '.join(where)}
            ORDER BY {order_clause}
            LIMIT ?
        """
        params.append(limit)

    cursor = conn.execute(sql, params)

    results = []
    for row in cursor:
        metadata = json.loads(row[6]) if row[6] else None
        results.append(
            {
                "id": row[0],
                "distance": row[1],
                "source": row[2],
                "source_id": row[3],
                "content": row[4],
                "timestamp": row[5],
                "metadata": metadata,
                "total_in_source": row[7],
                "score_components": {"vector": row[1]},
            }
        )

    # Hybrid: fuse BM25 with vector via reciprocal rank fusion.
    if mode == "hybrid":
        fts_hits = _fts_search(
            conn, query,
            candidate_limit=max(limit * 8, 100),
            min_content_length=min_content_length,
            from_ts=from_ts, to_ts=to_ts,
            sources=sources,
        )
        if fts_hits:
            # Build vector_rank map for RRF.
            sorted_vec = sorted(results, key=lambda r: r["distance"])
            vec_rank = {r["id"]: i + 1 for i, r in enumerate(sorted_vec)}

            # Collect FTS-only records not yet present in vector results.
            existing_ids = {r["id"] for r in results}
            missing_ids = [rid for rid in fts_hits if rid not in existing_ids]
            if missing_ids:
                placeholders = ",".join(["?"] * len(missing_ids))
                cur = conn.execute(
                    f"""SELECT id, source, source_id, content, timestamp, metadata
                        FROM records WHERE id IN ({placeholders})""",
                    missing_ids,
                )
                for row in cur:
                    metadata = json.loads(row[5]) if row[5] else None
                    results.append(
                        {
                            "id": row[0],
                            "distance": 999.0,  # missing — penalized in scoring
                            "source": row[1],
                            "source_id": row[2],
                            "content": row[3],
                            "timestamp": row[4],
                            "metadata": metadata,
                            "total_in_source": 1,
                            "score_components": {"vector_missing": True},
                        }
                    )

            # RRF: combined = sum(1/(k + rank)) over each ranker. k=60 standard.
            K = 60
            scored = []
            for r in results:
                vr = vec_rank.get(r["id"], len(results) + 1)
                fr = fts_hits.get(r["id"], {}).get("bm25_rank")
                rrf = 1.0 / (K + vr) + (1.0 / (K + fr) if fr else 0.0)
                r["score_components"]["vector_rank"] = vr
                r["score_components"]["bm25_rank"] = fr
                r["score_components"]["rrf"] = rrf
                scored.append(r)

            # All-tokens-match boost: when the user types multiple terms
            # (e.g. "Sky MISSION 相見積もり"), records that contain ALL of
            # them should jump above records that only match one. We bump
            # those records' RRF score by a generous constant.
            tokens = _extract_query_tokens(query)
            if len(tokens) >= 2:
                lower_tokens = [t.lower() for t in tokens]
                for r in scored:
                    content_lower = (r.get("content") or "").lower()
                    matches = sum(1 for t in lower_tokens if t in content_lower)
                    r["score_components"]["matched_tokens"] = matches
                    r["score_components"]["total_tokens"] = len(lower_tokens)
                    if matches == len(lower_tokens):
                        r["score_components"]["all_terms_match"] = True
                        # Lift this record above all single-match records.
                        r["score_components"]["rrf"] += 0.5
                    elif matches >= 2 and matches < len(lower_tokens):
                        # Partial multi-match — small bump.
                        r["score_components"]["rrf"] += 0.1 * matches

            # Re-sort by RRF descending and trim.
            if sort == "relevance":
                scored.sort(key=lambda r: -r["score_components"]["rrf"])
            elif sort == "newest":
                scored.sort(key=lambda r: -(r["timestamp"] or 0))
            elif sort == "oldest":
                scored.sort(key=lambda r: (r["timestamp"] or 0))
            # Hold onto a wider candidate pool so the cross-encoder has
            # room to reshuffle. 2× the user-requested limit keeps rerank
            # latency under ~3 s on Apple Silicon for limit=20 while still
            # giving the model enough headroom to reorder meaningfully.
            results = scored[: max(limit * 2, 20)]

    # Cross-encoder rerank (only meaningful for the relevance sort —
    # newest/oldest already have a deterministic ordering).
    if rerank and sort == "relevance" and len(results) > 1:
        from bunshin.rerank import rerank as cross_encode_rerank
        # Rerank against the original (un-expanded) query so the
        # scorer judges relevance to the user's actual intent.
        # Cap the *input* to rerank — cross-encoding on CPU is ~0.5s
        # per pair, so 8 candidates ≈ 4s, 15 ≈ 7.5s. Reviewer 10 measured
        # 15 still yielding 7.5s wall time for limit=3 queries, so we
        # tighten the cap to 8 — the top-3 results almost never escape
        # the top-8-by-vector+BM25 pool, and search now returns in <2s
        # in the steady state.
        RERANK_INPUT_CAP = 8
        # min() not max() — the whole point of the cap is to LIMIT how
        # many candidates get cross-encoded. With max() the cap was a
        # no-op for any limit ≥ 8, so limit=20 still cross-encoded 20
        # records (~10 s). Reviewer 11 caught the typo.
        rerank_input = results[: min(limit if limit > 0 else RERANK_INPUT_CAP, RERANK_INPUT_CAP)]
        # Surface the rest unranked at the bottom so we don't quietly
        # drop them when the caller asks for more than the cap.
        tail = results[len(rerank_input):]
        results = cross_encode_rerank(original_query, rerank_input, top_k=limit)
        if tail and len(results) < limit:
            results.extend(tail[: limit - len(results)])

        # v0.10.9 (Honda Patch B): jina-reranker-v2 returns negative
        # logits for some multi-word proper-noun queries ("SKYPIX 対馬",
        # "投資 NISA") even when the doc clearly contains both terms.
        # That makes every relevance_percent clamp to 0 — the user sees
        # "hits but no ranking". Boost docs that contain *all* query
        # tokens by +0.5 so they win regardless of rerank's mood. Stops
        # ranking from breaking on proper-noun + descriptor pairs.
        _q_tokens = [
            t for t in re.findall(r"\w+", original_query, re.UNICODE)
            if len(t) >= 2
        ]
        if len(_q_tokens) >= 2:
            for r in results:
                content = (r.get("content") or "").lower()
                hits = sum(1 for t in _q_tokens if t.lower() in content)
                if hits == len(_q_tokens):
                    r["rerank_score"] = r.get("rerank_score", 0.0) + 0.5
                    sc = r.setdefault("score_components", {})
                    sc["rerank"] = r["rerank_score"]
                    sc["all_terms_match"] = True
            results.sort(key=lambda r: -r.get("rerank_score", 0.0))
    else:
        results = results[:limit]

    # For non-relevance sorts, force the final order to honor the
    # caller's wish. Reviewer 12 found limit≥5 in sort=newest mixing
    # dates because the hybrid retrieval's "wider candidate pool"
    # (limit*2 or 20) was preserved instead of getting one final sort
    # pass over the trimmed-to-`limit` results.
    if sort == "newest":
        results.sort(key=lambda r: -(r.get("timestamp") or 0))
    elif sort == "oldest":
        results.sort(key=lambda r: (r.get("timestamp") or 0))

    return results
