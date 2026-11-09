# ARCHITECT.md - 設計書

> 最終更新: 2026-11-05 / 対象: Phase 1（SNS 滞在時間の計測コア）+ デスクトップ表示（タイマーのみ。アバターは差し替え枠）
> このファイルはコード変更に合わせて更新する（AGENTS.md §3）。

## 1. Overview

デスクトップ常駐型の自己実現支援エージェント。ドゥームスクロール（SNS の受動的な長時間閲覧）を検知し、
アバターの機嫌で気づかせる。Phase 1 では「SNS にどれだけ時間を使っているか」を計測するコアのみを実装済み。

## 2. Directory Structure

```
goo-gaa-project/
├── AGENTS.md              # 開発・メンタリング規約
├── REQUIREMENTS.md        # ハッカソン要件（提出物・審査基準・技術制約）
├── ARCHITECT.md           # 本書
├── PROBLEM.md             # 課題表（Spike / Backlog）
├── requirements.txt       # pyobjc-framework-Cocoa, pywebview
├── .gitignore             # .env / .venv/ / __pycache__/
├── Dockerfile             # Cloud Run 用イメージ。images/ を COPY するためルートに置く
├── .dockerignore          # 許可リスト方式（.env / .git / .venv / デスクトップ側を含めない）
├── images/                # アバター画像（デザイナーが push）。Lumo_*.png 7 枚（機嫌への対応は images.py の表）
├── scripts/
│   └── deploy_avatar_api.sh   # CI/CD 用: テスト -> Cloud Run デプロイ -> スモークテスト（環境変数で設定）
├── avatar_api/            # [クラウド] Cloud Run サービス。デスクトップとは別ディレクトリ
│   ├── mood.py            # [純粋] 社会メディア秒数 -> 機嫌 4 段階、フォールバック台詞
│   ├── schemas.py         # リクエスト / レスポンスの JSON 契約
│   ├── images.py          # MOOD_IMAGES（機嫌 -> ファイル名の表）と検索（大文字小文字を区別しない）
│   ├── gemini.py          # Google 呼び出しはここだけ（台詞 / 見張り = 構造化出力 + 検索グラウンディング / 感想、画像生成は任意）
│   ├── main.py            # POST /avatar・/watch・/recap、トークン検証、Google 障害時のフォールバック
│   ├── requirements.txt / requirements-dev.txt
│   ├── tests/test_api.py  # 偽 Gemini でのテスト（ネットワーク不要）
│   ├── tests/test_recap.py     # /recap（items から感想 / 障害時 fallback / 入力上限・トリム / トークン / items を log に出さない）
│   ├── tests/test_watch.py     # /watch（報告 + 最大 3 件 / リクエスト本文が不要 / 障害時 fallback / トークン / /research が無いこと）
│   └── README.md          # API・画像の命名規則・環境変数・デプロイ手順
├── goo_gaa/
│   ├── __init__.py
│   ├── classifier.py      # [純粋] アプリ名 / URL ホスト -> SNS か否か
│   ├── usage_tracker.py   # [純粋] SNS 秒数・総秒数の累積（monotonic、スリープ除外）
│   ├── watcher_macos.py   # [OS依存] 前面アプリ名 + ブラウザ URL の取得
│   ├── monitor.py         # [スレッド] ポーリングループ。state() が UI との唯一の契約
│   ├── main.py            # CLI 表示（デバッグ / ヘッドレス用）
│   ├── avatar_client.py   # [スレッド] Cloud Run を呼ぶ AvatarFeed + 設定（URL / トークンは環境変数）
│   ├── local_avatar.py    # [純粋] 同梱画像を data: URL にする（起動時の happy / 見張り中の 2 枚からランダム）。失敗しても None
│   ├── watch.py           # [スレッド] WatchSession: 「SNS見といて」の 1 回分。見続けて蓄積 → 「戻る」で感想（/recap。失敗時は端末で作る）
│   ├── app.py             # デスクトップウィジェット起動（pywebview）+ JS 公開 API（get_state / get_avatar_image / set_watching）
│   └── web/               # [UI] 差し替え可能な見た目レイヤー
│       ├── index.html     # カード構造: アバター枠 + 2 つの画面（ホーム / SNS 見張り中）+ 小さな時間表示
│       ├── style.css      # 色はトークン化（:root の CSS 変数）。見た目はデザインモック準拠（4.15）
│       ├── app.js         # 画面切替、見てきた内容の報告（台詞 + 一覧）。Avatar の中身は知らない
│       └── avatar.js      # ★アバター差し替え点（mount / update の 2 関数）。既定は画像 + 台詞の表示
├── .env.example           # AVATAR_API_URL / AVATAR_API_TOKEN の雛形（.env は ignore 対象。コミット禁止）
└── tests/
    ├── test_core.py       # classifier / usage_tracker の境界値テスト
    ├── test_monitor.py    # Monitor（偽サンプラ・偽クロック）のテスト
    ├── test_avatar_client.py  # AvatarFeed（偽 fetch）と実際に送信される内容（ローカル HTTP サーバ）のテスト
    ├── test_watch.py      # WatchSession（見ている内容の蓄積 / 感想 / 感想の失敗時 / オフライン / 古い返事の無視 / 停止）
    └── test_local_avatar.py   # 起動時画像（同梱 / クラウドとの優先順位 / 失敗時 None / 実ファイルの存在）のテスト
```

