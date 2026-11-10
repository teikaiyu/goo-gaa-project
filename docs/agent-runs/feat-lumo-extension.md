# 作業記録: feat/lumo-extension（拡張機能版 Lumo の仕上げ）

## 1. 時刻と終わった理由
| 回 | 開始（JST） | 終了（JST） | 終わった理由 |
|---|---|---|---|
| 1 回目（`claude -p`、`agent-runs/run.sh extension`） | 2026-11-10 02:21 | 02:37 | Claude の 5 時間の使用量上限（`usage_limit_reached`）。docs の変更が未コミット、5 回連続の e2e が未実行のまま停止 |
| 2 回目（対話セッションで再開） | 2026-11-10 08:35 | 同日 08:45 頃 | 完成（このときは「Web 版 + 拡張機能」の形） |
| 3 回目（対話セッション） | 2026-11-10 09:00 | 同日 09:50 頃 | 完成。ユーザーの指摘で「拡張機能を入れるだけで全部動く」形に作り直し |

## 2. やったこと（時系列）
- `48146e6` 拡張機能がページに目印（`<html data-lumo-extension="<版>">`）を付け、アプリのホームに「動いています / 入れてね / この端末では遮れません」を出す。
  入れ方の画面（`ExtensionGuidePage`）と `/lumo_extension.zip` の配布（`avatar_api/main.py`、Dockerfile に `EXTENSION_DIR`）。
  拡張機能が入ったときに Lumo のタブを読み込み直す（`background.js` の `onInstalled`）。始める・終わるときにアプリが拡張機能へすぐ伝える。版を 0.2.0 に。
- `3762b57` 通しのテスト `lumo_extension/e2e.py`（Playwright の Chromium + 本物のアプリ）。
- `1ea9028` zip の中をフォルダなしにする（Windows で二重フォルダになるのを防ぐ）。e2e はダウンロードした zip を入れて確かめる。
- （2 回目）`flutter build web` のあと e2e を 5 回連続で実行、全テスト実行、README・PROBLEM.md・decisions.md・`lumo_extension/README.md` とこの記録をコミット。

## 3. 自分で判断したこと
| 判断 | ほかの選択肢 | 根拠 |
|---|---|---|
| 拡張機能の検知は、ページに目印を付ける | `postMessage` で問い合わせ / `externally_connectable` | 待たずに分かる・権限が増えない。zip から入れると拡張機能の ID が変わるので `externally_connectable` は使えない（`docs/decisions.md` 2026-11-10） |
| 配布は Cloud Run の `/lumo_extension.zip`（リクエストごとに作る） | ウェブストア公開 / GitHub から落とす | 指示で「ウェブストアに公開しない」「今ある仕組みを使う」。ビルド手順が増えず、デプロイ中のアプリと常に同じ版 |
| 遮れない端末（iPhone・Android・Safari・Firefox）はホームで正直に伝える | 何も出さない | 指示 1。判定は User-Agent の `Chrome/` とパソコンかどうか。目印があれば最優先 |
| e2e で YouTube の許可は偽物に差し替え、watched は YouTube だけ | 本物の Google の許可画面 | 指示 3（Google の許可が要る部分は避けてよい）。SNS も偽のページに差し替え、本物には触れない（SPIKE-33） |
| 入れた直後の自動読み込み直しは「タブを見つけられるか」までの確認 | 本当に reload させる | Playwright の `--load-extension` で入れた拡張機能は `chrome.runtime.reload()` で消えるため |

## 4. 確認したこと（2 回目、2026-11-10 08:40 頃）
- `lumo_extension/e2e.py`: **5 回連続、11 項目すべて ok**（拡張機能なしの案内と zip のダウンロード → zip を入れる → 「動いています」→ 始める →
  選んでいない Instagram は通る → youtube.com が Lumo の画面 → やっぱやめとく で閉じる → 開く で通す → そのまま通り続ける → 完了後は通る）
- `flutter analyze`: 問題なし / `flutter test`: 10 件成功
- `avatar_api` の pytest: 40 件成功 / ルートの `tests/`（デスクトップ版）: 38 件成功・1 件スキップ
- `node --test lumo_extension/rules.test.mjs`: 3 件成功

## 5. できていないこと・人間がやること
1. **main へのマージとデプロイ**（エージェントには禁止）: PR を作ってマージ → CI が Cloud Run にデプロイする。
2. **Cloud Run の URL での通しの確認**: デプロイ後、アプリのビルドは不要で
   `.venv/bin/python lumo_extension/e2e.py https://<Cloud Run の URL>` を実行する（鍵は要らない）。
3. **手で確かめる**: パソコンの Chrome で、ホームの案内 → zip を落として入れる → Lumo のタブが自動で読み込み直されて「動いています」になるか
   （ここだけは自動テストで確かめられていない）。iPhone の Safari で「この端末では SNS を遮れません」と出るか。
4. iPhone のアプリと Safari を遮るのはネイティブ版（`feat/lumo-native-ios`、PROBLEM.md SPIKE-32）。

## 3 回目: 拡張機能だけで動くようにした作り直し
- きっかけ: ユーザー「サーバーも立ち上げて拡張機能もインストールして初めて使えるとかだったら話にならない」。11/09 の会話で
  「別々に導入する必要があるのか」と聞かれ、案 1（拡張機能の中にアプリごと入れる）と案 2（案内でつなぐ）を並べていたが、
  無人実行の指示では案 2 で書いていた（指示を書いた側の誤り）。
- やったこと: `lumo_extension/build.sh`（同じ Flutter アプリを拡張機能のページ用にビルドして `app/`、画像を `lumo/` に）、
  ツールバーのボタンと初めて入れたときに中の Lumo を開く、遮る画面はパトロールを始めた Lumo の画面に出す、
  `API_BASE`（報告は Cloud Run）、YouTube の許可は拡張機能の中では `chrome.identity`、`manifest.json` の `key` で ID を固定、
  zip に `app/` `lumo/` を含める、デプロイで `build.sh` を実行、`e2e.py` を拡張機能の中の Lumo で通すように変更。判断は `docs/decisions.md`。
- 確かめたこと: `e2e.py` 11 項目成功、`flutter analyze` / `flutter test`、API の pytest、`node --test`。
- 人間がやること: (1) OAuth クライアント（Web 版と同じもの）の承認済みのリダイレクト URI に
  `https://pogcdfbiphaccabcjjadojoppmmgepgf.chromiumapp.org/` を足す（Google Cloud コンソール → API とサービス → 認証情報 → そのクライアント）。
  (2) main にマージしてデプロイ。(3) 本物の Chrome で、zip を入れたら Lumo のタブが開くこと、パズルのアイコン → Lumo で開くことを確かめる。

## 6. 権限で止まったこと
なし（1 回目は権限ではなく使用量上限で停止）。
