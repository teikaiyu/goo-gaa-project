# 技術選定の記録

## 2026-11-09 チームの方向（上の比較を更新）
- DM に返信するなど、ユーザーの代わりに操作する機能は作らない。
- 核心は「ユーザーが見たくないアプリ・サイトを選ぶと、Lumo が代わりに巡回して報告する」。割り込み（インサート）は二の次。
- iOS では他のアプリの中身を読めない。そのため巡回は Web 経由で情報を取る。
- 割り込みは、そのアプリまたは同じサービスの Web 版を開いたときに「Lumo が楽しそうにスマホを見ている画面」を出す。
- 参考：one sec。登録したサイトを開くと、深呼吸の画面を挟んでから進むか決めさせる。禁止はせず手間を足すだけ。データは端末の中だけに置く。iOS 版は Screen Time とショートカット、Safari 拡張を使う。

- 大事なのは、本当に巡回しているかではなく、Lumo が楽しそうに代わりに見てくれることで、ユーザーがやるべきことに集中できる体験。
- 集中時間のあいだ見続けることはしない。集中時間が終わったときに一度だけ少し取ってきて報告する。
  例：Instagram ならフォロー中の人のストーリー（誰が何をしていたか）、X なら上位 10 件の投稿。

### 巡回の経路（サービスごと）
| サービス | 公式に取れる経路 | 取れないもの・注意 |
|---|---|---|
| YouTube | YouTube Data API v3（Google 技術、無料枠あり）、チャンネルの RSS | なし（公開動画のみ） |
| Reddit | サブレディットの `.rss` | 公式 API は 2023 年以降、商用利用が制限されている |
| Bluesky | 公開 API（認証なしで公開投稿を取れる） | なし |
| X | 読み取りできる API は有料（Basic 以上） | ログインした状態で中身を取る（スクレイピング）のは規約違反 |
| Instagram | Graph API はビジネス・クリエイターの自分のアカウントのみ。Basic Display API は 2024/12 に終了 | 他人のフィードやストーリーは取れない |
| TikTok | Research API は研究者向けのみ | 一般のアプリからは取れない |
| どれでも（ログインして見る） | Gemini Computer Use（プレビュー）＋クラウド上のブラウザに、ユーザー本人のログイン状態を渡して巡回させる。リールの動画は Gemini の動画理解で要約できる。Meta Muse が Instagram でやっていることに近い | 技術的には作れる。ただし Muse は Meta 自身の機能なので許されている。第三者が自動で見るのは Instagram・X の規約（自動化された手段でのアクセス禁止）に触れ、アカウント停止の恐れがある。ログイン情報の預かり、二段階認証、bot 検知、Cloud Run の費用（クレジット $20）も課題 |
| どれでも | 今の `/watch`（Gemini＋Google 検索）で、そのサービスで話題になっていることを公開 Web から拾う | 個人のタイムラインではなく、世の中の話題になる |

### 割り込みの経路（iOS）
| 開いたもの | 方法 | 必要なもの |
|---|---|---|
| ネイティブアプリ（Instagram など） | ショートカットのオートメーション「App が開かれたとき → Lumo の URL を開く」 | ユーザーが自分で設定する。実行したことを知らせる通知が出る |
| Safari で開いた Web 版 | Safari Web Extension | 中身を入れるネイティブアプリが必要（Xcode と Apple Developer 登録） |
| PC の Chrome で開いた Web 版 | Chrome 拡張（one sec と同じ方式） | Chrome ウェブストアへの公開、または「パッケージ化されていない拡張機能」として読み込む |

## iOS 版の形：ネイティブ SwiftUI か iOS 向け Web アプリか（2026-11-09・**未決定**）

前提：モック（https://claude.ai/artifact/VGvcY1giUJonVmBgb8vgtp）の4画面
「ホーム → 割り込み → パトロール中 → 報告」に実装を合わせる。モックは Android 想定だが、iOS 向けに作り直す。

