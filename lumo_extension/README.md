# Lumo の Chrome 拡張機能

パトロール中（Lumo のタイマーが動いている間）に、Lumo が代わりに見ている SNS の Web 版
（instagram.com / x.com / youtube.com）を開くと、そのタブを Lumo の画面に切り替えます。

- **やっぱやめとく**：そのタブを閉じる
- **開く**：そのタブだけ、このパトロールの間は開けるようにする
- パトロール中でなければ、何もしません

## 入れ方（パソコンの Chrome、1 回だけ）

Chrome ウェブストアには公開していません。Lumo のアプリが zip で配っています。

1. Lumo のアプリを開き、ホームの **SNS を遮るには拡張機能を入れてね** を押す → **lumo_extension.zip をダウンロード**
   （アプリを開かずに取るなら `<Lumo の URL>/lumo_extension.zip`。リポジトリの `lumo_extension` フォルダをそのまま使ってもよい）
2. zip を開いて `lumo_extension` フォルダを取り出す（Mac はダブルクリック、Windows は右クリック →「すべて展開」）
3. Chrome のアドレスバーに `chrome://extensions` と入れて開く
4. 右上の **デベロッパー モード** をオンにする
5. **パッケージ化されていない拡張機能を読み込む** を押し、`lumo_extension` フォルダ（`manifest.json` が入っているフォルダ）を選ぶ。
   このフォルダは、使っているあいだは消さない
6. Lumo のタブに戻る。拡張機能が Lumo のタブを自動で読み込み直し、ホームに **拡張機能が動いています** と出る

コードを変えたら、`chrome://extensions` の Lumo の **更新（↻）** を押す（Lumo のタブも自動で読み込み直される）。

## 入れたのに遮られないとき

| 確かめること | 理由 |
|---|---|
| ホームに **拡張機能が動いています** と出ているか | 出ていなければ、そのタブでは拡張機能が動いていない（下の行のどれか） |
| シークレット ウィンドウ・ゲストで開いていないか | 拡張機能は、初期設定ではシークレット ウィンドウで動かない。ふつうのウィンドウで Lumo と SNS を開く |
| 前に入れた古い Lumo（0.1.0）が残っていないか | 古い版はアプリに「入っている」と伝えられない。`chrome://extensions` で削除してから入れ直す |
| 「始める」の前に、そのアプリのスイッチがオンだったか | オフのアプリは遮らない |
| Lumo を開いている URL | 動くのは `manifest.json` の `matches` にある URL だけ（`localhost:8080`、`127.0.0.1:8080`、`*.run.app`） |
| それでも出ない | `chrome://extensions` → Lumo の **Service Worker** → **Console** で `chrome.storage.session.get(null).then(console.log)`。`lumo` の `endsAt`（終わる時刻）・`watched`・`app` を見る |

入れる前から開いていた SNS のタブも、「始める」を押した時点で遮られます。

## 仕組み

| ファイル | 役割 |
|---|---|
| `bridge.js` | Lumo のアプリのページで動く。ページに目印（`data-lumo-extension`）を付けてアプリに存在を知らせ、アプリが保存しているパトロールの状態（終わる時刻、見ている SNS）を拡張機能に伝え、Lumo の画面のボタン操作を受け渡す |
| `background.js` | パトロール中に SNS のタブが開かれたら、Lumo のアプリの `/?shield=<SNS>` に切り替える。ボタンに応じてタブを閉じる / 元のページに戻す。入れたとき（更新したとき）に、開いていた Lumo のタブを読み込み直す |
| `rules.js` | どの URL がどの SNS か、パトロール中か、の判定 |

Lumo の画面そのものは Flutter アプリ（`lumo_app/lib/main.dart` の `ShieldPage`）、入れ方の画面は同じファイルの
`ExtensionGuidePage`、zip は `avatar_api/main.py` の `/lumo_extension.zip`（このフォルダからテストを除いて毎回作る）。

## テスト

```sh
node --test lumo_extension/rules.test.mjs     # URL の判定（Node だけ）

# 通しの確認（本物のアプリ + Playwright の Chromium に拡張機能を入れる）
.venv/bin/pip install playwright && .venv/bin/playwright install chromium   # 初回だけ
(cd lumo_app && flutter build web)
.venv/bin/python lumo_extension/e2e.py        # localhost:8080 に何もなければ、avatar_api を起動して終わったら止める
```

`e2e.py` が確かめること: 拡張機能なしだとホームが入れ方へ案内し zip を落とせる → その zip を入れると「動いています」→
始める → youtube.com が Lumo の画面になる → **やっぱやめとく** でタブが閉じる / **開く** でそのタブは通る →
選んでいない Instagram は通る → 完了後は youtube.com が通る。本物の SNS と Google の許可画面は使わない（偽のページに差し替える）。

## 限界

- パソコンの Chrome（と Chromium 系のブラウザ）だけ。iPhone のアプリや Safari は遮れない（PROBLEM.md の SPIKE-32）。
  アプリはそのことをホームに表示する
- 入れた直後の自動読み込み直しは、Playwright では確かめられない（コマンドラインで入れた拡張機能は `chrome.runtime.reload()` で消えるため）。
  確かめたのは「開いている Lumo のタブを見つけられること」まで
