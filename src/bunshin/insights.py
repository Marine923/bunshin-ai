"""Generate daily insights from bunshin memory.

Surfaces:
  - Inactive projects (>7 days no mention)
  - Upcoming calendar events (next 14 days)
  - Recent manual notes
  - Pending decisions / questions (assistant ended with "?")
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from bunshin.search import search


def find_memory_dir() -> Optional[Path]:
    """Auto-detect Claude Code memory directory.

    Tries:
      1. Current working directory's Claude project (.claude/projects/<encoded-cwd>/memory)
      2. Environment variable BUNSHIN_MEMORY_DIR
      3. ~/.bunshin/memory if exists
    """
    import os
    env_dir = os.environ.get("BUNSHIN_MEMORY_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)

    cwd = Path.cwd().resolve()
    encoded = str(cwd).replace("/", "-")
    candidate = Path.home() / ".claude" / "projects" / encoded / "memory"
    if candidate.exists():
        return candidate

    fallback = Path.home() / ".bunshin" / "memory"
    if fallback.exists():
        return fallback

    # Scan all Claude projects for any memory dir (last resort)
    projects = Path.home() / ".claude" / "projects"
    if projects.exists():
        for p in projects.iterdir():
            if (p / "memory" / "MEMORY.md").exists():
                return p / "memory"
    return None


def parse_projects_from_memory() -> list[dict]:
    """Parse MEMORY.md to extract project list."""
    memory_dir = find_memory_dir()
    if not memory_dir:
        return []
    memory_path = memory_dir / "MEMORY.md"
    if not memory_path.exists():
        return []
    try:
        text = memory_path.read_text(encoding="utf-8")
    except OSError:
        return []

    projects = []
    for line in text.splitlines():
        line = line.strip()
        # Pattern: - [Name](file.md) — description
        m = re.match(r"^-\s+\[([^\]]+)\]\([^)]+\)\s*[—–\-]+\s*(.+)$", line)
        if m:
            projects.append({
                "name": m.group(1).strip(),
                "description": m.group(2).strip(),
            })
    return projects


def find_latest_record_for(conn: sqlite3.Connection, query: str) -> Optional[dict]:
    """Find newest record semantically matching `query`."""
    try:
        results = search(conn, query, limit=3, sort="newest", min_content_length=30)
        return results[0] if results else None
    except Exception:
        return None


def generate_insights(
    conn: sqlite3.Connection,
    section_limit: int = 6,
    inactive_threshold_days: int = 7,
) -> dict:
    """Generate insight sections."""
    now_ts = int(datetime.now().timestamp())
    now = datetime.now()

    out = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "inactive_projects": [],
        "upcoming_events": [],
        "recent_notes": [],
        "pending_questions": [],
        "recent_files": [],
        "watch_status": {},
        "setup_hints": [],
    }

    # Setup hints (oneliner suggestions for incomplete config)
    try:
        from bunshin.ingestion.calendar import load_url as _cal_url
        if not _cal_url():
            out["setup_hints"].append({
                "kind": "calendar",
                "message": "カレンダーURL未設定。「直近の予定」を有効にするには、Google Calendar 設定 → 統合 → iCal 非公開URL をコピーして、ターミナルで `bunshin setup-calendar URL` を実行。",
            })
    except Exception:
        pass
    try:
        from bunshin.ingestion.gmail import load_credentials as _gm_creds
        if not _gm_creds():
            out["setup_hints"].append({
                "kind": "gmail",
                "message": "Gmail未取り込み。メール記憶を有効にするには、`bunshin setup-gmail --email YOU@gmail.com` を実行（要 2FA + App Password）。",
            })
    except Exception:
        pass
    try:
        from bunshin.chat import check_ollama as _check_ol
        ok, models = _check_ol()
        if not ok or not models:
            out["setup_hints"].append({
                "kind": "ollama",
                "message": "Ollama未起動 or モデル未インストール。オフラインチャットを有効にするには `open /Applications/Ollama.app && ollama pull qwen2.5:14b`。",
            })
    except Exception:
        pass

    # ── 1. Inactive projects
    projects = parse_projects_from_memory()
    rows = []
    for p in projects:
        latest = find_latest_record_for(conn, p["name"])
        if not latest or not latest.get("timestamp"):
            continue
        days_ago = max(0, (now_ts - latest["timestamp"]) // 86400)
        if days_ago >= inactive_threshold_days:
            rows.append({
                "name": p["name"],
                "description": p["description"],
                "days_ago": days_ago,
                "last_seen": datetime.fromtimestamp(
                    latest["timestamp"]
                ).strftime("%Y-%m-%d"),
                "snippet": latest["content"][:250],
            })
    rows.sort(key=lambda x: -x["days_ago"])
    out["inactive_projects"] = rows[:section_limit]

    # ── 2. Upcoming calendar events
    cursor = conn.execute(
        """SELECT content, timestamp, metadata FROM records
           WHERE source = 'calendar'
             AND timestamp >= ? AND timestamp <= ?
           ORDER BY timestamp ASC
           LIMIT ?""",
        (now_ts, now_ts + 86400 * 14, section_limit),
    )
    for row in cursor.fetchall():
        meta = json.loads(row[2]) if row[2] else {}
        out["upcoming_events"].append({
            "summary": meta.get("summary", "") or row[0][:80],
            "start": meta.get("start", ""),
            "location": meta.get("location", ""),
            "timestamp": row[1],
        })

    # ── 3. Recent manual notes (last 7 days)
    seven_days_ago = now_ts - 86400 * 7
    cursor = conn.execute(
        """SELECT content, timestamp FROM records
           WHERE source = 'manual' AND timestamp >= ?
           ORDER BY timestamp DESC
           LIMIT ?""",
        (seven_days_ago, section_limit),
    )
    for row in cursor.fetchall():
        out["recent_notes"].append({
            "content": row[0][:300],
            "date": datetime.fromtimestamp(row[1]).strftime("%Y-%m-%d %H:%M"),
        })

    # ── 4. Recent file changes (surfaces the watcher's work)
    seven_days_ago = now_ts - 86400 * 7
    cursor = conn.execute(
        """SELECT DISTINCT source_id, MAX(timestamp) as ts
           FROM records
           WHERE source = 'file' AND timestamp >= ?
           GROUP BY source_id
           ORDER BY ts DESC
           LIMIT ?""",
        (seven_days_ago, section_limit),
    )
    for sid, ts in cursor.fetchall():
        if not sid:
            continue
        out["recent_files"].append({
            "path": sid,
            "name": sid.split("/")[-1] if "/" in sid else sid,
            "modified": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
        })

    # File-watcher status (best-effort — checks if the env / dir exists)
    import os
    watch_dir = (
        os.environ.get("BUNSHIN_WATCH_DIR")
        or str(Path.home() / "Documents")
    )
    out["watch_status"] = {
        "dir": watch_dir,
        "exists": Path(watch_dir).exists(),
    }

    # ── 5. Pending questions: recent assistant turns ending with "?"
    one_week_ago = now_ts - 86400 * 7
    cursor = conn.execute(
        """SELECT content, timestamp, metadata FROM records
           WHERE source = 'claude' AND timestamp >= ?
           ORDER BY timestamp DESC
           LIMIT 50""",
        (one_week_ago,),
    )
    for row in cursor.fetchall():
        content = row[0] or ""
        # Look for assistant question markers
        if any(p in content for p in ["か？", "ですか？", "ますか？", "?\n", "教えてください"]):
            # Skip if content is too short
            if len(content) < 80:
                continue
            out["pending_questions"].append({
                "content": content[:400],
                "date": datetime.fromtimestamp(row[1]).strftime("%Y-%m-%d %H:%M"),
            })
            if len(out["pending_questions"]) >= section_limit:
                break

    return out


def generate_llm_digest(
    conn: sqlite3.Connection,
    days: int = 7,
    model: Optional[str] = None,
) -> dict:
    """Use Ollama to summarize the past N days of records into a digest.

    Returns: {"digest": text, "model": ..., "covered_records": n, "error": str|None}
    """
    out: dict = {"digest": "", "model": None, "covered_records": 0, "error": None}

    try:
        from bunshin.chat import OLLAMA_HOST, check_ollama, pick_model
        import httpx
    except ImportError as e:
        out["error"] = f"imports failed: {e}"
        return out

    ok, available = check_ollama()
    if not ok or not available:
        out["error"] = "Ollama not available"
        return out

    chosen = model or pick_model(available)
    out["model"] = chosen

    now_ts = int(datetime.now().timestamp())
    since = now_ts - days * 86400

    cursor = conn.execute(
        """SELECT source, timestamp, content, metadata
           FROM records
           WHERE timestamp >= ? AND length(content) >= 50
           ORDER BY timestamp DESC
           LIMIT 200""",
        (since,),
    )
    rows = cursor.fetchall()
    out["covered_records"] = len(rows)
    if not rows:
        out["digest"] = "(過去 {} 日間に十分な記録がありません)".format(days)
        return out

    # Build a compact textual log for the LLM.
    blocks = []
    for src, ts, content, meta in rows:
        date = datetime.fromtimestamp(ts).strftime("%m-%d") if ts else "?"
        # truncate noisy content
        snippet = content[:400]
        blocks.append(f"[{date} {src}] {snippet}")
    log_text = "\n".join(blocks)[:14000]  # bound prompt

    prompt = (
        f"以下は過去 {days} 日間のユーザーの記録（メール・会話・ファイル）の抜粋です。"
        "ユーザーが「今週何があったか」「何を考えていたか」「今やるべきことは何か」を"
        "把握できる**簡潔な日本語サマリ**を作ってください。\n\n"
        "フォーマット：\n"
        "## このN日間のハイライト\n"
        "- 箇条書きで重要な出来事・決定（3-6項目）\n\n"
        "## 進行中のテーマ\n"
        "- 継続的に登場する話題、プロジェクト\n\n"
        "## 今やるべきこと\n"
        "- 記録から推測される未対応事項・締切（3-5項目）\n\n"
        "ルール：日付や固有名詞は記録から引用すること。"
        "推測で名前を作らないこと。\n\n"
        f"=== 記録 ===\n{log_text}\n=== ここまで ==="
    )

    try:
        r = httpx.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": chosen,
                "messages": [
                    {"role": "system", "content": "You write concise Japanese summaries."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
            timeout=180.0,
        )
        r.raise_for_status()
        out["digest"] = r.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        out["error"] = str(e)
    return out
