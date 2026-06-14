"""Chat with bunshin memory via local LLM (Ollama)."""
from datetime import datetime
from typing import Optional

import httpx

from bunshin.search import search


OLLAMA_HOST = "http://localhost:11434"
PREFERRED_MODELS = [
    # Best Japanese quality first
    "qwen2.5:14b",
    "qwen2.5:7b",
    "qwen2.5:3b",
    "qwen2.5:1.5b",
    # English-strong fallbacks
    "llama3.1:8b",
    "llama3.2:3b",
    "llama3.2:1b",
    "llama3.2",
    "phi3:mini",
]


def check_ollama(host: str = OLLAMA_HOST) -> tuple[bool, list[str]]:
    """Return (reachable, list of model names)."""
    try:
        r = httpx.get(f"{host}/api/tags", timeout=2.0)
        if r.status_code == 200:
            return True, [m["name"] for m in r.json().get("models", [])]
    except (httpx.RequestError, KeyError, ValueError):
        pass
    return False, []


def pick_model(available: list[str]) -> Optional[str]:
    """Choose the best model from those available."""
    available_set = set(available)
    for p in PREFERRED_MODELS:
        if p in available_set:
            return p
    return available[0] if available else None


def build_context(conn, query: str, limit: int = 5) -> str:
    results = search(conn, query, limit=limit)
    if not results:
        return ""
    lines = []
    for r in results:
        ts = (
            datetime.fromtimestamp(r["timestamp"]).strftime("%Y-%m-%d %H:%M")
            if r["timestamp"]
            else "n/a"
        )
        role = (r["metadata"] or {}).get("role", "?")
        # Truncate long content
        snippet = r["content"]
        if len(snippet) > 800:
            snippet = snippet[:800] + "..."
        lines.append(f"[{ts}] ({r['source']}/{role})\n{snippet}")
    return "\n\n---\n\n".join(lines)


def chat_ollama(
    query: str,
    context: str,
    model: str,
    host: str = OLLAMA_HOST,
    stream: bool = True,
    history: Optional[list[dict]] = None,
):
    """Send chat request to Ollama. Yields response chunks if stream=True, else returns full text.

    `history` is a list of prior turns: [{"role": "user"|"assistant", "content": ...}, ...]
    Used to support multi-turn conversations — Ollama gets the whole exchange.
    """
    system = (
        "あなたはユーザーの個人記憶アシスタント「分身（Bunshin）」です。\n\n"
        "下記の「関連する過去文脈」は、ユーザーの実際の過去会話・メール・ファイル・メモから"
        "意味検索で抽出された記録です。これが**あなたの記憶**です。\n\n"
        "重要な振る舞い：\n"
        "1. 過去文脈にある情報は**積極的に引用・要約**してください。日付やソースを必ず含めてください。\n"
        "2. 直接の回答がなくても、関連情報から**推測できる場合は「〜と思われます／〜の可能性が高い」と答えてください**。\n"
        "3. 逆質問は最小限に。**情報が完全に足りない時だけ**にしてください。\n"
        "4. 過去文脈が**本当に質問と無関係な場合のみ**「過去の記憶には該当情報が見当たりません」と答えてください。\n"
        "5. 「過去の記憶」を使って答えていることをユーザーに伝えるため、**日付を必ず引用**してください（例：「2026-05-14 の会話で...」）。\n"
        "6. 直前までの会話履歴がある場合は、**それを踏まえて連続性のある応答**をしてください。\n\n"
        f"=== 関連する過去文脈 ===\n{context}\n=== ここまで ==="
    )

    messages = [{"role": "system", "content": system}]
    if history:
        # Append prior turns. Cap to last ~20 turns to keep prompt bounded.
        messages.extend(history[-20:])
    messages.append({"role": "user", "content": query})

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }

    if stream:
        with httpx.stream("POST", f"{host}/api/chat", json=payload, timeout=120.0) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    import json as _json
                    data = _json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
                except (ValueError, KeyError):
                    continue
    else:
        r = httpx.post(f"{host}/api/chat", json=payload, timeout=120.0)
        r.raise_for_status()
        yield r.json()["message"]["content"]
