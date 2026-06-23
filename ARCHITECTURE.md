# Bunshin Architecture

A 10-minute read for anyone who wants to understand how Bunshin works
end-to-end, where to land a change, and why the design landed the way
it did.

## The 30-second summary

```
   ┌─────────────────────────────────────────────────────────┐
   │            Electron app (Bunshin.app)                    │
   │  ┌──────────────────────────────────────────────────┐    │
   │  │  Chromium renderer                              │    │
   │  │  · INDEX_HTML (single-file SPA)                 │    │
   │  │  · Search / Chat / Insights / Timeline / Graph  │    │
   │  └────────────────────────┬─────────────────────────┘    │
   │                           │ HTTP (127.0.0.1:8000)        │
   │  ┌────────────────────────▼─────────────────────────┐    │
   │  │  Bundled Python runtime (PyInstaller)            │    │
   │  │  uvicorn → FastAPI → bunshin.web.server          │    │
   │  └─────┬──────────────────┬─────────────────┬───────┘    │
   └────────┼──────────────────┼─────────────────┼────────────┘
            │                  │                 │
   ┌────────▼──────┐  ┌────────▼────────┐  ┌─────▼─────┐
   │  SQLite       │  │  Ollama         │  │ Importers │
   │  data.db      │  │  127.0.0.1:11434│  │ (Gmail,   │
   │  + sqlite-vec │  │  qwen2.5:32b    │  │  Photos,  │
   │  + FTS5       │  │  llama3.2:3b    │  │  Notes…)  │
   └───────────────┘  └─────────────────┘  └───────────┘
```

Everything inside the dotted box runs on the user's Mac. The two
external boxes Bunshin *might* talk to are user-configured imports
(Gmail IMAP, Google Calendar iCal) — and even those are read-only.

## The four-condition design

Bunshin promises four properties at once. Every architectural choice
exists to keep all four true at the same time:

| Property | What it means | Where you'll see it |
|---|---|---|
| **Local-first** | Data never leaves the Mac | SQLite on disk, Ollama for inference, IMAP not OAuth |
| **AI-agnostic** | Swap LLMs without touching ingestion | `chat.py` calls Ollama via HTTP; settings let you pick model |
| **Offline-capable** | Works on a plane | FastEmbed runs in-process, Ollama is local, no CDN scripts in `INDEX_HTML` |
| **Omni-source** | Any text the user generated | One small module per source in `ingestion/`, common `records` table |

If you propose a change that breaks any of these, you'll be asked
to justify it strongly. They're load-bearing.

## Module map

### `src/bunshin/web/server.py` (~6000 lines)
The whole web UI plus every JSON API. Deliberately a single file so
the server has **zero static asset dependencies** — the user gets one
Python process and one Chromium window, nothing else. JS / CSS / HTML
all live inside an `INDEX_HTML` string literal.

If this file scares you, read it tab-by-tab. Each `<section
class="pane">` has its own block of HTML, CSS, and JS.

### `src/bunshin/storage.py`
SQLite schema + every read/write helper. The `records` table is the
heart of Bunshin — every memory ends up here, regardless of source.
Vectors live in a separate `vec_records` virtual table (sqlite-vec).
Migrations are idempotent in `init_db()` — adding a column is safe.

### `src/bunshin/search.py`
Hybrid retrieval. For a query:
1. Embed the query (FastEmbed, multilingual-e5-large)
2. Vector search (top-K from `vec_records`)
3. FTS5 search (top-K from `records_fts`)
4. Reciprocal rank fusion → wide candidate list
5. (Optional) cross-encoder rerank → final ranking

### `src/bunshin/signals.py`
The "readability" layer that keeps email spam out of flashbacks.
`signal_score` is computed at insert time. Settings → 自動フィルター閾値
controls the cutoff.

### `src/bunshin/embeddings.py`
Thin wrapper around FastEmbed. The model (e5-large, 1024d) downloads
once on first launch to `~/.bunshin/models/`. After that, offline.

### `src/bunshin/ingestion/`
One file per source. Each module exports a single `import_<source>(conn, …)`
function that:
- Knows how to read its source (IMAP, file system, Photos.app DB, …)
- Chunks long content
- Deduplicates by content hash
- Inserts into the `records` table

