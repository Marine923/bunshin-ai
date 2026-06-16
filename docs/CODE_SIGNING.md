# コード署名 + notarization セットアップ

> 「右クリック→開く」をなくして、普通にダブルクリックで開ける状態にする手順。

現状の DMG は無署名なので、初回起動時に macOS Gatekeeper の警告が出ます。これを解消するには Apple Developer Program ($99/年) への加入と、署名・notarization の設定が必要です。

---

## 必要なもの

| 項目 | 用途 | 取得方法 |
|------|------|----------|
| Apple Developer Program | 証明書発行に必須 | https://developer.apple.com/programs/ ($99/年) |
| Developer ID Application 証明書 | 配布用アプリの署名 | Apple Developer サイトから |
| App-specific password | notarize（Apple のオンライン審査） | https://appleid.apple.com の「サインインとセキュリティ」 |
| Apple ID | notarize の認証 | 既存のもの |
| Team ID | 証明書の識別 | Apple Developer サイトの Membership |

---

## ステップ 1: Apple Developer Program 加入

1. https://developer.apple.com/programs/ にアクセス
2. **Enroll** を選択
3. Apple ID でサインイン
4. 個人 (Individual) か 組織 (Organization) を選択
   - 個人なら $99/年
   - 組織は D-U-N-S Number が必要、$99/年
5. 支払い → 承認待ち（24-48 時間）

---

## ステップ 2: Developer ID Application 証明書

1. https://developer.apple.com/account/resources/certificates/list を開く
2. **「+」ボタン** → **Developer ID Application** を選択
3. **Continue**
4. **CSR（証明書署名要求）** が必要：
   - Mac の Keychain Access を開く
   - メニュー → 証明書アシスタント → 認証局に証明書を要求
   - メールアドレスを入力、**「ディスクに保存」** を選択
   - 保存した `.certSigningRequest` を Apple サイトにアップロード
5. **Continue** → 証明書 (`.cer`) がダウンロードできる
6. ダウンロードした `.cer` をダブルクリック → Keychain Access に取り込み
7. Keychain Access で **「ログイン」** キーチェーンに `Developer ID Application: ...` が追加されているのを確認

---

## ステップ 3: App-specific Password

notarize（Apple への提出）に Apple ID + 専用パスワードが必要：

1. https://appleid.apple.com にサインイン
2. **「サインインとセキュリティ」** → **「App 用パスワード」**
3. **「+」** → ラベルに `bunshin-notarize` などを入力
4. 生成された 16 文字のパスワード（例: `abcd-efgh-ijkl-mnop`）を **メモする**（一度しか表示されない）

---

## ステップ 4: Team ID 確認

1. https://developer.apple.com/account を開く
2. **Membership** タブ
3. **Team ID** をコピー（10 文字英数字、例 `ABCD12EFGH`）

---

## ステップ 5: electron-builder の設定変更

`electron-app/package.json` の `build.mac` を編集：

```jsonc
"mac": {
  // ...既存設定...
  // 旧: "identity": null,
  "identity": "Developer ID Application: YOUR NAME (TEAM_ID)",
  "hardenedRuntime": true,
  "gatekeeperAssess": false,
  "entitlements": "build/entitlements.mac.plist",
  "entitlementsInherit": "build/entitlements.mac.plist",
  "notarize": {
    "teamId": "ABCD12EFGH"
  }
},
```

`identity` の文字列は Keychain Access に表示されている証明書の名前と完全一致させる必要があります。

`build/entitlements.mac.plist` を新規作成：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.cs.allow-jit</key>
  <true/>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
  <true/>
  <key>com.apple.security.cs.disable-library-validation</key>
  <true/>
</dict>
</plist>
```

（PyInstaller の同梱バイナリが unsigned なので library validation を緩める）

---

## ステップ 6: 環境変数で認証情報を渡してビルド

```bash
export APPLE_ID="your-apple-id@example.com"
export APPLE_APP_SPECIFIC_PASSWORD="abcd-efgh-ijkl-mnop"
export APPLE_TEAM_ID="ABCD12EFGH"

cd electron-app
npm run dist:mac
```

ビルド中に：

1. **署名** — Developer ID 証明書で各バイナリに署名
2. **notarize** — DMG が Apple のサーバーに送信されて自動審査（数分〜数十分）
3. **staple** — 審査通過後、DMG に審査結果を埋め込む

すべて成功すると、ユーザーは右クリック不要で普通にダブルクリックで開けるようになります。

---

## CI（GitHub Actions）で自動化

`.github/workflows/build-desktop.yml` に Secret として以下を設定：

| Secret 名 | 値 |
|-----------|------|
| `APPLE_ID` | Apple ID メールアドレス |
| `APPLE_APP_SPECIFIC_PASSWORD` | App-specific password |
| `APPLE_TEAM_ID` | Team ID |
| `CSC_LINK` | base64 エンコードした `.p12` 証明書（Keychain からエクスポート） |
| `CSC_KEY_PASSWORD` | `.p12` のパスワード |

`CSC_LINK` の作り方：

```bash
# Keychain Access で証明書を「書き出す」→ .p12 形式で保存（パスワード設定）
base64 -i certificate.p12 -o cert.b64
cat cert.b64 | pbcopy   # クリップボードにコピー
```

これを GitHub Settings → Secrets → Actions に貼り付け。

---

## トラブルシューティング

### `Error: No identity found for signing`
Keychain Access に証明書がインストールされていない、または `identity` 文字列が一致していない。完全一致を確認。

### `notarize failed` / `Status: Invalid`
ログ取得：
```bash
xcrun notarytool log <submission-id> --apple-id $APPLE_ID --password $APPLE_APP_SPECIFIC_PASSWORD --team-id $APPLE_TEAM_ID
```
よくある原因：entitlements の不足、hardenedRuntime 無効、signature 不整合。

### `errSecInternalComponent`
Keychain がロックされている。`security unlock-keychain` で解除。

---

## なぜここまで必要なのか

macOS では「身元の分からないアプリ」がデフォルトで実行できないように Gatekeeper が制限しています。署名 + notarize は **「このアプリは Apple Developer Program 加入済みの開発者が作っており、悪意あるコードを含んでいない」** ことを Apple が保証する仕組み。ユーザーは右クリック不要でダブルクリックで開けるようになり、信頼性も格段に上がります。

$99/年は決して安くはないですが、配布対象が増えるにつれ「セットアップで挫折するユーザー」が減るので、ROI は高いです。
