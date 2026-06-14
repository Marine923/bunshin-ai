# Bunshin (分身)

> **A personal memory engine where YOU are the protagonist, and AI is an interchangeable tool.**

ChatGPT and Claude are like personal assistants — replaceable.
Bunshin is like your brain's extension — not replaceable.

---

## The 4 Conditions (All Met)

| # | Condition | Description | Implementation |
|---|-----------|-------------|----------------|
| 1 | **Local-First** | All data stays on YOUR device | SQLite + sqlite-vec |
| 2 | **AI-Agnostic** | Works with any LLM (Claude, GPT, Gemini, Llama, ...) | MCP protocol |
| 3 | **Offline-Capable** | Functions without internet | Ollama integration |
| 4 | **Omni-Source** | Ingests email, files, conversations, calendar, chats | 6 ingestion paths |

**To our knowledge, no other product satisfies all 4 conditions** (as of 2026-06).

---

## Why this matters

Today's AI products tie your memory to the vendor:

- ChatGPT remembers you, but you can't take that memory elsewhere
- Claude has memory features, but only in Anthropic's ecosystem
- Mem0, Letta, etc. are cloud-based services

If your AI vendor changes pricing, shuts down, or you simply want to switch, **all your accumulated memory is gone**.

Bunshin inverts this: your memory lives on your machine, in a standard SQLite file. Any LLM that speaks the MCP protocol can use it. If Anthropic disappears tomorrow, your memory survives.

---

## What it does

- 🔍 **Semantic search** across past Claude conversations, emails, files, notes
- 💬 **Offline chat** powered by local LLM (Ollama) with past memory as context
- 💡 **Auto-generated insights**: dormant projects, upcoming events, unanswered questions
- 📝 **Capture anything**: `bunshin note "remember: ..."` or chat with `覚えといて: ...`
- 🔄 **Automatic ingestion** via launchd (every hour: Claude history + files + Gmail + calendar)
- 🤖 **MCP integration**: Claude Code / Claude Desktop can query bunshin as a tool
- 🕸 **Knowledge graph**: auto-extracted entities (people, projects, organizations) with co-occurrence relations

---

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/Marine923/bunshin-ai.git
cd bunshin
python3.11 -m venv ~/.bunshin/venv
~/.bunshin/venv/bin/pip install -e .

# 2. Initialize
~/.bunshin/venv/bin/bunshin init

# 3. Import your Claude Code history
~/.bunshin/venv/bin/bunshin import-claude
~/.bunshin/venv/bin/bunshin embed

# 4. Open the web UI
~/.bunshin/venv/bin/bunshin web
# → http://127.0.0.1:8000

# 5. Check setup health
~/.bunshin/venv/bin/bunshin doctor
```

See [`docs/SETUP.md`](docs/SETUP.md) for full setup (Gmail, Calendar, Ollama, MCP, launchd).

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│ Entry points: CLI / Web UI / MCP server              │
├──────────────────────────────────────────────────────┤
│ Core: search / chat / insights / knowledge graph     │
├──────────────────────────────────────────────────────┤
│ Storage: SQLite + sqlite-vec (~/.bunshin/data.db)    │
├──────────────────────────────────────────────────────┤
│ Ingestion: Claude / files / Gmail / calendar / LINE  │
└──────────────────────────────────────────────────────┘
       ↑                          ↑
   Ollama (offline)        Claude/GPT/Gemini (via MCP)
```

Details in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Documentation

- [`docs/SETUP.md`](docs/SETUP.md) — Full setup guide
- [`docs/COMMANDS.md`](docs/COMMANDS.md) — All CLI commands
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Internal design
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — Common issues

---

## Status & roadmap

This is an **early prototype**. Built in 2 days by one developer + Claude Code.

```
Phase 0 (1 week planned)    ━━━━━━━━━━━━━━━━━━━━ 100%  Prototype
Phase 1 (1 month planned)   ━━━━━━━━━━━━━━━━━━━━ 95%   MVP
Phase 2 (3 months planned)  ━━━━━━░░░░░░░░░░░░░░ 30%   Native app (Tauri)
Phase 3 (6 months planned)  ░░░░░░░░░░░░░░░░░░░░ 0%    OSS release polish
Phase 4 (12 months planned) ░░░░░░░░░░░░░░░░░░░░ 0%    Pro features, monetization
```

Known limitations:
- **macOS only** (launchd-specific automation). Linux/Windows support is a Phase 2 goal.
- No tests yet
- Ollama prompt engineering still being tuned
- Knowledge graph relations can have false positives (mitigated by specificity scoring)

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

This is a one-person prototype that just turned multi-person-eligible. Open issues for bugs and feature requests. PRs welcome but please discuss in an issue first.

---

## Acknowledgments

Built on the shoulders of:
- [SQLite](https://sqlite.org) + [sqlite-vec](https://github.com/asg017/sqlite-vec)
- [FastEmbed](https://github.com/qdrant/fastembed) (ONNX, no torch)
- [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- [Ollama](https://ollama.com)
- [MCP](https://modelcontextprotocol.io/) protocol from Anthropic
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (used to write 90% of this)

---

## 日本語ドキュメント

完全な日本語版は [`README.ja.md`](README.ja.md) （または上記の英語版を参照）。
