"""Semantic search over Bunshin records."""
import json
import sqlite3
from typing import Any, Optional

import numpy as np

from bunshin.embeddings import embed_query
from bunshin.storage import load_vec_extension


_ORDER_CLAUSES = {
    "relevance": "v.distance ASC",
    "newest": "r.timestamp DESC",
    "oldest": "r.timestamp ASC",
}


def search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 10,
    min_content_length: int = 20,
    sort: str = "relevance",
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
    max_per_source: int = 1,
) -> list[dict[str, Any]]:
    """Search records by semantic similarity to query.

    sort: "relevance" (default), "newest", or "oldest"
    from_ts / to_ts: optional Unix timestamps to bound the time range
    max_per_source: cap how many chunks come from the same source_id
                    (1 = strict dedup, 0 = no dedup). Each returned record
                    includes `total_in_source` so the UI can hint at more.

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
            }
        )
    return results
