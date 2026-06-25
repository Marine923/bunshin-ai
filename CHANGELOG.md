# Changelog

All notable changes to Bunshin are documented in this file. The format is
roughly [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.19] - 2026-06-25

第 15 回レビュー (両レビュアー 100+ 回触り) の致命 4 + 中度 3 を消化。

### Fixed — 🚨 関連エンティティに「undefined回共起」表示
- 玄人レビュー指摘: API は `weight` を返すが UI が
  `r.co_occurrences` を読んでいた。1 行修正 + `toLocaleString()`。

### Fixed — 🚨 関係性タブのエンティティ一覧で noise 未除外
- UI が `/api/entities` をオプション無しで叩いていた → note (1185
  件) が 1 位に。`?exclude_noisy=true&with_sources=true&limit=500`
  に変更、MCP `list_top_entities` と同じ結果に揃った。

### Fixed — 🚨 チャット履歴 UI に `hello/hi/test` が残る
- `/api/chat/sessions` に `min_user_chars=8` (デフォルト) と
  `include_empty=False` クエリパラメータ追加。短い greeting と
  空セッションは默認で隠れる。MCP `get_recent_chat` の挙動と一致。

### Fixed — Insights の hero card に `[assistant]` プレフィックス
- 表示時に `stripRolePrefix()` ヘルパーで `[user]/[assistant]/[tool]`
  接頭辞を除去 (ingest の harness scrub と相補)。

### Fixed — `describe` JSON parse 散発失敗
- 小型ローカル LLM (llama3.2:3b) が生成した text に制御文字
  (`\x01`〜`\x08`) が混入 → JSON 厳格モードでパース失敗。
  サーバ側で description / candidates / reasoning を sanitize。

### Changed — 検索結果カードのデフォルト折りたたみ
- 1 結果あたり長文 PDF/Claude transcript が縦に数十行 → 2 件目に
  辿り着くのに 20 スクロール、の UX 問題を解消。
- `.result-content` に `max-height: 180px` + 下部 fade + 「もっと
  見る ▾」ボタン (280 文字超のときのみ表示)。

### Changed — 検索ヘッダーを sticky 化
- 検索バー + ソート + ソース chip を `position: sticky; top: 0;` の
  ラッパーに格納。スクロールしても画面上部に残り、再検索時に
  トップへ戻る必要なし。

## [0.8.18] - 2026-06-25

### Fixed — 🐛 関係性のセッション内共起バイアス
- 玄人レビュー指摘: 「壱岐島」の関連 Top10 が Sequoia / X/Twitter /
  Product Hunt / a16z などに支配されていた。これらは dj-engine の
  Claude 1 セッションが大量 chunks を生成 → 全 chunk に両エンティティ
  が含まれる → `COUNT(*)` が水増しされる構造バグ。
- `entity_relations` の SQL を `COUNT(*)` → `COUNT(DISTINCT
  r.source_id)` に修正:
  - 1 セッションで何回共起しても 1 カウント
  - 修正後の壱岐島 Top1 が **ドローン (weight=155)** に変わった ✅
  - 「あなたの本当の関係性」(ドローン会社 / 農家 / リーフボール) が
    浮上、セッション偽装組は降格。

### Fixed — `learning_rules.applied_count` を既存 rule にも backfill
- v0.8.13 で rollup 追加したが forward-only だった。3,961 件 hidden
  なのにダッシュボードでは 0 のまま。
- 起動時 migration `learning_count_backfill_v0_8_18` で各 rule の
  実 hidden 数を SQL で再集計し直す。

### Added — `describe` の失敗ソース可視化
- マルチソース調査で hit しなかったソース (Wikipedia 該当なし、
  公式サイト推測失敗 等) を `failed_sources` で返す。
- UI で「✓ 採用」「✗ Wikipedia (no result)」のように成功/失敗を
  両方明示。「複数ソース調べました」と謳って 1 件しか出ないと
  「あれ?」となる UX を解消。

## [0.8.17] - 2026-06-25

### Changed — エンティティ説明を **マルチエージェント・マルチソース** 化
- ユーザー指摘:「Wikipedia だけじゃ弱い。いろんな人がいろんな場所を
  調べて最適解を出すイメージ」
- 5 つのソースを **並列で同時調査** (ThreadPoolExecutor):
  1. **Wikipedia (JA/EN)** — 既存。disambiguation も extract を渡す
  2. **DuckDuckGo Instant Answer** — 無料・無認証
  3. **公式サイト推測** — entity 名から `.com / .co.jp / .jp` を試行、
     meta description + title を取得
  4. **Anthropic Claude API** — 設定タブに API キー入力欄追加
  5. **ローカル LLM (qwen2.5:14b 等)** — ユーザー記録のみ参照
- 4-5 つの候補 description を集めて **judge agent** (Claude 優先、
  なければローカル LLM) が JSON で最良を選定:
  ```json
  {"description": "...", "chosen_source": "Wikipedia (ja)", "reasoning": "..."}
  ```
- UI: 「4 つのソース (Wikipedia / DuckDuckGo / 公式サイト / Claude)
  を並列調査中…」進捗 → 結果 + judge 名 + 採用ソース + 全候補
  (折りたたみ表示で個別確認可)。

### Added — Anthropic API キー設定
- 設定タブに新セクション「外部 AI」 + `anthropic_api_key` (secret type)
- `describe_enable_web` toggle (Web 参照を完全 OFF にできる)
- secret 型の安全性:
  - GET `/api/settings` は API キーを **`true/false`** に置き換えて返す
    (生キーは HTTP に乗せない)
  - UI は password input + 「保存済み」placeholder
  - 空欄保存は無視 (既存キー上書きしない)
- プライバシー: Wikipedia / DDG / 公式サイト / Claude には **entity
  名のみ** 送信。記録本文は一切送らない。

## [0.8.16] - 2026-06-25

### Fixed — 🚨 AI 説明が幻覚 (note を「ユーザーが記録した記述」と説明)
- ユーザー指摘:「note は文章投稿アプリ。AI が嘘ついたら誰も使わ
  なくなる」。v0.8.15 はローカル LLM (3b モデル) だけで合成 →
  小さいモデルは note.com を知らないので捏造していた。
- **修正**: Wikipedia 日本語 API (fallback: 英語) で entity 名を
  まず引く → その正確な定義 + ユーザー記録 snippet を LLM が
  ブレンドする方式に変更。
  - Wikipedia ヒットなし → LLM は **「詳細不明」と書く** よう指示
  - disambiguation (`note` 等) → 「同名複数あり、文脈で判定して」と
    LLM に伝える
  - organization type なら `{name} (企業)` `{name}株式会社` も試す
- 送信するのは **entity 名のみ** (記録本文は送らない)。プライバシー
  原則は維持。

### Changed — 描写 UI に出典リンク + 「やり直し」ボタン
- 生成された description の下に小さく **「ソース: Wikipedia (ja) ・
  qwen2.5:14b ・ 6 件の記録」** を表示。
- 「↻ やり直し」ボタンで再生成可能 (Wikipedia が更新されたとき用)。

## [0.8.15] - 2026-06-25

### Added — エンティティ詳細に「AI に説明させる」ボタン
- ユーザー実機指摘 v0.8.14 直後:「記憶の中から見つけてきて使い方を
  見せても、根本のこれが何かはわからない。AI 自身の言葉で説明させて」
- 新エンドポイント `POST /api/entities/{id}/describe`:
  - 該当エンティティの全 mention records (上位 8 件、文字数長い順) を
    pick light model (qwen2.5:14b 推奨) に渡す
  - 「2〜3 行の日本語で、ユーザーの文脈と一般知識をブレンドして説明」
    と prompt
  - 生成結果を `entities.description` に永続保存 → 次回開いた時は
    即表示 (再生成不要)
- UI: description が `(LLM 抽出)` placeholder のとき
  「✨ AI に説明させる」ボタン表示 → クリックで生成 → 完了後 inline
  に description を差し込む (モデル名 + 使用記録数のフッター付き)。

## [0.8.14] - 2026-06-25

### Changed — 関係性タブの右パネルに「これ何だっけ?」セクション
- ユーザー実機指摘:「中心の Native Instruments が何か思い出せない。
  関連エンティティを並べてくれてもそもそも本人が分からない」
- 改善:
  - description が `(LLM 抽出)` プレースホルダーのときは **非表示**
  - 新セクション **「あなたの記録での登場」** を追加:
    - **初出** (日付 + ソース + 抜粋 280 字)
    - **最新** (日付 + ソース + 抜粋、初出と違う record の場合のみ)
    - 計 N 件で言及
  - `/api/entities/{id}` のレスに `first_seen` フィールド追加
- 「関連エンティティだけ並べる」UI から、「**自分の記録を読み返して
  自己想起する**」UI へ。

## [0.8.13] - 2026-06-25

第 13 回レビューの 3 件 + 残骸 cleanup。

### Fixed — `[queue-operation]` 行頭タグを `[user]` に正規化
- Claude harness 内部の queue marker が chat の context に
  `[queue-operation] OK` として surface していた。
- `_strip_harness_noise` の冒頭で `[queue-operation] ` → `[user] `
  に置換。今後の ingest + 既存 record 両方に効く。