Adding a new source means: write one file here, call it from
`cli.py`'s `import-<source>` command, add an icon entry to
`SOURCE_ICON_NAME` in `server.py`. That's the whole contract.

### `src/bunshin/knowledge_graph.py`
LLM-based entity extraction (Ollama, qwen2.5:14b by default) → fills
the `entities` and `record_entities` tables. Powers the 関係性 tab's
spider-web view.

### `src/bunshin/scheduler.py`
Installs / uninstalls the platform-native job that runs `bunshin
update` hourly (launchd on macOS, systemd timer on Linux, crontab as
fallback). Pure side-effects, no Bunshin imports.

### `src/bunshin/insights.py`
Generates the cards on the 気づき tab: 長期未活動プロジェクト,
直近の予定, 最近変更されたファイル, etc. All read-only against the DB.

### `electron-app/src/main.js`
Electron main process. Responsibilities:
- Spawn the bundled Python server
- Create the BrowserWindow, splash, tray
- Native macOS notifications (insights + morning flashback)
- IPC bridge (`bunshin:notify`)
- Auto-updater hookup

## Data flow: an import end-to-end

```
$ bunshin import-gmail
   │
   ├─► gmail.py: IMAP fetch, parse, extract Subject/From/Date
   │       │
   │       └─► storage.insert_record(source='gmail', timestamp=<email date>,
   │             content=<body>, metadata={from, subject, date})
   │
   ├─► signals.extract_sender + compute_signal_score
   │       (filled in lazily on next server start, or by `recompute-signals`)
   │
   ├─► embeddings.embed_passages(content) → 1024d vector
   │       │
   │       └─► storage.insert_vector(record_id, vector)
   │
   └─► knowledge_graph.extract_entities(content) (on `bunshin graph build`)
           │
           └─► entities + record_entities tables
```

## Data flow: a search end-to-end

```
User types "壱岐黄金プロジェクトの出荷時期" in the search box
   │
   ├─► GET /api/search?q=…&from=…
   │
   ├─► search.search() :
   │   ├─ embeddings.embed_query(q)
   │   ├─ vector search (sqlite-vec, top-50)
   │   ├─ FTS5 search (top-50)
   │   ├─ RRF fusion
   │   ├─ filter: signal_score > threshold, user_signal != 1
   │   └─ rerank (jina-reranker-v2) → top-10
   │
   └─► JSON back to the renderer
           │
           └─► renderResult() in INDEX_HTML draws cards with
               source icon, snippet, relevance score, mark button
```

## What lives where on disk

```
~/.bunshin/
  data.db                — main SQLite database
  data.db-wal / -shm     — SQLite WAL
  gmail.json             — Gmail App Password (chmod 600)
  calendar.json          — Google Calendar iCal URL
  backups/               — daily VACUUM INTO snapshots (last 7)
  logs/                  — update.out.log / update.err.log
  models/                — FastEmbed model cache
  venv/                  — (dev installs) virtualenv with bunshin
~/Library/LaunchAgents/
  com.bunshin.update.plist — launchd job for hourly auto-update
~/Library/Application Support/Bunshin/
  Local Storage/          — Electron-store (notifications setting,
                           last morning-flashback date, etc.)
```

`bunshin doctor` will print all the above and a health check.

## Why one big HTML file?

A lot of contributors will ask "why isn't this a React app?" The
answer is the four conditions again: a build pipeline means npm
install on first launch, a CDN for React, a bundler config to debug,
breakage on offline machines. The cost of a 6000-line `INDEX_HTML`
is small compared to that. It also means a curious user can View
Source and read the entire UI.

If we ever do need a build step, it's reversible (the API surface
stays the same). The default is no build.

## Where to land your change

| You want to… | Edit… |
|---|---|
| Add a new tab / pane | `INDEX_HTML` in `server.py` + add to `PANE_TITLES` |
| Change how chat answers | `chat.py` (prompt + Ollama call) |
| Add a new source | New file in `ingestion/`, register in `cli.py` |
| Tweak ranking | `search.py` + maybe `signals.py` |
| Add a setting | `settings.py` SCHEMA, `INDEX_HTML` form renders automatically |
| Add a native notification | `electron-app/src/main.js` |
| Add a CLI command | `cli.py` |

Welcome. 🌀