### どちらの案でも変わらない iOS の制約
- **他のアプリの通知は読めない。** Android の `NotificationListenerService` にあたる仕組みが iOS にはない。
  そのため報告の中身は、すでにある Cloud Run の `/watch`（Gemini＋Google 検索で話題を拾う）と `/recap` で作る。
  モックにある「届いた通知を大事そう／あとでいいに分ける」と「DM に返信する」は、そのままでは作れない。
- **SNS の利用時間を自分で計る方法もない。** 計るには Screen Time API が必要（ネイティブ案のみ）。
- バックエンド（Cloud Run の `avatar_api/`）と Lumo の画像（`images/`）は、どちらの案でもそのまま使える。

### 比較

| | A. ネイティブ SwiftUI | B. iOS 向け Web アプリ（PWA） |
|---|---|---|
| 「割り込み」（SNS を開いた瞬間） | Screen Time API（FamilyControls / ManagedSettings）の遮る画面（Shield）。画面に置けるのはアイコン・文言・ボタン2つまでで、Lumo のアニメや画面の切り替えはできない | ショートカットのオートメーション「Instagram が開かれたとき → このページの URL を開く」。iOS 17 以降は確認なしで実行できるが、実行したことを知らせる通知は消せない。ユーザーが自分で設定する手間がある（one sec などの既存アプリと同じ方式） |
| 見た目・操作（HIG） | 標準部品で HIG どおりになる。触覚フィードバックや Dynamic Type も標準で使える | HIG に寄せて作り込める（SF フォント、セーフエリア、44pt 以上のタップ領域）。ただし標準部品ではない |
| 必要な準備 | Xcode（この Mac には未インストール。数GB）、**有料の Apple Developer Program**（無料の Personal Team では FamilyControls を有効にできない）、実機（Simulator では Screen Time を確かめにくい） | なし。今ある環境で作れる |
| 審査員が試せるか | TestFlight での配布には別の distribution entitlement が必要で、承認に数日〜数週間かかる。**11/10 の提出には間に合わない見込み** | URL を開けば誰でも試せる |
| 実行基盤の要件 | アプリ自体は Google の実行基盤に乗らない（Cloud Run の API 側で要件を満たす） | Firebase Hosting に置けば、それ自体が要件を満たす |
| Google 技術の見せ方 | Firebase iOS SDK で Firebase AI Logic を使える | Firebase Hosting と Firebase AI Logic（Web SDK）、または今の Cloud Run の API |
| 締切（11/10 19:00）までの現実性 | 低い。準備だけで半日かかり得るうえ、entitlement が取れないと割り込みを作れない | 高い。今のバックエンドをそのまま使える |
| 捨てるもの | 開発用のビルドは実機1台でしか見せられない | アプリストアの配布、ネイティブらしい手触り、利用時間の計測 |

### 決めること（チーム）
1. A と B のどちらにするか
2. 報告の中身を「Lumo が見てきた話題（`/watch`）」にする前提でよいか
3. 「DM に返信する（5分）」ボタンの扱い（iOS では DM を読めないので、「Instagram を開く（5分）」などに変える必要がある）