実行:
- ウィジェット: `python -m goo_gaa.app`（右上 × / ホバーで表示、で終了）
- CLI: `python -m goo_gaa.main`
- `.venv` は `uv venv --python 3.12 .venv` で作成

## 3. Architecture & Data Flow

責務分離の原則: **OS 依存コードは `watcher_macos.py` だけ**。判定と計測は純粋関数・純粋クラスにして
OS なしでテストできるようにする。

```
          1s ごと (monitor.py のスレッド, Event.wait)
                    │
                    ▼
   ┌──────────────────────────────┐
   │ watcher_macos.get_snapshot() │  OS 依存
   │  1. run loop を 0.05s 回す   │  <- NSWorkspace のキャッシュ更新
   │  2. frontmostApplication()   │  権限不要
   │  3. ブラウザなら osascript   │  Automation 権限
   └──────────────┬───────────────┘
                  │ Snapshot(app_name, url)
                  ▼
   ┌──────────────────────────────┐
   │ classifier.is_social()       │  純粋関数 (host のみ参照)
   └──────────────┬───────────────┘
                  │ bool
                  ▼
   ┌──────────────────────────────┐
   │ UsageTracker.update(b, now)  │  now = time.monotonic()
   └──────────────┬───────────────┘
                  │ social_seconds / total_seconds
                  ▼
        Monitor.state()  ← Lock で保護。集計値のみ（URL・アプリ名は含めない）
                  │ JSON: {"social_seconds": float, "total_seconds": float}
                  ▼
   ┌──────────────────────────────┐
   │ app.Api.get_state()          │  JS から 1s ごとに pull
   └──────────────┬───────────────┘
                  ▼
   ┌──────────────────────────────┐
   │ web/app.js  render(state)    │
   │   ├─ タイマー HH:MM:SS 表示  │  ← 固定
   │   └─ Avatar.update(state)    │  ← ★差し替え点 (web/avatar.js)
   └──────────────────────────────┘
```

### データモデル

| 型 | フィールド | 備考 |
| :--- | :--- | :--- |
| `Snapshot` (NamedTuple) | `app_name: str \| None`, `url: str \| None` | `url` は対応ブラウザのみ。ウィンドウタイトルは取得しない |
| `UsageTracker` | `social_seconds: float`, `total_seconds: float` | 直前サンプルの状態に経過時間を加算 |

### UI 契約（Monitor → 画面）

```json
{ "social_seconds": 754.0, "total_seconds": 1800.0,
  "avatar": { "mood": "grumpy", "message": "…", "action": "…", "source": "gemini|fallback" } }
```

- `avatar` は **追加フィールド**。クラウドが一度も応答していない間、または未設定の間は `null`（画面はプレースホルダのまま）。
- **画像は state に載せない**（毎秒ブリッジを往復するため）。ページが機嫌の変化時に一度だけ
  `pywebview.api.get_avatar_image(mood)` で取得する（`data:` URL、無ければ `null`）。