### Fixed — 孤立した `</task-notification>` 閉じタグの除去
- `chunk_messages` が wrapper を跨いで chunk を切ると、closer だけが
  次 chunk の冒頭に残る。10 件残存していたパターンを
  `_SKIP_LINE_RES` に `</task-notification>` / `</user-prompt-submit-hook>`
  単独行マッチ追加で消す。

### Fixed — `learning_rules.applied_count` が永久に 0
- SNS preset 適用時、各 rule が hide した record 数を
  `learning_rules.applied_count` に rollup していなかった。
- 学習ダッシュボード上で「このルールが何件 hide しているか」が
  ずっと 0 表示 → 実数 (例: `mail.note.com → 1184 件`) に。

### Changed — `memory_diff` で 7日窓に新規エンティティが無い時の UI
- entity extraction はバッチ実行のため、短い window では空配列が
  返ることが多い。空 `<ul>` の代わりに：
  > 「この期間に **初登場** のエンティティはありません」
  > 「（エンティティ抽出はバッチ実行のため、最近の ingest は
  >    まだ反映されていない場合があります）」

### Migration — `harness_noise_v0_8_13`
- 上記 2 つの新パターン (queue-op 正規化 + 孤立 closer) を既存
  records に再適用。

## [0.8.12] - 2026-06-24

### Fixed — 🐛 ライトモードでチャット応答の **太字** が白く消える
- `.chat-msg strong` と `.chat-msg .md-h` に `color: #fff` がハード
  コードされており、**ライトモード（白背景）で白文字 = 透明**
  状態だった。LLM が回答に `**2026年6月〜7月**` のような太字
  markdown を含めると、その箇所だけスクリーンショットで空白に見える。
- 修正: `color: var(--text-1)` (テーマ追従) に変更。ダークモードでも
  従来通り白く表示される。
- ユーザーが実機スクショで発見:「壱岐黄金プロジェクトの初出荷予定は
  ___ です」と日付が空白に。

## [0.8.11] - 2026-06-24

第 12 回レビュー: 致命 `re.MULTILINE` 欠落 + 中度 3。

### Fixed — 🚨🚨🚨 `_SKIP_LINE_RES` の `re.MULTILINE` 欠落
- v0.8.8〜v0.8.10 で 3 回 migration を走らせたが、regex に
  `re.MULTILINE` フラグが無く、`^` が "start of STRING" だけに
  マッチ → 多くの records が「ゲート check で即 return」されて
  silently no-op していた。
- 素人レビュー 12 が再現テスト付きで指摘:
  ```python
  text = "[user] hi\n<task-notification>..."
  pattern.search(text)  # → None (BUG)
  ```
- **修正**: 全 7 パターンに `re.IGNORECASE | re.MULTILINE` 追加。
- 私の手元で再確認:
  ```
  input : '意味のある最初の行\n[user] something else\n[queue-operation] <task-notification>\n...'
  out   : '意味のある最初の行\n[user] something else\n[user] 本物のメッセージ'
  ```
- 起動時 migration `harness_noise_v0_8_11` で 1,148 件 (玄人計測)
  の汚染レコードを再 scrub。

### Fixed — `FastAPI(title=..., version=...)` ハードコード `0.1.0`
- `/openapi.json` が `info.version: "0.1.0"` を返していた。
- `bunshin.__version__` を渡すよう修正。

### Fixed — `sort=newest` / `sort=oldest` が `limit ≥ 5` で壊れる
- hybrid retrieval の「wider candidate pool」(`scored[:max(limit*2,20)]`)
  が trim 後の最終 results に sort されないまま return されていた。
- 関数末尾で `if sort == "newest": results.sort(...)` の最終
  sort pass を追加。

### Added — `GET /api/records/{record_id}` (API 対称性)
- `DELETE` だけ存在していて `GET` が無かったので追加。
- 外部 API 利用者が特定 record を ID で取得できるように。

## [0.8.10] - 2026-06-24

第 11 回レビュー: 致命 typo 1 + 中度 3 + ドキュメント 1。

### Fixed — 🐛 `max → min` typo で rerank cap が limit≥8 で無効化
- v0.8.9 で `results[: max(limit, RERANK_INPUT_CAP)]` と書いたが、
  これは **「少なくとも limit 件 rerank する」** という逆の意味に
  なっており、`limit=20` のとき 20 件全て cross-encode で 10 秒
  に逆戻りしていた。
- `min()` に変更。`limit=20` の検索が ~10s → ~2.5s に。
- 玄人レビュー: 「設計者の意図は明らかに min。タイポと思われる」
  ← その通りでした。

### Fixed — 🐛 `get_today_hero` が user_role.md を誤検知
- MEMORY.md には `user_role.md` (プロフィール) や
  `feedback_*.md` (作業指針) も含まれるが、これらは「動かない
  もの」なので `stale_project` 判定すべきではない。
- `_NON_PROJECT_FILE_PREFIXES = ("user_", "feedback_", "entity_")` と
  `_NON_PROJECT_NAME_HINTS = ("プロフィール", "ユーザー", …)` で
  除外。「『ユーザーのプロフィール』が 13 日動いてません」が
  消える。

### Fixed — harness_noise regex が `[user]` 接頭辞を見逃し
- v0.8.9 の `_SKIP_LINE_RES` は `[queue-operation] <task-notification>`
  だけ match していたが、Claude history の chunk は実際には
  `[user] <task-notification>` / `[assistant] <…>` のロール接頭辞
  付きで保存されている → 141 件取りこぼし。
- パターンを `\[?(user|assistant|tool|queue-operation)\]?` に拡張、
  `<output-file>` も追加。
- 起動時 migration `harness_noise_v0_8_10` で既存 records を
  もう一度 scrub。

### Docs
- `README.ja.md`: 初回 backfill 中に RSS ~15 GB まで一時膨張する
  ことを追記。

## [0.8.9] - 2026-06-24

第 10 回レビュー: メモリ 11.9 GB 問題 + rerank 7.5 秒 + 残課題 4 件
を全部消化。

### Added — モデルの **アイドル自動アンロード**
- fastembed (e5-large, ~2 GB) と jina-reranker (~1 GB) が常駐で
  RSS ~11.9 GB → 8 GB Mac で swap 多発 という構造を解消。
- `embeddings.maybe_unload_idle()` (15 分未使用)、
  `rerank.maybe_unload_idle()` (10 分未使用) を追加。
- 60 秒間隔の `_idle_model_gc` thread が両方を監視。
- 期待動作: cold ~200 MB → 検索開始 ~3 GB → rerank 開始 ~11 GB
  → 10 分アイドル → ~3 GB → さらに 15 分アイドル → ~200 MB。

### Changed — Rerank 入力をさらに絞った (15 → 8)
- `RERANK_INPUT_CAP = 8`。15 件 cross-encode の 7.5 秒も玄人レビュー
  で「まだ遅い」と指摘 → 8 件で ~4 秒、limit=3 の top-3 結果は
  ほぼ変わらず。

### Changed — Backfill バッチサイズを 16 → 4
- backfill が lock を 16 件分（~5 秒）握り続ける → 検索が
  0.8 秒 timeout 内に取れず常時 fallback → 「Bunshin は keyword
  検索しかできない」と誤解される現象を解消。
- 4 件バッチ (~1 秒) なら検索 query が割り込める。

### Added — `harness_noise_v0_8_9` migration
- v0.8.8 で _strip_harness_noise() を ingest 時に追加したが、
  既存 296 件の Claude records (task-notification 含む) はそのまま
  だった。起動時 migration で UPDATE。
- chat の context に手動 XML が混ざる残存可能性を消す。

### Changed — pgrep liveness check に **cmdline 再確認**
- `os.kill(pid, 0)` だけでは pgrep 自身の subprocess を拾う
  race を防げないため、`ps -p PID -o command=` で cmdline を
  再 verify (python + bunshin + mcp 全て含むかチェック)。

### Docs
- `README.ja.md`: メモリ要件を **「16 GB 以上必須、推奨 32 GB」**
  に。アイドルアンロードの段階遷移 (200 MB → 3 GB → 11 GB) も明記。

## [0.8.8] - 2026-06-24

第 9 回レビューの 2 致命 + 4 中度を全消化。

### Fixed — 🚨🚨🚨 ~19,000 件の embedding 消失 (root cause 特定)
- **根本原因**: 各 ingestor (`claude_history.py`, `files.py`, `notes.py`
  等) が再取り込み時に `_delete_session_records()` で `records_vec`
  を削除するが、**embedding の再生成は startup 1 回限りの backfill
  thread に任せていた**。Claude を頻繁に使う = jsonl 更新 = vec
  削除 = 起動間で gap が積み上がる。
- **修正**: backfill thread を **60 秒間隔の永続 poll** に変更。
  ingest で gap が生じてもすぐに埋め直される。
- 副次効果: `total_embeddings > total_records` の不整合も自動修復。

### Fixed — 🚨🚨🚨 検索 rerank が 5〜26 秒の遅延ボトルネック
- **根本原因**: `search.py:483` で `top_k=limit` だが、入力候補数を
  絞っていなかった。`limit=20` → 40+ 件を cross-encode → 26 秒。
- **修正**: 入力を `RERANK_INPUT_CAP=15` 件に絞る。`limit=20` でも
  rerank コストは 15 件分 (~1.5 秒) に固定。