### 参考
- [Configuring Family Controls（Apple）](https://developer.apple.com/documentation/xcode/configuring-family-controls.md)
- [Personal Team では FamilyControls を有効にできない（Apple Developer Forums）](https://developer.apple.com/forums/thread/852204)
- [Distribution entitlement の承認待ち（Apple Developer Forums）](https://developer.apple.com/forums/thread/826427)
- [オートメーションの確認なし実行（Apple サポート）](https://support.apple.com/guide/shortcuts/apd602971e63/ios)
- [iOS 17 で通知が必須に（Matthew Cassinelli）](https://matthewcassinelli.com/automations-run-immediately-shortcuts-notifications)
- [one sec のセットアップ（ショートカット方式の例）](https://one-sec.app/setup)

## 2026-11-09 決定：iOS 向け Web アプリ（Flutter）＋ ログインして本当に見る
- **形**：iOS 向け Web アプリ（チームが決定）。Xcode も Apple Developer 登録も不要で、審査員は URL で試せる。
- **UI 部品**：Flutter の Cupertino ウィジェット（Google 製で、iOS の見た目と動きを再現する）。
  - 捨てた案：Material Web（Google 製だが Android 風の M3）、Ionic・Framework7・Konsta UI（Google 技術ではない）。
  - 同じコードから、あとでネイティブの iOS アプリも作れる。
- **報告の中身**：Gemini Computer Use がログイン済みのヘッドレス Chromium（Playwright）を数ステップだけ操作し、
  Gemini がスクリーンショットを読んで報告を書く（`/patrol`）。集中が終わる 90 秒前に一度だけ見に行く。
  失敗したら `/watch`（Gemini＋Google 検索）で、そのアプリで話題になっていることを伝える。
- **安全のための制限**：文字の入力はできない（投稿・送信・検索をさせない）。SNS 以外のサイトには行かない。
  確認が必要と判断された操作では止まる。プロンプトインジェクション検知を有効にしている。
  ログイン情報は Secret Manager に置き、リポジトリには入れない。テスト用アカウントを使う（規約違反でアカウントを止められる恐れがあるため）。
- **配信**：Cloud Run が API と Web アプリを同じ URL から配信する（CORS 不要）。

## 2026-11-09 決定：Lumo が実際に見るのは、ユーザー本人が許可した YouTube だけ
- **理由**：ログインした状態の Instagram などを自動で見る方法（Gemini Computer Use + ヘッドレスブラウザ）は、
  Instagram・X・YouTube の規約（自動の手段での収集の禁止）に触れる（PROBLEM.md SPIKE-33）。規約に触れるならやらない。
- **新しい形**：ユーザーは集中をじゃまするアプリ（Instagram / X / YouTube）を登録する。集中中は全部を遮る（Chrome 拡張機能）。
  Lumo が実際に見るのは YouTube だけで、**公式の YouTube Data API（読み取り専用）を、ユーザーが Google ログインで許可した範囲で** 使う。
  登録チャンネル（= 好み）と、その新着動画を取り、Gemini が好みに合うものを選んで Lumo の口調で「パトロール中にこんなことがあったよ!」と話す。
  - 許可の鍵（アクセストークン）はユーザーのブラウザの中だけ。YouTube へはブラウザから直接取りに行き、Lumo のサーバーには動画の題名・説明の短い抜粋だけを送る。
  - 呼び出しは 1 回あたり約 50 ユニット（無料枠は 1 日 1 万）。
- **捨てた案**：
  | 案 | 捨てた理由 |
  | :--- | :--- |
  | ログインした SNS を自動で見る（Computer Use） | 規約違反。アカウント停止の恐れ。他人の投稿を同意なく AI に送る |
  | Google 検索で公開の話題だけを拾う（`/watch`） | 規約は問題ないが、その人に合った話にならない |
  | X の公式 API | 読み取りは有料（月額 $200〜） |
  | Instagram Graph API | ビジネス・クリエイターの自分の投稿しか取れない。フォロー先は取れない |
- **消したもの**：`/patrol` の Computer Use とブラウザ操作（`avatar_api/patrol.py`）、Playwright と Chromium、SNS のログイン保存スクリプト。git の履歴には残る。

## 2026-11-10 拡張機能を「見つけられる・手に入れられる」ようにする
前提（11/09 夜〜11/10 の会話）：URL を開くだけでは SNS を遮れない（ブラウザの決まり）。当面は Chrome 拡張機能で進める（PROBLEM.md SPIKE-32）。
実際に「拡張機能を入れたのに遮られない」「拡張機能が別に要ることに気づけない」が起きた。

### アプリが拡張機能に気づく方法
| 案 | 長所 | 短所 |
|---|---|---|
| **A. 拡張機能がページに目印を付ける（`<html data-lumo-extension>`）**（採用） | アプリの起動前に付くので、待たずに同期的に分かる。権限が増えない | 拡張機能を後から入れたらページの読み込み直しが要る → 拡張機能が入ったときに Lumo のタブを読み込み直す |
| B. ページから `postMessage` で問い合わせ、拡張機能が答える | 目印が要らない | 答えが来ないことを「入っていない」とみなすまで待つ必要がある |
| C. `externally_connectable` でページから拡張機能に直接送る | Chrome 公式の仕組み | 拡張機能の ID が要る。zip から入れると ID が入れた場所ごとに変わるので使えない |

### 拡張機能の配り方
| 案 | 長所 | 短所 |
|---|---|---|
| Chrome ウェブストアに公開 | 1 クリックで入る | 審査に数日。締切に間に合わない。登録料（$5）。今回は公開しない方針 |
| **アプリ（Cloud Run）が `/lumo_extension.zip` で配る**（採用） | 今ある配信（`avatar_api`）に数行足すだけ。デプロイ中のアプリといつも同じ版。GitHub を見せなくてよい | デベロッパー モードと「パッケージ化されていない拡張機能を読み込む」が要る → 画面で手順を案内する |
| GitHub からリポジトリを落としてもらう | 作るものがない | 審査員に Git やフォルダ構成を説明する必要がある |
- zip はリクエストのたびに `lumo_extension/` から作る（テストのファイルは入れない）。ビルドの手順を増やさず、手元でも Cloud Run でも同じに動く。
- zip の中はフォルダに入れず、ファイルを直に置く。Windows の「すべて展開」は zip 名のフォルダを作るため、中にもフォルダがあると二重になり、外側を選ぶと読み込めない。

### 遮れない端末の扱い
- iPhone・Android・Safari・Firefox では「この端末では SNS を遮れません」とホームに正直に出す（タイマーと報告は使える）。
  判定はブラウザの種類（User-Agent の `Chrome/`）とパソコンかどうか。入っている拡張機能の目印があれば、それを最優先する。

## 2026-11-10 Lumo のアプリを拡張機能の中に入れる（入れるのは拡張機能 1 つだけ）
前提：11/09 の会話で「拡張機能と Web アプリを別々に導入する必要があるのか」という問いが出ていた（チームの答えは「入れるのは 1 つで全部動くべき」）。
上の「見つけられる・手に入れられる」だけでは、拡張機能を入れたうえで Web 版の URL も開く必要が残っていた。
| 案 | 長所 | 短所 |
|---|---|---|
| **A. 同じ Flutter アプリを拡張機能のページとしてビルドし、拡張機能に同梱**（採用） | 入れるのは拡張機能だけ。画面のコードは Web 版と 1 つのまま。遮る画面も拡張機能の中で出る | 拡張機能が約 33MB（CanvasKit を同梱。拡張機能のページは CDN を読めない）。YouTube の許可は `chrome.identity` に切り替え、OAuth クライアントにリダイレクト URI の追加が要る |
| B. 拡張機能のポップアップに、別に作った小さな画面を置く | 軽い | 画面を 2 つ作って保つことになる。手で UI を書くことになる（UI は保守されている部品で作る方針に反する） |
| C. 今のまま（Web アプリ + 拡張機能、案内でつなぐ） | 作り直しがない | 2 つ入れて・開く必要があり、「入れるだけで動く」にならない |
- 報告の文章（Gemini）はデプロイ済みの Cloud Run の `/patrol` を呼ぶ（`API_BASE`）。拡張機能の `host_permissions` で呼ぶので、サーバーに CORS は足さない。
- 拡張機能の ID は `manifest.json` の `key`（公開鍵）で固定。zip から入れても ID が変わらないので、OAuth のリダイレクト URI を 1 つに決められる。秘密鍵は作ったあと保存していない（ストアに出さないので不要）。
- Web 版（Cloud Run の URL）は残す。iPhone ではそちらを使う。