- 既存フィールドの名前変更・削除はしない（アバター差し替えを壊さないため）。
- アプリ名・URL・タイトルは契約に含めない（プライバシー）。

### 外部通信スキーマ（デスクトップ → Cloud Run）

```
デスクトップ (Monitor.state)  ──POST /avatar──►  Cloud Run (avatar_api)  ──►  Vertex AI (Gemini)
  Authorization: Bearer <API_TOKEN>                │ mood.py で機嫌を決定（Google 不要）
                                                   │ images/<mood>.<ext> を読む
◄── 機嫌・台詞・行動・画像 ─────────────────────────┘ 台詞だけ Gemini（失敗時はフォールバック）
```

リクエスト（集計値のみ。URL・アプリ名・タイトルを入れるフィールドは存在しない）:
```json
{ "social_seconds": 3000, "total_seconds": 4000, "local_hour": 23, "goal": "study", "include_image": true }
```
レスポンス:
```json
{ "mood": "grumpy", "message": "…", "action": "…",
  "image_base64": "<bytes>|null", "image_mime": "image/png|null",
  "image_source": "file|generated|null", "source": "gemini|fallback" }
```
- `mood` は `happy | uneasy | grumpy | angry`（`avatar_api/mood.py` の `THRESHOLDS` で調整）。
- 追加はするが既存フィールドの改名・削除はしない（UI 契約と同じ方針）。
- `goal` は任意の自由入力（100 文字まで）で Gemini に送られる唯一のユーザー入力。

## 4. "Own the Why"

### 4.1 前面ウィンドウの取得: ポーリング vs イベントフック

| | Pros | Cons |
| :--- | :--- | :--- |
| **ポーリング 1s（採用）** | 実装が単純。スリープ復帰でも自然に動く。ブラウザのタブ切り替えも拾える | 常時わずかな CPU を使う。最大 ~1s の誤差 |
| イベントフック (NSWorkspace 通知) | アイドル時の CPU がほぼ 0。切替時刻が正確 | run loop 必須。ブラウザ内のタブ切替は検知できず別途 URL 取得が必要 |

**採用理由**: 目的は「数分単位のドゥームスクロール」の検知で、1 秒の誤差は許容できる。ブラウザ内のタブ切替は
イベントでは拾えないため、どのみち定期取得が必要になる。

### 4.2 SNS の判定: ネイティブアプリ名 + ブラウザ URL ドメイン

| | Pros | Cons |
| :--- | :--- | :--- |
| **アプリ名 + URL ホスト（採用）** | ブラウザ内のスクロールを捉えられる（実際の主戦場） | Automation 権限が必要。Chrome / Safari のみ対応 |
| アプリ名のみ | 権限不要で最も単純 | ブラウザ利用を見逃す |

### 4.3 ブラウザ URL の取得手段

| 手段 | 必要権限 | 評価 |
| :--- | :--- | :--- |
| **AppleScript (osascript)（採用）** | Automation（ブラウザごと・初回のみ） | 動作確認済み。権限が最小で粒度も十分 |
| ブラウザ拡張 + localhost | macOS 権限なし | 最も堅牢で他 OS にも展開可能だが、別コンポーネントが必要。将来候補 |
| ウィンドウタイトル (CGWindowList) | Screen Recording | タイトルに機密が含まれうる（セキュリティ観点で不採用） |
| Accessibility API | Accessibility | ブラウザ UI 構造に依存し脆い |

### 4.4 実装言語: Python + PyObjC

ハッカソンの短期間で最速に反復できる。AppKit を直接呼べるため OS 層が薄い。Swift は型安全だが
初期セットアップと反復が重い。**環境メモ**: Homebrew の Python 3.14 は `ensurepip` が壊れていたため、
`uv` + Python 3.12 で venv を作成した。

### 4.5 時間計測の設計判断

