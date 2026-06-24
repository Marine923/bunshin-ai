<div align="center">

# 分身（Bunshin）

### **あなたの過去は、あなたのもの。**

メール、写真、会話、メモ、ファイル—
あなたが Mac で扱った全部を Bunshin が覚えていて、
**「あの時のあれ何だっけ」を AI が教えてくれる** Mac アプリ。

データは Mac の中だけ。ネット送信ゼロ。

[ダウンロード（macOS）](https://github.com/Marine923/bunshin-ai/releases/latest) &nbsp;·&nbsp;
[English README](./README.md) &nbsp;·&nbsp;
[使い方ガイド](./docs/SETUP.md)

</div>

<p align="center">
  <img src="docs/demo.gif" width="800" alt="9 秒で見る Bunshin — 検索・関係性・チャット" />
</p>

<p align="center">
  <img src="docs/screenshots/01-search-flashback.png" width="32%" alt="検索タブと今日のフラッシュバック" />
  <img src="docs/screenshots/02-relationships.png" width="32%" alt="関係性タブの蜘蛛の巣ビュー" />
  <img src="docs/screenshots/03-chat.png" width="32%" alt="ローカル AI チャット" />
</p>

---

## こんな時に便利

- 「あの店、メールに書いてあった気がするけど…いつだっけ」
- 「先月の写真、京都旅行のやつ全部出して」
- 「Claude に半年前に相談したな、なんて答えてもらったっけ」
- 「あのファイル、どこに保存したっけ」
- 「1 年前の今日、自分は何してた？」

→ Bunshin に聞けば、**全ソース横断**で探してくれます。

---

## 5 分で始める

1. **[ダウンロード](https://github.com/Marine923/bunshin-ai/releases/latest)** から `.dmg` を落とす
2. ダウンロードした `.dmg` を開く → **Bunshin を Applications にドラッグ**
3. Bunshin を起動 → **案内に沿って** Gmail / 写真 / メモを繋ぐ
4. 検索タブの **「今日のフラッシュバック」** から「1 年前の今日、自分が書いてたこと」を見てみる

---

## 何が安心？

| 約束 | 中身 |
|---|---|
| **データはあなたの Mac の中だけ** | 外部サーバーに送りません |
| **AI もローカル** | Ollama という無料の AI を使うので、Anthropic / OpenAI / Google にも送りません |
| **いつでも持ち出せる** | 設定タブから JSON / SQLite ファイルでエクスポート可能 |
| **公開されたコード** | 何をしているか全部見える（オープンソース）|
| **削除も自由** | `~/.bunshin/` フォルダごと消せば、痕跡ゼロで完全消去 |

---

## 他のアプリとの違い

| | ChatGPT 記憶 | Mem0 | Rewind | **Bunshin** |
|---|:---:|:---:|:---:|:---:|
| データ保管場所 | OpenAI のサーバー | クラウド | あなたの Mac | **あなたの Mac** |
| AI の切り替え | ❌ | ❌ | スクショベースのみ | **✅ どの AI でも** |
| オフラインで動く | ❌ | ❌ | ❌ | **✅** |
| メール・写真・メモを横断 | ❌（自分内のみ） | ❌ | スクショのみ | **✅ 11 種類のソース** |

<sub>※ Mem0 は OSS 版（自前ホスト可）もありますが、主力はクラウドサービスです。Bunshin はクラウド版を持たず、最初から最後まであなたの Mac の中だけで動きます。</sub>

---

## 入っているもの

| ▍ | 機能 | 何ができるか |
|---|---|---|
| 🔍 | **検索** | 過去の自分が触れた全部から、自然な日本語で探せる |
| ✦ | **今日のフラッシュバック** | 1 年前・3 ヶ月前・先週の同じ日に書いてたことを毎朝見せてくれる |
| 💬 | **AI と相談** | 過去記憶を AI が読んだ上で答える（あなたの文脈を持ったまま） |
| 🕸 | **関係性** | あなたの記憶に出てきた人・場所・プロジェクトの繋がりを蜘蛛の巣で可視化 |
| 📅 | **タイムライン** | 日付ごとに「この日に何してた」が一覧で見える |
| 🗑 | **不要は捨てる** | 「これ要らない」とマークすれば、Bunshin が学習して以降の似た記録は自動非表示 |
| 🔔 | **メニューバー常駐** | 画面右上の `∞` から、アプリ閉じてても瞬時に呼べる |

---

## 必要な環境

- **macOS 11 以降**
- **メモリ 8 GB 以上**（推奨 16 GB）
- **空き容量 5 GB 以上**（記憶が育つと増えます）
- **[Ollama](https://ollama.com/)** をインストールしておくと AI チャット機能が使えます

---

## 質問・問い合わせ

- **使い方が分からない** → [Discussions](https://github.com/Marine923/bunshin-ai/discussions)
- **バグを見つけた** → [Issues](https://github.com/Marine923/bunshin-ai/issues/new/choose) から「Bug report」
- **機能要望** → 同じく「Feature request」

---

## ライセンス

MIT — 商用・改変・再配布、全部 OK。
