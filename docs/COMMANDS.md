# コマンド早見表

すべてのコマンドは `~/.bunshin/venv/bin/bunshin` 経由で実行（または alias 推奨）。

## エイリアス推奨

`~/.zshrc` or `~/.bashrc` に追加：

```bash
alias bun='~/.bunshin/venv/bin/bunshin'
```

以降、すべて `bun` で OK。

---

## 初期化・確認

### `bunshin init`
DB を初期化（`~/.bunshin/data.db`）。冪等、何度実行してもOK。

```bash
bun init
```

### `bunshin status`
記憶の総数、ソース別件数、ベクトル化済件数を表示。

```bash
bun status
```

---

## 取り込み（手動）

### `bunshin import-claude [PATH]`
Claude Code 履歴を取り込み。デフォルトは `~/.claude/projects`。

```bash
bun import-claude              # デフォルトパス
bun import-claude /other/path  # 別のパス
bun import-claude -v           # 詳細ログ
```

差分検出：jsonl の mtime が変わったセッションのみ再処理。

### `bunshin import-files [PATH] [--ext .md] [--force]`
ローカル `.md` / `.txt` ファイルを取り込み。

```bash
bun import-files                                       # ~/Documents/Seiyo/ob
bun import-files ~/Documents/notes                     # 別フォルダ
bun import-files --ext .md --ext .txt --ext .markdown # 拡張子指定
bun import-files --force                               # 変更検出を無視して全部再取り込み
```

### `bunshin import-gmail [--limit N] [--initial-days 90] [-v]`
Gmail を取り込み。事前に `setup-gmail` 必要。

```bash
bun import-gmail              # 全件（初回90日、以降差分）
bun import-gmail --limit 100  # 最新100件のみ
bun import-gmail --initial-days 30  # 初回30日に短縮
bun import-gmail -v           # 詳細
```

### `bunshin import-calendar [--url URL]`
カレンダーを取り込み。事前に `setup-calendar` 必要。

```bash
bun import-calendar                    # 保存済みURL
bun import-calendar --url "https://..." # 別のURL
```

### `bunshin import-line PATH`
LINE エクスポート（テキスト）を取り込み。

```bash
bun import-line "/path/to/[LINE] トーク履歴.txt"
```

### `bunshin note "CONTENT" [--tag TAG]`
手動メモを追加。即時に埋め込みも実施。

```bash
bun note "来週火曜10時、漁協ミーティング"
bun note "壱岐黄金 5kg ロゴ印刷確定" --tag iki_gold --tag decision
```

---

## 自動取り込み

### `bunshin update [--quiet] [--no-files]`
Claude＋ファイル＋Gmail＋カレンダーを差分取り込み + 自動embed。
launchd で毎時実行される。

```bash
bun update           # 全部取り込み（詳細出力）
bun update --quiet   # 1行サマリーのみ（cron用）
bun update --no-files # ファイル取り込みスキップ
```

---

## 検索・閲覧

### `bunshin search "QUERY" [-n N] [--full]`
意味検索（CLI）。

```bash
bun search "壱岐黄金の進捗"
bun search "ドローン" -n 20
bun search "ク エ リ" --full  # 全文表示
```

### `bunshin insights`
自動気づき（長期未活動・直近予定・手動メモ・未回答質問）を表示。

```bash
bun insights
```

---

## チャット

### `bunshin chat "QUERY" [--model MODEL]`
Ollama 経由でオフラインチャット。

```bash
bun chat "壱岐黄金の現状を要約して"
bun chat "..." --model llama3.2:3b  # モデル指定
bun chat "..." --model qwen2.5:14b  # 高品質
```

---

## サーバー類

### `bunshin web [--host HOST] [--port PORT]`
Web UI（FastAPI + ブラウザ）を起動。

```bash
bun web
bun web --host 0.0.0.0 --port 8080  # 全インターフェースで listen
```

### `bunshin mcp`
MCP サーバー（stdio）を起動。
Claude Code / Desktop の設定から自動的に呼び出される。**手動実行不要**。

---

## メンテナンス

### `bunshin embed`
未ベクトル化レコードを embed。

```bash
bun embed
```

### `bunshin clean [--min-length N] [--dry-run]`
N文字未満の短文レコードを削除。

```bash
bun clean --dry-run            # 削除予定件数のみ確認
bun clean                      # 20文字未満を削除（デフォルト）
bun clean --min-length 30      # 30文字未満を削除
```

### `bunshin reindex`
全 Claude 会話を強制的にチャンク再構築 + 再embed。
チャンクサイズ変更時などに使用。**通常は不要**。

```bash
bun reindex
```

---

## 認証情報セットアップ

### `bunshin setup-gmail --email EMAIL`
Gmail の App Password を保存。`~/.bunshin/gmail.json` に格納（chmod 600）。

```bash
bun setup-gmail --email you@gmail.com
# パスワード入力プロンプト
```

### `bunshin setup-calendar URL`
カレンダーの iCal URL を保存。`~/.bunshin/calendar.json` に格納。

```bash
bun setup-calendar "https://calendar.google.com/calendar/ical/..."
```

---

## デフォルトパス一覧

| 項目 | パス |
|------|------|
| データベース | `~/.bunshin/data.db` |
| Gmail認証 | `~/.bunshin/gmail.json` (chmod 600) |
| カレンダー URL | `~/.bunshin/calendar.json` (chmod 600) |
| 自動更新ログ | `~/.bunshin/logs/update.{out,err}.log` |
| venv | `~/.bunshin/venv/` |
| 埋め込みモデルキャッシュ | `~/.cache/huggingface/` |
| Ollama モデル | `~/.ollama/models/` |
| Claude Code 履歴ソース | `~/.claude/projects/` |
| ファイル取り込みデフォルト | `~/Documents/Seiyo/ob/` |
