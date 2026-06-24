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

    @mcp.tool()
    def get_flashback(date: str | None = None) -> str:
        """Get "this date in the past" recall windows for a given date.

        Returns up to 5 records each from last week, 3 months ago, 1 year ago,
        and 5 years ago. Use this when the user asks "what was I doing last
        year on this day?" or for daily morning reflection prompts.

        Args:
            date: ISO date string (YYYY-MM-DD). Defaults to today.
        """
        from datetime import date as _date, datetime as _dt, timedelta
        conn = init_db(db_path)
        try:
            target = _date.fromisoformat(date) if date else _date.today()
            # Honest about the corpus's left edge — anything older than
            # the earliest record we have should say so, not show empty.
            oldest_row = conn.execute(
                "SELECT MIN(timestamp) FROM records WHERE timestamp > 0"
            ).fetchone()
            oldest_ts = (oldest_row[0] if oldest_row else None) or 0
            windows = []
            for label, days_back in [
                ("先週の同じ日", 7),
                ("3 ヶ月前の今日", 90),
                ("1 年前の今日", 365),
                ("5 年前の今日", 365 * 5),
            ]:
                anchor = target - timedelta(days=days_back)
                day_start = int(_dt.combine(anchor, _dt.min.time()).timestamp())
                day_end = day_start + 86400
                rows = conn.execute(
                    "SELECT id, source, content, timestamp FROM records "
                    "WHERE timestamp BETWEEN ? AND ? AND length(content) >= 50 "
                    "ORDER BY COALESCE(signal_score, 50) DESC LIMIT 5",
                    (day_start, day_end),
                ).fetchall()
                items = [
                    {"id": r[0], "source": r[1],
                     "content": r[2][:300], "timestamp": r[3]}
                    for r in rows
                ]
                window = {
                    "label_ja": label,
                    "date": anchor.isoformat(),
                    "items": items,
                }
                if not items:
                    if day_end < oldest_ts:
                        window["empty_message"] = (
                            f"{label}。Bunshin はまだあなたを知りませんでした。"
                        )
                    else:
                        window["empty_message"] = (
                            f"{label}は静かな日でした（記録なし）。"
                        )
                windows.append(window)
            return json.dumps(
                {"target_date": target.isoformat(), "windows": windows},
                ensure_ascii=False, indent=2,
            )
        finally:
            conn.close()

    @mcp.tool()
    def list_top_entities(
        type_: str | None = None,
        limit: int = 20,
    ) -> str:
        """List the most-mentioned entities in the user's memory.

        Use this to surface what's currently active in the user's life:
        the people, projects, and places that come up most often across
        all sources. Filter by `type_` ("person", "project", "place",
        "organization", "topic") if you want a specific category.

        Each entity now includes `top_sources` — the breakdown of which
        sources mention it most. Useful for spotting noise: an entity
        with 1000 mentions but {gmail: 980} is probably a newsletter,
        not a real interest.

        Args:
            type_: Optional entity type filter.
            limit: Max number of entities to return (default 20).
        """
        from bunshin.knowledge_graph import entity_with_counts, init_kg_schema
        conn = init_db(db_path)
        try:
            init_kg_schema(conn)
            entities = entity_with_counts(conn)
            if type_:
                entities = [e for e in entities if e.get("type") == type_]
            entities = entities[:limit]
            # Attach per-entity source breakdown so the calling agent
            # can spot newsletter-driven noise.
            for e in entities:
                eid = e.get("id")
                if eid is None:
                    e["top_sources"] = {}
                    continue
                src_rows = conn.execute(
                    "SELECT r.source, COUNT(*) FROM record_entities re "
                    "JOIN records r ON r.id = re.record_id "
                    "WHERE re.entity_id = ? GROUP BY r.source "
                    "ORDER BY 2 DESC",
                    (eid,),
                ).fetchall()
                e["top_sources"] = {row[0]: row[1] for row in src_rows}
            return json.dumps(
                {"count": len(entities), "entities": entities},
                ensure_ascii=False, indent=2,
            )
        finally:
            conn.close()

    @mcp.tool()
    def get_today_hero() -> str:
        """Return the single most actionable insight for today.

        Auto-picks from upcoming events (next 14 days), stale projects,
        and recent files — same logic as the web app's "今日これだけ"
        hero card. Use this for daily morning briefings or when the
        user asks "what should I focus on today?".

        Returns:
            JSON object: {"hero": {...}, "generated_at": "..."} where
            `hero` is one of three shapes selected by priority:

            - kind="event":         {headline, detail}   — calendar event in next 14 days (BLUE/info)
            - kind="stale_project": {headline, detail}   — project no signal for >7 days (YELLOW/warn)
            - kind="recent_file":   {headline, detail}   — most recent file (GRAY/neutral)
            - or `null` if nothing surfaces.

            The kind names are stable — callers can branch on them to
            choose an appropriate UI tone.
        """
        from bunshin.insights import generate_insights
        conn = init_db(db_path)
        try:
            j = generate_insights(conn)
            hero = None
            if j.get("upcoming_events"):
                e = j["upcoming_events"][0]
                hero = {
                    "kind": "event",
                    "headline": f"次の予定: {e.get('summary', '?')}",
                    "detail": f"{e.get('start', '?')}"
                              + (f" @ {e['location']}" if e.get('location') else ""),
                }
            elif j.get("inactive_projects"):
                p = j["inactive_projects"][0]
                hero = {
                    "kind": "stale_project",
                    "headline": f"「{p.get('name')}」が {p.get('days_ago')} 日動いてません",
                    "detail": p.get("description", ""),
                }
            elif j.get("recent_files"):
                f = j["recent_files"][0]
                hero = {
                    "kind": "recent_file",
                    "headline": f.get("name", "?"),
                    "detail": f.get("modified", ""),
                }
            return json.dumps({"hero": hero, "generated_at": j.get("generated_at")},
                              ensure_ascii=False, indent=2)
        finally:
            conn.close()

    @mcp.tool()
    def get_recent_chat(n: int = 5, min_user_chars: int = 8) -> str:
        """Return the user's N most recent substantive chat sessions.

        Sessions whose first user message is shorter than `min_user_chars`
        (default 8) are skipped — "hello" / "hi" / "test" don't carry
        useful context. To include them, pass min_user_chars=0.

        Use to give continuity context — "what has the user been
        discussing with their assistant lately?" — without dredging up
        old conversations from RAG search.
        """
        from bunshin.chat_history import list_sessions, get_messages, init_chat_schema
        conn = init_db(db_path)
        try:
            init_chat_schema(conn)
            # Overfetch and post-filter so the n we return is "substantive"
            # sessions, not raw most-recent.
            raw_sessions = list_sessions(conn, limit=max(1, n) * 4)
            out = []
            for s in raw_sessions:
                if len(out) >= max(1, n):
                    break
                msgs = get_messages(conn, s["id"])
                # Empty sessions (placeholder rows the user opened then
                # walked away from) have no value to an external agent.
                if not msgs:
                    continue
                first_user = next(
                    (m["content"] for m in msgs if m["role"] == "user"), None
                )
                if first_user is None:
                    continue
                stripped = first_user.strip()
                if len(stripped) < max(0, min_user_chars):
                    continue
                out.append({
                    "id": s["id"],
                    "title": s.get("title") or "",
                    "created_at": _format_timestamp(s.get("created_at")),
                    "message_count": len(msgs),
                    "first_user_message": first_user[:200],
                })
            return json.dumps({"count": len(out), "sessions": out},
                              ensure_ascii=False, indent=2)
        finally:
            conn.close()

    return mcp


def run(db_path: Path = DEFAULT_DB_PATH) -> None:
    log.info(f"Bunshin MCP server starting (db={db_path})")
    mcp = create_mcp(db_path)
    mcp.run()
