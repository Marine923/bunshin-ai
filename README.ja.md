# 分身（Bunshin）

> **「自分が主役で、AI は取り替え可能な道具」になる、世界初の4条件AI**

[![Latest release](https://img.shields.io/github/v/release/Marine923/bunshin-ai)](https://github.com/Marine923/bunshin-ai/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)]()

ChatGPT・Claude が秘書なら、分身は **脳の延長**。
秘書は替えがきく。脳は替えがきかない。

---

## 4条件すべて満たす

| 条件 | 説明 | 実装 |
|------|------|------|
| **ローカル** | データは手元の Mac のみ | SQLite + sqlite-vec |
| **AI-Agnostic** | Claude/ChatGPT/Gemini/Llama 何でも繋がる | MCP プロトコル準拠 |
| **オフライン** | ネットが切れても動く | Ollama (qwen2.5:14b 等) |
| **オムニソース** | メール・ファイル・会話・メモ・写真・履歴・予定・音声 | 9種類の取り込み |

**この4条件全部入りは知る限り世界に存在しない**（2026-06時点）。

---

## なぜ重要か

いまの AI 製品は、あなたの記憶を各社のサービスに人質に取っています：

- ChatGPT は記憶機能を持つが、他のサービスへ持ち出せない
- Claude のメモリも Anthropic 圏内でだけ動く
- Mem0 / Letta などはクラウド型

ベンダーが料金を変える・サービスを停止する・あるいは単に乗り換えたい時、**蓄積した記憶ごと消える**。

分身は逆。記憶は手元の SQLite ファイルに住み、MCP を喋るどの LLM でも使える。Anthropic が明日消えても、あなたの記憶は生き残る。

---

## できること

### 🔍 何でも検索できる
ハイブリッド検索（意味 + キーワード）。日本語と英語。ソース・期間で絞り込み、クリックで会話全体を展開、バッジクリックで同じ会話内の他チャンクを引き出す。

### 💬 オフラインで分身と対話
ローカル LLM（Ollama）に過去記録を自動注入。返答には根拠の引用リンク付き。データは手元から出ません。

### 💡 自動「気づき」
放置中のプロジェクト、直近のカレンダー予定、最近触ったファイル、過去の AI が投げかけた未回答の質問。1 タブで朝の状況把握。

### 📅 タイムライン
全記録を日付 × ソースでグルーピング。「今日」「昨日」ラベル。ソース別件数ピル（💬 Claude / 📧 Gmail / 📓 メモ / 📷 写真 / 🌐 ブラウザ …）。ピルクリックで詳細展開、ホバーで全文展開。

### 🕸 知識グラフ
LLM 抽出の人物・組織・プロジェクト、特異性スコア付きの関係。

### 🔁 常に最新
ファイル監視で編集を秒で反映。launchd / systemd / cron で毎時同期。日次自動バックアップ（VACUUM INTO）。

### 🤖 どの AI からでも呼べる MCP
Claude Code、Claude Desktop、または MCP を喋るどんな AI からも `search_memory` と `recall_session` で記憶にアクセス可能。

---

## 取り込めるもの（9 ソース）

| ソース | 中身 | 場所 |
|--------|------|------|
| 💬 Claude | Claude Code / Claude Desktop の全会話 | `~/.claude/projects/**/*.jsonl` |
| 📧 Gmail | 過去 90 日のメール（以後は差分） | Gmail API + アプリパスワード |
| 📄 ファイル | `.md` / `.txt` / `.pdf` / `.docx` | 指定ディレクトリ配下 |
| 📓 Apple メモ | Notes.app の全ノート（AppleScript、FDA 不要） | macOS |
| 💌 iMessage / SMS | `chat.db` + 連絡先・グループ名結合 | macOS、FDA 必要 |
| 📷 写真 | EXIF（日付・GPS・カメラ）+ macOS Vision OCR（日英） | `~/Pictures` や任意ディレクトリ |
| 📷 写真.app ライブラリ | Photos.app の全 media item | macOS |
| 🌐 ブラウザ | Safari / Chrome / Arc の訪問履歴 | macOS |
| 📅 カレンダー | 直近 14 日（iCal URL から） | iCloud / Google など |
| 🔊 音声 | Whisper 文字起こし（3 バックエンド） | 任意の音声ファイル |
| 💭 手動 | `bunshin note "…"` or チャットで `覚えといて: …` | どこでも |

**スキャン PDF も OCR**：埋め込みテキストがない PDF は自動で macOS Vision に流される。名刺・見積書・領収書まで検索可能になります。

---

## クイックスタート

### Mac アプリで使う（推奨）

1. [Releases](https://github.com/Marine923/bunshin-ai/releases/latest) から最新 DMG をダウンロード：
   - **Apple Silicon (M1/M2/M3/M4)**: `Bunshin-x.y.z-arm64.dmg`
   - **Intel Mac**: `Bunshin-x.y.z.dmg`
2. DMG を開き、Bunshin を `/Applications` にドラッグ。
3. 初回起動：右クリック → 開く（quarantine 解除のため）。

アプリが初期設定を済ませて、裏で `bunshin web` を起動、UI がすぐ使えます。

### ソースから入れる

```bash
git clone https://github.com/Marine923/bunshin-ai.git
cd bunshin
python3.11 -m venv ~/.bunshin/venv
~/.bunshin/venv/bin/pip install -e .

# 初期化
~/.bunshin/venv/bin/bunshin init

# 何か入れる（Claude 履歴が最速の最初の取り込み）
~/.bunshin/venv/bin/bunshin import-claude
~/.bunshin/venv/bin/bunshin embed

# Web UI を開く
~/.bunshin/venv/bin/bunshin web      # → http://127.0.0.1:8000

# 設定診断
~/.bunshin/venv/bin/bunshin doctor
```

Gmail / Calendar / Ollama / MCP / 自動スケジューラの設定は [`docs/SETUP.md`](docs/SETUP.md) 参照。

---

## アーキテクチャ

```
┌──────────────────────────────────────────────────────────┐
│ 入口: CLI · Web UI · MCP サーバ · Electron アプリ        │
├──────────────────────────────────────────────────────────┤
│ コア: 検索 · チャット · 気づき · 知識グラフ              │
├──────────────────────────────────────────────────────────┤
│ ストレージ: SQLite + sqlite-vec  (~/.bunshin/data.db)    │
│ 埋め込み: intfloat/multilingual-e5-large (1024d, ONNX)   │
│ ハイブリッド検索: vector + FTS5 BM25 を RRF で統合        │
├──────────────────────────────────────────────────────────┤
│ 取り込み: Claude · Gmail · ファイル · メモ · iMessage    │
│           写真 · Photos.app · ブラウザ · カレンダー       │
│           音声 · 手動                                     │
└──────────────────────────────────────────────────────────┘
        ↑                                            ↑
    Ollama（オフライン）         Claude / GPT / Gemini（MCP 経由）
```

詳細は [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

---

## 実際の規模感

開発者の MacBook での実稼働例：

```
ソース        件数
─────────────  ────────
claude          約 2,400  会話ターン
gmail           約 1,650  メール
photos_app      約 2,700  写真（うち 1,113 件に GPS）
file              約 900  ドキュメント
browser           約 600  訪問
notes             約 490  Apple メモ
photo              約 99  ルース画像（OCR テキスト付）
manual              1
─────────────  ────────
合計           約 8,650  records
embedding      約 9,200  (1024 次元, e5-large)
```

写真 OCR で、DJI T25P の見積書一式（¥4,028,264、業者住所・項目内訳・振込口座まで）が完全に検索可能な状態で記憶されました。

---

## カスタマイズ：自分専用エンティティ

知識グラフを自分の業界・組織に合わせるには `~/.bunshin/entities.json` を作成：

```json
[
  {
    "name": "自社名",
    "type": "organization",
    "aliases": ["略称1", "略称2"],
    "description": "説明"
  },
  {
    "name": "東京",
    "type": "place"
  }
]
```

`bunshin graph rebuild` で既存記録に再リンク。

タイプ：`project` / `organization` / `person` / `place` / `tool` / `concept` / `topic`

---

## ドキュメント

- [`docs/SETUP.md`](docs/SETUP.md) — 初期セットアップ（Gmail / Calendar / Ollama / MCP / スケジューラ）
- [`docs/COMMANDS.md`](docs/COMMANDS.md) — 全 CLI コマンド早見表
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 内部構造と設計判断
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — 困った時の対処
- [`CHANGELOG.md`](CHANGELOG.md) — リリースノート

---

## ステータス

```
Phase 0  プロトタイプ                       ━━━━━━━━━━━━━━━━━━━━ 100%
Phase 1  MVP（検索 / チャット / 取り込み）   ━━━━━━━━━━━━━━━━━━━━ 100%
Phase 2  Mac ネイティブアプリ（Electron）   ━━━━━━━━━━━━━━━━━━━━ 100%
Phase 3  マルチソース取り込みの磨き込み     ━━━━━━━━━━━━━━━━━━━━ 100%   ← v0.3.x
Phase 4  Pro / Team 機能                   ░░░░░░░░░░░░░░░░░░░░   0%
```

### 既知の制約

- **macOS のみ**確認済み。Linux 用スケジューラ（`systemd --user` / `cron`）はあるが UI 含めての動作確認は未。Windows 未対応。
- **macOS 署名なし** — 初回起動は右クリック→開く、または `xattr -dr com.apple.quarantine /Applications/Bunshin.app`。
- **iMessage はフルディスクアクセス必要**。CLI 側で日本語ガイドが表示されます。
- **Photos.app の OCR** は `--with-ocr` でオプト・イン（各 item を Photos.app からエクスポートする必要があり遅いため）。
- **Whisper** バックエンドは別途 `pip install` が必要（デフォルトでは同梱していません）。

---

## ライセンス

MIT — [LICENSE](LICENSE) 参照。

---

## コントリビューション

バグ・機能要望は Issue で。PR 歓迎ですが、大きい変更は事前に Issue で相談してください。

---

## 謝辞

以下のプロジェクトの上に建っています：

- [SQLite](https://sqlite.org) + [sqlite-vec](https://github.com/asg017/sqlite-vec)
- [FastEmbed](https://github.com/qdrant/fastembed)（ONNX、torch 不要）
- [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- [Ollama](https://ollama.com)
- Anthropic の [MCP](https://modelcontextprotocol.io/) プロトコル
- [Electron](https://www.electronjs.org/) + [electron-builder](https://www.electron.build/)
- macOS Vision フレームワーク（OCR）
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)（このコードの 90% を書いてくれた）
