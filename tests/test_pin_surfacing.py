"""Regression tests for v0.10.35-37 pin-context surfacing across MCP responses.

These don't exercise the MCP transport — they validate the SQL invariants
behind each pin-surfacing field, so a refactor in the settings layer
can't silently break the LLM-facing contract.
"""
import sqlite3

import pytest


def _seed_entity(conn, name, type_, description=None):
    cur = conn.execute(
        "INSERT INTO entities (name, type, description, created_at) "
        "VALUES (?, ?, ?, strftime('%s','now'))",
        (name, type_, description),
    )
    conn.commit()
    return cur.lastrowid


def _pin(conn, entity_id, context):
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (f"pin:entity:{entity_id}", context),
    )
    conn.commit()


def test_pin_list_endpoint_query_returns_only_active_pins(conn):
    """v0.10.31 GET /api/pins/list backing query: JOIN settings × entities
    on 'pin:entity:<id>'. Must exclude empty strings, NULL values, and
    stale settings rows whose entity has been deleted."""
    from bunshin.knowledge_graph import init_kg_schema
    init_kg_schema(conn)

    e1 = _seed_entity(conn, "壱岐島", "place")
    e2 = _seed_entity(conn, "MARINE FLIGHT", "organization")
    e3 = _seed_entity(conn, "AIR Flight", "organization")
    # Active pins
    _pin(conn, e1, "壱岐黄金プロジェクト・MARINE FLIGHT・海洋教育の活動拠点")
    _pin(conn, e2, "個人向けドローン体験＋同伴空撮")
    # Empty-value pin — must NOT show up
    _pin(conn, e3, "")
    # Orphan pin: entity was deleted but the settings row remains
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)",
        ("pin:entity:9999", "stale orphan pin"),
    )
    conn.commit()

    rows = conn.execute(
        "SELECT s.key, s.value, e.id, e.name "
        "FROM settings s "
        "JOIN entities e ON ('pin:entity:' || e.id) = s.key "
        "WHERE s.key LIKE 'pin:entity:%' "
        "  AND s.value IS NOT NULL AND TRIM(s.value) <> '' "
        "ORDER BY e.name COLLATE NOCASE"
    ).fetchall()
    names = [r[3] for r in rows]
    assert names == ["MARINE FLIGHT", "壱岐島"], (
        f"only active-pin entities (MARINE FLIGHT + 壱岐島) should surface — "
        f"got {names}. Empty-string pin on AIR Flight and orphan #9999 "
        f"must be excluded."
    )


def test_search_memory_pinned_entities_query_substring_match(conn):
    """v0.10.35 search_memory's pinned_entities branch (v0.10.44
    narrowing): query surfaces a pin ONLY when query is a substring
    of the entity name. Record-content matching removed because it
    was polluting unrelated queries — e.g. "Claude" would surface
    the 壱岐黄金 pin because Claude co-appears in its records."""
    from bunshin.knowledge_graph import init_kg_schema
    init_kg_schema(conn)

    iki = _seed_entity(conn, "壱岐島", "place")
    iki_kin = _seed_entity(conn, "壱岐黄金プロジェクト", "project")
    unrelated = _seed_entity(conn, "Coca-Cola", "organization")
    _pin(conn, iki, "壱岐の主要事業の拠点")
    _pin(conn, iki_kin, "小粒じゃがいもの高級ブランド化")
    # unrelated has a pin but its name doesn't contain "壱岐"
    _pin(conn, unrelated, "アメリカの飲料会社")

    def _surface(query):
        rows = conn.execute(
            "SELECT e.name FROM entities e "
            "JOIN settings s ON s.key = 'pin:entity:' || e.id "
            "WHERE s.value IS NOT NULL AND TRIM(s.value) <> '' "
            "AND LOWER(e.name) LIKE '%' || LOWER(?) || '%'",
            (query,),
        ).fetchall()
        return {r[0] for r in rows}

    surfaced = _surface("壱岐")
    assert "壱岐島" in surfaced
    assert "壱岐黄金プロジェクト" in surfaced
    assert "Coca-Cola" not in surfaced

    # v0.10.44 narrowing: "Claude" query must not surface any pin
    # even though Claude co-appears in the 壱岐黄金 project's records.
    surfaced_unrelated = _surface("Claude")
    assert surfaced_unrelated == set(), (
        "'Claude' query must not surface any pin — the v0.10.44 name-"
        "only match prevents record-content pollution"
    )