- rerank 対象外になった候補は末尾に保持し、`limit` 不足時にフォロー。

### Fixed — Claude history の `<task-notification>` XML 取り込み
- `bunshin/ingestion/claude_history.py` に `_strip_harness_noise()`
  追加。`<task-notification>`, `<user-prompt-submit-hook>`,
  `<task-id>`, `<tool-use-id>` などの harness 内部 XML を ingest
  時に除去。
- chat の context にメタ情報が混ざる現象を解消。

### Fixed — pgrep の phantom PID
- pgrep 経路にも `os.kill(pid, 0)` liveness check を追加。
- 死亡 subprocess 残骸が「v0.8.5 以前」として表示される現象を解消。

### Changed — 検索 fallback chip の文言改善
- 「⚙ 簡易検索」chip に **「数十秒〜数分で自動回復」** 一行追加。
- backfill の初回 warm-up 中の体験を改善。

### Added — `/api/health` に `rss_mb` 同梱、設定タブで表示
- 「困った時は」パネルに **「現在のメモリ使用量: N GB」** 表示。
- 9 GB 超では「8 GB 機では swap が発生します」と警告色に。
- 第 9 回素人レビューの「8 GB Mac で重い」を可視化。

## [0.8.7] - 2026-06-24

第 8 回レビュー: 検索/RAG-chat が backfill 中に **15 秒タイムアウト**
していた致命バグを根本対処 + 残り 6 件まとめて消化。

### Fixed — 🚨🚨🚨 検索/RAG が backfill 中に 15 秒ハング
- **根本原因**: `fastembed.TextEmbedding` がプロセス内シングルトン。
  backfill ワーカーが推論中、検索側の `embed_query()` が順番待ちで
  **正常時 10ms → 14.6s (1400 倍)** に。
- **修正**: `embeddings._model_lock` を導入し、
  - `embed_passages()` (backfill 側、長時間): 普通に lock 取得
  - `embed_query()` (検索/RAG 側): `timeout=0.8s` で acquire、
    取れなければ **新例外 `EmbedBusyError`** を raise
- `search.py` は `EmbedBusyError` を catch して keyword fallback。
  検索 UI には **「⚙ 現在「簡易検索」で表示中（分身が育成中）」** chip
  を表示し、ユーザーに事情を伝える。
- 友人配布の最悪ケース「初回 backfill 中に検索 → 15 秒待つ → 諦める」
  が物理的に発生しない。

### Fixed — 🚨 730 件の孤立 vector
- `records` から削除されたが `records_vec` に残った行を起動時マイグ
  レーション `orphan_vectors_v0_8_7` で一括削除。
- 玄人レビューの「total_embeddings > total_records → backfill 100%
  超え」が解消。

### Fixed — pgrep が Claude wrapper を誤検出
- `pgrep -f "bunshin mcp"` → **`pgrep -f "python.*bunshin mcp"`** に。
  Claude.app の `disclaimer` helper や pgrep subprocess の残骸を
  除外。素人レビューの「11 個と表示されるが実 MCP は 8 個」を修正。

### Fixed — `/api/note` の重複検出メッセージ
- 同じメモを 2 回保存すると「Empty content」を返していた問題。
- empty / duplicate を区別し、**「Duplicate — 同じ内容のメモが既に
  保存されています」** を返す。

### Fixed — 検索 keyword fallback の signal_score フィルタ
- `min_signal_score` 設定を keyword fallback パスにも適用。
- 「カレー」で newsletter 「カレー好きな自由人さんにスキされました！」が
  浮上する現象を解消。`user_signal == -1` (ユーザーが非表示) も除外。

### Fixed — `/api/diagnostics` の numpy bool エラー
- `bool(numpy_array)` → `v is not None and len(v) > 0`。
- "The truth value of an array with more than one element is
  ambiguous" を解消。

### Docs
- `README.ja.md` のメモリ要件を **「8 GB 以上」→「16 GB 以上（推奨
  32 GB — fastembed + rerank で実 RSS ~11 GB）」** に修正。

## [0.8.6] - 2026-06-24

第 7 回レビュー: v0.8.5 の MCP 鮮度バナーに **「pre-v0.8.5 プロセス
透明人間」問題** があり、初回アップデート時に banner が黙ったまま
ハマる可能性 → 構造的に解決。

### Fixed — 🚨 pre-v0.8.5 MCP プロセスの未追跡
- v0.8.5 の `/api/mcp/status` は `~/.bunshin/mcp_status/*.json` のみ
  走査していたため、status ファイルを書かない古い MCP プロセスは
  完全に透明だった。
- 素人レビュー実機: 8 個動いてるうち 2 個だけ追跡、`stale_count: 0`
  と誤情報を返す → banner が出ない → 初回アップデートで詰まる。
- **修正**: `pgrep -f "bunshin mcp"` フォールバックを追加。
  未追跡 PID は `{version: null, matches: false,
  note: "Pre-v0.8.5 MCP process — restart Claude to get fresh tracking"}`
  として混ぜる。Web server 自身の PID は除外。
- 私の手元で `pgrep` を叩いたら **8 時間前から動いていた古い MCP
  プロセス** 5 個が検出された (= 素人レビュアーの状況を完全再現)。

### Changed — banner の表現を 2 種類に対応
- 「v0.8.3 が 1 個 + 未追跡 v0.8.5 以前 6 個 = 合計 7 個」のように
  混在表示できるよう改修。

## [0.8.5] - 2026-06-24

第 6 回レビューの **MCP プロセス鮮度問題** を構造的に解決。
両レビュアー (素人/玄人) が 3 回連続で踏んだ "Claude 側 MCP が古い" 罠を、
設定タブの自動バナーで物理的に見逃せなくしました。

### Added — MCP プロセスバージョン監視
- 新エンドポイント `GET /api/mcp/status`: ローカルで動作中の全
  Bunshin MCP プロセスの **PID + version + 起動時刻** を返す
  (`~/.bunshin/mcp_status/<pid>.json` ベース)。
- 新 MCP ツール `get_server_info()`: Claude Desktop 側から
  自分が見ている MCP の version を取得可能。Claude が起動時に
  自発的に呼び、bundled と差があれば user に知らせるためのフック。
- MCP `run()` で起動時に status ファイル書き出し、atexit で削除。
  死んだ PID は自動清掃。

### Added — 設定タブに **「⟳ Claude を再起動してください」バナー**
- 設定タブ最上部に新コンポーネント `system-health-panel` を追加。
- MCP の `version` が `bunshin.__version__` と不一致なら自動表示:
  > ⟳ Claude を再起動してください
  > Bunshin は v0.8.5 ですが、Claude が掴んでいる MCP プロセスは
  > v0.8.4 のままです (1 個)。Claude を ⌘Q で終了→再起動すると…

### Added — Embedding backfill **進捗バー**
- 新エンドポイント `GET /api/embedding/status`:
  `{pending, filled, active, error}` を返す。
- 設定パネルに「分身が育っています…」のプログレスバー (5 秒間隔
  オートリフレッシュ)。素人レビュー: 初回起動 15 分の沈黙が
  「動いてるの？」と感じる問題を解消。

### Docs
- `docs/SETUP.md` に「Bunshin を更新した後に」セクション追加。
  Claude を ⌘Q→再起動する手順 + v0.8.5 のバナーで自動検知される
  ことを明記。

## [0.8.4] - 2026-06-24

第 5 回レビュー — **0.8 系を通じて潜伏していた致命バグ 1 件** を発見+修正。

### Fixed — 🚨🚨🚨 起動時 embedding backfill が v0.8.1 以降ずっと sailently dead
- **root cause**: `init_db()` は sqlite-vec を load しない設計。
  v0.8.1 で追加した `_fill_missing_embeddings()` が
  `load_vec_extension()` を呼んでおらず、`get_records_without_vectors()`
  が `no such module: vec0` で例外発生 → `except Exception: pass` で
  完全に握りつぶされていた。
- **発見**: 玄人レビュアーが実機で再現、5,781 件 (うち file 563 +
  claude 430) が「意味検索の射程外」になっていた。
- **修正**: 1 行で `load_vec_extension(_conn)` 追加 +
  `except Exception: pass` を `except Exception as e: print(...)` に
  変えて二度とサイレント失敗しないように。
- 起動時にターミナルログへ「`[startup] filling 5781 missing
  embeddings…`」と出るようになる。
- これだけで「壱岐黄金で検索しても最新の関連記録が出てこない」
  「先週話した内容が見つからない」が一気に治る。

### Fixed — `get_records_without_vectors()` に防御的 raise
- 関数に「`vec` ext 未 load 時は `RuntimeError` を投げる」防御を追加。
- 二度と同種のサイレント失敗を作らないための構造的対策。

### Refactored — HTTP `/api/entities` と MCP `list_top_entities` を共通関数化
- 新しい `knowledge_graph.get_top_entities(*, limit, type_, with_sources, exclude_noisy)` を
  追加し、HTTP / MCP 両方がこれを呼ぶように統合。
- 玄人レビュー: 「外部 AI が見るリストと UI が見るリストが別実装で
  ズレる ⇒ Phase 4 思想が破綻」を構造的に解決。
- `MCP list_top_entities` も `exclude_noisy=True` デフォルトに。

