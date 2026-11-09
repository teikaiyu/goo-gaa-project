# Lumo の Chrome 拡張機能

パトロール中（Lumo のタイマーが動いている間）に、Lumo が代わりに見ている SNS の Web 版
（instagram.com / x.com / youtube.com）を開くと、そのタブを Lumo の画面に切り替えます。

- **やっぱやめとく**：そのタブを閉じる
- **開く**：そのタブだけ、このパトロールの間は開けるようにする
- パトロール中でなければ、何もしません

## 入れ方（Chrome）

1. Chrome のアドレスバーに `chrome://extensions` と入れて開く
2. 右上の **デベロッパー モード** をオンにする
3. **パッケージ化されていない拡張機能を読み込む** を押し、この `lumo_extension` フォルダを選ぶ
4. Lumo のアプリ（`http://localhost:8080` または Cloud Run の URL）を開いて「始める」を押す

コードを変えたら、`chrome://extensions` の Lumo の **更新（↻）** を押す。

## 仕組み

| ファイル | 役割 |
|---|---|
| `bridge.js` | Lumo のアプリのページで動く。アプリが保存しているパトロールの状態（終わる時刻、見ている SNS）を拡張機能に伝え、Lumo の画面のボタン操作を受け渡す |
| `background.js` | パトロール中に SNS のタブが開かれたら、Lumo のアプリの `/?shield=<SNS>` に切り替える。ボタンに応じてタブを閉じる / 元のページに戻す |
| `rules.js` | どの URL がどの SNS か、パトロール中か、の判定（テスト: `node --test lumo_extension/rules.test.mjs`） |

Lumo の画面そのものは Flutter アプリ（`lumo_app/lib/main.dart` の `ShieldPage`）にある。

## 限界

- パソコンの Chrome だけ。iPhone のアプリや Safari は遮れない（PROBLEM.md の SPIKE-32）
- 動く Lumo のアプリの URL は `manifest.json` の `matches` に書いたものだけ（localhost:8080 と `*.run.app`）
