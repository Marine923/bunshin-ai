"""User-facing settings persisted in the `settings` table.

This module wraps the existing KV settings table with a typed,
documented API that the Web UI / CLI can use to read and update
user preferences.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any


# Registry of all settings. Each entry is (key, default, type, description).
# Adding a new setting here is enough to expose it to the API.
SCHEMA: dict[str, dict[str, Any]] = {
    "notifications_enabled": {
        "default": True,
        "type": "bool",
        "label_ja": "システム通知を有効にする",
        "label_en": "Enable system notifications",
        "help_ja": "Insights からの重要な気づきを macOS 通知として表示します。",
        "help_en": "Show insights (inactive projects, upcoming events) as native notifications.",
        "section": "notifications",
    },
    "notify_interval_hours": {
        "default": 6,
        "type": "int",
        "min": 1,
        "max": 24,
        "label_ja": "通知の間隔（時間）",
        "label_en": "Notification interval (hours)",
        "help_ja": "Insights からの自動通知の頻度（時間）。",
        "help_en": "How often (in hours) to send insight notifications.",
        "section": "notifications",
    },
    "default_sort": {
        "default": "relevance",
        "type": "enum",
        "enum": ["relevance", "newest", "oldest"],
        "label_ja": "検索のデフォルトソート",
        "label_en": "Default search sort",
        "help_ja": "検索結果を最初にどの順序で並べるか。",
        "help_en": "Initial sort order for search results.",
        "section": "search",
    },
    "default_min_chars": {
        "default": 20,
        "type": "int",
        "min": 0,
        "max": 500,
        "label_ja": "検索結果の最小文字数",
        "label_en": "Min content length for search results",
        "help_ja": "これより短い記録は検索結果から除外します（ノイズ対策）。",
        "help_en": "Records shorter than this length are filtered out (noise reduction).",
        "section": "search",
    },
    "default_max_per_source": {
        "default": 1,
        "type": "int",
        "min": 0,
        "max": 20,
        "label_ja": "1ソースあたりの最大ヒット数",
        "label_en": "Max results per source",
        "help_ja": "同じ会話/ファイルから何件まで結果に含めるか。0 = 制限なし。",
        "help_en": "Cap on how many chunks from the same source_id appear. 0 = no cap.",
        "section": "search",
    },
    "chat_context_limit": {
        "default": 5,
        "type": "int",
        "min": 0,
        "max": 20,
        "label_ja": "チャットの過去記憶参照件数",
        "label_en": "Chat context size",
        "help_ja": "チャット応答時に AI が参照する過去記憶の件数。",
        "help_en": "Number of memory records loaded into chat context.",
        "section": "chat",
    },
    "chat_preferred_model": {
        "default": "auto",
        "type": "string",
        "label_ja": "優先するチャットモデル",
        "label_en": "Preferred chat model",
        "help_ja": "Ollama のモデル名。`auto` で自動選択。",
        "help_en": "Ollama model name. Use 'auto' for automatic selection.",
        "section": "chat",
    },
}


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )"""
    )


def get(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    """Get a setting value, parsed to its declared type."""
    _ensure_table(conn)
    cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    schema = SCHEMA.get(key)
    if not row:
        return schema["default"] if schema else default
    raw = row[0]
    if raw is None:
        return schema["default"] if schema else default
    if not schema:
        return raw
    t = schema["type"]
    try:
        if t == "bool":
            return raw.lower() in ("1", "true", "yes", "on")
        if t == "int":
            return int(raw)
        if t == "float":
            return float(raw)
        if t == "json":
            return json.loads(raw)
        return raw
    except (ValueError, json.JSONDecodeError):
        return schema["default"]


def set_value(conn: sqlite3.Connection, key: str, value: Any) -> None:
    """Set a setting value. Coerces booleans/ints/json to their string form."""
    _ensure_table(conn)
    schema = SCHEMA.get(key)
    if schema:
        t = schema["type"]
        if t == "bool":
            raw = "true" if bool(value) else "false"
        elif t == "int":
            raw = str(int(value))
        elif t == "float":
            raw = str(float(value))
        elif t == "json":
            raw = json.dumps(value, ensure_ascii=False)
        elif t == "enum":
            if value not in schema["enum"]:
                raise ValueError(f"value must be one of {schema['enum']}")
            raw = str(value)
        else:
            raw = str(value)
    else:
        raw = str(value)
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, raw),
    )
    conn.commit()


def all_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return current values for every known setting, with current = default merge."""
    out: dict[str, Any] = {}
    for key in SCHEMA:
        out[key] = get(conn, key)
    return out


def settings_schema() -> dict[str, Any]:
    """Expose the schema (for the Web UI to render the form)."""
    return SCHEMA
