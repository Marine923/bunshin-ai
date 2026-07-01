# 壱岐の友人向け配布テンプレ

このファイルは「Bunshin Memory を友人に渡すときに使う、コピペで送れる文章」をまとめたものです。

---

## LINE / メッセージ用（短いやつ）

```
Bunshin Memory（分身メモリー）っていう、自分の Mac の中だけで動く記憶 AI を作ったから試してみて！

メール / 写真 / メモ / Claude の会話を全部読み込んで、
「あの時のあれ何だっけ」を一発で思い出せるアプリ。

ダウンロード:
https://github.com/Marine923/bunshin-ai/releases/latest

→ "Bunshin Memory-X.Y.Z-arm64.dmg"（M1/M2/M3/M4 Mac）か
   "Bunshin Memory-X.Y.Z.dmg"（Intel Mac）を落として、開いてアプリをドラッグ。
   ※ X.Y.Z は最新版番号

⚠ 「開発元未確認」って言われたら → 右クリック → 開く
⚠ メモリ 16 GB 以上の Mac 推奨

何かあれば連絡して！
```

---

## メール用（少しちゃんとした版）

件名: **Bunshin Memory（分身メモリー）試してみてください**

```
○○さん、

最近作ってる "Bunshin Memory" っていう Mac アプリをお試しで触ってもらえたら嬉しいです。

【何をするアプリか】
あなたが Mac で扱っているメール・写真・メモ・Claude との会話 —
全部を Mac の中だけで覚えて、
「あの時のあれ何だっけ」を AI が思い出させてくれます。

【何が違うか】
・データは Mac から一切外に出ません（Anthropic にも OpenAI にも送りません）
・AI もローカル（Ollama を使うので追加料金ゼロ）
・後から「やっぱり消したい」も `~/.bunshin/` フォルダごと削除でゼロに

【ダウンロード】
https://github.com/Marine923/bunshin-ai/releases/latest

  Apple Silicon Mac (M1/M2/M3/M4): "Bunshin-X.Y.Z-arm64.dmg"
  Intel Mac: "Bunshin-X.Y.Z.dmg"
  ※ X.Y.Z は最新リリース番号（GitHub の Releases ページから取得）

【インストール手順】
1. .dmg を開く → Bunshin を Applications フォルダにドラッグ
2. 初回だけ "開発元未確認" が出るので、Bunshin を **右クリック → 開く**
3. ウィザードに沿って Gmail / 写真 / メモを接続
4. 【初回のみ】ターミナルで `~/Applications/Bunshin\ Memory.app/Contents/Resources/bunshin warm`
   を実行 → AI モデル ~2 GB を事前 DL (5-10 分)。
   ※ この手順を飛ばすと、初回検索時に無反応で 5-10 分固まります。

【必要環境】
・macOS 11 以降
・メモリ 16 GB 以上推奨（8 GB だと swap が発生します）
・空き容量 5 GB 以上

【困った時】
アプリ右上の「困った時は」から診断情報を送ってください。
GitHub Issues も使えます: https://github.com/Marine923/bunshin-ai/issues

ぜひ感想を聞かせてください。

本田
```

---

## 30 秒で説明したいとき

> 「メール、写真、メモ、Claude との会話、全部を覚えてて
>  『あの時のあれ何だっけ』を一発で思い出させてくれる Mac アプリ。
>  データは全部 Mac の中だけ。AI もローカル。
>  Anthropic にも OpenAI にも一切送ってない。」

---

## よくある質問への準備回答

### Q. ネットに送られるの？
> 「いいえ。データは全部 Mac の中だけです。
>  ただし関係性タブで『AI に説明させる』ボタンを押した時だけ、
>  エンティティ名（"Native Instruments" とか）が Wikipedia に送られます。
>  記録の中身は送りません。これは設定タブで OFF にできます。」

### Q. 何のために作ったの？
> 「自分が忘れっぽいから。
>  Gmail で半年前にもらった重要な情報、Claude と相談した壱岐黄金の戦略、
>  写真に写ってる名刺、メモアプリに書いた青枯病対策 —
>  全部頭の中じゃなく分身に覚えさせて、必要な時に呼び出す。」

### Q. ChatGPT の Memory と何が違うの？
> 「ChatGPT の記憶は OpenAI のサーバーに保存されてるから、
>  あなたの記憶を別の AI に持って行けません。
>  分身はあなたの Mac の中に SQLite で保存してるので、
>  Claude にも ChatGPT にも MCP 経由で同じ記憶を見せられます。
>  AI を変えても記憶は残る — これが『分身』の意味です。」

### Q. 月いくら？
> 「無料。サブスクなし。買い切りでもない。
>  オープンソース (MIT) なので、ソースも GitHub で全部見られます。」

### Q. アンインストールしたい
> 「Applications から Bunshin を Trash に。
>  完全に痕跡を消したいなら `~/.bunshin/` フォルダも削除してください。」

---

## 配布前チェックリスト

- [ ] 最新リリース DMG を `/Applications/Bunshin Memory.app` で動作確認
- [ ] 別の Mac で clean install してオンボーディングが完走するか
- [ ] `bunshin warm` で初回モデル DL が完了するか (別 Mac)
- [ ] `bunshin doctor` の 4 項目 (embed/rerank/disk/runtime) が clean で緑になるか
- [ ] Gmail App Password の取得手順を口頭で説明できるようにする
- [ ] 「困った時は」から診断情報が送れることを再確認
- [ ] バックアップ機能 (`~/.bunshin/backups/`) が走ってることを確認