### Changed — SNS preset 2 回目以降の「既に綺麗です」
- 適用前プレビューで対象 0 件のとき、disabled 適用ボタンの上に
  「🎉 既に綺麗です。一括非表示の対象となる新しいノイズはありません」
  と前向きメッセージを表示。

## [0.8.3] - 2026-06-24

第 4 回レビューの 6 件 (致命 1 + UX 1 + 整合性 2 + 透明性 1 + 残課題 1) 全消化。

### Fixed — 🚨 `/api/health` 未実装でメニューバーが永遠に「⚠ 応答なし」
- v0.8.2 で Electron tray が 30 秒ごとに叩いていた `/api/health` の
  エンドポイントが web server 側に存在しなかった (404 が返り続けていた)。
- 5 行で endpoint 追加。レスは `{ok: true, version: "0.8.3"}`。
- これで「メニューバーで稼働状態を見る」が初めて実機で動く。

### Added — バージョン差検知（"DMG 更新したのに古いコードで動いてる"対策）
- `/api/health` のレスに `version` を同梱。
- Electron tray は app.getVersion() と比較し、不一致なら
  **「⟳ 再起動が必要 (0.8.2 → 0.8.3)」** と表示 + クリックで再起動。
- 玄人レビュー: 「ソース編集後の再起動忘れに気付けない」を解消。

### Fixed — 分身の成長記録の **数字整合性**
- `top_new_entities` を **本当に新規** なエンティティに修正:
  従来は `entities.created_at >= cutoff` (= 再インデックスで全件
  ヒット) → 真の "30 日以内のレコードにのみ登場するエンティティ"
  を SQL で算出。
- レスポンスに `visible_records_now` (auto-filter 抜き) と
  `auto_filtered_now` を追加。設定パネル UI でも
  「合計 N 件のうち、+M 件追加（うち K 件は自動フィルター中）」と
  /api/status と同じ言語で表示。

### Added — SNS preset の **適用前プレビュー** (透明性)
- `GET /api/learning/sns_preset/preview` を追加: 各ドメイン/送信者
  パターンの **実際の対象件数** を返す。
- 設定タブのボタン → 確認モーダル（各パターンをチェックボックスで
  個別解除可能） → 適用、の 2 ステップに変更。
- POST `/api/learning/sns_preset` は `{domains: [...], senders: [...]}`
  の選択リストを受けるよう拡張（無指定なら従来通り全適用）。

### Fixed — `get_recent_chat` で **空セッションを除外**
- `msgs == []` のセッションは外部 AI に渡しても無価値なので
  skip 条件を追加。
- これで Claude Desktop からの `get_recent_chat(n=10)` が
  「最初の 3 件 + (empty) 7 件」にならない。

## [0.8.2] - 2026-06-24

第 3 回 (素人 + 玄人) レビューの **全 6 件** を消化。

### Changed — MCP ツール 4 本に磨きをかけた
- **`list_top_entities`**: 各エンティティに **`top_sources`** を追加
  （`{gmail: 460, claude: 15}` のような分解）。外部 AI が
  「これは note 通知由来のノイズ」と判定できるようになった。
- **`get_recent_chat`**: 新パラメータ `min_user_chars` (デフォルト 8)
  追加。`hello` / `hi` / `test` のような短すぎる会話は履歴に出ない。
- **`get_flashback`**: 空窓に `empty_message` フィールド追加。
  - 5 年前枠が DB の最古より古い → 「Bunshin はまだあなたを知り
    ませんでした」
  - それ以外で空 → 「静かな日でした」
- **`get_today_hero`**: docstring に **`kind` の取り得る値を列挙**
  (`event` / `stale_project` / `recent_file`) + 推奨 UI トーン。
  外部 AI が `switch (hero.kind)` で安全に分岐できる。

### Changed — 分身の成長記録からノイズ除外
- `top_new_entities` で gmail/browser シェアが 80% 超のエンティティ
  (note.com ニュースレター由来の「note」「ポーランド」等) を除外。
- 残ったエンティティには `top_sources` を付加。

### Added — メニューバーアイコンに **状態表示**
- 30 秒ごとに `/api/health` に ping し、結果を反映:
  - 稼働中 → tooltip 「Bunshin · 稼働中」 + 最上段「● 稼働中」
  - 応答なし → tooltip 「⚠ Web UI 応答なし」 + 最上段「⚠ Web UI
    停止中 — クリックで再起動」
- 素人レビュー「UI 落ちてるのか動いてるのか分からない」を解消。

## [0.8.1] - 2026-06-24

「ほぼ全て」じゃなく **全て** をやり切る patch。残っていた 4 件 + 玄人指摘の
未完了 embedding を全部消化。

### Added — 起動時の自動 embedding backfill
- 玄人レビューで「埋め込み未完了 508 件」と指摘されたが、調査の結果
  この dev DB だけで **5,403 件** が未 embed のまま放置されていた。
- 起動 15 秒後にバックグラウンドで未 embed 全件を埋める処理を追加。
  進捗はターミナルログにのみ出力（UI を邪魔しない）。

### Added — ノイズメール一括非表示（SNS プリセット学習）
- 設定タブに **「よくあるノイズを一括非表示」ボタン** 追加。
- 16 のドメイン (mailchimp / sendgrid / mercari / paypal / amazon /
  rakuten / list-manage / smartnews / newspicks 等) と 7 の送信者
  パターン (noreply / no-reply / marketing@ 等) を **learning_rules**
  に一括投入 + 既存記録に即時適用。
- 玄人レビュー C 案の実装。

