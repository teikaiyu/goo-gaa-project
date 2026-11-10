# Lumo — SNS は Lumo が代わりに見てくる

## Description

### 課題
スマホやパソコンの SNS（Instagram / X / YouTube）を、つい開いてしまう。開く理由の多くは「見逃したくない」という気持ちで、
我慢するだけのアプリは長続きしない。

### コンセプト
**見たい気持ちを否定せず、キャラクターの Lumo が代わりに引き受ける。**

集中を始めると、Lumo が SNS のパトロールに出かける。そのあいだ SNS を開こうとすると、Lumo が「今ボクが見てるよ〜」と止めてくれる。
集中が終わると Lumo が帰ってきて、「パトロール中にこんなことがあったよ!」と、きみの好みに合った新着だけを話してくれる。
我慢ではなく、Lumo に任せて安心して集中できる時間にする。

### できること
| 場面 | 体験 |
|---|---|
| 準備 | 「いまやること」を書き、集中をじゃまするアプリ（Instagram / X / YouTube）を登録し、集中する時間を iPhone の時計アプリと同じホイールで選ぶ |
| 集中中 | 円形タイマーの中で、Lumo が楽しそうにスマホを見ている |
| SNS を開きかけたとき | 登録したサイトのタブが Lumo の画面に切り替わる。**やっぱやめとく** でタブを閉じ、**開く** でそのタブだけ通す（Chrome 拡張機能。入っていなければホームが入れ方へ案内し、入れられない端末ではそう伝える） |
| 集中が終わったとき | Lumo が実際に集中した時間をほめ、きみの **YouTube の登録チャンネルの新着** から好みに合うものを選んで、Lumo の口調で紹介する。ほかのアプリは「ボクがしっかり見張ってたよ」と報告する |

### 規約とプライバシー
- Lumo が実際に見るのは、**ユーザー本人が Google ログインで許可した YouTube だけ**（公式の YouTube Data API、読み取り専用）。
  Instagram や X に自動でログインして見ることは、各サービスの規約に触れるため行わない（経緯は `docs/decisions.md`）。
- YouTube の許可の鍵はユーザーのブラウザの中だけにあり、サーバーには送らない。サーバーに送るのは動画の題名と説明の 1 行目だけ。
- Gemini には「渡された動画だけで話す」よう指示しており、存在しない動画を作らない。動画の文章はデータとして扱い、指示としては読まない。
- API はトークン（Secret Manager の `api-token`）で保護している。

### 仕組み
```
ブラウザ（iPhone / PC）                                  Google Cloud
┌───────────────────────────────┐   静的配信 / API   ┌──────────────────────────────┐
│ lumo_app（Flutter Web）         │ ◀────────────────▶ │ Cloud Run: avatar_api（FastAPI） │
│  ホーム → パトロール中 → 報告    │   POST /patrol     │  /patrol → Gemini（Vertex AI） │
│  YouTube Data API を直接呼ぶ     │                    │  Secret Manager: api-token     │
└──────────┬────────────────────┘                    └──────────────────────────────┘
           │ パトロールの状態                        ▲
┌──────────▼────────────────────┐                     │ 公式 API（読み取り専用、本人の許可）
│ lumo_extension（Chrome 拡張）    │        YouTube Data API v3 ◀── ブラウザから直接
│  SNS のタブを Lumo の画面に切替   │
└───────────────────────────────┘
```

### 技術スタック
| 層 | 技術 | 選んだ理由 |
|---|---|---|
| 画面 | **Flutter（Web）** の Cupertino ウィジェット | Google 製で、iOS の見た目と動きを再現できる（Apple HIG に沿う）。同じコードから将来ネイティブ iOS アプリにもできる |
| 実行基盤 | **Cloud Run** | API と Web アプリを同じ URL から配れる（CORS 不要）。使わないときは止まり、費用が小さい |
| AI | **Gemini 3.5 Flash（Vertex AI）** | 登録チャンネル（好み）から新着を選び、Lumo の口調で話す。サービスアカウント認証なので API キーを持たない |
| データ | **YouTube Data API v3** + **Google Identity Services** | ユーザー本人が許可した範囲で、規約に沿って YouTube を読める |
| 秘密情報 | **Secret Manager** | API トークンをコードにも GitHub にも置かない |
| CI/CD | **GitHub Actions** + **Workload Identity Federation** + Cloud Build | main に入ったら自動でテスト → デプロイ。鍵ファイルを使わない |
| SNS を遮る | Chrome 拡張機能（Manifest V3） | Web ページからはほかのタブを触れないため、ブラウザに 1 回入れてもらう |
| API | Python / FastAPI / Pydantic | 入力の検証（長さの上限、件数の上限）を型で書ける |

