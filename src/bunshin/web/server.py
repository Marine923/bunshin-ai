"""FastAPI web server for Bunshin."""
import json
from pathlib import Path
from typing import Optional

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
  .chat-container {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 200px);
    max-height: 800px;
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
  <div class="tab" data-pane="graph">🕸 関係性</div>
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

  <!-- ============== Chat Pane ============== -->
  <section class="pane" id="pane-chat">
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
  });
});

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
let searchTimer = null;
let currentPeriod = 'all';

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
    const j = await (await fetch(`/api/search?${params}`)).json();
    if (!j.results?.length) { results.innerHTML = '<div class="empty">該当なし</div>'; return; }
    results.innerHTML = j.results.map((r, i) => renderResult(r, i)).join('');
    document.querySelectorAll('.result').forEach((el, i) => {
      el.addEventListener('click', () => toggleSession(el, j.results[i]));
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
  return `
    <div class="result" data-idx="${idx}">
      <div class="result-meta">
        <span>${ts}</span>
        <span class="source-badge ${srcClass}">${esc(srcLabel)}</span>
        <span class="distance">distance ${r.distance.toFixed(3)}</span>
        <span class="expand-hint">クリックで会話全体を表示 ▾</span>
      </div>
      <div class="result-content">${esc(r.content)}</div>
    </div>
  `;
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

function appendMsg(role, content, contextList) {
  const msg = document.createElement('div');
  msg.className = 'chat-msg ' + role;
  msg.textContent = content;
  if (contextList && contextList.length) {
    const toggle = document.createElement('span');
    toggle.className = 'ctx-toggle';
    toggle.textContent = `📚 参照した過去記憶 ${contextList.length}件 ▾`;
    const list = document.createElement('div');
    list.className = 'ctx-list';
    list.innerHTML = contextList.map(c => {
      const ts = c.timestamp ? new Date(c.timestamp * 1000).toLocaleString('ja-JP') : 'n/a';
      return `<div style="margin-bottom:8px;"><b>${ts}</b> [${esc(c.source)}]<br>${esc((c.content||'').slice(0,200))}…</div>`;
    }).join('');
    toggle.onclick = () => list.classList.toggle('shown');
    msg.appendChild(document.createElement('br'));
    msg.appendChild(toggle);
    msg.appendChild(list);
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
    const resp = await fetch('/api/chat?' + new URLSearchParams({ q: query }));
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
          if (j.context) {
            contextList = j.context;
          } else if (j.delta) {
            fullText += j.delta;
            respMsg.textContent = fullText;
            chatMessages.scrollTop = chatMessages.scrollHeight;
          } else if (j.error) {
            respMsg.textContent = 'エラー: ' + j.error;
          }
        } catch {}
      }
    }
    // Re-render with context toggle
    if (contextList) {
      respMsg.textContent = '';
      respMsg.textContent = fullText;
      const toggle = document.createElement('span');
      toggle.className = 'ctx-toggle';
      toggle.textContent = `📚 参照した過去記憶 ${contextList.length}件 ▾`;
      const list = document.createElement('div');
      list.className = 'ctx-list';
      list.innerHTML = contextList.map(c => {
        const ts = c.timestamp ? new Date(c.timestamp * 1000).toLocaleString('ja-JP') : 'n/a';
        return `<div style="margin-bottom:8px;"><b>${ts}</b> [${esc(c.source)}]<br>${esc((c.content||'').slice(0,200))}…</div>`;
      }).join('');
      toggle.onclick = () => list.classList.toggle('shown');
      respMsg.appendChild(document.createElement('br'));
      respMsg.appendChild(toggle);
      respMsg.appendChild(list);
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


def create_app(db_path: Path = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="分身 (Bunshin)")

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
    ):
        conn = init_db(db_path)
        try:
            results = search(
                conn, q, limit=limit, min_content_length=min_chars,
                sort=sort, from_ts=from_ts, to_ts=to_ts,
            )
            return {"query": q, "count": len(results), "results": results}
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

    @app.get("/api/chat")
    def api_chat(
        q: str = Query(..., min_length=1),
        model: Optional[str] = Query(None),
        context_limit: int = Query(5, ge=0, le=20),
    ):
        """Stream a chat response. Yields newline-delimited JSON:
            {"context": [...]} once at start
            {"delta": "..."} per chunk
            {"error": "..."} on failure
        """
        from bunshin.chat import (
            build_context,
            chat_ollama,
            check_ollama,
            pick_model,
        )

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
                results = search(conn, q, limit=context_limit) if context_limit > 0 else []
            finally:
                conn.close()

            # Emit context list first
            context_summary = [
                {
                    "timestamp": r["timestamp"],
                    "source": r["source"],
                    "content": r["content"],
                    "distance": r["distance"],
                }
                for r in results
            ]
            yield json.dumps({"context": context_summary, "model": chosen}, ensure_ascii=False) + "\n"

            # Build prompt context text
            from datetime import datetime
            ctx_lines = []
            for r in results:
                ts = datetime.fromtimestamp(r["timestamp"]).strftime("%Y-%m-%d %H:%M") if r["timestamp"] else "n/a"
                snippet = r["content"]
                if len(snippet) > 800:
                    snippet = snippet[:800] + "..."
                ctx_lines.append(f"[{ts}] ({r['source']})\n{snippet}")
            ctx_text = "\n\n---\n\n".join(ctx_lines)

            try:
                for delta in chat_ollama(q, ctx_text, model=chosen, stream=True):
                    yield json.dumps({"delta": delta}, ensure_ascii=False) + "\n"
            except Exception as e:
                yield json.dumps({"error": str(e)}, ensure_ascii=False) + "\n"

        return StreamingResponse(event_stream(), media_type="application/x-ndjson")

    return app