### Added — `bunshin export` / `bunshin import` CLI
- マシン移行用の export/import コマンド。
  - \`bunshin export --since 2026-01-01 --source claude --out backup.jsonl\`
  - \`bunshin import backup.jsonl --skip-existing\`
- export は既定で browser 履歴を除外（プライバシー）。

### Added — 「分身の成長記録」（memory diff）
- 設定タブ最上部に「この 30 日間で +N 件、新登場エンティティ X 個」
  を可視化するパネル追加。
- `/api/memory_diff?days=30` endpoint で取得。
- 玄人レビュー: 「自分が変わった軌跡が見える、これは差別化要素として
  刺さる」。

## [0.8.0] - 2026-06-24

**Minor 番号を 0.8 に上げる節目**。v0.7.0 から始まった「壱岐の友人配布
向け」改修サイクルが終わり、AI ヘビーユーザー / Claude Desktop 連携の
土台が揃ったため。

### Added — MCP ツールを 6 本に拡張（玄人レビュー優先度 C→A）
Claude Desktop など MCP 対応 AI から、Bunshin を **能動的に問い合わ
せる** ためのツールが 4 本増えました（既存 2 本＋新規 4 本）:

| ツール名 | できること |
|---|---|
| `search_memory` (既存) | 過去記憶を semantic + BM25 + rerank で検索 |
| `recall_session` (既存) | 指定セッションの全メッセージ展開 |
| **`get_flashback(date?)`** | この日付の過去窓 (1週/3ヶ月/1年/5年) を一括取得 |
| **`get_today_hero()`** | 「今日これだけ見ればOK」を JSON で返す |
| **`list_top_entities(type?)`** | 言及多い順のエンティティ一覧 |
| **`get_recent_chat(n)`** | 直近 N 件のチャットセッション要約 |

これで Claude Desktop が **自分から** 「先週の今日のあなたは何を
話してたか」「今日の優先事項は何か」を引き出せるようになります。
ナレッジ管理を超えて、**主体的な記憶エージェント** に。

## [0.7.12] - 2026-06-24

エラー時のサポート導線 + フラッシュバック感情調整 + エンティティ品質。

### Added — エラー時に「診断情報を送る」リンク
- チャット / 検索でエラーが起きた時、エラーメッセージの下に
  **「診断情報を取得して開発者に送る →」** リンクを表示。
- クリックで設定タブ → 困った時は へ自動ジャンプ + 「診断情報を取得」
  ボタンをハイライト。
- 素人レビュー指摘: 「困った時はパネルが超優秀だけど、エラー発生時の
  ユーザーが見つけられない」を解消。

### Changed — フラッシュバック「5 年前空」の特殊メッセージ
- 5 年前枠が空の時 **「5 年前。あなたはまだ Bunshin に来ていません」**
  と明示。一般の「静かな日」プロンプトより文脈に合う。

### Added — エンティティ辞書を拡張 + ノイズ削除
- `ENTITY_TYPE_OVERRIDES` に英語表記 (Tokyo, Japan, USA…) + ユーザー
  特有のエンティティ (`ホークす`, `MARINE FLIGHT`, `AIR Flight` 等) を追加。
- `NOISE_ENTITY_NAMES` 定数を追加し、`the` / `a` / `?` / 1 文字 などの
  ノイズエンティティを `upsert_entity()` で削除 + 起動時に既存 DB からも
  一括 prune。

## [0.7.11] - 2026-06-24

実機レビュー（玄人 + 素人）で見つかった残り 4 件を修正。

### Fixed — 既存ブラウザ履歴の SNS demotion が効いていなかった（致命的）
- v0.7.8 の `-35 点` ロジックは **新規取り込み時のみ** 適用されていた。
  既存 2,000+ 件の browser 記録は signal_score がそのままで、
  フラッシュバックや検索に YouTube/SNS が出続けていた。
- **起動時のマイグレーション**を追加: 初回起動で全 browser 記録の
  signal_score を再計算。1 回だけ実行（`migrations` テーブルで記録）。
- これで「金のため23匹のヘビが入った寝袋で寝る男達 - YouTube」が消える。

### Fixed — 旧 `(empty)` セッションが履歴サイドバーに残る
- v0.7.6 で新規セッションは自動命名されるようになったが、**過去の
  (empty) セッションはそのまま残骸として表示** されていた。
- 起動時マイグレーションで既存 sessions も最初の発言から自動命名。

### Fixed — `entity.mention_count` が API で常に null
- `entity_by_id()` が単純 SELECT で `record_entities` を JOIN
  していなかったため、MCP / API 越しに見ると `mention_count: null`
  になっていた。
- LEFT JOIN + COUNT を追加。後方互換のため `mentions` と
  `mention_count` 両方のキーで返却。

### Added — チャットの雑談判定（短いクエリは RAG しない）
- 「hello」「おはよう」「ありがとう」など **短い挨拶** は context 取得
  をスキップし、AI に過去記憶を渡さないように。
- 素人レビュー: 「hello だけ送ったら 5 件の Claude 会話を勝手に
  掘り起こされて『侵略的』に感じた」。
- ヒューリスティック: 8 文字以下の挨拶リストマッチ、または 3 文字以下。

## [0.7.10] - 2026-06-24

### Changed — エクスポートからブラウザ履歴を既定除外（プライバシー対応）
- `/api/export/json` のデフォルトを **ブラウザソース除外** に変更
  （玄人レビューの「OSS 公開時にユーザーがエクスポートして共有する
  シナリオでうっかり漏れる」懸念への対応）。
- UI に **「ブラウザ履歴も含める（自分用バックアップ）」チェックボックス**
  を追加。明示的に ON にした時だけ含めて出力。
- ファイル名にも `-with-browser` サフィックスがつくので、共有時の
  視認性も担保。

## [0.7.9] - 2026-06-24

### Added — 気づきタブの「今日これだけ見ればOK」ヒーローカード
- 気づきタブの最上部に **1 枚だけ** の大きなカードを追加。`/api/insights`
  の結果から **最も今日アクションすべき 1 件** を自動選出:
  - 14 日以内の予定があれば → 「次の予定: XXX」（緑）
  - 長期未活動プロジェクトがあれば → 「『〇〇』が N 日動いてません」（オレンジ）
  - 最近触ったファイル → 「最近触ったファイル」（青）
- 素人レビュー「気づきタブの項目が多すぎて、何を見ればいいの？」への
  直接の回答。

### Changed — フラッシュバック空時の文言
- 「この日は静かでした」→ 日付ハッシュで以下から選択:
  - 「この頃、何してたっけ？」
  - 「記憶がない日。後で思い出したら ⌘N でメモ」
  - 「静かな日。あなたが Bunshin に来る前かも」
- 同じカードが 3 枚並んだ時の「全部空」感を緩和。

## [0.7.8] - 2026-06-24

「触ってみて気持ちいい」UX 3 点。素人レビューで指摘された細部。

### Changed — 検索ハイライトを「目に飛び込む黄色」に
- `<mark>` の色をダークモード時は **#ffd400 背景 / 黒文字 / 微シャドウ**
  に強化（前: 茶背景に薄い黄文字 — 控えめすぎ）。
- ライトモードは **#ffeb3b** で同等のコントラスト。
- どちらでも「ここがマッチした」が一瞬で見える。

### Added — 「+N 件 記憶しました」毎日トースト
- 起動時 1 回（その日初回のみ）、画面下部にスライドイン:
  - **「+47 件 記憶しました（合計 15,381 件）」**
  - 4.5 秒で消える、`localStorage` で「今日は表示済み」を記録
- 育成ゲーム感 → 毎日アプリを開く理由になる（素人レビュー提案）。

### Changed — YouTube / SNS の閲覧履歴を信号スコアで自動下げ
- ブラウザ履歴の中で **YouTube / X (Twitter) / Instagram / TikTok /
  Reddit / Facebook / niconico / X の SNS** に該当する記録は、
  signal_score を **-35 点**。
- 自動フィルター閾値（30）以下に落ちるので、検索やフラッシュバックで
  「金のため23匹のヘビが入った寝袋で寝る男達 - YouTube」のような
  受動視聴履歴がデフォルトで出てこなくなる。
- 完全削除ではないので、設定で自動フィルターを下げれば再表示可能。

## [0.7.7] - 2026-06-24

AI ヘビーユーザー向け 2 機能。検索結果の説明性 + 「Claude/ChatGPT に
丸ごと渡す」ワークフロー。

### Added — 検索結果「なぜヒットしたか」chip
- 各検索結果カードのメタ行に **マッチ理由の小チップ** を表示:
  - 「AI N」 — クロスエンコーダで上位
  - 「意味 N」 — embedding 類似度
  - 「キーワード ✓」 — BM25 でクエリ語が当たった
  - 「重要」 — signal_score 60+
  - 「⚠ 簡易検索」 — embedding 失敗時の keyword fallback
- score_components はもとから DB に持っていたが、UI に出ていなかった
  ので AI ヘビーユーザー（玄人レビュー指摘）の信頼を得られなかった。

### Added — 「まとめて Markdown でコピー」ボタン
- 検索結果が表示されたら、結果一覧の上に **「📋 まとめて Markdown
  でコピー」** ボタンを表示。
- クリックでクエリ + 取得件数 + 各記録（時刻・ソース・本文）を Markdown
  として **クリップボードへ一発コピー** → Claude / ChatGPT にそのまま
  貼れる。
- 玄人レビュー: 「AI ヘビーユーザーは毎日 10 回これをやる」

## [0.7.6] - 2026-06-24

AI 玄人レビューで指摘された **「見えない構造的問題」 3 件** を修正。

### Fixed — Insights ダイジェストの 3 分タイムアウト
- 「今週のダイジェスト」が常時タイムアウト（`covered_records: 200` 件
  を `qwen2.5:32b` で要約しようとして 3 分超過）していたバグ。
- 新規 `pick_light_model()` を追加し、digest / entity 抽出 / query 拡張
  などの **バッチ系・長プロンプト系処理は軽量モデル優先** に変更。
  - digest なら `qwen2.5:7b` か `:3b` で 30〜60 秒に収まる。

### Fixed — チャット履歴が「(empty)」だらけ
- 新規チャット作成時、最初の発話で **session.title が自動更新されな
  かった** 問題を修正（玄人レビュー指摘）。
- 1 件目の user message の先頭 40 字をタイトルとして即保存。ChatGPT /
  Claude と同じ動作。これで履歴サイドバーが判別可能になる。

### Fixed — エンティティタイプの誤分類
- 「YouTube が place」「note が organization」のように LLM 抽出が雑に
  ラベル付けていた問題を修正。`ENTITY_TYPE_OVERRIDES` という curated
  辞書（Tech 企業 / 国・地域 / プログラミング言語など 40 件）を追加し、
  `upsert_entity()` で常に正規化されるように。
- 起動時に既存 DB の誤ラベルも一括 patch（バックグラウンド・非同期）。

## [0.7.5] - 2026-06-24

**緊急修正 + UX 全面磨き直し**。AI 素人視点 + AI 玄人視点の評価をもとに、Bunshin の中核機能を救出し、第一印象を救う改修。

### Fixed — 検索が壊れていた致命的バグ
- **embedding model cache の破損で検索が常時 0 件を返す** バグを修正。
  fastembed の `model.onnx_data` が部分ダウンロードのまま放置されていた
  ことで、ONNX ロードが失敗し、`/api/search` が常に空を返していた。
- **`search()` に keyword fallback を追加**。embedding が万が一壊れても
  全件 0 件にはならず、`content LIKE '%query%'` で必ず何かを返す。
- **設定タブ「困った時は」に検索エンジン健全性表示** を追加。
  「N 件中 M 件インデックス済み」を可視化し、壊れていれば **「検索
  インデックスを再構築」ボタン** ですぐ復旧可能。
- 新規 endpoints: `/api/embedding/rebuild` (NDJSON ストリーム)。

### Changed — エラーメッセージから「ターミナル」「ログ」を一掃
- AI 素人の評価で「`ターミナルのログに詳細が出ています` と言われた瞬間
  に閉じる」と指摘されたので、`friendly_error()` の hint を全て **次に
  ユーザー自身が取れる行動** に書き直した:
  - 「もう一度試してみてください。続く場合は 設定 → 困った時は から
    開発者に教えてください」
  - 「システム設定 → プライバシーとセキュリティ で Bunshin を許可して
    ください」 etc.

### Changed — チャット待ち時間に「考えてるよ」アニメ
- 数十秒の無反応で離脱されないように、チャット送信瞬間から **跳ねる
  3 つのドット** を表示。「過去のあなたを読み込み中…」 → 「N 件の
  過去記憶を読みました。{model} が考え中…」 → 応答開始で消える。

### Changed — デフォルトチャットモデルを 14b 優先に
- `PREFERRED_MODELS` の先頭を `qwen2.5:32b` から `qwen2.5:14b` に変更。
  32b は応答に 30〜60 秒かかり「壊れた？」と思われる主因。14b なら
  10〜20 秒で品質も十分。RAM-aware の `pick_model()` と組み合わさって、
  16 GB Mac の体感が劇的に良くなる。

### Changed — SETUP.md の冒頭に DMG ユーザー向け案内
- AI 素人が「`brew install python@3.11` で挫折確定」と指摘した問題に
  対応。`.dmg` 版にはすべて内包されているので「ここから先は読まなくて
  大丈夫」を **ページ最上部に大きく明示**。

## [0.7.4] - 2026-06-24

### Added — カレンダー登録 UI
- 設定タブに「カレンダー」セクション追加。Google カレンダー / iCloud
  カレンダーの **iCal 公開 URL** を貼り付けて「登録 & 取り込み」ボタンを
  押すだけで、今後の予定 14 日分を Bunshin の記憶として取り込みます。
- 取り込み済みの URL が見える、件数が見える、「今すぐ再取り込み」
  「URL を解除」ボタン。
- iCal URL の取り方（Google / iCloud それぞれ）を panel 内に展開可能な
  ヘルプとして同梱。ターミナルを開く必要なし。
- `webcal://` で始まる URL は自動で `https://` に変換します（iCloud
  デフォルト形式）。
