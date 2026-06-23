# Screenshots for the README hero

The README's hero strip embeds three images from this folder. They
should all show **real, populated** Bunshin (no Lorem ipsum), at
**Retina resolution**, in **light mode**, with the user's personal
data redacted only if absolutely necessary (the whole point of the
hero is to show "this thing remembers everything").

## Files

| File | What to capture |
|---|---|
| `01-search-flashback.png` | 検索タブ — フラッシュバック 3 カードがいい感じに埋まってる状態 |
| `02-relationships.png` | 関係性タブ — 蜘蛛の巣ビューで中央エンティティから線が伸びてる状態 |
| `03-chat.png` | チャットタブ — AI 応答 + 「参照した過去記憶」が展開してる状態 |

## Recipe (3 minutes per shot)

1. **Window size to 1600 × 1000.** macOS の Bunshin ウィンドウを掴んで
   右下をドラッグ。きっちり揃えたい場合は Rectangle / BetterSnapTool 等で。
2. **Light mode** に切り替え（ヘッダー右の月アイコン）。
3. 該当タブで「いい状態」を作る：
   - **#01 検索** — 起動直後、検索ボックス空、フラッシュバック 3 カードが
     全部埋まってる状態。検索ボックスはクリックしない（オートコンプリート
     を出さない）。
   - **#02 関係性** — 蜘蛛の巣ビュー、中央に話題のエンティティ
     （プロジェクト名など）を選んで、周りの線が綺麗に伸びてる状態。
     右ペインに詳細が出てる方が「中身がある」感が出る。
   - **#03 チャット** — 自分が使った実際の質問を投げて、AI 応答が
     完了した状態。「📚 参照した過去記憶」を展開しておくと「ローカル
     検索 → AI 引用」のフロー全体が見える。
4. **Cmd + Shift + 4 → Space → Bunshin ウィンドウをクリック**。
   ファイル名を `01-search-flashback.png` 等に変えて、この
   `docs/screenshots/` フォルダに保存。
5. ファイルサイズが 2 MB 超えたら `pngcrush -brute -reduce input.png
   output.png` で圧縮（README が重くならないように）。

## Why these three

- **検索 + フラッシュバック** が Bunshin の唯一無二の体験。「過去の自分が
  返してくれる」が一目で伝わる。
- **関係性** が「ただの全文検索じゃない、構造化されてる」を示す。
- **チャット** が「ローカル LLM で AI 質問もできる」を示す。

3 枚で「記憶を貯める / 構造化する / 質問する」の全フローが画像で伝わる。

## 動画版（v0.7 以降）

`docs/screenshots/demo.mp4`（60 秒、画面録画）も入れたい。
QuickTime Player → 新規画面収録 → Bunshin ウィンドウだけ選択 →
- 起動 → 検索 → フラッシュバック → カードクリック → 検索結果 → チャット
の流れを 1 分で見せる。`ffmpeg -i input.mov -c:v libx264 -preset slow
-crf 28 -movflags +faststart output.mp4` で圧縮して README に
`![demo](docs/screenshots/demo.mp4)` で埋め込み。

優先度低。スクショ 3 枚が先。