- `time.monotonic()`: システム時刻の変更・NTP 補正の影響を受けない（`time.time()` は不可）。
- 直前サンプルの状態に経過時間を加算: その区間にユーザーがしていたことが直前の状態だから。
- 1 回のギャップが `max_gap`（= ポーリング間隔 × 5）を超えたら捨てる: スリープ復帰で
  「8 時間 SNS を見ていた」と誤計上しないため。
- 初回サンプルは 0 秒として扱う（基準点がない）。

### 4.6 プライバシー

- 参照するのは **アプリ名と URL ホストのみ**。ウィンドウタイトルは読まない・保存しない。
- ログ / 標準出力は集計秒数のみ。例外として `[warn]` は **ブラウザ名と OS のエラー文言** のみを出す（URL は出さない）。

### 4.7 Graceful Shutdown

`signal` で `threading.Event` を立て、ループは `stop.wait(POLL_SEC)` で待つ。`time.sleep()` と違い
停止要求で即座に起きるため、Ctrl+C / SIGTERM で更新の途中で落ちない。

**ウィジェット（`app.py`）の終了は「後始末 → `os._exit`」**: スレッドの停止（`Monitor.stop()` / `AvatarFeed.stop()`、
いずれも短い `join`）まで行ったら `_exit_now()` でプロセスを確実に終了する。普通に `return` すると、pywebview が
ページへの戻り値返送のために立てる **非デーモンのスレッド**（ウィンドウが既に無いと永遠に待つ）を Python が待ち続けて
ハングするため（再現済み。[SPIKE-22]）。こちらのスレッドは daemon で、保存すべき状態もないので、待つものがない。
出力は `os._exit` がフラッシュしないので、先に明示的にフラッシュする。

### 4.8 `frontmostApplication()` は run loop を回さないと更新されない（Spike の結論）

`NSWorkspace.frontmostApplication()` は呼び出しごとに OS へ問い合わせず、**run loop 経由の通知で更新される
キャッシュ値**を返す。素の Python スクリプトには run loop がないため、起動時の値（ターミナル）のまま固定され、
ブラウザへ切り替えても検知できなかった。`get_snapshot()` の先頭で run loop を 0.05s 回して解決した。
（調査の経緯は PROBLEM.md [SPIKE-01]）

### 4.9 UI: pywebview (HTML/CSS) + 小型フローティングウィジェット

| | Pros | Cons |
| :--- | :--- | :--- |
| **pywebview + HTML/CSS（採用）** | アバターが SVG / Lottie / CSS アセットになり、差し替えがファイル単位で済む。デザインを HTML で素早く反復できる。macOS 標準の WKWebView を使い、既に導入済みの PyObjC を再利用する | 依存が 1 つ増える。Python ⇔ JS の橋渡しを学ぶ必要がある |
| PyObjC (AppKit) ネイティブ | 依存追加なし。実行時が最軽量 | アバター差し替え = 描画 / アニメのコード書き換え。自前の run loop も必要 |
| Tkinter | 標準ライブラリ。最小コード | macOS で透過・枠なしが不安定。見た目が古い。Homebrew の Python は Tk が使えないことがある |

**差し替え設計**: 画面とコアの接点を JSON 1 つ（上記 UI 契約）に絞り、アバターは `web/avatar.js` の
`mount(el)` / `update(state)` だけに閉じ込めた。Python 側とタイマー表示は変更不要。

**Python → JS ではなく JS → Python の pull**: ページが `pywebview.api.get_state()` を 1s ごとに呼ぶ。
Python 側で JS 文字列を組み立てず、スレッド間の呼び出しも単純。将来サーバ（Cloud Run 等）の同じ JSON を
読む構成にも移行しやすい。

**ウィンドウ**: `frameless` + `on_top` + `transparent` + `easy_drag`。実測で layer 25（通常ウィンドウは 0）。
枠なしのため終了手段として、ホバー時だけ出る × ボタンを用意した。

**セキュリティ**: ページは自前ファイルのみ読み込み、JS から呼べる Python は `get_state()` / `quit()` に限定。
pywebview はページ配信用に `127.0.0.1` のランダムポートで待ち受ける（ローカル限定）。CSP は未設定（[SPIKE-12]）。
`_setDrawsTransparentBackground` の deprecation 警告は透過実装由来で、脆弱性ではない。

