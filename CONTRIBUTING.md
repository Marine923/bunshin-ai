# Contributing to Bunshin Memory

Thanks for thinking about contributing — Bunshin Memory only gets useful if
more people can read its code, file good bug reports, and ship improvements.

This document is the shortest possible "how do I get my change in?" guide.
If anything here is wrong or unclear, please open an issue or a PR fixing
it — meta-contributions are very welcome.

## Quick start

```bash
# 1) Clone
git clone https://github.com/Marine923/bunshin-ai.git
cd bunshin-ai

# 2) Python side (CLI + FastAPI server)
python3 -m venv ~/.bunshin/venv
source ~/.bunshin/venv/bin/activate
pip install -e .

# 3) Electron side (desktop wrapper)
cd electron-app
npm install
cd ..

# 4) Run the server in dev mode
bunshin serve   # http://127.0.0.1:8000

# 5) Or run the full Electron app
cd electron-app && npm start
```

## Project layout

```
src/bunshin/
  cli.py              — `bunshin …` commands (Click)
  web/server.py       — FastAPI server + every page of the UI (yes, one file)
  storage.py          — SQLite schema, records / vectors / learning_rules
  search.py           — hybrid retrieval (vector + FTS5) + rerank
  signals.py          — readability score + content cleaner
  embeddings.py       — FastEmbed wrapper (multilingual-e5-large)
  ingestion/          — one file per source (gmail, claude_history, photos_app, …)
  knowledge_graph.py  — entity extraction + relationship table
  scheduler.py        — launchd / systemd / cron install helpers
  insights.py         — "気づき" tab generators
  rerank.py           — jina-reranker-v2 cross-encoder

electron-app/
  src/main.js         — Electron main process, tray, notifications
  src/preload.js      — IPC bridge
  src/splash.html     — startup splash
  build/              — DMG icons + iconTemplate.png for the tray

tests/                — pytest, run with `pytest`
docs/                 — long-form articles (SETUP.md etc.)
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for how these pieces talk to each
other and **why** the design landed where it did.

## Branches & PRs

- `main` is always shippable. Don't push directly.
- Branch off `main`, name it something like `fix/flashback-empty` or
  `feat/calendar-write`.
- One PR = one logical change. Don't fold UI polish into a bug fix.
- Reference the issue you're fixing in the PR description
  (`closes #42`).
- The PR template will ask you for screenshots when the change is
  user-visible — please include them.

## Coding style

### Python
- 4 spaces, `from __future__ import annotations` at the top of new files
- Type hints on function signatures
- Docstrings: a single short sentence is fine; the *why* matters more
  than the *what*
- Errors: catch only what you can recover from; let everything else
  surface

### JavaScript (Electron / `INDEX_HTML`)
- 2 spaces
- No build step. The whole web UI lives inline in `server.py`'s
  `INDEX_HTML` literal — by design, so that the server has zero static
  asset dependencies
- New JS goes in the same `<script>` block. Keep it readable; this isn't
  a place for clever
- Use the `icon('name', 14)` helper instead of emoji in system UI

### Comments
- Default to no comments. Self-explanatory code is better
- When you do comment, explain *why*, not *what* — assume the reader can
  read the next 5 lines

## Tests

```bash
pytest                   # run everything
pytest tests/test_search.py -k "vector"   # one test
```

The test suite covers storage, search, embeddings, ingestion edge cases.
UI changes are typically verified manually (Bunshin is GUI-heavy). Manual
verification steps should go in the PR description.

## Good first issues

Look for the [`good first issue`](https://github.com/Marine923/bunshin-ai/labels/good%20first%20issue)
label. These are scoped, well-defined tasks with someone on hand to review
quickly. If none are open, two safe starting points:

1. **Pick a TODO from the source** — `grep -rn "TODO\|XXX\|FIXME" src/`
2. **Improve documentation** — find something that confused you while
   reading and fix it

## Releasing (maintainers only)

1. Bump `pyproject.toml` + `electron-app/package.json`
2. Add a `## [x.y.z] - YYYY-MM-DD` block to `CHANGELOG.md`
3. `cd electron-app && npm run dist:mac` builds the two DMGs
4. `git tag vX.Y.Z && git push origin main vX.Y.Z`
5. `gh release create vX.Y.Z --notes-file <notes> <dmg-files…>`

## Questions

Open a GitHub Discussion or an Issue with the "question" template. We
try to respond within a week. For security issues, please email the
maintainer privately (see [README](./README.md#contact)).

Thanks again. 🌀
