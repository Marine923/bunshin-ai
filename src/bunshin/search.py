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

from bunshin.embeddings import embed_query
from bunshin.storage import init_fts, load_vec_extension


_ORDER_CLAUSES = {
    "relevance": "v.distance ASC",
    "newest": "r.timestamp DESC",
    "oldest": "r.timestamp ASC",
}


def _sanitize_fts_query(q: str) -> str:
    """Convert a free-text query into a safe FTS5 MATCH expression.

    FTS5 has its own syntax (NEAR/AND/OR, double-quoted phrases). To avoid
    syntax errors on user input we extract token-like substrings and join
    them with OR, quoting each. This loses some power but is robust.
    """
    tokens = re.findall(r"[\w　-鿿々]+", q)
    tokens = [t for t in tokens if len(t) >= 2]
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
) -> list[dict[str, Any]]:
    """Search records by semantic similarity to query.

    sort: "relevance" (default), "newest", or "oldest"
    from_ts / to_ts: optional Unix timestamps to bound the time range
    max_per_source: cap how many chunks come from the same source_id
                    (1 = strict dedup, 0 = no dedup). Each returned record
                    includes `total_in_source` so the UI can hint at more.
    mode: "vector" (semantic only) or "hybrid" (vector + FTS5 BM25 fused
          via reciprocal rank fusion). Hybrid is the default and dominates
          on queries with proper nouns ("Sky MISSION", "ウニ殻").

    min_content_length filters out very short messages (greetings, ack,
    "OK", "お願いします", etc.) which tend to be semantic noise.
    """
    load_vec_extension(conn)

    query_vec = embed_query(query)
    blob = np.asarray(query_vec, dtype=np.float32).tobytes()

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

            # Re-sort by RRF descending and trim.
            if sort == "relevance":
                scored.sort(key=lambda r: -r["score_components"]["rrf"])
            elif sort == "newest":
                scored.sort(key=lambda r: -(r["timestamp"] or 0))
            elif sort == "oldest":
                scored.sort(key=lambda r: (r["timestamp"] or 0))
            results = scored[:limit]

    return results
