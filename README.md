<div align="center">

# Bunshin Memory

### **Your past is yours. AI is just the lens.**

A **personal memory engine** that ingests your emails, files,
chats, notes, photos, and browser history — then lets any LLM you
choose read it, *locally*. Japanese-first.

> The CLI binary is still `bunshin` for backwards compatibility.
> "Bunshin Memory" is the product name; "Bunshin" alone gets
> confused with [bunshin.app](https://bunshin.app/) (a Claude
> Code desktop wrapper — different category, same anime root).

[![Latest release](https://img.shields.io/github/v/release/Marine923/bunshin-ai?style=for-the-badge&color=818cf8)](https://github.com/Marine923/bunshin-ai/releases/latest)
[![CI](https://img.shields.io/github/actions/workflow/status/Marine923/bunshin-ai/ci.yml?branch=main&style=for-the-badge&label=CI&color=5fbf6f)](https://github.com/Marine923/bunshin-ai/actions/workflows/ci.yml)
[![Platform](https://img.shields.io/badge/macOS-11%2B-lightgrey?style=for-the-badge)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-fbbf24?style=for-the-badge)](LICENSE)
[![Local-first](https://img.shields.io/badge/local--first-100%25-5fbf6f?style=for-the-badge)]()

[Download for macOS ↓](https://github.com/Marine923/bunshin-ai/releases/latest) &nbsp;·&nbsp;
[日本語版 README](./README.ja.md) &nbsp;·&nbsp;
[Architecture](./ARCHITECTURE.md) &nbsp;·&nbsp;
[Contributing](./CONTRIBUTING.md)

</div>

<p align="center">
  <img src="docs/demo.gif" width="800" alt="Bunshin in 9 seconds — search, relationships, chat" />
</p>

<!-- Three static stills below the animated demo, for context + alt text. -->
<p align="center">
  <img src="docs/screenshots/01-search-flashback.png" width="32%" alt="Today's flashback on the search tab" />
  <img src="docs/screenshots/02-relationships.png" width="32%" alt="Spider-web relationship graph" />
  <img src="docs/screenshots/03-chat.png" width="32%" alt="Local chat grounded in past memory" />
</p>

> ChatGPT and Claude are *personal assistants* — replaceable.
> Bunshin is your *brain's extension* — yours.

---

## Why Bunshin

Today's AI products tie your memory to the vendor:

- ChatGPT remembers you, but you can't take that memory elsewhere
- Claude has memory features, but only in Anthropic's ecosystem
- Mem0, Letta, etc. are cloud-based services by default (OSS self-host variants exist, but the hosted offering is the mainline product)

If your AI vendor changes pricing, shuts down, or you simply want to switch, **all your accumulated memory is gone**.

Bunshin inverts this: your memory lives on your machine, in a standard SQLite file. Any LLM that speaks the MCP protocol can use it. If Anthropic disappears tomorrow, your memory survives.

## Where Bunshin Memory fits

Bunshin Memory sits in a space that local-first AI projects are starting to converge on. We're not the only entrant:

- Stanford's open-source [OpenJarvis](https://github.com/Marqovo/OpenJarvis) covers similar local + AI-agnostic ground (English-first).
- [bunshin.app](https://bunshin.app/) (frankkk96 — same anime name, **different category**: a Tauri desktop wrapper that puts a UI around Claude Code for developers). If you came here looking for a coding-agent host, **that's the one you want, not this one**.

Bunshin Memory's differentiation is:

| Axis | Detail |
|---|---|
| 🇯🇵 Japanese-first sources | LINE chat history, iMessage, Photos.app albums + GPS clusters, Apple Notes — built for what Japanese users actually use day-to-day |
| 📸 Deep Photos integration | GPS-tagged photos auto-cluster into `place` entities (Wikipedia-resolved: 壱岐市 / Long-march City / etc.) and contiguous photo days collapse into trip events |
| 🕸 Knowledge graph with type colors | Entities color-coded by kind (person / place / organization / project / concept / tool) — visible at a glance |
| 🔌 MCP-native | Claude Code / Claude Desktop / any MCP client can call `search_memory`, `get_today_hero` and 5 other tools |
| 🔒 Local + offline-capable | SQLite + sqlite-vec for storage, Ollama for inference. Everything works without internet (cloud AI optional for the describe pass) |

---

## What it does

### 🔍 Search anything you've ever encountered
Hybrid (semantic + BM25) search across every record. Japanese and English. Source filters, period filters, click-to-expand whole sessions, click-the-badge for sibling chunks.

### 💬 Chat with offline LLM grounded in your past
Local Ollama with auto-injected past-record context. Citations link back to source records. No data leaves your machine.

### 💡 Auto-generated daily insights
Dormant projects, upcoming calendar events, recent file changes, pending questions from past assistants. One tab to start your day.

### 📅 Timeline
Every record grouped by day and source. Today / yesterday markers. Per-source pill icons (💬 Claude, 📧 Gmail, 📓 notes, 📷 photos, 🌐 browser …). Click a pill to drill into that day, hover a record to expand it.

### 🕸 Knowledge graph
LLM-extracted entities (people, projects, organizations) with specificity-scored relations.

### 🔁 Always up to date
File watcher catches edits in seconds. launchd / systemd / cron syncs every hour. Automatic daily backups (`VACUUM INTO`).

### 🤖 MCP for any AI
Claude Code, Claude Desktop, or any MCP-aware LLM can call **8 MCP tools** against your records: `search_memory`, `recall_session`, `get_flashback`, `list_top_entities`, `get_today_hero`, `get_recent_chat`, `pin_entity_context`, `get_server_info`.

### 📌 Pin off-screen reality
Some entities have a real-life role that doesn't show up in textual records (e.g. an island that hosts your e-commerce + drone services + ocean-education businesses, but your records mostly capture AI research chat). **Pin** a 1–2 sentence override on that entity from the relationships tab, settings list, CLI (`bunshin pin-context`), or MCP (`pin_entity_context`) — describe will treat it as a **hard constraint** on the next regeneration.

**Why it exists.** Bunshin Memory's describe pass reads what the records *say*, not what you actually *do*. If you spend Monday–Friday talking to Claude about AI research and Saturday–Sunday running your farm, your "farm" entity's records will be dominated by AI research context — the describe reflects that lopsidedness. A pin says "regardless of what the records imply, this entity is X" and every downstream consumer (relationships graph description, MCP `search_memory`, `get_today_hero` briefing, `list_top_entities` metadata) inherits your framing. Pins **round-trip** via `bunshin export-pins` / `import-pins` so you can carry your declared reality between machines.

---

## Ingestion sources (11 paths)

| Source | What goes in | Path |
|--------|--------------|------|
| 💬 Claude | Every Claude Code / Claude Desktop transcript | `~/.claude/projects/**/*.jsonl` |
| 📧 Gmail | Last 90 days of mail (incremental after that) | Gmail API + App Password |
| 📄 Files | `.md` / `.txt` / `.pdf` / `.docx` under a watched root | Walkable directory |
| 📓 Apple Notes | Every note from Notes.app via AppleScript (no FDA) | macOS only |
| 💌 iMessage / SMS | `chat.db` joined with handles + group names | macOS, FDA required |
| 📷 Photos | EXIF (date, GPS, camera) + macOS Vision OCR (JP + EN) | `~/Pictures` or any dir |
| 📷 Photos.app library | All media items from Photos.app via AppleScript | macOS only |
| 🌐 Browser | Safari / Chrome / Arc visit history | macOS |
| 📅 Calendar | Next 14 days from any iCal URL | iCloud, Google, etc. |
| 🔊 Audio | Whisper transcription (3 backends: faster-whisper, openai-whisper, whisper-cpp) | Any audio file |
| 💭 Manual | `bunshin note "…"` or `覚えといて: …` in chat | Anywhere |

PDFs without an embedded text layer (scanned documents) are automatically routed through macOS Vision OCR via PDFKit + CoreGraphics page rendering — including business cards, quote sheets, and receipts.

---

## Quick start

### Install the Mac app (recommended)

1. Download the latest DMG from [Releases](https://github.com/Marine923/bunshin-ai/releases/latest):
   - **Apple Silicon (M1/M2/M3/M4)**: `Bunshin-x.y.z-arm64.dmg`
   - **Intel Mac**: `Bunshin-x.y.z.dmg`
2. Open the DMG, drag Bunshin to `/Applications`.
3. First launch: right-click → Open (macOS quarantine).

The app handles initial setup, runs `bunshin web` in the background, and gives you the full UI immediately.

### Or install from source

```bash
git clone https://github.com/Marine923/bunshin-ai.git
cd bunshin
python3.11 -m venv ~/.bunshin/venv
~/.bunshin/venv/bin/pip install -e .

# Initialize
~/.bunshin/venv/bin/bunshin init

# Pull what you have (Claude history is the fastest first import)
~/.bunshin/venv/bin/bunshin import-claude
~/.bunshin/venv/bin/bunshin embed

# Open the web UI
~/.bunshin/venv/bin/bunshin web
# → http://127.0.0.1:8000

# Check setup health any time
~/.bunshin/venv/bin/bunshin doctor

# Clean up NER duplicates (e.g. "Bunshin" + "分身（Bunshin）" → one entity)
~/.bunshin/venv/bin/bunshin find-duplicates
~/.bunshin/venv/bin/bunshin merge-entities <source> <target> --dry-run
```

See [`docs/SETUP.md`](docs/SETUP.md) for Gmail, Calendar, Ollama, MCP, and scheduler setup.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ Entry points: CLI · Web UI · MCP server · Electron app   │
├──────────────────────────────────────────────────────────┤
│ Core: search · chat · insights · knowledge graph         │
├──────────────────────────────────────────────────────────┤
│ Storage: SQLite + sqlite-vec  (~/.bunshin/data.db)       │
│ Embeddings: intfloat/multilingual-e5-large (1024d, ONNX) │
│ Hybrid search: vector + FTS5 BM25 via reciprocal-rank    │
├──────────────────────────────────────────────────────────┤
│ Ingestion: Claude · Gmail · files · Notes · iMessage     │
│            photos · Photos.app · browser · calendar      │
│            audio · manual                                │
└──────────────────────────────────────────────────────────┘
        ↑                                          ↑
    Ollama (offline)                Claude / GPT / Gemini (via MCP)
```

Details in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Real-world numbers

A live install on the developer's MacBook holds:

```
Source          Records
─────────────  ────────
claude          ~2,400   conversation turns
gmail           ~1,650   messages
photos_app      ~2,700   media items (1,113 with GPS)
file              ~900   docs (.md, .txt, .pdf, .docx)
browser           ~600   visits
notes             ~490   Apple notes
photo              ~99   loose images (with OCR text)
manual              1
─────────────  ────────
Total           ~8,650   records
Embeddings      ~9,200   (1024-d, e5-large)
```

OCR on the photo set recovered, among other things, an entire DJI T25P quote sheet (¥4,028,264, with vendor address, item breakdown, and bank details) — fully searchable.

---

## Documentation

- [`docs/SETUP.md`](docs/SETUP.md) — Full setup guide
- [`docs/COMMANDS.md`](docs/COMMANDS.md) — All CLI commands
- [`docs/CLEANUP.md`](docs/CLEANUP.md) — Weekly DB maintenance cheatsheet
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Internal design
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — Common issues
- [`CHANGELOG.md`](CHANGELOG.md) — Release notes

---

## What's new in v0.10 (47 releases, two days)

The current minor version line is unusually deep — a tight feedback
loop with a single power user produced 47 patch releases across two
days. The **v0.10.42–46 arc** in particular represents a full
9-of-9 resolution of a structured 100-query evaluation the same user
ran against the app. Headline themes:

- **Retrieval quality: Honda 100-test 9/9 solved** (v0.10.42–46):
  - **Cascade retrieval** (v0.10.42) — auto-retry at min_relevance
    thresholds 20 → 10 → 0 when hit count is 0
  - **Temporal query router** (v0.10.43) — 「昨日」「3ヶ月前」等の
    time phrases がヒットするクエリで get_recent_chat / get_flashback
    への recall_suggestion を返す
  - **signal_score filter in flashback** (v0.10.44) — newsletter noise
    が朝の flashback を汚さないよう floor 30 でカット
  - **Cross-lingual query expansion** (v0.10.45) — LLM expand prompt
    が英↔日 相互翻訳を必ず含める形に (Iki Gold potato ↔ 壱岐黄金
    じゃがいも)
  - **Partial-match rerank boost** (v0.10.46) — 4+ token queries で
    ≥50% 一致に比例ブースト (`hits/total * 0.5`)、8-token 自然文で
    6/8 一致が 0 → +0.375 に
- **Bunshin Memory rename** (v0.10.27) — disambiguates from the
  similarly-named [bunshin.app](https://bunshin.app/) (a
  Tauri-based Claude Code wrapper, different category). The CLI
  binary stays `bunshin` for backwards compatibility.
- **Pin-context** (v0.10.28–32) — user-authored hard constraint
  on an entity's AI description, reachable from CLI / relationships
  tab / settings panel / MCP. Solves "the records reflect what I've
  been talking *about*, not what this entity actually *is*."
- **Nominatim geocoder + photos-relabel-places** (v0.10.23–26) —
  GPS-based place entities now use modern admin names (諫早市) instead
  of historical Wikipedia article titles (小栗村 (長崎県)) or building
  names (Barcelona City Hall).
- **Entity hygiene trio** (v0.10.18–19, v0.10.21) — `find-duplicates`
  detects NER variants, `merge-entities` collapses them, `doctor`
  surfaces the count so you know when cleanup is due.
- **MCP self-introspection** (v0.10.22) — `get_server_info`
  exposes record / entity / source counts so a connecting LLM can
  decide whether to lean on `search_memory` at all.
- **Entity-extraction prompt revamp** (v0.10.11–12) — startup
  migration heals existing miscategorized entities (websites flagged
  as places, software features flagged as places, ML concepts
  flagged as places).
- **Hidden Honda-DB cleanups already applied** — 8 photo place
  entities renamed via Nominatim, 5 merged into canonical forms,
  6 main-business entities pinned with off-screen reality.

---

## Testing

70 pytest cases run on every push against a matrix of Ubuntu × macOS × Python 3.10/3.11/3.12 (see the CI badge above). New v0.10 features have dedicated regression suites:

- `test_entity_hygiene.py` (4) — merge-entities SQL, find-duplicates normalize, pin round-trip, tool-keyword reclassify
- `test_pin_surfacing.py` (12) — pin-list endpoint, search_memory substring match, get_today_hero LIMIT+sort, list_top_entities batched lookup, export/import round-trip, cascade retrieval threshold order, temporal query router, flashback signal filter, bilingual expansion prompt, partial-match boost tiers
- `test_photos_place_regex.py` (4) — v0.10.14 dab-tail regex regression protection
- `test_doctor_json.py` (4) — public `--json` output contract

Plus the existing 46 covering storage, chunking, iMessage, PDF OCR, insights, notes, scheduler, knowledge graph. Run locally: `uv run pytest`.

---

## Status

```
Phase 0  Prototype                        ━━━━━━━━━━━━━━━━━━━━ 100%
Phase 1  MVP (search / chat / ingest)     ━━━━━━━━━━━━━━━━━━━━ 100%
Phase 2  Native Mac app (Electron)        ━━━━━━━━━━━━━━━━━━━━ 100%
Phase 3  Multi-source ingestion polish    ━━━━━━━━━━━━━━━━━━━━ 100%   ← v0.3.x
Phase 4  Pro / Team features              ░░░░░░░░░░░░░░░░░░░░   0%
```

### Known limitations

- **macOS only** for now. Linux scheduler exists (`systemd --user` / `cron`); UI works in any browser. Windows untested.
- **macOS code signing** not configured — first launch needs right-click → Open, or `xattr -dr com.apple.quarantine /Applications/Bunshin.app`.
- **iMessage requires Full Disk Access** on the terminal / Python process. The CLI prints a Japanese guide when it can't read `chat.db`.
- **Photos.app OCR** is opt-in via `--with-ocr` because each item has to be exported through Photos.app first (slow).
- **Whisper** backends need a separate `pip install` (we don't ship one by default).

---

## Customizing for your context

Bunshin ships with no personal data. To make the knowledge graph aware of your own organizations, places, and concepts, create `~/.bunshin/entities.json`:

```json
[
  {
    "name": "My Company",
    "type": "organization",
    "aliases": ["MyCo", "MCO"],
    "description": "My main company"
  },
  {
    "name": "Tokyo",
    "type": "place",
    "aliases": ["東京"]
  }
]
```

Then run `bunshin graph rebuild` to link existing records.

Types: `project`, `organization`, `person`, `place`, `tool`, `concept`, `topic`.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Contributing

Open issues for bugs and feature requests. PRs welcome — please discuss substantial changes in an issue first.

---

## Acknowledgments

Built on the shoulders of:
- [SQLite](https://sqlite.org) + [sqlite-vec](https://github.com/asg017/sqlite-vec)
- [FastEmbed](https://github.com/qdrant/fastembed) (ONNX, no torch)
- [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- [Ollama](https://ollama.com)
- [MCP](https://modelcontextprotocol.io/) protocol from Anthropic
- [Electron](https://www.electronjs.org/) + [electron-builder](https://www.electron.build/)
- macOS Vision framework (text recognition)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (used to write 90% of this)

---

## 日本語ドキュメント

完全な日本語版は [`README.ja.md`](README.ja.md)。
