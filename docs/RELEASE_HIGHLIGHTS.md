# Release Highlights — v0.10 series

The v0.10 minor version line was unusually deep — 54 patch releases across two days, driven by a tight feedback loop with a single power user. This document distills the arcs that mattered most.

---

## Arc 1: Honda 100-test resolution (v0.10.42 – v0.10.46)

A structured 100-query retrieval evaluation surfaced 9 distinct failure modes. Every one shipped a targeted fix — no follow-up gaps in the last review.

| # | Finding | Fix version |
|---|---------|-------------|
| A | `min_relevance` gate produced empty hits for descriptive queries | **v0.10.42** cascade retrieval — auto-retries 20 → 10 → 0 |
| B | Time phrases (`昨日`, `3ヶ月前`, `明日`) returned generic results | **v0.10.43** temporal query router — `recall_suggestion` field to MCP |
| C, D | Entity descriptions reflected what the user talked *about*, not what the entity *was* | v0.10.29-32 pin architecture (pre-arc) |
| E | Deck A duplicate entities | Already resolved, confirmed |
| F | Gmail newsletter noise contaminated flashback | **v0.10.44** `signal_score` filter (floor 30) |
| G | Cross-lingual retrieval — `Iki Gold potato` returned 0 hits on JP corpus | **v0.10.45** bilingual query expansion (EN↔JA required, `max_variants` 3→5) |
| H | 8+ token natural-sentence queries decayed to 0% relevance | **v0.10.46** partial-match rerank boost — 4+ tokens with ≥50% match get proportional boost |
| I | Pinned entities polluted unrelated searches | **v0.10.44** name-only substring match |

**All 9 resolved.** Full transcript: search commits `v0.10.42 (Honda A)` etc.

---

## Arc 2: β-distribution polish (v0.10.47 – v0.10.54)

Turned the "install → first search" path into something a non-technical β tester can complete without a terminal.

### Silent-failure detectors (v0.10.47, 49, 50, 51)

`bunshin doctor` shifted from a shallow "green if endpoints respond" check to a stack of specific probes for silent failures:

- **v0.10.47**: 4 new probes — embedding cache path & size, reranker cache, disk free space (`~/.bunshin` usage + mount capacity), runtime info (Python version / OS / arch) for bug reports
- **v0.10.49**: sqlite-vec extension load — was silently swallowed with `except: pass`, now **❌** escalated when vec search can't work
- **v0.10.50**: Ollama has models but *none* match `PREFERRED_MODELS` — flags the silent quality collapse where chat "works" but Japanese quality is poor
- **v0.10.51**: `--deep` flag runs end-to-end search (embed → vec → BM25 → rerank) on the real DB, reports timing, catches "green shallow / dead deep" divergence

### `bunshin warm` — the 5-10 minute silent freeze fix (v0.10.48, 52, 53)

Fresh installs silently download `intfloat/multilingual-e5-large` (~1 GB) + `jinaai/jina-reranker-v2-base-multilingual` (~1.1 GB) on first search. Prior to this arc there was no indication anything was happening.

- **v0.10.48**: `bunshin warm` CLI subcommand — explicit pre-download with per-stage timing
- **v0.10.52**: same flow exposed as `GET /api/models/status` + `POST /api/models/warm`, plus a settings-tab section "AI モデル準備" with a `🔥 モデルを事前 DL` button
- **v0.10.53**: onboarding wizard's final "準備できました" step now embeds the same button, pre-checks cache and shows "✓ 既に DL 済み" when the models already exist

Result: users go **install → wizard 5 steps → 1 click warm → search** without ever opening Terminal.

### Documentation & issue-reporting friction (v0.10.49, 54)

- **v0.10.49**: `docs/FOR_FRIENDS.md` install step 4 now includes the warm command; the distribution checklist adds warm+doctor gates
- **v0.10.54**: "困った時は" panel gains a "GitHub Issue に貼付済で開く" button. Diagnostics JSON is embedded as URL params (title + code-block body), truncated to 6000 chars if needed. Reduces issue submission from **5 steps** (fetch / copy / navigate / paste / write) to **2 steps** (fetch / click / write situation).

---

## By the numbers (v0.10 line, 2026-06-30 – 2026-07-01)

- **54 patch releases** over 2 days
- **75 pytest tests** (up from 46 pre-arc)
- **9 signed retrieval failure modes** resolved
- **10 β-distribution polish releases** stacked on top
- **Every release**: dual-architecture DMG (Intel + Apple Silicon) attached to GitHub Releases

---

## Related documents

- [CHANGELOG.md](../CHANGELOG.md) — full per-release notes
- [FOR_FRIENDS.md](FOR_FRIENDS.md) — β-tester distribution templates
- [ARCHITECTURE.md](ARCHITECTURE.md) — how the pieces fit together
- [README.md](../README.md#whats-new-in-v010-51-releases-two-days) — TL;DR of the arcs
