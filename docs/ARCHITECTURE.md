# アーキテクチャ

## 全体構造

```
┌──────────────────────────────────────────────────────────────────┐
│ ユーザーの Mac                                                    │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 入口（複数）                                                │  │
│  │  - CLI (`bunshin ...`)                                      │  │
│  │  - Web UI (FastAPI, http://127.0.0.1:8000)                 │  │
│  │  - MCP サーバー (stdio, Claude Code / Desktop が呼ぶ)       │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                              │                                     │
│  ┌──────────────────────────▼─────────────────────────────────┐  │
│  │ コア機能                                                    │  │
│  │  - search.py: 意味検索                                      │  │
│  │  - chat.py: Ollama 経由のチャット                           │  │
│  │  - insights.py: 自動気づき生成                              │  │
│  │  - embeddings.py: FastEmbed (ONNX 多言語モデル)            │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                              │                                     │
│  ┌──────────────────────────▼─────────────────────────────────┐  │
│  │ ストレージ層 (storage.py)                                   │  │
│  │  - SQLite (~/.bunshin/data.db)                              │  │
│  │  - sqlite-vec (ベクトル検索)                                │  │
│  │  - records / records_vec / settings テーブル                │  │
│  └──────────────────────────▲─────────────────────────────────┘  │
│                              │                                     │
│  ┌──────────────────────────┴─────────────────────────────────┐  │
│  │ 取り込み層 (ingestion/)                                     │  │
│  │  - claude_history.py: ~/.claude/projects の .jsonl          │  │
│  │  - files.py: ローカル .md/.txt                              │  │
│  │  - gmail.py: IMAP via App Password                          │  │
│  │  - calendar.py: iCal URL fetch                              │  │
│  │  - line.py: LINE エクスポート                               │  │
│  │  - manual.py: 手動メモ                                      │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 自動化                                                      │  │
│  │  - launchd (毎時 update コマンドを実行)                     │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
       ↑                          ↑
       ↓                          ↓
   Ollama                    Claude / GPT / Gemini
   (ローカルLLM)              (クラウドLLM、MCP経由)
```

---

## データモデル

### `records` テーブル（全レコード共通）

```sql
CREATE TABLE records (
    id              TEXT PRIMARY KEY,         -- UUID
    source          TEXT NOT NULL,            -- "claude"/"gmail"/"file"/"manual"/"calendar"/"line"
    source_id       TEXT,                     -- 元データの識別子
    timestamp       INTEGER NOT NULL,         -- Unix epoch
    content         TEXT,                     -- 本文
    content_hash    TEXT,                     -- 重複検出 (SHA256 先頭16文字)
    metadata        TEXT,                     -- JSON
    file_path       TEXT,                     -- バイナリ実体への参照（あれば）
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL
);
```

### `records_vec` 仮想テーブル（sqlite-vec）

```sql
CREATE VIRTUAL TABLE records_vec USING vec0(
    record_id TEXT PRIMARY KEY,
    embedding FLOAT[384]  -- multilingual-MiniLM-L12-v2
);
```

### `settings` テーブル（KV ストア）

```sql
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
```

用途:
- `last_update_at`: 直近 update 実行時刻
- `gmail_last_date`: Gmail 差分取得用
- `claude_mtime:<path>`: Claude セッションごとの mtime キャッシュ
- `file_mtime:<path>`: ファイルごとの mtime キャッシュ

---

## ソース別の取り込み戦略

| ソース | 取り込み方式 | 差分検出 | チャンク粒度 |
|--------|------------|---------|------------|
| claude | jsonl 解析 + ターンチャンク | `mtime` キャッシュ | 1500文字単位 |
| gmail | IMAP SEARCH `(SINCE date)` | `gmail_last_date` | 1500文字単位 |
| file | rglob + mtime チェック | `file_mtime:<path>` | 1500文字単位 |
| calendar | iCal 全取得 + DELETE+INSERT | なし（idempotent） | イベント単位 |
| line | テキストパース + DELETE+INSERT | なし | 1500文字単位 |
| manual | 単発 INSERT | なし | 1レコード |

### 取り込みフロー（共通）

```
1. ソースから raw data 取得
2. 差分検出（mtime / timestamp など）
3. 既存 records 削除（同 source_id 対象）
4. チャンク化
5. records へ INSERT
6. 短文 (< 20文字) 以外を embed
7. records_vec へ INSERT
```

---

## 検索の仕組み

```python
def search(query, limit=10, sort="relevance", from_ts=None, to_ts=None):
    # 1. クエリを embed
    q_vec = fastembed.embed_query(query)
    
    # 2. sqlite-vec で近傍検索（過剰取得）
    SELECT v.record_id, v.distance, r.*
    FROM records_vec v
    JOIN records r ON r.id = v.record_id
    WHERE v.embedding MATCH ? AND v.k = ?     # k = limit * 6 (over-fetch)
      AND length(r.content) >= 20             # ノイズ除去
      AND r.timestamp BETWEEN ? AND ?         # 期間フィルタ
    ORDER BY v.distance  -- or r.timestamp
    LIMIT ?
```