- 新規 endpoints: `/api/calendar/status` (GET), `/api/calendar/setup`
  (POST), `/api/calendar/import` (POST), `/api/calendar/remove` (POST).

## [0.7.3] - 2026-06-23

「触ってみて感じる速度」と「Mac スペックに合うモデル」の両方を改善した patch。

### Performance — Search
- 検索の cross-encoder rerank に渡す候補数を 4×limit から 2×limit に削減。
  典型的な検索（limit=20）で rerank 入力 80 件 → 40 件、Apple Silicon
  では rerank 時間が ~5 秒 → ~2 秒に。並び順への影響は最小（top の入れ替え
  は元から上位 10 件内で起きる）。

### Changed — Default chat model is now RAM-aware
- `pick_model()` が Mac の物理メモリ（`sysctl hw.memsize`）を見て、
  fit する最大の Q4 量子化モデルを自動選択するように。
  - 8 GB Mac → `llama3.2:3b`（〜3 GB）
  - 16 GB Mac → `qwen2.5:14b`（〜12 GB）
  - 32 GB Mac → `qwen2.5:32b`（〜22 GB）
  - 48 GB+ Mac → `qwen2.5:72b`（〜48 GB）
- これまでは「PREFERRED_MODELS の先頭が available なら」で 32b/72b を
  選んでしまい、16 GB 以下の Mac でスワップが頻発していた。

## [0.7.2] - 2026-06-23

QA リスト 4 件をまとめた patch。

### Changed — Source naming
- ソース名を「分かりやすさ優先」に変更:
  - `メモ` → **クイックメモ** (+記憶ボタンや「覚えといて:」で追加したもの)
  - `メモ帳` → **Apple メモ** (macOS のメモ.app から取り込んだもの)
- 一元的な `SOURCE_LABEL_JA` 辞書に統合（過去の `FLASHBACK_SOURCE_LABEL` 別途定義を削除）。

### Added — Timeline source icon tooltips
- タイムラインの日次サマリで、ソースアイコン（🌐💬📄📧 …）に hover
  すると「ブラウザ: 64 件」「Claude: 587 件」のように具体名と件数が
  tooltip で出るように。

### Added — Header "+記憶" tooltip 強化
- `+ 記憶` ボタンの title を「メモを記憶に追加 (⌘N)」から
  「メモを Bunshin に追加（後で検索や AI チャットから参照できます）⌘N」に。

### Fixed — ⌘N shortcut conflict
- `⌘N` が「新規チャット」と「+記憶 modal」の両方で取り合いになって
  いた。**+記憶 modal** を常に開くように統一。help モーダルの
  説明文も合わせて更新。

## [0.7.1] - 2026-06-23

QA パスで見つかった UX のひっかかりを潰した patch リリース。

### Changed — Search UI
- 検索クエリ入力中はフラッシュバックを自動で折り畳み、結果が画面上部
  にすぐ出るように。空クエリに戻すと再表示。
- ソースチップの active 状態を「うっすら背景色」から「accent 色の濃い背景 +
  白文字 + box-shadow」に強化。どのソースで絞ってるかが一目でわかります。

### Changed — Chat status text
- 「応答生成中…」だけだった表示を、ステージごとに更新するように:
  「過去記憶を検索中…」 → 「N 件の過去記憶を参考に {model} が考え中…
  （10〜30 秒）」 → 応答ストリーム開始でクリア。
- ローカル LLM の体感速度に対する不安を減らす。

## [0.7.0] - 2026-06-23

The "壱岐の友人に渡せる" release. Quality pass before sharing with
non-technical first users — every install-blocker, every silent confusion
point, every "?" moment that an early test surfaced has a one-click answer.

### Added — Demo GIF build pipeline
- New **`scripts/build-demo-gif.sh`** converts a QuickTime `.mov` recording
  into an optimized `docs/demo.gif` (1200px wide, 12fps, ffmpeg palette
  pass + optional gifsicle lossy pass). Target output ≤ 8 MB so GitHub
  renders it inline in the README.
- README recipe in `docs/screenshots/README.md` documents the 30-second
  shot list (検索 → チャット → 関係性) and the markdown snippet to
  embed the GIF at the top of the project README.

### Added — Uninstall feedback path
- 設定タブの末尾に「Bunshin を辞める」セクション。「アンインストール
  手順を見る」ボタンで modal を開くと、5 つの理由 (重い / 難しい /
  想像と違った / バグ / その他) + 任意の補足コメント + 環境情報を
  `mailto` のテンプレートとしてプリフィルしてメールクライアントを開きます。
- 送信せずに手順だけ見ることもできます。アンインストール手順は
  Bunshin.app 削除 + `~/.bunshin/` 完全消去 + launchd plist の unload
  を 4 ステップで明示。

### Added — Post-onboarding tour
- New **3-step visual tour** runs once after the setup wizard completes:
  検索 → チャット → 関係性 タブを順番に切り替えながら、各タブで何ができ
  るかを 1 〜 2 行で説明します。スキップ可、`localStorage` に `bunshin.tour`
  を立てて 2 回目以降は出ません。Wizard だけだと「データの入れ方」しか
  分からず、何のためのアプリかが見えない問題への一手。

### Added — "困った時は" diagnostics panel
- New section at the bottom of the settings tab. One click gathers OS,
  Bunshin version, Ollama 4-state, DB size + record count, and the last
  100 lines of `update.out.log` / `update.err.log` into a single JSON
  payload via the new **`/api/diagnostics`** endpoint.
- Buttons to **copy to clipboard** and **prefill a mailto** template
  (`Bunshin 困りごと (v0.6.0)` subject + diagnostic JSON in body),
  plus a deep link to **GitHub Issues** for users who prefer that.
- Excludes records, file contents, email bodies, and entity data — only
  ships infrastructural facts so the user can debug without worrying
  about leaking personal memory.

### Changed — Japanese error messages everywhere
- **`friendly_error()` helper** translates Python exceptions
  (`FileNotFoundError`, `PermissionError`, `ConnectionError`, `TimeoutError`,
  `ValueError`, etc.) to `{error, hint, code}` payloads in 日本語.
- **Global FastAPI exception handler** ensures unhandled errors never
  leak a raw Python traceback to the UI — the full stack still prints
  to the dev terminal, but users see a calm Japanese message.
- Replaced six English error strings (`"not indexed"`, `"not on disk"`,
  `"restore failed"`, `"record not found"`, `"Ollama not running"`,
  `"Ollama.app not found"`) with proper Japanese equivalents.
- Six remaining `str(e)` leaks (scheduler endpoints, Ollama launch,
  chat streaming) now route through `friendly_error()` instead.

### Added — Quick memory capture
- **"+ 記憶" button** in the top-right header (every tab). One click opens
  a modal with a textarea and "保存 (⌘↵)" / "キャンセル" buttons.
- **⌘N global shortcut** opens the same modal from anywhere except while
  typing in another input.
- Persists via the existing `/api/note` endpoint (same path as the
  `覚えといて: …` chat prefix), so vectors and search indexing are
  shared with the rest of the pipeline.
- Replaces the previous "type a magic prefix in chat" workflow as the
  primary discoverable entry point — the prefix still works for power
  users.

### Added — DMG install hint
- DMG background now carries a footer band explaining the first-launch
  step (`right-click → 開く`) so users don't hit the macOS gatekeeper
  warning with no guidance.

### Added — Ollama onboarding
- New **`/api/ollama/status`** endpoint returns a 4-state readiness
  signal: `not_installed` / `not_running` / `no_models` / `ready`. Looks
  for the `ollama` binary in `shutil.which` plus the standard macOS
  install paths (`/usr/local/bin`, `/opt/homebrew/bin`,
  `Ollama.app/Contents/Resources`), so detection works even when the
  bundled Python has a minimal `PATH`.
