# Lumo の Chrome 拡張機能

**これを入れるだけで Lumo が全部使えます**（サーバーを立てる必要も、別の URL を開く必要もありません）。
Lumo のアプリ（ホーム・タイマー・遮る画面・報告）は拡張機能の中に入っていて、Chrome 右上のパズルのアイコン → **Lumo** で開きます。
報告の文章（Gemini）だけは、デプロイ済みの Cloud Run を呼びます。

パトロール中（Lumo のタイマーが動いている間）に、Lumo が代わりに見ている SNS の Web 版
（instagram.com / x.com / youtube.com）を開くと、そのタブを Lumo の画面に切り替えます。

- **やっぱやめとく**：そのタブを閉じる
- **開く**：そのタブだけ、このパトロールの間は開けるようにする
- パトロール中でなければ、何もしません

## 入れ方（パソコンの Chrome、1 回だけ）

Chrome ウェブストアには公開していません。Lumo のアプリが zip で配っています。

1. `<Lumo の URL>/lumo_extension.zip` をダウンロードする（Web 版 Lumo のホームの **SNS を遮るには拡張機能を入れてね** からも落とせる）。
   リポジトリから使うなら、先に `lumo_extension/build.sh` でアプリを中に入れる（`app/` と `lumo/` ができる。git には入れない）
2. zip を開いて `lumo_extension` フォルダを取り出す（Mac はダブルクリック、Windows は右クリック →「すべて展開」）
3. Chrome のアドレスバーに `chrome://extensions` と入れて開く
4. 右上の **デベロッパー モード** をオンにする
5. **パッケージ化されていない拡張機能を読み込む** を押し、`lumo_extension` フォルダ（`manifest.json` が入っているフォルダ）を選ぶ。
   このフォルダは、使っているあいだは消さない
6. Lumo が新しいタブで開く。次からは Chrome 右上のパズルのアイコン → **Lumo**（ピン留めするとツールバーに出る）で開く

コードを変えたら、`lumo_extension/build.sh` → `chrome://extensions` の Lumo の **更新（↻）** を押す。

## 入れたのに遮られないとき

| 確かめること | 理由 |
|---|---|
| ホームに **拡張機能が動いています** と出ているか | 出ていなければ、そのタブでは拡張機能が動いていない（下の行のどれか） |
| シークレット ウィンドウ・ゲストで開いていないか | 拡張機能は、初期設定ではシークレット ウィンドウで動かない。ゲストには入れられない。ふつうのウィンドウで Lumo と SNS を開く |
| 前に入れた古い Lumo（0.1.0 / 0.2.0）が残っていないか | 古い版にはアプリが入っていない。`chrome://extensions` で削除してから入れ直す |
| 「始める」の前に、そのアプリのスイッチがオンだったか | オフのアプリは遮らない |
| （Web 版の Lumo から使うとき）Lumo を開いている URL | 拡張機能が読み取れるのは `manifest.json` の `matches` にある URL だけ（`localhost:8080`、`127.0.0.1:8080`、`*.run.app`） |
| それでも出ない | `chrome://extensions` → Lumo の **Service Worker** → **Console** で `chrome.storage.session.get(null).then(console.log)`。`lumo` の `endsAt`（終わる時刻）・`watched`・`app` を見る |

入れる前から開いていた SNS のタブも、「始める」を押した時点で遮られます。

## 仕組み

| ファイル | 役割 |
|---|---|
| `bridge.js` | Lumo のアプリのページ（中の `app/` と Web 版）で動く。ページに目印（`data-lumo-extension`）を付けてアプリに存在を知らせ、アプリが保存しているパトロールの状態（終わる時刻、見ている SNS）を拡張機能に伝え、Lumo の画面のボタン操作を受け渡す |
| `background.js` | ツールバーのボタンと初めて入れたときに、中の Lumo（`app/index.html`）を開く。パトロール中に SNS のタブが開かれたら、パトロールを始めた Lumo の画面の `?shield=<SNS>` に切り替える。ボタンに応じてタブを閉じる / 元のページに戻す。入れたとき（更新したとき）に、開いていた Web 版 Lumo のタブを読み込み直す |
| `build.sh` | Flutter のアプリ（`lumo_app`）を拡張機能のページ用にビルドして `app/` に、Lumo の画像を `lumo/` に入れる。拡張機能のページは外部のスクリプトを読めないので、CDN を使わない・Google のログイン用スクリプトの代わりに `chrome.identity` を使う・`bridge.js` を読み込む |
| `rules.js` | どの URL がどの SNS か、パトロール中か、の判定 |

Lumo の画面そのものは Flutter アプリ（`lumo_app/lib/main.dart` の `ShieldPage`）、入れ方の画面は同じファイルの
`ExtensionGuidePage`、zip は `avatar_api/main.py` の `/lumo_extension.zip`（このフォルダからテストを除いて毎回作る）。

## テスト

```sh
node --test lumo_extension/rules.test.mjs     # URL の判定（Node だけ）

# 通しの確認（本物のアプリ + Playwright の Chromium に拡張機能を入れる）
.venv/bin/pip install playwright && .venv/bin/playwright install chromium   # 初回だけ
# 本番と同じく GOOGLE_CLIENT_ID を付けてビルドする（付けないと「始める」で Google の画面が開く場合を通らない）
export GOOGLE_CLIENT_ID=<Web 版と同じクライアント ID>
(cd lumo_app && flutter build web --dart-define=GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID) && lumo_extension/build.sh
.venv/bin/python lumo_extension/e2e.py        # localhost:8080 に何もなければ、avatar_api を起動して終わったら止める
```

`e2e.py` が確かめること: 拡張機能なしだと Web 版のホームが入れ方へ案内し zip を落とせる → その zip だけを入れ、ここからは
拡張機能の中の Lumo で: 「動いています」→ 始める → youtube.com が Lumo の画面になる → **やっぱやめとく** でタブが閉じる / **開く** でそのタブは通る →
選んでいない Instagram は通る → 完了で報告が出る → 完了後は youtube.com が通る。本物の SNS と Google の許可画面は使わない（偽のページに差し替える）。

## 限界

- パソコンの Chrome（と Chromium 系のブラウザ）だけ。iPhone のアプリや Safari は遮れない（PROBLEM.md の SPIKE-32）。
  アプリはそのことをホームに表示する
- 入れた直後に Web 版 Lumo のタブを読み込み直す動きは、自動テストでは確かめていない
- YouTube の許可を拡張機能の中で使うには、OAuth クライアント（Web 版と同じもの）の **承認済みのリダイレクト URI** に
  `https://pogcdfbiphaccabcjjadojoppmmgepgf.chromiumapp.org/` を足す必要がある（拡張機能の ID は `manifest.json` の `key` で固定）。
  ビルドのときに `GOOGLE_CLIENT_ID` を渡す（`scripts/deploy_avatar_api.sh` は渡す）
- 報告の文章は Cloud Run の `/patrol` を呼ぶので、Web 版と同じく、設定に API の鍵を入れていないと Lumo の決まった言葉になる
- Playwright では、ツールバーのボタンと初めて入れたときに Lumo が開くことは確かめられない（中の Lumo のページを直接開いて確かめた）