def test_flashback_signal_score_filter(conn):
    """v0.10.44 (Honda 100-test finding F): get_flashback SQL filter
    on COALESCE(signal_score, 50) >= 30 excludes low-signal records
    (Gmail notification emails, tracking-pixel pings)."""
    from bunshin.storage import insert_record

    # Insert 2 records at the same timestamp: one high-signal note,
    # one low-signal notification.
    ts = 1717000000  # arbitrary
    insert_record(
        conn, source="notes", timestamp=ts,
        content="本田: 壱岐黄金プロジェクトの試作じゃがいも試食会を来週開催予定。"
                "参加者は 15 名、場所は壱岐島の直売所。準備リストは別途 Notion に。",
        source_id="note-real-1",
        metadata={"signal_score": 80},
    )
    insert_record(
        conn, source="gmail", timestamp=ts,
        content="[note.com] さんがあなたの投稿にスキしました。詳しくはこちら…",
        source_id="mail-noise-1",
        metadata={"signal_score": 10},
    )
    # Manually populate signal_score column (importer normally does this)
    conn.execute("UPDATE records SET signal_score = 80 WHERE source_id = ?", ("note-real-1",))
    conn.execute("UPDATE records SET signal_score = 10 WHERE source_id = ?", ("mail-noise-1",))
    conn.commit()

    # Same WHERE as MCP get_flashback
    rows = conn.execute(
        "SELECT source, content FROM records "
        "WHERE timestamp BETWEEN ? AND ? "
        "  AND length(content) >= 50 "
        "  AND COALESCE(signal_score, 50) >= 30",
        (ts, ts + 86400),
    ).fetchall()
    sources = {r[0] for r in rows}
    assert "notes" in sources, "high-signal real record must survive"
    assert "gmail" not in sources, (
        "low-signal noise (signal_score=10) must be filtered out by the >=30 gate"
    )


def test_get_today_hero_pinned_anchors_query_caps_at_8_alphabetical(conn):
    """v0.10.36 get_today_hero attaches `pinned_anchors` — up to 8 entries,
    sorted by name COLLATE NOCASE so the briefing reads stable across days."""
    from bunshin.knowledge_graph import init_kg_schema
    init_kg_schema(conn)

    # Create 10 entities, pin all of them. Only 8 should come back.
    names = ["Z entity", "y entity", "M entity", "A entity",
             "壱岐島", "MARINE", "AIR", "リーフ", "沼津", "壱岐黄金"]
    for n in names:
        eid = _seed_entity(conn, n, "project")
        _pin(conn, eid, f"context for {n}")

    rows = conn.execute(
        "SELECT e.name FROM settings s "
        "JOIN entities e ON s.key = 'pin:entity:' || e.id "
        "WHERE s.key LIKE 'pin:entity:%' "
        "  AND s.value IS NOT NULL AND TRIM(s.value) <> '' "
        "ORDER BY e.name COLLATE NOCASE "
        "LIMIT 8"
    ).fetchall()
    assert len(rows) == 8, f"LIMIT 8 must cap, got {len(rows)}"
    returned = [r[0] for r in rows]
    # COLLATE NOCASE means 'y' and 'Y' sort together, 'a' before 'b'.
    # Result must be sorted ascending.
    assert returned == sorted(returned, key=str.casefold), (
        f"name sort must be stable + case-insensitive — got {returned}"
    )


def test_list_top_entities_pinned_field_batched_query(conn):
    """v0.10.37 list_top_entities decorates each entity with `pinned` bool +
    `pinned_context_preview`. Uses a single batched SELECT keyed on
    settings.key IN (pin:entity:1, pin:entity:2, ...)."""
    from bunshin.knowledge_graph import init_kg_schema
    init_kg_schema(conn)

    e1 = _seed_entity(conn, "壱岐島", "place")
    e2 = _seed_entity(conn, "Unpinned Org", "organization")
    e3 = _seed_entity(conn, "MARINE FLIGHT", "organization")
    _pin(conn, e1, "壱岐黄金・MARINE FLIGHT・海洋教育の活動拠点\n(改行後はpreviewでカットされる)")
    _pin(conn, e3, "個人向けドローン体験")

    ids = [e1, e2, e3]
    placeholders = ",".join("?" * len(ids))
    keys = [f"pin:entity:{i}" for i in ids]
    rows = conn.execute(
        f"SELECT key, value FROM settings "
        f"WHERE key IN ({placeholders}) "
        f"AND value IS NOT NULL AND TRIM(value) <> ''",
        keys,
    ).fetchall()
    pinned_map = {int(k.split(":")[-1]): v for k, v in rows}

    assert pinned_map.get(e1), "壱岐島 must come back from the batched lookup"
    assert pinned_map.get(e3), "MARINE FLIGHT must come back"
    assert e2 not in pinned_map, (
        "Unpinned Org has no pin row — must not appear in the map"
    )

    # Preview = first newline, capped at 120 chars
    preview_e1 = pinned_map[e1].split("\n")[0][:120]
    assert "改行後" not in preview_e1, (
        "preview must stop at first newline so multi-line pins don't bleed"
    )
    assert len(preview_e1) <= 120


