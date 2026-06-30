# データ手入れチートシート

Bunshin の自動取り込みは完璧ではありません。NER のゆれ、写真の旧 Wikipedia 地名、
description の depthness — 既存ユーザーが定期的に手入れすると見通しが良くなる項目を、
1 セッションで終わる手順に整理しました。

> v0.10.26 時点で、すべての手入れは **CLI から完結** します。Bunshin.app の UI を
> 触る必要はありません。

---

## 1. 写真の地名を Nominatim ベースに refresh

**いつ**: doctor が「古い写真地名: N 件」と表示したら。

**何が起きる**:
- 旧地名 ("小栗村 (長崎県)") や建物名 ("Barcelona City Hall") を picked up していた
  古い entity を、Nominatim の **現代の admin** ("諫早市" / "バルセロナ") に rename。
- 同時に description の `(Wikipedia から逆ジオコーディング)` も
  `(Nominatim から逆ジオコーディング)` に更新。
- rename の結果同名 entity が並んだら、merge コマンドを最後に出力。

```bash
# Dry-run: 何が変わるか確認
bunshin photos-relabel-places --dry-run

# 実行
bunshin photos-relabel-places
```

出力例:

```
Found 9 photo place entities.

8 entities to rename:

  # 201  '小栗村 (長崎県)' → '諫早市'  (32.8300,130.0600)
  # 202  '多比良町' → '雲仙市'  (32.8600,130.3000)
  # 203  'Olsztyn County' → 'オルシュティン'  (53.7800,20.4900)
  # 204  'Barcelona City Hall' → 'バルセロナ'  (41.3800,2.1800)
  ...

✓ Renamed 8 entities

3 duplicate group(s) appeared after rename:

  1.  'バルセロナ'
    → # 204  'バルセロナ'  (place,   7 mentions)
      # 208  'バルセロナ'  (place,   3 mentions)
       $ bunshin merge-entities 208 204
```

出てきた `$ bunshin merge-entities …` 行をそのままコピペで実行すれば dup 解消。

---

## 2. Entity の type を直す

**いつ**: 関係性タブで「Deck A が `place`」「DJ ライブラリが `place`」のように、
明らかに type がおかしい entity を見つけたら。

**何が起きる**: Bunshin の起動時に走るマイグレで、description キーワードベースの
reclassify が動きます。`_TOOL_KEYWORDS` / `_CONCEPT_KEYWORDS` / `_ORG_KEYWORDS`
を見て type を矯正します。

```bash
# Bunshin.app を一度終了して再起動
# → 起動時マイグレで該当 entity の type が自動的に直る
```

これで直らなければ:
- 該当 entity の description が空、または分類キーワードに該当する語が含まれていない
  ケース。関係性タブで「やり直し」ボタンを押して describe を再生成 →
  もう一度 Bunshin.app を再起動。

---

## 3. NER の重複 entity を集約

**いつ**: doctor が「重複候補エンティティ: N 件」と表示したら。

**何が起きる**:
- normalize 後の name (parenthesized suffix / 大文字小文字 / 句読点除去) が同じ
  entity を group 化。
- 最も mentions の多い entity (同数なら短い名前) を target に推奨し、
  ready-to-paste の merge コマンドを表示。
- `merge-entities` は record_entities + entity_relations を target に書換、
  source の row を削除します。

```bash
# 候補発見
bunshin find-duplicates

# 出力された `$ bunshin merge-entities <src> <tgt> --dry-run` をまず確認
# 問題なければ --dry-run を外して実行
```

---

## 4. Entity の description を refresh

**いつ**: description が古い、または当該 entity の **主要関連先 (top_relations)**
が大きく変わったとき。v0.10.15 で describe prompt に top_relations を注入
するようになったので、関連先が変われば description も意味のある形で変わります。

```bash
# Bunshin.app または bunshin web を起動した状態で:
bunshin re-describe-all --limit 200 --min-mentions 2

# 単独 entity を refresh するなら、関係性タブで対象 entity を開いて
# 「✨ AI に説明させる → やり直し」をクリック。
```

---

## 5. doctor で全体ヘルスチェック

迷ったら最初にこれ。すべてのチェックを 1 回で実行します:

```bash
bunshin doctor
```

代表的な出力 (本田さん DB):
```
✓ データベース: 20821 件
✓ ベクトル化: 20832/20821
✓ Ollama: 3 モデル
✓ Gmail: configured
✓ 自動更新: macos で毎時実行中
✓ Claude Desktop MCP: 設定済
✓ bunshin web v0.10.26 起動中
✓ Knowledge Graph: 191 エンティティ, 10935 リンク

ℹ 古い写真地名: 5 件 → bunshin photos-relabel-places
ℹ 重複候補エンティティ: 1 件 → bunshin find-duplicates
ℹ Anthropic API キー: 未設定 → 設定タブ
```

---

## ワークフローまとめ (週次推奨)

```
bunshin doctor                       # 全体ヘルス
bunshin photos-relabel-places        # 写真の地名 refresh + 重複表示 + merge command
bunshin find-duplicates              # NER 重複候補
bunshin merge-entities <src> <tgt>   # 1 件ずつ merge (CLI が提案する向きで)
bunshin re-describe-all              # entity description を refresh
```
