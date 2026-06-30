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
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

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

    # v0.9.16: max chars of `content` to return per hit. Long records
    # (PDF/Notes) used to blow the MCP response up to 100KB+, which
    # ate the calling LLM's context budget. Truncated bodies suggest
    # `recall_session(source_id=...)` for the full text.
    _MCP_CONTENT_MAX = 1500

    def _distance_to_percent(r: dict) -> int | None:
        """Mirror the Web UI's relevance_label() so MCP hits show the
        same 0-100 scale the user sees in the search tab.
        Returns None when the distance is meaningless (keyword fallback
        or missing vector)."""
        sc = r.get("score_components") or {}
        if "keyword_fallback" in sc:
            return None  # fallback distances are fake (all 1.0)
        rerank = sc.get("rerank")
        if isinstance(rerank, (int, float)):
            return max(0, min(100, round(rerank * 100)))
        d = r.get("distance")
        if d is None or d >= 999:
            return None
        # Same formula as web/server.py relevanceLabel():
        # 13–15 ≈ great, 16–18 ≈ ok, 20+ ≈ weak.
        return max(0, min(100, round(100 - (d - 10) * 6)))

    @mcp.tool()
    def search_memory(
        query: Annotated[
            str,
            Field(description=(
                "Natural language search query, Japanese OK. "
                "Multi-word queries (e.g. '壱岐黄金 じゃがいも') are "
                "automatically LLM-paraphrased for better recall."
            )),
        ],
        limit: Annotated[
            int,
            Field(
                default=10, ge=1, le=50,
                description="Max results to return (1-50, default 10).",
            ),
        ] = 10,
        sort: Annotated[
            str,
            Field(
                default="relevance",
                description=(
                    "'relevance' (default), 'newest', or 'oldest'."
                ),
            ),
        ] = "relevance",
        min_relevance: Annotated[
            int,
            Field(
                default=20, ge=0, le=100,
                description=(
                    "Drop hits below this relevance_percent (0-100, default 20). "
                    "Set 0 to disable filtering. Mirrors Bunshin's web-UI "
                    "auto-filter so callers don't see junk-tier hits."
                ),
            ),
        ] = 20,
        content_max_chars: Annotated[
            int,
            Field(
                default=1500, ge=100, le=20000,
                description=(
                    "Per-hit content cap (default 1500). Use a smaller "
                    "value (e.g. 400) when context budget is tight, or a "
                    "larger one (e.g. 4000) when you need more text inline "
                    "without an extra recall_session round-trip."
                ),
            ),
        ] = 1500,
    ) -> str:
        """Search the user's past memory by semantic similarity.

        Use this whenever the user references something from the past — past
        conversations, projects, decisions, files, etc. The query can be in
        Japanese or English; matches are by meaning, not exact words.
        Multi-word Japanese queries (e.g. "壱岐黄金 じゃがいも") are
        automatically expanded via LLM paraphrasing for higher recall.

        Examples of when to use:
        - User mentions a project / organization / person name: search for it
        - User asks "before"/"last week"/"何だっけ"/"do you remember": search and recall
        - User makes a decision that may have past context: search to verify

        Args:
            query: Natural language search query (Japanese OK).
            limit: Maximum number of results to return (default 10, max 50).
            sort: "relevance" (default), "newest", or "oldest".
            min_relevance: Drop hits below this relevance_percent (0-100,
                default 20). Set 0 to disable. Mirrors Bunshin's auto-filter
                so MCP callers don't see junk-tier hits.
            content_max_chars: Per-hit content cap (default 1500). Use a
                smaller value (e.g. 400) when context budget is tight, or
                a larger one (e.g. 4000) when you need more text inline
                without an extra recall_session round-trip.

        Returns:
            JSON list of relevant past records, each with timestamp, role,
            source, source_id, relevance_percent (0-100, same as web UI;
            null when only keyword-fallback matched), content_truncated
            (bool — when true, fetch full text via recall_session), and
            content (capped at content_max_chars to preserve calling LLM
            context budget).
        """
        conn = init_db(db_path)
        # Clamp inputs to sane bounds — callers sometimes pass through
        # raw user input and we don't want a 5000-limit query DoSing
        # ourselves or a negative content cap producing empty strings.
        eff_limit = min(max(limit, 1), 50)
        eff_min_rel = max(0, min(int(min_relevance), 100))
        eff_max_chars = max(100, min(int(content_max_chars), 20000))
        try:
            results = do_search(
                conn,
                query,
                limit=eff_limit,
                sort=sort if sort in ("relevance", "newest", "oldest") else "relevance",
                # Fix 1: force LLM query expansion. Settings panel toggle
                # doesn't help here — MCP callers don't read user settings.
                expand=True,
                # Cross-encoder rerank — turns the "all distance=1.0"
                # keyword-fallback noise into a real similarity score.
                rerank=True,
            )
            formatted = []
            for r in results:
                rel = _distance_to_percent(r)
                # v0.10.8 Honda Patch A: drop sub-threshold hits. Mirrors
                # the Web UI's auto-filter behaviour so MCP callers don't
                # get a "0% relevance" hit they'd have to filter out
                # themselves. None (keyword-fallback) passes through —
                # we have no quality signal so let the caller judge.
                if rel is not None and rel < eff_min_rel:
                    continue
                content = r.get("content") or ""
                truncated = len(content) > eff_max_chars
                if truncated:
                    content = (
                        content[:eff_max_chars]
                        + f"\n\n…[content truncated at {eff_max_chars} chars — "
                        f"call recall_session(source_id={r['source_id']!r}) for the full session]"
                    )
                formatted.append({
                    "timestamp": _format_timestamp(r["timestamp"]),
                    "role": (r["metadata"] or {}).get("role"),
                    "source": r["source"],
                    "source_id": r["source_id"],
                    # Fix 3: surface the same 0-100 score the web UI shows
                    # so the calling LLM can sort/filter on actual quality
                    # rather than the all-1.0 raw distance.
                    "relevance_percent": rel,
                    "content_truncated": truncated,  # Fix 2 transparency
                    "content": content,
                })
            # v0.10.35: surface pinned entities the user has explicitly
            # annotated. A connecting LLM can use this to "anchor"
            # downstream reasoning — e.g. if the query is "壱岐島" and
            # the user has pinned 壱岐島 with "壱岐黄金 / MARINE FLIGHT
            # / 海洋教育 の活動拠点", the LLM should treat that as the
            # user's declared reality rather than inferring from
            # record snippets.
            pinned_entities = []
            try:
                pin_rows = conn.execute(
                    "SELECT e.id, e.name, e.type, s.value "
                    "FROM settings s "
                    "JOIN entities e ON s.key = 'pin:entity:' || e.id "
                    "WHERE s.key LIKE 'pin:entity:%' "
                    "  AND s.value IS NOT NULL AND TRIM(s.value) <> '' "
                    "  AND EXISTS ("
                    "    SELECT 1 FROM entities e2 "
                    "    WHERE e2.id = e.id "
                    "    AND (LOWER(e2.name) LIKE '%' || LOWER(?) || '%' "
                    "         OR EXISTS ("
                    "           SELECT 1 FROM record_entities re "
                    "           JOIN records r ON r.id = re.record_id "
                    "           WHERE re.entity_id = e.id "
                    "           AND r.content LIKE '%' || ? || '%' "
                    "           LIMIT 1"
                    "         )"
                    "    )"
                    "  ) "
                    "LIMIT 5",
                    (query, query),
                ).fetchall()
                for r in pin_rows:
                    pinned_entities.append({
                        "entity_id": r[0],
                        "entity_name": r[1],
                        "entity_type": r[2],
                        "pinned_context": r[3],
                    })
            except Exception:
                pass
            payload = {
                "query": query,
                "count": len(formatted),
                "min_relevance_applied": eff_min_rel,
                "content_max_chars": eff_max_chars,
                "results": formatted,
            }
            if pinned_entities:
                payload["pinned_entities"] = pinned_entities
                payload["pinned_entities_note"] = (
                    "These entities have user-authored pinned context that "
                    "describes off-screen reality not captured in the "
                    "records. Treat these as the user's declared truth "
                    "when answering — outrank what record snippets imply."
                )
            return json.dumps(payload, ensure_ascii=False, indent=2)
        finally:
            conn.close()

    @mcp.tool()
    def recall_session(
        source_id: Annotated[
            str,
            Field(description=(
                "source_id from a search_memory result. Identifies the "
                "session / file / message thread to expand."
            )),
        ],
        max_messages: Annotated[
            int,
            Field(
                default=100, ge=1, le=1000,
                description="Max messages to return (1-1000, default 100).",
            ),
        ] = 100,
    ) -> str:
        """Get the full conversation/session that contains a specific record.

        Use this after `search_memory` returns a hit, when you need full
        context around the matched record (e.g. "what led up to that
        decision?", "what was the rest of that discussion?").

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
    def get_flashback(
        date: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "ISO date string (YYYY-MM-DD). Defaults to today. "
                    "The function pulls records from this date last week, "
                    "3 months ago, 1 year ago, and 5 years ago."
                ),
            ),
        ] = None,
    ) -> str:
        """Get "this date in the past" recall windows for a given date.

        Returns up to 5 records each from last week, 3 months ago, 1 year ago,
        and 5 years ago. Use this when the user asks "what was I doing last
        year on this day?" or for daily morning reflection prompts.
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
        type_: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "Optional entity type filter: 'person', 'project', "
                    "'place', 'organization', 'concept', 'tool', or 'topic'. "
                    "Omit to get all types."
                ),
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                default=20, ge=1, le=200,
                description="Max number of entities to return (1-200, default 20).",
            ),
        ] = 20,
        exclude_noisy: Annotated[
            bool,
            Field(
                default=True,
                description=(
                    "Drop newsletter-driven noise (entities whose mentions "
                    "come >80% from gmail/browser). Default True."
                ),
            ),
        ] = True,
    ) -> str:
        """List the most-mentioned entities in the user's memory.

        Use this to surface what's currently active in the user's life:
        the people, projects, and places that come up most often across
        all sources.

        Each entity includes `top_sources` (per-source mention
        breakdown). When `exclude_noisy=True` (default), entities whose
        mentions come >80% from gmail/browser — usually newsletter
        signals like "note", "ポーランド" surfacing from note.com
        weekly digests — are dropped so what's returned is what's *new
        in the user's life*, not what's new in their inbox.

        Backed by the shared `get_top_entities()` helper, so this list
        always matches what the web UI shows.
        """
        from bunshin.knowledge_graph import get_top_entities, init_kg_schema
        conn = init_db(db_path)
        try:
            init_kg_schema(conn)
            entities = get_top_entities(
                conn, limit=limit, type_=type_,
                with_sources=True, exclude_noisy=exclude_noisy,
            )
            return json.dumps(
                {"count": len(entities), "entities": entities},
                ensure_ascii=False, indent=2,
            )
        finally:
            conn.close()

    # v0.9.16: generate_insights() can take 5-30s on large DBs because
    # it joins records + entities + signal_score + dates. MCP clients
    # time out around 30s — and Claude calling it for a morning
    # briefing was hitting timeout. Cache today's hero to disk so 2nd+
    # calls within the same day are sub-millisecond.
    _HERO_CACHE_PATH = Path.home() / ".bunshin" / "hero_cache.json"

    def _compute_today_hero(conn) -> dict:
        from bunshin.insights import generate_insights
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
        # v0.10.36: pull the user's pinned entities into every hero
        # response. The morning-briefing LLM gets a one-line reminder
        # of the user's declared core projects, so it stays anchored
        # even when the hero itself is about a random recent file.
        pinned_summary = []
        try:
            for r in conn.execute(
                "SELECT e.name, e.type, s.value "
                "FROM settings s "
                "JOIN entities e ON s.key = 'pin:entity:' || e.id "
                "WHERE s.key LIKE 'pin:entity:%' "
                "  AND s.value IS NOT NULL AND TRIM(s.value) <> '' "
                "ORDER BY e.name COLLATE NOCASE "
                "LIMIT 8"
            ):
                pinned_summary.append({
                    "name": r[0], "type": r[1],
                    # First line of the pin only, capped at 120 chars,
                    # to keep the briefing payload small.
                    "context_preview": (r[2].split("\n")[0])[:120],
                })
        except Exception:
            pass
        return {
            "hero": hero,
            "generated_at": j.get("generated_at"),
            "pinned_anchors": pinned_summary,
        }

    @mcp.tool()
    def get_today_hero() -> str:
        """Return the single most actionable insight for today.

        Auto-picks from upcoming events (next 14 days), stale projects,
        and recent files — same logic as the web app's "今日これだけ"
        hero card. Use this for daily morning briefings or when the
        user asks "what should I focus on today?".

        Cached to ~/.bunshin/hero_cache.json per-day for sub-millisecond
        second calls. First call of the day takes 5-30s (computes from
        scratch); subsequent calls serve the cached value.

        Returns:
            JSON object: {"hero": {...}, "generated_at": "...", "from_cache": bool}
            where `hero` is one of three shapes selected by priority:

            - kind="event":         {headline, detail}   — calendar event in next 14 days (BLUE/info)
            - kind="stale_project": {headline, detail}   — project no signal for >7 days (YELLOW/warn)
            - kind="recent_file":   {headline, detail}   — most recent file (GRAY/neutral)
            - or `null` if nothing surfaces.

            The kind names are stable — callers can branch on them to
            choose an appropriate UI tone.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        # Cache hit path — sub-ms response.
        try:
            cached = json.loads(_HERO_CACHE_PATH.read_text())
            if cached.get("date") == today:
                return json.dumps(
                    {
                        "hero": cached.get("hero"),
                        "generated_at": cached.get("generated_at"),
                        "from_cache": True,
                    },
                    ensure_ascii=False, indent=2,
                )
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        # Cache miss — compute + persist.
        conn = init_db(db_path)
        try:
            result = _compute_today_hero(conn)
            try:
                _HERO_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                _HERO_CACHE_PATH.write_text(json.dumps(
                    {"date": today, **result}, ensure_ascii=False,
                ))
            except OSError:
                pass  # cache write best-effort; still return the result
            return json.dumps(
                {**result, "from_cache": False},
                ensure_ascii=False, indent=2,
            )
        finally:
            conn.close()

    @mcp.tool()
    def get_recent_chat(
        n: Annotated[
            int,
            Field(
                default=5, ge=1, le=50,
                description="Max sessions to return (1-50, default 5).",
            ),
        ] = 5,
        min_user_chars: Annotated[
            int,
            Field(
                default=8, ge=0, le=200,
                description=(
                    "Skip sessions whose first user message is shorter "
                    "than this (default 8). 'hello' / 'hi' / 'test' "
                    "don't carry useful context. Set 0 to include them all."
                ),
            ),
        ] = 8,
    ) -> str:
        """Return the user's N most recent substantive chat sessions.

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

    @mcp.tool()
    def pin_entity_context(
        entity: Annotated[
            str,
            Field(description=(
                "Entity to pin context onto. Either the integer ID "
                "(as a string, e.g. '22') or the EXACT entity name "
                "(e.g. '壱岐島'). Use list_top_entities or search_memory "
                "to find the right identifier."
            )),
        ],
        context: Annotated[
            str,
            Field(
                default="",
                description=(
                    "1-2 sentence user-authored context that will be "
                    "applied as a HARD CONSTRAINT on the next describe "
                    "for this entity. Overrides record co-occurrence "
                    "and web sources. Pass empty string to clear the "
                    "existing pin. Pass nothing (no arg) to read the "
                    "current pin without changing it."
                ),
            ),
        ] = "",
        action: Annotated[
            str,
            Field(
                default="auto",
                description=(
                    "'auto' (default): set if context is non-empty, "
                    "clear if context is empty. 'get': always read "
                    "(ignores context). 'clear': always delete (ignores context)."
                ),
            ),
        ] = "auto",
    ) -> str:
        """Set, read, or clear a user-pinned context on an entity.

        Pins are the user's hand-written declaration of what an entity
        actually is — they override what the records and web sources
        would otherwise infer. Useful when:

        - The records reflect what the user has been *talking about*
          rather than what an entity *actually is* (e.g. 壱岐島's record
          co-occurrence is dominated by AI-research entities Honda
          chatted with Claude about, but the real-world place hosts his
          ECommerce / drone-services / ocean-education businesses).
        - Wikipedia / official site returns a generic public answer
          that the user wants to override with private context (e.g.
          AIR Flight's public profile vs. Honda's "I'm the new-business
          producer there" framing).

        After setting a pin, the next describe call will weave it into
        the prompt as a hard constraint. The pin persists in the
        settings table until cleared.
        """
        conn = init_db(db_path)
        try:
            row = conn.execute(
                "SELECT id, name FROM entities WHERE "
                + ("id = ?" if entity.isdigit() else "name = ?"),
                (int(entity) if entity.isdigit() else entity,),
            ).fetchone()
            if not row:
                return json.dumps(
                    {"ok": False, "error": f"entity not found: {entity!r}"},
                    ensure_ascii=False,
                )
            eid, name = row["id"] if isinstance(row, dict) else row[0], row[1] if not isinstance(row, dict) else row["name"]
            key = f"pin:entity:{eid}"
            # Resolve action
            if action == "get":
                op = "get"
            elif action == "clear":
                op = "clear"
            elif action == "auto":
                op = "clear" if not (context or "").strip() else "set"
            else:
                return json.dumps({"ok": False, "error": f"unknown action: {action}"}, ensure_ascii=False)
            if op == "get":
                cur = conn.execute(
                    "SELECT value FROM settings WHERE key = ?", (key,)
                ).fetchone()
                v = (cur[0] if cur else "") or ""
                return json.dumps(
                    {"ok": True, "entity_id": eid, "entity_name": name,
                     "action": "get", "context": v},
                    ensure_ascii=False, indent=2,
                )
            if op == "clear":
                with conn:
                    conn.execute("DELETE FROM settings WHERE key = ?", (key,))
                return json.dumps(
                    {"ok": True, "entity_id": eid, "entity_name": name,
                     "action": "clear"},
                    ensure_ascii=False, indent=2,
                )
            # set
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, context.strip()),
                )
            return json.dumps(
                {"ok": True, "entity_id": eid, "entity_name": name,
                 "action": "set", "context": context.strip(),
                 "note": "Next describe call for this entity will use this pin as a hard constraint."},
                ensure_ascii=False, indent=2,
            )
        finally:
            conn.close()

    @mcp.tool()
    def get_server_info() -> str:
        """Return the running MCP server's version, uptime, and DB stats.

        Use this on session start for two things:

        1. Detect "Bunshin was updated but Claude is still talking to
           the old MCP server" — if the version returned here lags
           behind the bundled DMG version, ask the user to quit and
           relaunch Claude so a fresh MCP process is spawned.

        2. Get a quick read on **how much memory exists**: record /
           entity counts, top source breakdown, oldest record date.
           Useful for sanity-checking "is the user's DB rich enough
           that I should rely on it" before deciding whether to lean
           on search_memory results.
        """
        from bunshin import __version__
        import os as _os
        conn = init_db(db_path)
        try:
            n_records = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            try:
                n_entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            except Exception:
                n_entities = 0
            sources = {}
            try:
                for src, cnt in conn.execute(
                    "SELECT source, COUNT(*) FROM records GROUP BY source "
                    "ORDER BY 2 DESC LIMIT 8"
                ):
                    sources[src] = cnt
            except Exception:
                pass
            oldest = conn.execute(
                "SELECT MIN(timestamp) FROM records WHERE timestamp > 0"
            ).fetchone()
            oldest_ts = (oldest[0] if oldest else None) or 0
            oldest_iso = _format_timestamp(oldest_ts) if oldest_ts else None
        finally:
            conn.close()
        return json.dumps({
            "server": "bunshin-mcp",
            "version": __version__,
            "pid": _os.getpid(),
            "tools": [
                "search_memory", "recall_session", "get_flashback",
                "list_top_entities", "get_today_hero", "get_recent_chat",
                "pin_entity_context", "get_server_info",
            ],
            "memory": {
                "records": n_records,
                "entities": n_entities,
                "top_sources": sources,
                "oldest_record": oldest_iso,
            },
            "note": (
                "If this version is older than the Bunshin app you just "
                "updated, quit Claude (⌘Q) and relaunch — the MCP "
                "process is spawned once per Claude session and won't "
                "pick up DMG updates otherwise."
            ),
        }, ensure_ascii=False, indent=2)

    return mcp