**スレッド構成**: macOS では GUI がメインスレッドを占有するため、ポーリングは `Monitor` のバックグラウンド
スレッドへ移した（[SPIKE-08] 解決）。GUI モードでも前面アプリの切替が検知されることを実測で確認。

### 4.10 バックエンド: Cloud Run + Vertex AI

| | Pros | Cons |
| :--- | :--- | :--- |
| **Cloud Run → Vertex AI（採用）** | 実行基盤の必須要件を実際に満たす。サービスアカウントで Vertex AI を呼ぶため **API キーがリポジトリにもクライアントにも存在しない**。プロンプトをサーバ側に置け、アプリ再配布なしで人格を調整できる | ネットワークと デプロイが必要。公開エンドポイントは課金悪用の対象 → トークン + 予算アラートで対処。コールドスタートで初回が遅い |
| デスクトップから Gemini 直呼び | 最も単純 | キーが全クライアントに乗る。Google Cloud 上で何も動かず必須要件を満たさない |
| Firebase Hosting + Functions | 要件は満たせる | Hosting は静的で、結局 Functions が要る。Cloud Run 単体より部品が多い |

**機嫌は Gemini ではなく純粋関数 `decide_mood()` が決める**: 決定的でテスト可能、無料、Google 障害時も動く。
Gemini は「台詞と行動提案」の生成だけを担う（構造化出力で JSON の形を強制）。

**障害時の劣化設計**: Gemini が失敗してもリクエストは 200 を返し、固定台詞（`source: "fallback"`）を使う。
Google クライアントは「初回使用時」に生成する（起動時に作ると、設定不足が全リクエストの 500 になるため）。

**セキュリティ**: Cloud Run 上（環境変数 `K_SERVICE` あり）で `API_TOKEN` 未設定なら 503 で起動を拒否。
トークン比較は `hmac.compare_digest`（定数時間）。ログにはエラーの型のみ（メッセージはプロンプトを含みうる）。

### 4.11 アバター画像: ファイル配信を優先、生成は任意

| | Pros | Cons |
| :--- | :--- | :--- |
| **`images/` のファイルを返す（採用）** | デザイナーの絵がそのまま出る。無料・高速・決定的 | 画像追加には再デプロイが必要。JSON に base64 で載せるため大きい画像は不向き（現状 1 応答 約 350 KB） |
| 毎回 Gemini で画像生成 | 絵を用意しなくてよい | 気分ごとに別キャラになりがち。費用と遅延。モデル ID が不安定 |
| Cloud Storage から配信 | 再デプロイ不要 | 追加のインフラと権限 |

**機嫌 → ファイルの対応は表（`MOOD_IMAGES`）で持つ**: デザイナーのファイル名（`Lumo_<表情>.png`、7 表情）を変えずに、
機嫌 4 段階へ対応づけられる。`happy → Lumo_happy` / `uneasy → Lumo_disappointed` / `grumpy → Lumo_annoyed` /
`angry → Lumo_angry`。未割り当ての `calm`（待機）/ `smile`（挨拶）/ `cheering`（達成）は将来の状態用。
検討した代案: デザイナーに `happy.png` 等へ改名してもらう = コード変更は不要だが Lumo の命名と余剰 3 表情を失う。
`<mood>.<ext>` の素の名前もフォールバックとして使える（表の名前が優先）。
実フォルダに全機嫌分の画像があることはテスト（`test_repo_images_cover_every_mood`）で守る。

**`images/` がリポジトリ直下にある理由**: Docker ビルドはビルドフォルダ内のファイルしかコピーできないため、
`Dockerfile` もルートに置き、`avatar_api/` と `images/` の両方をコピーする。

**ファイル名の大文字小文字**: macOS は区別しないが Cloud Run（Linux）は区別する。`Happy.PNG` が手元でだけ動いて
デプロイ後に消えるのを防ぐため、`images.py` は小文字化して比較する（テストあり）。

画像生成は `ENABLE_IMAGE_GENERATION=1` かつ該当ファイルが無い場合のみ（既定は無効）。

