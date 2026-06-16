"""FastAPI web server for Bunshin."""
import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from bunshin.search import search
from bunshin.storage import (
    DEFAULT_DB_PATH,
    count_records,
    count_vectors,
    get_session_records,
    init_db,
    init_vector_db,
    list_sources_with_counts,
)


INDEX_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>分身（Bunshin）</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 0;
    background: #0a0a0a;
    color: #e5e5e5;
    font-family: -apple-system, "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif;
    line-height: 1.6;
    -webkit-text-size-adjust: 100%;
  }
  header {
    padding: 18px 24px;
    border-bottom: 1px solid #1a1a1a;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
  }
  h1 {
    margin: 0;
    font-size: 22px;
    font-weight: 500;
    letter-spacing: 0.05em;
  }
  .stats { font-size: 12px; color: #888; }
  nav.tabs {
    display: flex;
    gap: 0;
    border-bottom: 1px solid #1a1a1a;
    padding: 0 24px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .tab {
    padding: 12px 18px;
    cursor: pointer;
    color: #888;
    border-bottom: 2px solid transparent;
    transition: all 0.15s;
    white-space: nowrap;
    font-size: 14px;
  }
  .tab:hover { color: #ddd; }
  .tab.active {
    color: #fff;
    border-bottom-color: #4a8fef;
  }
  main {
    max-width: 900px;
    margin: 0 auto;
    padding: 24px;
  }
  @media (max-width: 640px) {
    header { padding: 14px 16px; }
    h1 { font-size: 18px; }
    nav.tabs { padding: 0 12px; }
    .tab { padding: 10px 14px; font-size: 13px; }
    main { padding: 18px 16px; }
  }
  .pane { display: none; }
  .pane.active { display: block; }

  /* ── Search pane ── */
  .search-box {
    width: 100%;
    padding: 18px 24px;
    font-size: 17px;
    background: #161616;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    color: #fff;
    outline: none;
    transition: border-color 0.15s;
    font-family: inherit;
  }
  .search-box:focus { border-color: #4a8fef; }
  .hint { margin-top: 12px; color: #666; font-size: 13px; }
  .filter-row {
    margin-top: 16px;
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    align-items: center;
    font-size: 13px;
    color: #888;
  }
  .filter-row select {
    background: #161616;
    color: #ddd;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    cursor: pointer;
    font-family: inherit;
  }
  .filter-row select:focus { outline: none; border-color: #4a8fef; }
  .chips-row { display: flex; flex-wrap: wrap; gap: 6px; }
  .filter-chip {
    padding: 5px 10px;
    background: #161616;
    border: 1px solid #2a2a2a;
    border-radius: 14px;
    font-size: 12px;
    color: #aaa;
    cursor: pointer;
    transition: all 0.15s;
  }
  .filter-chip:hover { background: #222; color: #fff; }
  .filter-chip.active {
    background: #1a3a6a;
    border-color: #4a8fef;
    color: #fff;
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
    background: #161616;
    border: 1px solid #232323;
    border-radius: 8px;
    padding: 14px 16px;
    margin-bottom: 8px;
  }
  .timeline-day-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 10px;
  }
  .timeline-day-date {
    font-weight: 600;
    color: #ddd;
    font-size: 14px;
  }
  .timeline-day-date .today-marker {
    color: #4a8fef;
    font-weight: 500;
    margin-left: 6px;
    font-size: 12px;
  }
  .timeline-day-total {
    font-size: 12px;
    color: #888;
  }
  .timeline-day-sources {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .src-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: #1c1c1c;
    border: 1px solid #2a2a2a;
    border-radius: 14px;
    padding: 4px 10px;
    font-size: 13px;
    color: #ccc;
    cursor: pointer;
    transition: all 0.15s;
    user-select: none;
  }
  .src-pill:hover { background: #252525; border-color: #555; color: #fff; }
  .src-pill.expanded { background: #1a3a6a; border-color: #4a8fef; color: #fff; }
  .timeline-day-records {
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid #2a2a2a;
  }
  .timeline-record {
    display: flex;
    gap: 12px;
    padding: 6px 0;
    font-size: 13px;
    color: #bbb;
    border-bottom: 1px solid #1f1f1f;
    align-items: flex-start;
  }
  .timeline-record:last-child { border-bottom: 0; }
  .timeline-rec-time {
    color: #777;
    min-width: 42px;
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;
  }
  .timeline-rec-content {
    flex: 1;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.5;
  }
  .examples {
    margin-top: 16px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .chip {
    padding: 6px 12px;
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 16px;
    font-size: 12px;
    color: #aaa;
    cursor: pointer;
    transition: all 0.15s;
  }
  .chip:hover { background: #222; color: #fff; border-color: #4a8fef; }
  .results { margin-top: 32px; }
  .result {
    padding: 20px;
    background: #111;
    border: 1px solid #1f1f1f;
    border-radius: 8px;
    margin-bottom: 12px;
    transition: border-color 0.15s;
    cursor: pointer;
  }
  .result:hover { border-color: #333; }
  .result.expanded { border-color: #4a8fef; cursor: default; }
  .result-meta {
    font-size: 12px;
    color: #777;
    margin-bottom: 12px;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    align-items: center;
  }
  .result-meta .role { color: #4a8fef; }
  .result-meta .source-badge {
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
  }
  .source-badge.claude { background: #1a3a6a; color: #8fb4ef; }
  .source-badge.file { background: #2a3a1a; color: #b4ef8f; }
  .result-meta .distance { color: #999; }
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
    background: #0d0d0d;
    border-left: 3px solid #efaf4a;
    border-radius: 4px;
    font-size: 13px;
  }
  .sibling-item .meta {
    font-size: 11px;
    color: #888;
    margin-bottom: 4px;
  }
  .sibling-item .content {
    color: #ccc;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  .result-meta .expand-hint { margin-left: auto; color: #555; font-size: 11px; }
  .result-content {
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
    color: #ddd;
    font-size: 14px;
  }
  .session-panel {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid #2a2a2a;
  }
  .session-header { font-size: 12px; color: #888; margin-bottom: 12px; }
  .session-msg {
    margin-bottom: 16px;
    padding: 12px 16px;
    border-radius: 6px;
    background: #161616;
    border-left: 3px solid #333;
  }
  .session-msg.user { border-left-color: #4a8fef; }
  .session-msg.assistant { border-left-color: #5fbf6f; }
  .session-msg-meta {
    font-size: 11px;
    color: #777;
    margin-bottom: 6px;
    display: flex;
    gap: 12px;
  }
  .session-msg-meta .role.user { color: #4a8fef; }
  .session-msg-meta .role.assistant { color: #5fbf6f; }
  .session-msg-content {
    white-space: pre-wrap;
    word-wrap: break-word;
    color: #ccc;
    font-size: 13px;
  }
  .empty { text-align: center; color: #555; padding: 60px 0; }
  .loading { text-align: center; color: #888; padding: 20px; }

  /* ── Chat pane ── */
  .chat-layout {
    display: grid;
    grid-template-columns: 240px 1fr;
    gap: 16px;
    height: calc(100vh - 200px);
    max-height: 820px;
  }
  @media (max-width: 720px) {
    .chat-layout { grid-template-columns: 1fr; grid-template-rows: 140px 1fr; }
  }
  .chat-sidebar {
    background: #0d0d0d;
    border: 1px solid #1a1a1a;
    border-radius: 8px;
    padding: 8px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .chat-new-btn {
    width: 100%;
    padding: 10px;
    background: #1a3a6a;
    border: 1px solid #2a4a7a;
    border-radius: 6px;
    color: #fff;
    font-size: 13px;
    cursor: pointer;
    font-family: inherit;
    margin-bottom: 10px;
    transition: background 0.15s;
  }
  .chat-new-btn:hover { background: #234a7a; }
  .chat-session-item {
    padding: 8px 10px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    color: #aaa;
    transition: all 0.15s;
    margin-bottom: 2px;
    position: relative;
  }
  .chat-session-item:hover { background: #1a1a1a; color: #ddd; }
  .chat-session-item.active { background: #1a3a6a; color: #fff; }
  .chat-session-item .title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding-right: 18px;
  }
  .chat-session-item .meta { font-size: 10px; color: #666; margin-top: 2px; }
  .chat-session-item .delete-btn {
    position: absolute;
    top: 6px;
    right: 6px;
    width: 16px;
    height: 16px;
    line-height: 14px;
    text-align: center;
    border-radius: 3px;
    font-size: 12px;
    color: #555;
    opacity: 0;
    transition: opacity 0.15s;
  }
  .chat-session-item:hover .delete-btn { opacity: 1; }
  .chat-session-item .delete-btn:hover { background: #6a1a1a; color: #fff; }

  .chat-container {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
  }
  .chat-msg {
    margin-bottom: 16px;
    padding: 14px 18px;
    border-radius: 12px;
    max-width: 85%;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  .chat-msg.user {
    background: #1a3a6a;
    color: #fff;
    margin-left: auto;
  }
  .chat-msg.assistant {
    background: #161616;
    border: 1px solid #2a2a2a;
    color: #ddd;
  }
  .chat-msg .ctx-toggle {
    display: inline-block;
    margin-top: 8px;
    font-size: 11px;
    color: #888;
    cursor: pointer;
  }
  .chat-msg .ctx-list {
    display: none;
    margin-top: 8px;
    padding: 10px;
    background: #0a0a0a;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    font-size: 12px;
  }
  .chat-msg .ctx-list.shown { display: block; }
  .chat-msg .citation {
    display: inline-block;
    padding: 1px 6px;
    margin: 0 2px;
    background: #1a3a6a;
    color: #8fb4ef;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    vertical-align: middle;
    text-decoration: none;
  }
  .chat-msg .citation:hover { background: #234a7a; color: #fff; }
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
    background: #1a3a6a;
    color: #8fb4ef;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
  }
  .chat-input-row {
    display: flex;
    gap: 8px;
    padding-top: 16px;
    border-top: 1px solid #1a1a1a;
  }
  .chat-input {
    flex: 1;
    padding: 14px 18px;
    font-size: 15px;
    background: #161616;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    color: #fff;
    outline: none;
    font-family: inherit;
  }
  .chat-input:focus { border-color: #4a8fef; }
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
  .chat-status {
    font-size: 12px;
    color: #777;
    padding: 8px 0;
    text-align: center;
  }
  .chat-status.error { color: #ff6666; }

  /* ── Insights pane ── */
  .insights-section {
    margin-bottom: 32px;
  }
  .insights-section h2 {
    font-size: 15px;
    font-weight: 600;
    color: #ddd;
    margin: 0 0 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid #1a1a1a;
  }
  .insights-card {
    padding: 14px 18px;
    background: #111;
    border: 1px solid #1f1f1f;
    border-radius: 8px;
    margin-bottom: 10px;
  }
  .insights-card.alert { border-left: 3px solid #ef4a4a; }
  .insights-card.upcoming { border-left: 3px solid #4a8fef; }
  .insights-card.note { border-left: 3px solid #5fbf6f; }
  .insights-card.pending { border-left: 3px solid #d18fef; }
  .insights-card .title {
    font-weight: 600;
    color: #fff;
    margin-bottom: 4px;
    font-size: 14px;
  }
  .insights-card .meta {
    font-size: 12px;
    color: #888;
    margin-bottom: 8px;
  }
  .insights-card .body {
    font-size: 13px;
    color: #bbb;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  .insights-generated {
    font-size: 11px;
    color: #555;
    text-align: right;
    margin-bottom: 16px;
  }

  /* ── Graph pane ── */
  .graph-layout {
    display: grid;
    grid-template-columns: 320px 1fr;
    gap: 24px;
    margin-top: 8px;
  }
  @media (max-width: 700px) { .graph-layout { grid-template-columns: 1fr; } }
  .entity-list {
    max-height: 70vh;
    overflow-y: auto;
    padding-right: 8px;
  }
  .entity-pill {
    padding: 10px 14px;
    background: #111;
    border: 1px solid #1f1f1f;
    border-radius: 6px;
    margin-bottom: 6px;
    cursor: pointer;
    transition: all 0.15s;
    font-size: 13px;
  }
  .entity-pill:hover { background: #1a1a1a; border-color: #2a2a2a; }
  .entity-pill.active { background: #1a3a6a; border-color: #4a8fef; color: #fff; }
  .entity-pill .name { font-weight: 600; }
  .entity-pill .meta { font-size: 11px; color: #777; margin-top: 2px; }
  .entity-pill .type-org { color: #ef8f4a; }
  .entity-pill .type-project { color: #4aef8f; }
  .entity-pill .type-place { color: #8f4aef; }
  .entity-pill .type-person { color: #ef4a8f; }
  .entity-pill .type-concept { color: #8fef4a; }
  .entity-pill .type-tool { color: #4aefef; }
  .entity-pill .type-topic { color: #aaa; }

  .entity-detail {
    padding: 4px;
  }
  .entity-detail h2 {
    margin: 0 0 6px;
    font-size: 22px;
  }
  .entity-detail .type-badge {
    display: inline-block;
    padding: 2px 8px;
    background: #1a1a1a;
    border-radius: 10px;
    font-size: 11px;
    color: #aaa;
    margin-right: 8px;
  }
  .entity-detail .description {
    color: #bbb;
    margin: 12px 0;
    line-height: 1.6;
  }
  .entity-detail .section {
    margin-top: 24px;
  }
  .entity-detail .section h3 {
    font-size: 14px;
    color: #ccc;
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
    background: #111;
    border: 1px solid #1f1f1f;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s;
    font-size: 12px;
  }
  .relation-card:hover { background: #1a1a1a; border-color: #4a8fef; }
  .relation-card .name { color: #ddd; font-weight: 600; }
  .relation-card .weight { color: #777; font-size: 11px; margin-top: 2px; }

  .entity-record {
    padding: 14px;
    background: #0d0d0d;
    border: 1px solid #1a1a1a;
    border-radius: 6px;
    margin-bottom: 8px;
    font-size: 13px;
  }
  .entity-record .meta {
    font-size: 11px;
    color: #777;
    margin-bottom: 6px;
  }
  .entity-record .content {
    color: #ccc;
    white-space: pre-wrap;
    word-wrap: break-word;
  }

  /* ── Settings pane ── */
  .settings-section {
    margin-bottom: 28px;
    background: #0d0d0d;
    border: 1px solid #1a1a1a;
    border-radius: 10px;
    padding: 18px 22px;
  }
  .settings-section h2 {
    margin: 0 0 14px;
    font-size: 14px;
    font-weight: 600;
    color: #ddd;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding-bottom: 8px;
    border-bottom: 1px solid #1a1a1a;
  }
  .settings-field {
    display: grid;
    grid-template-columns: 1fr 200px;
    gap: 16px;
    align-items: start;
    padding: 12px 0;
    border-bottom: 1px solid #141414;
  }
  .settings-field:last-child { border-bottom: none; }
  @media (max-width: 640px) {
    .settings-field { grid-template-columns: 1fr; }
  }
  .settings-label {
    color: #e0e0e0;
    font-size: 14px;
    font-weight: 500;
  }
  .settings-help {
    color: #777;
    font-size: 12px;
    margin-top: 4px;
  }
  .settings-input {
    background: #161616;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    color: #fff;
    padding: 8px 12px;
    font-size: 13px;
    font-family: inherit;
    width: 100%;
  }
  .settings-input:focus { outline: none; border-color: #4a8fef; }
  .settings-toggle {
    display: inline-flex;
    align-items: center;
    cursor: pointer;
    user-select: none;
    background: #161616;
    border: 1px solid #2a2a2a;
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
  .settings-toggle.on { background: #1a3a6a; border-color: #4a8fef; }
  .settings-toggle.on .knob { transform: translateX(28px); background: #4a8fef; }

  .settings-save-bar {
    position: sticky;
    bottom: 0;
    background: linear-gradient(to top, #0a0a0a 60%, transparent);
    padding: 16px 0 0;
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    align-items: center;
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
<header>
  <h1>🌀 分身（Bunshin）</h1>
  <div class="stats" id="stats">loading...</div>
</header>

<nav class="tabs">
  <div class="tab active" data-pane="search">🔍 検索</div>
  <div class="tab" data-pane="chat">💬 チャット</div>
  <div class="tab" data-pane="insights">💡 気づき</div>
  <div class="tab" data-pane="timeline">📅 タイムライン</div>
  <div class="tab" data-pane="graph">🕸 関係性</div>
  <div class="tab" data-pane="settings">⚙ 設定</div>
</nav>

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
        <span class="filter-chip active" data-source="">全部</span>
        <span class="filter-chip" data-source="claude">💬 Claude</span>
        <span class="filter-chip" data-source="gmail">📧 Gmail</span>
        <span class="filter-chip" data-source="file">📄 ファイル</span>
        <span class="filter-chip" data-source="manual">📝 メモ</span>
        <span class="filter-chip" data-source="calendar">📅 予定</span>
        <span class="filter-chip" data-source="line">💬 LINE</span>
        <span class="filter-chip" data-source="browser">🌐 ブラウザ</span>
        <span class="filter-chip" data-source="notes">📓 メモ帳</span>
        <span class="filter-chip" data-source="imessage">💌 iMessage</span>
        <span class="filter-chip" data-source="photo">📷 写真</span>
      </div>
    </div>

    <div class="examples" id="example-chips">
      <!-- Examples will be loaded from your top entities -->
    </div>

    <div class="results" id="results">
      <div class="empty">検索クエリを入力するか、上のタグを押してください</div>
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
    <div class="graph-layout">
      <div class="entity-list" id="entity-list">
        <div class="loading">読み込み中…</div>
      </div>
      <div class="entity-detail" id="entity-detail">
        <div class="empty">左のリストからエンティティを選んでください</div>
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
        <button class="chat-new-btn" id="chat-new-btn">＋ 新規チャット</button>
        <div id="chat-sessions">
          <div style="font-size:11px;color:#666;padding:8px;">読み込み中…</div>
        </div>
      </aside>
      <div class="chat-container">
        <div class="chat-messages" id="chat-messages">
          <div class="empty">
            ローカルLLM（Ollama）で過去記憶を参照しながらチャットします。<br>
            下に質問を入力してください。<br><br>
            💡 「<b>覚えといて: 来週火曜10時に漁協ミーティング</b>」のように<br>
            先頭に <code>覚えといて:</code> や <code>メモ:</code> を付けると、AI に聞かずに記憶に保存だけします。
          </div>
        </div>
        <div class="chat-status" id="chat-status"></div>
        <form class="chat-input-row" id="chat-form">
          <input class="chat-input" id="chat-input" type="text" placeholder="分身に聞く… / Ask your bunshin..." autocomplete="off">
          <button class="chat-send" id="chat-send" type="submit">送信</button>
        </form>
      </div>
    </div>
  </section>
</main>

<script>
const $ = (id) => document.getElementById(id);
const esc = (s) => { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; };

// ===== Tabs =====
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.pane').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    $('pane-' + tab.dataset.pane).classList.add('active');
    if (tab.dataset.pane === 'chat') $('chat-input').focus();
    if (tab.dataset.pane === 'search') $('q').focus();
    if (tab.dataset.pane === 'insights') loadInsights();
    if (tab.dataset.pane === 'graph') loadEntities();
    if (tab.dataset.pane === 'settings') loadSettings();
    if (tab.dataset.pane === 'timeline') loadTimeline();
  });
});

// ===== Settings =====
let settingsLoaded = false;
let settingsSchemaCache = null;
let settingsCurrent = {};

const SECTION_TITLES = {
  notifications: { ja: '🔔 通知', en: 'Notifications' },
  search:        { ja: '🔍 検索',  en: 'Search' },
  chat:          { ja: '💬 チャット', en: 'Chat' },
};

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
      const title = (SECTION_TITLES[section] || { ja: section }).ja;
      html += `<div class="settings-section"><h2>${esc(title)}</h2>`;
      for (const [key, meta] of bySection[section]) {
        const current = settingsCurrent[key];
        html += `<div class="settings-field">
          <div>
            <div class="settings-label">${esc(meta.label_ja || key)}</div>
            <div class="settings-help">${esc(meta.help_ja || '')}</div>
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
    root.innerHTML = html;
    settingsLoaded = true;

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
      return;
    }
    renderEntityList(allEntities);
    entitiesLoaded = true;
  } catch (e) {
    listEl.innerHTML = `<div class="empty">エラー: ${esc(String(e))}</div>`;
  }
}

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
    el.addEventListener('click', () => loadEntityDetail(parseInt(el.dataset.id)));
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
          <h3>🔗 関連エンティティ（特異性スコア順）</h3>
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
      el.addEventListener('click', () => loadEntityDetail(parseInt(el.dataset.id)));
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
  notes: '📓', imessage: '💌', photo: '📷'
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
      c.innerHTML = '<div class="empty">この期間に記録がありません</div>';
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
      const icon = TIMELINE_SOURCE_ICONS[src] || '❓';
      return `<span class="src-pill" data-src="${src}" data-date="${d.date}">${icon} ${cnt}</span>`;
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

    // LLM digest section first — shown only as a button, fetched on click.
    html += `
      <div class="insights-section">
        <h2>📰 過去7日間のサマリ（AI 生成）</h2>
        <div id="digest-area">
          <button id="digest-btn" class="settings-save-btn" style="background:#3a5a8a;padding:8px 18px;font-size:13px;">
            AI でサマリを作成（30 秒〜2 分）
          </button>
        </div>
      </div>
    `;

    if (j.setup_hints?.length) {
      html += '<div class="insights-section"><h2>🛠 セットアップ案内</h2>';
      for (const h of j.setup_hints) {
        html += `
          <div class="insights-card" style="border-left:3px solid #efaf4a;">
            <div class="body">${esc(h.message)}</div>
          </div>`;
      }
      html += '</div>';
    }

    if (j.inactive_projects?.length) {
      html += '<div class="insights-section"><h2>🔥 長期未活動プロジェクト</h2>';
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
      html += '<div class="insights-section"><h2>📅 直近の予定（14日以内）</h2>';
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
        ? `<div style="font-size:11px;color:#5fbf6f;margin-bottom:8px;">👁 監視中: ${esc(j.watch_status.dir)}</div>`
        : '';
      html += '<div class="insights-section"><h2>📁 最近変更されたファイル</h2>' + watchInfo;
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
      html += '<div class="insights-section"><h2>📝 直近の手動メモ</h2>';
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
      html += '<div class="insights-section"><h2>❓ 直近1週間で未回答の質問</h2>';
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
async function loadStats() {
  try {
    const j = await (await fetch('/api/status')).json();
    $('stats').textContent = `${j.total_records.toLocaleString()} records · ${j.total_embeddings.toLocaleString()} embedded`;
  } catch { $('stats').textContent = 'error'; }
}
loadStats();

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

async function doSearch(query) {
  if (!query.trim()) { results.innerHTML = '<div class="empty">検索クエリを入力してください</div>'; return; }
  results.innerHTML = '<div class="loading">検索中…</div>';
  try {
    const params = new URLSearchParams({ q: query, limit: 20, sort: sortSel.value });
    const sec = periodToSec(currentPeriod);
    if (sec) params.set('from', Math.floor(Date.now()/1000) - sec);
    if (currentSource) params.set('sources', currentSource);
    const j = await (await fetch(`/api/search?${params}`)).json();
    if (!j.results?.length) { results.innerHTML = '<div class="empty">該当なし</div>'; return; }
    results.innerHTML = j.results.map((r, i) => renderResult(r, i)).join('');
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

function renderResult(r, idx) {
  const ts = r.timestamp ? new Date(r.timestamp * 1000).toLocaleString('ja-JP') : 'n/a';
  const role = (r.metadata && r.metadata.role) ? r.metadata.role : '';
  const srcClass = r.source === 'file' ? 'file' : 'claude';
  const srcLabel = r.source === 'file'
    ? `📄 ${(r.source_id || '').split('/').pop()}`
    : `💬 ${role || 'claude'}`;
  const more = (r.total_in_source && r.total_in_source > 1)
    ? `<span class="more-chunks" data-more-sid="${esc(r.source_id || '')}" data-more-idx="${idx}" title="クリックで展開">📚 同じ会話内に他 ${r.total_in_source - 1} 件 ▾</span>`
    : '';
  return `
    <div class="result" data-idx="${idx}">
      <div class="result-meta">
        <span>${ts}</span>
        <span class="source-badge ${srcClass}">${esc(srcLabel)}</span>
        <span class="distance">distance ${r.distance.toFixed(3)}</span>
        ${more}
        <span class="expand-hint">クリックで会話全体を表示 ▾</span>
      </div>
      <div class="result-content">${esc(r.content)}</div>
    </div>
  `;
}

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
        <div class="content">${esc(s.content)}</div>
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
      <div class="session-msg-content">${esc(rec.content)}</div>
    </div>
  `;
}

q.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => doSearch(q.value), 200); });
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
const chatSessions = $('chat-sessions'), chatNewBtn = $('chat-new-btn');
let currentSessionId = null;

async function loadSessionList() {
  try {
    const r = await fetch('/api/chat/sessions');
    const j = await r.json();
    const sessions = j.sessions || [];
    if (!sessions.length) {
      chatSessions.innerHTML = '<div style="font-size:11px;color:#666;padding:8px;">(まだ会話がありません)</div>';
      return;
    }
    chatSessions.innerHTML = sessions.map(s => {
      const date = new Date(s.updated_at * 1000).toLocaleDateString('ja-JP');
      const active = s.id === currentSessionId ? 'active' : '';
      return `
        <div class="chat-session-item ${active}" data-sid="${esc(s.id)}">
          <div class="title">${esc(s.title)}</div>
          <div class="meta">${esc(date)} · ${s.message_count} メッセージ</div>
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
    💡 「覚えといて: ...」「メモ: ...」で記憶への保存だけもできます。
  </div>`;
  loadSessionList();
}

chatNewBtn.addEventListener('click', startNewChat);
loadSessionList();

function linkifyCitations(text, contextList) {
  // Replace [N] tokens with clickable links to the citation block below,
  // but only if N is a valid index for the context list.
  if (!contextList || !contextList.length) {
    return esc(text);
  }
  let html = '';
  let lastEnd = 0;
  const re = /\[(\d+)\]/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const num = parseInt(m[1], 10);
    html += esc(text.slice(lastEnd, m.index));
    if (num >= 1 && num <= contextList.length) {
      const cid = `cit-${num}-${Math.random().toString(36).slice(2, 6)}`;
      html += `<a class="citation" href="#${cid}" data-cit="${num}">[${num}]</a>`;
    } else {
      html += esc(m[0]);
    }
    lastEnd = re.lastIndex;
  }
  html += esc(text.slice(lastEnd));
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
  if (role === 'assistant' && contextList && contextList.length) {
    msg.innerHTML = linkifyCitations(content, contextList);
  } else {
    msg.textContent = content;
  }
  if (contextList && contextList.length) {
    const toggle = document.createElement('span');
    toggle.className = 'ctx-toggle';
    toggle.textContent = `📚 参照した過去記憶 ${contextList.length}件 ▾`;
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
  const note = appendMsg('assistant', '📝 メモを保存中…');
  try {
    const resp = await fetch('/api/note', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    const j = await resp.json();
    if (j.saved) {
      note.textContent = `✅ メモを記憶に保存しました（${content.length}文字）。後で「`+ content.slice(0, 20) + `」で検索できます。`;
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
  chatStatus.textContent = '記憶を検索中…';
  chatStatus.className = 'chat-status';

  const respMsg = appendMsg('assistant', '');
  try {
    const params = new URLSearchParams({ q: query });
    if (currentSessionId) params.set('session_id', currentSessionId);
    const resp = await fetch('/api/chat?' + params);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      respMsg.textContent = `エラー: ${err.detail || resp.statusText}`;
      chatStatus.textContent = '';
      chatSend.disabled = false;
      return;
    }
    chatStatus.textContent = '応答生成中…';
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let contextList = null;
    let fullText = '';
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
          } else if (j.delta) {
            fullText += j.delta;
            respMsg.textContent = fullText;
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
      toggle.textContent = `📚 参照した過去記憶 ${contextList.length}件 ▾`;
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

    # For now, watch the user's Documents/Seiyo/ob (where most user data is)
    # if it exists; otherwise watch ~/Documents.
    import os
    candidates = [
        os.environ.get("BUNSHIN_WATCH_DIR"),
        str(Path.home() / "Documents" / "Seiyo" / "ob"),
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


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="分身 (Bunshin)")
    _start_background_watcher(db_path)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return INDEX_HTML

    @app.get("/api/status")
    def api_status():
        conn = init_db(db_path)
        try:
            init_vector_db(conn)
            return {
                "total_records": count_records(conn),
                "total_embeddings": count_vectors(conn),
                "sources": dict(list_sources_with_counts(conn)),
            }
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
    def api_chat_sessions():
        from bunshin.chat_history import list_sessions
        conn = init_db(db_path)
        try:
            return {"sessions": list_sessions(conn)}
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

                results = search(conn, q, limit=context_limit) if context_limit > 0 else []

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
                    yield json.dumps({"error": str(e)}, ensure_ascii=False) + "\n"
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
