# Changelog

All notable changes to Bunshin are documented in this file. The format is
roughly [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