### 4.12 デスクトップ → Cloud Run の接続（AvatarFeed）

| | Pros | Cons |
| :--- | :--- | :--- |
| **専用スレッドが 60 秒ごとに呼ぶ（採用）** | UI を止めない。呼び出し頻度とコストが一定。失敗しても最後の応答を残して再試行できる | 機嫌が変わってから画面に出るまで最大 1 周期 + 応答時間（実測 約 22 秒）かかる |
| UI（JS）が毎秒 Python 経由で呼ぶ | 反応が速い | 毎秒ネットワーク呼び出し。Gemini 呼び出しが無駄に増え、クォータ（429）を踏みやすい |
| 機嫌をクライアントで先に計算し、変化時だけ呼ぶ | 呼び出しが最小 | 機嫌の閾値がサーバ（`mood.py`）とクライアントに二重化する |

**画像は機嫌ごとに一度だけ取得**: 通常は `include_image=false`（約 1 KB）で呼び、見たことのない機嫌が返ったときだけ
`include_image=true` で再取得してキャッシュする（最大 4 回。サーバに画像が無い機嫌は `None` として記憶し、聞き直さない）。
1 応答 約 350 KB の画像を毎分運ばないため（[SPIKE-17] への対応）。

**設定は環境変数 / `.env`**（コードにもリポジトリにも入れない）: `AVATAR_API_URL`, `AVATAR_API_TOKEN`,
任意で `AVATAR_REFRESH_SEC`（下限 5 秒）。未設定ならアバターなしでタイマーだけ動く。URL は `https://` 必須
（`localhost` の検証用を除く）。トークンは `repr` に出ない。

**送るのは集計値だけ**: `social_seconds` / `total_seconds` / `local_hour` / `include_image`。テストで
「この 4 項目以外は送らない」ことを固定している。24 時間を超える値はサーバが 422 で拒否するため 86,400 に丸める。

**タイムアウトは 25 秒**: サーバは Gemini を最大 20 秒待ってからフォールバックする。実測で応答が 10 秒を超えることがあり
（通常 5〜6 秒、最大 11.5 秒）、当初の 10 秒では取りこぼした。

**失敗時**: 最後に成功した応答を画面に残し、障害ごとに 1 行だけ警告（エラーの型と HTTP コードのみ。401 = トークン違い、
429 = クォータ、5xx = サーバ側の見分けがつく）。

**停止**: `stop()` は短い `join`（0.2 秒）で諦める。ネットワーク呼び出し中のスレッドは割り込めず、daemon で
保存すべき状態もないため（`Monitor.stop()` と同じ判断）。

**起動時の初期画像（楽観的な最初の画面）**: クラウドの最初の返事は数秒〜十数秒かかり（実測 約 14.5 秒）、オフラインや
`.env` 未設定では来ない。その間アバター枠が空の円だと「壊れている」ように見える。そこで **アプリに同梱した画像を
先に出し、本物の返事が来たら置き換える**。

| | Pros | Cons |
| :--- | :--- | :--- |
| **同梱画像を `get_avatar_image` の後ろ盾にする（採用）** | 起動直後に表示（実測 約 1.5〜2.6 秒 = Python とウィンドウの起動時間）。オフラインでも出る。追加の通信なし。ページ側は同じ呼び出しのまま | 「happy → どのファイル」がデスクトップ側（`local_avatar.py`）にも 1 箇所できる |
| 起動時にクラウドへ先に問い合わせる | 対応表が二重にならない | 初回表示が約 14.5 秒。オフラインでは出ない |
| 画像を `web/` にコピーして `<img src>` 固定 | JS だけで済む | 画像が 2 か所に重複し、差し替えで食い違う |

- **優先順位**: クラウドの画像 → 同梱画像 → なし（プレースホルダ）。`Api.get_avatar_image()` の中で決める。
- **同梱するのは起動時の 1 枚（`happy`）だけ**。全ムードの表は `avatar_api/images.py`（サーバ側）が持ち、二重管理でずれるのを避ける。
- **読み込みは失敗しても落ちない**: ファイルが無い・読めない・画像以外の拡張子なら `None`（従来どおりプレースホルダ）。
- **競合対策**: ページは「最後に頼んだ機嫌」を覚え、古い答えで上書きしない。クラウドが先に答えていたら起動画像は出さない。
- 実リポジトリの `images/Lumo_happy.png` が読めることをテストで固定している（デザイナーの改名・削除に気づくため）。