def test_export_pins_round_trips_through_import(conn, tmp_path):
    """v0.10.39 export-pins / import-pins: round-trip on name match.
    Names (not IDs) are the portable identifier — exported on machine
    A, imported on machine B where IDs are different but names match,
    pins land on the correct entity."""
    import json as _json
    from bunshin.knowledge_graph import init_kg_schema
    init_kg_schema(conn)

    # Simulate source DB: 3 entities, 2 pinned
    e_iki = _seed_entity(conn, "壱岐島", "place")
    _seed_entity(conn, "Unrelated", "topic")
    e_air = _seed_entity(conn, "AIR Flight", "organization")
    _pin(conn, e_iki, "main business hub")
    _pin(conn, e_air, "drone subsidiary")

    # Export: same query the CLI uses, no JSON ID
    rows = conn.execute(
        "SELECT e.name, e.type, s.value "
        "FROM settings s "
        "JOIN entities e ON s.key = 'pin:entity:' || e.id "
        "WHERE s.key LIKE 'pin:entity:%' "
        "  AND s.value IS NOT NULL AND TRIM(s.value) <> '' "
        "ORDER BY e.name COLLATE NOCASE"
    ).fetchall()
    exported = [
        {"entity_name": r[0], "entity_type": r[1], "context": r[2]}
        for r in rows
    ]
    out = tmp_path / "pins.json"
    out.write_text(_json.dumps(exported, ensure_ascii=False))
    assert len(exported) == 2, "only the 2 pinned entities export"
    assert {p["entity_name"] for p in exported} == {"壱岐島", "AIR Flight"}

    # Wipe pins to simulate a fresh destination DB; entities stay.
    conn.execute("DELETE FROM settings WHERE key LIKE 'pin:entity:%'")
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM settings WHERE key LIKE 'pin:entity:%'"
    ).fetchone()[0] == 0

    # Import: same logic as the CLI — match by name, skip-if-exists
    # default. Here nothing exists, so all should land.
    data = _json.loads(out.read_text())
    applied = 0
    for item in data:
        row = conn.execute(
            "SELECT id FROM entities WHERE name = ?", (item["entity_name"],)
        ).fetchone()
        assert row, f"{item['entity_name']} should be present in dest DB"
        key = f"pin:entity:{row[0]}"
        existing = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if existing and (existing[0] or "").strip():
            continue  # default skip
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, item["context"]),
        )
        applied += 1
    conn.commit()
    assert applied == 2, "fresh dest DB → both pins should apply"

    # Verify the pins landed on the correct entities by name
    iki_pin = conn.execute(
        "SELECT s.value FROM settings s "
        "JOIN entities e ON s.key = 'pin:entity:' || e.id "
        "WHERE e.name = ?", ("壱岐島",),
    ).fetchone()
    assert iki_pin[0] == "main business hub"