### 検索戦略の判断ポイント

- **過剰取得 (k = limit × 6)**: 短文除外でも結果が足りるよう確保
- **min_content_length = 20**: 短文ノイズを実質除外
- **ソート切替**: 関連度（distance）/ 新しい順 / 古い順
- **期間フィルタ**: 今日/今週/今月/今年/全部

---

## チャット (Ollama) の仕組み

```python
def chat(query):
    # 1. 関連記憶を検索
    contexts = search(query, limit=5)
    
    # 2. システムプロンプト構築
    system = f"""
    あなたは個人記憶アシスタント「分身」です。
    過去文脈に該当情報が無い場合は『過去の記憶には見当たりません』
    と正直に答えてください。
    
    === 関連する過去文脈 ===
    {format_contexts(contexts)}
    === ここまで ===
    """
    
    # 3. Ollama にストリーミング送信
    POST http://localhost:11434/api/chat
    Body: { model, messages: [system, user], stream: true }
```

---

## MCP サーバーの仕組み

`bunshin mcp` は stdio で JSON-RPC を喋る MCP サーバーを起動。

提供ツール：

- `search_memory(query, limit, sort)`: 意味検索
- `recall_session(source_id, max_messages)`: セッション全文取得

Claude Code / Desktop は `.mcp.json` or `claude_desktop_config.json` で bunshin を登録 → 自動的にツールが追加される。

---

## なぜ非編集 install か（重要）

開発時は `pip install -e .`（editable）が普通。
だが分身は **`pip install .`（非編集）** を使う：

### 理由

- macOS Sandbox 制限：launchd や Claude Desktop は `~/Documents/` 配下を読めない
- editable install だと `~/.bunshin/venv/` から `~/Documents/.../src/bunshin/` を import する
- → launchd 経由で起動すると ImportError

### 対策

- 非編集 install で venv 内にコピーを持つ
- コード変更時：`~/.bunshin/venv/bin/pip install --force-reinstall --no-deps /path/to/bunshin`

---

## なぜ venv を `~/Documents/` に置かないか

同じ理由（macOS Sandbox）。

```
✅ ~/.bunshin/venv/          ← 動く
❌ ~/Documents/.../venv/     ← Sandbox で読めない
```

---

## なぜ multilingual-MiniLM か（埋め込みモデル選定）

| モデル | 次元 | サイズ | 日本語 | 採用？ |
|--------|------|-------|--------|--------|
| paraphrase-multilingual-MiniLM-L12-v2 | 384 | 220MB | ○ | ✅ |
| multilingual-e5-large | 1024 | 2.2GB | ◎ | △ DL重い |
| multilingual-mpnet-base | 768 | 1GB | ○ | △ DL重い |

→ Phase 0/1 は MiniLM（軽量・速い・十分）。
Phase 2 で e5-large に切替検討。

---

## なぜ Ollama か（オフライン LLM 選定）

| 候補 | 特徴 | 採用？ |
|------|------|--------|
| Ollama | モデル管理楽、HTTP API、Mac 最適化 | ✅ |
| llama.cpp 直 | 軽量だがセットアップ面倒 | △ |
| LM Studio | GUI あり、API も Ollama 互換 | △ 代替可 |
| MLX | Apple Silicon 最速だがエコシステム小 | × Phase 2 検討 |

---

## なぜ FastAPI + 単一 HTML か（Web UI 選定）

| 選択肢 | 特徴 | 採用？ |
|--------|------|--------|
| FastAPI + vanilla HTML | 単純、依存最小、保守楽 | ✅ |
| React + REST API | 機能リッチだが overkill | × |
| Streamlit | 速いが limited customization | × |
| Tauri | ネイティブだが Phase 2 | △ 後で |

→ Phase 1 までは vanilla で十分。Phase 2 で Tauri 化。

---

## 制限事項

### 既知の制限

- **編集者と launchd の整合性**: 開発時に editable install すると launchd が動かなくなる
- **Sandbox 起因**: Claude Desktop は `~/Documents/` 内 venv を読めない
- **モデル品質**: llama3.2:3b は幻覚が多い。qwen2.5:14b 推奨
- **チャンク跨ぎ**: 検索結果はチャンク単位、文の途中で切れることあり
- **画像非対応**: 添付画像、写真は未取り込み

### 将来の改善候補

- Phase 2: Tauri デスクトップアプリ化（ネイティブ感、配布可能）
- Phase 2: 知識グラフ（人名・場所・プロジェクトの関係性可視化）
- Phase 3: OSS 公開（GitHub）
- Phase 4: 暗号化バックアップ・デバイス間同期（Pro 版）