### 4.13 方向転換: 「アバターが代わりに SNS を見る」（2026-11-09）と、メモ / 下調べの廃止

**新しい体験**: ユーザーが「SNS 見といて」と頼むと、アバターが代わりに SNS の話題を見に行き、その間ユーザーは別の作業ができる
（4.14）。以前の「見すぎると不機嫌になる」は、時間表示と `/avatar` の機嫌としてそのまま残してある。

**画面は 2 つ（ウィンドウは 240x330 のまま）**: `home`（「SNS見といて」のボタン）と `watch`（見張り中: 見ているものの一覧・「戻る」）。
`card[data-view]` で切り替え、状態は Python の `Api._watching`（`get_state()` の `watching`）が持つ。

**廃止したもの（同日）: 気になったことのメモ入力 / メモの保存 / メモの下調べ（`POST /research`）/ メモ由来の `topics`**。
理由と影響:
- 「ユーザーの関心事をアバターが調べる」機能は不要になった。メモが無いので、`/watch` に渡していた `topics`（直近 5 件のメモ）も消し、
  `/watch` は **「いま一般に話題になっていること」を調べる**形になった（リクエストに個人情報が一切ない）。
- **プライバシーが以前の状態に戻った**: 端末の外へ出るのは集計値（`/avatar`: 秒数・時刻）だけ。メモ本文という自由記述は送らない
  （[SPIKE-25] は解消）。`/recap` が送るのは、クラウド自身が返した題・要点・経過分のみ。
- 実装は Git の履歴に残っている（`NoteStore` の原子的書き込み、`NoteResearcher` のバックグラウンド再試行など）。復活させるなら履歴から。

**デプロイ（CI/CD）**: `scripts/deploy_avatar_api.sh` — ① avatar_api のテスト（赤なら中止）② `gcloud run deploy --source .`
（Secret Manager の `API_TOKEN`・実行用サービスアカウント・`--max-instances` 上限）③ スモークテスト（`/health` が 200、
`/avatar` `/watch` `/recap` がトークンなしで 401）。設定は環境変数のみ（`GCP_PROJECT` 必須）で、手元でも CI でも同じ手順。

### 4.15 見た目をデザインモックに合わせる（2026-11-09）

モック「代わりに見てくる モック」（390x844 のスマホ 4 画面）の**視覚言語だけ**を 240x330 のウィジェットに移した。
タスク / タイマー / 通知の振り分けなど、モックにあって本アプリにまだ無い**機能は作っていない**。
- 配色: 面 `#F8FAFD`、白い吹き出し、淡い青のチップ `#D3E3FD`、主ボタン `#1967D2`（トークン化）。
- 吹き出しをアバターの**上**に置く（DOM 順を入れ替え）。ボタンは丸いピル型（主 = 塗り、副 = 枠線）。見た目一覧はチップ化。
- 書体は M PLUS Rounded 1c（Google Fonts）。オフライン時は macOS の丸ゴシックへフォールバック（外部フォント依存は任意）。
- Pros: 既存のロジック・テストに触れない CSS / HTML のみの変更。Cons: 暗い背景用だった旧配色は廃止（ダークモード未対応）、
  フォントの初回読込でネットワークに出る（fonts.googleapis.com）。

### 4.14 アバターが「見ているもの」と「どうだったか」を話す（`/watch` + `/recap`、2026-11-09）

