# セットアップガイド

分身を最大限活用するための初期セットアップ手順。
全部やる必要はない、必要な機能だけ拾ってください。

---

## 必須：基本セットアップ

### 1. Python 3.10+ をインストール

```bash
# macOS Homebrew
brew install python@3.11
```

### 2. venv 作成 + 分身インストール

**重要**: venv は `~/.bunshin/venv/` に作る（macOS Sandbox 回避のため）。

```bash
python3.11 -m venv ~/.bunshin/venv
~/.bunshin/venv/bin/pip install --upgrade pip
~/.bunshin/venv/bin/pip install -e /path/to/bunshin
```

### 3. データベース初期化

```bash
~/.bunshin/venv/bin/bunshin init
```

→ `~/.bunshin/data.db` が作成される。

### 4. Claude Code 履歴を取り込み

```bash
~/.bunshin/venv/bin/bunshin import-claude
~/.bunshin/venv/bin/bunshin embed
~/.bunshin/venv/bin/bunshin status
```

初回は埋め込みモデル（約 220MB）をダウンロード。

### 5. Web UI を起動

```bash
~/.bunshin/venv/bin/bunshin web
```

→ ブラウザで http://127.0.0.1:8000 を開く。

---

## オプション：Gmail 取り込み

### 前提
- Google アカウントで **2段階認証 (2FA) が有効**であること

### 手順

1. **App Password を生成**
   - [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   - 名前「Bunshin」で生成
   - 16文字のパスワードをコピー（スペース含む可）

2. **bunshin に登録**

   ```bash
   ~/.bunshin/venv/bin/bunshin setup-gmail --email you@gmail.com
   # パスワード入力プロンプト → App Password 貼り付け
   ```

3. **取り込み**

   ```bash
   ~/.bunshin/venv/bin/bunshin import-gmail -v
   ```

初回は過去90日分のメールを取得。以降は launchd が差分自動取得。

---

## オプション：カレンダー取り込み

### 手順

1. **iCal URL を取得**
   - [Google Calendar](https://calendar.google.com) を開く
   - 左の「マイカレンダー」→ 該当カレンダーの「︙」→「設定と共有」
   - 一番下の「**カレンダーの非公開URL（iCal形式）**」をコピー
   - **このURL は秘密**（流出すると予定が読まれる）

2. **bunshin に登録**

   ```bash
   ~/.bunshin/venv/bin/bunshin setup-calendar "コピーしたURL"
   ```

3. **取り込み**

   ```bash
   ~/.bunshin/venv/bin/bunshin import-calendar
   ```

以降は launchd が毎時自動取得。

---

## オプション：Ollama（オフライン LLM チャット）

### 手順

1. **Ollama インストール**

   ```bash
   brew install --cask ollama-app
   open /Applications/Ollama.app
   ```

2. **モデルダウンロード**

   軽量・速い（2GB）：
   ```bash
   ollama pull llama3.2:3b
   ```

   日本語強い・実用品質（9GB）：
   ```bash
   ollama pull qwen2.5:14b
   ```

3. **チャット**

   ```bash
   ~/.bunshin/venv/bin/bunshin chat "壱岐黄金の現状を要約して"
   ```

   または Web UI の「💬 チャット」タブ。

---

## オプション：MCP 連携（Claude Code / Desktop）

### Claude Code（プロジェクトスコープ）

プロジェクトディレクトリに `.mcp.json` を配置：

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

→ Claude Code 起動時に自動認識（初回は許可を聞かれる）。

### Claude Desktop（全プロジェクト）

`~/Library/Application Support/Claude/claude_desktop_config.json` を編集：

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

→ Claude Desktop を ⌘+Q → 再起動。

---

## オプション：自動取り込み（毎時）

毎時、Claude会話＋ファイル＋Gmail＋カレンダー を自動取り込み。
OS 自動検出で、Mac/Linux どちらでも同じコマンド：

```bash
bunshin install-scheduler
```

### 自動検出される仕組み

| OS | 使われる仕組み |
|----|--------------|
| macOS | `launchd` user agent (`~/Library/LaunchAgents/com.bunshin.update.plist`) |
| Linux + systemd | `systemctl --user` timer + service |
| Linux + cron のみ | `crontab` エントリ |

### ログ確認

すべてのプラットフォーム共通：

```bash
tail -f ~/.bunshin/logs/update.out.log
```

### 解除

```bash
bunshin uninstall-scheduler
```

### 状態確認

```bash
bunshin doctor
# → 「自動更新: macos で毎時実行中」のような行を確認
```

### 手動セットアップ（任意、上記が動かない場合）

#### macOS

```bash
mkdir -p ~/.bunshin/logs
# bunshin install-scheduler が ~/Library/LaunchAgents/ に plist を生成し
# launchctl load します。中身を見たい場合は plist を直接確認。
launchctl list | grep bunshin
```

#### Linux + systemd

```bash
# bunshin install-scheduler が以下を生成・有効化します:
# ~/.config/systemd/user/bunshin-update.{service,timer}
systemctl --user status bunshin-update.timer
journalctl --user -u bunshin-update.service
```

#### Linux + cron のみ

```bash
# bunshin install-scheduler が crontab に追記します。
crontab -l | grep bunshin
```

---

## オプション：LINE 取り込み

1. LINE アプリ → トーク → 設定（⚙）→ **トーク履歴を送信** → テキスト保存
2. Mac に転送（AirDrop など）
3. ターミナルで：

   ```bash
   ~/.bunshin/venv/bin/bunshin import-line "/path/to/[LINE] トーク履歴.txt"
   ```

差分取得には対応してないので、定期的にエクスポートしてください。

---

## セットアップ完了の確認

```bash
~/.bunshin/venv/bin/bunshin status
```

期待される出力：

```
Source        Records
claude        2000
gmail         1500
file          400
manual        5
calendar      30
line          200
Total         4135
Embeddings    4100
```
