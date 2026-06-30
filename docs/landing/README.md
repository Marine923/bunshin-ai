# docs/landing — bunshinmemory.com 用 landing page

ドメイン取得後に静的ホスティングへそのまま deploy できる
single-file landing page。

## 内容

- `index.html` — Bunshin Memory のヒーロー / 機能カード /
  プライバシー強調 / bunshin.app との区別 / footer。1 ファイル完結、
  外部依存 (フォント以外) なし。
- ダーク・ライト両対応 (`prefers-color-scheme`)
- OG / Twitter card メタタグ済
- canonical = `https://bunshinmemory.com/`

## デプロイ先候補 (本田さん action)

| 候補 | 必要なもの | 利点 |
|---|---|---|
| **GitHub Pages** | この repo の Settings → Pages | 無料、リポジトリと連動、ドメイン取得後 `bunshinmemory.com` を CNAME |
| **Cloudflare Pages** | Cloudflare アカウント | 無料、CI に組み込みやすい、CDN 強い |
| **Vercel** | Vercel アカウント | 無料、デプロイ早い |
| 自前サーバー | VPS | 既存サーバーあれば |

## GitHub Pages にする場合の最短手順

1. `bunshinmemory.com` を取得 (Cloudflare Registrar 推奨、$10/年)
2. このリポジトリの Settings → Pages → Source: `main` / `/docs/landing`
3. Settings → Pages → Custom domain: `bunshinmemory.com`
4. ドメイン業者の DNS 設定で `A` レコードを GitHub の IP に向ける:
   - `185.199.108.153`
   - `185.199.109.153`
   - `185.199.110.153`
   - `185.199.111.153`
   - もしくは `CNAME` → `marine923.github.io.`
5. SSL 自動発行を待つ (数分)

## タグライン変更時

`index.html` の以下 3 箇所を一括書換:
- `<title>` 内
- `meta name="description"` 内
- `<section class="hero">` の `<h1>` と `.tagline`