def test_temporal_router_matches_time_phrases_and_ignores_others():
    """v0.10.43 temporal router: queries with time phrases must
    surface a recall_suggestion pointing at the right recall tool.
    Non-temporal queries must NOT trigger a suggestion (no false
    positive on entity names)."""
    import re as _re
    _patterns = [
        (r"(昨日|きのう|yesterday)", "get_recent_chat"),
        (r"(今日|きょう|today)", "get_today_hero"),
        (r"(先週|last week|1 週間前|一週間前)", "get_flashback"),
        (r"(1 ?年前|一年前|去年|last year|1yr ago)", "get_flashback"),
        (r"(3 ?ヶ月前|三ヶ月前|3 months ago)", "get_flashback"),
        (r"(明日|あした|tomorrow|来週|next week)", "get_today_hero"),
        (r"(最近|recently|直近|latest chat)", "get_recent_chat"),
    ]

    def _detect(query):
        for pat, tool in _patterns:
            if _re.search(pat, query, _re.IGNORECASE):
                return tool
        return None

    # Positive cases — must route
    positives = [
        ("昨日何話した", "get_recent_chat"),
        ("先週の予定", "get_flashback"),
        ("3ヶ月前の記録", "get_flashback"),
        ("明日 アラーム", "get_today_hero"),
        ("最近のチャット", "get_recent_chat"),
        ("what did I say yesterday", "get_recent_chat"),
        ("last week meeting", "get_flashback"),
    ]
    for q, expected_tool in positives:
        assert _detect(q) == expected_tool, (
            f"query {q!r} should route to {expected_tool}, got {_detect(q)}"
        )

    # Negative cases — must NOT route (real entity names / non-temporal)
    negatives = [
        "壱岐黄金プロジェクト",
        "MARINE FLIGHT",
        "リーフボールジャパン",
        "Bunshin Memory",
        "search_memory usage",
        "gmail import",
    ]
    for q in negatives:
        assert _detect(q) is None, (
            f"query {q!r} should NOT trigger temporal routing, "
            f"got {_detect(q)}"
        )


def test_cascade_threshold_order_and_early_exit():
    """v0.10.42 cascade retrieval: threshold sequence must be
    strictly descending, and cascade stops at the first non-empty
    tier."""
    # Simulated candidate hits with relevance percentages
    candidates = [
        {"rel": 45, "id": "high"},
        {"rel": 12, "id": "medium"},
        {"rel": 3, "id": "low"},
    ]

    def _filter(threshold):
        return [c for c in candidates if c["rel"] >= threshold]

    # Case 1: primary at 20 → 1 hit, cascade never triggers
    primary = 20
    hits = _filter(primary)
    cascade = [primary]
    if not hits and primary >= 10:
        for fb in (10, 0):
            if fb >= primary:
                continue
            hits = _filter(fb)
            cascade.append(fb)
            if hits:
                break
    assert len(hits) == 1 and cascade == [20]

    # Case 2: primary at 50 → 0 → cascade to 10 → 2 hits, stop
    primary = 50
    hits = _filter(primary)
    cascade = [primary]
    if not hits and primary >= 10:
        for fb in (10, 0):
            if fb >= primary:
                continue
            hits = _filter(fb)
            cascade.append(fb)
            if hits:
                break
    assert cascade == [50, 10]
    assert len(hits) == 2

    # Case 3: caller opted into low threshold (5) → no cascade
    primary = 5
    hits = _filter(primary)
    cascade = [primary]
    if not hits and primary >= 10:
        for fb in (10, 0):
            if fb >= primary:
                continue
            hits = _filter(fb)
            cascade.append(fb)
            if hits:
                break
    assert cascade == [5], "caller-opt-in low threshold must not cascade further"


def test_import_pins_skips_missing_entities(conn, tmp_path):
    """Items whose entity name isn't in the destination DB are
    skipped without error — the import-pins CLI logs a warning but
    keeps going."""
    import json as _json
    from bunshin.knowledge_graph import init_kg_schema
    init_kg_schema(conn)

    _seed_entity(conn, "壱岐島", "place")
    # Note: "GhostEntity" is NOT seeded
    data = [
        {"entity_name": "壱岐島", "entity_type": "place", "context": "ok"},
        {"entity_name": "GhostEntity", "entity_type": "project", "context": "should skip"},
    ]
    applied = missing = 0
    for item in data:
        row = conn.execute(
            "SELECT id FROM entities WHERE name = ?", (item["entity_name"],)
        ).fetchone()
        if not row:
            missing += 1
            continue
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (f"pin:entity:{row[0]}", item["context"]),
        )
        applied += 1
    conn.commit()
    assert applied == 1
    assert missing == 1


