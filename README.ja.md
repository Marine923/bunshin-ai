# 分身（Bunshin）

> **「自分が主役で、AIは取り替え可能な道具」になる、世界初の4条件AI**

ChatGPT・Claude が秘書なら、分身は **脳の延長**。
秘書は替えがきく。脳は替えがきかない。

---

## 4条件すべて満たす

| 条件 | 説明 | 実装 |
|------|------|------|
| **ローカル** | データは手元（PC/NAS/スマホ）のみ | SQLite + sqlite-vec |
| **AI-Agnostic** | Claude/ChatGPT/Gemini/Llama 何でも繋がる | MCP プロトコル準拠 |
| **オフライン** | ネット切れても動く | Ollama (qwen2.5:14b 等) |
| **オムニソース** | メール・ファイル・会話・カレンダー・チャット全部 | 6種類の取り込み |

**この4条件全部入りは知る限り世界に存在しない**（2026-06時点）。

---

## できること

- 🔍 **意味検索**: 過去の Claude 会話・メール・ファイルから自然言語で検索
- 💬 **オフラインチャット**: ローカル LLM で過去文脈つきの応答（ネット不要）
- 💡 **自動気づき**: 長期未活動プロジェクト・直近予定・未回答質問を自動抽出
- 📝 **手動メモ**: `覚えといて: ...` で何でも記憶に保存
- 🔄 **自動取り込み**: launchd で毎時、新しい会話・メール・ファイルを取り込み
- 🤖 **MCP連携**: Claude Code / Claude Desktop が分身を呼び出せる
- 🕸 **知識グラフ**: 人物・プロジェクト・組織を自動抽出、特異性スコアで真の関係を可視化

---

## クイックスタート

```bash
git clone https://github.com/Marine923/bunshin-ai.git
cd bunshin
python3.11 -m venv ~/.bunshin/venv
~/.bunshin/venv/bin/pip install -e .
~/.bunshin/venv/bin/bunshin init
~/.bunshin/venv/bin/bunshin import-claude
~/.bunshin/venv/bin/bunshin embed
~/.bunshin/venv/bin/bunshin web      # → http://127.0.0.1:8000
~/.bunshin/venv/bin/bunshin doctor   # 設定診断
```

詳細は [`docs/SETUP.md`](docs/SETUP.md) 参照。

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

- [`docs/SETUP.md`](docs/SETUP.md) — 初期セットアップ（Gmail / Calendar / Ollama / MCP / launchd）
- [`docs/COMMANDS.md`](docs/COMMANDS.md) — 全 CLI コマンド早見表
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — 内部構造と設計判断
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — 困ったときの対処

---

## ステータス

- **設計開始**: 2026-06-09
- **Phase 0 完了**: 2026-06-09（1日、設計予定1週間）
- **Phase 1 95%完了**: 2026-06-11（2日、設計予定1ヶ月）

```
Phase 0 ━━━━━━━━━━━━━━━━━━━━ 100% ✅
Phase 1 ━━━━━━━━━━━━━━━━━━━━ 95%  ✅
Phase 2 ━━━━━━░░░░░░░░░░░░░░ 30%  (ローカルLLMだけ前倒し)
Phase 3 ░░░░░░░░░░░░░░░░░░░░ 0%   (OSS公開)
Phase 4 ░░░░░░░░░░░░░░░░░░░░ 0%   (収益化)
```

既知の制約：
- **macOS のみ動作確認**（launchd 依存）。Linux/Windows は Phase 2 で
- テストなし
- 知識グラフは誤検知あり（特異性スコアで軽減）

---

## ライセンス

未定（Phase 3 で MIT または Apache 2.0 予定）
