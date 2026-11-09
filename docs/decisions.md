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