**流れ**: 「SNS見といて」→ `Api.set_watching(True)` が `WatchSession` を起動し、`POST /watch`（本文なし）。
クラウドは Gemini + **Google 検索グラウンディング**で「今話題のこと」を調べ `{report, items[≤3], source}` を返す。
セッションは `WATCH_REFRESH_SEC`（既定 180 秒、下限 30 秒）ごとに見直し、**新しく見たものだけを足していく**（題で重複排除、最大 8 件、新しい順）。
ページは `get_state()["watch"]` = `{status, report, items, recap, trouble}` を 1 秒ごとに読み、
- **見ている間**: アバターの台詞（`#speech`）に「いま見ているもの」の `report`、一覧に「いま見ているもの」。
- **「戻る」**: `set_watching(False)` → `WatchSession.finish()`。実行中の見直しが終わったら、見たもの（`items` + 経過分）を `POST /recap` に送り、
  **「どうだったか」を台詞に出す**（ホーム画面に戻ったあとも 60 秒表示）。まとめている間は「どうだったか、まとめるね…」。

**状態**: `idle → watching → recapping → recap(60 秒) → idle`。「戻る」を押さない限り `watching` が続く。

| 判断 | Pros | Cons |
| :--- | :--- | :--- |
| **検索グラウンディングで「見る」（採用）** vs SNS の API / ブラウザ自動操作 | 各 SNS の有料 API・規約・ログイン問題を避けられる。Google 技術が中核のまま | **本物のタイムラインではない**（Web 上で話題の内容）。デモでは「検索で SNS の話題を見てきた」と説明する |
| **離れている間、定期的に見直して蓄積（採用）** vs 開始時に 1 回だけ | 「見ている間に何があったか」を戻ったときに語れる。長く離れるほど中身が増える | 呼び出しが増える（既定 3 分ごと。429 と費用に注意: [SPIKE-19]）。下限 30 秒で暴走を防ぐ |
| **`/recap` は検索せず、見たものだけから感想を書く** | 新しい事実を足せない = でっち上げが起きない。軽く速い | 感想の材料は `/watch` の返事の質に依存 |
| **感想の失敗時は端末で素朴なまとめを作る（`local_recap`）** | 「戻る」で必ず何か言う。ネットが切れても成立 | 感想というより件数の報告になる |
| **`/watch` は検索なしの再試行をしない** | 検索なしだと見てもいない内容を作ってしまうため。失敗は `trouble` として正直に伝える | Google が不調だと何も見られない |
| **セッション番号で古い返事を捨てる** | 「戻る → もう一度見て」の途中に古い返事が来ても上書きしない | 少しコードが増える |
| **Avatar 契約は変えず、ページが `avatar` を `{mood, message}` で渡す**（見張り中は `mood: "watching"`、感想は `happy`） | 差し替え予定のアバターが台詞の出し方を 1 つ知っているだけで済む | `watching` はサーバーの機嫌ではなく、ページが付ける擬似的な機嫌 |
| **見張り中の絵は 2 枚からランダム（`Lumo_phone_thick_tail.png` / `Lumo_happy_phone.png`）** | 同梱画像なので通信なし・オフラインでも出る。ページは機嫌が変わった時だけ画像を頼むため、**1 回の見張りの間は同じ絵**で、次の見張りで変わる（ちらつかない） | 1 枚 約 1.6 MB（base64 で約 2.2 MB）が橋を 1 回通る。片方のファイルが無ければ残りの 1 枚にする（空の円にしない）。`Lumo_lounging_with_phone.png` はパートナーが `Lumo_phone_thick_tail.png` に改名済み |

**プライバシー**: `/watch` はユーザーの情報を一切送らない。`/recap` はクラウド自身が返した題・要点・経過分だけ。
サーバーは `items` を log に出さない（テストで固定）。

## 5. 技術スタックと要件との関係

| 項目 | 現状 | 要件 (REQUIREMENTS.md) |
| :--- | :--- | :--- |
| 実行基盤 | Cloud Run 用サービスをコード化済み（**未デプロイ**。ローカルで動作確認のみ） | Google Cloud の実行基盤を 1 つ以上使用が必須（**デプロイするまで未達**） |
| Google 技術 | Gemini（台詞）を実装済みだが **実 Gemini は未検証**。モデル ID は未確認 | Gemini / Google Cloud がコアであること（**検証待ち**） |
| カテゴリー | 未決定 | 医療・福祉 / 観光 / 教育 / エンタメ / クリエイティブのいずれか（**未決定**） |

→ [SPIKE-05] で扱う。
