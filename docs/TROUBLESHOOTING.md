# トラブルシューティング

## インストール・実行

### Q. `bunshin: command not found`

PATH に venv のバイナリが入っていない。

```bash
# 直接フルパスで実行
~/.bunshin/venv/bin/bunshin status

# または alias 設定
echo 'alias bun=~/.bunshin/venv/bin/bunshin' >> ~/.zshrc
source ~/.zshrc
bun status
```

### Q. `ModuleNotFoundError: No module named 'bunshin'`

venv へのインストールが完了していない。

```bash
~/.bunshin/venv/bin/pip install --force-reinstall --no-deps /path/to/bunshin
```

### Q. インストール時に `ERROR: pyvenv.cfg ... Operation not permitted`

macOS Sandbox 制限。venv が `~/Documents/` 配下にあると、launchd や Claude Desktop から読めない。

**解決策**：venv を `~/.bunshin/venv/` に作り直し：

```bash
rm -rf /Users/YOU/Documents/path/to/.venv
/Users/YOU/.local/bin/python3.11 -m venv ~/.bunshin/venv
~/.bunshin/venv/bin/pip install -e /path/to/bunshin
```

---

## データ取り込み

### Q. `bunshin import-claude` で何も取り込まれない

確認：
1. `~/.claude/projects/` が存在するか
2. その配下に `.jsonl` ファイルがあるか

```bash
ls ~/.claude/projects/
find ~/.claude/projects -name "*.jsonl" | wc -l
```

### Q. `bunshin import-gmail` で `Login failed` エラー

App Password を使ってない可能性。**通常のパスワードは使えない**。

1. 2段階認証が有効か確認
2. [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) で生成
3. 16文字をそのまま貼り付け（スペースは取ってもOK）

### Q. App Password 画面に「お探しの設定は…利用できません」と出る

2段階認証 (2FA) が無効の可能性。

1. [https://myaccount.google.com/signinoptions/twosv](https://myaccount.google.com/signinoptions/twosv) で 2FA を有効化
2. 再度 App Passwords ページへ

Workspace アカウント（仕事用 Google）の場合、管理者制限で App Password が禁止されてる場合もある。
→ 個人 `@gmail.com` で試す。

### Q. `bunshin import-calendar` でカレンダーが取れない

iCal URL を確認。Google Calendar 個別カレンダーの「**カレンダーの非公開URL（iCal形式）**」を使う。
公開URLや埋め込みURLでは取れない。

---

## 検索・チャット

### Q. 検索結果が出てこない

```bash
bun status  # ベクトル化されてるか確認
```

Embeddings が Records より少ない場合：

```bash
bun embed
```

### Q. 検索結果が「お願いします」「OK」のような短文ばかり

古い実装の名残。最新版は 20文字未満を自動除外。
DB を掃除：

```bash
bun clean
```

### Q. `bunshin chat` で `Ollama not running`

Ollama を起動：

```bash
open /Applications/Ollama.app
# または
ollama serve
```

### Q. `bunshin chat` で `No Ollama models installed`

モデルをダウンロード：

```bash
ollama pull qwen2.5:14b  # 推奨（9GB、日本語強い）
# または軽量版
ollama pull llama3.2:3b  # 2GB、英語強い、日本語△
```

### Q. チャット応答に幻覚（存在しない日付・人物）が混じる

モデルサイズが小さすぎ。llama3.2:3b で起きやすい。

```bash
ollama pull qwen2.5:14b
bun chat "..." --model qwen2.5:14b
```

### Q. チャット応答で AI が「教えてください」と逆質問する

クエリが漠然としてる。具体的なプロジェクト名・送信元を含める：

❌ 「最近の重要なメール教えて」
✅ 「Sky MISSION からの最近のメール3件を時系列で要約して」

---

## MCP 連携

### Q. Claude Code で bunshin ツールが見えない

1. `.mcp.json` が プロジェクトディレクトリにあるか確認
2. `claude` を再起動

### Q. Claude Desktop で `MCP bunshin: Server disconnected`

macOS Sandbox 制限。`/Users/YOU/Documents/.../venv/` を指してると失敗。

**解決策**：venv を `~/.bunshin/venv/` に移動 + Claude Desktop config を更新：

```json
{
  "mcpServers": {
    "bunshin": {
      "command": "/Users/YOU/.bunshin/venv/bin/bunshin",
      "args": ["mcp"]
    }
  }
}
```

→ Claude Desktop ⌘+Q → 再起動。

### Q. MCP サーバーのログを見たい

Claude Desktop の場合：

```bash
tail -f ~/Library/Logs/Claude/mcp-server-bunshin.log
```

---

## 自動取り込み（launchd）

### Q. launchd が動いてるか確認したい

```bash
launchctl list | grep bunshin
```

PID が表示されていれば登録済み。

### Q. launchd の動作ログを見たい

```bash
tail -f ~/.bunshin/logs/update.out.log
tail -f ~/.bunshin/logs/update.err.log
```

### Q. launchd を一時停止したい

```bash
launchctl unload ~/Library/LaunchAgents/com.bunshin.update.plist
# 再開
launchctl load ~/Library/LaunchAgents/com.bunshin.update.plist
```

### Q. launchd を即時実行したい（テスト用）

```bash
launchctl kickstart -k gui/$UID/com.bunshin.update
```

---

## Web UI

### Q. http://127.0.0.1:8000 が開けない

サーバーが起動してない or 別ポートで動いてる。

```bash
lsof -i:8000   # 何か listen してるか
~/.bunshin/venv/bin/bunshin web   # 起動
```

### Q. スマホからアクセスしたい

サーバーをすべての NIC で listen させる：

```bash
~/.bunshin/venv/bin/bunshin web --host 0.0.0.0
```

→ Mac の IP を確認して `http://[Mac-IP]:8000`：

```bash
ipconfig getifaddr en0   # Wi-Fi の IP
```

**セキュリティ注意**: 同一LAN内の誰でもアクセスできる。Wi-Fi が安全な場合のみ。

---

## DB

### Q. DB を完全リセットしたい

```bash
rm ~/.bunshin/data.db
bun init
bun import-claude
bun import-files
bun import-gmail
bun import-calendar
bun embed
```

### Q. 特定の source だけ削除したい

```bash
~/.bunshin/venv/bin/python -c "
import sqlite3
from pathlib import Path
conn = sqlite3.connect(Path.home() / '.bunshin' / 'data.db')
conn.execute(\"DELETE FROM records WHERE source = 'gmail'\")
conn.commit()
print('Deleted')
"
```

### Q. DB のバックアップ

```bash
cp ~/.bunshin/data.db ~/.bunshin/data.db.backup
# 復元時は逆向きにコピー
```

---

## パフォーマンス

### Q. 検索が遅い

- DB サイズが GB 級に膨らんでないか確認 (`du -sh ~/.bunshin/data.db`)
- 古い短文を削除: `bun clean`
- インデックスは自動で作られているので追加対応不要

### Q. embed が遅い

- 初回はモデルダウンロード（〜220MB）
- 2回目以降は速い（〜30件/秒）
- それでも遅い場合は CPU を確認

---

## どうしても分からないとき

1. `bun status` で全体像確認
2. `tail ~/.bunshin/logs/update.{out,err}.log` で直近のログ
3. `~/.claude/projects/` や `~/.bunshin/data.db` の存在確認
4. GitHub Issue（OSS 公開後）