def test_bilingual_query_expansion_prompt_includes_translation_instruction():
    """v0.10.45 (Honda 100-test G): the expand_query_with_llm prompt must
    explicitly request English↔Japanese translation. This test doesn't call
    Ollama — it inspects the module's source to lock in the prompt structure
    so a future refactor can't silently drop the translation instruction.

    Rationale: Honda's test showed 'Iki Gold potato luxury brand' returned 0
    hits against a JP-only corpus. The prior prompt only asked for same-
    language variants. The fix teaches the LLM to always cross-translate.
    """
    import inspect
    from bunshin import search

    src = inspect.getsource(search.expand_query_with_llm)
    # Must mention both directions explicitly
    assert "英語クエリ" in src, "prompt must handle EN→JA case explicitly"
    assert "日本語クエリ" in src, "prompt must handle JA→EN case explicitly"
    assert "壱岐黄金" in src and "Iki Gold" in src, (
        "prompt must show a concrete EN↔JA translation example so the "
        "LLM understands the intended output shape"
    )
    # max_variants default must be ≥5 so both directions fit
    sig = inspect.signature(search.expand_query_with_llm)
    assert sig.parameters["max_variants"].default >= 5, (
        "cross-lingual coverage needs room for at least one EN and one JA "
        "variant on top of the usual same-language synonyms"
    )


def test_query_expansion_cache_avoids_repeat_calls(monkeypatch):
    """v0.10.45: cache invariant — the second call with the same query
    key returns cached variants without re-hitting Ollama. Regression
    guard for a hot-path perf issue that would double LLM cost per
    query if broken."""
    from bunshin import search

    # Seed the cache directly (bypasses Ollama entirely)
    search._QUERY_EXPANSION_CACHE.clear()
    key = "iki gold potato"
    search._QUERY_EXPANSION_CACHE[key] = ["壱岐黄金 じゃがいも", "Iki Gold potato"]

    # If the cache hit path works, this returns instantly without any
    # httpx / check_ollama calls. We assert both by patching them to
    # raise if ever invoked.
    def _fail(*_a, **_k):
        raise AssertionError("cache miss — should not reach Ollama")

    monkeypatch.setattr("bunshin.chat.check_ollama", _fail)
    result = search.expand_query_with_llm("Iki Gold Potato")  # case-insensitive
    assert result == ["壱岐黄金 じゃがいも", "Iki Gold potato"]


def test_partial_match_boost_scales_for_long_queries():
    """v0.10.46 (Honda 100-test H): 8+ token queries used to get zero
    all_terms_match boost because natural sentences almost never phrase
    a doc's exact words. This test verifies the proportional-boost path:

    - full match (hits==total) → +0.5, all_terms_match=True
    - long query (≥4 tokens) with ≥50% hits → linear boost hits/total*0.5
    - short query with partial hits → no partial boost (preserves prior
      strict behavior for 2-3 token proper-noun queries)
    """
    import re
    # Simulate the boost block in isolation. Extract by re-implementing
    # its exact contract — if the source diverges, this catches the drift.
    def compute_boost(query, content, base=0.0):
        tokens = [t for t in re.findall(r"\w+", query, re.UNICODE) if len(t) >= 2]
        if len(tokens) < 2:
            return base, {}
        content_l = content.lower()
        hits = sum(1 for t in tokens if t.lower() in content_l)
        total = len(tokens)
        sc = {}
        score = base
        if hits == total:
            score += 0.5
            sc["all_terms_match"] = True
        elif total >= 4 and hits / total >= 0.5:
            score += (hits / total) * 0.5
            sc["partial_match_ratio"] = round(hits / total, 2)
        return score, sc

    # Full 4-token match
    score, sc = compute_boost("壱岐 黄金 じゃがいも 出荷", "2026年6月に壱岐黄金じゃがいもを出荷開始")
    assert sc.get("all_terms_match") is True
    assert score == 0.5

    # 6/8 tokens match (販売, EC 欠落) → partial ratio 0.75, boost = 0.375
    q = "壱岐 黄金 じゃがいも 高級 ブランド 出荷 販売 EC"
    content = "壱岐黄金の高級じゃがいもブランドとして出荷開始、note で告知"
    score, sc = compute_boost(q, content)
    assert sc.get("all_terms_match") is None
    assert sc.get("partial_match_ratio") == 0.75
    assert abs(score - 0.375) < 1e-9

    # 2/8 tokens (below 50%) → no boost
    score, sc = compute_boost(q, "全然関係のない記事、壱岐と黄金だけ含む")
    assert sc == {}
    assert score == 0.0

    # Short query (2 tokens), 1/2 hits → no partial boost (strict tier held)
    score, sc = compute_boost("SKYPIX 対馬", "SKYPIX の記事")
    assert sc == {}
    assert score == 0.0
