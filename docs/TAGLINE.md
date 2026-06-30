# タグライン候補 (英語)

OSS 公開・README ヒーロー・SNS 紹介の **1 行** をどれにするかを決めるためのメモ。
最終的に 1 つに絞って README.md と OG メタ description に流し込む想定。

現在の README hero (v0.10.27): `Your past is yours. AI is just the lens.`

---

## 候補 A — 哲学型 (現在のもの)

> **Your past is yours. AI is just the lens.**

- 強み: 一読で「データ主権 + AI は道具」が伝わる。覚えやすい
- 弱み: 何のアプリかは1行では分からない (説明文が必要)

## 候補 B — 機能直球型

> **Search 10 years of your Gmail, photos, notes, and Claude chats — locally.**

- 強み: 何をするかが即明示。検索範囲 (10 年 / マルチソース) と
  ローカル性が一行で揃う
- 弱み: 「10 years」は最初は嘘になる (新規ユーザーは 0 件で始まる)。
  「all your」に置き換える手もある

## 候補 C — 競合との対比型

> **The personal memory engine that runs entirely on your Mac.**

- 強み: カテゴリ (personal memory engine) を一語で名乗る。
  Mem0 / OpenJarvis / Personal.ai 系のクラウド製品と差別化
- 弱み: 「memory engine」は新語、馴染みがない人もいる

## 候補 D — 詩的型

> **Remember everything. Send nothing.**

- 強み: 短い + 韻が立つ + プライバシーポジションが秒で伝わる
- 弱み: AI とも検索とも書いてないので、文脈なしだとピンと来ない

## 候補 E — 「Your second brain」型

> **Your second brain, kept on your Mac.**

- 強み: Tiago Forte の "second brain" 概念で既に頭の準備がある人に瞬間届く
- 弱み: Tiago Forte は Notion / Obsidian カルチャー寄りで、
  Bunshin Memory のターゲット (一般日本人) には弱いかも

## 候補 F — 日本語ファースト宣言型

> **The personal memory engine, Japanese-first.**

- 強み: 「日本語ファースト」を最初に名乗る = OpenJarvis 含む英語圏
  競合との明確な差別化軸を 1 行で立てる
- 弱み: 海外開発者には響かない (海外 OSS contributor を集めたいなら不利)

---

## 私の推奨ランキング (主観)

1. **C** — カテゴリ名 + 主権、最も「何が違うか」が立つ
2. **D** — SNS で繰り返し言える 詩的短文、覚醒度高い
3. **B** — README の hero に最適 (具体性で「使える」感)
4. A / E / F — 文脈次第

ヒーロー (README) と SNS (Twitter bio) で違う候補を使う手もある:
- README hero: **C** (カテゴリ名)
- Twitter bio: **D** (秒で伝わる)
- 詳細セクション head: **B** (具体)

---

## 次のステップ

1. 本田さんが 1 つ (or 組み合わせ) を選ぶ
2. README.md / README.ja.md / OG meta description / electron-app の splash に展開
3. `bunshinmemory.com` のランディングページにも反映