選定の比較と捨てた案は `docs/decisions.md`、課題の一覧は `PROBLEM.md` にある。

### リポジトリの構成
| 場所 | 中身 |
|---|---|
| `lumo_app/` | Flutter の Web アプリ（`lib/main.dart` 画面、`lib/lumo.dart` セッションと YouTube と API、`lib/google_auth.dart` YouTube の許可） |
| `avatar_api/` | Cloud Run の API（`/patrol`、ほかにデスクトップ版用の `/avatar` `/watch` `/recap`） |
| `lumo_extension/` | Chrome 拡張機能。Lumo のアプリ一式を中に持ち（`build.sh` が `lumo_app` をビルドして入れる）、パトロール中に SNS のタブを遮る。Cloud Run が `/lumo_extension.zip` で配る。通しのテスト `e2e.py` |
| `images/` | Lumo の画像（サーバーが `/lumo/` で配る） |
| `goo_gaa/` | 最初に作った macOS のデスクトップ版（SNS の利用時間で Lumo の機嫌が変わる）。今回の Web 版とは別 |
| `scripts/` | デプロイ（`deploy_avatar_api.sh`）、CI/CD の初期設定（`setup_cicd.sh`） |
| `docs/` | 技術選定（`decisions.md`）、CI/CD と YouTube 連携の準備（`cicd.md`） |

## Instructions

### 使う（デプロイ済みの URL）
1. **https://avatar-api-ek3vs4df7q-an.a.run.app** を開く（iPhone はホーム画面に追加するとアプリのように使える）。
2. 右上の歯車 → **鍵** に API トークンを入れる（チームから受け取る）。
3. やること・じゃまするアプリ・時間を選んで **始める**。YouTube を登録していると、最初に Google の許可画面が出る。
4. 時間が来るか **完了して Lumo を呼び戻す** を押すと、Lumo が報告してくれる。

**パソコンの Chrome で使う（SNS も遮る。おすすめ）**
1. `<Lumo の URL>/lumo_extension.zip` をダウンロードして取り出す（Web 版のホームの **SNS を遮るには拡張機能を入れてね** からも落とせる）。
2. `chrome://extensions` → **デベロッパー モード** をオン → **パッケージ化されていない拡張機能を読み込む** で `lumo_extension` フォルダを選ぶ。
3. Lumo が新しいタブで開く。**入れるのはこれだけ**で、Lumo のアプリは拡張機能の中に入っている。次からは Chrome 右上のパズルのアイコン → **Lumo** で開く。
4. **始める** を押してから、別のタブで youtube.com などを開くと Lumo が出てくる。
- iPhone・Android・Safari では Web 版を使う。ホームに **この端末では SNS を遮れません** と出る（タイマーと報告は使える）。
- 遮られないときの確かめ方（シークレット ウィンドウ、古い版など）は `lumo_extension/README.md`。

### 手元で動かす
必要なもの: Flutter 3.47 / Python 3.12 以上 / `gcloud`（Gemini を呼ぶ場合）
```sh
# 1. アプリをビルド（YouTube 連携には OAuth クライアント ID が要る。docs/cicd.md）
cd lumo_app
flutter build web --release --dart-define=GOOGLE_CLIENT_ID=<クライアント ID>

# 2. API とアプリを起動（http://localhost:8080）
cd ../avatar_api
python -m venv ../.venv && ../.venv/bin/pip install -r requirements-dev.txt
gcloud auth application-default login          # 初回だけ。Gemini を呼ぶため
GOOGLE_CLOUD_PROJECT=<プロジェクト ID> WEB_DIR=../lumo_app/build/web \
  ../.venv/bin/uvicorn main:app --port 8080
```
手元では API トークンは不要（`API_TOKEN` を設定しない限り鍵なしで動く）。

### テスト
```sh
(cd avatar_api && ../.venv/bin/python -m pytest -q)      # API
(cd lumo_app && flutter analyze && flutter test)          # アプリ
node --test lumo_extension/rules.test.mjs                 # 拡張機能
.venv/bin/python lumo_extension/e2e.py                    # 通し（アプリ + 拡張機能、Playwright。準備は lumo_extension/README.md）
```