- **Chat tab now self-explains** what's missing when chat can't work,
  with a one-click resolution for each state:
  - `not_installed` → "Ollama をダウンロード" button (deep link to
    `ollama.com/download/mac`).
  - `not_running` → "Ollama を起動" button (`open -a Ollama.app` via
    new `/api/ollama/launch`).
  - `no_models` → "qwen2.5:3b を入手" button that streams `ollama pull`
    progress inline via new `/api/ollama/pull`.
- Banner disappears automatically once Ollama reaches the `ready` state.

## [0.6.0] - 2026-06-23

The "OSS-ready" release. Bunshin can now be opened from the menu bar
without ever launching the main window, surface the day's flashback
as a native macOS notification, and prove its privacy promises through
a transparent settings panel. The README has real screenshots, and the
repo has the docs an outside contributor needs to find their way in.

### Added — Menu bar & notifications
- **Tray icon** (`∞`) in the macOS menu bar. Left-click toggles the
  main window's visibility; right-click opens a context menu with
  shortcuts to 検索 / チャット / フラッシュバック / 終了.
- Uses a macOS template image (auto-tinted to match the menu bar),
  so it reads as a system icon — not a colored sticker.
- **Morning flashback push** — once per day, between 07:00 and 11:00
  local time, a native macOS notification surfaces the day's most
  distant flashback ("5 年前の今日 の記憶") with the record snippet.
  Clicking it opens the main window straight to the search tab.
  Idempotent via a date-stamped store key.

### Added — Privacy panel
- New **設定 → プライバシー** section at the top of the settings tab.
- "あなたのデータは、この Mac から一歩も出ません" promise banner with
  a real checkmark, plus a one-sentence summary of why.
- Lists the live DB path + size, total data-folder size, Ollama
  running status (probed at `127.0.0.1:11434`), and every external
  destination Bunshin actually contacts (proves the empty list when
  nothing is configured).

### Added — OSS contributor docs
- `CONTRIBUTING.md` — quick-start, project layout, branch + PR rules,
  coding style, good-first-issue pointers, release recipe.
- `ARCHITECTURE.md` — module map, the 4-condition design rationale,
  end-to-end data flow diagrams for import and search, "where to
  land your change" cheatsheet.
- `CODE_OF_CONDUCT.md` — Contributor Covenant 2.1.
- `.github/ISSUE_TEMPLATE/` — `bug_report.md`, `feature_request.md`,
  `question.md`, with `config.yml` routing blank issues to
  Discussions / docs.
- `.github/pull_request_template.md` — required checks include
  "4-condition impact" so changes that break Local-first / AI-Agnostic /
  Offline / Omni-source get caught at review.

### Added — README hero
- README hero strip with three real screenshots (search + flashback,
  relationship spider-web, chat with cited memory).
- Shields.io badges for release, platform, license, and a custom
  "local-first 100%" badge.
- Recipe for adding / refreshing screenshots in
  `docs/screenshots/README.md`.

### Changed
- Settings save button is now a **floating round button** in the
  bottom-right of the settings tab. No longer disappears when you
  scroll past the schema-driven fields, no chrome wrapper around it.
- Settings sections gained icon prefixes (lock for プライバシー,
  clock for 自動取り込み, archive for バックアップ, download for
  エクスポート, brain for 学習).

### Fixed
- The black gradient bleeding through the settings tab in light mode
  (`.settings-save-bar` was hardcoded to `#0a0a0a`) — now driven by
  CSS variables so it follows the theme.

## [0.5.0] - 2026-06-22

The "ready for friends" release. Everything a first-time user needs to go
from "what is this app" to "Bunshin is now remembering me" — without ever
touching Terminal.

### Added — Onboarding wizard
- **5-step wizard** auto-shown on first launch (DB < 200 records).
  Welcome → Gmail → Photos → Notes/iMessage → Done, with per-step
  skip / back / next navigation.
- Each step **pre-explains the macOS permission dialog** that's about
  to appear, so users aren't scared by "full disk access" out of
  nowhere.
- Final step shows live stats: records / entities / sources / oldest
  year. Onboarding flag persisted in `localStorage` so the wizard
  never reappears once dismissed.

### Added — Mac spec detection & model recommendation
- `/api/system/recommend-model` detects this Mac's RAM via
  `sysctl hw.memsize` and recommends the largest Ollama model that
  fits comfortably (ladder: 1b → 3b → 7b → 14b → 32b → 72b).
- Recommendation banner in **Settings → チャット** shows
  "`qwen2.5:32b` がおすすめ (32 GB RAM)" with installed / not-installed
  status and a one-click copy of the `ollama pull` command if missing.
- Chat model field is now a **dropdown** populated with every model
  in the ladder, each annotated with ★ 推奨・✓ インストール済み・
  · 未ダウンロード.

### Added — Auto-import scheduler UI
- **Settings → 自動取り込み** section with a toggle that installs or
  removes the launchd plist (macOS) / systemd timer (Linux) directly.
  No more `bunshin install-scheduler` from Terminal.
- "今すぐ更新" button fires off a background `bunshin update --quiet`.
- Status line shows the active plist path or "未設定 — トグルで有効化".

### Changed — Visual identity
- **Every emoji in the system UI replaced with inline SVG**
  (Feather / Lucide style, outline, stroke 2). Bunshin now reads as
  a real tool, not a chat thread. Affected: tabs, source chips,
  search-result icons, flashback cards, learning rules, settings
  section headers (📤 → download, 🧠 → brain, 💾 → archive, …),
  wizard step titles, insights tab, ctx-toggle, score icons.
- **Empty-state welcome page rewritten** from "run these terminal
  commands" to "今日から、あなたの記憶が育ち始めます" with three
  action cards (open wizard / open chat / open settings) — zero
  command-line requirements for first-time users.
- Settings → チャット → 優先するチャットモデル now reads
  "auto のままで OK — 下のおすすめが自動で使われます".

### Fixed
- Light mode no longer leaks a black gradient at the bottom of the
  settings tab (`.settings-save-bar` was hardcoded to `#0a0a0a`).

## [0.4.0] - 2026-06-19

The "actually useful daily" release. The flashback widget brings the
day back to you, the noise filter learns from your taste, and the UI
got much quieter — fewer chrome lines, denser sidebars, a real
foothold for new users on the first launch.

### Added — Flashback widget
- **Today's flashback** on the search tab — three retrospective cards
  ("先週の今日 / 3 ヶ月前 / 5 年前") populated from records on the
  same calendar date in the past. Click a card to drill into the
  full day's records.
- The three retrospective windows now adapt to how much history
  Bunshin actually has, so users on a 30-day-old DB see
  "1 ヶ月前 / 2 週間前 / 先週" instead of empty year-old cards.
- New `/api/records?from=&to=` endpoint — plain time-range listing
  (no FTS) used by the flashback drill-down.

### Added — Learning-based noise filter
- New `signals.py` with a per-record `signal_score` (0–100). Computed
  at insert time and backfilled on server start for any record still
  missing it.
- `clean_for_display()` strips URLs, mail headers, tracking blobs,
  long hash-like tokens, HTML tags, empty `( )` pairs, decoration
  lines (▲▲▲ / ─── / ===), and collapses the runaway blank lines
  that HTML email bodies leave behind.
- **Mark UI** — `🗑 要らない` button on every flashback card and
  drill-down row, with a modal asking *learn this record / this
  sender / this domain*. Marked rules persist in a new
  `learning_rules` table.
- **Undo toast** — 5-second window to take back a mark, with live
  countdown and one-click revert.
- **Settings → 🧠 学習** dashboard lists every rule with per-rule
  delete and a "全部リセット" button.
- **Auto-filter** — records with `signal_score` below a configurable
  threshold (default 30) are excluded from search and flashback.
  Header shows a `2,717件自動フィルター中` chip explaining what's
  hidden. New setting: `min_signal_score` (search section, 0–100).

### Added — Quality-of-life
- **Header stats are now stats to brag about**: `10,711 records ·
  137 entities · 8 sources · 2015年から · 47件非表示`.
- **Source chips show per-source counts** (`💬 Claude (3,422)`,
  `📧 Gmail (1,660)`, etc.) and dim to ~40% opacity when the source
  has zero records.
- New chip: **📸 写真ライブラリ** distinguishes Photos.app library
  imports from manual photo-OCR records.
- Empty-state copy rewritten across all four tabs ("過去の自分に
  聞いてみてください", "分身は、過去のあなたを全部読んでいます",
  etc.).

### Changed — UI density and polish
- **Chat sidebar redesigned**: flat `+ 新規チャット` button,
  explicit 設定 / 履歴 sections, search icon embedded in input,
  session cards now show last-message preview + model + count + date.
- The chat tab no longer leaves a gap between the left nav rail and
  the history sidebar — `body.chat-mode` drops main's padding to
  zero for that tab only.
- Header underline removed across all tabs for a flatter look.
- Splash screen palette aligned with the app icon (indigo +
  pink ribbon + yellow core), replacing the old blue/green.

### Fixed
- Relationship graph: clicking an entity in the list now actually
  re-centers the spider-web, not just the right-hand detail pane.
- Chat session list now carries `preview` (last message) so the
  redesigned sidebar can show a real "what did we talk about" hint.

### Importers
- `import-gmail --full` and `import-browser --full` ignore the
  last-sync marker and refetch the full `--initial-days` window
  (use with `--initial-days 36500` to backfill everything still
  on the IMAP server / browser DB).

