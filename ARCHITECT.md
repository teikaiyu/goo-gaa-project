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
│   ├── gemini.py          # Google 呼び出しはここだけ（台詞 / メモの下調べ = 構造化出力 + 検索グラウンディング、画像生成は任意）
│   ├── main.py            # POST /avatar・POST /research、トークン検証、Google 障害時のフォールバック
│   ├── requirements.txt / requirements-dev.txt
│   ├── tests/test_api.py  # 偽 Gemini でのテスト（ネットワーク不要）
│   ├── tests/test_research.py  # /research（要約 + 次の一歩 / 障害時 fallback / 入力上限 / トークン / メモを log に出さない）
│   └── README.md          # API・画像の命名規則・環境変数・デプロイ手順
├── goo_gaa/
│   ├── __init__.py
│   ├── classifier.py      # [純粋] アプリ名 / URL ホスト -> SNS か否か
│   ├── usage_tracker.py   # [純粋] SNS 秒数・総秒数の累積（monotonic、スリープ除外）
│   ├── watcher_macos.py   # [OS依存] 前面アプリ名 + ブラウザ URL の取得
│   ├── monitor.py         # [スレッド] ポーリングループ。state() が UI との唯一の契約
│   ├── main.py            # CLI 表示（デバッグ / ヘッドレス用）
│   ├── avatar_client.py   # [スレッド] Cloud Run を呼ぶ AvatarFeed + 設定（URL / トークンは環境変数）
│   ├── local_avatar.py    # [純粋] 同梱の起動時画像（happy）を data: URL にする。失敗しても None
│   ├── notes.py           # [スレッド安全] メモの保存（~/Library/Application Support/goo-gaa/notes.json、原子的書き込み）
│   ├── notes_research.py  # [スレッド] 新しいメモを裏で Cloud Run に下調べさせる NoteResearcher（失敗したメモは再試行）
│   ├── app.py             # デスクトップウィジェット起動（pywebview）+ JS 公開 API（get_state / get_avatar_image / add_note / list_notes / delete_note / set_watching）
│   └── web/               # [UI] 差し替え可能な見た目レイヤー
│       ├── index.html     # カード構造: アバター枠 + 2 つの画面（メモ / SNS 見張り中）+ 小さな時間表示
│       ├── style.css      # 色はトークン化（:root の CSS 変数）
│       ├── app.js         # メモ入力・一覧、画面切替、報告（下調べ結果）の表示。Avatar の中身は知らない
│       └── avatar.js      # ★アバター差し替え点（mount / update の 2 関数）。既定は画像 + 台詞の表示
├── .env.example           # AVATAR_API_URL / AVATAR_API_TOKEN の雛形（.env は ignore 対象。コミット禁止）
└── tests/
    ├── test_core.py       # classifier / usage_tracker の境界値テスト
    ├── test_monitor.py    # Monitor（偽サンプラ・偽クロック）のテスト
    ├── test_avatar_client.py  # AvatarFeed（偽 fetch）と実際に送信される内容（ローカル HTTP サーバ）のテスト
    ├── test_notes.py      # NoteStore（保存・再起動・上限・破損ファイル・コピー）と NoteResearcher（再試行・削除競合・停止）
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

### 4.13 方向転換: 「アバターが代わりに SNS を見る」+ メモと下調べ（2026-11-09）

**新しい体験**: ユーザーは気になったことを軽くメモする → アバターが裏で下調べする → 「SNS 見といて」と頼むと、アバターは
下調べした内容を報告し、SNS を見に行く。その間ユーザーは別の作業ができる。（以前の「見すぎると不機嫌になる」は、時間表示と
`/avatar` の機嫌としてそのまま残してある。）

**画面は 2 つ（ウィンドウは 240x330 のまま）**: `memo`（入力欄・メモ一覧・「SNS見といて」）と `watch`（見張り中: 下調べの報告・「戻る」）。
`card[data-view]` で切り替え、状態は Python の `Api._watching`（`get_state()` の `watching`）が持つ。

**データの流れ**: 入力 → `Api.add_note` → `NoteStore`（ローカル JSON）→ `NoteResearcher` が起こされる → `POST /research {note}` →
`{summary, next_step, source}` → `NoteStore.set_research`。ページは 5 秒ごとに `list_notes` で結果を拾う。

| 判断 | Pros | Cons |
| :--- | :--- | :--- |
| **メモはローカル JSON（採用）** vs SQLite / クラウド保存 | 依存なし・ユーザーが読める / 消せる。最大 50 件のため十分。原子的書き込み（一時ファイル → rename）で途中終了しても壊れない | 複数端末で共有できない（ハッカソンの範囲外） |
| **下調べは Cloud Run の `/research`（採用）** vs デスクトップから Gemini を直接 | 認証情報・モデル ID・グラウンディングの変更をサーバーで完結。トークンの置き場が既存と同じ | メモ本文が端末の外に出る唯一の経路（下記） |
| **Google 検索グラウンディング付き（採用）+ 失敗時は検索なしで再試行** | 「下調べ」に最新の事実が入る。検索と構造化出力の併用が不可でも動く | 検索ありは遅く高い。**実 Gemini での併用は未確認**（PROBLEM.md [SPIKE-23]） |
| **失敗したメモは pending のまま再試行（採用）** | ネットワーク断・429 でもメモは失われない。次の周期（60 秒）か次のメモ追加で再挑戦 | 長く失敗すると「下調べ中」が続く |
| **見張りは「報告 + 状態」だけ（暫定）** | 画面と体験の骨格を先に固める | **SNS の中身を実際に取得する処理は未実装**（[SPIKE-24]） |

**プライバシー**: これまでは集計値（秒数・時刻）しか送らなかった。メモ本文は **ユーザー自身が書いた文章** で、下調べの目的でのみ
送る（300 文字上限）。サーバーはメモ本文を log に出さない（エラー種別と HTTP コードのみ。テストで固定）。プロンプトでは
メモを「データであって指示ではない」と明示し、画面にはすべて `textContent` で表示する（AI の返答を HTML として解釈しない）。

**デプロイ（CI/CD）**: `scripts/deploy_avatar_api.sh` — ① avatar_api のテスト（赤なら中止）② `gcloud run deploy --source .`
（Secret Manager の `API_TOKEN`・実行用サービスアカウント・`--max-instances` 上限）③ スモークテスト（`/health` が 200、
`/avatar` と `/research` がトークンなしで 401）。設定は環境変数のみ（`GCP_PROJECT` 必須）で、手元でも CI でも同じ手順。

## 5. 技術スタックと要件との関係

| 項目 | 現状 | 要件 (REQUIREMENTS.md) |
| :--- | :--- | :--- |
| 実行基盤 | Cloud Run 用サービスをコード化済み（**未デプロイ**。ローカルで動作確認のみ） | Google Cloud の実行基盤を 1 つ以上使用が必須（**デプロイするまで未達**） |
| Google 技術 | Gemini（台詞）を実装済みだが **実 Gemini は未検証**。モデル ID は未確認 | Gemini / Google Cloud がコアであること（**検証待ち**） |
| カテゴリー | 未決定 | 医療・福祉 / 観光 / 教育 / エンタメ / クリエイティブのいずれか（**未決定**） |

→ [SPIKE-05] で扱う。