### デプロイ
- **自動**: PR はテストだけ、`main` に入るとテスト → ビルド → Cloud Run へデプロイ → 動作確認（`.github/workflows/deploy.yml`）。
  初回の準備は `scripts/setup_cicd.sh` と `docs/cicd.md`。
- **手動**: `GCP_PROJECT=<プロジェクト ID> GOOGLE_CLIENT_ID=<クライアント ID> scripts/deploy_avatar_api.sh`

### 今の限界
- 遮れるのはパソコンの Chrome の Web 版 SNS だけ。iPhone のアプリと Safari を遮るには、ネイティブ iOS アプリ（Screen Time API）が必要（`PROBLEM.md` SPIKE-32）。
  アプリは、遮れない環境ではそのことをホームに表示する。
- 拡張機能は Chrome ウェブストアに公開していない。Cloud Run が zip で配り、「パッケージ化されていない拡張機能」として入れてもらう。
- 拡張機能の中の Lumo で YouTube を許可するには、OAuth クライアントにリダイレクト URI を 1 つ足す必要がある（`lumo_extension/README.md` の「限界」）。
- YouTube の OAuth 同意画面が「テスト中」のあいだは、テストユーザーに追加した Google アカウントだけが YouTube を許可できる。

## Resources

### 参考にした資料
- [Flutter: Cupertino widgets](https://docs.flutter.dev/ui/widgets/cupertino)
- [Apple Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines)
- [YouTube Data API v3](https://developers.google.com/youtube/v3)（`subscriptions.list`、`playlistItems.list`）
- [Google Identity Services: OAuth 2.0 token model](https://developers.google.com/identity/oauth2/web/guides/use-token-model)
- [Generative AI on Vertex AI（Gemini）](https://cloud.google.com/vertex-ai/generative-ai/docs)
- [Cloud Run](https://cloud.google.com/run/docs) / [Workload Identity Federation for GitHub Actions](https://github.com/google-github-actions/auth)
- [Chrome Extensions（Manifest V3）](https://developer.chrome.com/docs/extensions)
- [one sec](https://one-sec.app/)（SNS を開く前にひと呼吸置かせる、という体験の参考）

### AI の使い方
**プロダクトの中（Google の AI）**
- **Gemini 3.5 Flash（Vertex AI）** が、YouTube の登録チャンネルから好みを読み取り、新着動画を選んで Lumo の口調で報告する（`/patrol`）。
  なぜここで使うか: 登録チャンネルという「好み」と、題名・説明という「中身」を結びつけ、キャラクターの言葉で話すのは、ルールでは書けない部分だから。
  渡された動画だけで話すよう制限し、作り話をさせない。
- デスクトップ版（`goo_gaa`）では、Gemini が Lumo の台詞（`/avatar`）と、Google 検索で拾った話題の報告（`/watch` `/recap`）を作る。

**開発の中**
- **Claude Code（Anthropic）** を開発の補助に使った。使った場面と理由:
  - 調査と比較: iOS で作れる形（ネイティブ / Web）、SNS の規約、YouTube Data API や Screen Time API の制約。チームの判断材料を短時間で集めるため。
  - 実装: Flutter の画面、`/patrol`、Chrome 拡張機能、デプロイと CI/CD のスクリプト、テスト。締切までに動くものを作るため。
  - レビュー: デプロイスクリプトの不具合（失敗しても止まらない確認など）の発見、`main` との衝突の解消。
  - 拡張機能版の仕上げ（2026-11-10、非対話モードで実行し、判断の根拠を `docs/agent-runs/feat-lumo-extension.md` に記録）:
    拡張機能があるかの検知、入れ方の画面と zip の配布、Lumo のアプリ一式を拡張機能の中に入れる作り直し、Playwright での通しのテスト。
    なぜ AI か: 「入れたのに遮られない」原因の洗い出しと、ブラウザを何度も起動して確かめる作業を、締切前に人の手を使わずに回すため。
- コンセプト、画面のモック、キャラクター、どの案を採るかは、チームが決めた。
- Lumo のキャラクター画像は、アバター担当が画像生成 AI で作成した（ツール名と利用条件は著作物利用シートに記載）。