def _write_status_file() -> None:
    """Write {pid, version, started_at} to ~/.bunshin/mcp_status/<pid>.json
    so the Bunshin web server can detect "MCP process running an older
    version than the DMG-bundled web server" and surface a banner.

    Reviewers in rounds 4-6 all hit the same trap: edited code on disk
    + a Claude-spawned MCP process still importing the previous version
    = silent "your fix isn't applied". Disk status files are the
    cross-process source of truth that closes this loop.
    """
    try:
        from bunshin import __version__
        import os as _os, json as _json, time as _time
        status_dir = Path.home() / ".bunshin" / "mcp_status"
        status_dir.mkdir(parents=True, exist_ok=True)
        # Prune dead siblings — their PIDs no longer exist.
        for f in status_dir.glob("*.json"):
            try:
                pid = int(f.stem)
                _os.kill(pid, 0)  # signal 0 = existence check
            except (OSError, ValueError):
                f.unlink(missing_ok=True)
        path = status_dir / f"{_os.getpid()}.json"
        path.write_text(_json.dumps({
            "pid": _os.getpid(),
            "version": __version__,
            "started_at": int(_time.time()),
        }, ensure_ascii=False))
        # Best-effort cleanup at shutdown.
        import atexit as _atexit
        _atexit.register(lambda: path.unlink(missing_ok=True))
    except Exception as e:
        log.warning(f"failed to write mcp status file: {e}")


def run(db_path: Path = DEFAULT_DB_PATH) -> None:
    log.info(f"Bunshin MCP server starting (db={db_path})")
    _write_status_file()
    mcp = create_mcp(db_path)
    mcp.run()
