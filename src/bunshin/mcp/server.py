"""MCP server for Bunshin — exposes memory search to MCP-compatible AI clients.

Run via `bunshin mcp`. Communicates over stdio with the JSON-RPC MCP protocol.
Anything written to stdout that isn't valid MCP protocol breaks the client,
so logging goes to stderr only.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from bunshin.search import search as do_search
from bunshin.storage import (
    DEFAULT_DB_PATH,
    get_session_records,
    init_db,
)


logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("bunshin.mcp")


def _format_timestamp(ts: int | None) -> str | None:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return None


def create_mcp(db_path: Path = DEFAULT_DB_PATH) -> FastMCP:
    mcp = FastMCP("bunshin")

    @mcp.tool()
    def search_memory(
        query: str,
        limit: int = 10,
        sort: str = "relevance",
    ) -> str:
        """Search the user's past memory by semantic similarity.

        Use this whenever the user references something from the past — past
        conversations, projects, decisions, files, etc. The query can be in
        Japanese or English; matches are by meaning, not exact words.

        Examples of when to use:
        - User mentions a project / organization / person name: search for it
        - User asks "before"/"last week"/"何だっけ"/"do you remember": search and recall
        - User makes a decision that may have past context: search to verify

        Args:
            query: Natural language search query (Japanese OK).
            limit: Maximum number of results to return (default 10, max 50).
            sort: "relevance" (default), "newest", or "oldest".

        Returns:
            JSON list of relevant past records, each with timestamp, role,
            source, source_id (use with recall_session to expand), distance
            (lower = closer match), and content.
        """
        conn = init_db(db_path)
        try:
            results = do_search(
                conn,
                query,
                limit=min(max(limit, 1), 50),
                sort=sort if sort in ("relevance", "newest", "oldest") else "relevance",
            )
            formatted = [
                {
                    "timestamp": _format_timestamp(r["timestamp"]),
                    "role": (r["metadata"] or {}).get("role"),
                    "source": r["source"],
                    "source_id": r["source_id"],
                    "distance": round(r["distance"], 3),
                    "content": r["content"],
                }
                for r in results
            ]
            return json.dumps(
                {"query": query, "count": len(formatted), "results": formatted},
                ensure_ascii=False,
                indent=2,
            )
        finally:
            conn.close()

    @mcp.tool()
    def recall_session(source_id: str, max_messages: int = 100) -> str:
        """Get the full conversation/session that contains a specific record.

        Use this after `search_memory` returns a hit, when you need full
        context around the matched record (e.g. "what led up to that
        decision?", "what was the rest of that discussion?").

        Args:
            source_id: The source_id from a search_memory result.
            max_messages: Maximum messages to return (default 100).

        Returns:
            JSON list of all messages in that session, in chronological
            order, each with timestamp, role, and content.
        """
        conn = init_db(db_path)
        try:
            records = get_session_records(conn, source_id)[: max(1, max_messages)]
            formatted = [
                {
                    "timestamp": _format_timestamp(r["timestamp"]),
                    "role": (r["metadata"] or {}).get("role"),
                    "content": r["content"],
                }
                for r in records
            ]
            return json.dumps(
                {
                    "source_id": source_id,
                    "count": len(formatted),
                    "messages": formatted,
                },
                ensure_ascii=False,
                indent=2,
            )
        finally:
            conn.close()

    return mcp


def run(db_path: Path = DEFAULT_DB_PATH) -> None:
    log.info(f"Bunshin MCP server starting (db={db_path})")
    mcp = create_mcp(db_path)
    mcp.run()