### Schema migration
- Idempotent migration in `init_db()`: adds `signal_score`,
  `user_signal`, `sender`, `sender_domain` columns to `records`
  and creates the `learning_rules` table. Existing databases
  upgrade in place; no manual step required.

## [0.3.3] - 2026-06-16

The "works on a clean Mac" release. Self-contained DMG, no Python
install required.

### Added
- **Bundled Python runtime** — the DMG now ships a complete
  PyInstaller-built `bunshin` CLI inside `Contents/Resources/bunshin/`.
  Users with no Python install can drag the app to Applications and it
  just works.
- Electron's `findBunshinBinary()` now prefers the bundled CLI over a
  developer venv, falling back to `~/.bunshin/venv/bin/bunshin`,
  `/usr/local/bin/bunshin`, and `/opt/homebrew/bin/bunshin` for source
  installs.

### Changed
- **DMG size**: 96MB → 169MB (arm64), 100MB → 173MB (x64). The
  extra ~73MB is the bundled Python runtime + every fastembed /
  sqlite-vec / fastapi / pillow dependency. First-launch model
  download (e5-large, ~2GB) is unchanged.

### Build infrastructure
- New `bunshin.spec` for PyInstaller. Collects all data files and
  hidden imports for the runtime-discovered dependencies.
- New `src/bunshin/__main__.py` entry point so the bundle can run as
  a single executable.

## [0.3.2] - 2026-06-16

Hot fix for a v0.3.1 regression that broke tab switching.

### Fixed
- **All tabs except Search were unreachable** in v0.3.1. The
  search-highlight regex relied on backslash escapes that Python's
  triple-quoted string mangled, producing an invalid regular
  expression literal. The JS parser bailed on the whole script,
  killing every event handler including the tab-switch one.
- Replaced the regex with a plain character-walk loop so no
  backslash escapes are needed in the served JS. Highlight behavior
  is unchanged.

## [0.3.1] - 2026-06-16

A same-day polish release after v0.3.0 — adds Photos.app library
ingestion, search-match highlights, and a hover-expand for timeline
records.

### Added
- **Photos.app library ingestion** (`bunshin import-photos-app`).
  AppleScript pulls metadata (id, filename, date, GPS) for every media
  item in 200-item batches with progress reporting. Tested live on a
  2,725-item library — 1,113 items came back with GPS, so place-based
  recall ("沖縄 2023") works out of the box. Optional `--with-ocr`
  exports each item and routes it through the existing Vision OCR
  pipeline.
- **Search-match highlights** — query terms get wrapped in `<mark>`
  with a distinct amber style across results, expanded sessions, and
  the sibling chunks panel.

### Changed
- **Timeline records** now fade out at the bottom and expand on hover,
  so you can scan a day's full context just by moving the cursor.

## [0.3.0] - 2026-06-16

The "fill the gaps" release — broadens what Bunshin can actually
remember on macOS. Real-world stress-tested at 5,944 records across 7
sources.

### Added — ingestion
- **Apple Notes** via AppleScript (`bunshin import-notes`). No Full Disk
  Access required. Incremental: a per-note modification timestamp is
  stored in `settings` so subsequent runs only re-import changed notes.
  HTML body is converted to plain text and chunked. Handles both English
  and Japanese AppleScript date formats (Monterey+ space-after-日 included).
- **iMessage / SMS** via `~/Library/Messages/chat.db`
  (`bunshin import-imessage`). Joins messages with the handle (contact
  id) and chat (group name) tables; best-effort recovers text from
  `attributedBody` blobs on modern macOS where the plain `text` column
  is NULL. Surfaces a friendly Japanese error pointing to System
  Settings when Full Disk Access is missing.
- **Photos** with EXIF + macOS Vision OCR (`bunshin import-photos`).
  Extracts date, GPS, and camera via Pillow, and runs Japanese + English
  text recognition via a tiny swift program compiled once to
  `~/.bunshin/bin/bunshin-ocr`. Verified on 99 real images — 63
  contained recognized text (business cards, screenshots, quote PDFs).
- **Scanned-PDF OCR fallback** in the existing file ingester. PDFs with
  fewer than 20 average characters per page are re-processed through
  the swift Vision binary using PDFKit + CoreGraphics page rendering.

### Added — UI
- **📅 Timeline pane** grouping all records by local-date and source,
  with today / yesterday markers and per-source pill counts. Clicking a
  pill expands records inline. Backed by `/api/timeline` and
  `/api/timeline/day` endpoints.
- **New source filter chips** in the search pane: 📓 メモ帳, 💌 iMessage,
  📷 写真.

### Fixed
- File ingestion no longer indexes Python packaging artefacts
  (`top_level.txt`, `requires.txt`, `.egg-info/`, `.dist-info/`,
  `package-lock.json`, `yarn.lock`, `Cargo.lock`, `.bunshin/`).

### Known limitations
- **iMessage** requires Full Disk Access. The CLI surfaces a Japanese
  guide to System Settings → Privacy → Full Disk Access on failure.
- **Photos.app library** (`.photoslibrary` bundles) is not yet
  ingested — only loose image files under the given root.

## [0.2.0] - 2026-06-15

This release transforms Bunshin from a working prototype into a polished
desktop product. Highlights:

### Added — desktop & distribution
- **Native Mac app** (Electron 33). Splash, native menus following OS
  language, single-instance lock, persisted window geometry, dock icon,
  ⌘+K / ⌘+N / ⌘+R shortcuts.
- **Auto-update infrastructure** for users who install the DMG.
- **GitHub Actions CI/CD** building and uploading DMGs on tag push.
- **Linux scheduler support** — `bunshin install-scheduler` auto-detects
  macOS (launchd) / Linux+systemd (`systemctl --user`) / Linux+cron.

### Added — search & retrieval
- **Hybrid search** combining sqlite-vec semantic similarity with FTS5
  BM25 keyword scoring via reciprocal rank fusion (default mode).
- **Result deduplication** by source — at most one chunk per source_id by
  default, with `total_in_source` hint for "📚 N more in this conversation".
- **Source filter chips** — Claude / Gmail / files / memos / calendar /
  LINE / browser. Combinable with period filter.
- **Upgraded embedding model** to `intfloat/multilingual-e5-large` (1024d,
  ~2 GB) for materially better Japanese recall. `bunshin migrate-embeddings`
  command handles the transition.

### Added — chat
- **Multi-turn conversations** with persistent sessions in `chat_sessions`
  + `chat_messages` tables, sidebar UI with delete/resume, automatic title
  generation from the first user message.
- **Citation links** — assistant responses include `[1] [2]` markers that
  scroll to the corresponding context block.
- **Improved system prompt** that pushes the LLM to actively cite,
  surface dates, and avoid lazy "I have no information" replies.

### Added — ingestion
- **PDF and DOCX** files via pypdf / python-docx.
- **Browser history** for Safari / Chrome / Arc (reads via temp DB copy
  so it works while the browser is running). Incremental via watermark.
- **Audio transcription** (`bunshin transcribe`) with three backends
  (`faster-whisper`, `openai-whisper`, `whisper-cpp`).
- **Real-time file watching** via watchdog — file edits show up in search
  within seconds, no waiting for the hourly job.
- **Manual memos** via `bunshin note` or the chat input prefix
  `覚えといて:` / `メモ:`.

### Added — graph & insights
- **LLM-based entity discovery** — `bunshin graph discover` samples records
  and asks the local LLM to extract people / organizations / projects.
  Brought our local graph from 37 → 137 meaningful entities. Noise filter
  rejects single-letter tags and AI-tool names.
- **Specificity-scored entity relations** (specificity = co-occurrence
  divided by the related entity's total mentions).
- **AI-generated 7-day digest** in the Insights tab — Ollama produces a
  three-section Japanese summary of recent activity.

### Added — settings & ops
- **Settings UI** at the Web `⚙ 設定` tab, backed by a typed KV store
  (`settings.py`) for notifications, search defaults, chat defaults.
- **Automatic daily backups** (`VACUUM INTO` snapshots in
  `~/.bunshin/backups/`, retention default 7).
- **`bunshin doctor`** diagnoses DB / Ollama / Gmail / Calendar / MCP /
  scheduler and prints actionable remediation hints.
- **Cross-platform scheduler module** with launchd / systemd / cron paths.

### Fixed
- Menu language detection that defaulted to English on first launch
  (now refreshed inside `app.whenReady`).
- Knowledge graph SQL bug where the CTE referenced `v.distance` instead
  of the unprefixed alias post-join.
- Vector dimensions mismatch detection so `migrate-embeddings` reliably
  recognizes which model is currently active.

### Known limitations
- **macOS code signing** is not configured — first launch requires
  right-click → Open or running `xattr -dr com.apple.quarantine`.
- **Knowledge-graph relations** still include some lexical noise
  (use `bunshin graph cleanup`).
- **Whisper** requires a manual `pip install` of one of the three
  backends; we don't ship one by default.

## [0.1.0] - 2026-06-09

Initial release — Phase 0/1 prototype of the 4-condition personal
memory AI: local-first SQLite + sqlite-vec storage, AI-agnostic via
MCP, offline-capable via Ollama, omni-source ingestion of Claude
history / Gmail / files / calendar / LINE / manual memos.

See README for the design intent and the four conditions.
