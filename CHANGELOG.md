# Changelog

All notable changes to Bunshin are documented in this file. The format is
roughly [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
