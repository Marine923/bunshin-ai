"""FastAPI web server for Bunshin."""
import datetime
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from bunshin.search import search
from bunshin.storage import (
    DEFAULT_DB_PATH,
    apply_mark,
    count_records,
    count_vectors,
    get_session_records,
    hidden_count,
    init_db,
    init_vector_db,
    list_learning_rules,
    list_sources_with_counts,
    recompute_signals,
    reset_learning,
    undo_record_mark,
    undo_rule,
)


INDEX_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>分身（Bunshin）</title>
<style>
  /* ─────────────── Design tokens ───────────────
     Anchored on a Linear / Notion / Raycast palette: cool deep indigo
     backgrounds, near-white headings, indigo accent, sparing chroma. */
  :root {
    /* Dark theme — default. */
    --bg-0:         #0b0d12;  /* page background */
    --bg-1:         #11141b;  /* cards, panels */
    --bg-2:         #161a23;  /* hover state */
    --bg-3:         #1d2230;  /* expanded / nested */
    --border-1:     #1d2230;
    --border-2:     #262c3a;
    --text-1:       #f4f5f7;  /* primary heading */
    --text-2:       #c9cdd5;  /* body */
    --text-3:       #8a8f9c;  /* secondary */
    --text-4:       #5d6271;  /* hint / placeholder */
    --accent-1:     #818cf8;  /* primary indigo */
    --accent-2:     #a5b4fc;  /* lighter indigo */
    --accent-soft:  #1f2540;  /* selected chip bg */
    --warn:         #f59e0b;
    --good:         #34d399;
    --shadow-1:     0 1px 2px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.02);
    --radius-sm:    6px;
    --radius-md:    10px;
    --radius-lg:    14px;
    --radius-pill:  999px;
    color-scheme: dark;
  }
  /* Light theme — applied via .theme-light on <html>. Same token names
     so every component stays one var swap away from working. */
  :root.theme-light {
    --bg-0:         #ffffff;
    --bg-1:         #f6f7f9;
    --bg-2:         #eef0f4;
    --bg-3:         #e5e8ee;
    --border-1:     #e3e6ec;
    --border-2:     #cdd2db;
    --text-1:       #0f1117;
    --text-2:       #2c3140;
    --text-3:       #5a6376;
    --text-4:       #8b95a9;
    --accent-1:     #4f46e5;
    --accent-2:     #6366f1;
    --accent-soft:  #e7e9ff;
    --warn:         #d97706;
    --good:         #059669;
    --shadow-1:     0 1px 2px rgba(15,17,23,0.06), 0 0 0 1px rgba(15,17,23,0.04);
    color-scheme: light;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    height: 100%;
    overflow: hidden;
  }
  /* Custom scrollbars (Chromium / Electron) so the gray OS bar doesn't
     clash with the indigo palette. Firefox falls back to scrollbar-color. */
  * {
    scrollbar-width: thin;
    scrollbar-color: rgba(129,140,248,0.28) transparent;
  }
  *::-webkit-scrollbar {
    width: 10px;
    height: 10px;
  }
  *::-webkit-scrollbar-track {
    background: transparent;
  }
  *::-webkit-scrollbar-thumb {
    background: rgba(129,140,248,0.22);
    border-radius: 10px;
    border: 2px solid transparent;
    background-clip: padding-box;
  }
  *::-webkit-scrollbar-thumb:hover {
    background: rgba(129,140,248,0.40);
    background-clip: padding-box;
  }
  *::-webkit-scrollbar-corner { background: transparent; }
  /* Help modal (⌘+/) */
  .help-modal {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    backdrop-filter: blur(4px);
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    animation: help-fade-in 0.14s ease;
  }
  @keyframes help-fade-in {
    from { opacity: 0; }
    to   { opacity: 1; }
  }
  .help-modal-card {
    background: var(--bg-1);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-lg);
    box-shadow: 0 20px 60px rgba(0,0,0,0.7);
    width: 100%;
    max-width: 560px;
    max-height: 80vh;
    overflow-y: auto;
  }
  .help-modal-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 22px;
    border-bottom: 1px solid var(--border-1);
  }
  .help-modal-head h2 {
    margin: 0;
    font-size: 16px;
    color: var(--text-1);
    font-weight: 600;
  }
  .help-modal-close {
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    color: var(--text-2);
    border-radius: 50%;
    width: 28px;
    height: 28px;
    font-size: 14px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
  }
  .help-modal-close:hover { background: var(--bg-3); color: var(--text-1); }
  .help-modal-body { padding: 18px 22px; }
  .help-section { margin-bottom: 20px; }
  .help-section:last-child { margin-bottom: 0; }
  .help-section-title {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-3);
    margin-bottom: 10px;
    font-weight: 600;
  }
  .help-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    font-size: 13px;
    color: var(--text-2);
  }
  .help-row span:not(.help-tip) {
    margin-left: 8px;
    color: var(--text-2);
  }
  .help-row .help-tip {
    color: var(--text-3);
    font-size: 13px;
  }
  .help-row .help-tip code {
    background: var(--bg-2);
    color: var(--accent-2);
    padding: 1px 6px;
    border-radius: 4px;
    font-family: ui-monospace, monospace;
    font-size: 12px;
  }
  kbd {
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    border-bottom-width: 2px;
    color: var(--text-1);
    padding: 1px 8px;
    border-radius: 4px;
    font-family: -apple-system, "Hiragino Sans", sans-serif;
    font-size: 12px;
    min-width: 24px;
    text-align: center;
    box-shadow: 0 1px 0 rgba(0,0,0,0.4);
  }
  /* Skeleton placeholder for any "Loading…" surface. */
  .skeleton {
    background: linear-gradient(
      90deg,
      var(--bg-1) 0%,
      var(--bg-2) 50%,
      var(--bg-1) 100%
    );
    background-size: 200% 100%;
    animation: skeleton-pulse 1.4s ease-in-out infinite;
    border-radius: 6px;
    color: transparent;
    user-select: none;
    pointer-events: none;
  }
  @keyframes skeleton-pulse {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
  .skeleton-line {
    height: 14px;
    margin: 8px 0;
    border-radius: 4px;
  }
  .skeleton-line.short { width: 40%; }
  .skeleton-line.medium { width: 70%; }
  .skeleton-line.long { width: 92%; }
  .skeleton-card {
    padding: 16px;
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
    margin-bottom: 8px;
  }
  body {
    background: var(--bg-0);
    color: var(--text-2);
    font-family: "Inter", "SF Pro Text", -apple-system, "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif;
    line-height: 1.55;
    font-size: 14px;
    -webkit-text-size-adjust: 100%;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    font-feature-settings: "cv11", "ss01";
    display: flex;
  }
  /* ── Sidebar (Discord / Linear style) ── */
  aside.sidebar {
    width: 60px;
    flex-shrink: 0;
    background: var(--bg-1);
    border-right: 1px solid var(--border-1);
    display: flex;
    flex-direction: column;
    align-items: center;
    /* Top padding leaves room for the macOS traffic lights. */
    padding: 38px 0 14px;
    -webkit-app-region: drag;
  }
  aside.sidebar > * { -webkit-app-region: no-drag; }
  .sidebar-logo {
    width: 36px;
    height: 36px;
    border-radius: 9px;
    overflow: hidden;
    margin-bottom: 22px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.04);
    line-height: 0;
  }
  .sidebar-logo svg { width: 100%; height: 100%; display: block; }
  .sidebar-nav {
    display: flex;
    flex-direction: column;
    gap: 4px;
    align-items: center;
  }
  .sidebar-tab {
    position: relative;
    width: 40px;
    height: 40px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    border-radius: 10px;
    color: var(--text-3);
    background: transparent;
    border: 0;
    padding: 0;
    transition: color 0.18s ease, background 0.18s ease, transform 0.12s ease;
    font: inherit;
  }
  .sidebar-tab svg {
    width: 18px;
    height: 18px;
    transition: transform 0.18s ease;
  }
  .sidebar-tab:hover {
    color: var(--text-1);
    background: var(--bg-2);
  }
  .sidebar-tab:hover svg {
    transform: scale(1.08);
  }
  .sidebar-tab.active {
    color: var(--accent-2);
    background: var(--accent-soft);
  }
  /* Tooltip on the right side of each pill. */
  .sidebar-tab::after {
    content: attr(data-tooltip);
    position: absolute;
    left: calc(100% + 14px);
    top: 50%;
    transform: translateY(-50%) translateX(-6px);
    background: var(--bg-3);
    border: 1px solid var(--border-2);
    color: var(--text-1);
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.14s ease, transform 0.14s ease;
    box-shadow: 0 6px 18px rgba(0,0,0,0.5);
    z-index: 200;
  }
  .sidebar-tab:hover::after {
    opacity: 1;
    transform: translateY(-50%) translateX(0);
  }
  /* ── Main area (right of the sidebar) ── */
  .main-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
  }
  header {
    padding: 14px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    background: var(--bg-0);
    -webkit-app-region: drag;
    flex-shrink: 0;
  }
  header > * { -webkit-app-region: no-drag; }
  h1 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    letter-spacing: -0.005em;
    color: var(--text-1);
  }
  .stats {
    font-size: 12px;
    color: var(--text-3);
    font-variant-numeric: tabular-nums;
  }
  .header-right {
    display: flex;
    align-items: center;
    gap: 14px;
  }
  /* Theme toggle */
  .theme-toggle {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    color: var(--text-2);
    width: 32px;
    height: 32px;
    border-radius: 8px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    transition: background 0.15s ease, color 0.15s ease, transform 0.18s ease;
  }
  .theme-toggle:hover { background: var(--bg-3); color: var(--text-1); transform: rotate(15deg); }
  .theme-icon { width: 15px; height: 15px; }
  /* Add-memory button (header right) */
  .add-memory-btn {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    color: var(--text-1);
    height: 32px;
    padding: 0 12px;
    border-radius: 8px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 500;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
  }
  .add-memory-btn:hover { background: var(--bg-3); color: var(--text-0); border-color: var(--border-2); }
  .add-memory-btn svg { width: 14px; height: 14px; stroke-width: 2.2; }
  @media (max-width: 640px) {
    .add-memory-btn .add-memory-label { display: none; }
    .add-memory-btn { padding: 0; width: 32px; justify-content: center; }
  }
  /* Add-memory modal */
  .add-memory-modal {
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: 14px;
    padding: 22px;
    width: min(480px, calc(100vw - 40px));
    box-shadow: 0 20px 60px rgba(0,0,0,0.45);
  }
  .add-memory-modal h3 { margin: 0 0 6px; font-size: 16px; color: var(--text-0); }
  .add-memory-modal .sub { margin: 0 0 14px; font-size: 12px; color: var(--text-3); }
  .add-memory-modal textarea {
    width: 100%;
    min-height: 140px;
    padding: 12px;
    border: 1px solid var(--border-1);
    border-radius: 8px;
    background: var(--bg-0);
    color: var(--text-0);
    font: inherit;
    font-size: 14px;
    line-height: 1.6;
    resize: vertical;
    box-sizing: border-box;
  }
  .add-memory-modal textarea:focus {
    outline: none;
    border-color: var(--accent, #6a6dff);
    box-shadow: 0 0 0 3px rgba(106,109,255,0.12);
  }
  .add-memory-modal .actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 14px; }
  .add-memory-modal .btn { padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-1); background: var(--bg-2); color: var(--text-0); font-size: 13px; cursor: pointer; }
  .add-memory-modal .btn:hover { background: var(--bg-3); }
  .add-memory-modal .btn.primary { background: linear-gradient(135deg, #4c4d8a, #3b3f7a); border-color: transparent; color: #fff; }
  .add-memory-modal .btn.primary:hover { filter: brightness(1.1); }
  .add-memory-modal .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .add-memory-modal .status { margin-top: 10px; font-size: 12px; color: var(--text-3); min-height: 16px; }
  .add-memory-modal .status.success { color: #58cc6e; }
  .add-memory-modal .status.error { color: #ff6b6b; }
  /* In-app tour (post-onboarding) */
  .tour-backdrop {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.65);
    z-index: 9998;
    display: flex; align-items: center; justify-content: center;
    animation: fadeIn 0.2s ease;
  }
  @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
  .tour-card {
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: 16px;
    padding: 28px 28px 22px;
    max-width: 420px;
    width: calc(100% - 40px);
    text-align: center;
    box-shadow: 0 24px 80px rgba(0,0,0,0.5);
    animation: tourPop 0.25s cubic-bezier(0.2, 0.9, 0.3, 1.4);
  }
  @keyframes tourPop { from { opacity: 0; transform: scale(0.92); } to { opacity: 1; transform: scale(1); } }
  .tour-card .tour-icon {
    width: 48px; height: 48px;
    margin: 0 auto 14px;
    border-radius: 12px;
    background: linear-gradient(135deg, #4c4d8a 0%, #3b3f7a 100%);
    color: #fff;
    display: flex; align-items: center; justify-content: center;
  }
  .tour-card .tour-icon svg { width: 24px; height: 24px; stroke-width: 2; }
  .tour-card h3 { margin: 0 0 10px; font-size: 18px; font-weight: 600; color: var(--text-0); }
  .tour-card p { margin: 0 0 18px; font-size: 14px; line-height: 1.65; color: var(--text-2); }
  .tour-card .tour-dots { display: flex; justify-content: center; gap: 6px; margin-bottom: 16px; }
  .tour-card .tour-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--border-1); }
  .tour-card .tour-dot.active { background: var(--accent-1, #6a6dff); transform: scale(1.2); }
  .tour-card .tour-dot.done { background: var(--text-3); }
  .tour-card .tour-actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
  .tour-card .tour-skip {
    background: none; border: none;
    color: var(--text-3); font-size: 12px;
    cursor: pointer; padding: 6px 10px;
  }
  .tour-card .tour-skip:hover { color: var(--text-1); }
  .tour-card .tour-next {
    background: linear-gradient(135deg, #4c4d8a 0%, #3b3f7a 100%);
    color: #fff; border: none;
    padding: 10px 20px; border-radius: 8px;
    font-size: 13px; font-weight: 500; cursor: pointer;
    transition: filter 0.15s;
  }
  .tour-card .tour-next:hover { filter: brightness(1.12); }
  /* Dark mode shows the sun (switch to light); light mode shows the moon. */
  :root .theme-icon-light { display: none; }
  :root.theme-light .theme-icon-dark { display: none; }
  :root.theme-light .theme-icon-light { display: inline-block; }
  main {
    flex: 1;
    overflow-y: auto;
    padding: 26px 32px;
  }
  main > .pane {
    max-width: 920px;
    margin: 0 auto;
  }
  /* Chat tab fills the whole content area — no gap between left nav and history panel. */
  body.chat-mode main { padding: 0; }
  body.chat-mode main > .pane { max-width: none; margin: 0; }
  @media (max-width: 640px) {
    aside.sidebar { width: 52px; padding-top: 30px; }
    header { padding: 12px 16px; }
    main { padding: 18px 16px; }
  }
  .pane { display: none; }
  .pane.active { display: block; }

  /* ── Search pane ── */
  .search-box {
    width: 100%;
    padding: 16px 20px;
    font-size: 16px;
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
    color: var(--text-1);
    outline: none;
    transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
    font-family: inherit;
    box-shadow: var(--shadow-1);
  }
  .search-box::placeholder { color: var(--text-4); }
  .search-box:hover { background: var(--bg-2); }
  .search-box:focus {
    border-color: var(--accent-1);
    background: var(--bg-1);
    box-shadow: 0 0 0 3px rgba(129,140,248,0.18);
  }
  /* Autocomplete dropdown attached to the search box. */
  .autocomplete-anchor { position: relative; }
  .autocomplete-dropdown {
    position: absolute;
    top: -8px;
    left: 0;
    right: 0;
    z-index: 30;
    background: var(--bg-1);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-md);
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    max-height: 320px;
    overflow-y: auto;
    display: none;
    padding: 6px 0;
  }
  .autocomplete-dropdown.shown { display: block; }
  .autocomplete-section-title {
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-4);
    padding: 8px 14px 4px;
  }
  .autocomplete-item {
    padding: 8px 14px;
    cursor: pointer;
    color: var(--text-2);
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 13px;
    transition: background 0.1s ease;
  }
  .autocomplete-item:hover,
  .autocomplete-item.active {
    background: var(--bg-2);
    color: var(--text-1);
  }
  .autocomplete-item .ac-icon {
    color: var(--text-4);
    font-size: 12px;
  }
  .autocomplete-item .ac-label {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .autocomplete-item .ac-hint {
    font-size: 10.5px;
    color: var(--text-4);
    margin-left: auto;
  }
  .hint { margin-top: 12px; color: var(--text-4); font-size: 13px; }
  .filter-row {
    margin-top: 16px;
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    align-items: center;
    font-size: 13px;
    color: var(--text-3);
  }
  .filter-row select {
    background: var(--bg-1);
    color: var(--text-1);
    border: 1px solid var(--border-2);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    cursor: pointer;
    font-family: inherit;
  }
  .filter-row select:focus { outline: none; border-color: var(--accent-1); }
  .chips-row { display: flex; flex-wrap: wrap; gap: 6px; }
  .filter-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 10px;
    background: var(--bg-1);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-pill);
    font-size: 12px;
    color: var(--text-2);
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
  }
  .filter-chip svg { color: var(--text-3); flex-shrink: 0; }
  .filter-chip:hover svg, .filter-chip.active svg { color: var(--accent-2); }
  .filter-chip:hover { background: var(--bg-2); color: var(--text-1); }
  .filter-chip.active {
    background: var(--accent-1);
    border-color: var(--accent-1);
    color: #fff;
    font-weight: 600;
    box-shadow: 0 1px 3px rgba(106,109,255,0.35);
  }
  .filter-chip.active svg { color: #fff; }
  :root.theme-light .filter-chip.active { color: #fff; }
  :root.theme-light .filter-chip.active svg { color: #fff; }
  /* Dim source chips that have zero records in the current DB. */
  .filter-chip.chip-empty { opacity: 0.4; }
  .filter-chip.chip-empty:hover { opacity: 0.7; }

  /* ── Inline SVG icon layout helpers (used everywhere) ── */
  /* Settings section headers: "<icon> Backup" etc. */
  .settings-section h2 {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .settings-section h2 .h2-icon {
    display: inline-flex;
    align-items: center;
    color: var(--accent-2);
  }
  /* Timeline source pills (used inside timeline day cards) */
  .src-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .src-pill svg { color: var(--text-3); flex-shrink: 0; }
  /* Flashback source line: "<icon> Claude · 他 117 件" */
  .fb-source svg { color: var(--text-3); margin-right: 2px; vertical-align: -2px; }
  .flashback-result-meta svg { color: var(--text-3); margin-right: 3px; vertical-align: -2px; }
  /* Mark / hide button — replaces the 🗑 emoji */
  .card-hide-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  /* Learning-rule icon column */
  .rule-row .rule-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--text-3);
  }
  /* Wizard warning banner: icon + body in a row */
  .onboarding-content .step-warn {
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }
  .onboarding-content .step-warn .warn-icon {
    flex-shrink: 0;
    color: #c98000;
    margin-top: 1px;
  }
  :root.theme-light .onboarding-content .step-warn .warn-icon { color: #b45309; }
  /* ── Privacy panel (settings → プライバシー) ── */
  .privacy-hero {
    background: var(--accent-soft);
    border: 1px solid var(--accent-1);
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 16px;
  }
  .privacy-promise {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14.5px;
    color: var(--text-1);
    margin-bottom: 4px;
  }
  .privacy-promise svg { color: #5fbf6f; flex-shrink: 0; }
  .privacy-note {
    font-size: 12.5px;
    color: var(--text-3);
    line-height: 1.6;
    margin: 0;
  }
  .privacy-grid {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 18px;
  }
  .privacy-row {
    display: grid;
    grid-template-columns: 200px 1fr;
    gap: 14px;
    align-items: start;
    padding: 8px 0;
    border-bottom: 1px solid var(--border-1);
  }
  .privacy-row:last-child { border-bottom: 0; }
  .privacy-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12.5px;
    color: var(--text-3);
    font-weight: 500;
  }
  .privacy-label svg { color: var(--text-4); flex-shrink: 0; }
  .privacy-value {
    font-size: 12.5px;
    color: var(--text-1);
    word-break: break-all;
  }
  .privacy-value code {
    background: var(--bg-2);
    padding: 2px 7px;
    border-radius: 5px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11.5px;
  }
  .privacy-muted {
    color: var(--text-4);
    font-size: 11.5px;
    margin-left: 8px;
  }
  .privacy-ok { color: #5fbf6f; }
  .privacy-warn { color: #efaf4a; }
  .privacy-section-title {
    margin: 18px 0 8px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-2);
  }
  .privacy-zero {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 14px;
    background: var(--bg-2);
    border-radius: 8px;
    font-size: 12.5px;
    color: var(--text-1);
  }
  .privacy-zero svg { color: #5fbf6f; flex-shrink: 0; }
  .privacy-outbound {
    background: var(--bg-2);
    border-radius: 8px;
    padding: 12px 14px;
  }
  .privacy-conn {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 6px 0;
    font-size: 12.5px;
    color: var(--text-1);
  }
  .privacy-conn svg { color: var(--text-3); flex-shrink: 0; margin-top: 3px; }
  .privacy-conn code {
    background: var(--bg-0);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11.5px;
  }
  .privacy-footnote {
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid var(--border-1);
  }
  .privacy-footnote p {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    margin: 4px 0;
    font-size: 11.5px;
    color: var(--text-3);
    line-height: 1.6;
  }
  .privacy-footnote svg { color: #c98000; margin-top: 3px; flex-shrink: 0; }
  :root.theme-light .privacy-footnote svg { color: #b45309; }
  .privacy-footnote code {
    background: var(--bg-2);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 11px;
  }

  /* Model recommendation banner (settings → chat → preferred model) */
  .model-rec-loading {
    margin-top: 8px;
    padding: 8px 12px;
    background: var(--bg-2);
    border-radius: 8px;
    font-size: 12px;
    color: var(--text-3);
  }
  .model-rec {
    margin-top: 8px;
    padding: 12px 14px;
    background: var(--accent-soft);
    border: 1px solid var(--accent-1);
    border-radius: 8px;
    font-size: 12.5px;
    color: var(--text-1);
  }
  .model-rec-head {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
    font-size: 13.5px;
  }
  .model-rec-head svg { color: var(--accent-2); flex-shrink: 0; }
  .model-rec-head b { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .model-rec-ram { color: var(--text-3); font-size: 11.5px; margin-left: 4px; }
  .model-rec-why { color: var(--text-2); font-size: 12px; margin-bottom: 8px; }
  .model-rec-installed {
    display: flex; align-items: center; gap: 5px;
    color: #5fbf6f;
    font-size: 11.5px;
  }
  .model-rec-install {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11.5px;
    color: var(--text-2);
    flex-wrap: wrap;
  }
  .model-rec-install code {
    background: var(--bg-0);
    padding: 3px 8px;
    border-radius: 5px;
    border: 1px solid var(--border-1);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11.5px;
  }
  .copy-btn-mini {
    background: transparent;
    border: 1px solid var(--border-2);
    color: var(--text-3);
    padding: 3px 8px;
    border-radius: 5px;
    font-size: 11px;
    cursor: pointer;
    font-family: inherit;
    transition: background 0.15s, color 0.15s;
  }
  .copy-btn-mini:hover { background: var(--bg-2); color: var(--text-1); }

  /* Inline tip icon (used in chat empty state, settings tips, etc.) */
  .inline-tip-icon {
    width: 13px;
    height: 13px;
    color: #c98000;
    vertical-align: -2px;
    margin-right: 4px;
    flex-shrink: 0;
  }
  :root.theme-light .inline-tip-icon { color: #b45309; }
  /* Wizard tip bullets in the final step */
  .onboarding-content .step-tips {
    list-style: none;
    padding: 0;
    margin: 12px 0 0;
    font-size: 12.5px;
    color: var(--text-3);
  }
  .onboarding-content .step-tips li {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin: 4px 0;
    line-height: 1.6;
  }
  .onboarding-content .step-tips li svg {
    flex-shrink: 0;
    margin-top: 3px;
    color: #c98000;
  }
  :root.theme-light .onboarding-content .step-tips li svg { color: #b45309; }

  /* ── Flashback widget (Bunshin's signature daily reminder) ── */
  .flashback-section {
    margin: 22px 0 18px;
    padding: 16px 0 4px;
    border-top: 1px solid var(--border-1);
  }
  .flashback-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
    font-size: 13px;
    flex-wrap: wrap;
  }
  .flashback-icon { width: 18px; height: 18px; color: var(--accent-1); flex-shrink: 0; }
  .flashback-title { font-weight: 600; color: var(--text-1); font-size: 14px; }
  .flashback-sub { color: var(--text-3); font-size: 12px; }
  .flashback-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
  }
  @media (max-width: 760px) {
    .flashback-grid { grid-template-columns: 1fr; }
  }
  .flashback-card {
    padding: 13px 14px 12px;
    border-radius: 10px;
    border: 1px solid var(--border-1);
    background: var(--bg-0);
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-height: 130px;
    transition: border-color 0.18s, transform 0.18s, box-shadow 0.18s;
  }
  .flashback-card:hover {
    border-color: var(--accent-1);
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(0,0,0,0.08);
    cursor: pointer;
  }
  .flashback-card .fb-when {
    font-size: 11px;
    color: var(--accent-2);
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .flashback-card .fb-date {
    font-size: 11px;
    color: var(--text-4);
    font-variant-numeric: tabular-nums;
    margin-top: -2px;
  }
  .flashback-card .fb-preview {
    font-size: 12.5px;
    color: var(--text-1);
    line-height: 1.55;
    flex: 1;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 4;
    -webkit-box-orient: vertical;
    margin: 4px 0 2px;
  }
  .flashback-card .fb-source {
    font-size: 11px;
    color: var(--text-3);
    margin-top: auto;
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .flashback-card .fb-empty {
    font-size: 12px;
    color: var(--text-4);
    font-style: italic;
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  /* ── Mark / learning action button on cards ── */
  .card-hide-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 22px;
    height: 22px;
    line-height: 18px;
    border-radius: 6px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-4);
    font-size: 13px;
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.15s, background 0.15s, color 0.15s, border-color 0.15s;
    padding: 0;
    z-index: 2;
  }
  .flashback-card { position: relative; }
  .flashback-card:hover .card-hide-btn,
  .flashback-result:hover .card-hide-btn { opacity: 1; }
  .card-hide-btn:hover {
    background: var(--bg-2);
    border-color: var(--border-2);
    color: var(--text-1);
  }
  /* Re-purpose the same look inside a flashback result row */
  .flashback-result { position: relative; }
  .flashback-result .card-hide-btn { top: 10px; right: 10px; }

  /* ── Mark modal ── */
  .mark-modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.55);
    backdrop-filter: blur(2px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  :root.theme-light .mark-modal-backdrop { background: rgba(0,0,0,0.30); }
  .mark-modal {
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: 12px;
    padding: 22px 24px;
    width: min(440px, 92vw);
    box-shadow: 0 14px 40px rgba(0,0,0,0.5);
  }
  .mark-modal h3 {
    margin: 0 0 6px;
    font-size: 16px;
    font-weight: 600;
    color: var(--text-1);
  }
  .mark-modal-sub {
    margin: 0 0 16px;
    font-size: 12.5px;
    color: var(--text-3);
    line-height: 1.5;
  }
  .mark-scope {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    margin-bottom: 6px;
    transition: background 0.15s;
    font-size: 13px;
  }
  .mark-scope:hover { background: var(--bg-2); }
  .mark-scope input[type="radio"] { margin-top: 2px; accent-color: var(--accent-1); }
  .mark-scope .label-line { flex: 1; }
  .mark-scope .scope-title { color: var(--text-1); font-weight: 500; }
  .mark-scope .scope-hint { color: var(--text-3); font-size: 11.5px; margin-top: 2px; }
  .mark-scope.recommended .scope-title::after {
    content: "おすすめ";
    margin-left: 6px;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 4px;
    background: var(--accent-soft);
    color: var(--accent-2);
    font-weight: 500;
  }
  .mark-scope.disabled { opacity: 0.4; pointer-events: none; }
  .mark-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
  .mark-actions button {
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    border: 1px solid var(--border-2);
    background: transparent;
    color: var(--text-1);
    transition: background 0.15s, border-color 0.15s;
    font-family: inherit;
  }
  .mark-actions .btn-cancel:hover { background: var(--bg-2); }
  .mark-actions .btn-apply {
    background: var(--accent-soft);
    border-color: var(--accent-1);
    color: var(--text-1);
    font-weight: 500;
  }
  .mark-actions .btn-apply:hover { background: var(--accent-1); color: #fff; }

  /* ── Undo toast ── */
  .undo-toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--bg-3);
    border: 1px solid var(--border-2);
    border-radius: 10px;
    padding: 12px 16px;
    display: flex;
    align-items: center;
    gap: 14px;
    font-size: 13px;
    color: var(--text-1);
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    z-index: 1100;
    animation: undo-slide-in 0.18s ease-out;
  }
  @keyframes undo-slide-in {
    from { transform: translate(-50%, 20px); opacity: 0; }
    to   { transform: translate(-50%, 0); opacity: 1; }
  }
  .undo-toast .undo-btn {
    background: transparent;
    border: 1px solid var(--accent-1);
    color: var(--accent-2);
    padding: 5px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12.5px;
    font-family: inherit;
    transition: background 0.15s;
  }
  .undo-toast .undo-btn:hover { background: var(--accent-soft); }
  .undo-toast .undo-countdown {
    font-variant-numeric: tabular-nums;
    color: var(--text-4);
    font-size: 11.5px;
    min-width: 28px;
    text-align: right;
  }

  /* ── Learning dashboard (settings tab) ── */
  .learning-dashboard {
    margin-top: 20px;
    padding-top: 18px;
    border-top: 1px solid var(--border-1);
  }
  .learning-dashboard h3 {
    margin: 0 0 4px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-1);
  }
  .learning-dashboard .desc {
    font-size: 12px;
    color: var(--text-3);
    margin-bottom: 12px;
  }
  .rule-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 8px;
    border: 1px solid var(--border-1);
    background: var(--bg-0);
    margin-bottom: 6px;
    font-size: 12.5px;
  }
  .rule-row .rule-icon { font-size: 14px; width: 18px; flex-shrink: 0; }
  .rule-row .rule-pattern {
    flex: 1;
    color: var(--text-1);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .rule-row .rule-type-badge {
    font-size: 10.5px;
    padding: 2px 6px;
    border-radius: 4px;
    background: var(--bg-2);
    color: var(--text-3);
    letter-spacing: 0.03em;
  }
  .rule-row .rule-count { font-size: 11px; color: var(--text-3); white-space: nowrap; }
  .rule-row .rule-delete {
    background: transparent;
    border: 1px solid var(--border-2);
    color: var(--text-3);
    padding: 4px 8px;
    border-radius: 5px;
    cursor: pointer;
    font-size: 11.5px;
    font-family: inherit;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }
  .rule-row .rule-delete:hover { background: var(--bg-2); color: var(--text-1); }
  .learning-dashboard .reset-row {
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--border-1);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .learning-dashboard .reset-btn {
    background: transparent;
    border: 1px solid #6a1a1a;
    color: #b4474a;
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    font-family: inherit;
  }
  .learning-dashboard .reset-btn:hover { background: #2a0a0a; color: #fff; }
  :root.theme-light .learning-dashboard .reset-btn { border-color: #d4a3a3; color: #b03030; }
  :root.theme-light .learning-dashboard .reset-btn:hover { background: #fbeaea; }

  /* ── Onboarding Wizard ── */
  .onboarding-overlay {
    position: fixed;
    inset: 0;
    background: rgba(10, 12, 20, 0.85);
    backdrop-filter: blur(6px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 2000;
  }
  :root.theme-light .onboarding-overlay { background: rgba(255,255,255,0.85); }
  .onboarding-modal {
    background: var(--bg-1);
    border: 1px solid var(--border-2);
    border-radius: 16px;
    padding: 32px 36px 24px;
    width: min(560px, 92vw);
    max-height: 88vh;
    overflow-y: auto;
    box-shadow: 0 24px 64px rgba(0,0,0,0.6);
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  .onboarding-dots {
    display: flex;
    gap: 6px;
    justify-content: center;
  }
  .onboarding-dot {
    width: 28px;
    height: 4px;
    border-radius: 2px;
    background: var(--border-2);
    transition: background 0.2s;
  }
  .onboarding-dot.active { background: var(--accent-1); }
  .onboarding-dot.done   { background: var(--accent-2); opacity: 0.6; }
  .onboarding-content { min-height: 240px; }
  .onboarding-content h2 {
    font-size: 20px;
    font-weight: 600;
    margin: 4px 0 4px;
    color: var(--text-1);
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .onboarding-content .step-label {
    font-size: 11px;
    color: var(--accent-2);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 500;
    margin-bottom: 4px;
  }
  .onboarding-content .step-body {
    font-size: 14px;
    color: var(--text-2);
    line-height: 1.7;
    margin: 10px 0 14px;
  }
  .onboarding-content .step-cmd {
    background: var(--bg-0);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    padding: 10px 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12.5px;
    color: var(--text-1);
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 6px 0;
  }
  .onboarding-content .step-cmd code { flex: 1; word-break: break-all; }
  .onboarding-content .step-cmd .copy-btn {
    background: transparent;
    border: 1px solid var(--border-2);
    color: var(--text-3);
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 11.5px;
    cursor: pointer;
    flex-shrink: 0;
    font-family: inherit;
    transition: background 0.15s, color 0.15s;
  }
  .onboarding-content .step-cmd .copy-btn:hover { background: var(--bg-2); color: var(--text-1); }
  .onboarding-content .step-cmd .copy-btn.copied {
    color: var(--accent-2);
    border-color: var(--accent-1);
  }
  .onboarding-content .step-warn {
    background: rgba(234, 179, 8, 0.08);
    border-left: 3px solid #facc15;
    padding: 9px 12px;
    border-radius: 4px;
    font-size: 12.5px;
    color: var(--text-2);
    margin: 10px 0;
    line-height: 1.6;
  }
  :root.theme-light .onboarding-content .step-warn {
    background: #fef9c3;
    color: #713f12;
  }
  .onboarding-content .step-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 8px;
    margin: 12px 0;
  }
  .onboarding-content .step-stat {
    background: var(--bg-2);
    padding: 10px 12px;
    border-radius: 8px;
    text-align: center;
  }
  .onboarding-content .step-stat .num {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-1);
    display: block;
  }
  .onboarding-content .step-stat .label {
    font-size: 11px;
    color: var(--text-3);
  }
  .onboarding-footer {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-top: 14px;
    border-top: 1px solid var(--border-1);
  }
  .onboarding-skip, .onboarding-back, .onboarding-next {
    padding: 8px 16px;
    border-radius: 7px;
    border: 1px solid var(--border-2);
    background: transparent;
    color: var(--text-2);
    font-size: 13px;
    cursor: pointer;
    font-family: inherit;
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }
  .onboarding-skip:hover, .onboarding-back:hover { background: var(--bg-2); color: var(--text-1); }
  .onboarding-next {
    background: var(--accent-1);
    border-color: var(--accent-1);
    color: #fff;
    font-weight: 500;
  }
  .onboarding-next:hover { filter: brightness(1.1); }

  /* Hidden-count chip in the header stats */
  .stats .hidden-chip {
    margin-left: 8px;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--bg-2);
    color: var(--text-3);
    font-size: 11px;
    cursor: pointer;
  }
  .stats .hidden-chip:hover { background: var(--bg-3); color: var(--text-1); }

  /* Flashback drill-down result list */
  .flashback-results-header {
    font-size: 13px;
    font-weight: 600;
    color: var(--accent-2);
    margin: 12px 0 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-1);
  }
  .flashback-result {
    padding: 12px 14px;
    border-radius: 8px;
    border: 1px solid var(--border-1);
    background: var(--bg-0);
    margin-bottom: 8px;
  }
  .flashback-result-meta {
    font-size: 11px;
    color: var(--text-3);
    margin-bottom: 6px;
    font-variant-numeric: tabular-nums;
  }
  .flashback-result-content {
    font-size: 13px;
    color: var(--text-1);
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
  }
  /* Timeline */
  .timeline-controls {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }
  .timeline-day {
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-left: 3px solid var(--border-2);
    border-radius: var(--radius-md);
    padding: 14px 18px;
    margin-bottom: 8px;
    transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
  }
  .timeline-day:hover {
    border-color: var(--border-2);
    border-left-color: var(--accent-1);
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(0,0,0,0.25), 0 1px 0 rgba(255,255,255,0.02);
  }
  .timeline-day-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 10px;
  }
  .timeline-day-date {
    font-weight: 600;
    color: var(--text-1);
    font-size: 14px;
    letter-spacing: -0.005em;
  }
  .timeline-day-date .today-marker {
    color: var(--accent-2);
    font-weight: 500;
    margin-left: 8px;
    font-size: 11px;
    padding: 2px 8px;
    background: rgba(129,140,248,0.12);
    border-radius: var(--radius-pill);
    letter-spacing: 0.02em;
  }
  .timeline-day-total {
    font-size: 12px;
    color: var(--text-3);
    font-variant-numeric: tabular-nums;
  }
  .timeline-day-sources {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    position: relative;
  }
  .src-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-pill);
    padding: 4px 10px;
    font-size: 12.5px;
    color: var(--text-2);
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease, transform 0.12s ease;
    user-select: none;
    position: relative;
    font-variant-numeric: tabular-nums;
  }
  .src-pill:hover {
    background: var(--bg-3);
    border-color: var(--border-2);
    color: var(--text-1);
    transform: translateY(-1px);
  }
  .src-pill.expanded {
    background: var(--accent-soft);
    border-color: var(--accent-1);
    color: var(--text-1);
  }
  /* Hover preview tooltip for source pills */
  .src-pill-preview {
    position: absolute;
    bottom: calc(100% + 8px);
    left: 0;
    min-width: 220px;
    max-width: 360px;
    background: #1c2030;
    border: 1px solid var(--border-2);
    border-radius: var(--radius-md);
    padding: 10px 12px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.55);
    font-size: 12px;
    color: var(--text-2);
    line-height: 1.45;
    pointer-events: none;
    opacity: 0;
    transform: translateY(4px);
    transition: opacity 0.15s ease, transform 0.15s ease;
    z-index: 100;
    white-space: normal;
  }
  .src-pill-preview .preview-meta {
    font-size: 11px;
    color: var(--text-3);
    margin-bottom: 4px;
    font-variant-numeric: tabular-nums;
  }
  .src-pill-preview .preview-body {
    color: var(--text-2);
    max-height: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 5;
    -webkit-box-orient: vertical;
  }
  .src-pill:hover .src-pill-preview {
    opacity: 1;
    transform: translateY(0);
  }
  .timeline-day-records {
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid var(--border-2);
  }
  .timeline-record {
    display: flex;
    gap: 12px;
    padding: 6px 0;
    font-size: 13px;
    color: var(--text-2);
    border-bottom: 1px solid #1f1f1f;
    align-items: flex-start;
  }
  .timeline-record:last-child { border-bottom: 0; }
  .timeline-rec-time {
    color: var(--text-3);
    min-width: 42px;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }
  .timeline-rec-content {
    flex: 1;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.5;
    max-height: 78px;
    overflow: hidden;
    position: relative;
    transition: max-height 0.25s ease;
  }
  .timeline-rec-content::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 28px;
    background: linear-gradient(transparent, #161616);
    pointer-events: none;
    opacity: 1;
    transition: opacity 0.2s;
  }
  .timeline-record:hover .timeline-rec-content {
    max-height: 1600px;
  }
  .timeline-record:hover .timeline-rec-content::after {
    opacity: 0;
  }
  .examples {
    margin-top: 16px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .chip {
    padding: 6px 12px;
    background: var(--bg-1);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-pill);
    font-size: 12px;
    color: var(--text-2);
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
  }
  .chip:hover {
    background: var(--bg-2);
    color: var(--text-1);
    border-color: var(--accent-1);
  }
  .results { margin-top: 22px; }
  .result {
    padding: 14px 18px;
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
    margin-bottom: 8px;
    transition: border-color 0.15s, background 0.15s;
    cursor: pointer;
  }
  .result:hover { border-color: var(--border-2); background: var(--bg-2); }
  .result.expanded { border-color: var(--accent-1); cursor: default; }
  .result-meta {
    font-size: 11.5px;
    color: var(--text-3);
    margin-bottom: 8px;
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    align-items: center;
    font-variant-numeric: tabular-nums;
  }
  .result-meta .role { color: var(--accent-2); }
  .result-meta .source-badge {
    padding: 2px 7px;
    border-radius: var(--radius-pill);
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.01em;
  }
  .source-badge.claude { background: #1f2540; color: #a5b4fc; }
  .source-badge.file { background: #1f3528; color: #6ee7b7; }
  .source-badge.gmail { background: #3b1f1f; color: #fca5a5; }
  .source-badge.notes { background: #2a1f3b; color: #c4b5fd; }
  .source-badge.imessage { background: #3b1f33; color: #f9a8d4; }
  .source-badge.photo,
  .source-badge.photos_app { background: #1f2f3b; color: #93c5fd; }
  .source-badge.browser { background: #1f3b3b; color: #67e8f9; }
  .source-badge.calendar { background: #3b2f1f; color: #fcd34d; }
  .source-badge.line { background: #1f3b29; color: #86efac; }
  .source-badge.manual { background: #2a2a3b; color: #cbd5e1; }
  .result-meta .distance { color: var(--text-4); }
  .result-meta .relevance {
    padding: 1px 8px;
    border-radius: var(--radius-pill);
    font-size: 11px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    background: rgba(129,140,248,0.12);
    color: var(--accent-2);
    border: 1px solid rgba(129,140,248,0.22);
    cursor: help;
  }
  .result-meta .relevance.rerank {
    background: rgba(245,158,11,0.14);
    color: #fcd34d;
    border-color: rgba(245,158,11,0.30);
  }
  /* Why-this-record-matched chips (vector / keyword / rerank / signal) */
  .why-chips { display: inline-flex; gap: 4px; flex-wrap: wrap; }
  .why-chip {
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 500;
    background: var(--bg-2);
    color: var(--text-3);
    border: 1px solid var(--border-2);
    cursor: help;
    line-height: 16px;
  }
  .why-chip.why-rerank { color: #a8aaff; border-color: rgba(168,170,255,0.35); background: rgba(168,170,255,0.10); }
  .why-chip.why-vector { color: #6dd47c; border-color: rgba(88,204,110,0.35); background: rgba(88,204,110,0.08); }
  .why-chip.why-keyword { color: #f6b73c; border-color: rgba(246,183,60,0.35); background: rgba(246,183,60,0.08); }
  .why-chip.why-signal { color: #efaf4a; border-color: rgba(239,175,74,0.35); background: rgba(239,175,74,0.08); }
  .why-chip.why-kwfb { color: #ff9b6b; border-color: rgba(255,155,107,0.35); background: rgba(255,155,107,0.10); }
  /* Results toolbar: "copy all to Claude/ChatGPT" */
  .results-toolbar {
    display: flex; justify-content: flex-end; align-items: center;
    gap: 8px;
    margin: 8px 0 14px;
    padding: 0;
  }
  .results-toolbar .copy-bundle-btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 12px;
    border-radius: 8px;
    border: 1px solid var(--border-1);
    background: var(--bg-1);
    color: var(--text-1);
    font-size: 12px;
    cursor: pointer;
    transition: background 0.12s;
  }
  .results-toolbar .copy-bundle-btn:hover { background: var(--bg-2); }
  .results-toolbar .copy-bundle-btn svg { width: 13px; height: 13px; }
  .results-toolbar .copy-bundle-btn.copied { color: #58cc6e; border-color: rgba(88,204,110,0.4); }
  .result-meta .more-chunks {
    color: #efaf4a;
    background: rgba(239, 175, 74, 0.1);
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .result-meta .more-chunks:hover {
    background: rgba(239, 175, 74, 0.25);
  }
  .siblings-panel {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px dashed #2a2a2a;
  }
  .sibling-item {
    padding: 10px 14px;
    margin: 6px 0;
    background: var(--bg-1);
    border-left: 3px solid #efaf4a;
    border-radius: 4px;
    font-size: 13px;
  }
  .sibling-item .meta {
    font-size: 11px;
    color: var(--text-3);
    margin-bottom: 4px;
  }
  .sibling-item .content {
    color: var(--text-2);
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  .result-meta .expand-hint { margin-left: auto; color: var(--text-4); font-size: 11px; }
  .record-delete-btn {
    background: transparent;
    border: 1px solid transparent;
    color: var(--text-4);
    border-radius: 5px;
    width: 24px;
    height: 24px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    opacity: 0;
    transition: opacity 0.15s ease, color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
  }
  .record-delete-btn svg { width: 13px; height: 13px; }
  .result:hover .record-delete-btn { opacity: 0.7; }
  .record-delete-btn:hover {
    color: #fca5a5;
    background: rgba(248, 113, 113, 0.12);
    border-color: rgba(248, 113, 113, 0.30);
    opacity: 1 !important;
  }
  .result-content {
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
    color: var(--text-2);
    font-size: 13.5px;
    line-height: 1.55;
  }
  /* Photo / PDF preview that sits above the OCR text on photo and
     file results so the user can see the actual image instead of
     just the recovered text. */
  .result-media {
    margin: 0 0 12px 0;
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }
  .result-media .thumb {
    width: 160px;
    height: 160px;
    flex-shrink: 0;
    border-radius: 8px;
    overflow: hidden;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    cursor: zoom-in;
    transition: transform 0.15s ease, border-color 0.15s ease;
  }
  .result-media .thumb:hover { transform: scale(1.02); border-color: var(--accent-1); }
  .result-media .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .result-media .open-link {
    font-size: 12px;
    color: var(--text-3);
    text-decoration: none;
  }
  .result-media .open-link:hover { color: var(--accent-2); }
  /* Full-screen overlay for clicked thumbnails. */
  .lightbox {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.88);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 28px;
  }
  .lightbox.shown { display: flex; }
  .lightbox-close {
    position: fixed;
    top: 18px;
    right: 18px;
    width: 40px;
    height: 40px;
    background: rgba(28, 32, 48, 0.92);
    border: 1px solid var(--border-2);
    border-radius: 50%;
    color: var(--text-1);
    font-size: 20px;
    line-height: 1;
    cursor: pointer;
    z-index: 1001;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.15s ease, transform 0.15s ease;
    padding: 0;
  }
  .lightbox-close:hover {
    background: var(--accent-1);
    transform: scale(1.06);
  }
  .lightbox-hint {
    position: fixed;
    bottom: 18px;
    left: 50%;
    transform: translateX(-50%);
    color: var(--text-3);
    font-size: 12px;
    background: rgba(28, 32, 48, 0.85);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-pill);
    padding: 6px 14px;
    z-index: 1001;
    pointer-events: none;
  }
  .lightbox-body {
    max-width: 100%;
    max-height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .lightbox-body img, .lightbox-body iframe {
    max-width: 100%;
    max-height: 100%;
    border-radius: 8px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.7);
    background: var(--bg-1);
  }
  .lightbox-body iframe { width: 90vw; height: 88vh; }
  /* Inline file mentions inside Claude transcripts — clickable. */
  .file-mention {
    color: var(--accent-2);
    background: rgba(129,140,248,0.10);
    padding: 1px 6px;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 500;
    transition: background 0.15s ease, color 0.15s ease;
  }
  .file-mention:hover {
    background: rgba(129,140,248,0.22);
    color: var(--text-1);
  }
  .file-mention::before { content: "· "; opacity: 0.6; }
  /* Tone down the [assistant] [user] [tool_use:...] markers that
     come out of the Claude transcript — they're useful structure
     but were dominating the page visually. */
  .result-content {
    --marker-bg: rgba(129,140,248,0.10);
    --marker-fg: var(--text-4);
  }
  .result-content::before { content: ""; }
  /* Structural markers from Claude transcripts (assistant / user /
     tool_use:Bash etc) — hidden from the reading surface but kept in
     the underlying text so search still indexes them. */
  .marker { display: none; }
  /* Search-query match highlight, applied across result / session /
     siblings panels by the highlight() JS helper.
     Strong contrast for both dark + light themes so the match is the
     thing the eye lands on, not just a tinted nuance. */
  mark {
    background: #ffd400;
    color: #1a1100;
    border-radius: 3px;
    padding: 1px 4px;
    font-weight: 600;
    box-shadow: 0 0 0 1px rgba(255,212,0,0.35);
  }
  :root.theme-light mark {
    background: #ffeb3b;
    color: #1a1100;
    box-shadow: 0 0 0 1px rgba(255,193,7,0.5);
  }
  /* Growth toast — "+N 件 記憶しました" on first stats load each day */
  .growth-toast {
    position: fixed;
    bottom: 28px;
    left: 50%;
    transform: translateX(-50%) translateY(20px);
    padding: 10px 18px;
    border-radius: 22px;
    background: linear-gradient(135deg, #4c4d8a, #3b3f7a);
    color: #fff;
    font-size: 13px;
    font-weight: 500;
    box-shadow: 0 10px 30px rgba(0,0,0,0.4);
    z-index: 9999;
    opacity: 0;
    transition: opacity 0.35s ease, transform 0.35s ease;
    display: flex; align-items: center; gap: 8px;
  }
  .growth-toast.show {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
  .growth-toast .gt-icon svg { width: 14px; height: 14px; }
  /* Insights hero card — "今日これだけ見ればOK" */
  .insights-hero {
    margin: 0 0 22px;
    padding: 22px 26px;
    border-radius: 14px;
    background: linear-gradient(135deg, var(--bg-1) 0%, var(--bg-2) 100%);
    border: 1px solid var(--border-1);
    border-left: 4px solid var(--accent-1, #6a6dff);
    box-shadow: 0 8px 22px rgba(0,0,0,0.18);
  }
  .insights-hero-label {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-3);
    margin-bottom: 10px;
  }
  .insights-hero-label svg { width: 14px; height: 14px; }
  .insights-hero-headline {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-0);
    line-height: 1.4;
    margin-bottom: 6px;
  }
  .insights-hero-sub {
    font-size: 13px;
    color: var(--text-2);
    line-height: 1.5;
  }
  .insights-hero-event   { border-left-color: #58cc6e; }
  .insights-hero-stale   { border-left-color: #ef9b6b; }
  .insights-hero-recent  { border-left-color: #6a6dff; }
  /* Welcome / onboarding state shown when the DB is nearly empty. */
  .welcome {
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: 14px;
    padding: 32px 36px;
    margin-top: 18px;
    color: var(--text-2);
  }
  .welcome-hero {
    text-align: center;
    padding: 12px 0 24px;
    border-bottom: 1px solid var(--border-1);
    margin-bottom: 24px;
  }
  .welcome-icon-big {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 72px;
    height: 72px;
    border-radius: 50%;
    background: var(--accent-soft);
    color: var(--accent-2);
    margin-bottom: 14px;
  }
  .welcome h2 {
    margin: 0 0 10px 0;
    font-size: 22px;
    color: var(--text-1);
    font-weight: 600;
    letter-spacing: -0.01em;
  }
  .welcome p {
    margin: 0 0 12px 0;
    color: var(--text-2);
    font-size: 14px;
    line-height: 1.7;
  }
  .welcome-tagline {
    max-width: 520px;
    margin: 0 auto !important;
    color: var(--text-3) !important;
  }
  .welcome-steps {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin-bottom: 24px;
  }
  .welcome-step {
    display: flex;
    gap: 16px;
    padding: 16px 18px;
    border: 1px solid var(--border-1);
    border-radius: 10px;
    background: var(--bg-0);
    align-items: flex-start;
  }
  .welcome-step.welcome-step-action {
    border-color: var(--accent-1);
    background: var(--accent-soft);
  }
  .welcome-step-num {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--bg-2);
    color: var(--text-2);
    font-weight: 600;
    font-size: 13px;
    flex-shrink: 0;
  }
  .welcome-step-action .welcome-step-num {
    background: var(--accent-1);
    color: #fff;
  }
  .welcome-step-body { flex: 1; }
  .welcome-step-body h3 {
    margin: 2px 0 6px;
    font-size: 14.5px;
    font-weight: 600;
    color: var(--text-1);
  }
  .welcome-step-body p {
    margin: 0 0 10px;
    font-size: 13px;
    line-height: 1.6;
    color: var(--text-3);
  }
  .welcome-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 14px;
    border: 1px solid var(--border-2);
    background: transparent;
    color: var(--text-1);
    border-radius: 7px;
    font-size: 12.5px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    transition: background 0.15s, border-color 0.15s;
  }
  .welcome-btn:hover { background: var(--bg-2); border-color: var(--accent-1); }
  .welcome-btn-primary {
    background: var(--accent-1);
    border-color: var(--accent-1);
    color: #fff;
  }
  .welcome-btn-primary:hover { filter: brightness(1.1); background: var(--accent-1); }
  .welcome-tips {
    margin-top: 16px;
    padding-top: 14px;
    border-top: 1px solid var(--border-1);
  }
  .welcome-tips p {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin: 4px 0 !important;
    font-size: 12.5px !important;
    color: var(--text-3) !important;
    line-height: 1.6;
  }
  .welcome-tips p svg { flex-shrink: 0; margin-top: 3px; color: #c98000; }
  :root.theme-light .welcome-tips p svg { color: #b45309; }
  .welcome-tips code {
    background: var(--bg-2);
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 11.5px;
  }
  .welcome .cmd-list {
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .welcome .cmd-list li {
    padding: 8px 0;
    border-top: 1px solid #232323;
    display: flex;
    gap: 14px;
    align-items: center;
    font-size: 13px;
    color: var(--text-2);
  }
  .welcome .cmd-list li:first-child {
    border-top: 0;
  }
  .welcome .cmd-list .label {
    flex: 1;
  }
  .welcome .cmd-list code {
    background: var(--bg-1);
    border: 1px solid #252525;
    padding: 4px 10px;
    border-radius: 4px;
    color: #ffd987;
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 12px;
    white-space: nowrap;
  }
  .welcome .footnote {
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid #252525;
    color: var(--text-3);
    font-size: 12px;
    line-height: 1.5;
  }
  .session-panel {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #2a2a2a;
  }
  .session-header { font-size: 12px; color: var(--text-3); margin-bottom: 12px; }
  .session-msg {
    margin-bottom: 16px;
    padding: 12px 16px;
    border-radius: 6px;
    background: var(--bg-1);
    border-left: 3px solid #333;
  }
  .session-msg.user { border-left-color: var(--accent-1); }
  .session-msg.assistant { border-left-color: #5fbf6f; }
  .session-msg-meta {
    font-size: 11px;
    color: var(--text-3);
    margin-bottom: 6px;
    display: flex;
    gap: 12px;
  }
  .session-msg-meta .role.user { color: var(--accent-1); }
  .session-msg-meta .role.assistant { color: #5fbf6f; }
  .session-msg-content {
    white-space: pre-wrap;
    word-wrap: break-word;
    color: var(--text-2);
    font-size: 13px;
  }
  .empty { text-align: center; color: var(--text-4); padding: 60px 0; }
  .loading { text-align: center; color: var(--text-3); padding: 20px; }

  /* ── Chat pane ── */
  /* Chat pane uses the full main-area: no center padding, sidebar
     flush to the left of the workspace, input docked at the bottom. */
  main > #pane-chat.active {
    max-width: none;
    margin: 0;
    padding: 0;
    flex: 1;
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .chat-layout {
    display: flex;
    flex: 1;
    min-height: 0;
    height: 100%;
  }
  @media (max-width: 720px) {
    .chat-layout { flex-direction: column; }
  }
  .chat-sidebar {
    width: 260px;
    flex-shrink: 0;
    background: var(--bg-0);
    border-right: 1px solid var(--border-1);
    padding: 14px 10px 14px 12px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  @media (max-width: 720px) {
    .chat-sidebar { width: auto; height: 160px; border-right: 0; border-bottom: 1px solid var(--border-1); }
  }
  /* Section label (アクション / 設定 / 履歴) */
  .sidebar-section {
    font-size: 10px;
    color: var(--text-4);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 10px 8px 4px;
    font-weight: 600;
  }
  .sidebar-section:first-child { margin-top: 0; }
  .chat-new-btn {
    width: 100%;
    padding: 9px 12px;
    background: transparent;
    border: 1px solid var(--border-2);
    border-radius: 8px;
    color: var(--text-1);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    transition: background 0.15s, border-color 0.15s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }
  .chat-new-btn:hover { background: var(--bg-2); border-color: var(--accent-1); }
  .chat-new-btn svg { width: 14px; height: 14px; }
  .model-row { padding: 0; }
  .model-select {
    width: 100%;
    background: transparent;
    border: 1px solid var(--border-1);
    color: var(--text-1);
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 12px;
    font-family: inherit;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
  }
  .model-select:hover { background: var(--bg-2); }
  .model-select:focus { outline: none; border-color: var(--accent-1); }
  /* Search field with embedded icon */
  .chat-search-wrap {
    position: relative;
    width: 100%;
  }
  .chat-search-wrap svg {
    position: absolute;
    left: 9px;
    top: 50%;
    transform: translateY(-50%);
    width: 13px;
    height: 13px;
    color: var(--text-4);
    pointer-events: none;
  }
  .chat-session-search {
    width: 100%;
    background: var(--bg-1);
    border: 1px solid transparent;
    color: var(--text-1);
    border-radius: 8px;
    padding: 7px 10px 7px 28px;
    font-size: 12px;
    font-family: inherit;
    transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
  }
  .chat-session-search::placeholder { color: var(--text-4); }
  .chat-session-search:focus {
    outline: none;
    background: var(--bg-0);
    border-color: var(--accent-1);
    box-shadow: 0 0 0 3px rgba(129,140,248,0.15);
  }
  /* Session list items */
  .chat-sessions-list {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-top: 2px;
  }
  .chat-session-item {
    padding: 9px 10px;
    border-radius: 8px;
    cursor: pointer;
    color: var(--text-2);
    transition: background 0.15s, border-color 0.15s;
    position: relative;
    border-left: 2px solid transparent;
  }
  .chat-session-item:hover { background: var(--bg-2); color: var(--text-1); }
  .chat-session-item.active {
    background: var(--accent-soft);
    border-left-color: var(--accent-1);
    color: var(--text-1);
  }
  .chat-session-item .title {
    font-size: 12.5px;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding-right: 18px;
    color: var(--text-1);
  }
  .chat-session-item .preview {
    font-size: 11px;
    color: var(--text-3);
    margin-top: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-style: italic;
  }
  .chat-session-item .meta {
    font-size: 10.5px;
    color: var(--text-4);
    margin-top: 4px;
    display: flex;
    gap: 6px;
    font-variant-numeric: tabular-nums;
  }
  .chat-session-item .meta .sep { opacity: 0.4; }
  .chat-session-item .delete-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 18px;
    height: 18px;
    line-height: 16px;
    text-align: center;
    border-radius: 4px;
    font-size: 12px;
    color: var(--text-4);
    opacity: 0;
    transition: opacity 0.15s, background 0.15s, color 0.15s;
  }
  .chat-session-item:hover .delete-btn { opacity: 1; }
  .chat-session-item .delete-btn:hover { background: #6a1a1a; color: #fff; }
  :root.theme-light .chat-session-item .delete-btn:hover { background: #fde4e4; color: #c53030; }

  .chat-container {
    display: flex;
    flex-direction: column;
    min-height: 0;
    flex: 1;
  }
  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px 24px;
    min-height: 0;
  }
  .ollama-status-banner {
    margin: 16px 24px 0;
    padding: 18px 20px;
    border-radius: 12px;
    background: linear-gradient(180deg, rgba(255,193,7,0.08), rgba(255,193,7,0.03));
    border: 1px solid rgba(255,193,7,0.35);
    color: var(--text-1);
    font-size: 13px;
    line-height: 1.6;
    animation: chat-msg-in 0.2s ease;
  }
  .ollama-status-banner.state-ready { display: none; }
  .ollama-status-banner h3 {
    margin: 0 0 8px;
    font-size: 14px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-0);
  }
  .ollama-status-banner h3 svg { width: 18px; height: 18px; stroke-width: 2.2; }
  .ollama-status-banner p { margin: 6px 0; color: var(--text-2); }
  .ollama-status-banner .actions {
    display: flex;
    gap: 10px;
    margin-top: 14px;
    flex-wrap: wrap;
  }
  .ollama-status-banner .btn {
    padding: 8px 16px;
    border-radius: 8px;
    border: 1px solid var(--border-1);
    background: var(--bg-1);
    color: var(--text-0);
    font-size: 13px;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: background 0.12s;
  }
  .ollama-status-banner .btn:hover { background: var(--bg-2); }
  .ollama-status-banner .btn.primary {
    background: linear-gradient(135deg, #4c4d8a 0%, #3b3f7a 100%);
    border-color: transparent;
    color: #fff;
  }
  .ollama-status-banner .btn.primary:hover { filter: brightness(1.1); }
  .ollama-status-banner .pull-log {
    margin-top: 12px;
    padding: 10px 12px;
    background: rgba(0,0,0,0.18);
    border-radius: 6px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
    color: var(--text-3);
    max-height: 120px;
    overflow-y: auto;
    white-space: pre-wrap;
  }
  :root.theme-light .ollama-status-banner .pull-log { background: rgba(0,0,0,0.04); }
  .ollama-status-banner .hint { color: var(--text-3); font-size: 12px; margin-top: 8px; }
  .chat-msg {
    margin-bottom: 14px;
    padding: 14px 18px;
    border-radius: 14px;
    max-width: 82%;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-size: 14px;
    line-height: 1.6;
    animation: chat-msg-in 0.18s ease;
  }
  @keyframes chat-msg-in {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  .chat-msg.user {
    background: linear-gradient(135deg, #3b3f7a 0%, #4c4d8a 100%);
    color: #fff;
    margin-left: auto;
    border-bottom-right-radius: 4px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.3);
  }
  .chat-msg.assistant {
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    color: var(--text-2);
    border-bottom-left-radius: 4px;
  }
  /* Markdown rendered inside assistant chat messages. */
  .chat-msg strong { color: #fff; font-weight: 600; }
  .chat-msg em { font-style: italic; color: var(--text-1); }
  .chat-msg .md-h {
    margin: 14px 0 8px;
    font-weight: 600;
    color: #fff;
    line-height: 1.3;
  }
  .chat-msg .md-h1 { font-size: 19px; }
  .chat-msg .md-h2 { font-size: 17px; }
  .chat-msg .md-h3 { font-size: 15px; }
  .chat-msg .md-ul, .chat-msg .md-ol {
    margin: 8px 0;
    padding-left: 24px;
  }
  .chat-msg .md-ul li, .chat-msg .md-ol li {
    margin: 3px 0;
    line-height: 1.55;
  }
  .chat-msg .md-pre {
    background: #0a0d14;
    border: 1px solid var(--border-1);
    border-radius: 8px;
    padding: 12px 14px;
    overflow-x: auto;
    margin: 10px 0;
    position: relative;
  }
  .md-copy-btn {
    position: absolute;
    top: 6px;
    right: 8px;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border-1);
    color: var(--text-3);
    width: 28px;
    height: 26px;
    border-radius: 5px;
    cursor: pointer;
    font-size: 12px;
    line-height: 1;
    padding: 0;
    opacity: 0;
    transition: opacity 0.15s ease, background 0.15s ease, color 0.15s ease;
  }
  .chat-msg .md-pre:hover .md-copy-btn { opacity: 1; }
  .md-copy-btn:hover { background: rgba(129,140,248,0.18); color: var(--text-1); }
  .md-copy-btn.copied {
    background: rgba(52, 211, 153, 0.18);
    color: #6ee7b7;
    border-color: rgba(52, 211, 153, 0.35);
    opacity: 1 !important;
  }
  .chat-msg .md-lang {
    position: absolute;
    top: 6px;
    right: 10px;
    font-size: 10.5px;
    color: var(--text-4);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .chat-msg .md-code {
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 12.5px;
    color: #cdd5e0;
    line-height: 1.5;
    display: block;
    white-space: pre;
  }
  .chat-msg .md-inline {
    background: rgba(129, 140, 248, 0.12);
    border: 1px solid var(--border-2);
    padding: 1px 6px;
    border-radius: 4px;
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 12.5px;
    color: #c4b5fd;
  }
  .chat-msg .md-bq {
    border-left: 3px solid var(--accent-1);
    margin: 8px 0;
    padding: 4px 12px;
    color: var(--text-3);
    font-style: italic;
  }
  .chat-msg .md-hr {
    border: 0;
    border-top: 1px solid var(--border-2);
    margin: 14px 0;
  }
  /* TTS button on assistant messages. */
  .chat-msg.assistant { position: relative; }
  .tts-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 28px;
    height: 28px;
    border: 1px solid var(--border-1);
    background: rgba(255,255,255,0.02);
    color: var(--text-3);
    border-radius: 6px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.15s ease, background 0.15s ease, color 0.15s ease;
    padding: 0;
  }
  .tts-btn svg { width: 14px; height: 14px; }
  .chat-msg.assistant:hover .tts-btn { opacity: 1; }
  .tts-btn:hover { background: var(--bg-3); color: var(--text-1); }
  .tts-btn.speaking {
    opacity: 1 !important;
    background: var(--accent-soft);
    color: var(--accent-2);
    border-color: var(--accent-1);
  }
  /* Blinking caret shown at the end of an assistant message while
     tokens are still streaming in. Removed when the response completes. */
  .typing-cursor {
    display: inline-block;
    width: 8px;
    height: 1.05em;
    background: var(--accent-2);
    margin-left: 3px;
    vertical-align: text-bottom;
    border-radius: 1px;
    animation: typing-blink 0.85s steps(2, end) infinite;
  }
  @keyframes typing-blink {
    50% { opacity: 0; }
  }

  .chat-msg .ctx-toggle {
    display: inline-block;
    margin-top: 8px;
    font-size: 11px;
    color: var(--text-3);
    cursor: pointer;
  }
  .chat-msg .ctx-list {
    display: none;
    margin-top: 8px;
    padding: 10px;
    background: var(--bg-0);
    border: 1px solid var(--border-2);
    border-radius: 6px;
    font-size: 12px;
  }
  .chat-msg .ctx-list.shown { display: block; }
  .chat-msg .citation {
    display: inline-block;
    padding: 1px 6px;
    margin: 0 2px;
    background: var(--accent-soft);
    color: var(--accent-2);
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    vertical-align: middle;
    text-decoration: none;
  }
  .chat-msg .citation:hover { background: #234a7a; color: #fff; }
  /* Floating preview that appears when hovering a [N] citation. */
  .citation-preview {
    position: fixed;
    z-index: 1500;
    background: #1c2030;
    border: 1px solid var(--border-2);
    border-radius: var(--radius-md);
    padding: 10px 12px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.55);
    font-size: 12px;
    color: var(--text-2);
    line-height: 1.5;
    max-width: 420px;
    pointer-events: none;
    white-space: normal;
  }
  .citation-preview .cp-head {
    font-size: 11px;
    color: var(--text-3);
    margin-bottom: 4px;
    font-variant-numeric: tabular-nums;
  }
  .citation-preview .cp-body {
    color: var(--text-2);
    display: -webkit-box;
    -webkit-line-clamp: 6;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .chat-msg .ctx-item-numbered {
    display: flex;
    gap: 8px;
    padding: 8px;
    border-radius: 4px;
    margin-bottom: 6px;
  }
  .chat-msg .ctx-item-numbered:target {
    background: rgba(74, 143, 239, 0.15);
    outline: 1px solid #4a8fef;
  }
  .chat-msg .ctx-num {
    flex: 0 0 24px;
    height: 24px;
    line-height: 24px;
    text-align: center;
    background: var(--accent-soft);
    color: var(--accent-2);
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
  }
  .chat-input-row {
    display: flex;
    gap: 8px;
    padding: 14px 20px;
    background: var(--bg-0);
    flex-shrink: 0;
  }
  .chat-input {
    flex: 1;
    padding: 14px 18px;
    font-size: 15px;
    background: var(--bg-0);
    border: 1px solid var(--border-1);
    border-radius: 10px;
    color: var(--text-1);
    outline: none;
    font-family: inherit;
  }
  .chat-input:focus { border-color: var(--accent-1); }
  .chat-send {
    padding: 14px 28px;
    background: #4a8fef;
    border: none;
    border-radius: 10px;
    color: #fff;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: background 0.15s;
  }
  .chat-send:hover { background: #6aa5ff; }
  .chat-send:disabled { background: #2a3a5a; cursor: not-allowed; }
  /* Voice input button — Web Speech API.
     The .recording class is toggled by JS while the mic is live. */
  .chat-mic {
    width: 44px;
    height: 44px;
    flex-shrink: 0;
    background: transparent;
    border: 1px solid var(--border-1);
    border-radius: 10px;
    color: var(--text-3);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: background 0.15s ease, color 0.15s ease, transform 0.15s ease;
    padding: 0;
  }
  .chat-mic svg { width: 18px; height: 18px; }
  .chat-mic:hover { background: var(--bg-1); color: var(--text-1); }
  .chat-mic.recording {
    background: #b91c1c;
    color: #fff;
    border-color: #f87171;
    animation: mic-pulse 1.2s ease-in-out infinite;
  }
  @keyframes mic-pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(248, 113, 113, 0.45); }
    50%      { box-shadow: 0 0 0 7px rgba(248, 113, 113, 0); }
  }
  .chat-mic[disabled] {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .chat-status {
    font-size: 12px;
    color: var(--text-3);
    padding: 8px 0;
    text-align: center;
  }
  .chat-status.error { color: #ff6666; }
  .chat-status.thinking { color: var(--text-2); }
  .thinking-dots {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    margin-right: 6px;
    vertical-align: middle;
  }
  .thinking-dots span {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--accent-1, #6a6dff);
    animation: thinking-bounce 1.2s infinite ease-in-out;
  }
  .thinking-dots span:nth-child(2) { animation-delay: 0.15s; }
  .thinking-dots span:nth-child(3) { animation-delay: 0.3s; }
  @keyframes thinking-bounce {
    0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
    30%           { transform: translateY(-4px); opacity: 1; }
  }

  /* ── Insights pane ── */
  .insights-section {
    margin-bottom: 28px;
  }
  .insights-section h2 {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-3);
    margin: 0 0 12px;
    padding-bottom: 0;
    border-bottom: 0;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .insights-section h2::before {
    content: "";
    width: 3px;
    height: 13px;
    background: var(--accent-1);
    border-radius: 2px;
  }
  .insights-card {
    padding: 14px 18px;
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
    margin-bottom: 8px;
    transition: border-color 0.15s ease, background 0.15s ease;
  }
  .insights-card:hover {
    border-color: var(--border-2);
    background: var(--bg-2);
  }
  .insights-card.alert    { border-left: 3px solid #f87171; }
  .insights-card.upcoming { border-left: 3px solid var(--accent-1); }
  .insights-card.note     { border-left: 3px solid #34d399; }
  .insights-card.pending  { border-left: 3px solid #c4b5fd; }
  .insights-card .title {
    font-weight: 600;
    color: var(--text-1);
    margin-bottom: 4px;
    font-size: 14px;
  }
  .insights-card .meta {
    font-size: 11.5px;
    color: var(--text-4);
    margin-bottom: 8px;
    font-variant-numeric: tabular-nums;
  }
  .insights-card .body {
    font-size: 13px;
    color: var(--text-2);
    white-space: pre-wrap;
    word-wrap: break-word;
    line-height: 1.55;
  }
  .insights-generated {
    font-size: 11px;
    color: var(--text-4);
    text-align: right;
    margin-bottom: 16px;
  }

  /* ── Graph pane: spider-web + list dual view ── */
  .graph-view-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border-1);
    background: var(--bg-0);
    flex-shrink: 0;
    gap: 12px;
  }
  .graph-view-toggle {
    display: inline-flex;
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-pill);
    padding: 2px;
    gap: 0;
  }
  .graph-view-btn {
    background: transparent;
    border: 0;
    color: var(--text-3);
    padding: 5px 12px;
    border-radius: var(--radius-pill);
    cursor: pointer;
    font-size: 12px;
    font-family: inherit;
    transition: background 0.15s ease, color 0.15s ease;
  }
  .graph-view-btn.active {
    background: var(--accent-1);
    color: #fff;
  }
  .graph-view-hint {
    font-size: 11px;
    color: var(--text-4);
  }
  .entity-web {
    flex: 1;
    position: relative;
    background:
      radial-gradient(1200px 600px at 50% 50%, rgba(129,140,248,0.05), transparent 70%),
      var(--bg-0);
    overflow: hidden;
    min-width: 0;
  }
  #entity-web-svg {
    width: 100%;
    height: 100%;
    display: block;
    cursor: grab;
  }
  #entity-web-svg:active { cursor: grabbing; }
  .entity-web-loading {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-3);
    font-size: 13px;
    pointer-events: none;
  }
  /* SVG node styling. We use classes (not inline fills) so themes work. */
  .web-edge {
    stroke: var(--border-2);
    stroke-opacity: 0.55;
    fill: none;
    transition: stroke 0.18s ease, stroke-opacity 0.18s ease, stroke-width 0.18s ease;
  }
  .web-edge.hot { stroke: var(--accent-1); stroke-opacity: 0.85; }
  .web-node circle {
    fill: var(--bg-2);
    stroke: var(--border-2);
    stroke-width: 1.5;
    transition: fill 0.18s ease, stroke 0.18s ease, r 0.18s ease;
  }
  .web-node:hover circle { stroke: var(--accent-2); }
  .web-node.center circle {
    fill: var(--accent-1);
    stroke: var(--accent-2);
    stroke-width: 2.5;
  }
  .web-node.neighbor circle {
    fill: var(--accent-soft);
    stroke: var(--accent-2);
  }
  .web-node text {
    font-size: 12px;
    fill: var(--text-1);
    pointer-events: none;
    text-anchor: middle;
    user-select: none;
    font-family: inherit;
  }
  .web-node.center text { font-weight: 700; font-size: 13px; }
  .web-node.neighbor text { fill: var(--text-2); }
  .web-node.faded { opacity: 0.25; }
  .web-edge.faded { opacity: 0.12; }

  /* ── Graph pane: full-bleed, like the chat pane ── */
  main > #pane-graph.active {
    max-width: none;
    margin: 0;
    padding: 0;
    flex: 1;
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }
  .graph-layout {
    display: flex;
    flex: 1;
    min-height: 0;
    height: 100%;
  }
  @media (max-width: 700px) { .graph-layout { flex-direction: column; } }
  .entity-list {
    width: 300px;
    flex-shrink: 0;
    border-right: 1px solid var(--border-1);
    background: var(--bg-1);
    overflow-y: auto;
    padding: 14px 12px;
  }
  @media (max-width: 700px) {
    .entity-list { width: auto; height: 200px; border-right: 0; border-bottom: 1px solid var(--border-1); }
  }
  .entity-pill {
    padding: 10px 14px;
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-sm);
    margin-bottom: 6px;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease;
    font-size: 13px;
    color: var(--text-2);
  }
  .entity-pill:hover { background: var(--bg-2); border-color: var(--border-2); }
  .entity-pill.active {
    background: var(--accent-soft);
    border-color: var(--accent-1);
    color: var(--text-1);
  }
  .entity-pill .name { font-weight: 600; }
  .entity-pill .meta { font-size: 11px; color: var(--text-3); margin-top: 2px; }
  .entity-pill .type-org { color: #ef8f4a; }
  .entity-pill .type-project { color: #4aef8f; }
  .entity-pill .type-place { color: #8f4aef; }
  .entity-pill .type-person { color: #ef4a8f; }
  .entity-pill .type-concept { color: #8fef4a; }
  .entity-pill .type-tool { color: #4aefef; }
  .entity-pill .type-topic { color: var(--text-3); }

  .entity-detail {
    flex: 1;
    overflow-y: auto;
    padding: 28px 32px;
    min-width: 0;
    background:
      radial-gradient(1200px 400px at 20% -10%, rgba(129,140,248,0.06), transparent 60%),
      var(--bg-0);
  }
  .entity-detail h2 {
    margin: 0 0 6px;
    font-size: 22px;
    font-weight: 700;
    color: var(--text-1);
    letter-spacing: -0.01em;
  }
  .entity-detail .type-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: var(--radius-pill);
    font-size: 11px;
    font-weight: 600;
    margin-right: 8px;
    letter-spacing: 0.02em;
    text-transform: lowercase;
  }
  .entity-detail .description {
    color: var(--text-3);
    margin: 14px 0 20px;
    font-size: 13.5px;
    line-height: 1.6;
  }
  .entity-detail .section {
    margin-top: 24px;
  }
  .entity-detail .section h3 {
    margin: 0 0 12px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-2);
    letter-spacing: -0.005em;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .entity-detail .section h3::before {
    content: "";
    width: 3px;
    height: 14px;
    background: var(--accent-1);
    border-radius: 2px;
  }
  .entity-detail h2 {
    margin: 0 0 6px;
    font-size: 22px;
  }
  .entity-detail .type-badge {
    display: inline-block;
    padding: 2px 8px;
    background: var(--bg-2);
    border-radius: 10px;
    font-size: 11px;
    color: var(--text-3);
    margin-right: 8px;
  }
  .entity-detail .description {
    color: var(--text-2);
    margin: 12px 0;
    line-height: 1.6;
  }
  .entity-detail .section {
    margin-top: 24px;
  }
  .entity-detail .section h3 {
    font-size: 14px;
    color: var(--text-2);
    margin: 0 0 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid #1a1a1a;
  }
  .relation-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
  }
  .relation-card {
    padding: 10px 12px;
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s;
    font-size: 12px;
  }
  .relation-card:hover { background: var(--bg-2); border-color: var(--accent-1); }
  .relation-card .name { color: var(--text-1); font-weight: 600; }
  .relation-card .weight { color: var(--text-3); font-size: 11px; margin-top: 2px; }

  .entity-record {
    padding: 14px;
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: 6px;
    margin-bottom: 8px;
    font-size: 13px;
  }
  .entity-record .meta {
    font-size: 11px;
    color: var(--text-3);
    margin-bottom: 6px;
  }
  .entity-record .content {
    color: var(--text-2);
    white-space: pre-wrap;
    word-wrap: break-word;
  }

  /* ── Settings pane ── */
  .settings-section {
    margin-bottom: 24px;
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
    padding: 20px 24px;
    box-shadow: var(--shadow-1);
  }
  .settings-section h2 {
    margin: 0 0 14px;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-3);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border-1);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .settings-section h2::before {
    content: "";
    width: 3px;
    height: 12px;
    background: var(--accent-1);
    border-radius: 2px;
  }
  .settings-field {
    display: grid;
    grid-template-columns: 1fr 220px;
    gap: 18px;
    align-items: start;
    padding: 14px 0;
    border-bottom: 1px solid var(--border-1);
  }
  .settings-field:last-child { border-bottom: none; padding-bottom: 0; }
  .settings-field:first-of-type { padding-top: 4px; }
  @media (max-width: 640px) {
    .settings-field { grid-template-columns: 1fr; }
  }
  .settings-label {
    color: var(--text-1);
    font-size: 13.5px;
    font-weight: 500;
    letter-spacing: -0.005em;
  }
  .settings-help {
    color: var(--text-4);
    font-size: 12px;
    margin-top: 5px;
    line-height: 1.5;
  }
  .settings-input {
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    border-radius: 7px;
    color: var(--text-1);
    padding: 8px 12px;
    font-size: 13px;
    font-family: inherit;
    width: 100%;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }
  .settings-input:hover { border-color: var(--text-4); }
  .settings-input:focus {
    outline: none;
    border-color: var(--accent-1);
    box-shadow: 0 0 0 3px rgba(129,140,248,0.15);
  }
  /* Backup list rows */
  .backup-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
    border-top: 1px solid var(--border-1);
  }
  .backup-row:first-child { border-top: 0; }
  .backup-meta { flex: 1; min-width: 0; }
  .backup-name {
    font-size: 13px;
    color: var(--text-1);
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .backup-info {
    font-size: 11px;
    color: var(--text-3);
    font-variant-numeric: tabular-nums;
  }
  .backup-restore-btn {
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    color: var(--text-2);
    border-radius: 6px;
    padding: 5px 12px;
    font-size: 12px;
    cursor: pointer;
    font-family: inherit;
    transition: background 0.15s ease, color 0.15s ease;
  }
  .backup-restore-btn:hover {
    background: var(--accent-soft);
    color: var(--accent-2);
    border-color: var(--accent-1);
  }
  .backup-restore-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .settings-toggle {
    display: inline-flex;
    align-items: center;
    cursor: pointer;
    user-select: none;
    background: var(--bg-1);
    border: 1px solid var(--border-2);
    border-radius: 20px;
    padding: 4px;
    width: 60px;
    transition: background 0.15s;
  }
  .settings-toggle input { display: none; }
  .settings-toggle .knob {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: #888;
    transition: transform 0.2s, background 0.2s;
  }
  .settings-toggle.on { background: var(--accent-soft); border-color: var(--accent-1); }
  .settings-toggle.on .knob { transform: translateX(28px); background: #4a8fef; }

  /* Floating save button — pinned to the bottom-right of the settings
     tab, no wrapper chrome (the button itself stands alone). */
  .settings-save-bar {
    position: fixed;
    bottom: 22px;
    right: 32px;
    z-index: 100;
    display: none;  /* shown only when the settings tab is active */
    align-items: center;
    gap: 12px;
  }
  body.settings-mode .settings-save-bar { display: flex; }
  body.settings-mode .settings-save-btn {
    box-shadow: 0 6px 20px rgba(74, 143, 239, 0.45);
  }
  .settings-save-btn {
    background: #4a8fef;
    color: #fff;
    border: none;
    padding: 10px 24px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
  }
  .settings-save-btn:hover { background: #6aa5ff; }
  .settings-save-btn:disabled { background: #2a3a5a; cursor: not-allowed; }
  .settings-toast {
    color: #5fbf6f;
    font-size: 13px;
  }
  .settings-toast.error { color: #ef6666; }

  /* ── Mobile responsive ── */
  @media (max-width: 640px) {
    .search-box, .chat-input { padding: 14px 16px; font-size: 16px; }
    .chat-send { padding: 14px 20px; }
    .chip { font-size: 13px; padding: 8px 14px; }
    .filter-chip { padding: 7px 13px; font-size: 13px; }
    .filter-row select { padding: 8px 12px; font-size: 13px; }
    .filter-row { gap: 10px; font-size: 12px; }
    .result { padding: 14px; }
    .result-content { font-size: 13px; }
    .chat-msg { font-size: 14px; padding: 12px 14px; max-width: 92%; }
    .chat-container { height: calc(100vh - 220px); }
    .chat-input-row { flex-direction: column; }
    .chat-send { width: 100%; padding: 12px; }
  }
</style>
</head>
<body>
<aside class="sidebar">
  <div class="sidebar-logo" aria-label="Bunshin">
    <svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="logoBg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#312e81"/>
          <stop offset="100%" stop-color="#4c1d95"/>
        </linearGradient>
        <linearGradient id="logoRib" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"  stop-color="#818cf8"/>
          <stop offset="50%" stop-color="#c4b5fd"/>
          <stop offset="100%" stop-color="#f472b6"/>
        </linearGradient>
      </defs>
      <rect width="1024" height="1024" rx="229" ry="229" fill="url(#logoBg)"/>
      <g transform="translate(512 512)">
        <path d="M -250 0 C -250 -140, -110 -140, 0 0 C 110 140, 250 140, 250 0 C 250 -140, 110 -140, 0 0 C -110 140, -250 140, -250 0 Z"
              fill="none" stroke="url(#logoRib)" stroke-width="56" stroke-linecap="round" stroke-linejoin="round"/>
      </g>
      <circle cx="512" cy="512" r="46" fill="#fef3c7"/>
    </svg>
  </div>
  <nav class="sidebar-nav">
    <button class="sidebar-tab active" data-pane="search" data-tooltip="検索" aria-label="検索">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
    </button>
    <button class="sidebar-tab" data-pane="chat" data-tooltip="チャット" aria-label="チャット">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
    </button>
    <button class="sidebar-tab" data-pane="insights" data-tooltip="気づき" aria-label="気づき">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 5.8h6.1l-4.9 3.6 1.9 5.8L12 14.6l-4.9 3.6 1.9-5.8L4 8.8h6.1z"/></svg>
    </button>
    <button class="sidebar-tab" data-pane="timeline" data-tooltip="タイムライン" aria-label="タイムライン">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/></svg>
    </button>
    <button class="sidebar-tab" data-pane="graph" data-tooltip="関係性" aria-label="関係性">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 7v3M12 10l-6 7M12 10l6 7"/></svg>
    </button>
    <button class="sidebar-tab" data-pane="settings" data-tooltip="設定" aria-label="設定">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
    </button>
  </nav>
</aside>

<div class="main-area">
<header>
  <h1 id="pane-title">検索</h1>
  <div class="header-right">
    <button class="add-memory-btn" id="add-memory-btn" type="button" title="メモを Bunshin に追加（後で検索や AI チャットから参照できます）⌘N" aria-label="メモ追加">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      <span class="add-memory-label">記憶</span>
    </button>
    <button class="theme-toggle" id="theme-toggle" type="button" title="テーマを切替" aria-label="テーマ切替">
      <svg class="theme-icon theme-icon-dark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
      <svg class="theme-icon theme-icon-light" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
    </button>
    <div class="stats" id="stats">loading...</div>
  </div>
</header>

<main>
  <!-- ============== Search Pane ============== -->
  <section class="pane active" id="pane-search">
    <input class="search-box" id="q" type="text" placeholder="過去の自分に聞いてみる…" autofocus>
    <div class="hint">日本語OK。意味で検索します。クリックで会話全体を展開。</div>

    <div class="filter-row">
      <label>ソート:
        <select id="sort">
          <option value="relevance">関連度順</option>
          <option value="newest">新しい順</option>
          <option value="oldest">古い順</option>
        </select>
      </label>
      <span>期間:</span>
      <div class="chips-row" id="periods">
        <span class="filter-chip active" data-period="all">全部</span>
        <span class="filter-chip" data-period="day">今日</span>
        <span class="filter-chip" data-period="week">今週</span>
        <span class="filter-chip" data-period="month">今月</span>
        <span class="filter-chip" data-period="year">今年</span>
      </div>
    </div>

    <div class="filter-row">
      <span>ソース:</span>
      <div class="chips-row" id="sources">
        <span class="filter-chip active" data-source="" data-label="全部">全部</span>
        <span class="filter-chip" data-source="claude" data-label="Claude">Claude</span>
        <span class="filter-chip" data-source="gmail" data-label="Gmail">Gmail</span>
        <span class="filter-chip" data-source="file" data-label="ファイル">ファイル</span>
        <span class="filter-chip" data-source="manual" data-label="クイックメモ" title="+記憶 / 覚えといて: で追加したメモ">クイックメモ</span>
        <span class="filter-chip" data-source="calendar" data-label="予定">予定</span>
        <span class="filter-chip" data-source="line" data-label="LINE">LINE</span>
        <span class="filter-chip" data-source="browser" data-label="ブラウザ">ブラウザ</span>
        <span class="filter-chip" data-source="notes" data-label="Apple メモ" title="macOS のメモ.app から取り込んだもの">Apple メモ</span>
        <span class="filter-chip" data-source="imessage" data-label="iMessage">iMessage</span>
        <span class="filter-chip" data-source="photos_app" data-label="写真ライブラリ">写真ライブラリ</span>
        <span class="filter-chip" data-source="photo" data-label="写真OCR">写真OCR</span>
      </div>
    </div>

    <div class="examples" id="example-chips">
      <!-- Examples will be loaded from your top entities -->
    </div>

    <!-- ===== Flashback: records the user wrote on this date in the past ===== -->
    <section class="flashback-section" id="flashback-section" style="display:none;">
      <div class="flashback-header">
        <svg class="flashback-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        <span class="flashback-title">今日のフラッシュバック</span>
        <span class="flashback-sub">過去の同じ日付に書いていたこと</span>
      </div>
      <div class="flashback-grid" id="flashback-grid"></div>
    </section>

    <div class="autocomplete-anchor">
      <div class="autocomplete-dropdown" id="autocomplete" role="listbox" aria-hidden="true"></div>
    </div>
    <div class="results" id="results">
      <div class="empty" id="search-empty-state">読み込み中…</div>
    </div>
  </section>

  <!-- ============== Insights Pane ============== -->
  <section class="pane" id="pane-insights">
    <div class="insights-generated" id="insights-generated"></div>
    <div id="insights-content">
      <div class="loading">読み込み中…</div>
    </div>
  </section>

  <!-- ============== Timeline Pane ============== -->
  <section class="pane" id="pane-timeline">
    <div class="timeline-controls">
      <span>期間:</span>
      <div class="chips-row" id="timeline-periods">
        <span class="filter-chip" data-days="7">直近1週間</span>
        <span class="filter-chip active" data-days="30">直近1ヶ月</span>
        <span class="filter-chip" data-days="90">直近3ヶ月</span>
        <span class="filter-chip" data-days="365">直近1年</span>
      </div>
    </div>
    <div id="timeline-content">
      <div class="loading">読み込み中…</div>
    </div>
  </section>

  <!-- ============== Graph Pane ============== -->
  <section class="pane" id="pane-graph">
    <div class="graph-view-bar">
      <div class="graph-view-toggle" id="graph-view-toggle">
        <button class="graph-view-btn active" data-view="web" type="button">🕸 蜘蛛の巣</button>
        <button class="graph-view-btn" data-view="list" type="button">📋 リスト</button>
      </div>
      <div class="graph-view-hint" id="graph-view-hint">ノードクリックで中央を切り替え、ドラッグで動かす</div>
    </div>
    <div class="graph-layout">
      <div class="entity-list" id="entity-list" style="display:none;">
        <div class="loading">読み込み中…</div>
      </div>
      <div class="entity-web" id="entity-web">
        <svg id="entity-web-svg" xmlns="http://www.w3.org/2000/svg"></svg>
        <div class="entity-web-loading" id="entity-web-loading">読み込み中…</div>
      </div>
      <div class="entity-detail" id="entity-detail">
        <div class="empty">中心ノードをクリックすると関係性が広がります</div>
      </div>
    </div>
  </section>

  <!-- ============== Settings Pane ============== -->
  <section class="pane" id="pane-settings">
    <div id="settings-content">
      <div class="loading">読み込み中…</div>
    </div>
  </section>

  <!-- ============== Chat Pane ============== -->
  <section class="pane" id="pane-chat">
    <div class="chat-layout">
      <aside class="chat-sidebar">
        <button class="chat-new-btn" id="chat-new-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          <span>新規チャット</span>
        </button>
        <div class="sidebar-section">設定</div>
        <div class="model-row">
          <select id="chat-model" class="model-select" aria-label="モデル"></select>
        </div>
        <div class="sidebar-section">履歴</div>
        <div class="chat-search-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input id="chat-session-search" type="text" class="chat-session-search" placeholder="検索…" autocomplete="off">
        </div>
        <div id="chat-sessions" class="chat-sessions-list">
          <div style="font-size:11px;color:var(--text-4);padding:8px;">読み込み中…</div>
        </div>
      </aside>
      <div class="chat-container">
        <div class="ollama-status-banner" id="ollama-status-banner" hidden></div>
        <div class="chat-messages" id="chat-messages">
          <div class="empty">
            分身（Bunshin）は、過去のあなたを全部読んでいます。<br>
            気になることを聞いてみてください。<br><br>
            <svg class="inline-tip-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.3 1 2.1V18h6v-1.2c0-.8.4-1.6 1-2.1A7 7 0 0 0 12 2z"/></svg>
            「<b>覚えといて: 来週火曜10時に漁協ミーティング</b>」のように<br>
            先頭に <code>覚えといて:</code> や <code>メモ:</code> を付けると、AI に聞かずに記憶に保存だけします。
          </div>
        </div>
        <div class="chat-status" id="chat-status"></div>
        <form class="chat-input-row" id="chat-form">
          <button class="chat-mic" id="chat-attach" type="button" title="画像をアップロード (OCR して記憶に追加)" aria-label="画像アップロード">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
          </button>
          <input type="file" id="chat-file-input" accept="image/*" style="display:none">
          <button class="chat-mic" id="chat-mic" type="button" title="音声入力 (Web Speech API)" aria-label="音声入力">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
          </button>
          <input class="chat-input" id="chat-input" type="text" placeholder="分身に聞く… / Ask your bunshin..." autocomplete="off">
          <button class="chat-send" id="chat-send" type="submit">送信</button>
        </form>
      </div>
    </div>
  </section>
</main>
</div><!-- /.main-area -->

<!-- ===== Add-memory modal (lives in body, opened by header button or ⌘N) ===== -->
<div class="mark-modal-backdrop" id="add-memory-modal" style="display:none;">
  <div class="add-memory-modal">
    <h3>記憶に追加</h3>
    <p class="sub">あとで検索・チャットから参照できます。日付や場所、固有名詞を入れると見つけやすくなります。</p>
    <textarea id="add-memory-text" placeholder="例: 2026/6/23 漁協ミーティング 来週火曜 10 時 / 神社ガイド事業の試算は月 30 万円目標 / 桃ピザの試作レシピ 卵 1, 桃 3..." autofocus></textarea>
    <div class="status" id="add-memory-status"></div>
    <div class="actions">
      <button class="btn" type="button" id="add-memory-cancel">キャンセル</button>
      <button class="btn primary" type="button" id="add-memory-save">保存 (⌘↵)</button>
    </div>
  </div>
</div>

<!-- ===== Mark / learning modal (lives in body, opened by JS) ===== -->
<div class="mark-modal-backdrop" id="mark-modal" style="display:none;">
  <div class="mark-modal">
    <h3 id="mark-modal-title">この記録は要らない</h3>
    <p class="mark-modal-sub" id="mark-modal-sub">学習範囲を選んでください。同じ送信者やドメインも今後 Bunshin が自動で非表示にします。</p>
    <label class="mark-scope" data-scope="record">
      <input type="radio" name="mark-scope" value="record">
      <span class="label-line">
        <span class="scope-title">この記録だけ非表示</span>
        <span class="scope-hint">他は学習しません</span>
      </span>
    </label>
    <label class="mark-scope recommended" data-scope="sender">
      <input type="radio" name="mark-scope" value="sender" checked>
      <span class="label-line">
        <span class="scope-title">同じ送信者を全部非表示</span>
        <span class="scope-hint" id="mark-scope-sender-hint">—</span>
      </span>
    </label>
    <label class="mark-scope" data-scope="domain">
      <input type="radio" name="mark-scope" value="domain">
      <span class="label-line">
        <span class="scope-title">同じドメインを全部非表示</span>
        <span class="scope-hint" id="mark-scope-domain-hint">—</span>
      </span>
    </label>
    <div class="mark-actions">
      <button class="btn-cancel" id="mark-cancel">キャンセル</button>
      <button class="btn-apply" id="mark-apply">適用</button>
    </div>
  </div>
</div>

<!-- ===== Undo toast ===== -->
<div class="undo-toast" id="undo-toast" style="display:none;">
  <span class="undo-msg" id="undo-msg"></span>
  <button class="undo-btn" id="undo-btn">取り消す</button>
  <span class="undo-countdown" id="undo-countdown">5</span>
</div>

<!-- ===== Onboarding Wizard (shown only on first launch with empty DB) ===== -->
<div class="onboarding-overlay" id="onboarding-overlay" style="display:none;">
  <div class="onboarding-modal">
    <div class="onboarding-dots" id="onboarding-dots"></div>
    <div class="onboarding-content" id="onboarding-content">
      <!-- step body rendered by JS -->
    </div>
    <div class="onboarding-footer">
      <button class="onboarding-skip" id="onboarding-skip">スキップ</button>
      <div style="flex:1;"></div>
      <button class="onboarding-back" id="onboarding-back" style="display:none;">← 戻る</button>
      <button class="onboarding-next" id="onboarding-next">次へ →</button>
    </div>
  </div>
</div>

<script>
// ===== Theme (dark / light) — applied before anything else so the page
// doesn't briefly flash the wrong palette. =====
(function setupTheme() {
  const KEY = 'bunshin.theme';
  let saved = null;
  try { saved = localStorage.getItem(KEY); } catch {}
  const root = document.documentElement;
  function apply(theme) {
    if (theme === 'light') root.classList.add('theme-light');
    else root.classList.remove('theme-light');
  }
  apply(saved || 'dark');
  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.addEventListener('click', () => {
      const next = root.classList.contains('theme-light') ? 'dark' : 'light';
      apply(next);
      try { localStorage.setItem(KEY, next); } catch {}
    });
  });
})();

// ===== Add-memory modal =====
(function setupAddMemory() {
  function openModal() {
    const m = document.getElementById('add-memory-modal');
    const t = document.getElementById('add-memory-text');
    const s = document.getElementById('add-memory-status');
    if (!m || !t) return;
    if (s) { s.textContent = ''; s.className = 'status'; }
    m.style.display = 'flex';
    setTimeout(() => t.focus(), 30);
  }
  function closeModal() {
    const m = document.getElementById('add-memory-modal');
    const t = document.getElementById('add-memory-text');
    if (m) m.style.display = 'none';
    if (t) t.value = '';
  }
  async function save() {
    const t = document.getElementById('add-memory-text');
    const s = document.getElementById('add-memory-status');
    const btn = document.getElementById('add-memory-save');
    if (!t || !s || !btn) return;
    const content = (t.value || '').trim();
    if (!content) {
      s.textContent = '内容を入力してください';
      s.className = 'status error';
      return;
    }
    btn.disabled = true;
    s.textContent = '保存中…';
    s.className = 'status';
    try {
      const r = await fetch('/api/note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      const j = await r.json();
      if (j.saved) {
        s.textContent = '✓ 記憶に保存しました（' + content.length + ' 文字）';
        s.className = 'status success';
        setTimeout(closeModal, 700);
        // Refresh stats badge if present.
        if (typeof loadStats === 'function') { try { loadStats(); } catch {} }
      } else {
        s.textContent = '✗ ' + (j.error || '保存に失敗しました');
        s.className = 'status error';
      }
    } catch (e) {
      s.textContent = '✗ ネットワークエラー';
      s.className = 'status error';
    } finally {
      btn.disabled = false;
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const trigger = document.getElementById('add-memory-btn');
    if (trigger) trigger.addEventListener('click', openModal);

    const cancel = document.getElementById('add-memory-cancel');
    if (cancel) cancel.addEventListener('click', closeModal);

    const saveBtn = document.getElementById('add-memory-save');
    if (saveBtn) saveBtn.addEventListener('click', save);

    const backdrop = document.getElementById('add-memory-modal');
    if (backdrop) {
      backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) closeModal();
      });
    }

    const ta = document.getElementById('add-memory-text');
    if (ta) {
      ta.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
        if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); save(); }
      });
    }
  });

  // Global ⌘N (and ⌃N) — capture before browser's "new window" intercepts it.
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && (e.key === 'n' || e.key === 'N') && !e.shiftKey && !e.altKey) {
      // Don't hijack when user is typing in an input/textarea, unless modal is already open.
      const m = document.getElementById('add-memory-modal');
      if (m && m.style.display === 'flex') return;
      const tag = (e.target && e.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      e.preventDefault();
      openModal();
    }
  });
})();

const $ = (id) => document.getElementById(id);
const esc = (s) => { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; };

// ===== Icon library (inline SVG, Feather/Lucide-style, currentColor) =====
// Replaces every emoji in the UI with a real outline icon so Bunshin
// reads as a tool, not a chat-thread. All icons share viewBox 24x24 +
// stroke=2 + round joins, and inherit color from the parent.
const _ICON_PATHS = {
  message:    '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
  'message-square': '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  mail:       '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>',
  'file-text':'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>',
  edit:       '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>',
  calendar:   '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
  globe:      '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
  notebook:   '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
  image:      '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
  camera:     '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
  sparkles:   '<path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3z"/>',
  lightbulb:  '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.3 1 2.1V18h6v-1.2c0-.8.4-1.6 1-2.1A7 7 0 0 0 12 2z"/>',
  lock:       '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  'alert-triangle': '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  trash:      '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1.5 14.5a2 2 0 0 1-2 1.5h-7a2 2 0 0 1-2-1.5L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
  star:       '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
  brain:      '<path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3 2.5 2.5 0 0 1 2.46-2.04Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3 2.5 2.5 0 0 0-2.46-2.04Z"/>',
  download:   '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  archive:    '<polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>',
  clock:      '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  check:      '<polyline points="20 6 9 17 4 12"/>',
  plus:       '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  database:   '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
  search:     '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  hash:       '<line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/>',
  link:       '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  settings:   '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  layers:     '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
  newspaper:  '<path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8z"/>',
  flame:      '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
  eye:        '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  folder:     '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
  tool:       '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  mic:        '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>',
  bell:       '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
  'check-circle': '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
  flag:       '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
  'life-buoy': '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4"/><line x1="4.93" y1="4.93" x2="9.17" y2="9.17"/><line x1="14.83" y1="14.83" x2="19.07" y2="19.07"/><line x1="14.83" y1="9.17" x2="19.07" y2="4.93"/><line x1="14.83" y1="9.17" x2="18.36" y2="5.64"/><line x1="4.93" y1="19.07" x2="9.17" y2="14.83"/>',
  copy:       '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  'external-link': '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
};

function icon(name, size) {
  const path = _ICON_PATHS[name];
  if (!path) return '';
  const s = size || 16;
  return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
}

// Source-type → icon name. Used by source chips, search results, flashback cards.
const SOURCE_ICON_NAME = {
  claude:     'message',
  gmail:      'mail',
  file:       'file-text',
  manual:     'edit',
  calendar:   'calendar',
  line:       'message-square',
  browser:    'globe',
  notes:      'notebook',
  imessage:   'message-square',
  photos_app: 'image',
  photo:      'camera',
};

// Source-type → human-friendly Japanese label. Used by timeline tooltips,
// flashback cards, search-result badges. Single source of truth.
const SOURCE_LABEL_JA = {
  claude:     'Claude',
  gmail:      'Gmail',
  file:       'ファイル',
  manual:     'クイックメモ',
  calendar:   '予定',
  line:       'LINE',
  browser:    'ブラウザ',
  notes:      'Apple メモ',
  imessage:   'iMessage',
  photo:      '写真OCR',
  photos_app: '写真ライブラリ',
};

// ===== Sidebar tabs =====
const PANE_TITLES = {
  search: '検索',
  chat: 'チャット',
  insights: '気づき',
  timeline: 'タイムライン',
  graph: '関係性',
  settings: '設定',
};
document.querySelectorAll('.sidebar-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.sidebar-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.pane').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const pane = tab.dataset.pane;
    $('pane-' + pane).classList.add('active');
    document.body.classList.toggle('chat-mode', pane === 'chat');
    document.body.classList.toggle('settings-mode', pane === 'settings');
    const titleEl = $('pane-title');
    if (titleEl && PANE_TITLES[pane]) titleEl.textContent = PANE_TITLES[pane];
    if (pane === 'chat') $('chat-input').focus();
    if (pane === 'search') $('q').focus();
    if (pane === 'insights') loadInsights();
    if (pane === 'graph') loadEntities();
    if (pane === 'settings') loadSettings();
    if (pane === 'timeline') loadTimeline();
  });
});

// ===== Settings =====
let settingsLoaded = false;
let settingsSchemaCache = null;
let settingsCurrent = {};

const SECTION_TITLES = {
  notifications: { ja: '通知',    en: 'Notifications', icon: 'bell' },
  search:        { ja: '検索',    en: 'Search',        icon: 'search' },
  chat:          { ja: 'チャット', en: 'Chat',          icon: 'message' },
  ingestion:     { ja: '取り込み', en: 'Ingestion',     icon: 'download' },
};

function renderBackupPanel() {
  return `
    <div class="settings-section" id="backup-section">
      <h2><span class="h2-icon">${icon('archive', 18)}</span> バックアップ</h2>
      <div class="settings-field" style="grid-template-columns: 1fr 220px;">
        <div>
          <div class="settings-label">DB のバックアップ</div>
          <div class="settings-help">~/.bunshin/backups/ にスナップショットを作成します（毎日 1 つまで、直近 7 件保持）。</div>
        </div>
        <div>
          <button class="settings-save-btn" id="backup-create-btn" style="background:var(--accent-1);">今すぐ作成</button>
        </div>
      </div>
      <div id="backup-list" style="margin-top:8px;">読み込み中…</div>
    </div>`;
}

function renderExportPanel() {
  return `
    <div class="settings-section">
      <h2><span class="h2-icon">${icon('download', 18)}</span> エクスポート</h2>
      <div class="settings-field" style="grid-template-columns: 1fr 220px;">
        <div>
          <div class="settings-label">記憶を持ち出す</div>
          <div class="settings-help">あなたのデータをいつでも持ち出せます。Local-first の証。<br><span style="color:var(--text-3);font-size:11px;">※ ブラウザ履歴（YouTube/SNS など）は既定で除外されます。誰かに共有する時の意図しない漏れを防ぐためです。</span></div>
        </div>
        <div style="display:flex;gap:8px;flex-direction:column;">
          <div style="display:flex;gap:8px;">
            <a href="/api/export/json" class="settings-save-btn" style="background:var(--bg-2);color:var(--text-1);text-decoration:none;text-align:center;">JSON</a>
            <a href="/api/export/sqlite" class="settings-save-btn" style="background:var(--bg-2);color:var(--text-1);text-decoration:none;text-align:center;">SQLite</a>
          </div>
          <label style="font-size:11px;color:var(--text-3);display:flex;align-items:center;gap:6px;cursor:pointer;">
            <input type="checkbox" id="export-include-browser" style="margin:0;">
            ブラウザ履歴も含める（自分用バックアップ）
          </label>
        </div>
      </div>
    </div>`;
}

(function setupExportToggle() {
  document.addEventListener('change', (e) => {
    if (e.target?.id === 'export-include-browser') {
      const include = e.target.checked ? '?include_browser=true' : '';
      const jsonLink = document.querySelector('a[href^="/api/export/json"]');
      const sqliteLink = document.querySelector('a[href^="/api/export/sqlite"]');
      if (jsonLink) jsonLink.href = '/api/export/json' + include;
      if (sqliteLink) sqliteLink.href = '/api/export/sqlite' + include;
    }
  });
})();

function renderCalendarPanel() {
  return `
    <div class="settings-section">
      <h2><span class="h2-icon">${icon('calendar', 18)}</span> カレンダー</h2>
      <div class="settings-help" style="margin-bottom:12px;">
        Google カレンダー / iCloud カレンダーから「予定」を取り込むと、検索・チャット・タイムラインに反映されます。
        Google / iCloud の <b>iCal URL（公開リンク）</b> を貼り付けて「登録」ボタンを押してください。
      </div>

      <div id="cal-current" style="margin-bottom:10px;font-size:13px;color:var(--text-3);">読み込み中…</div>

      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">
        <input id="cal-url-input" type="url"
          placeholder="https://calendar.google.com/calendar/ical/.../basic.ics"
          style="flex:1;min-width:280px;padding:8px 12px;border:1px solid var(--border-1);border-radius:8px;background:var(--bg-0);color:var(--text-0);font:inherit;font-size:13px;">
        <button class="settings-save-btn" id="cal-save-btn" type="button">登録 &amp; 取り込み</button>
      </div>
      <div id="cal-status" style="font-size:12px;color:var(--text-3);min-height:18px;margin-bottom:8px;"></div>

      <div id="cal-actions" hidden style="display:flex;gap:8px;margin-bottom:10px;">
        <button class="settings-save-btn" id="cal-reimport-btn" type="button" style="background:var(--bg-2);color:var(--text-1);">今すぐ再取り込み</button>
        <button class="settings-save-btn" id="cal-remove-btn" type="button" style="background:var(--bg-2);color:var(--text-2);">URL を解除</button>
      </div>

      <details style="margin-top:10px;font-size:12px;color:var(--text-3);">
        <summary style="cursor:pointer;color:var(--text-2);">iCal URL の取り方（クリックで展開）</summary>
        <div style="margin-top:8px;line-height:1.7;padding:10px 14px;background:var(--bg-1);border-radius:8px;">
          <p style="margin:0 0 8px;"><b>Google カレンダー</b></p>
          <ol style="margin:0 0 12px;padding-left:20px;">
            <li>ブラウザで calendar.google.com を開く</li>
            <li>左サイドバー → 「マイカレンダー」 → カレンダー名にホバー → 「︙」 → 「設定と共有」</li>
            <li>下にスクロール → 「カレンダーの統合」 → 「カレンダーの<b>非公開 URL</b>（iCal 形式）」をコピー</li>
            <li>上の入力欄に貼り付け</li>
          </ol>
          <p style="margin:0 0 8px;"><b>iCloud カレンダー</b></p>
          <ol style="margin:0 0 12px;padding-left:20px;">
            <li>Mac のカレンダー.app を開く</li>
            <li>左サイドバーのカレンダー名を <b>Ctrl+クリック</b> → 「カレンダーを公開」</li>
            <li>表示された URL（webcal:// で始まる）をコピー</li>
            <li>上の入力欄に貼り付け（自動で https:// に変換されます）</li>
          </ol>
          <p style="margin:0;color:var(--text-4);">※ 非公開 URL は人に教えないでください。Bunshin はこの URL を <code>~/.bunshin/calendar.json</code> に保存します（外部送信なし）。</p>
        </div>
      </details>
    </div>`;
}

function wireCalendarPanel() {
  const current = document.getElementById('cal-current');
  const input = document.getElementById('cal-url-input');
  const saveBtn = document.getElementById('cal-save-btn');
  const status = document.getElementById('cal-status');
  const actions = document.getElementById('cal-actions');
  const reimportBtn = document.getElementById('cal-reimport-btn');
  const removeBtn = document.getElementById('cal-remove-btn');
  if (!saveBtn) return;

  async function refresh() {
    try {
      const j = await (await fetch('/api/calendar/status')).json();
      if (j.url) {
        const truncated = j.url.length > 60 ? j.url.slice(0, 60) + '…' : j.url;
        current.innerHTML = `${icon('check-circle', 14)} 登録済み: <code style="font-size:11px;">${esc(truncated)}</code> ・ ${j.event_count} 件の予定`;
        current.style.color = 'var(--text-1)';
        actions.hidden = false;
      } else {
        current.textContent = 'まだ何も登録されていません';
        current.style.color = 'var(--text-3)';
        actions.hidden = true;
      }
    } catch {
      current.textContent = '状態取得に失敗';
    }
  }

  async function setStatus(text, cls) {
    status.textContent = text;
    status.style.color = (cls === 'error') ? '#ff6b6b'
                       : (cls === 'success') ? '#58cc6e'
                       : 'var(--text-3)';
  }

  saveBtn.addEventListener('click', async () => {
    const url = (input.value || '').trim();
    if (!url) { setStatus('URL を入力してください', 'error'); return; }
    saveBtn.disabled = true;
    setStatus('取り込み中…（数秒〜30秒）', '');
    try {
      const r = await fetch('/api/calendar/setup', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url}),
      });
      const j = await r.json();
      if (j.ok) {
        setStatus(`✓ ${j.imported || 0} 件の予定を取り込みました`, 'success');
        input.value = '';
        refresh();
        if (typeof loadStats === 'function') { try { loadStats(); } catch {} }
      } else {
        setStatus('✗ ' + (j.error || '登録に失敗しました'), 'error');
      }
    } catch (e) {
      setStatus('✗ ネットワークエラー', 'error');
    } finally {
      saveBtn.disabled = false;
    }
  });

  reimportBtn.addEventListener('click', async () => {
    reimportBtn.disabled = true;
    setStatus('再取り込み中…', '');
    try {
      const j = await (await fetch('/api/calendar/import', {method: 'POST'})).json();
      if (j.ok) {
        setStatus(`✓ ${j.imported || 0} 件を再取り込みしました`, 'success');
        refresh();
        if (typeof loadStats === 'function') { try { loadStats(); } catch {} }
      } else {
        setStatus('✗ ' + (j.error || '失敗'), 'error');
      }
    } finally {
      reimportBtn.disabled = false;
    }
  });

  removeBtn.addEventListener('click', async () => {
    if (!confirm('カレンダー URL を解除して、取り込んだ予定をすべて削除します。よろしいですか？')) return;
    removeBtn.disabled = true;
    try {
      const j = await (await fetch('/api/calendar/remove', {method: 'POST'})).json();
      if (j.ok) {
        setStatus(`✓ 解除しました（${j.removed} 件の予定を削除）`, 'success');
        refresh();
        if (typeof loadStats === 'function') { try { loadStats(); } catch {} }
      }
    } finally {
      removeBtn.disabled = false;
    }
  });

  refresh();
}

function renderUninstallPanel() {
  return `
    <div class="settings-section">
      <h2><span class="h2-icon">${icon('trash', 18)}</span> Bunshin を辞める</h2>
      <div class="settings-help" style="margin-bottom:12px;">
        合わなかった時のための、完全削除の手順です。理由を 1 つだけ教えてもらえると、次の人がもっと使いやすくなります（任意）。
      </div>
      <button class="settings-save-btn" id="uninstall-btn" type="button" style="background:var(--bg-2);color:var(--text-1);">
        ${icon('trash', 14)} アンインストール手順を見る
      </button>
    </div>`;
}

function wireUninstallPanel() {
  const btn = document.getElementById('uninstall-btn');
  if (btn) btn.addEventListener('click', openUninstallModal);
}

function openUninstallModal() {
  let bd = document.getElementById('uninstall-modal');
  if (!bd) {
    bd = document.createElement('div');
    bd.id = 'uninstall-modal';
    bd.className = 'mark-modal-backdrop';
    bd.style.display = 'none';
    document.body.appendChild(bd);
  }
  bd.innerHTML = `
    <div class="add-memory-modal" style="max-width:500px;">
      <h3>Bunshin を辞める</h3>
      <p class="sub">合わなくて辞めるとき、一番の理由を 1 つだけ教えてもらえると助かります（任意・匿名でも送れます）。送信しないで手順だけ見ることもできます。</p>
      <div style="display:flex;flex-direction:column;gap:8px;margin:14px 0;">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;"><input type="radio" name="uninstall-reason" value="heavy">動作が重い・遅い</label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;"><input type="radio" name="uninstall-reason" value="hard">使い方がわからない・難しい</label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;"><input type="radio" name="uninstall-reason" value="mismatch">想像と違った・必要なかった</label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;"><input type="radio" name="uninstall-reason" value="bug">バグ・エラーが多い</label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;"><input type="radio" name="uninstall-reason" value="other">その他</label>
      </div>
      <textarea id="uninstall-comment" placeholder="補足があれば（任意）— 例: 「Gmail 取り込みが Apple Pass... のところでつまずいた」" style="width:100%;min-height:70px;padding:10px;border:1px solid var(--border-1);border-radius:8px;background:var(--bg-0);color:var(--text-0);font:inherit;font-size:13px;resize:vertical;box-sizing:border-box;"></textarea>
      <div class="actions" style="margin-top:14px;">
        <button class="btn" type="button" id="uninstall-cancel">キャンセル</button>
        <button class="btn" type="button" id="uninstall-skip">送信しないで手順だけ見る</button>
        <button class="btn primary" type="button" id="uninstall-send">送信して手順を見る</button>
      </div>
      <div id="uninstall-steps" hidden style="margin-top:18px;padding-top:14px;border-top:1px solid var(--border-1);">
        <h4 style="margin:0 0 10px;font-size:14px;">削除手順（残骸ゼロ）</h4>
        <ol style="margin:0;padding-left:20px;font-size:13px;line-height:1.7;color:var(--text-1);">
          <li>Bunshin を終了する（メニューバー ∞ → 終了）</li>
          <li>Finder で <code>/Applications/Bunshin.app</code> を ゴミ箱へ</li>
          <li>ターミナルで <code>rm -rf ~/.bunshin</code> を実行（データ完全消去）</li>
          <li>必要なら <code>launchctl unload ~/Library/LaunchAgents/com.bunshin.update.plist</code> + plist 削除</li>
        </ol>
        <p style="margin-top:10px;color:var(--text-3);font-size:12px;">ありがとうございました。フィードバックは https://github.com/Marine923/bunshin-ai/issues でも歓迎です。</p>
      </div>
    </div>
  `;
  bd.style.display = 'flex';

  const close = () => { bd.style.display = 'none'; };
  document.getElementById('uninstall-cancel').addEventListener('click', close);
  bd.addEventListener('click', (e) => { if (e.target === bd) close(); });

  const showSteps = () => {
    const steps = document.getElementById('uninstall-steps');
    if (steps) steps.hidden = false;
  };

  document.getElementById('uninstall-skip').addEventListener('click', showSteps);

  document.getElementById('uninstall-send').addEventListener('click', () => {
    const reason = (document.querySelector('input[name="uninstall-reason"]:checked') || {}).value || 'unspecified';
    const comment = (document.getElementById('uninstall-comment').value || '').trim();
    const reasonLabel = {
      heavy: '動作が重い・遅い',
      hard: '使い方がわからない・難しい',
      mismatch: '想像と違った・必要なかった',
      bug: 'バグ・エラーが多い',
      other: 'その他',
      unspecified: '未選択',
    }[reason] || reason;
    const subj = `[Bunshin] アンインストール理由: ${reasonLabel}`;
    const body = `理由: ${reasonLabel}\\n\\n補足:\\n${comment || '(なし)'}\\n\\n--- 環境 ---\\nBunshin version: ${(typeof STATS_BUNSHIN_VERSION === 'string') ? STATS_BUNSHIN_VERSION : '0.7.0'}\\nOS: ${navigator.platform}\\n`;
    const mailto = `mailto:?subject=${encodeURIComponent(subj)}&body=${encodeURIComponent(body)}`;
    window.open(mailto, '_blank');
    showSteps();
  });
}

function renderTroubleshootPanel() {
  return `
    <div class="settings-section">
      <h2><span class="h2-icon">${icon('life-buoy', 18)}</span> 困った時は</h2>

      <div id="search-health" style="margin-bottom:14px;padding:12px 14px;border:1px solid var(--border-1);border-radius:8px;background:var(--bg-1);font-size:13px;color:var(--text-2);">
        検索エンジンの状態を確認中…
      </div>

      <div class="settings-help" style="margin-bottom:12px;">
        うまく動かない時は、下のボタンで診断情報を取得して、開発者にメールで送ってください。
        個人データ（メール本文・写真・記憶）は含まれません。OS バージョン・Bunshin バージョン・Ollama 状態・直近のログ 100 行だけです。
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;">
        <button class="settings-save-btn" id="diag-fetch-btn" type="button" style="background:var(--bg-2);color:var(--text-1);">
          ${icon('search', 14)} 診断情報を取得
        </button>
        <button class="settings-save-btn" id="diag-copy-btn" type="button" hidden style="background:var(--bg-2);color:var(--text-1);">
          ${icon('copy', 14)} コピー
        </button>
        <a class="settings-save-btn" id="diag-mail-btn" href="#" hidden style="text-decoration:none;text-align:center;">
          ${icon('mail', 14)} メールで送る
        </a>
        <a class="settings-save-btn" href="https://github.com/Marine923/bunshin-ai/issues/new/choose" target="_blank" rel="noopener" style="background:var(--bg-2);color:var(--text-1);text-decoration:none;text-align:center;">
          ${icon('external-link', 14)} GitHub Issues
        </a>
      </div>
      <textarea id="diag-output" hidden readonly
        style="width:100%;min-height:200px;padding:12px;border:1px solid var(--border-1);border-radius:8px;background:var(--bg-0);color:var(--text-1);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;line-height:1.5;resize:vertical;box-sizing:border-box;"
        placeholder="ここに診断情報が出ます"></textarea>
    </div>`;
}

async function refreshSearchHealth() {
  const el = document.getElementById('search-health');
  if (!el) return;
  try {
    const j = await (await fetch('/api/diagnostics')).json();
    const emb = j.embedding || {};
    const total = j.db?.record_count || 0;
    const indexed = emb.vec_count || 0;
    const pct = total > 0 ? Math.round((indexed / total) * 100) : 0;
    const ok = emb.ok && !emb.needs_rebuild;
    if (ok) {
      el.innerHTML = `${icon('check-circle', 14)} <b>検索エンジン正常</b>: ${total.toLocaleString()} 件の記憶のうち ${indexed.toLocaleString()} 件（${pct}%）がインデックス済み`;
      el.style.borderColor = 'rgba(88,204,110,0.4)';
      el.style.background = 'rgba(88,204,110,0.06)';
    } else {
      const errMsg = emb.error ? `<br><span style="color:var(--text-3);font-size:11px;">原因: ${esc(emb.error.slice(0, 100))}</span>` : '';
      const need = emb.needs_rebuild
        ? `<br><b style="color:#ff9b6b;">⚠ 検索インデックスが壊れている可能性があります</b> (${total.toLocaleString()} 件中 ${indexed.toLocaleString()} 件しかインデックスされていません)`
        : '';
      el.innerHTML = `
        ${icon('alert-triangle', 14)} <b>検索エンジンに問題があります</b>${errMsg}${need}
        <div style="margin-top:10px;">
          <button class="settings-save-btn" id="rebuild-embeddings-btn" type="button">${icon('database', 14)} 検索インデックスを再構築</button>
          <span id="rebuild-progress" style="margin-left:10px;color:var(--text-3);font-size:12px;"></span>
        </div>`;
      el.style.borderColor = 'rgba(255,155,107,0.5)';
      el.style.background = 'rgba(255,155,107,0.06)';
      const rb = document.getElementById('rebuild-embeddings-btn');
      if (rb) rb.addEventListener('click', rebuildEmbeddings);
    }
  } catch (e) {
    el.textContent = '状態取得に失敗しました';
  }
}

async function rebuildEmbeddings() {
  const btn = document.getElementById('rebuild-embeddings-btn');
  const pg = document.getElementById('rebuild-progress');
  if (!btn) return;
  if (!confirm('全 ' + (window._totalRecords || '?') + ' 件の記憶を再インデックスします。10〜30 分かかります。続けますか？')) return;
  btn.disabled = true;
  pg.textContent = '開始中…';
  try {
    const r = await fetch('/api/embedding/rebuild', { method: 'POST' });
    if (!r.body) { pg.textContent = '応答なし'; return; }
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\\n');
      buffer = lines.pop() || '';
      for (const ln of lines) {
        if (!ln.trim()) continue;
        try {
          const j = JSON.parse(ln);
          if (j.phase === 'progress') {
            const pct = Math.round((j.done / j.total) * 100);
            pg.textContent = `${j.done} / ${j.total} (${pct}%)`;
          } else if (j.phase === 'done') {
            pg.textContent = `✓ 完了 (${j.total} 件)`;
            setTimeout(refreshSearchHealth, 800);
          } else if (j.phase === 'error') {
            pg.textContent = '✗ ' + (j.error || 'エラー');
          }
        } catch {}
      }
    }
  } finally {
    btn.disabled = false;
  }
}

function wireTroubleshootPanel() {
  refreshSearchHealth();
  const btn = document.getElementById('diag-fetch-btn');
  const out = document.getElementById('diag-output');
  const copy = document.getElementById('diag-copy-btn');
  const mail = document.getElementById('diag-mail-btn');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = '取得中…';
    try {
      const r = await fetch('/api/diagnostics');
      const j = await r.json();
      const text = JSON.stringify(j, null, 2);
      if (out) { out.value = text; out.hidden = false; }
      if (copy) copy.hidden = false;
      if (mail) {
        mail.hidden = false;
        const subj = `Bunshin 困りごと (v${j.bunshin_version || '?'})`;
        const body = '下記の問題が起きました：\\n\\n[ここに状況を書いてください — 何をしたら、何が起きたか]\\n\\n--- 診断情報（自動生成） ---\\n' + text;
        mail.href = `mailto:?subject=${encodeURIComponent(subj)}&body=${encodeURIComponent(body)}`;
      }
    } catch (e) {
      if (out) { out.value = '取得に失敗しました。Bunshin を再起動してもう一度お試しください。'; out.hidden = false; }
    } finally {
      btn.disabled = false;
      btn.innerHTML = btn.innerHTML.replace('取得中…', '再取得');
    }
  });
  if (copy && out) {
    copy.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(out.value);
        const orig = copy.innerHTML;
        copy.textContent = '✓ コピー済み';
        setTimeout(() => { copy.innerHTML = orig; }, 1500);
      } catch {}
    });
  }
}

function renderPrivacyPanel() {
  return `
    <div class="settings-section">
      <h2><span class="h2-icon">${icon('lock', 18)}</span> プライバシー</h2>
      <div class="privacy-hero">
        <div class="privacy-promise">
          ${icon('check-circle', 16)}
          <span><b>あなたのデータは、この Mac から一歩も出ません。</b></span>
        </div>
        <p class="privacy-note">
          AI モデルはローカル（Ollama）で動作。Gmail / Calendar は読み取り専用、外部 AI 企業（Anthropic / OpenAI / Google）へのデータ送信は<b>ゼロ</b>です。
        </p>
      </div>
      <div id="privacy-status">
        <div style="font-size:12px;color:var(--text-4);padding:6px 0;">読み込み中…</div>
      </div>
    </div>`;
}

function _formatBytes(n) {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return n.toFixed(n < 10 ? 1 : 0) + ' ' + units[i];
}

async function loadPrivacyStatus() {
  const root = $('privacy-status');
  if (!root) return;
  try {
    const j = await (await fetch('/api/privacy/status')).json();
    const dbSize = _formatBytes(j.db_bytes || 0);
    const dataSize = _formatBytes(j.data_dir_bytes || 0);
    const outbound = j.outbound_destinations || [];

    root.innerHTML = `
      <div class="privacy-grid">
        <div class="privacy-row">
          <div class="privacy-label">${icon('database', 14)} データの保存場所</div>
          <div class="privacy-value">
            <code>${esc(j.db_path)}</code>
            <span class="privacy-muted">${esc(dbSize)}</span>
          </div>
        </div>
        <div class="privacy-row">
          <div class="privacy-label">${icon('folder', 14)} データフォルダ全体</div>
          <div class="privacy-value">
            <code>${esc(j.data_dir)}</code>
            <span class="privacy-muted">${esc(dataSize)}（バックアップ等含む）</span>
          </div>
        </div>
        <div class="privacy-row">
          <div class="privacy-label">${icon('check-circle', 14)} ローカル AI モデル</div>
          <div class="privacy-value">
            <span class="${j.ollama_running ? 'privacy-ok' : 'privacy-warn'}">
              ${j.ollama_running ? 'Ollama 稼働中（127.0.0.1:11434）' : 'Ollama 未起動 — AI チャットを使うには起動が必要'}
            </span>
          </div>
        </div>
      </div>

      <div class="privacy-section-title">外部への接続</div>
      ${outbound.length === 0 ? `
        <div class="privacy-zero">
          ${icon('check-circle', 14)}
          <span>外部サービスへの接続は<b>ありません</b>。すべての処理がローカルで完結しています。</span>
        </div>
      ` : `
        <div class="privacy-outbound">
          <p class="privacy-note" style="margin:0 0 8px;">あなたが許可した、読み取り専用の接続のみ：</p>
          ${outbound.map(d => `
            <div class="privacy-conn">
              ${icon('globe', 13)}
              <div>
                <code>${esc(d.host)}</code>
                <div class="privacy-muted">${esc(d.purpose)}</div>
              </div>
            </div>
          `).join('')}
        </div>
      `}

      <div class="privacy-footnote">
        <p>${icon('lightbulb', 12)}<span>データを別の場所に移したい時は「エクスポート」セクションから JSON / SQLite で持ち出せます。</span></p>
        <p>${icon('lightbulb', 12)}<span>すべて忘れたい時は <code>${esc(j.data_dir)}</code> フォルダごと削除すれば完全消去できます。</span></p>
      </div>
    `;
  } catch (e) {
    root.innerHTML = `<div style="color:#f87171;font-size:12px;">読み込みエラー: ${esc(String(e))}</div>`;
  }
}

function renderSchedulerPanel() {
  return `
    <div class="settings-section">
      <h2><span class="h2-icon">${icon('clock', 18)}</span> 自動取り込み</h2>
      <div class="settings-field" style="grid-template-columns: 1fr 220px;">
        <div>
          <div class="settings-label">1 時間ごとに自動更新</div>
          <div class="settings-help">
            ターミナル不要。Bunshin が裏で Claude 会話・ファイル・Gmail を取り込み続けます。
            <br>Mac のログイン時に自動起動 (macOS では launchd を使用)。
          </div>
          <div id="scheduler-status" style="margin-top:8px;font-size:12px;color:var(--text-3);">状態確認中…</div>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;align-items:flex-end;">
          <label class="settings-toggle" id="scheduler-toggle-wrap">
            <input type="checkbox" id="scheduler-toggle">
            <span class="knob"></span>
          </label>
          <button class="settings-save-btn" id="scheduler-run-now" style="background:var(--bg-2);color:var(--text-1);font-size:12px;padding:6px 14px;">今すぐ更新</button>
        </div>
      </div>
    </div>`;
}

async function loadSchedulerStatus() {
  const statusEl = $('scheduler-status');
  const toggle = $('scheduler-toggle');
  const wrap = $('scheduler-toggle-wrap');
  if (!statusEl || !toggle) return;
  try {
    const j = await (await fetch('/api/scheduler/status')).json();
    const isInstalled = !!j.installed;
    toggle.checked = isInstalled;
    if (wrap) wrap.classList.toggle('on', isInstalled);
    if (isInstalled) {
      statusEl.innerHTML = `${icon('check-circle', 12)} 有効 — ${esc(j.path || '')}`;
      statusEl.style.color = '#5fbf6f';
      statusEl.style.display = 'flex';
      statusEl.style.alignItems = 'center';
      statusEl.style.gap = '4px';
    } else {
      statusEl.textContent = '未設定 — トグルで有効化';
      statusEl.style.color = 'var(--text-3)';
    }
  } catch (e) {
    statusEl.textContent = '状態取得エラー: ' + e;
  }
}

function wireSchedulerPanel() {
  const wrap = $('scheduler-toggle-wrap');
  const toggle = $('scheduler-toggle');
  const runNow = $('scheduler-run-now');
  const statusEl = $('scheduler-status');
  if (!toggle || !wrap) return;

  wrap.addEventListener('click', async (ev) => {
    // The wrapper handles clicks (knob is visual only).
    ev.preventDefault();
    const turningOn = !toggle.checked;
    toggle.checked = turningOn;
    wrap.classList.toggle('on', turningOn);
    statusEl.textContent = turningOn ? '有効化中…' : '無効化中…';
    statusEl.style.color = 'var(--text-3)';
    try {
      const url = turningOn ? '/api/scheduler/install' : '/api/scheduler/uninstall';
      const r = await fetch(url, {method: 'POST'});
      const j = await r.json();
      if (!j.ok) {
        statusEl.textContent = 'エラー: ' + (j.message || '不明');
        statusEl.style.color = '#f87171';
        // Revert the toggle since the operation failed.
        toggle.checked = !turningOn;
        wrap.classList.toggle('on', !turningOn);
        return;
      }
      loadSchedulerStatus();
    } catch (e) {
      statusEl.textContent = 'エラー: ' + e;
      statusEl.style.color = '#f87171';
    }
  });

  if (runNow) {
    runNow.addEventListener('click', async () => {
      runNow.disabled = true;
      runNow.textContent = '実行中…';
      try {
        const r = await fetch('/api/scheduler/run-now', {method: 'POST'});
        const j = await r.json();
        runNow.textContent = j.ok ? '✓ 開始しました' : 'エラー';
        setTimeout(() => {
          runNow.textContent = '今すぐ更新';
          runNow.disabled = false;
        }, 3000);
      } catch (e) {
        runNow.textContent = 'エラー';
        runNow.disabled = false;
      }
    });
  }
}

function renderLearningDashboard() {
  return `
    <div class="settings-section">
      <h2><span class="h2-icon">${icon('brain', 18)}</span> 学習</h2>
      <div class="learning-dashboard">
        <h3>あなたが Bunshin に教えたこと</h3>
        <p class="desc">「要らない」マークした記録から学習したルール。クリックで取り消せます。</p>
        <div id="learning-rules-list">
          <div style="font-size:12px;color:var(--text-4);padding:6px 0;">読み込み中…</div>
        </div>
        <div class="reset-row">
          <span style="font-size:12px;color:var(--text-3);">学習を全部忘れて最初からやり直したいとき</span>
          <button class="reset-btn" id="learning-reset-btn">全部リセット</button>
        </div>
      </div>
    </div>`;
}

async function refreshLearningRules() {
  const root = $('learning-rules-list');
  if (!root) return;
  try {
    const j = await (await fetch('/api/learning/rules')).json();
    const rules = j.rules || [];
    if (!rules.length) {
      root.innerHTML = '<div style="font-size:12px;color:var(--text-4);padding:6px 0;">まだ何も学習していません。フラッシュバックや検索結果のカードの「要らない」ボタンを押すと、ここに記録されます。</div>';
      return;
    }
    root.innerHTML = rules.map(r => {
      const iconHtml = icon(r.action === 'hide' ? 'trash' : 'star', 14);
      const typeLabel = r.rule_type === 'sender' ? '送信者'
                       : r.rule_type === 'domain' ? 'ドメイン'
                       : '記録単体';
      const date = new Date(r.created_at * 1000).toLocaleDateString('ja-JP');
      return `
        <div class="rule-row">
          <span class="rule-icon">${iconHtml}</span>
          <span class="rule-type-badge">${esc(typeLabel)}</span>
          <span class="rule-pattern">${esc(r.pattern)}</span>
          <span class="rule-count">${r.applied_count.toLocaleString()}件・${esc(date)}</span>
          <button class="rule-delete" data-id="${r.id}">取り消す</button>
        </div>`;
    }).join('');
    root.querySelectorAll('.rule-delete').forEach(btn => {
      btn.addEventListener('click', async () => {
        const ruleId = parseInt(btn.dataset.id, 10);
        if (!confirm('このルールを取り消しますか？ 非表示にしていた記録が再表示されます。')) return;
        await fetch('/api/mark/undo', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({rule_id: ruleId}),
        });
        refreshLearningRules();
        loadStats();
      });
    });
  } catch (e) {
    root.innerHTML = '<div style="font-size:12px;color:#f87171;">読み込み失敗</div>';
  }
}

async function loadModelRecommendation() {
  const el = $('model-rec');
  const selectEl = $('chat-model-select');
  if (!el && !selectEl) return;
  try {
    const j = await (await fetch('/api/system/recommend-model')).json();
    const ram = j.ram_gb || 0;
    const model = j.recommended;
    const why = j.recommended_why || '';
    const installed = j.is_installed;
    const installCmd = `ollama pull ${model}`;

    // ---- Populate the model dropdown ----
    if (selectEl) {
      const current = selectEl.value || 'auto';
      const ladder = j.ladder || [];
      const installedSet = new Set(j.installed || []);
      // Build options: auto + every ladder model + current (if it's a
      // custom name the user typed in by hand). Mark each with status.
      const seen = new Set();
      const opts = [];
      opts.push({value: 'auto', label: 'auto（自動選択 — おすすめ）', status: 'auto'});
      for (const t of ladder) {
        const isRec = t.model === j.recommended;
        const isInstalled = installedSet.has(t.model);
        let suffix = '';
        if (isRec && isInstalled) suffix = '  ★ 推奨・インストール済み';
        else if (isRec) suffix = '  ★ 推奨（未ダウンロード）';
        else if (isInstalled) suffix = '  ✓ インストール済み';
        else suffix = '  · 未ダウンロード';
        opts.push({value: t.model, label: `${t.model}  —  ${t.headline}${suffix}`});
        seen.add(t.model);
      }
      // If the current value is a custom model name not in the ladder, keep it as an option.
      if (current && !seen.has(current) && current !== 'auto') {
        opts.unshift({value: current, label: `${current}  （カスタム）`});
      }
      selectEl.innerHTML = opts
        .map(o => `<option value="${esc(o.value)}" ${o.value === current ? 'selected' : ''}>${esc(o.label)}</option>`)
        .join('');
    }

    if (!el) return;
    el.classList.remove('model-rec-loading');
    el.classList.add('model-rec');
    el.innerHTML = `
      <div class="model-rec-head">
        ${icon('sparkles', 14)}
        <span><b>${esc(model)}</b> がおすすめ</span>
        <span class="model-rec-ram">（${ram} GB RAM）</span>
      </div>
      <div class="model-rec-why">${esc(why)}</div>
      ${installed
        ? `<div class="model-rec-installed">${icon('check-circle', 12)} ダウンロード済み — そのまま使えます</div>`
        : `<div class="model-rec-install">
            <span>未ダウンロード:</span>
            <code>${esc(installCmd)}</code>
            <button class="copy-btn-mini" data-copy="${esc(installCmd)}">コピー</button>
          </div>`}
    `;
    // Wire copy button
    const btn = el.querySelector('.copy-btn-mini');
    if (btn) {
      btn.addEventListener('click', () => {
        navigator.clipboard.writeText(btn.dataset.copy).then(() => {
          btn.textContent = '✓';
          setTimeout(() => { btn.textContent = 'コピー'; }, 1500);
        });
      });
    }
  } catch (e) {
    el.style.display = 'none';
  }
}

function wireLearningDashboard() {
  refreshLearningRules();
  const resetBtn = $('learning-reset-btn');
  if (resetBtn) {
    resetBtn.addEventListener('click', async () => {
      if (!confirm('学習を全部リセットしますか？\\nこれまでに「要らない」マークした全ての記録が再表示されます。\\n（記録そのものは消えません）')) return;
      await fetch('/api/learning/reset', {method: 'POST'});
      refreshLearningRules();
      loadStats();
    });
  }
}

async function refreshBackupList() {
  const root = $('backup-list');
  if (!root) return;
  try {
    const j = await (await fetch('/api/backups')).json();
    const items = j.backups || [];
    if (!items.length) {
      root.innerHTML = '<div style="color:var(--text-4);font-size:12px;padding:8px 0;">バックアップはまだありません。</div>';
      return;
    }
    root.innerHTML = items.map(b => `
      <div class="backup-row">
        <div class="backup-meta">
          <div class="backup-name">${esc(b.name)}</div>
          <div class="backup-info">${esc(b.mtime_str)} · ${(b.bytes/(1024*1024)).toFixed(1)} MB</div>
        </div>
        <button class="backup-restore-btn" data-path="${esc(b.path)}">復元</button>
      </div>`).join('');
  } catch {
    root.innerHTML = '<div style="color:#f87171;font-size:12px;padding:8px 0;">バックアップ一覧の取得に失敗しました。</div>';
  }
}

function wireBackupPanel() {
  const create = $('backup-create-btn');
  if (create) {
    create.addEventListener('click', async () => {
      create.disabled = true;
      create.textContent = '作成中…';
      try {
        const r = await fetch('/api/backups', { method: 'POST' });
        const j = await r.json();
        if (j.error) {
          alert('失敗: ' + j.error);
        } else {
          await refreshBackupList();
        }
      } finally {
        create.disabled = false;
        create.textContent = '今すぐ作成';
      }
    });
  }
  const list = $('backup-list');
  if (list) {
    list.addEventListener('click', async (e) => {
      const btn = e.target.closest('.backup-restore-btn');
      if (!btn) return;
      const path = btn.dataset.path;
      if (!path) return;
      if (!confirm('このバックアップから復元します。現在の DB は安全のため別ファイルに保存されます。続けますか？')) return;
      btn.disabled = true;
      btn.textContent = '復元中…';
      try {
        const r = await fetch('/api/backups/restore', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path }),
        });
        const j = await r.json();
        if (!r.ok || j.error) {
          alert('復元失敗: ' + (j.error || j.detail || r.statusText));
        } else {
          alert('復元しました。Bunshin を再起動してください。\\n旧 DB: ' + j.previous_saved_to);
        }
      } finally {
        btn.disabled = false;
        btn.textContent = '復元';
      }
    });
  }
  refreshBackupList();
}

async function loadSettings() {
  if (settingsLoaded) return;
  const root = $('settings-content');
  try {
    const j = await (await fetch('/api/settings')).json();
    settingsSchemaCache = j.schema;
    settingsCurrent = JSON.parse(JSON.stringify(j.settings));  // working copy

    // Group by section
    const bySection = {};
    for (const [key, meta] of Object.entries(j.schema)) {
      const s = meta.section || 'misc';
      (bySection[s] ||= []).push([key, meta]);
    }

    let html = '';
    for (const section of Object.keys(bySection)) {
      const meta = SECTION_TITLES[section] || { ja: section, icon: null };
      const iconHtml = meta.icon ? `<span class="h2-icon">${icon(meta.icon, 18)}</span> ` : '';
      html += `<div class="settings-section"><h2>${iconHtml}${esc(meta.ja)}</h2>`;
      for (const [key, meta] of bySection[section]) {
        const current = settingsCurrent[key];
        const extra = key === 'chat_preferred_model'
          ? '<div id="model-rec" class="model-rec-loading">あなたの Mac に最適なモデルを判定中…</div>'
          : '';
        html += `<div class="settings-field">
          <div>
            <div class="settings-label">${esc(meta.label_ja || key)}</div>
            <div class="settings-help">${esc(meta.help_ja || '')}</div>
            ${extra}
          </div>
          <div>${renderSettingControl(key, meta, current)}</div>
        </div>`;
      }
      html += '</div>';
    }
    html += `<div class="settings-save-bar">
      <span class="settings-toast" id="settings-toast"></span>
      <button class="settings-save-btn" id="settings-save-btn">保存</button>
    </div>`;
    // Extra panels that don't fit the schema-driven flow.
    html += renderPrivacyPanel();
    html += renderCalendarPanel();
    html += renderSchedulerPanel();
    html += renderBackupPanel();
    html += renderExportPanel();
    html += renderLearningDashboard();
    html += renderTroubleshootPanel();
    html += renderUninstallPanel();
    root.innerHTML = html;
    settingsLoaded = true;
    wireCalendarPanel();
    wireBackupPanel();
    wireLearningDashboard();
    wireSchedulerPanel();
    wireTroubleshootPanel();
    wireUninstallPanel();
    loadModelRecommendation();
    loadSchedulerStatus();
    loadPrivacyStatus();

    // Attach toggle behaviour
    root.querySelectorAll('.settings-toggle').forEach(el => {
      el.addEventListener('click', () => {
        const cb = el.querySelector('input');
        cb.checked = !cb.checked;
        el.classList.toggle('on', cb.checked);
        settingsCurrent[cb.dataset.key] = cb.checked;
      });
    });
    root.querySelectorAll('input.settings-input, select.settings-input').forEach(el => {
      el.addEventListener('change', () => {
        const key = el.dataset.key;
        const meta = settingsSchemaCache[key];
        let v = el.value;
        if (meta.type === 'int') v = parseInt(v, 10);
        else if (meta.type === 'float') v = parseFloat(v);
        settingsCurrent[key] = v;
      });
    });
    $('settings-save-btn').addEventListener('click', saveSettings);
  } catch (e) {
    root.innerHTML = `<div class="empty">エラー: ${esc(String(e))}</div>`;
  }
}

function renderSettingControl(key, meta, current) {
  // Chat model field gets a dynamic dropdown — populated in
  // loadModelRecommendation() once we know which models are installed.
  if (key === 'chat_preferred_model') {
    return `<select class="settings-input" data-key="${esc(key)}" id="chat-model-select">
      <option value="${esc(current || 'auto')}" selected>${esc(current || 'auto')}</option>
    </select>`;
  }
  if (meta.type === 'bool') {
    const on = current ? 'on' : '';
    return `<label class="settings-toggle ${on}">
      <input type="checkbox" data-key="${esc(key)}" ${current ? 'checked' : ''}>
      <span class="knob"></span>
    </label>`;
  }
  if (meta.type === 'enum') {
    const opts = meta.enum.map(o => `<option value="${esc(o)}" ${o===current?'selected':''}>${esc(o)}</option>`).join('');
    return `<select class="settings-input" data-key="${esc(key)}">${opts}</select>`;
  }
  if (meta.type === 'int' || meta.type === 'float') {
    const min = meta.min !== undefined ? `min="${meta.min}"` : '';
    const max = meta.max !== undefined ? `max="${meta.max}"` : '';
    return `<input type="number" class="settings-input" data-key="${esc(key)}" value="${esc(String(current))}" ${min} ${max}>`;
  }
  return `<input type="text" class="settings-input" data-key="${esc(key)}" value="${esc(String(current))}">`;
}

async function saveSettings() {
  const btn = $('settings-save-btn');
  const toast = $('settings-toast');
  btn.disabled = true;
  toast.textContent = '保存中…';
  toast.classList.remove('error');
  try {
    const r = await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ values: settingsCurrent }),
    });
    const j = await r.json();
    if (j.errors && Object.keys(j.errors).length) {
      toast.textContent = 'エラー: ' + Object.entries(j.errors).map(([k,v]) => `${k}: ${v}`).join(', ');
      toast.classList.add('error');
    } else {
      const n = Object.keys(j.updated || {}).length;
      toast.textContent = `✓ ${n} 項目を保存しました`;
      setTimeout(() => { toast.textContent = ''; }, 3000);
    }
  } catch (e) {
    toast.textContent = 'エラー: ' + e;
    toast.classList.add('error');
  } finally {
    btn.disabled = false;
  }
}

// ===== Knowledge Graph =====
let entitiesLoaded = false;
let allEntities = [];

async function loadEntities() {
  if (entitiesLoaded) return;
  const listEl = $('entity-list');
  try {
    const j = await (await fetch('/api/entities')).json();
    allEntities = j.entities || [];
    if (!allEntities.length) {
      listEl.innerHTML = '<div class="empty">エンティティ未構築<br><br>ターミナルで <code>bun graph build</code> を実行してください</div>';
      $('entity-web-loading').textContent = 'エンティティが構築されていません';
      return;
    }
    renderEntityList(allEntities);
    entitiesLoaded = true;
    // Initialize the spider-web view with the most-mentioned entity.
    const top = [...allEntities].filter(e => e.mentions > 0)
      .sort((a, b) => b.mentions - a.mentions)[0];
    if (top) await loadEntityWeb(top.id);
  } catch (e) {
    listEl.innerHTML = `<div class="empty">エラー: ${esc(String(e))}</div>`;
    $('entity-web-loading').textContent = 'エラー';
  }
}

// ===== Spider-web force-directed graph =====
let _webSim = null;
let _webRoot = null;

async function loadEntityWeb(centerId) {
  // Sync the active highlight in the entity list so the user sees which
  // entity is at the center, no matter which surface they clicked from.
  document.querySelectorAll('.entity-pill').forEach(el => el.classList.remove('active'));
  const _pill = document.querySelector(`.entity-pill[data-id="${centerId}"]`);
  if (_pill) _pill.classList.add('active');

  const loading = $('entity-web-loading');
  loading.style.display = '';
  loading.textContent = 'グラフを描画中…';
  try {
    const j = await (await fetch('/api/entities/' + encodeURIComponent(centerId))).json();
    const center = j.entity;
    // API returns "relations" (plural). Older code path called it
    // "related" — accept either so we don't break on a stale build.
    const all = j.relations || j.related || [];
    const neighbors = all.slice(0, 18);
    _webRoot = { center, neighbors };
    drawWeb(center, neighbors);
    loading.style.display = 'none';
    renderEntityDetailFromAPI(center, all);
  } catch (e) {
    loading.textContent = 'エラー: ' + String(e);
  }
}

function renderEntityDetailFromAPI(e, related) {
  const detailEl = $('entity-detail');
  if (!detailEl) return;
  detailEl.innerHTML = `
    <h2>${esc(e.name)}</h2>
    <div>
      <span class="type-badge type-${esc(e.type)}">${esc(e.type)}</span>
      ${e.aliases?.length ? `<span style="color:var(--text-3);font-size:12px;">別名: ${esc(e.aliases.join(', '))}</span>` : ''}
    </div>
    ${e.description ? `<div class="description">${esc(e.description)}</div>` : ''}
    <div class="section">
      <h3><span class="h3-icon">${icon('link', 14)}</span> 関連エンティティ（特異性スコア順）</h3>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;">
        ${related.slice(0, 16).map(r => `
          <div class="entity-pill" data-id="${r.id}" style="margin:0;cursor:pointer;">
            <div class="name">${esc(r.name)}</div>
            <div class="meta">
              <span class="type-${esc(r.type)}">${esc(r.type)}</span> ·
              ${r.co_occurrences}回共起 ·
              <span style="color:var(--good);">特異性 ${(r.specificity*100).toFixed(0)}%</span>
            </div>
          </div>`).join('')}
      </div>
    </div>`;
  detailEl.querySelectorAll('.entity-pill').forEach(el => {
    el.addEventListener('click', () => {
      loadEntityWeb(el.dataset.id);
    });
  });
}

function drawWeb(center, neighbors) {
  const svg = $('entity-web-svg');
  if (!svg) return;
  const rect = svg.getBoundingClientRect();
  const W = rect.width || 800;
  const H = rect.height || 500;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  // Build node + edge data.
  const nodes = [
    { id: center.id, name: center.name, type: center.type, role: 'center',
      x: W / 2, y: H / 2, vx: 0, vy: 0, pinned: true },
  ];
  const edges = [];
  const n = neighbors.length;
  const radius = Math.min(W, H) * 0.36;
  neighbors.forEach((r, i) => {
    const angle = (i / Math.max(n, 1)) * Math.PI * 2;
    nodes.push({
      id: r.id, name: r.name, type: r.type, role: 'neighbor',
      weight: r.specificity || 0.5,
      x: W / 2 + Math.cos(angle) * radius,
      y: H / 2 + Math.sin(angle) * radius,
      vx: 0, vy: 0,
    });
    edges.push({ source: center.id, target: r.id, weight: r.specificity || 0.5 });
  });

  // Build SVG (clear first).
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  const gEdges = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  svg.appendChild(gEdges);
  const gNodes = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  svg.appendChild(gNodes);

  const edgeEls = edges.map(ed => {
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('class', 'web-edge');
    line.setAttribute('stroke-width', String(0.8 + ed.weight * 2.5));
    line.dataset.target = ed.target;
    gEdges.appendChild(line);
    return { el: line, source: ed.source, target: ed.target };
  });

  const nodeEls = nodes.map(node => {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'web-node ' + node.role);
    g.dataset.id = node.id;
    const r = node.role === 'center' ? 30 : Math.max(12, 14 + (node.weight || 0.5) * 10);
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('r', String(r));
    g.appendChild(circle);
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('y', String(r + 14));
    text.textContent = node.name.length > 14 ? node.name.slice(0, 13) + '…' : node.name;
    g.appendChild(text);
    gNodes.appendChild(g);
    return { el: g, circle, text, node, r };
  });

  // Wire interactions: click → recenter; drag → reposition; hover → highlight edges.
  nodeEls.forEach((ne) => {
    ne.el.addEventListener('click', () => {
      if (ne.node.role === 'center') return;
      loadEntityWeb(ne.node.id);
    });
    ne.el.style.cursor = ne.node.role === 'center' ? 'default' : 'pointer';
    ne.el.addEventListener('mouseenter', () => {
      edgeEls.forEach(ed => {
        if (ed.source === ne.node.id || ed.target === ne.node.id) ed.el.classList.add('hot');
        else ed.el.classList.add('faded');
      });
      nodeEls.forEach(other => {
        if (other.node.id !== ne.node.id && other.node.role !== 'center') {
          const connected = edges.some(ed =>
            (ed.source === ne.node.id && ed.target === other.node.id) ||
            (ed.target === ne.node.id && ed.source === other.node.id));
          if (!connected) other.el.classList.add('faded');
        }
      });
    });
    ne.el.addEventListener('mouseleave', () => {
      edgeEls.forEach(ed => { ed.el.classList.remove('hot'); ed.el.classList.remove('faded'); });
      nodeEls.forEach(other => other.el.classList.remove('faded'));
    });

    // Drag.
    let dragging = false;
    let startX = 0, startY = 0;
    let originX = 0, originY = 0;
    ne.el.addEventListener('pointerdown', (e) => {
      dragging = true;
      ne.node.pinned = true;
      startX = e.clientX; startY = e.clientY;
      originX = ne.node.x; originY = ne.node.y;
      ne.el.setPointerCapture(e.pointerId);
    });
    ne.el.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      const ratio = W / rect.width;
      ne.node.x = originX + (e.clientX - startX) * ratio;
      ne.node.y = originY + (e.clientY - startY) * ratio;
      requestSimStep();
    });
    ne.el.addEventListener('pointerup', (e) => {
      dragging = false;
      if (ne.node.role !== 'center') ne.node.pinned = false;
      ne.el.releasePointerCapture(e.pointerId);
    });
  });

  // Force simulation.
  if (_webSim) cancelAnimationFrame(_webSim);
  let cooling = 1.0;
  function step() {
    // Repulsion between every pair.
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dist2 = dx * dx + dy * dy + 0.01;
        const dist = Math.sqrt(dist2);
        const force = 4500 / dist2;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        if (!a.pinned) { a.vx += fx; a.vy += fy; }
        if (!b.pinned) { b.vx -= fx; b.vy -= fy; }
      }
    }
    // Attraction along edges.
    edges.forEach(ed => {
      const a = nodes.find(n => n.id === ed.source);
      const b = nodes.find(n => n.id === ed.target);
      if (!a || !b) return;
      const dx = b.x - a.x, dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) + 0.01;
      const target = 180 - ed.weight * 60;  // stronger ties pull closer
      const force = (dist - target) * 0.02;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      if (!a.pinned) { a.vx += fx; a.vy += fy; }
      if (!b.pinned) { b.vx -= fx; b.vy -= fy; }
    });
    // Centering pull.
    nodes.forEach(n => {
      if (n.pinned) return;
      n.vx += (W / 2 - n.x) * 0.003;
      n.vy += (H / 2 - n.y) * 0.003;
    });
    // Apply with damping.
    nodes.forEach(n => {
      if (n.pinned) { n.vx = 0; n.vy = 0; return; }
      n.vx *= 0.85 * cooling;
      n.vy *= 0.85 * cooling;
      n.x += n.vx;
      n.y += n.vy;
      // Soft bounds.
      n.x = Math.max(50, Math.min(W - 50, n.x));
      n.y = Math.max(50, Math.min(H - 50, n.y));
    });
    nodeEls.forEach(ne => {
      ne.el.setAttribute('transform', `translate(${ne.node.x.toFixed(1)} ${ne.node.y.toFixed(1)})`);
    });
    edgeEls.forEach(ed => {
      const a = nodes.find(n => n.id === ed.source);
      const b = nodes.find(n => n.id === ed.target);
      if (!a || !b) return;
      ed.el.setAttribute('x1', a.x.toFixed(1));
      ed.el.setAttribute('y1', a.y.toFixed(1));
      ed.el.setAttribute('x2', b.x.toFixed(1));
      ed.el.setAttribute('y2', b.y.toFixed(1));
    });
    cooling *= 0.997;
    if (cooling > 0.05) {
      _webSim = requestAnimationFrame(step);
    } else {
      _webSim = null;
    }
  }
  function requestSimStep() {
    if (_webSim) return;
    cooling = Math.max(cooling, 0.4);
    _webSim = requestAnimationFrame(step);
  }
  _webSim = requestAnimationFrame(step);
}

// View switcher (web ↔ list).
document.addEventListener('click', (e) => {
  const btn = e.target.closest('.graph-view-btn');
  if (!btn) return;
  const view = btn.dataset.view;
  document.querySelectorAll('.graph-view-btn').forEach(b => b.classList.toggle('active', b === btn));
  const listEl = $('entity-list');
  const webEl = $('entity-web');
  const hint = $('graph-view-hint');
  if (view === 'web') {
    listEl.style.display = 'none';
    webEl.style.display = '';
    if (hint) hint.textContent = 'ノードクリックで中央を切り替え、ドラッグで動かす';
    if (_webRoot) drawWeb(_webRoot.center, _webRoot.neighbors);
  } else {
    webEl.style.display = 'none';
    listEl.style.display = '';
    if (hint) hint.textContent = '左でエンティティを選ぶ';
  }
});

function renderEntityList(entities) {
  const listEl = $('entity-list');
  // Filter out zero-mention entities
  const list = entities.filter(e => e.mentions > 0);
  listEl.innerHTML = list.map(e => `
    <div class="entity-pill" data-id="${e.id}">
      <div class="name">${esc(e.name)}</div>
      <div class="meta">
        <span class="type-${esc(e.type)}">${esc(e.type)}</span> · ${e.mentions}件言及
      </div>
    </div>
  `).join('');
  listEl.querySelectorAll('.entity-pill').forEach(el => {
    el.addEventListener('click', () => loadEntityWeb(el.dataset.id));
  });
}

async function loadEntityDetail(entityId) {
  document.querySelectorAll('.entity-pill').forEach(el => el.classList.remove('active'));
  const pill = document.querySelector(`.entity-pill[data-id="${entityId}"]`);
  if (pill) pill.classList.add('active');

  const detailEl = $('entity-detail');
  detailEl.innerHTML = '<div class="loading">読み込み中…</div>';

  try {
    const j = await (await fetch(`/api/entities/${entityId}`)).json();
    if (j.error) {
      detailEl.innerHTML = `<div class="empty">${esc(j.error)}</div>`;
      return;
    }
    const e = j.entity;
    let html = `
      <h2>${esc(e.name)}</h2>
      <div>
        <span class="type-badge">${esc(e.type)}</span>
        ${e.aliases.length ? `<span class="type-badge">別名: ${esc(e.aliases.join(', '))}</span>` : ''}
      </div>
    `;
    if (e.description) {
      html += `<div class="description">${esc(e.description)}</div>`;
    }

    if (j.relations?.length) {
      html += `
        <div class="section">
          <h3><span class="h3-icon">${icon('link', 14)}</span> 関連エンティティ（特異性スコア順）</h3>
          <div class="hint" style="margin-bottom:12px;color:#888;font-size:12px;">
            ${esc(e.name)} と一緒に登場する記録ベース。特異性 = 「その相手が登場する記録のうち、${esc(e.name)} と一緒の割合」が高いほど真の関係性が強い。
          </div>
          <div class="relation-grid">
            ${j.relations.map(r => {
              const specPct = Math.round(r.specificity * 100);
              const specColor = specPct >= 50 ? '#5fbf6f' : specPct >= 25 ? '#efaf4a' : '#888';
              return `
                <div class="relation-card" data-id="${r.id}">
                  <div class="name">${esc(r.name)}</div>
                  <div class="weight">
                    <span class="type-${esc(r.type)}">${esc(r.type)}</span> · ${r.weight}回共起
                  </div>
                  <div style="margin-top:4px;font-size:11px;color:${specColor};">
                    特異性 ${specPct}% (${r.weight}/${r.e2_total})
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    if (j.records?.length) {
      html += `<div class="section"><h3>📜 直近の言及記録</h3>`;
      for (const r of j.records) {
        const ts = r.timestamp ? new Date(r.timestamp * 1000).toLocaleString('ja-JP') : 'n/a';
        const snippet = r.content.length > 300 ? r.content.slice(0, 300) + '...' : r.content;
        html += `
          <div class="entity-record">
            <div class="meta">${esc(ts)} · ${esc(r.source)}</div>
            <div class="content">${esc(snippet)}</div>
          </div>
        `;
      }
      html += `</div>`;
    }

    detailEl.innerHTML = html;
    detailEl.querySelectorAll('.relation-card').forEach(el => {
      el.addEventListener('click', () => loadEntityWeb(el.dataset.id));
    });
    // Scroll to top of detail
    detailEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    detailEl.innerHTML = `<div class="empty">エラー: ${esc(String(e))}</div>`;
  }
}

// ===== Timeline =====
const TIMELINE_SOURCE_ICONS = {
  claude: '💬', gmail: '📧', file: '📄', manual: '📝',
  calendar: '📅', line: '💬', browser: '🌐',
  notes: '📓', imessage: '💌', photo: '📷', photos_app: '📸'
};
let _timelineDays = 30;
async function loadTimeline(days) {
  if (typeof days === 'number') _timelineDays = days;
  const c = $('timeline-content');
  c.innerHTML = '<div class="loading">読み込み中…</div>';
  try {
    const r = await fetch(`/api/timeline?days=${_timelineDays}`);
    const j = await r.json();
    if (!j.days || !j.days.length) {
      c.innerHTML = '<div class="empty">この期間はまだ静かです</div>';
      return;
    }
    c.innerHTML = j.days.map(renderTimelineDay).join('');
  } catch (e) {
    c.innerHTML = `<div class="empty">エラー: ${esc(String(e))}</div>`;
  }
}
function renderTimelineDay(d) {
  const sources = Object.entries(d.sources)
    .sort((a,b) => b[1] - a[1])
    .map(([src, cnt]) => {
      const iconHtml = icon(SOURCE_ICON_NAME[src] || 'file-text', 13);
      const lbl = SOURCE_LABEL_JA[src] || src;
      return `<span class="src-pill" data-src="${src}" data-date="${d.date}" title="${lbl}: ${cnt} 件">${iconHtml} ${cnt}</span>`;
    }).join('');
  return `
    <div class="timeline-day" data-date="${d.date}">
      <div class="timeline-day-header">
        <span class="timeline-day-date">${formatDateLabel(d.date)}</span>
        <span class="timeline-day-total">合計 ${d.total} 件</span>
      </div>
      <div class="timeline-day-sources">${sources}</div>
      <div class="timeline-day-records" style="display:none"></div>
    </div>`;
}
function formatDateLabel(yyyy_mm_dd) {
  const [y, mo, d] = yyyy_mm_dd.split('-').map(n => parseInt(n));
  const dt = new Date(y, mo - 1, d);
  const today = new Date();
  today.setHours(0,0,0,0);
  const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
  const isToday = dt.getTime() === today.getTime();
  const isYesterday = dt.getTime() === yesterday.getTime();
  const weekday = ['日','月','火','水','木','金','土'][dt.getDay()];
  let suffix = '';
  if (isToday) suffix = '<span class="today-marker">今日</span>';
  else if (isYesterday) suffix = '<span class="today-marker">昨日</span>';
  return `${yyyy_mm_dd} (${weekday})${suffix}`;
}
function formatTimelineTime(ts) {
  const d = new Date(ts * 1000);
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}
document.addEventListener('click', async (e) => {
  const pill = e.target.closest('.src-pill');
  if (!pill) return;
  const dayEl = pill.closest('.timeline-day');
  if (!dayEl) return;
  const recordsEl = dayEl.querySelector('.timeline-day-records');
  const date = pill.dataset.date;
  const source = pill.dataset.src;
  const sameSource = recordsEl.dataset.source === source;
  const isOpen = recordsEl.style.display !== 'none';
  // Reset all pills in this day
  dayEl.querySelectorAll('.src-pill').forEach(p => p.classList.remove('expanded'));
  if (isOpen && sameSource) {
    recordsEl.style.display = 'none';
    recordsEl.dataset.source = '';
    return;
  }
  pill.classList.add('expanded');
  recordsEl.dataset.source = source;
  recordsEl.style.display = 'block';
  recordsEl.innerHTML = '<div class="loading">読み込み中…</div>';
  try {
    const r = await fetch(`/api/timeline/day?date=${date}&source=${encodeURIComponent(source)}&limit=50`);
    const j = await r.json();
    if (!j.results.length) {
      recordsEl.innerHTML = '<div class="empty">なし</div>';
      return;
    }
    recordsEl.innerHTML = j.results.map(rec => {
      const time = formatTimelineTime(rec.timestamp);
      const text = rec.content.slice(0, 400) + (rec.content.length > 400 ? '…' : '');
      return `
        <div class="timeline-record">
          <div class="timeline-rec-time">${time}</div>
          <div class="timeline-rec-content">${esc(text)}</div>
        </div>`;
    }).join('');
  } catch (err) {
    recordsEl.innerHTML = `<div class="empty">エラー: ${esc(String(err))}</div>`;
  }
});
document.querySelectorAll('#timeline-periods .filter-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('#timeline-periods .filter-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    loadTimeline(parseInt(chip.dataset.days));
  });
});

// Hover-preview on timeline source pills: lazy-fetch the first record
// for (date × source) so users can scan a day's content without clicking.
const _pillPreviewCache = {};
async function fetchPillPreview(date, source) {
  const key = date + '|' + source;
  if (_pillPreviewCache[key] !== undefined) return _pillPreviewCache[key];
  try {
    const r = await fetch(
      '/api/timeline/day?date=' + date +
      '&source=' + encodeURIComponent(source) + '&limit=1'
    );
    const j = await r.json();
    const rec = j.results && j.results[0];
    _pillPreviewCache[key] = rec || null;
    return _pillPreviewCache[key];
  } catch {
    _pillPreviewCache[key] = null;
    return null;
  }
}
document.addEventListener('mouseover', async (e) => {
  const pill = e.target.closest && e.target.closest('.src-pill');
  if (!pill) return;
  if (pill.querySelector('.src-pill-preview')) return;
  const date = pill.dataset.date;
  const source = pill.dataset.src;
  if (!date || !source) return;
  const rec = await fetchPillPreview(date, source);
  if (!rec || pill.querySelector('.src-pill-preview')) return;
  const preview = document.createElement('div');
  preview.className = 'src-pill-preview';
  const time = formatTimelineTime(rec.timestamp);
  const body = (rec.content || '').slice(0, 240);
  preview.innerHTML =
    '<div class="preview-meta">' + time + ' · ' + esc(rec.source) + '</div>' +
    '<div class="preview-body">' + esc(body) + '</div>';
  pill.appendChild(preview);
});

// ===== Insights =====
let insightsLoaded = false;
async function loadInsights() {
  if (insightsLoaded) return;
  const content = $('insights-content');
  const genEl = $('insights-generated');
  try {
    const j = await (await fetch('/api/insights')).json();
    genEl.textContent = `生成: ${j.generated_at}`;
    let html = '';

    // "今日これだけ見ればOK" hero card — picks the single most actionable
    // insight from the bundle so non-power users don't drown in 5 sections.
    // Priority: imminent event > stale project > recent file.
    const top = (() => {
      if (j.upcoming_events?.length) {
        const e = j.upcoming_events[0];
        const loc = e.location ? ` @ ${esc(e.location)}` : '';
        return {
          icon: 'calendar',
          label: '今日これだけ見ればOK',
          headline: `次の予定: ${esc(e.summary)}`,
          sub: `${esc(e.start)}${loc}`,
          tone: 'event',
        };
      }
      if (j.inactive_projects?.length) {
        const p = j.inactive_projects[0];
        return {
          icon: 'flame',
          label: '今日これだけ見ればOK',
          headline: `「${esc(p.name)}」が ${p.days_ago} 日動いてません`,
          sub: `最終 ${esc(p.last_seen)} ｜ ${esc((p.description || '').slice(0, 80))}`,
          tone: 'stale',
        };
      }
      if (j.recent_files?.length) {
        const f = j.recent_files[0];
        return {
          icon: 'folder',
          label: '最近触ったファイル',
          headline: esc(f.name),
          sub: esc(f.modified),
          tone: 'recent',
        };
      }
      return null;
    })();
    if (top) {
      html += `
        <div class="insights-hero insights-hero-${top.tone}">
          <div class="insights-hero-label">${icon(top.icon, 14)} ${top.label}</div>
          <div class="insights-hero-headline">${top.headline}</div>
          <div class="insights-hero-sub">${top.sub}</div>
        </div>
      `;
    }

    // LLM digest section — shown only as a button, fetched on click.
    html += `
      <div class="insights-section">
        <h2><span class="h2-icon">${icon('newspaper', 18)}</span> 過去7日間のサマリ（AI 生成）</h2>
        <div id="digest-area">
          <button id="digest-btn" class="settings-save-btn" style="background:#3a5a8a;padding:8px 18px;font-size:13px;">
            AI でサマリを作成（30 秒〜2 分）
          </button>
        </div>
      </div>
    `;

    if (j.setup_hints?.length) {
      html += `<div class="insights-section"><h2><span class="h2-icon">${icon('tool', 18)}</span> セットアップ案内</h2>`;
      for (const h of j.setup_hints) {
        html += `
          <div class="insights-card" style="border-left:3px solid #efaf4a;">
            <div class="body">${esc(h.message)}</div>
          </div>`;
      }
      html += '</div>';
    }

    if (j.inactive_projects?.length) {
      html += `<div class="insights-section"><h2><span class="h2-icon">${icon('flame', 18)}</span> 長期未活動プロジェクト</h2>`;
      for (const p of j.inactive_projects) {
        html += `
          <div class="insights-card alert">
            <div class="title">${esc(p.name)} — <span style="color:#ef4a4a">${p.days_ago}日未活動</span></div>
            <div class="meta">最終 ${esc(p.last_seen)} ｜ ${esc(p.description)}</div>
            <div class="body">${esc(p.snippet)}…</div>
          </div>`;
      }
      html += '</div>';
    }

    if (j.upcoming_events?.length) {
      html += `<div class="insights-section"><h2><span class="h2-icon">${icon('calendar', 18)}</span> 直近の予定（14日以内）</h2>`;
      for (const e of j.upcoming_events) {
        const loc = e.location ? ` @ ${esc(e.location)}` : '';
        html += `
          <div class="insights-card upcoming">
            <div class="title">${esc(e.summary)}</div>
            <div class="meta">${esc(e.start)}${loc}</div>
          </div>`;
      }
      html += '</div>';
    }

    if (j.recent_files?.length) {
      const watchInfo = j.watch_status?.exists
        ? `<div style="font-size:11px;color:#5fbf6f;margin-bottom:8px;display:flex;align-items:center;gap:6px;">${icon('eye', 12)}<span>監視中: ${esc(j.watch_status.dir)}</span></div>`
        : '';
      html += `<div class="insights-section"><h2><span class="h2-icon">${icon('folder', 18)}</span> 最近変更されたファイル</h2>` + watchInfo;
      for (const f of j.recent_files) {
        html += `
          <div class="insights-card" style="border-left:3px solid #4a8fef;">
            <div class="title" style="font-family: ui-monospace, monospace; font-size: 12px;">${esc(f.name)}</div>
            <div class="meta">${esc(f.modified)} · <span style="color:#777;">${esc(f.path)}</span></div>
          </div>`;
      }
      html += '</div>';
    }

    if (j.recent_notes?.length) {
      html += `<div class="insights-section"><h2><span class="h2-icon">${icon('edit', 18)}</span> 直近の手動メモ</h2>`;
      for (const n of j.recent_notes) {
        html += `
          <div class="insights-card note">
            <div class="meta">${esc(n.date)}</div>
            <div class="body">${esc(n.content)}</div>
          </div>`;
      }
      html += '</div>';
    }

    if (j.pending_questions?.length) {
      html += `<div class="insights-section"><h2><span class="h2-icon">${icon('search', 18)}</span> 直近1週間で未回答の質問</h2>`;
      for (const q of j.pending_questions) {
        html += `
          <div class="insights-card pending">
            <div class="meta">${esc(q.date)}</div>
            <div class="body">${esc(q.content)}</div>
          </div>`;
      }
      html += '</div>';
    }

    if (!html) html = '<div class="empty">気づきがまだありません</div>';
    content.innerHTML = html;
    insightsLoaded = true;

    // Wire the digest button (lazy because LLM call is slow).
    const digestBtn = document.getElementById('digest-btn');
    if (digestBtn) {
      digestBtn.addEventListener('click', async () => {
        const area = document.getElementById('digest-area');
        area.innerHTML = '<div class="loading">AI が記憶を要約中…（最大2分）</div>';
        try {
          const r = await fetch('/api/insights/digest?days=7');
          const j = await r.json();
          if (j.error) {
            area.innerHTML = `<div class="empty">エラー: ${esc(j.error)}</div>`;
            return;
          }
          const formatted = esc(j.digest).replace(/\\n/g, '<br>').replace(/^## (.+)$/gm, '<h3 style="margin:14px 0 6px;color:#ddd;">$1</h3>').replace(/^- (.+)$/gm, '• $1');
          area.innerHTML = `
            <div class="insights-card" style="border-left:3px solid #5fbf6f;">
              <div class="meta">モデル: ${esc(j.model)} · 対象記録: ${j.covered_records} 件</div>
              <div class="body" style="white-space:pre-wrap;">${formatted}</div>
            </div>
          `;
        } catch (e) {
          area.innerHTML = `<div class="empty">エラー: ${esc(String(e))}</div>`;
        }
      });
    }
  } catch (e) {
    content.innerHTML = `<div class="empty">エラー: ${esc(String(e))}</div>`;
  }
}

// ===== Stats =====
let _latestStats = null;
// Show "あなたの分身が今日 +N 件 育ちました" toast at most once per day
// per app launch. This is the most-recommended addition from the novice
// review: makes opening Bunshin feel like checking a Tamagotchi.
function showGrowthToast(total) {
  if (!total || _growthToastShown) return;
  _growthToastShown = true;
  let prev = null;
  try {
    const today = new Date().toISOString().slice(0, 10);
    const stored = JSON.parse(localStorage.getItem('bunshin.growth') || '{}');
    if (stored.date === today) return;  // already shown today
    prev = stored.last_total;
    localStorage.setItem('bunshin.growth', JSON.stringify({date: today, last_total: total}));
  } catch {}
  const delta = (prev != null) ? (total - prev) : null;
  const txt = (delta != null && delta > 0)
    ? `+${delta.toLocaleString()} 件 記憶しました（合計 ${total.toLocaleString()} 件）`
    : `あなたの分身は ${total.toLocaleString()} 件 の記憶を持っています`;
  const el = document.createElement('div');
  el.className = 'growth-toast';
  el.innerHTML = `<span class="gt-icon">${icon('sparkles', 14)}</span> ${esc(txt)}`;
  document.body.appendChild(el);
  setTimeout(() => el.classList.add('show'), 30);
  setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 400); }, 4500);
}

async function loadStats() {
  try {
    const j = await (await fetch('/api/status')).json();
    showGrowthToast(j.total_records);
    _latestStats = j;
    const sourceCount = j.sources ? Object.keys(j.sources).length : 0;
    const parts = [
      `${(j.total_records || 0).toLocaleString()} records`,
    ];
    if (j.total_entities) parts.push(`${j.total_entities.toLocaleString()} entities`);
    if (sourceCount) parts.push(`${sourceCount} sources`);
    if (j.oldest_ts) {
      const d = new Date(j.oldest_ts * 1000);
      parts.push(`${d.getFullYear()}年から`);
    }
    let html = parts.join(' · ');
    if (j.auto_filtered_count && j.auto_filtered_count > 0) {
      html += ` <span class="hidden-chip" title="シグナルスコア ${j.min_signal_score} 以下を自動非表示中。設定タブで調整可能">${j.auto_filtered_count.toLocaleString()}件自動フィルター中</span>`;
    }
    if (j.hidden_count && j.hidden_count > 0) {
      html += ` <span class="hidden-chip" title="あなたの学習で非表示にした記録">${j.hidden_count.toLocaleString()}件非表示</span>`;
    }
    $('stats').innerHTML = html;
    renderEmptyState(j);
    updateSourceChipCounts(j.sources || {});
  } catch {
    $('stats').textContent = 'error';
    renderEmptyState(null);
  }
}

// Annotate each source chip with its record count so users see the
// breadth of memory at a glance — "[mail-icon] Gmail (1,660)".
function updateSourceChipCounts(sources) {
  document.querySelectorAll('#sources .filter-chip').forEach(chip => {
    const src = chip.dataset.source;
    const label = chip.dataset.label || chip.textContent.trim();
    if (!src) {
      // "全部" chip: just the label, no icon.
      chip.innerHTML = label;
      return;
    }
    const iconName = SOURCE_ICON_NAME[src] || 'file-text';
    const count = sources[src] || 0;
    const countTxt = count ? ` (${count.toLocaleString()})` : '';
    chip.innerHTML = `${icon(iconName, 13)}<span>${label}${countTxt}</span>`;
    chip.classList.toggle('chip-empty', !count);
  });
}

function renderEmptyState(stats) {
  const el = $('search-empty-state');
  if (!el) return;
  const totalRecords = stats && typeof stats === 'object'
    ? (stats.total_records ?? null)
    : stats; // backwards-compat: callers might still pass a number
  // Welcome / onboarding for fresh installs and almost-empty DBs
  if (totalRecords !== null && totalRecords < 200) {
    const count = totalRecords ? totalRecords.toLocaleString() : '0';
    el.outerHTML = `
      <div class="welcome" id="search-empty-state">
        <div class="welcome-hero">
          <div class="welcome-icon-big">${icon('sparkles', 36)}</div>
          <h2>今日から、あなたの記憶が育ち始めます</h2>
          <p class="welcome-tagline">
            ${totalRecords > 0
              ? `すでに <b>${count}</b> 件の記憶が集まっています。あと少しで Bunshin はあなたの "もう一人の自分" になります。`
              : `Bunshin は、あなたの過去の記憶を集めて、いつでも思い出させてくれる AI です。<br>最初の一歩から始めましょう。`}
          </p>
        </div>

        <div class="welcome-steps">
          <div class="welcome-step welcome-step-action">
            <div class="welcome-step-num">1</div>
            <div class="welcome-step-body">
              <h3>5 分で全部つなぐ</h3>
              <p>ウィザードに沿って Gmail・写真・メモを取り込み。最初の数千件があっという間に揃います。</p>
              <button class="welcome-btn welcome-btn-primary" id="welcome-open-wizard">
                ${icon('sparkles', 14)}<span>ウィザードを開く</span>
              </button>
            </div>
          </div>

          <div class="welcome-step">
            <div class="welcome-step-num">2</div>
            <div class="welcome-step-body">
              <h3>チャットで最初の記憶を保存</h3>
              <p>「<code>覚えといて: 今日の出来事</code>」とチャットに書くだけ。AI に聞かずに記憶だけが保存されます。</p>
              <button class="welcome-btn" id="welcome-open-chat">
                ${icon('message', 14)}<span>チャットを開く</span>
              </button>
            </div>
          </div>

          <div class="welcome-step">
            <div class="welcome-step-num">3</div>
            <div class="welcome-step-body">
              <h3>自動取り込みを ON</h3>
              <p>毎時間バックグラウンドで Gmail・ファイルを自動取り込み。あとは Bunshin に任せて OK。</p>
              <button class="welcome-btn" id="welcome-open-settings">
                ${icon('settings', 14)}<span>設定タブを開く</span>
              </button>
            </div>
          </div>
        </div>

        <div class="welcome-tips">
          <p>${icon('lightbulb', 13)}<span><b>あなたのデータはこの Mac から出ません。</b>AI モデルもローカルで動きます。</span></p>
          <p>${icon('lightbulb', 13)}<span>古い Gmail も遡って取り込みたいときは <code>bunshin import-gmail --full</code></span></p>
          <p>${icon('lightbulb', 13)}<span>詳しい説明は <a href="https://github.com/Marine923/bunshin-ai/blob/main/docs/SETUP.md" target="_blank">セットアップガイド</a>。</span></p>
        </div>
      </div>`;
    // Wire the welcome action buttons.
    setTimeout(() => {
      const w = $('welcome-open-wizard');
      const c = $('welcome-open-chat');
      const s = $('welcome-open-settings');
      if (w) w.addEventListener('click', () => openOnboarding(true));
      if (c) c.addEventListener('click', () => {
        const tab = document.querySelector('.sidebar-tab[data-pane="chat"]');
        if (tab) tab.click();
      });
      if (s) s.addEventListener('click', () => {
        const tab = document.querySelector('.sidebar-tab[data-pane="settings"]');
        if (tab) tab.click();
      });
    }, 30);
  } else {
    const year = (stats && stats.oldest_ts) ? new Date(stats.oldest_ts * 1000).getFullYear() : null;
    el.outerHTML = `
      <div class="empty" id="search-empty-state">
        ${year ? `${year}年から今日まで、` : ''}${(totalRecords || 0).toLocaleString()}件の記憶があります。<br>
        過去の自分に聞いてみてください。
      </div>`;
  }
}

loadStats();

// ===== Flashback (records the user wrote on this same date in the past) =====
// SOURCE_LABEL_JA is declared near SOURCE_ICON_NAME above — same dict reused.

async function loadFlashback() {
  const section = $('flashback-section');
  const grid = $('flashback-grid');
  if (!section || !grid) return;
  try {
    const j = await (await fetch('/api/flashback')).json();
    const windows = j.windows || [];
    // Only render windows that actually have content. If nothing across
    // all three, leave the section hidden — we don't want to advertise
    // emptiness on the user's first impression.
    const populated = windows.filter(w => w.items && w.items.length);
    if (!populated.length) {
      section.style.display = 'none';
      section.dataset.populated = '0';
      return;
    }
    section.dataset.populated = '1';
    grid.innerHTML = windows.map(w => {
      const it = (w.items && w.items[0]) || null;
      if (!it) {
        // Empty windows used to read as a flat "この日は静かでした" — a
        // bit of a downer when 3 of 3 cards say it. Replace with a soft
        // prompt that invites the user to seed memory.
        const PROMPTS = [
          'この頃、何してたっけ？',
          '記憶がない日。後で思い出したら ⌘N でメモ',
          '静かな日。あなたが Bunshin に来る前かも',
        ];
        const prompt = PROMPTS[Math.floor(w.date.charCodeAt(w.date.length - 1) % PROMPTS.length)];
        return `
          <div class="flashback-card" data-empty="1">
            <div class="fb-when">${esc(w.label_ja)}</div>
            <div class="fb-date">${esc(w.date)} (${esc(w.weekday)})</div>
            <div class="fb-empty">${esc(prompt)}</div>
          </div>`;
      }
      const iconHtml = icon(SOURCE_ICON_NAME[it.source] || 'file-text', 13);
      const label = SOURCE_LABEL_JA[it.source] || it.source;
      const more = (w.total_count || 1) - 1;
      const sender = it.sender || '';
      const domain = it.domain || '';
      return `
        <div class="flashback-card" data-date="${esc(w.date)}" data-id="${esc(it.id)}" data-sender="${esc(sender)}" data-domain="${esc(domain)}">
          <button class="card-hide-btn" title="この記録は要らない" aria-label="非表示">${icon('trash', 14)}</button>
          <div class="fb-when">${esc(w.label_ja)}</div>
          <div class="fb-date">${esc(w.date)} (${esc(w.weekday)})</div>
          <div class="fb-preview">${esc(it.content)}</div>
          <div class="fb-source">${iconHtml} ${esc(label)}${more > 0 ? ` · 他 ${more} 件` : ''}</div>
        </div>`;
    }).join('');
    // Card body → drill-down by date; trash button → mark modal.
    grid.querySelectorAll('.flashback-card[data-date]').forEach(el => {
      el.addEventListener('click', (ev) => {
        if (ev.target.classList.contains('card-hide-btn')) return; // handled below
        const date = el.dataset.date;
        if (!date) return;
        const start = new Date(date + 'T00:00:00').getTime() / 1000;
        const end = new Date(date + 'T23:59:59').getTime() / 1000;
        runDateSearch(Math.floor(start), Math.floor(end), date);
      });
    });
    grid.querySelectorAll('.card-hide-btn').forEach(btn => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const card = btn.closest('.flashback-card');
        if (!card) return;
        openMarkModal(card.dataset.id, card.dataset.sender, card.dataset.domain);
      });
    });
    section.style.display = '';
  } catch (e) {
    section.style.display = 'none';
  }
}

// Run a date-bounded search and scroll the results into view. Defined
// here as a thin wrapper so flashback cards can trigger the existing
// search machinery without knowing its internals.
function runDateSearch(fromTs, toTs, dateStr) {
  const resultsEl = $('results');
  if (!resultsEl) return;
  const params = new URLSearchParams();
  params.set('from', String(fromTs));
  params.set('to', String(toTs));
  params.set('limit', '50');
  resultsEl.innerHTML = '<div class="loading">読み込み中…</div>';
  fetch('/api/records?' + params.toString())
    .then(r => r.json())
    .then(j => {
      if (!j.results || !j.results.length) {
        resultsEl.innerHTML = `<div class="empty">${esc(dateStr)} の記録は見つかりませんでした</div>`;
        return;
      }
      resultsEl.innerHTML = `
        <div class="flashback-results-header">
          <span>${esc(dateStr)} の記録 (${j.results.length}件)</span>
        </div>
        ` + j.results.map(r => {
          const iconHtml = icon(SOURCE_ICON_NAME[r.source] || 'file-text', 13);
          const label = SOURCE_LABEL_JA[r.source] || r.source;
          const time = new Date((r.timestamp||0) * 1000).toLocaleTimeString('ja-JP', {hour:'2-digit', minute:'2-digit'});
          const content = (r.content || '').slice(0, 500);
          const sender = r.sender || '';
          const domain = sender.includes('@') ? sender.split('@')[1] : '';
          return `
            <div class="flashback-result" data-id="${esc(r.id)}" data-sender="${esc(sender)}" data-domain="${esc(domain)}">
              <button class="card-hide-btn" title="この記録は要らない" aria-label="非表示">${icon('trash', 14)}</button>
              <div class="flashback-result-meta">${iconHtml} ${esc(label)} · ${esc(time)}</div>
              <div class="flashback-result-content">${esc(content)}</div>
            </div>`;
        }).join('');
      resultsEl.querySelectorAll('.card-hide-btn').forEach(btn => {
        btn.addEventListener('click', (ev) => {
          ev.stopPropagation();
          const row = btn.closest('.flashback-result');
          if (!row) return;
          openMarkModal(row.dataset.id, row.dataset.sender, row.dataset.domain);
        });
      });
      resultsEl.scrollIntoView({behavior: 'smooth', block: 'start'});
    })
    .catch(() => {
      resultsEl.innerHTML = '<div class="empty">エラーが発生しました</div>';
    });
}

loadFlashback();

// ===== Onboarding Wizard =====
// Shown only on first launch with an essentially-empty DB. The user can
// dismiss it from any step; we set localStorage so it never reappears
// on this Mac, even if the DB gets emptied later.
const ONBOARDING_STEPS = [
  {
    label: '1 / 5',
    title: () => `${icon('sparkles', 22)} ようこそ、分身（Bunshin）へ`,
    body: () => `
      <p class="step-body">
        分身は、あなたの過去の記憶を集めて、いつでも思い出させてくれる AI です。
        Claude の会話、Gmail、写真、メモ — ぜんぶを横断して検索できます。
      </p>
      <div class="step-warn">
        <span class="warn-icon">${icon('lock', 16)}</span>
        <span>
          <b>あなたのデータは、この Mac から一歩も出ません。</b><br>
          AI モデルもローカル（Ollama）で動きます。外部サービスへの送信はありません。
        </span>
      </div>
    `,
  },
  {
    label: '2 / 5',
    title: () => `${icon('mail', 22)} Gmail を読みますか？`,
    body: () => `
      <p class="step-body">
        過去のメールから「あの店なんだっけ」「あの予約いつだっけ」を思い出せるようになります。
        まず接続設定 → その後 import コマンドで取り込み。
      </p>
      <div class="step-cmd">
        <code>bunshin setup-gmail --email YOUR@gmail.com</code>
        <button class="copy-btn" data-copy="bunshin setup-gmail --email YOUR@gmail.com">コピー</button>
      </div>
      <div class="step-cmd">
        <code>bunshin import-gmail --full</code>
        <button class="copy-btn" data-copy="bunshin import-gmail --full">コピー</button>
      </div>
      <div class="step-warn">
        <span class="warn-icon">${icon('alert-triangle', 16)}</span>
        <span>
          App Password が必要です（通常パスワードでは入りません）。
          Google アカウント → セキュリティ → 2段階認証 → App Password。
        </span>
      </div>
    `,
  },
  {
    label: '3 / 5',
    title: () => `${icon('image', 22)} 写真ライブラリを読みますか？`,
    body: () => `
      <p class="step-body">
        Photos.app から写真の撮影日・場所・OCR テキストを取り込みます。
        「先月の旅行の写真」が日付・場所・内容で探せるように。
      </p>
      <div class="step-cmd">
        <code>bunshin import-photos-app</code>
        <button class="copy-btn" data-copy="bunshin import-photos-app">コピー</button>
      </div>
      <div class="step-warn">
        <span class="warn-icon">${icon('alert-triangle', 16)}</span>
        <span>
          次に macOS が「写真へのアクセス許可」を求めます。
          「<b>すべての写真</b>」を選ぶと全期間取り込めます。
        </span>
      </div>
    `,
  },
  {
    label: '4 / 5',
    title: () => `${icon('notebook', 22)} Apple メモ・iMessage を読みますか？`,
    body: () => `
      <p class="step-body">
        Notes.app のメモ、iMessage の履歴、ブラウザの閲覧履歴を取り込めます。
        必要なものだけターミナルで実行してください。
      </p>
      <div class="step-cmd">
        <code>bunshin import-notes</code>
        <button class="copy-btn" data-copy="bunshin import-notes">コピー</button>
      </div>
      <div class="step-cmd">
        <code>bunshin import-imessage</code>
        <button class="copy-btn" data-copy="bunshin import-imessage">コピー</button>
      </div>
      <div class="step-cmd">
        <code>bunshin import-browser --full</code>
        <button class="copy-btn" data-copy="bunshin import-browser --full">コピー</button>
      </div>
      <div class="step-warn">
        <span class="warn-icon">${icon('alert-triangle', 16)}</span>
        <span>
          iMessage / Notes は「フルディスクアクセス」が必要です。
          macOS が設定画面を開いたら、リストに <b>Terminal</b>（または iTerm）を追加してください。
          データはこの Mac 内のみで処理されます。
        </span>
      </div>
    `,
  },
  {
    label: '5 / 5',
    title: () => `${icon('sparkles', 22)} 準備できました`,
    body: (stats) => {
      const total = (stats && stats.total_records) || 0;
      const ent = (stats && stats.total_entities) || 0;
      const src = (stats && stats.sources) ? Object.keys(stats.sources).length : 0;
      const oldestYear = (stats && stats.oldest_ts) ? new Date(stats.oldest_ts * 1000).getFullYear() : null;
      return `
        <p class="step-body">
          ${total > 0
            ? `${total.toLocaleString()} 件の記憶があなたを待っています。`
            : '取り込みが終わると、ここに件数が表示されます。'}
        </p>
        <div class="step-stats">
          <div class="step-stat"><span class="num">${total.toLocaleString()}</span><span class="label">記録</span></div>
          <div class="step-stat"><span class="num">${ent.toLocaleString()}</span><span class="label">エンティティ</span></div>
          <div class="step-stat"><span class="num">${src}</span><span class="label">ソース</span></div>
          ${oldestYear ? `<div class="step-stat"><span class="num">${oldestYear}</span><span class="label">最古</span></div>` : ''}
        </div>
        <ul class="step-tips">
          <li>${icon('lightbulb', 13)}<span>「<b>覚えといて: ◯◯</b>」とチャットで書くと、AI に聞かずに記憶に追加されます。</span></li>
          <li>${icon('lightbulb', 13)}<span>設定タブでフィルター強度や接続を調整できます。</span></li>
        </ul>
      `;
    },
  },
];

let _onboardingIdx = 0;

function shouldShowOnboarding() {
  if (localStorage.getItem('bunshin.onboarded') === '1') return false;
  // Only auto-show if the DB looks essentially empty. Power users with
  // existing data shouldn't be greeted by an onboarding screen.
  if (_latestStats && _latestStats.total_records > 200) {
    localStorage.setItem('bunshin.onboarded', '1');
    return false;
  }
  return true;
}

function openOnboarding(force) {
  _onboardingIdx = 0;
  if (force || shouldShowOnboarding()) {
    $('onboarding-overlay').style.display = 'flex';
    renderOnboarding();
  }
}

function closeOnboarding() {
  localStorage.setItem('bunshin.onboarded', '1');
  $('onboarding-overlay').style.display = 'none';
  // After the setup wizard, run a short visual tour the very first time
  // so the user sees what each tab actually does.
  try {
    if (localStorage.getItem('bunshin.tour') !== '1') {
      setTimeout(() => { if (typeof startTour === 'function') startTour(); }, 350);
    }
  } catch {}
}

// ===== In-app tour (3 steps, first launch only) =====
const TOUR_STEPS = [
  {
    pane: 'search',
    iconKey: 'search',
    title: '記憶を検索する',
    body: '過去のメール・写真・メモ・Claude 会話を、ぜんぶ横断して検索できます。日本語で「あの店なんだっけ」のように聞いてみてください。',
  },
  {
    pane: 'chat',
    iconKey: 'message',
    title: 'AI に聞いてみる',
    body: 'チャットタブで、ローカル AI が <b>あなたの過去記憶を踏まえて</b> 答えます。データは Mac の中だけで処理されます。',
  },
  {
    pane: 'graph',
    iconKey: 'link',
    title: '人と場所の繋がり',
    body: '関係性タブで、あなたの記憶に出てきた人・プロジェクト・場所が、どう繋がっているかを地図のように見られます。',
  },
];

function _tourSwitchTab(pane) {
  const tab = document.querySelector('.sidebar-tab[data-pane="' + pane + '"]');
  if (tab) tab.click();
}

function startTour() {
  let idx = 0;

  function render() {
    if (idx >= TOUR_STEPS.length) { endTour(); return; }
    const s = TOUR_STEPS[idx];
    _tourSwitchTab(s.pane);

    let bd = document.getElementById('tour-backdrop');
    if (!bd) {
      bd = document.createElement('div');
      bd.id = 'tour-backdrop';
      bd.className = 'tour-backdrop';
      document.body.appendChild(bd);
    }
    const dots = TOUR_STEPS.map((_, k) => {
      const cls = k === idx ? 'active' : (k < idx ? 'done' : '');
      return `<span class="tour-dot ${cls}"></span>`;
    }).join('');
    const isLast = idx === TOUR_STEPS.length - 1;
    bd.innerHTML = `
      <div class="tour-card">
        <div class="tour-icon">${icon(s.iconKey, 24)}</div>
        <div class="tour-dots">${dots}</div>
        <h3>${s.title}</h3>
        <p>${s.body}</p>
        <div class="tour-actions">
          <button class="tour-skip" type="button" id="tour-skip-btn">スキップ</button>
          <button class="tour-next" type="button" id="tour-next-btn">${isLast ? '触ってみる' : '次へ →'}</button>
        </div>
      </div>
    `;
    bd.style.display = 'flex';
    const next = document.getElementById('tour-next-btn');
    const skip = document.getElementById('tour-skip-btn');
    if (next) next.addEventListener('click', () => { idx++; render(); });
    if (skip) skip.addEventListener('click', endTour);
  }

  function endTour() {
    const bd = document.getElementById('tour-backdrop');
    if (bd) bd.remove();
    try { localStorage.setItem('bunshin.tour', '1'); } catch {}
  }

  // Expose for the Esc key handler if we ever wire one.
  window._endTour = endTour;
  render();
}

function renderOnboarding() {
  const step = ONBOARDING_STEPS[_onboardingIdx];
  if (!step) { closeOnboarding(); return; }

  const dotsEl = $('onboarding-dots');
  dotsEl.innerHTML = ONBOARDING_STEPS.map((_, i) => {
    const cls = i === _onboardingIdx ? 'active' : (i < _onboardingIdx ? 'done' : '');
    return `<div class="onboarding-dot ${cls}"></div>`;
  }).join('');

  const contentEl = $('onboarding-content');
  contentEl.innerHTML = `
    <div class="step-label">${esc(step.label)}</div>
    <h2>${typeof step.title === 'function' ? step.title() : step.title}</h2>
    ${step.body(_latestStats)}
  `;

  // Wire copy buttons
  contentEl.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.dataset.copy;
      navigator.clipboard.writeText(text).then(() => {
        btn.classList.add('copied');
        btn.textContent = '✓ コピー済み';
        setTimeout(() => {
          btn.classList.remove('copied');
          btn.textContent = 'コピー';
        }, 2000);
      });
    });
  });

  $('onboarding-back').style.display = _onboardingIdx === 0 ? 'none' : '';
  $('onboarding-next').textContent =
    _onboardingIdx === ONBOARDING_STEPS.length - 1 ? '使ってみる →' : '次へ →';
}

document.addEventListener('DOMContentLoaded', () => {
  const skipBtn = $('onboarding-skip');
  const backBtn = $('onboarding-back');
  const nextBtn = $('onboarding-next');
  if (skipBtn) skipBtn.addEventListener('click', closeOnboarding);
  if (backBtn) backBtn.addEventListener('click', () => {
    if (_onboardingIdx > 0) { _onboardingIdx--; renderOnboarding(); }
  });
  if (nextBtn) nextBtn.addEventListener('click', () => {
    if (_onboardingIdx < ONBOARDING_STEPS.length - 1) {
      _onboardingIdx++;
      renderOnboarding();
    } else {
      closeOnboarding();
    }
  });
});

// Auto-open the wizard once the very first loadStats() resolves and we
// can confirm the DB really is empty. Subsequent reloads do nothing
// because localStorage now flags the user as onboarded.
(async function tryOpenOnboarding() {
  // Give loadStats time to finish (it runs at module load).
  for (let i = 0; i < 30 && _latestStats === null; i++) {
    await new Promise(r => setTimeout(r, 100));
  }
  if (shouldShowOnboarding()) openOnboarding(false);
})();

// ===== Mark / Learning UI =====
let _markCtx = {recordId: null, sender: '', domain: ''};
let _undoTimer = null;
let _undoResult = null;

function openMarkModal(recordId, sender, domain) {
  _markCtx = {recordId, sender: sender || '', domain: domain || ''};
  const modal = $('mark-modal');
  const senderHint = $('mark-scope-sender-hint');
  const domainHint = $('mark-scope-domain-hint');
  const senderRow = modal.querySelector('[data-scope="sender"]');
  const domainRow = modal.querySelector('[data-scope="domain"]');

  if (sender) {
    senderHint.textContent = sender;
    senderRow.classList.remove('disabled');
  } else {
    senderHint.textContent = '送信者情報なし（メール以外の記録）';
    senderRow.classList.add('disabled');
  }
  if (domain) {
    domainHint.textContent = '@' + domain + ' から来る全部';
    domainRow.classList.remove('disabled');
  } else {
    domainHint.textContent = 'ドメイン情報なし';
    domainRow.classList.add('disabled');
  }
  // Default selection: sender > record (and never default to a disabled option)
  modal.querySelectorAll('input[name="mark-scope"]').forEach(r => r.checked = false);
  if (sender) {
    modal.querySelector('input[value="sender"]').checked = true;
  } else {
    modal.querySelector('input[value="record"]').checked = true;
  }
  modal.style.display = 'flex';
}

function closeMarkModal() { $('mark-modal').style.display = 'none'; }

document.addEventListener('DOMContentLoaded', () => {
  const cancelBtn = $('mark-cancel');
  const applyBtn = $('mark-apply');
  const backdrop = $('mark-modal');
  if (cancelBtn) cancelBtn.addEventListener('click', closeMarkModal);
  if (backdrop) backdrop.addEventListener('click', (ev) => {
    if (ev.target === backdrop) closeMarkModal();
  });
  if (applyBtn) applyBtn.addEventListener('click', applyMark);
});

async function applyMark() {
  const checked = document.querySelector('input[name="mark-scope"]:checked');
  if (!checked) return;
  const scope = checked.value;
  const rid = _markCtx.recordId;
  if (!rid) return;
  closeMarkModal();
  try {
    const r = await fetch('/api/mark', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({record_id: rid, action: 'hide', scope}),
    });
    const j = await r.json();
    _undoResult = {...j, recordId: rid, scope};
    showUndoToast(_undoResult);
    if (typeof loadFlashback === 'function') loadFlashback();
    loadStats();
  } catch (e) {
    console.error(e);
  }
}

function showUndoToast(result) {
  const toast = $('undo-toast');
  const msg = $('undo-msg');
  const countdown = $('undo-countdown');
  const btn = $('undo-btn');
  if (!toast || !msg || !btn) return;

  let label;
  if (result.scope === 'sender' && result.sender) {
    label = `${result.sender} を非表示にしました`;
  } else if (result.scope === 'domain' && result.domain) {
    label = `@${result.domain} を非表示にしました`;
  } else {
    label = 'この記録を非表示にしました';
  }
  msg.textContent = `${label}（${result.applied}件適用）`;
  toast.style.display = 'flex';

  let remain = 5;
  countdown.textContent = remain;
  if (_undoTimer) clearInterval(_undoTimer);
  _undoTimer = setInterval(() => {
    remain--;
    countdown.textContent = remain;
    if (remain <= 0) {
      clearInterval(_undoTimer);
      toast.style.display = 'none';
    }
  }, 1000);

  btn.onclick = async () => {
    clearInterval(_undoTimer);
    toast.style.display = 'none';
    try {
      const body = result.rule_id
        ? {rule_id: result.rule_id}
        : {record_id: result.recordId};
      await fetch('/api/mark/undo', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      if (typeof loadFlashback === 'function') loadFlashback();
      loadStats();
    } catch (e) {
      console.error(e);
    }
  };
}

// ===== Search =====
const q = $('q'), results = $('results'), sortSel = $('sort'), periodsEl = $('periods');
const sourcesEl = $('sources');
let searchTimer = null;
let currentPeriod = 'all';
let currentSource = '';

function periodToSec(p) {
  const day = 86400;
  return { day, week: day*7, month: day*30, year: day*365 }[p] || null;
}

// Current query, shared with renderResult / renderSessionMsg so they can
// highlight matched terms in the displayed content.
let _currentQuery = '';
let _lastResults = [];
let _growthToastShown = false;

function copyResultsBundle() {
  // Build a self-contained Markdown bundle the user can paste into
  // Claude / ChatGPT. Includes the query, every result's source+date+
  // snippet, and a footer for context. Power users do this 10x/day.
  if (!_lastResults || !_lastResults.length) return;
  const lines = [];
  lines.push(`# 過去記憶の検索結果`);
  lines.push(``);
  lines.push(`**クエリ**: ${_currentQuery}`);
  lines.push(`**取得件数**: ${_lastResults.length} 件`);
  lines.push(`**取得日時**: ${new Date().toLocaleString('ja-JP')}`);
  lines.push(``);
  lines.push(`---`);
  lines.push(``);
  for (let i = 0; i < _lastResults.length; i++) {
    const r = _lastResults[i];
    const ts = r.timestamp ? new Date(r.timestamp * 1000).toLocaleString('ja-JP') : '?';
    const sourceLabel = (SOURCE_LABEL_JA[r.source] || r.source);
    const fileTail = (r.source === 'file' || r.source === 'photo' || r.source === 'photos_app')
      ? ` · ${(r.source_id || '').split('/').pop()}`
      : '';
    lines.push(`## ${i + 1}. [${sourceLabel}${fileTail}] ${ts}`);
    lines.push(``);
    lines.push(r.content || '');
    lines.push(``);
  }
  lines.push(`---`);
  lines.push(`*このコピーは Bunshin (https://github.com/Marine923/bunshin-ai) の検索結果です。*`);
  const text = lines.join('\\n');
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById('copy-bundle-btn');
    if (btn) {
      btn.classList.add('copied');
      const orig = btn.innerHTML;
      btn.innerHTML = '✓ コピー済み — Claude/ChatGPT に貼れます';
      setTimeout(() => { btn.innerHTML = orig; btn.classList.remove('copied'); }, 2500);
    }
  }).catch(err => {
    alert('コピーに失敗しました: ' + err);
  });
}
function highlight(text, query) {
  // No regex — Python's triple-quoted string mangles the backslash
  // escapes needed for character classes, so we walk the text manually.
  const escaped = esc(text);
  if (!query) return escaped;
  const terms = query.trim().split(/[ 　\t]+/).filter(t => t.length >= 2);
  if (!terms.length) return escaped;
  let result = escaped;
  for (const term of terms) {
    const needle = term.toLowerCase();
    let out = '';
    let i = 0;
    while (i < result.length) {
      const slice = result.substr(i, needle.length);
      if (slice.toLowerCase() === needle) {
        out += '<mark>' + slice + '</mark>';
        i += needle.length;
      } else {
        out += result[i];
        i++;
      }
    }
    result = out;
  }
  return result;
}

// User-configured search preferences (from /api/settings). Cached here so
// each doSearch() doesn't re-fetch settings.
let _searchPrefs = { search_rerank: true, search_expand: false };
(async () => {
  try {
    const r = await fetch('/api/settings');
    const j = await r.json();
    if (j.settings) {
      if ('search_rerank' in j.settings) _searchPrefs.search_rerank = !!j.settings.search_rerank;
      if ('search_expand' in j.settings) _searchPrefs.search_expand = !!j.settings.search_expand;
    }
  } catch {}
})();

async function doSearch(query) {
  const flashbackSec = document.getElementById('flashback-section');
  if (!query.trim()) {
    results.innerHTML = '<div class="empty">検索クエリを入力してください</div>';
    // Empty query → restore flashback (if it had content originally).
    if (flashbackSec && flashbackSec.dataset.populated === '1') flashbackSec.style.display = '';
    return;
  }
  // Active search → fold the flashback out of the way so results aren't
  // buried below it.
  if (flashbackSec) flashbackSec.style.display = 'none';
  _currentQuery = query;
  results.innerHTML = '<div class="loading">検索中…</div>';
  try {
    const params = new URLSearchParams({ q: query, limit: 20, sort: sortSel.value });
    const sec = periodToSec(currentPeriod);
    if (sec) params.set('from', Math.floor(Date.now()/1000) - sec);
    if (currentSource) params.set('sources', currentSource);
    if (_searchPrefs.search_rerank === false) params.set('rerank', 'false');
    if (_searchPrefs.search_expand === true) params.set('expand', 'true');
    const j = await (await fetch(`/api/search?${params}`)).json();
    if (!j.results?.length) { results.innerHTML = '<div class="empty">該当なし</div>'; return; }
    _lastResults = j.results;
    const toolbar = `
      <div class="results-toolbar">
        <button class="copy-bundle-btn" id="copy-bundle-btn" type="button" title="検索結果を Markdown でクリップボードへ。Claude/ChatGPT にそのまま貼れます">
          ${icon('copy', 13)} まとめて Markdown でコピー
        </button>
      </div>`;
    results.innerHTML = toolbar + j.results.map((r, i) => renderResult(r, i)).join('');
    const cb = document.getElementById('copy-bundle-btn');
    if (cb) cb.addEventListener('click', copyResultsBundle);
    document.querySelectorAll('.result').forEach((el, i) => {
      el.addEventListener('click', (ev) => {
        // Don't open session expand when clicking the "📚 N more" badge.
        if (ev.target.classList.contains('more-chunks')) {
          ev.stopPropagation();
          toggleSiblings(el, ev.target);
          return;
        }
        toggleSession(el, j.results[i]);
      });
    });
  } catch (e) {
    results.innerHTML = `<div class="empty">エラー: ${esc(String(e))}</div>`;
  }
}

// Wrap the [assistant] / [user] / [tool_use: ...] markers that come
// out of Claude transcripts in a quiet pill so the body text reads
// without them dominating.
function styleMarkers(htmlSafe) {
  return htmlSafe.replace(
    /\[(assistant|user|tool_use|tool_result|queue-operation|browser|chrome|safari|arc|photo|notes|gmail|calendar)([^\]]{0,40})\]/g,
    (_m, kind, rest) => `<span class="marker">${kind}${rest}</span>`
  );
}

// Turn markdown-style file references like
// `[sky_mission_確認シート.pdf](sky_mission_確認シート.pdf)`
// into clickable chips that re-search by filename so the actual file
// record (where a real preview lives) surfaces.
function linkifyFileMentions(htmlSafe) {
  return htmlSafe.replace(
    /\[([^\[\]]{1,100}\.(?:pdf|md|markdown|txt|docx|jpg|jpeg|png|heic|heif|tif|tiff|webp))\]\([^)]{1,300}\)/gi,
    (_m, fname) => `<span class="file-mention" data-filename="${fname}">${fname}</span>`
  );
}

// Collapse runs of 3+ blank lines down to a single break so transcripts
// don't waste vertical space. Built without a regex on purpose — Python's
// triple-quoted string would interpret the escape sequences.
function compactBlankLines(text) {
  if (!text) return '';
  const NL = String.fromCharCode(10);
  const lines = text.split(NL);
  const out = [];
  let blanks = 0;
  for (const line of lines) {
    if (line.trim() === '') {
      blanks++;
      if (blanks <= 2) out.push(line);
    } else {
      blanks = 0;
      out.push(line);
    }
  }
  return out.join(NL);
}

const SOURCE_BADGE_META = {
  claude:     { cls: 'claude',     label: 'Claude' },
  gmail:      { cls: 'gmail',      label: 'Gmail' },
  file:       { cls: 'file',       label: 'ファイル' },
  notes:      { cls: 'notes',      label: 'メモ帳' },
  imessage:   { cls: 'imessage',   label: 'iMessage' },
  photo:      { cls: 'photo',      label: '写真' },
  photos_app: { cls: 'photos_app', label: '写真' },
  browser:    { cls: 'browser',    label: 'ブラウザ' },
  calendar:   { cls: 'calendar',   label: 'カレンダー' },
  line:       { cls: 'line',       label: 'LINE' },
  manual:     { cls: 'manual',     label: 'メモ' },
};

const IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.gif', '.heic', '.heif', '.tif', '.tiff', '.webp'];
const PDF_EXTS = ['.pdf'];

function fileExt(path) {
  if (!path) return '';
  const m = path.match(/\.[a-zA-Z0-9]+$/);
  return m ? m[0].toLowerCase() : '';
}

function renderResultMedia(r) {
  const path = r.source_id || '';
  if (r.source !== 'photo' && r.source !== 'file') return '';
  const ext = fileExt(path);
  const url = '/api/file?source_id=' + encodeURIComponent(path);
  if (IMAGE_EXTS.includes(ext)) {
    return `
      <div class="result-media">
        <div class="thumb" data-preview="image" data-url="${esc(url)}">
          <img src="${esc(url)}" alt="${esc(path.split('/').pop())}" loading="lazy">
        </div>
      </div>`;
  }
  if (PDF_EXTS.includes(ext)) {
    return `
      <div class="result-media">
        <div class="thumb" data-preview="pdf" data-url="${esc(url)}" style="display:flex;align-items:center;justify-content:center;gap:4px;color:var(--text-3);font-size:11px;">${icon('file-text', 14)} PDF</div>
      </div>`;
  }
  return '';
}

// When a record is much longer than the screen real-estate (~400
// chars), excerpt the chunk around the first query-token match so the
// user sees the relevant passage instead of the file header.
function makeSnippet(content, query, maxLen) {
  if (!content) return '';
  const limit = maxLen || 480;
  if (content.length <= limit) return content;
  const trimmed = (query || '').trim();
  if (!trimmed) return content.slice(0, limit) + '…';
  const tokens = trimmed.split(/[ 　\t]+/).filter(t => t.length >= 2);
  if (!tokens.length) return content.slice(0, limit) + '…';
  const lc = content.toLowerCase();
  let bestIdx = -1;
  for (const t of tokens) {
    const i = lc.indexOf(t.toLowerCase());
    if (i >= 0 && (bestIdx < 0 || i < bestIdx)) bestIdx = i;
  }
  if (bestIdx < 0) return content.slice(0, limit) + '…';
  const half = Math.floor(limit / 2);
  let start = Math.max(0, bestIdx - half);
  let end = Math.min(content.length, start + limit);
  start = Math.max(0, end - limit);
  const prefix = start > 0 ? '… ' : '';
  const suffix = end < content.length ? ' …' : '';
  return prefix + content.slice(start, end) + suffix;
}

// Convert raw distance / rerank score to a 0–100 "relevance" reading
// that's easier to interpret at a glance than e5-large distance values.
function relevanceLabel(r) {
  const sc = r.score_components || {};
  // Rerank score is a normalized 0–1 (jina v2) — use it directly.
  if (typeof sc.rerank === 'number') {
    const pct = Math.max(0, Math.min(100, Math.round(sc.rerank * 100)));
    return {
      pct,
      kind: 'rerank',
      icon: pct >= 80 ? icon('star', 12) : pct >= 60 ? icon('sparkles', 12) : '',
    };
  }
  // Otherwise approximate from the e5-large distance.
  // Empirically: 13-15 = great, 16-18 = ok, 20+ = weak.
  const d = r.distance;
  if (d == null || d >= 999) return { pct: null, kind: 'none', icon: '' };
  const pct = Math.max(0, Math.min(100, Math.round(100 - (d - 10) * 6)));
  return { pct, kind: 'vector', icon: pct >= 80 ? icon('star', 12) : pct >= 60 ? icon('sparkles', 12) : '' };
}

function whyHitChips(r) {
  // Render score-component badges so the user understands WHY this
  // record matched: vector similarity, keyword match, or signal-score
  // boost. Power users find this trustworthy + debuggable.
  const sc = r.score_components || {};
  const chips = [];
  if (sc.rerank != null) {
    chips.push(`<span class="why-chip why-rerank" title="AI 再ソートで上位">AI ${Math.round(sc.rerank * 100)}</span>`);
  } else if (sc.vector != null || r.distance != null) {
    const dist = r.distance ?? 1;
    const sim = Math.max(0, Math.round((1 - dist) * 100));
    chips.push(`<span class="why-chip why-vector" title="意味の近さ (embedding)">意味 ${sim}</span>`);
  }
  if (sc.bm25 != null && sc.bm25 > 0) {
    chips.push(`<span class="why-chip why-keyword" title="キーワード一致 (BM25)">キーワード ✓</span>`);
  }
  if (sc.keyword_fallback) {
    chips.push(`<span class="why-chip why-kwfb" title="検索エンジンが応答しないため、キーワード fallback で取得">⚠ 簡易検索</span>`);
  }
  if (r.signal_score != null && r.signal_score >= 60) {
    chips.push(`<span class="why-chip why-signal" title="重要度の高い記録">重要</span>`);
  }
  return chips.length ? `<span class="why-chips">${chips.join('')}</span>` : '';
}

function renderResult(r, idx) {
  const ts = r.timestamp ? new Date(r.timestamp * 1000).toLocaleString('ja-JP') : 'n/a';
  const role = (r.metadata && r.metadata.role) ? r.metadata.role : '';
  const badge = SOURCE_BADGE_META[r.source] || { cls: 'manual', label: r.source };
  const srcLabel = (r.source === 'file' || r.source === 'photo' || r.source === 'photos_app')
    ? `${badge.label} · ${(r.source_id || '').split('/').pop()}`
    : (role ? `${badge.label} · ${role}` : badge.label);
  const more = (r.total_in_source && r.total_in_source > 1)
    ? `<span class="more-chunks" data-more-sid="${esc(r.source_id || '')}" data-more-idx="${idx}" title="クリックで展開">${icon('layers', 12)} <span>同じ会話内に他 ${r.total_in_source - 1} 件</span> ▾</span>`
    : '';
  const snippet = makeSnippet(compactBlankLines(r.content || ''), _currentQuery);
  const body = linkifyFileMentions(styleMarkers(highlight(snippet, _currentQuery)));
  const media = renderResultMedia(r);
  const rel = relevanceLabel(r);
  const relHtml = rel.pct === null
    ? '<span class="distance">距離 ?</span>'
    : `<span class="relevance ${rel.kind}" title="${rel.kind === 'rerank' ? 'リランカー判定' : 'ベクトル類似'}">${rel.icon} 関連度 ${rel.pct}%</span>`;
  const whyChips = whyHitChips(r);
  return `
    <div class="result" data-idx="${idx}" data-record-id="${esc(r.id)}">
      <div class="result-meta">
        <span>${ts}</span>
        <span class="source-badge ${badge.cls}">${esc(srcLabel)}</span>
        ${relHtml}
        ${whyChips}
        ${more}
        <span class="expand-hint">クリックで会話全体 ▾</span>
        <button class="record-delete-btn" title="この記録を削除" aria-label="削除">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </div>
      ${media}
      <div class="result-content">${body}</div>
    </div>
  `;
}

// Record deletion (with confirmation).
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.record-delete-btn');
  if (!btn) return;
  e.stopPropagation();
  const card = btn.closest('.result');
  const id = card?.dataset.recordId;
  if (!id) return;
  if (!confirm('この記録を完全に削除します。元に戻せません。続けますか？')) return;
  try {
    const r = await fetch('/api/records/' + encodeURIComponent(id), { method: 'DELETE' });
    if (!r.ok) {
      alert('削除に失敗しました: ' + r.statusText);
      return;
    }
    card.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
    card.style.opacity = '0';
    card.style.transform = 'translateX(-12px)';
    setTimeout(() => card.remove(), 200);
  } catch (err) {
    alert('削除に失敗しました: ' + err);
  }
});

// Click on a [file.pdf] mention inside a Claude transcript:
//   1. Look up the file by filename via /api/search (file + photo sources).
//   2. If found, open the actual asset in the lightbox.
//   3. If not found, fall back to re-searching by filename.
const FILE_RESOLVE_CACHE = {};
async function resolveFileMention(filename) {
  if (FILE_RESOLVE_CACHE[filename] !== undefined) return FILE_RESOLVE_CACHE[filename];
  try {
    const r = await fetch(
      '/api/search?q=' + encodeURIComponent(filename) +
      '&sources=file,photo&limit=3&min_chars=0'
    );
    const j = await r.json();
    for (const rec of (j.results || [])) {
      const sid = rec.source_id || '';
      const tail = sid.split('/').pop();
      if (tail === filename) {
        FILE_RESOLVE_CACHE[filename] = sid;
        return sid;
      }
    }
  } catch (e) { /* fall through */ }
  FILE_RESOLVE_CACHE[filename] = null;
  return null;
}

document.addEventListener('click', async (e) => {
  const mention = e.target.closest('.file-mention');
  if (!mention) return;
  e.stopPropagation();
  const fname = mention.dataset.filename;
  if (!fname) return;
  const lb = $('lightbox');
  // Open lightbox with a loading state immediately so the click feels
  // responsive even while we resolve the source_id.
  lb.innerHTML = '<div style="color:#9aa;font-size:14px;">…</div>';
  lb.classList.add('shown');
  const sid = await resolveFileMention(fname);
  if (!sid) {
    // Fall back to a re-search by filename.
    lb.classList.remove('shown');
    lb.innerHTML = '';
    $('q').value = fname;
    doSearch(fname);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    return;
  }
  const ext = (fname.match(/\.[a-zA-Z0-9]+$/) || [''])[0].toLowerCase();
  const url = '/api/file?source_id=' + encodeURIComponent(sid);
  showLightboxByExt(lb, fname, ext, url);
});

function lightboxChrome() {
  return `
    <button class="lightbox-close" aria-label="閉じる" title="閉じる (Esc)">✕</button>
    <div class="lightbox-hint">背景クリック / Esc / ✕ で閉じる</div>`;
}

function showLightboxByExt(lb, fname, ext, url) {
  // HEIC / TIFF: Chromium can't render these. Offer the original to
  // open in the user's default macOS app.
  const browserPreviewable = ['.jpg','.jpeg','.png','.gif','.webp','.pdf'];
  let body = '';
  if (browserPreviewable.includes(ext)) {
    if (ext === '.pdf') {
      body = `<div class="lightbox-body"><iframe src="${url}"></iframe></div>`;
    } else {
      body = `<div class="lightbox-body"><img src="${url}" onerror="this.outerHTML='<div style=&quot;color:#fff;text-align:center&quot;>表示できませんでした<br><a href=&quot;${url}&quot; download style=&quot;color:#a5b4fc&quot;>ダウンロード</a></div>'"></div>`;
    }
  } else if (['.md','.markdown','.txt'].includes(ext)) {
    body = `<div class="lightbox-body"><iframe src="${url}"></iframe></div>`;
  } else {
    const panelStyle = "color:#fff;text-align:center;background:#1c2030;padding:32px;border-radius:12px;max-width:420px;font-size:14px;line-height:1.6;";
    body = `
      <div class="lightbox-body"><div style="${panelStyle}">
        <div style="margin-bottom:12px;color:var(--text-3);">${icon('file-text', 48)}</div>
        <div style="font-weight:600;margin-bottom:4px;">${esc(fname)}</div>
        <div style="color:#9aa;font-size:12px;margin-bottom:18px;">${esc(ext)} はブラウザで直接表示できません</div>
        <a href="${url}" target="_blank" style="display:inline-block;padding:8px 18px;background:#818cf8;color:#fff;border-radius:6px;text-decoration:none;font-weight:500;">ダウンロード / 開く</a>
      </div></div>`;
  }
  lb.innerHTML = lightboxChrome() + body;
}

// Lightbox: clicking a thumbnail opens the full asset.
(function setupLightbox() {
  const lb = document.createElement('div');
  lb.className = 'lightbox';
  lb.id = 'lightbox';
  document.body.appendChild(lb);
  function closeLightbox() {
    lb.classList.remove('shown');
    lb.innerHTML = '';
  }
  lb.addEventListener('click', (e) => {
    // Close on: background click, ✕ button, anywhere outside the body.
    if (e.target === lb || e.target.classList?.contains('lightbox-close')) {
      closeLightbox();
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && lb.classList.contains('shown')) {
      closeLightbox();
    }
  });
  document.addEventListener('click', (e) => {
    const thumb = e.target.closest('.thumb');
    if (!thumb) return;
    e.stopPropagation();
    const kind = thumb.dataset.preview;
    const url = thumb.dataset.url;
    const fname = (url.match(/source_id=.*%2F([^&]+)$/) || [,''])[1] || '';
    const decodedFname = decodeURIComponent(fname);
    const ext = (decodedFname.match(/\.[a-zA-Z0-9]+$/) || [''])[0].toLowerCase();
    if (kind === 'image') {
      showLightboxByExt(lb, decodedFname || 'image', ext, url);
    } else if (kind === 'pdf') {
      lb.innerHTML = lightboxChrome() + `<div class="lightbox-body"><iframe src="${url}"></iframe></div>`;
    }
    lb.classList.add('shown');
  });
})();

async function toggleSiblings(resultEl, badge) {
  const existing = resultEl.querySelector('.siblings-panel');
  if (existing) {
    existing.remove();
    badge.textContent = badge.textContent.replace('▴', '▾');
    return;
  }
  const sid = badge.dataset.moreSid;
  if (!sid) return;

  const panel = document.createElement('div');
  panel.className = 'siblings-panel';
  panel.innerHTML = '<div class="loading">読み込み中…</div>';
  resultEl.appendChild(panel);
  badge.textContent = badge.textContent.replace('▾', '▴');

  try {
    const params = new URLSearchParams({ q: q.value, source_id: sid, limit: 30 });
    const j = await (await fetch(`/api/search/siblings?${params}`)).json();
    const sibs = j.results || [];
    if (!sibs.length) {
      panel.innerHTML = '<div class="empty">他の一致は見つかりません</div>';
      return;
    }
    // Skip the first one if it's the same as the result we expanded from
    panel.innerHTML = sibs.slice(1).map(s => {
      const ts = s.timestamp ? new Date(s.timestamp * 1000).toLocaleString('ja-JP') : 'n/a';
      const role = (s.metadata && s.metadata.role) ? s.metadata.role : '';
      return `<div class="sibling-item">
        <div class="meta">${esc(ts)} · ${esc(s.source)}${role ? '/' + esc(role) : ''} · dist ${s.distance.toFixed(2)}</div>
        <div class="content">${highlight(s.content, _currentQuery)}</div>
      </div>`;
    }).join('');
  } catch (e) {
    panel.innerHTML = `<div class="empty">エラー: ${esc(String(e))}</div>`;
  }
}

async function toggleSession(el, result) {
  const existing = el.querySelector('.session-panel');
  if (existing) { existing.remove(); el.classList.remove('expanded'); return; }
  if (!result.source_id) return;
  el.classList.add('expanded');
  const panel = document.createElement('div');
  panel.className = 'session-panel';
  panel.innerHTML = '<div class="loading">会話を読み込み中…</div>';
  el.appendChild(panel);
  try {
    const j = await (await fetch(`/api/session?source_id=${encodeURIComponent(result.source_id)}`)).json();
    if (!j.records?.length) { panel.innerHTML = '<div class="empty">会話が見つかりません</div>'; return; }
    panel.innerHTML = `
      <div class="session-header">この会話の全${j.count}メッセージ（時系列順）</div>
      ${j.records.map(rec => renderSessionMsg(rec, result.id)).join('')}
    `;
  } catch (e) {
    panel.innerHTML = `<div class="empty">エラー: ${esc(String(e))}</div>`;
  }
}

function renderSessionMsg(rec, highlightId) {
  const ts = rec.timestamp ? new Date(rec.timestamp * 1000).toLocaleString('ja-JP') : 'n/a';
  const role = (rec.metadata && rec.metadata.role) ? rec.metadata.role : '?';
  const roleKey = role === 'user' || role === 'assistant' ? role : 'other';
  return `
    <div class="session-msg ${roleKey}">
      <div class="session-msg-meta">
        <span class="role ${roleKey}">${esc(role)}</span>
        <span>${ts}</span>
      </div>
      <div class="session-msg-content">${highlight(rec.content, _currentQuery)}</div>
    </div>
  `;
}

q.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => doSearch(q.value), 200); });

// ===== Search autocomplete (recent queries + entities) =====
const RECENT_QUERIES_KEY = 'bunshin.recentQueries';
function getRecentQueries() {
  try { return JSON.parse(localStorage.getItem(RECENT_QUERIES_KEY) || '[]'); }
  catch { return []; }
}
function pushRecentQuery(query) {
  if (!query || !query.trim()) return;
  const t = query.trim();
  const cur = getRecentQueries().filter(x => x !== t);
  cur.unshift(t);
  localStorage.setItem(RECENT_QUERIES_KEY, JSON.stringify(cur.slice(0, 20)));
}

let _entityNames = null;
async function loadEntityNames() {
  if (_entityNames) return _entityNames;
  try {
    const r = await fetch('/api/entities');
    const j = await r.json();
    _entityNames = (j.entities || []).map(e => ({
      name: e.name,
      type: e.type,
      mentions: e.mentions,
    }));
  } catch { _entityNames = []; }
  return _entityNames;
}

const acEl = $('autocomplete');
let _acItems = [];
let _acIdx = -1;

function renderAutocomplete(qstr) {
  const trimmed = (qstr || '').trim().toLowerCase();
  const recents = getRecentQueries().filter(x => !trimmed || x.toLowerCase().includes(trimmed));
  const entities = (_entityNames || []).filter(e =>
    !trimmed || e.name.toLowerCase().includes(trimmed)
  ).slice(0, 8);
  _acItems = [];
  let html = '';
  if (recents.length) {
    html += '<div class="autocomplete-section-title">最近の検索</div>';
    for (const r of recents.slice(0, 5)) {
      _acItems.push(r);
      html += `<div class="autocomplete-item" data-value="${esc(r)}">
        <span class="ac-icon">🕐</span>
        <span class="ac-label">${esc(r)}</span>
      </div>`;
    }
  }
  if (entities.length) {
    html += '<div class="autocomplete-section-title">関連エンティティ</div>';
    for (const e of entities) {
      _acItems.push(e.name);
      html += `<div class="autocomplete-item" data-value="${esc(e.name)}">
        <span class="ac-icon">#</span>
        <span class="ac-label">${esc(e.name)}</span>
        <span class="ac-hint">${esc(e.type)} · ${e.mentions}件</span>
      </div>`;
    }
  }
  if (!_acItems.length) {
    hideAutocomplete();
    return;
  }
  _acIdx = -1;
  acEl.innerHTML = html;
  acEl.classList.add('shown');
  acEl.setAttribute('aria-hidden', 'false');
}

function hideAutocomplete() {
  acEl.classList.remove('shown');
  acEl.innerHTML = '';
  acEl.setAttribute('aria-hidden', 'true');
  _acIdx = -1;
}

function pickAcItem(idx) {
  const value = _acItems[idx];
  if (!value) return;
  q.value = value;
  hideAutocomplete();
  pushRecentQuery(value);
  doSearch(value);
}

q.addEventListener('focus', async () => {
  await loadEntityNames();
  renderAutocomplete(q.value);
});
q.addEventListener('blur', () => {
  // Delay so a click on a dropdown item still registers.
  setTimeout(hideAutocomplete, 150);
});
q.addEventListener('input', () => {
  if (_entityNames) renderAutocomplete(q.value);
});
q.addEventListener('keydown', (e) => {
  const items = acEl.querySelectorAll('.autocomplete-item');
  if (!items.length) {
    if (e.key === 'Enter') pushRecentQuery(q.value);
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _acIdx = (_acIdx + 1) % items.length;
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    _acIdx = (_acIdx - 1 + items.length) % items.length;
  } else if (e.key === 'Enter') {
    if (_acIdx >= 0) {
      e.preventDefault();
      pickAcItem(_acIdx);
      return;
    } else {
      pushRecentQuery(q.value);
      hideAutocomplete();
      return;
    }
  } else if (e.key === 'Escape') {
    hideAutocomplete();
    return;
  } else {
    return;
  }
  items.forEach((el, i) => el.classList.toggle('active', i === _acIdx));
});
acEl.addEventListener('click', (e) => {
  const item = e.target.closest('.autocomplete-item');
  if (!item) return;
  const idx = Array.from(acEl.querySelectorAll('.autocomplete-item')).indexOf(item);
  pickAcItem(idx);
});
sortSel.addEventListener('change', () => doSearch(q.value));
periodsEl.addEventListener('click', e => {
  if (!e.target.classList.contains('filter-chip')) return;
  document.querySelectorAll('#periods .filter-chip').forEach(c => c.classList.remove('active'));
  e.target.classList.add('active');
  currentPeriod = e.target.dataset.period;
  doSearch(q.value);
});
sourcesEl.addEventListener('click', e => {
  if (!e.target.classList.contains('filter-chip')) return;
  document.querySelectorAll('#sources .filter-chip').forEach(c => c.classList.remove('active'));
  e.target.classList.add('active');
  currentSource = e.target.dataset.source;
  doSearch(q.value);
});
// Populate example chips from user's top entities
async function loadExampleChips() {
  try {
    const j = await (await fetch('/api/entities')).json();
    const top = (j.entities || []).filter(e => e.mentions > 0).slice(0, 8);
    const container = $('example-chips');
    if (!container || !top.length) return;
    container.innerHTML = top.map(e => `<span class="chip" data-q="${esc(e.name)}">${esc(e.name)}</span>`).join('');
    container.querySelectorAll('.chip').forEach(chip => {
      chip.addEventListener('click', () => { q.value = chip.dataset.q; doSearch(q.value); q.focus(); });
    });
  } catch {}
}
loadExampleChips();

// ===== Chat =====
const chatForm = $('chat-form'), chatInput = $('chat-input'), chatMessages = $('chat-messages'), chatStatus = $('chat-status'), chatSend = $('chat-send');
const chatMic = $('chat-mic');
const chatModel = $('chat-model');
let _selectedModel = null;

// ===== Model selector (Ollama) =====
async function loadModelList() {
  try {
    const r = await fetch('/api/ollama/models');
    const j = await r.json();
    if (!j.models || !j.models.length) {
      chatModel.innerHTML = '<option value="">Ollama 未起動</option>';
      chatModel.disabled = true;
      return;
    }
    chatModel.innerHTML = j.models.map(m =>
      `<option value="${esc(m)}"${m === j.default ? ' selected' : ''}>${esc(m)}</option>`
    ).join('');
    _selectedModel = j.default || j.models[0];
    chatModel.disabled = false;
  } catch {
    chatModel.innerHTML = '<option value="">エラー</option>';
    chatModel.disabled = true;
  }
}
chatModel.addEventListener('change', () => {
  _selectedModel = chatModel.value || null;
});
loadModelList();

// ===== Ollama setup wizard (chat tab) =====
const ollamaBanner = $('ollama-status-banner');
let _ollamaPullInProgress = false;

function ollamaBannerHTML(state, info) {
  const ico = (path) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
  const warn = ico('<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>');
  const dl   = ico('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>');
  const play = ico('<polygon points="5 3 19 12 5 21 5 3"/>');
  const box  = ico('<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>');
  const model = info && info.recommended_model || 'qwen2.5:3b';

  if (state === 'not_installed') {
    return `
      <h3>${warn} チャット機能には Ollama が必要です</h3>
      <p>Ollama は、あなたの Mac の中だけで動く無料の AI です。インストールするとチャット機能が使えるようになります。</p>
      <div class="actions">
        <a class="btn primary" href="https://ollama.com/download/mac" target="_blank" rel="noopener">${dl} Ollama をダウンロード</a>
        <button class="btn" type="button" onclick="refreshOllamaStatus()">インストール済みなら再チェック</button>
      </div>
      <p class="hint">ダウンロード後、Ollama の指示に従ってインストールしてください。検索・タイムライン・関係性タブは Ollama なしでも動きます。</p>
    `;
  }
  if (state === 'not_running') {
    return `
      <h3>${warn} Ollama が起動していません</h3>
      <p>Ollama アプリを起動するとチャットが使えます。</p>
      <div class="actions">
        <button class="btn primary" type="button" onclick="launchOllamaApp()">${play} Ollama を起動</button>
        <button class="btn" type="button" onclick="refreshOllamaStatus()">起動済みなら再チェック</button>
      </div>
    `;
  }
  if (state === 'no_models') {
    return `
      <h3>${box} AI モデルが入っていません</h3>
      <p>軽量モデル <code>${esc(model)}</code> をダウンロードします（約 1.9 GB、Wi-Fi で数分）。</p>
      <div class="actions">
        <button class="btn primary" type="button" id="ollama-pull-btn" onclick="pullDefaultModel('${esc(model)}')">${dl} ${esc(model)} を入手</button>
      </div>
      <pre class="pull-log" id="ollama-pull-log" hidden></pre>
    `;
  }
  return '';
}

async function refreshOllamaStatus() {
  if (!ollamaBanner) return;
  if (_ollamaPullInProgress) return;  // don't disrupt an in-flight pull
  try {
    const r = await fetch('/api/ollama/status');
    const s = await r.json();
    if (s.state === 'ready') {
      ollamaBanner.hidden = true;
      ollamaBanner.innerHTML = '';
      // Refresh the model selector now that Ollama is ready.
      loadModelList();
      return;
    }
    ollamaBanner.hidden = false;
    ollamaBanner.innerHTML = ollamaBannerHTML(s.state, s);
  } catch {
    // Network or parse error — keep banner state untouched.
  }
}

async function launchOllamaApp() {
  try {
    const r = await fetch('/api/ollama/launch', { method: 'POST' });
    const j = await r.json();
    if (!r.ok) {
      alert('Ollama アプリが見つかりません。先にインストールしてください。');
      return;
    }
    // Give Ollama 3 s to start the server, then recheck.
    setTimeout(refreshOllamaStatus, 3000);
  } catch {
    alert('Ollama の起動に失敗しました');
  }
}

async function pullDefaultModel(model) {
  const log = $('ollama-pull-log');
  const btn = $('ollama-pull-btn');
  if (!log || !btn) return;
  if (_ollamaPullInProgress) return;
  _ollamaPullInProgress = true;
  log.hidden = false;
  log.textContent = `pulling ${model}...`;
  btn.disabled = true;
  btn.textContent = 'ダウンロード中…';
  try {
    const r = await fetch(`/api/ollama/pull?model=${encodeURIComponent(model)}`, { method: 'POST' });
    if (!r.body) throw new Error('no stream');
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let lastLine = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\\n');
      buffer = lines.pop() || '';
      for (const ln of lines) {
        if (!ln.trim()) continue;
        try {
          const j = JSON.parse(ln);
          if (j.line) { lastLine = j.line; log.textContent = lastLine; log.scrollTop = log.scrollHeight; }
          if (j.done) {
            if (j.code === 0) {
              log.textContent = lastLine + '\\n✓ ダウンロード完了';
            } else {
              log.textContent = lastLine + `\\n✗ エラー (code ${j.code})`;
            }
          }
        } catch {}
      }
    }
  } catch (e) {
    log.textContent += '\\n✗ ' + (e && e.message || 'error');
  } finally {
    _ollamaPullInProgress = false;
    btn.disabled = false;
    btn.textContent = `${model} を入手`;
    // Recheck so banner disappears on success.
    setTimeout(refreshOllamaStatus, 800);
  }
}

refreshOllamaStatus();

// ===== Image upload → OCR → save as record =====
(function setupImageUpload() {
  const btn = $('chat-attach');
  const file = $('chat-file-input');
  if (!btn || !file) return;
  btn.addEventListener('click', () => file.click());
  file.addEventListener('change', async () => {
    const f = file.files?.[0];
    if (!f) return;
    file.value = '';  // allow re-uploading the same file
    const empty = chatMessages.querySelector('.empty');
    if (empty) empty.remove();
    appendMsg('user', `📎 ${f.name}`);
    const status = appendMsg('assistant', '画像を解析中…');
    const fd = new FormData();
    fd.append('image', f);
    try {
      const r = await fetch('/api/upload-image', { method: 'POST', body: fd });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        status.textContent = 'エラー: ' + (err.detail || r.statusText);
        return;
      }
      const j = await r.json();
      const lines = ['記憶に追加しました'];
      if (j.exif?.date) {
        lines.push(`- 撮影日: ${new Date(j.exif.date*1000).toLocaleString('ja-JP')}`);
      }
      if (j.exif?.camera) lines.push(`- カメラ: ${j.exif.camera}`);
      if (j.exif?.gps) lines.push(`- GPS: ${j.exif.gps.lat}, ${j.exif.gps.lon}`);
      lines.push(`- OCR テキスト: ${j.ocr_chars} 文字`);
      if (j.ocr_preview) {
        lines.push('');
        lines.push('```');
        lines.push(j.ocr_preview);
        lines.push('```');
      }
      status.innerHTML = renderMarkdown(lines.join(String.fromCharCode(10)));
      addTTSButton(status);
    } catch (e) {
      status.textContent = 'エラー: ' + String(e);
    }
  });
})();

// ===== Voice output (Text-to-Speech via speechSynthesis) =====
let _currentUtterance = null;
function pickJaVoice() {
  const voices = window.speechSynthesis?.getVoices?.() || [];
  return voices.find(v => v.lang === 'ja-JP') ||
         voices.find(v => v.lang?.startsWith('ja')) ||
         voices[0] || null;
}
function speakText(text, btn) {
  if (!window.speechSynthesis) return;
  // Toggle off if the same button is clicked while speaking.
  if (_currentUtterance && btn === _currentUtterance._btn) {
    window.speechSynthesis.cancel();
    return;
  }
  window.speechSynthesis.cancel();
  // Strip markdown markers so the reader doesn't say "asterisk asterisk".
  const clean = text
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`[^`]+`/g, ' ')
    .replace(/[#*_>\-]/g, ' ')
    .replace(/\[\d+\]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!clean) return;
  const u = new SpeechSynthesisUtterance(clean);
  u.lang = 'ja-JP';
  u.rate = 1.05;
  u.pitch = 1.0;
  const voice = pickJaVoice();
  if (voice) u.voice = voice;
  u._btn = btn;
  u.onend = () => {
    if (_currentUtterance && _currentUtterance._btn === btn) {
      btn.classList.remove('speaking');
      btn.title = '読み上げ';
      _currentUtterance = null;
    }
  };
  u.onerror = u.onend;
  _currentUtterance = u;
  btn.classList.add('speaking');
  btn.title = '停止';
  window.speechSynthesis.speak(u);
}

function addTTSButton(msg) {
  if (!window.speechSynthesis) return;
  const btn = document.createElement('button');
  btn.className = 'tts-btn';
  btn.type = 'button';
  btn.title = '読み上げ';
  btn.setAttribute('aria-label', '読み上げ');
  btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>`;
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    // The text we read is the rendered text content of the message,
    // excluding any context list rendered later.
    const txt = msg.textContent || '';
    speakText(txt, btn);
  });
  msg.appendChild(btn);
}

// Preload voices (Chromium fires getVoices async).
if (window.speechSynthesis) {
  window.speechSynthesis.onvoiceschanged = () => {/* fire-and-forget */};
}

// ===== Voice input (Web Speech API) =====
(function setupVoiceInput() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    chatMic.disabled = true;
    chatMic.title = 'このブラウザでは音声入力に対応していません';
    return;
  }
  const rec = new SR();
  rec.continuous = false;
  rec.interimResults = true;
  rec.lang = (navigator.language || 'ja-JP').startsWith('ja') ? 'ja-JP' : 'en-US';
  let listening = false;
  let baseText = '';

  function start() {
    baseText = chatInput.value;
    try {
      rec.start();
    } catch (e) {
      // Already running — Safari can throw if we double-start.
      return;
    }
    listening = true;
    chatMic.classList.add('recording');
    chatMic.title = 'クリックで停止';
    chatStatus.textContent = '聞いています…';
  }
  function stop() {
    listening = false;
    try { rec.stop(); } catch {}
    chatMic.classList.remove('recording');
    chatMic.title = '音声入力 (Web Speech API)';
    if (chatStatus.textContent === '聞いています…') chatStatus.textContent = '';
  }

  rec.onresult = (e) => {
    let interim = '';
    let finalT = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) finalT += r[0].transcript;
      else interim += r[0].transcript;
    }
    const sep = baseText && !baseText.endsWith(' ') ? ' ' : '';
    chatInput.value = baseText + sep + finalT + interim;
  };
  rec.onerror = (e) => {
    chatStatus.textContent = `音声入力エラー: ${e.error}`;
    chatStatus.className = 'chat-status error';
    setTimeout(() => { chatStatus.textContent = ''; chatStatus.className = 'chat-status'; }, 2200);
    stop();
  };
  rec.onend = () => {
    if (listening) stop();
  };

  chatMic.addEventListener('click', () => {
    if (listening) stop();
    else start();
  });
})();
const chatSessions = $('chat-sessions'), chatNewBtn = $('chat-new-btn');
let currentSessionId = null;

async function loadSessionList(searchQuery) {
  try {
    const q = (searchQuery || '').trim();
    const url = q ? '/api/chat/sessions?q=' + encodeURIComponent(q) : '/api/chat/sessions';
    const r = await fetch(url);
    const j = await r.json();
    const sessions = j.sessions || [];
    if (!sessions.length) {
      chatSessions.innerHTML = '<div style="font-size:11px;color:var(--text-4);padding:8px;">' +
        (q ? '(該当する会話なし)' : '(まだ会話がありません)') + '</div>';
      return;
    }
    const shortenModel = (m) => {
      if (!m) return '';
      const base = String(m).split(':')[0];
      const tail = String(m).includes(':') ? String(m).split(':')[1] : '';
      // qwen2.5:32b → 32b / llama3.2:3b → 3b / fallback to last 10 chars
      return tail || (base.length > 12 ? base.slice(0, 10) + '…' : base);
    };
    const fmtDate = (ts) => {
      const d = new Date(ts * 1000), now = new Date();
      const sameYear = d.getFullYear() === now.getFullYear();
      return sameYear ? `${d.getMonth()+1}/${d.getDate()}` : `${d.getFullYear()}/${d.getMonth()+1}/${d.getDate()}`;
    };
    chatSessions.innerHTML = sessions.map(s => {
      const date = fmtDate(s.updated_at);
      const active = s.id === currentSessionId ? 'active' : '';
      const model = shortenModel(s.model);
      const preview = s.preview ? `<div class="preview">${esc(s.preview)}</div>` : '';
      const modelChip = model ? `<span>${esc(model)}</span><span class="sep">·</span>` : '';
      return `
        <div class="chat-session-item ${active}" data-sid="${esc(s.id)}">
          <div class="title">${esc(s.title)}</div>
          ${preview}
          <div class="meta">${modelChip}<span>${s.message_count}件</span><span class="sep">·</span><span>${esc(date)}</span></div>
          <div class="delete-btn" data-del="${esc(s.id)}" title="削除">×</div>
        </div>
      `;
    }).join('');
    chatSessions.querySelectorAll('.chat-session-item').forEach(el => {
      el.addEventListener('click', (ev) => {
        if (ev.target.dataset && ev.target.dataset.del) return;
        loadSession(el.dataset.sid);
      });
    });
    chatSessions.querySelectorAll('.delete-btn').forEach(el => {
      el.addEventListener('click', async (ev) => {
        ev.stopPropagation();
        const sid = el.dataset.del;
        if (!confirm('この会話を削除しますか？')) return;
        await fetch(`/api/chat/sessions/${sid}`, { method: 'DELETE' });
        if (currentSessionId === sid) startNewChat();
        loadSessionList();
      });
    });
  } catch (e) {
    chatSessions.innerHTML = `<div style="font-size:11px;color:#a44;padding:8px;">${esc(String(e))}</div>`;
  }
}

async function loadSession(sid) {
  try {
    const r = await fetch(`/api/chat/sessions/${sid}`);
    const j = await r.json();
    if (j.error) return;
    currentSessionId = sid;
    chatMessages.innerHTML = '';
    for (const m of (j.messages || [])) {
      appendMsg(m.role, m.content, m.context_used);
    }
    loadSessionList();  // refresh active highlight
  } catch (e) {
    console.error(e);
  }
}

function startNewChat() {
  currentSessionId = null;
  chatMessages.innerHTML = `<div class="empty">
    新しい会話を始めましょう。<br><br>
    <svg class="inline-tip-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.3 1 2.1V18h6v-1.2c0-.8.4-1.6 1-2.1A7 7 0 0 0 12 2z"/></svg>
    「覚えといて: ...」「メモ: ...」で記憶への保存だけもできます。
  </div>`;
  loadSessionList();
}

chatNewBtn.addEventListener('click', startNewChat);
loadSessionList();

// Chat session search — filter the sidebar list as the user types.
(function setupChatSessionSearch() {
  const input = $('chat-session-search');
  if (!input) return;
  let timer = null;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => loadSessionList(input.value), 220);
  });
})();

// ===== Global keyboard shortcuts =====
// ⌘+K: focus search   ⌘+1-6: tab switch
// ⌘+N: new chat       ⌘+/: show shortcut help
// Esc:  close lightbox / help (already wired)
(function setupShortcuts() {
  const PANE_ORDER = ['search', 'chat', 'insights', 'timeline', 'graph', 'settings'];
  function switchTab(pane) {
    const tab = document.querySelector('.sidebar-tab[data-pane="' + pane + '"]');
    if (tab) tab.click();
  }
  document.addEventListener('keydown', (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (!mod) return;
    // ⌘+K → focus search
    if (e.key.toLowerCase() === 'k') {
      e.preventDefault();
      switchTab('search');
      setTimeout(() => $('q')?.focus(), 30);
      return;
    }
    // ⌘+N is owned by the "+ 記憶" modal (setupAddMemory). Don't intercept
    // it here — the add-memory handler will pick it up.
    // ⌘+/ → help modal
    if (e.key === '/' || e.key === '?') {
      e.preventDefault();
      showHelpModal();
      return;
    }
    // ⌘+1-6 → tabs
    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= PANE_ORDER.length) {
      e.preventDefault();
      switchTab(PANE_ORDER[n - 1]);
    }
  });
})();

function showHelpModal() {
  const existing = document.getElementById('help-modal');
  if (existing) { existing.remove(); return; }
  const modal = document.createElement('div');
  modal.id = 'help-modal';
  modal.className = 'help-modal';
  const isMac = navigator.platform.toLowerCase().includes('mac');
  const K = isMac ? '⌘' : 'Ctrl';
  modal.innerHTML = `
    <div class="help-modal-card">
      <div class="help-modal-head">
        <h2>キーボードショートカット</h2>
        <button class="help-modal-close" aria-label="閉じる">✕</button>
      </div>
      <div class="help-modal-body">
        <div class="help-section">
          <div class="help-section-title">タブ切替</div>
          <div class="help-row"><kbd>${K}</kbd><kbd>1</kbd><span>検索</span></div>
          <div class="help-row"><kbd>${K}</kbd><kbd>2</kbd><span>チャット</span></div>
          <div class="help-row"><kbd>${K}</kbd><kbd>3</kbd><span>気づき</span></div>
          <div class="help-row"><kbd>${K}</kbd><kbd>4</kbd><span>タイムライン</span></div>
          <div class="help-row"><kbd>${K}</kbd><kbd>5</kbd><span>関係性</span></div>
          <div class="help-row"><kbd>${K}</kbd><kbd>6</kbd><span>設定</span></div>
        </div>
        <div class="help-section">
          <div class="help-section-title">アクション</div>
          <div class="help-row"><kbd>${K}</kbd><kbd>K</kbd><span>検索バーにフォーカス</span></div>
          <div class="help-row"><kbd>${K}</kbd><kbd>N</kbd><span>メモを記憶に追加</span></div>
          <div class="help-row"><kbd>${K}</kbd><kbd>/</kbd><span>このヘルプを表示 / 閉じる</span></div>
          <div class="help-row"><kbd>Esc</kbd><span>ライトボックス / モーダルを閉じる</span></div>
        </div>
        <div class="help-section">
          <div class="help-section-title">チャットの便利機能</div>
          <div class="help-row"><span class="help-tip"><code>覚えといて: ◯◯</code> → AI に聞かずに記憶へ保存</span></div>
          <div class="help-row"><span class="help-tip">マイクボタン → 音声で入力（日本語認識）</span></div>
          <div class="help-row"><span class="help-tip">📎 ボタン → 画像アップロード（OCR 自動）</span></div>
        </div>
      </div>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', (e) => {
    if (e.target === modal || e.target.classList.contains('help-modal-close')) {
      modal.remove();
    }
  });
  document.addEventListener('keydown', function onEsc(e) {
    if (e.key === 'Escape') {
      modal.remove();
      document.removeEventListener('keydown', onEsc);
    }
  });
}

// Lightweight Markdown → HTML renderer.
//
// We intentionally avoid pulling in a full library: this handles 90% of
// what Ollama returns (headings, lists, bold, italic, inline code, fenced
// blocks, blockquotes) and is small enough to ship inline.
function renderMarkdown(text) {
  if (!text) return '';
  // 1. Escape HTML first.
  let html = esc(text);
  const NL = String.fromCharCode(10);

  // 2. Pull code blocks out so their contents survive other rewrites.
  const blocks = [];
  html = html.replace(/```([a-zA-Z0-9_+-]*)([\s\S]*?)```/g, (_m, lang, code) => {
    // strip a single leading/trailing newline that frames the fence
    if (code.charAt(0) === NL) code = code.slice(1);
    if (code.endsWith(NL)) code = code.slice(0, -1);
    blocks.push({ lang: lang || '', code });
    return '__BCB' + (blocks.length - 1) + '__';
  });
  const inlines = [];
  html = html.replace(/`([^`]{1,200})`/g, (_m, code) => {
    inlines.push(code);
    return '__BIC' + (inlines.length - 1) + '__';
  });

  // 3. Headings, bold, italic — line-anchored, no NL in regex.
  html = html.replace(/^### (.+)$/gm, '<h3 class="md-h md-h3">$1</h3>');
  html = html.replace(/^## (.+)$/gm,  '<h2 class="md-h md-h2">$1</h2>');
  html = html.replace(/^# (.+)$/gm,   '<h1 class="md-h md-h1">$1</h1>');
  html = html.replace(/\*\*([^*]{1,300})\*\*/g, '<strong>$1</strong>');
  html = html.replace(/(?<![\*\w])\*([^*]{1,300})\*(?![\*\w])/g, '<em>$1</em>');

  // 4. Lists, blockquotes, hr — process line-by-line so we never need
  //    a newline character inside a regex literal.
  const lines = html.split(NL);
  const out = [];
  let inUl = false;
  let inOl = false;
  function closeLists() {
    if (inUl) { out.push('</ul>'); inUl = false; }
    if (inOl) { out.push('</ol>'); inOl = false; }
  }
  for (const raw of lines) {
    const ulM = raw.match(/^([-*]) (.+)$/);
    const olM = raw.match(/^(\d+)\. (.+)$/);
    if (ulM) {
      if (inOl) { out.push('</ol>'); inOl = false; }
      if (!inUl) { out.push('<ul class="md-ul">'); inUl = true; }
      out.push('<li>' + ulM[2] + '</li>');
      continue;
    }
    if (olM) {
      if (inUl) { out.push('</ul>'); inUl = false; }
      if (!inOl) { out.push('<ol class="md-ol">'); inOl = true; }
      out.push('<li>' + olM[2] + '</li>');
      continue;
    }
    closeLists();
    const bqM = raw.match(/^&gt; (.+)$/);
    if (bqM) {
      out.push('<blockquote class="md-bq">' + bqM[1] + '</blockquote>');
      continue;
    }
    if (/^---+$/.test(raw)) {
      out.push('<hr class="md-hr">');
      continue;
    }
    out.push(raw);
  }
  closeLists();

  // 5. Reassemble. Replace remaining bare newlines that are still inside
  //    flowing text with <br> — but skip blanks adjacent to block tags
  //    we just emitted.
  const finalLines = [];
  for (let i = 0; i < out.length; i++) {
    const cur = out[i];
    finalLines.push(cur);
    const next = out[i + 1];
    if (next === undefined) continue;
    const endsTag = /<\/?(?:ul|ol|li|h[1-6]|blockquote|hr|pre)[^>]*>\s*$/.test(cur);
    const startsTag = /^<\/?(?:ul|ol|li|h[1-6]|blockquote|hr|pre)/.test(next);
    if (!endsTag && !startsTag && cur.trim() !== '' && next.trim() !== '') {
      finalLines.push('<br>');
    }
  }
  html = finalLines.join('');

  // 6. Restore code blocks and inline code at the very end.
  html = html.replace(/__BCB(\d+)__/g, (_m, idx) => {
    const b = blocks[parseInt(idx, 10)];
    const langLabel = b.lang ? `<span class="md-lang">${esc(b.lang)}</span>` : '';
    // Encode the raw code in a data attribute so the copy button can
    // recover it untouched (esc-decoded automatically by the browser).
    const dataAttr = esc(b.code);
    return `<pre class="md-pre">${langLabel}<button class="md-copy-btn" data-copy-source="block" aria-label="コピー">📋</button><code class="md-code" data-raw="${dataAttr}">${b.code}</code></pre>`;
  });
  html = html.replace(/__BIC(\d+)__/g, (_m, idx) => {
    return `<code class="md-inline">${inlines[parseInt(idx, 10)]}</code>`;
  });
  return html;
}

// Copy-button click → write the code block content to the clipboard.
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.md-copy-btn');
  if (!btn) return;
  e.stopPropagation();
  const pre = btn.parentElement;
  const code = pre?.querySelector('code.md-code');
  const raw = code?.dataset.raw || code?.textContent || '';
  try {
    await navigator.clipboard.writeText(raw);
    const original = btn.textContent;
    btn.textContent = '✓';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = original;
      btn.classList.remove('copied');
    }, 1200);
  } catch {
    btn.textContent = '✗';
    setTimeout(() => { btn.textContent = '📋'; }, 1200);
  }
});

function linkifyCitations(text, contextList) {
  // First render Markdown (escapes + structural HTML), then turn [N]
  // tokens into citation pills if a context list exists.
  let html = renderMarkdown(text);
  if (!contextList || !contextList.length) return html;
  html = html.replace(/\[(\d+)\]/g, (m, n) => {
    const num = parseInt(n, 10);
    if (num >= 1 && num <= contextList.length) {
      return `<a class="citation" data-cit="${num}">[${num}]</a>`;
    }
    return m;
  });
  return html;
}

function renderCtxList(contextList, listId) {
  return contextList.map((c, i) => {
    const num = i + 1;
    const ts = c.timestamp ? new Date(c.timestamp * 1000).toLocaleString('ja-JP') : 'n/a';
    const cid = `${listId}-${num}`;
    return `<div class="ctx-item-numbered" id="${cid}">
      <div class="ctx-num">${num}</div>
      <div style="flex:1;">
        <div style="color:#bbb;font-size:12px;"><b>${esc(ts)}</b> · ${esc(c.source)}</div>
        <div style="color:#999;font-size:12px;margin-top:4px;">${esc((c.content||'').slice(0,300))}…</div>
      </div>
    </div>`;
  }).join('');
}

function appendMsg(role, content, contextList) {
  const msg = document.createElement('div');
  msg.className = 'chat-msg ' + role;
  if (role === 'assistant') {
    msg.innerHTML = linkifyCitations(content, contextList);
    // TTS button — only show on assistant messages with content.
    addTTSButton(msg);
  } else {
    msg.textContent = content;
  }
  if (contextList && contextList.length) {
    const toggle = document.createElement('span');
    toggle.className = 'ctx-toggle';
    toggle.innerHTML = `${icon('layers', 13)} <span>参照した過去記憶 ${contextList.length}件</span> ▾`;
    const listId = 'ctx-' + Math.random().toString(36).slice(2, 8);
    const list = document.createElement('div');
    list.className = 'ctx-list';
    list.innerHTML = renderCtxList(contextList, listId);
    toggle.onclick = () => list.classList.toggle('shown');
    msg.appendChild(document.createElement('br'));
    msg.appendChild(toggle);
    msg.appendChild(list);
    // Wire citation link clicks to expand the list + scroll to item.
    msg.querySelectorAll('.citation').forEach(a => {
      a.addEventListener('click', (ev) => {
        ev.preventDefault();
        list.classList.add('shown');
        const num = parseInt(a.dataset.cit, 10);
        const target = list.querySelector(`#${CSS.escape(listId)}-${num}`);
        if (target) target.scrollIntoView({ block: 'center', behavior: 'smooth' });
      });
      // Hover-preview: spawn a floating card with the cited record's
      // content so the user can peek without scrolling down.
      a.addEventListener('mouseenter', () => {
        const num = parseInt(a.dataset.cit, 10);
        const rec = contextList[num - 1];
        if (!rec) return;
        const prev = document.createElement('div');
        prev.className = 'citation-preview';
        prev.id = 'cit-prev-active';
        const ts = rec.timestamp ? new Date(rec.timestamp * 1000).toLocaleString('ja-JP') : '';
        prev.innerHTML = '<div class="cp-head">[' + num + '] ' + esc(rec.source || '') + ' · ' + esc(ts) + '</div>' +
                         '<div class="cp-body">' + esc((rec.content || '').slice(0, 360)) + '</div>';
        document.body.appendChild(prev);
        const rect = a.getBoundingClientRect();
        prev.style.top = (rect.bottom + 6) + 'px';
        // Keep it on-screen horizontally.
        const left = Math.min(rect.left, window.innerWidth - 440);
        prev.style.left = Math.max(8, left) + 'px';
      });
      a.addEventListener('mouseleave', () => {
        document.getElementById('cit-prev-active')?.remove();
      });
    });
  }
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return msg;
}

const MEMO_PREFIXES = ['覚えといて:', '覚えといて：', 'メモ:', 'メモ：', '覚えて:', '覚えて：', '/note ', '/memo '];

function detectMemo(text) {
  for (const prefix of MEMO_PREFIXES) {
    if (text.startsWith(prefix)) return text.slice(prefix.length).trim();
  }
  return null;
}

async function saveMemo(content) {
  const empty = chatMessages.querySelector('.empty');
  if (empty) empty.remove();
  appendMsg('user', content);
  const note = appendMsg('assistant', 'メモを保存中…');
  try {
    const resp = await fetch('/api/note', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    const j = await resp.json();
    if (j.saved) {
      note.textContent = `メモを記憶に保存しました（${content.length}文字）。後で「`+ content.slice(0, 20) + `」で検索できます。`;
      loadStats();
    } else {
      note.textContent = `エラー: ${j.error || '保存できませんでした'}`;
    }
  } catch (e) {
    note.textContent = `エラー: ${e}`;
  }
}

chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = chatInput.value.trim();
  if (!query) return;

  // Detect memo intent
  const memoContent = detectMemo(query);
  if (memoContent) {
    chatInput.value = '';
    await saveMemo(memoContent);
    return;
  }

  // Remove empty placeholder
  const empty = chatMessages.querySelector('.empty');
  if (empty) empty.remove();

  appendMsg('user', query);
  chatInput.value = '';
  chatSend.disabled = true;
  chatStatus.className = 'chat-status thinking';
  chatStatus.innerHTML = '<span class="thinking-dots"><span></span><span></span><span></span></span> 過去のあなたを読み込み中…';

  const respMsg = appendMsg('assistant', '');
  try {
    const params = new URLSearchParams({ q: query });
    if (currentSessionId) params.set('session_id', currentSessionId);
    if (_selectedModel) params.set('model', _selectedModel);
    const resp = await fetch('/api/chat?' + params);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      respMsg.textContent = `エラー: ${err.detail || resp.statusText}`;
      chatStatus.textContent = '';
      chatSend.disabled = false;
      return;
    }
    chatStatus.textContent = '過去記憶を検索中…';
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let contextList = null;
    let fullText = '';
    let firstDelta = true;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const j = JSON.parse(line);
          if (j.session_id) {
            currentSessionId = j.session_id;
          } else if (j.context) {
            contextList = j.context;
            const n = contextList.length;
            const mdl = _selectedModel || 'AI';
            chatStatus.innerHTML = `<span class="thinking-dots"><span></span><span></span><span></span></span> ${n} 件の過去記憶を読みました。${esc(mdl)} が考え中…（10〜30 秒）`;
          } else if (j.delta) {
            if (firstDelta) { chatStatus.textContent = ''; firstDelta = false; }
            fullText += j.delta;
            // Live Markdown rendering as chunks arrive. A blinking cursor
            // pinned to the end makes the wait feel like generation.
            respMsg.innerHTML = renderMarkdown(fullText) +
              '<span class="typing-cursor" aria-hidden="true"></span>';
            chatMessages.scrollTop = chatMessages.scrollHeight;
          } else if (j.done) {
            loadSessionList();  // refresh sidebar with new session/message count
          } else if (j.error) {
            respMsg.textContent = 'エラー: ' + j.error;
          }
        } catch {}
      }
    }
    // Re-render with citations linkified + context toggle.
    if (contextList) {
      respMsg.innerHTML = linkifyCitations(fullText, contextList);
      const toggle = document.createElement('span');
      toggle.className = 'ctx-toggle';
      toggle.innerHTML = `${icon('layers', 13)} <span>参照した過去記憶 ${contextList.length}件</span> ▾`;
      const listId = 'ctx-' + Math.random().toString(36).slice(2, 8);
      const list = document.createElement('div');
      list.className = 'ctx-list';
      list.innerHTML = renderCtxList(contextList, listId);
      toggle.onclick = () => list.classList.toggle('shown');
      respMsg.appendChild(document.createElement('br'));
      respMsg.appendChild(toggle);
      respMsg.appendChild(list);
      // Wire citation link clicks
      respMsg.querySelectorAll('.citation').forEach(a => {
        a.addEventListener('click', (ev) => {
          ev.preventDefault();
          list.classList.add('shown');
          const num = parseInt(a.dataset.cit, 10);
          const target = list.querySelector(`#${CSS.escape(listId)}-${num}`);
          if (target) target.scrollIntoView({ block: 'center', behavior: 'smooth' });
        });
      });
    }
    chatStatus.textContent = '';
  } catch (e) {
    respMsg.textContent = 'エラー: ' + e;
    chatStatus.textContent = '';
    chatStatus.className = 'chat-status error';
  } finally {
    chatSend.disabled = false;
    chatInput.focus();
  }
});
</script>
</body>
</html>
"""


def _start_background_watcher(db_path: Path) -> None:
    """If watchdog is available and the user has a watch directory configured,
    start a background watcher when the web server boots."""
    try:
        from bunshin.file_watcher import WATCHDOG_AVAILABLE, start_watcher
    except ImportError:
        return
    if not WATCHDOG_AVAILABLE:
        return

    # Default watch root precedence:
    #   1. settings.watch_dir set via the UI
    #   2. BUNSHIN_WATCH_DIR env var
    #   3. ~/Documents
    import os
    from bunshin.settings import get as get_setting
    saved_dir = None
    try:
        conn_tmp = init_db(db_path)
        try:
            v = get_setting(conn_tmp, "watch_dir")
            saved_dir = v.strip() if isinstance(v, str) and v.strip() else None
        finally:
            conn_tmp.close()
    except Exception:
        saved_dir = None
    candidates = [
        saved_dir,
        os.environ.get("BUNSHIN_WATCH_DIR"),
        str(Path.home() / "Documents"),
    ]
    watch_dir = None
    for c in candidates:
        if c and Path(c).exists():
            watch_dir = Path(c)
            break
    if not watch_dir:
        return

    try:
        start_watcher(db_path=db_path, root=watch_dir, idle_seconds=3.0)
        print(f"[bunshin] file watcher started on {watch_dir}", flush=True)
    except Exception as e:
        print(f"[bunshin] file watcher failed: {e}", flush=True)


def friendly_error(exc: Exception, fallback: str = "うまく動かなかったみたいです") -> dict:
    """Translate an internal exception to a JP-language payload safe for the UI.

    Never returns Python class names, tracebacks, paths, "ターミナル", or "ログ"
    — those words turn non-technical users away. The {error, hint, code} shape
    is what the frontend renders; hint should always be a *next action* the
    user themselves can take.
    """
    if isinstance(exc, FileNotFoundError):
        return {
            "error": "ファイルが見つかりません",
            "hint": "リネームや移動をした場合は、もう一度取り込んでみてください",
            "code": "file_not_found",
        }
    if isinstance(exc, PermissionError):
        return {
            "error": "権限がありません",
            "hint": "システム設定 → プライバシーとセキュリティ で Bunshin を許可してください",
            "code": "permission_denied",
        }
    if isinstance(exc, (ConnectionError, ConnectionRefusedError)):
        return {
            "error": "つながりませんでした",
            "hint": "Ollama アプリが起動しているか確認してから、もう一度試してください",
            "code": "connection_failed",
        }
    if isinstance(exc, TimeoutError):
        return {
            "error": "時間がかかりすぎました",
            "hint": "もう一度試してみてください。続く場合は AI モデルを軽いものに変えてみてください",
            "code": "timeout",
        }
    if isinstance(exc, ValueError):
        return {
            "error": "入力が正しくないようです",
            "hint": "値を確認してもう一度お試しください",
            "code": "invalid_value",
        }
    return {
        "error": fallback,
        "hint": "もう一度試してみてください。続く場合は 設定 → 困った時は から開発者に教えてください",
        "code": "internal_error",
    }


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="分身 (Bunshin)")

    @app.exception_handler(Exception)
    async def _all_exceptions(_request, exc):
        """Catch-all so users never see a raw Python traceback in the UI."""
        import traceback
        traceback.print_exc()  # full stack still goes to the dev terminal
        return JSONResponse(friendly_error(exc), status_code=500)

    _start_background_watcher(db_path)

    # ---- One-time signal computation on first launch after schema migration ----
    # Run on a background thread so server startup isn't blocked. The UI's
    # ordering by signal_score will be progressively populated as the
    # thread fills in each record. NULL signal_score is treated as 50.0
    # everywhere so partial state is still sortable.
    import threading
    def _backfill():
        try:
            _conn = init_db(db_path)
            try:
                recompute_signals(_conn, only_missing=True)
            finally:
                _conn.close()
        except Exception:
            pass
    threading.Thread(target=_backfill, daemon=True, name="signal-backfill").start()

    # One-time entity-type cleanup on startup — heals existing DBs where
    # the LLM mislabeled YouTube as a place, note as organization, etc.
    def _entity_heal():
        try:
            _conn = init_db(db_path)
            try:
                from bunshin.knowledge_graph import apply_entity_type_overrides
                apply_entity_type_overrides(_conn)
            finally:
                _conn.close()
        except Exception:
            pass
    threading.Thread(target=_entity_heal, daemon=True, name="entity-heal").start()

    # One-shot migrations. Each one runs at most once per DB; tracked in
    # the `migrations` table so we don't re-scan 15k records every launch.
    def _run_migrations():
        try:
            _conn = init_db(db_path)
            try:
                _conn.execute(
                    "CREATE TABLE IF NOT EXISTS migrations ("
                    "key TEXT PRIMARY KEY, applied_at INTEGER)"
                )
                _applied = {
                    r[0] for r in _conn.execute(
                        "SELECT key FROM migrations"
                    ).fetchall()
                }

                # v0.7.11: re-score every existing browser record so the
                # SNS/YouTube demotion added in v0.7.8 (-35) actually
                # applies to data already in the DB. Without this, the
                # flashback keeps surfacing YouTube titles even after the
                # signal logic change.
                if "sns_demotion_v0_7_11" not in _applied:
                    from bunshin.signals import compute_signal_score, extract_sender
                    rows = _conn.execute(
                        "SELECT id, metadata, content FROM records "
                        "WHERE source = 'browser'"
                    ).fetchall()
                    for rid, metadata, content in rows:
                        sender, domain = extract_sender(metadata)
                        score = compute_signal_score(content or "", "browser", sender, domain)
                        _conn.execute(
                            "UPDATE records SET signal_score = ? WHERE id = ?",
                            (score, rid),
                        )
                    _conn.execute(
                        "INSERT INTO migrations(key, applied_at) VALUES (?, ?)",
                        ("sns_demotion_v0_7_11",
                         int(__import__("time").time())),
                    )
                    _conn.commit()

                # v0.7.11: name old "(empty)" chat sessions retroactively
                # from their first user message (mirrors the auto-naming
                # added in v0.7.6 for new sessions).
                if "session_titles_v0_7_11" not in _applied:
                    try:
                        empty_sessions = _conn.execute(
                            "SELECT id FROM chat_sessions "
                            "WHERE (title IS NULL OR title = '' OR title = '(empty)')"
                        ).fetchall()
                        for (sid,) in empty_sessions:
                            row = _conn.execute(
                                "SELECT content FROM chat_messages "
                                "WHERE session_id = ? AND role = 'user' "
                                "ORDER BY created_at ASC LIMIT 1",
                                (sid,),
                            ).fetchone()
                            if row and row[0]:
                                first_line = row[0].strip().split("\n", 1)[0]
                                title = first_line[:40] + ("…" if len(first_line) > 40 else "")
                                if title:
                                    _conn.execute(
                                        "UPDATE chat_sessions SET title = ? WHERE id = ?",
                                        (title, sid),
                                    )
                    except Exception:
                        pass  # tables may not exist in very old DBs
                    _conn.execute(
                        "INSERT INTO migrations(key, applied_at) VALUES (?, ?)",
                        ("session_titles_v0_7_11",
                         int(__import__("time").time())),
                    )
                    _conn.commit()
            finally:
                _conn.close()
        except Exception:
            pass
    threading.Thread(target=_run_migrations, daemon=True, name="migrations").start()

    @app.get("/", response_class=HTMLResponse)
    def index():
        return INDEX_HTML

    _FILE_MIME = {
        # Images
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".heic": "image/heic", ".heif": "image/heif",
        ".tif": "image/tiff", ".tiff": "image/tiff",
        ".webp": "image/webp",
        # Documents
        ".pdf": "application/pdf",
        # Text — explicit UTF-8 so the browser actually renders them
        # instead of prompting to download.
        ".md": "text/plain; charset=utf-8",
        ".markdown": "text/plain; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".log": "text/plain; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".csv": "text/csv; charset=utf-8",
    }

    @app.get("/api/file")
    def api_file(source_id: str = Query(..., min_length=1)):
        """Stream a file that was previously indexed by Bunshin.

        Only paths registered in the records table are served — we look
        up the source_id first, then resolve to disk. This stops the
        endpoint from acting as an arbitrary file reader."""
        conn = init_db(db_path)
        try:
            cur = conn.execute(
                "SELECT source_id, source FROM records "
                "WHERE source_id = ? AND source IN ('photo', 'file') LIMIT 1",
                (source_id,),
            )
            row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="この記録はインデックスされていません")
        path = Path(row[0])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="ファイルがディスク上に見つかりません")
        mime = _FILE_MIME.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(str(path), media_type=mime)

    @app.get("/api/backups")
    def api_backups_list():
        from bunshin.backup import list_backups
        return {"backups": list_backups()}

    @app.post("/api/backups")
    def api_backup_create():
        from bunshin.backup import backup_db
        return backup_db(db_path)

    class BackupRestoreReq(BaseModel):
        path: str

    @app.post("/api/backups/restore")
    def api_backup_restore(req: BackupRestoreReq):
        from bunshin.backup import restore_backup
        res = restore_backup(db_path, Path(req.path))
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail=res.get("error", "バックアップの復元に失敗しました"))
        return res

    @app.delete("/api/records/{record_id}")
    def api_record_delete(record_id: str):
        """Forget a record permanently.

        Wipes the row from `records`, drops the matching vec entry, and
        removes any chat-context references so the deleted memory is
        gone from search, chat, and insights.
        """
        from bunshin.storage import load_vec_extension
        conn = init_db(db_path)
        try:
            load_vec_extension(conn)
            cur = conn.execute(
                "SELECT id FROM records WHERE id = ?", (record_id,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="該当する記録が見つかりません")
            try:
                conn.execute(
                    "DELETE FROM records_vec WHERE record_id = ?", (record_id,)
                )
            except Exception:
                pass
            conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
            conn.commit()
            return {"ok": True, "deleted": record_id}
        finally:
            conn.close()

    @app.get("/api/export/json")
    def api_export_json(
        include_browser: bool = Query(
            False,
            description="Include browser history records. Default False since "
                        "passive browsing (YouTube/SNS URLs) is rarely useful "
                        "in an export and can leak embarrassing private content.",
        ),
    ):
        """Stream every record as newline-delimited JSON so users can
        keep a copy of their memory in a portable, human-readable form.

        Defaults to excluding the 'browser' source — power user reviewer
        flagged it as a privacy risk when sharing exports.
        """
        def emit():
            conn = init_db(db_path)
            try:
                where = "" if include_browser else "WHERE source != 'browser'"
                cur = conn.execute(
                    f"SELECT id, source, source_id, timestamp, content, metadata "
                    f"FROM records {where} ORDER BY timestamp ASC"
                )
                for row in cur:
                    rec = {
                        "id": row[0],
                        "source": row[1],
                        "source_id": row[2],
                        "timestamp": row[3],
                        "content": row[4],
                        "metadata": json.loads(row[5]) if row[5] else None,
                    }
                    yield json.dumps(rec, ensure_ascii=False) + "\n"
            finally:
                conn.close()
        from datetime import datetime as _dt
        suffix = "-with-browser" if include_browser else ""
        fname = f"bunshin-export{suffix}-{_dt.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
        return StreamingResponse(
            emit(),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )

    @app.get("/api/export/sqlite")
    def api_export_sqlite():
        """Hand back the entire SQLite database as a single file.

        Snapshots via VACUUM INTO so the live DB isn't locked even
        during long-running queries.
        """
        import tempfile
        from datetime import datetime as _dt
        snap_path = Path(tempfile.gettempdir()) / f"bunshin-snap-{int(_dt.now().timestamp())}.db"
        conn = init_db(db_path)
        try:
            conn.execute(f"VACUUM INTO '{snap_path}'")
        finally:
            conn.close()
        fname = f"bunshin-{_dt.now().strftime('%Y%m%d-%H%M%S')}.db"
        return FileResponse(
            str(snap_path),
            media_type="application/octet-stream",
            filename=fname,
        )

    @app.get("/api/ollama/models")
    def api_ollama_models():
        """Return the list of locally installed Ollama models (if any)."""
        from bunshin.chat import check_ollama, pick_model
        ok, available = check_ollama()
        if not ok:
            return {"ok": False, "models": [], "default": None, "error": "Ollama が起動していません"}
        return {
            "ok": True,
            "models": available,
            "default": pick_model(available),
        }

    @app.get("/api/ollama/status")
    def api_ollama_status():
        """Return 4-state Ollama readiness for onboarding UI.

        States: not_installed, not_running, no_models, ready.
        Used by the chat tab to render a contextual help banner when chat
        cannot work, with a one-click resolution path for each state.
        """
        from bunshin.chat import check_ollama_status
        return check_ollama_status()

    @app.post("/api/ollama/launch")
    def api_ollama_launch():
        """Try to launch Ollama.app on macOS so the user doesn't have to
        hunt for it in /Applications. No-op on other platforms."""
        import subprocess
        from bunshin.chat import detect_ollama_app
        app_path = detect_ollama_app()
        if not app_path:
            return JSONResponse(
                {"ok": False, "error": "Ollama アプリが見つかりません"}, status_code=404
            )
        try:
            subprocess.Popen(["open", "-a", app_path])
        except OSError as e:
            return JSONResponse(
                {"ok": False, **friendly_error(e, fallback="Ollama の起動に失敗しました")},
                status_code=500,
            )
        return {"ok": True, "launched": app_path}

    @app.post("/api/ollama/pull")
    async def api_ollama_pull(model: str = "qwen2.5:3b"):
        """Stream `ollama pull <model>` output line by line as NDJSON.

        The frontend uses the stream to show download progress (e.g. "pulling
        manifest", "downloading 1.2 GB"). Final line is {"done": true, "code": N}.
        """
        import asyncio
        import json as _json
        from bunshin.chat import detect_ollama_binary

        binary = detect_ollama_binary()
        if not binary:
            return JSONResponse(
                {"ok": False, "error": "Ollama がインストールされていません"},
                status_code=400,
            )

        async def stream():
            proc = await asyncio.create_subprocess_exec(
                binary,
                "pull",
                model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert proc.stdout is not None
            while True:
                chunk = await proc.stdout.readline()
                if not chunk:
                    break
                line = chunk.decode("utf-8", errors="replace").rstrip()
                if line:
                    yield _json.dumps({"line": line}, ensure_ascii=False) + "\n"
            rc = await proc.wait()
            yield _json.dumps({"done": True, "code": rc, "model": model}) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/api/upload-image")
    async def api_upload_image(image: UploadFile = File(...)):
        """Save the uploaded image into the user's photo store and run it
        through Vision OCR. The recovered text is inserted as a record so
        future chat / search queries can reach it.
        """
        import shutil
        import tempfile
        from datetime import datetime as _dt
        from bunshin.ingestion.photos import (
            ensure_ocr_binary,
            extract_exif,
            ocr_batch,
        )
        from bunshin.storage import insert_record, load_vec_extension

        # Persist into ~/.bunshin/uploads/ so the record's file_path is stable.
        dest_dir = Path.home() / ".bunshin" / "uploads"
        dest_dir.mkdir(parents=True, exist_ok=True)
        ext = Path(image.filename or "upload.jpg").suffix.lower() or ".jpg"
        ts = _dt.now().strftime("%Y%m%d-%H%M%S")
        dest = dest_dir / f"upload-{ts}{ext}"
        with dest.open("wb") as out:
            shutil.copyfileobj(image.file, out)

        ensure_ocr_binary()  # build once, no-op afterwards
        ocr_results = ocr_batch([dest])
        ocr_text = ocr_results.get(str(dest), "") or ""
        exif = extract_exif(dest)
        item_ts = exif.get("date") or int(dest.stat().st_mtime)

        header_parts = ["[photo]", _dt.fromtimestamp(item_ts).strftime("%Y-%m-%d")]
        if exif.get("gps"):
            g = exif["gps"]
            header_parts.append(f"({g['lat']:.4f},{g['lon']:.4f})")
        if exif.get("camera"):
            header_parts.append(exif["camera"])
        header_parts.append(dest.name)
        header = " ".join(p for p in header_parts if p)

        body = ocr_text or "(no text recognized)"
        content = f"{header}\n{body}".strip()

        conn = init_db(db_path)
        try:
            load_vec_extension(conn)
            rid = insert_record(
                conn,
                source="photo",
                timestamp=item_ts,
                content=content,
                source_id=str(dest),
                metadata={
                    "path": str(dest),
                    "name": dest.name,
                    "date": exif.get("date"),
                    "gps": exif.get("gps"),
                    "camera": exif.get("camera"),
                    "ocr_chars": len(ocr_text),
                    "uploaded_via": "chat",
                },
                file_path=str(dest),
            )
        finally:
            conn.close()

        return {
            "record_id": rid,
            "saved_to": str(dest),
            "ocr_chars": len(ocr_text),
            "ocr_preview": ocr_text[:300],
            "exif": exif,
        }

    @app.get("/api/status")
    def api_status():
        from bunshin.settings import get as get_setting
        conn = init_db(db_path)
        try:
            init_vector_db(conn)
            try:
                ent = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            except sqlite3.OperationalError:
                ent = 0
            try:
                row = conn.execute(
                    "SELECT MIN(timestamp) FROM records WHERE timestamp IS NOT NULL"
                ).fetchone()
                oldest = int(row[0]) if row and row[0] is not None else None
            except sqlite3.OperationalError:
                oldest = None
            min_signal = int(get_setting(conn, "min_signal_score") or 0)
            auto_filtered = 0
            if min_signal > 0:
                auto_filtered = conn.execute(
                    """SELECT COUNT(*) FROM records
                        WHERE COALESCE(signal_score, 50.0) <= ?
                          AND COALESCE(user_signal, 0) != 1""",
                    (min_signal,),
                ).fetchone()[0]
            return {
                "total_records": count_records(conn),
                "total_embeddings": count_vectors(conn),
                "total_entities": ent,
                "oldest_ts": oldest,
                "sources": dict(list_sources_with_counts(conn)),
                "hidden_count": hidden_count(conn),
                "auto_filtered_count": auto_filtered,
                "min_signal_score": min_signal,
            }
        finally:
            conn.close()

    # ───── Learning / noise-filter API ──────────────────────────────────
    @app.post("/api/mark")
    def api_mark(payload: dict):
        """payload = {record_id, action: 'hide'|'star', scope: 'record'|'sender'|'domain'}"""
        rid = payload.get("record_id")
        action = payload.get("action")
        scope = payload.get("scope", "record")
        if not rid or action not in ("hide", "star"):
            raise HTTPException(status_code=400, detail="record_id + action required")
        if scope not in ("record", "sender", "domain"):
            scope = "record"
        conn = init_db(db_path)
        try:
            return apply_mark(conn, rid, action, scope)
        finally:
            conn.close()

    @app.post("/api/mark/undo")
    def api_mark_undo(payload: dict):
        """payload = {record_id} OR {rule_id}"""
        rid = payload.get("record_id")
        rule_id = payload.get("rule_id")
        conn = init_db(db_path)
        try:
            if rule_id is not None:
                return undo_rule(conn, int(rule_id))
            if rid:
                return undo_record_mark(conn, rid)
            raise HTTPException(status_code=400, detail="record_id or rule_id required")
        finally:
            conn.close()

    @app.get("/api/learning/rules")
    def api_learning_rules():
        conn = init_db(db_path)
        try:
            return {"rules": list_learning_rules(conn)}
        finally:
            conn.close()

    @app.post("/api/learning/reset")
    def api_learning_reset():
        conn = init_db(db_path)
        try:
            return reset_learning(conn)
        finally:
            conn.close()

    # ───── Privacy status (transparency for the user) ──────────────────────
    @app.get("/api/privacy/status")
    def api_privacy_status():
        """A snapshot of where the user's data lives and what's connected.

        Bunshin's whole promise is "this data stays on your Mac". This
        endpoint surfaces the evidence: paths, file sizes, what local
        services are talking to us, what (if anything) leaves the box.
        """
        import os as _os
        out = {
            "db_path": str(db_path),
            "db_bytes": 0,
            "data_dir": str(Path.home() / ".bunshin"),
            "data_dir_bytes": 0,
            "ollama_running": False,
            "gmail_configured": False,
            "calendar_configured": False,
            "outbound_destinations": [],
        }
        try:
            out["db_bytes"] = db_path.stat().st_size if db_path.exists() else 0
        except OSError:
            pass
        try:
            data_dir = Path.home() / ".bunshin"
            total = 0
            for dirpath, _, filenames in _os.walk(data_dir):
                for f in filenames:
                    try:
                        total += (Path(dirpath) / f).stat().st_size
                    except OSError:
                        pass
            out["data_dir_bytes"] = total
        except OSError:
            pass
        # Ollama presence check — quick local probe.
        try:
            import urllib.request as _req
            _req.urlopen("http://127.0.0.1:11434/api/version", timeout=0.5).read()
            out["ollama_running"] = True
        except Exception:
            pass
        out["gmail_configured"] = (Path.home() / ".bunshin" / "gmail.json").exists()
        out["calendar_configured"] = (Path.home() / ".bunshin" / "calendar.json").exists()
        # The only external destinations Bunshin contacts are user-configured.
        # IMAP for Gmail (when set up), and Google Calendar's iCal URL (if set up).
        # Nothing is sent — all reads. List them explicitly so the user can audit.
        if out["gmail_configured"]:
            out["outbound_destinations"].append({
                "host": "imap.gmail.com",
                "purpose": "Gmail メール読み取り（あなたの App Password、読み取り専用）",
                "direction": "read-only",
            })
        if out["calendar_configured"]:
            out["outbound_destinations"].append({
                "host": "calendar.google.com",
                "purpose": "Google Calendar 予定読み取り（あなたの iCal URL、読み取り専用）",
                "direction": "read-only",
            })
        return out

    # ───── Auto-import scheduler (launchd / systemd / cron) ────────────────
    @app.get("/api/calendar/status")
    def api_calendar_status():
        """Return the saved iCal URL (if any) + the current event count."""
        from bunshin.ingestion.calendar import load_url
        url = load_url()
        count = 0
        try:
            _conn = init_db(db_path)
            try:
                row = _conn.execute(
                    "SELECT COUNT(*) FROM records WHERE source = 'calendar'"
                ).fetchone()
                count = row[0] if row else 0
            finally:
                _conn.close()
        except Exception:
            pass
        return {"url": url, "event_count": count}

    class CalendarSetupReq(BaseModel):
        url: str

    @app.post("/api/calendar/setup")
    def api_calendar_setup(req: CalendarSetupReq):
        """Save iCal URL then immediately import. Returns import stats."""
        from bunshin.ingestion.calendar import save_url, import_calendar
        url = (req.url or "").strip()
        if not url or not url.startswith(("http://", "https://", "webcal://")):
            return JSONResponse(
                {
                    "ok": False,
                    "error": "iCal の URL を入力してください",
                    "hint": "http:// / https:// / webcal:// で始まる URL",
                },
                status_code=400,
            )
        # webcal:// → https:// (most calendar feeds accept either).
        if url.startswith("webcal://"):
            url = "https://" + url[len("webcal://") :]
        save_url(url)
        conn = init_db(db_path)
        try:
            stats = import_calendar(conn, url=url)
        finally:
            conn.close()
        if stats.get("error_msg"):
            return JSONResponse(
                {"ok": False, "error": stats["error_msg"]}, status_code=502
            )
        return {"ok": True, **stats}

    @app.post("/api/calendar/import")
    def api_calendar_reimport():
        """Re-fetch and re-import using the saved URL."""
        from bunshin.ingestion.calendar import load_url, import_calendar
        url = load_url()
        if not url:
            return JSONResponse(
                {"ok": False, "error": "iCal URL が登録されていません"},
                status_code=400,
            )
        conn = init_db(db_path)
        try:
            stats = import_calendar(conn, url=url)
        finally:
            conn.close()
        if stats.get("error_msg"):
            return JSONResponse(
                {"ok": False, "error": stats["error_msg"]}, status_code=502
            )
        return {"ok": True, **stats}

    @app.post("/api/calendar/remove")
    def api_calendar_remove():
        """Forget the saved URL and wipe all calendar records."""
        from bunshin.ingestion.calendar import CONFIG_PATH
        try:
            if CONFIG_PATH.exists():
                CONFIG_PATH.unlink()
        except OSError:
            pass
        conn = init_db(db_path)
        try:
            cur = conn.execute("SELECT id FROM records WHERE source = 'calendar'")
            ids = [r[0] for r in cur.fetchall()]
            if ids:
                placeholders = ",".join(["?"] * len(ids))
                try:
                    conn.execute(
                        f"DELETE FROM records_vec WHERE record_id IN ({placeholders})",
                        ids,
                    )
                except sqlite3.OperationalError:
                    pass
                conn.execute(
                    f"DELETE FROM records WHERE id IN ({placeholders})", ids
                )
                conn.commit()
        finally:
            conn.close()
        return {"ok": True, "removed": len(ids)}

    @app.get("/api/diagnostics")
    def api_diagnostics():
        """Aggregate everything a maintainer needs to debug a stuck install:
        OS, versions, Ollama 4-state, DB stats, last 100 lines of update logs.
        Deliberately omits user records, file contents, and email bodies.
        """
        import platform as _platform
        from bunshin.chat import check_ollama_status as _check_status

        bunshin_version = "unknown"
        try:
            from importlib.metadata import version as _pkg_version
            bunshin_version = _pkg_version("bunshin")
        except Exception:
            # PyInstaller bundle has no .dist-info — fall back to __version__.
            try:
                from bunshin import __version__ as bunshin_version  # type: ignore
            except Exception:
                pass

        log_dir = Path.home() / ".bunshin" / "logs"
        logs = {}
        for name in ("update.out.log", "update.err.log"):
            p = log_dir / name
            if p.exists():
                try:
                    with p.open() as f:
                        lines = f.readlines()[-100:]
                    logs[name] = "".join(lines)
                except Exception:
                    logs[name] = "(読み込みエラー)"

        db_size = db_path.stat().st_size if db_path.exists() else 0
        record_count = -1
        try:
            _conn = init_db(db_path)
            try:
                row = _conn.execute("SELECT COUNT(*) FROM records").fetchone()
                record_count = row[0] if row else -1
            finally:
                _conn.close()
        except Exception:
            pass

        # Embedding health probe — the most common silent failure is
        # fastembed cache corruption (model.onnx_data partial download).
        embedding_health = {"ok": False, "error": None, "vec_count": 0, "needs_rebuild": False}
        try:
            from bunshin.embeddings import embed_query
            v = embed_query("ヘルスチェック")
            embedding_health["ok"] = bool(v) and len(v) > 0
            embedding_health["dim"] = len(v) if v else 0
        except Exception as _e:
            embedding_health["error"] = str(_e)[:200]

        # Vector chunk count vs records — if drastically off, search is dead.
        try:
            _conn = init_db(db_path)
            try:
                from bunshin.storage import load_vec_extension
                load_vec_extension(_conn)
                row = _conn.execute("SELECT COUNT(*) FROM records_vec").fetchone()
                embedding_health["vec_count"] = row[0] if row else 0
                if record_count > 0 and embedding_health["vec_count"] < record_count * 0.1:
                    embedding_health["needs_rebuild"] = True
            finally:
                _conn.close()
        except Exception:
            pass

        return {
            "bunshin_version": bunshin_version,
            "os": {
                "platform": _platform.platform(),
                "python": _platform.python_version(),
                "machine": _platform.machine(),
            },
            "ollama": _check_status(),
            "embedding": embedding_health,
            "db": {
                "path": str(db_path),
                "size_bytes": db_size,
                "size_mb": round(db_size / 1024 / 1024, 2),
                "record_count": record_count,
            },
            "logs": logs,
        }

    @app.post("/api/embedding/rebuild")
    def api_embedding_rebuild():
        """Wipe the vector table and re-embed every record. Long-running.

        Called from the troubleshoot panel when the search index is broken.
        Streams progress so the UI can show a progress bar.
        """
        import asyncio, json as _json
        from bunshin.embeddings import DIMENSIONS, embed_passages
        from bunshin.storage import (
            detect_vec_dimensions,
            drop_vector_db,
            get_records_without_vectors,
            init_vector_db,
            insert_vector,
        )

        def stream():
            conn = init_db(db_path)
            try:
                # Drop & recreate to guarantee clean state.
                existing_dim = detect_vec_dimensions(conn)
                if existing_dim is not None:
                    drop_vector_db(conn)
                init_vector_db(conn, dimensions=DIMENSIONS)
                pending = [
                    (rid, text) for rid, text in get_records_without_vectors(conn)
                    if len(text or "") >= 20
                ]
                total = len(pending)
                yield _json.dumps({"phase": "start", "total": total}) + "\n"
                batch_size = 16
                done = 0
                for i in range(0, total, batch_size):
                    batch = pending[i : i + batch_size]
                    texts = [t for _, t in batch]
                    try:
                        embeddings = list(embed_passages(texts))
                        for (rid, _), emb in zip(batch, embeddings):
                            insert_vector(conn, rid, emb)
                        conn.commit()
                    except Exception as e:
                        yield _json.dumps({"phase": "error", "error": str(e)[:200]}) + "\n"
                        return
                    done += len(batch)
                    yield _json.dumps({"phase": "progress", "done": done, "total": total}) + "\n"
                yield _json.dumps({"phase": "done", "total": total}) + "\n"
            finally:
                conn.close()

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.get("/api/scheduler/status")
    def api_scheduler_status():
        from bunshin.scheduler import scheduler_status
        try:
            return scheduler_status()
        except Exception as e:
            return {"installed": False, **friendly_error(e, fallback="スケジューラの状態を取得できませんでした")}

    @app.post("/api/scheduler/install")
    def api_scheduler_install():
        from bunshin.scheduler import install_scheduler
        try:
            ok, msg = install_scheduler()
            return {"ok": ok, "message": msg}
        except Exception as e:
            return {"ok": False, "message": friendly_error(e, fallback="自動取り込みの設定に失敗しました")["error"]}

    @app.post("/api/scheduler/uninstall")
    def api_scheduler_uninstall():
        from bunshin.scheduler import uninstall_scheduler
        try:
            ok, msg = uninstall_scheduler()
            return {"ok": ok, "message": msg}
        except Exception as e:
            return {"ok": False, "message": friendly_error(e, fallback="自動取り込みの解除に失敗しました")["error"]}

    @app.post("/api/scheduler/run-now")
    def api_scheduler_run_now():
        """Trigger one immediate update — useful for testing."""
        from bunshin.scheduler import get_bunshin_binary
        import subprocess as _sub
        try:
            # Fire-and-forget; output is appended to ~/.bunshin/logs/update.out.log
            _sub.Popen(
                [get_bunshin_binary(), "update", "--quiet"],
                stdout=_sub.DEVNULL, stderr=_sub.DEVNULL,
            )
            return {"ok": True, "message": "更新をバックグラウンドで開始しました"}
        except Exception as e:
            return {"ok": False, "message": friendly_error(e, fallback="更新の起動に失敗しました")["error"]}

    @app.get("/api/system/recommend-model")
    def api_recommend_model():
        """Detect this Mac's RAM and recommend an Ollama model that fits.

        Rule of thumb for quantized Q4 models:
          - llama3.2:1b   needs ~ 1.5 GB free
          - llama3.2:3b   needs ~  3  GB free
          - qwen2.5:7b    needs ~  6  GB free
          - qwen2.5:14b   needs ~ 12  GB free
          - qwen2.5:32b   needs ~ 22  GB free
          - qwen2.5:72b   needs ~ 48  GB free
        We recommend the largest model the user's RAM can comfortably run
        (roughly half the total RAM, leaving headroom for the OS + apps).
        """
        # ---- RAM detection (macOS only, falls back to 0 on other OSes) ----
        ram_gb = 0
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=2)
            ram_gb = int(out.strip()) // (1024 ** 3)
        except Exception:
            try:
                # Fallback for non-macOS Unix.
                import os as _os
                ram_gb = _os.sysconf("SC_PAGE_SIZE") * _os.sysconf("SC_PHYS_PAGES") // (1024 ** 3)
            except Exception:
                ram_gb = 0

        # ---- Installed Ollama models ----
        installed: list[str] = []
        try:
            out = subprocess.check_output(["ollama", "list"], timeout=5, text=True)
            for line in out.splitlines()[1:]:
                parts = line.split()
                if parts:
                    installed.append(parts[0])
        except Exception:
            pass

        # ---- Ladder: (min_ram_gb, model, headline, why) ----
        ladder = [
            (1,  "llama3.2:1b",  "省メモリ機向け",       "小さいけど日本語もそこそこ"),
            (6,  "llama3.2:3b",  "軽快に動作",          "ちょっとした質問に十分"),
            (12, "qwen2.5:7b",   "バランス重視",        "日常使いの推奨ライン"),
            (20, "qwen2.5:14b",  "賢めの回答",          "複雑な指示も追える"),
            (28, "qwen2.5:32b",  "高品質",             "Claude / GPT-4 に迫る品質"),
            (56, "qwen2.5:72b",  "最高品質",           "ローカルで動く最高峰"),
        ]
        best = ladder[0]
        for tier in ladder:
            if ram_gb >= tier[0]:
                best = tier

        return {
            "ram_gb": ram_gb,
            "recommended": best[1],
            "recommended_headline": best[2],
            "recommended_why": best[3],
            "installed": installed,
            "is_installed": best[1] in installed,
            "ladder": [
                {"min_ram_gb": t[0], "model": t[1], "headline": t[2], "why": t[3]}
                for t in ladder
            ],
        }

    @app.get("/api/flashback")
    def api_flashback():
        """Records the user wrote on this calendar day in the past.

        The three retrospective windows adapt to how far back the user's
        DB actually goes. We never show a window for a date earlier than
        the oldest record — that would always be empty and tell the user
        "Bunshin doesn't know you" instead of "here's what you forgot".
        """
        from bunshin.signals import (
            URL_RE,
            clean_for_display as _clean,
            is_readable as _is_readable,
        )
        import re as _re

        def _readable_score(content: str) -> float:
            if not content:
                return -1e9
            sample = content[:600]
            n = len(sample)
            cjk = sum(
                1 for c in sample
                if '぀' <= c <= 'ヿ' or '一' <= c <= '鿿'
            )
            cjk_ratio = cjk / n
            url_count = len(URL_RE.findall(sample))
            # A run of non-space characters longer than 32 is almost always
            # a URL, hash, or encoded header — penalize.
            long_tokens = sum(1 for t in sample.split() if len(t) > 32)
            # Mail header fingerprints
            header_hits = sum(
                sample.count(h) for h in
                ("Subject:", "From:", "To:", "Content-Type:", "=?UTF-8?", "X-Google-")
            )
            return (
                cjk_ratio * 100
                - url_count * 8
                - long_tokens * 12
                - header_hits * 6
                + min(n, 200) * 0.05  # mild preference for non-trivial length
            )

        conn = init_db(db_path)
        try:
            now = datetime.datetime.now()
            # Pick three retrospective offsets that the user's DB can
            # actually populate. Falls back gracefully as the DB grows.
            try:
                row = conn.execute(
                    "SELECT MIN(timestamp) FROM records WHERE timestamp IS NOT NULL"
                ).fetchone()
                oldest_ts = int(row[0]) if row and row[0] else None
            except sqlite3.OperationalError:
                oldest_ts = None
            days_of_data = (
                int((now.timestamp() - oldest_ts) / 86400)
                if oldest_ts else 0
            )
            # Candidate windows, ordered shortest → longest.
            candidates = [
                ("week",    7,   "先週の今日"),
                ("fortnight", 14, "2 週間前の今日"),
                ("month",   30,  "1 ヶ月前の今日"),
                ("twomon",  60,  "2 ヶ月前の今日"),
                ("quarter", 90,  "3 ヶ月前の今日"),
                ("half",    180, "半年前の今日"),
                ("year",    365, "1 年前の今日"),
                ("twoyear", 730, "2 年前の今日"),
                ("fiveyear", 1825, "5 年前の今日"),
            ]
            usable = [c for c in candidates if c[1] <= days_of_data]
            # Always include "先週" if the DB is at least a week old.
            if not usable:
                usable = [candidates[0]] if days_of_data >= 7 else []
            # Pick 3 spread across the available span: nearest, mid, farthest.
            if len(usable) <= 3:
                windows = usable
            else:
                n = len(usable)
                windows = [usable[0], usable[n // 2], usable[-1]]
            out = []
            for label, days_back, ja in windows:
                target = now - datetime.timedelta(days=days_back)
                start = datetime.datetime(target.year, target.month, target.day)
                end = start + datetime.timedelta(days=1)
                start_ts, end_ts = int(start.timestamp()), int(end.timestamp())
                try:
                    from bunshin.settings import get as get_setting
                    min_signal = int(get_setting(conn, "min_signal_score") or 0)
                    rows = conn.execute(
                        """SELECT id, source, timestamp, content,
                                  COALESCE(signal_score, 50.0) AS sig
                             FROM records
                            WHERE timestamp >= ? AND timestamp < ?
                              AND LENGTH(content) >= 30
                              AND COALESCE(user_signal, 0) != 1
                              AND COALESCE(signal_score, 50.0) > ?""",
                        (start_ts, end_ts, min_signal),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
                # Drop records that turn out to be unreadable after cleaning.
                rows = [r for r in rows if _is_readable(r[3] or "")]
                scored = sorted(
                    rows,
                    key=lambda r: (r[4], _readable_score(r[3] or "")),
                    reverse=True,
                )
                # Diversify across sources for the top 3 cards.
                seen, picks = set(), []
                for r in scored:
                    if r[1] not in seen:
                        seen.add(r[1])
                        picks.append(r)
                    if len(picks) >= 3:
                        break
                for r in scored:
                    if len(picks) >= 3:
                        break
                    if r not in picks:
                        picks.append(r)
                # Fetch sender info for the picks so the UI can offer
                # "hide this sender / domain" without an extra round trip.
                items = []
                for r in picks:
                    sender_row = conn.execute(
                        "SELECT sender, sender_domain FROM records WHERE id=?",
                        (r[0],),
                    ).fetchone()
                    sender = sender_row[0] if sender_row else None
                    domain = sender_row[1] if sender_row else None
                    cleaned = _clean(r[3] or "")[:220]
                    items.append({
                        "id": r[0],
                        "source": r[1],
                        "timestamp": r[2],
                        "content": cleaned,
                        "sender": sender,
                        "domain": domain,
                    })
                out.append({
                    "label": label,
                    "label_ja": ja,
                    "date": start.strftime("%Y-%m-%d"),
                    "weekday": "月火水木金土日"[start.weekday()],
                    "items": items,
                    "total_count": len(rows),
                })
            return {"windows": out}
        finally:
            conn.close()

    @app.get("/api/records")
    def api_records(
        from_ts: Optional[int] = Query(None, alias="from"),
        to_ts: Optional[int] = Query(None, alias="to"),
        limit: int = Query(50, ge=1, le=200),
        include_hidden: bool = Query(False),
        include_auto_filtered: bool = Query(False),
    ):
        """Plain time-range listing of records.

        Each row's content is cleaned (URLs / tracking blobs / mail
        headers stripped); rows that turn out to be unreadable after
        cleaning are skipped — we keep fetching until `limit` readable
        rows are gathered or the underlying query is exhausted.
        """
        from bunshin.signals import clean_for_display as _clean, is_readable as _is_readable
        from bunshin.settings import get as get_setting
        conn = init_db(db_path)
        try:
            min_signal = int(get_setting(conn, "min_signal_score") or 0)
            clauses = ["LENGTH(content) >= 20"]
            params: list = []
            if not include_hidden:
                clauses.append("COALESCE(user_signal, 0) != 1")
            if not include_auto_filtered and min_signal > 0:
                clauses.append("COALESCE(signal_score, 50.0) > ?")
                params.append(min_signal)
            if from_ts is not None:
                clauses.append("timestamp >= ?")
                params.append(from_ts)
            if to_ts is not None:
                clauses.append("timestamp < ?")
                params.append(to_ts)
            # Over-fetch — many rows will be pure-noise after cleaning.
            params.append(limit * 4)
            rows = conn.execute(
                f"""SELECT id, source, timestamp, content,
                          COALESCE(signal_score, 50.0) AS sig,
                          COALESCE(user_signal, 0) AS us,
                          sender
                      FROM records
                     WHERE {' AND '.join(clauses)}
                     ORDER BY COALESCE(signal_score, 50.0) DESC, timestamp DESC
                     LIMIT ?""",
                params,
            ).fetchall()
            results = []
            for r in rows:
                if not _is_readable(r[3] or ""):
                    continue
                results.append({
                    "id": r[0],
                    "source": r[1],
                    "timestamp": r[2],
                    "content": _clean(r[3] or ""),
                    "signal_score": r[4],
                    "user_signal": r[5],
                    "sender": r[6],
                })
                if len(results) >= limit:
                    break
            return {"results": results}
        finally:
            conn.close()

    @app.get("/api/search")
    def api_search(
        q: str = Query(..., min_length=1),
        limit: int = Query(10, ge=1, le=50),
        min_chars: int = Query(20, ge=0, le=1000),
        sort: str = Query("relevance", pattern="^(relevance|newest|oldest)$"),
        from_ts: Optional[int] = Query(None, alias="from"),
        to_ts: Optional[int] = Query(None, alias="to"),
        max_per_source: int = Query(1, ge=0, le=20),
        mode: str = Query("hybrid", pattern="^(vector|hybrid)$"),
        sources: Optional[str] = Query(None, description="Comma-separated source filter"),
        rerank: bool = Query(True, description="Cross-encoder rerank pass"),
        expand: bool = Query(False, description="LLM query expansion"),
    ):
        conn = init_db(db_path)
        try:
            source_list = [s.strip() for s in sources.split(",")] if sources else None
            results = search(
                conn, q, limit=limit, min_content_length=min_chars,
                sort=sort, from_ts=from_ts, to_ts=to_ts,
                max_per_source=max_per_source,
                mode=mode,
                sources=source_list,
                rerank=rerank,
                expand=expand,
            )
            return {"query": q, "count": len(results), "results": results}
        finally:
            conn.close()

    @app.get("/api/search/siblings")
    def api_search_siblings(
        q: str = Query(..., min_length=1),
        source_id: str = Query(..., min_length=1),
        limit: int = Query(20, ge=1, le=100),
        min_chars: int = Query(20),
        mode: str = Query("hybrid", pattern="^(vector|hybrid)$"),
    ):
        """Return all results matching `q` that share `source_id` —
        i.e. the chunks hidden behind the "📚 N more" badge."""
        conn = init_db(db_path)
        try:
            results = search(
                conn, q,
                limit=max(limit * 4, 60),
                min_content_length=min_chars,
                mode=mode,
                max_per_source=0,
            )
            siblings = [r for r in results if r["source_id"] == source_id]
            return {"source_id": source_id, "count": len(siblings), "results": siblings[:limit]}
        finally:
            conn.close()

    @app.get("/api/timeline")
    def api_timeline(days: int = Query(30, ge=1, le=3650)):
        """Aggregate records per local-day, per source, for the last N days."""
        from datetime import datetime as _dt
        conn = init_db(db_path)
        try:
            now = int(_dt.now().timestamp())
            threshold = now - days * 86400
            cursor = conn.execute(
                """SELECT
                    date(timestamp, 'unixepoch', 'localtime') AS day,
                    source,
                    COUNT(*) AS cnt
                   FROM records
                   WHERE timestamp >= ? AND length(content) >= 20
                   GROUP BY day, source
                   ORDER BY day DESC, cnt DESC""",
                (threshold,),
            )
            by_day: dict = {}
            for day, source, cnt in cursor.fetchall():
                if day not in by_day:
                    by_day[day] = {"date": day, "sources": {}, "total": 0}
                by_day[day]["sources"][source] = cnt
                by_day[day]["total"] += cnt
            days_list = sorted(by_day.values(), key=lambda x: x["date"], reverse=True)
            return {"days": days_list, "range_days": days}
        finally:
            conn.close()

    @app.get("/api/timeline/day")
    def api_timeline_day(
        date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
        source: Optional[str] = Query(None),
        limit: int = Query(50, ge=1, le=200),
    ):
        """List records for a specific local-date (YYYY-MM-DD)."""
        conn = init_db(db_path)
        try:
            sql = (
                "SELECT id, source, source_id, timestamp, content, metadata "
                "FROM records "
                "WHERE date(timestamp, 'unixepoch', 'localtime') = ? "
                "AND length(content) >= 20"
            )
            params: list = [date]
            if source:
                sql += " AND source = ?"
                params.append(source)
            sql += " ORDER BY timestamp ASC LIMIT ?"
            params.append(limit)
            cursor = conn.execute(sql, params)
            rows = [
                {
                    "id": r[0],
                    "source": r[1],
                    "source_id": r[2],
                    "timestamp": r[3],
                    "content": r[4],
                    "metadata": json.loads(r[5]) if r[5] else {},
                }
                for r in cursor.fetchall()
            ]
            return {"date": date, "source": source, "count": len(rows), "results": rows}
        finally:
            conn.close()

    @app.get("/api/session")
    def api_session(source_id: str = Query(..., min_length=1)):
        conn = init_db(db_path)
        try:
            records = get_session_records(conn, source_id)
            return {"source_id": source_id, "count": len(records), "records": records}
        finally:
            conn.close()

    @app.get("/api/settings")
    def api_settings_get():
        from bunshin.settings import all_settings, settings_schema
        conn = init_db(db_path)
        try:
            return {"settings": all_settings(conn), "schema": settings_schema()}
        finally:
            conn.close()

    class SettingsUpdate(BaseModel):
        values: dict[str, Any]

    @app.put("/api/settings")
    def api_settings_put(req: SettingsUpdate):
        from bunshin.settings import all_settings, set_value, SCHEMA
        conn = init_db(db_path)
        try:
            updated = {}
            errors = {}
            for k, v in (req.values or {}).items():
                if k not in SCHEMA:
                    errors[k] = "unknown setting"
                    continue
                try:
                    set_value(conn, k, v)
                    updated[k] = v
                except Exception as e:
                    errors[k] = str(e)
            return {"updated": updated, "errors": errors, "settings": all_settings(conn)}
        finally:
            conn.close()

    @app.get("/api/entities")
    def api_entities():
        from bunshin.knowledge_graph import entity_with_counts, init_kg_schema
        conn = init_db(db_path)
        try:
            init_kg_schema(conn)
            entities = entity_with_counts(conn)
            return {"count": len(entities), "entities": entities}
        finally:
            conn.close()

    @app.get("/api/entities/{entity_id}")
    def api_entity_detail(entity_id: int):
        from bunshin.knowledge_graph import (
            entity_by_id,
            entity_records,
            entity_relations,
            init_kg_schema,
        )
        conn = init_db(db_path)
        try:
            init_kg_schema(conn)
            entity = entity_by_id(conn, entity_id)
            if not entity:
                return {"error": "Entity not found"}
            return {
                "entity": entity,
                "relations": entity_relations(conn, entity_id, limit=30),
                "records": entity_records(conn, entity_id, limit=10),
            }
        finally:
            conn.close()

    @app.get("/api/insights")
    def api_insights():
        from bunshin.insights import generate_insights
        conn = init_db(db_path)
        try:
            return generate_insights(conn)
        finally:
            conn.close()

    @app.get("/api/insights/digest")
    def api_insights_digest(days: int = Query(7, ge=1, le=90)):
        from bunshin.insights import generate_llm_digest
        conn = init_db(db_path)
        try:
            return generate_llm_digest(conn, days=days)
        finally:
            conn.close()

    class NoteRequest(BaseModel):
        content: str
        tags: list[str] = []

    @app.post("/api/note")
    def api_note(req: NoteRequest):
        from bunshin.embeddings import DIMENSIONS, embed_passages
        from bunshin.ingestion.manual import add_note
        from bunshin.storage import insert_vector

        conn = init_db(db_path)
        try:
            rid = add_note(conn, req.content, tags=req.tags)
            if not rid:
                return {"saved": False, "error": "Empty content"}
            if len(req.content) >= 20:
                init_vector_db(conn, dimensions=DIMENSIONS)
                for emb in embed_passages([req.content]):
                    insert_vector(conn, rid, emb)
                conn.commit()
            return {"saved": True, "record_id": rid}
        finally:
            conn.close()

    @app.get("/api/chat/sessions")
    def api_chat_sessions(q: Optional[str] = Query(None)):
        from bunshin.chat_history import list_sessions
        conn = init_db(db_path)
        try:
            return {"sessions": list_sessions(conn, query=q)}
        finally:
            conn.close()

    @app.get("/api/chat/sessions/{session_id}")
    def api_chat_session_detail(session_id: str):
        from bunshin.chat_history import get_messages, get_session
        conn = init_db(db_path)
        try:
            session = get_session(conn, session_id)
            if not session:
                return {"error": "session not found"}
            return {
                "session": session,
                "messages": get_messages(conn, session_id),
            }
        finally:
            conn.close()

    @app.delete("/api/chat/sessions/{session_id}")
    def api_chat_session_delete(session_id: str):
        from bunshin.chat_history import delete_session
        conn = init_db(db_path)
        try:
            n = delete_session(conn, session_id)
            return {"deleted_messages": n}
        finally:
            conn.close()

    @app.get("/api/chat")
    def api_chat(
        q: str = Query(..., min_length=1),
        model: Optional[str] = Query(None),
        context_limit: int = Query(5, ge=0, le=20),
        session_id: Optional[str] = Query(None),
    ):
        """Stream a chat response. Yields newline-delimited JSON:
            {"session_id": "..."} once at start (so the client can persist it)
            {"context": [...]} once at start
            {"delta": "..."} per chunk
            {"done": true} at end
            {"error": "..."} on failure
        """
        from bunshin.chat import (
            build_context,
            chat_ollama,
            check_ollama,
            pick_model,
        )
        from bunshin.chat_history import add_message, create_session, get_messages, get_session

        def event_stream():
            ok, available = check_ollama()
            if not ok:
                yield json.dumps({"error": "Ollama が起動していません。`ollama serve` で起動してください。"}, ensure_ascii=False) + "\n"
                return
            if not available:
                yield json.dumps({"error": "Ollama モデルが入っていません。`ollama pull qwen2.5:14b` 等で入れてください。"}, ensure_ascii=False) + "\n"
                return

            chosen = model or pick_model(available)
            if not chosen:
                yield json.dumps({"error": "モデルが選択できません"}, ensure_ascii=False) + "\n"
                return

            conn = init_db(db_path)
            try:
                # Session: create new if not supplied or not found
                sid = session_id
                history = []
                if sid:
                    sess = get_session(conn, sid)
                    if sess:
                        for m in get_messages(conn, sid):
                            history.append({"role": m["role"], "content": m["content"]})
                    else:
                        sid = None
                if not sid:
                    sid = create_session(conn, model=chosen)
                    # Auto-name the session from the first user message so
                    # the history sidebar doesn't fill up with "(empty)"
                    # entries. ChatGPT/Claude do this; users expect it.
                    try:
                        from bunshin.chat_history import update_session_title
                        first_line = q.strip().split("\n", 1)[0]
                        title = first_line[:40] + ("…" if len(first_line) > 40 else "")
                        if title:
                            update_session_title(conn, sid, title)
                    except Exception:
                        pass

                # Skip RAG for trivial greetings / pure chit-chat — the
                # reviewer reported that typing just "hello" caused the
                # assistant to dredge up five Claude Code sessions from
                # the past, which feels invasive. Heuristic: very short
                # messages OR exact greeting matches → no context.
                _CHITCHAT = {
                    "hello", "hi", "hey", "yo", "やあ", "ハロー", "ハーイ",
                    "おはよう", "おはようございます",
                    "こんにちは", "こんばんは",
                    "ありがとう", "ありがとうございます", "thx", "thanks", "thank you",
                    "おやすみ", "おやすみなさい",
                    "test", "テスト",
                }
                stripped = q.strip().lower().rstrip("。.!?！？")
                is_chitchat = (
                    len(stripped) <= 8 and stripped in _CHITCHAT
                ) or (
                    len(stripped) <= 3  # 「??」「うん」程度
                )

                # Augment the search query with the last 2 user turns so
                # pronouns ("で、それいくら？") resolve correctly.
                aug_q = q
                if history:
                    from bunshin.chat import _augment_query_with_history
                    aug_q = _augment_query_with_history(q, history)
                results = (
                    [] if is_chitchat
                    else (search(conn, aug_q, limit=context_limit) if context_limit > 0 else [])
                )

                # Emit session id + context for the client.
                yield json.dumps({"session_id": sid, "model": chosen}, ensure_ascii=False) + "\n"
                context_summary = [
                    {
                        "timestamp": r["timestamp"],
                        "source": r["source"],
                        "content": r["content"],
                        "distance": r["distance"],
                    }
                    for r in results
                ]
                yield json.dumps({"context": context_summary}, ensure_ascii=False) + "\n"

                # Save the user turn before generating, so it's persisted even if generation fails.
                add_message(conn, sid, "user", q, context_used=context_summary)

                # Build prompt context text with citation numbers.
                from datetime import datetime as _dt
                ctx_lines = []
                for i, r in enumerate(results, 1):
                    ts = _dt.fromtimestamp(r["timestamp"]).strftime("%Y-%m-%d %H:%M") if r["timestamp"] else "n/a"
                    snippet = r["content"]
                    if len(snippet) > 800:
                        snippet = snippet[:800] + "..."
                    ctx_lines.append(f"[{i}] {ts} ({r['source']})\n{snippet}")
                ctx_text = "\n\n---\n\n".join(ctx_lines)

                full_response = []
                try:
                    for delta in chat_ollama(q, ctx_text, model=chosen, stream=True, history=history):
                        full_response.append(delta)
                        yield json.dumps({"delta": delta}, ensure_ascii=False) + "\n"
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    yield json.dumps(
                        friendly_error(e, fallback="AI からの応答中にエラーが発生しました"),
                        ensure_ascii=False,
                    ) + "\n"
                    return

                # Save the assistant turn.
                assistant_text = "".join(full_response)
                if assistant_text.strip():
                    add_message(conn, sid, "assistant", assistant_text)
                yield json.dumps({"done": True}, ensure_ascii=False) + "\n"
            finally:
                conn.close()

        return StreamingResponse(event_stream(), media_type="application/x-ndjson")

    return app
