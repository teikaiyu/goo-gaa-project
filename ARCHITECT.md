# ARCHITECT.md - 設計書

> 最終更新: 2026-11-05 / 対象: Phase 1（SNS 滞在時間の計測コア）
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
├── requirements.txt       # pyobjc-framework-Cocoa
├── .gitignore             # .env / .venv/ / __pycache__/
├── goo_gaa/
│   ├── __init__.py
│   ├── classifier.py      # [純粋] アプリ名 / URL ホスト -> SNS か否か
│   ├── usage_tracker.py   # [純粋] SNS 秒数・総秒数の累積（monotonic、スリープ除外）
│   ├── watcher_macos.py   # [OS依存] 前面アプリ名 + ブラウザ URL の取得
│   └── main.py            # ポーリングループ + Graceful Shutdown
└── tests/
    └── test_core.py       # classifier / usage_tracker の境界値テスト
```

実行: `python -m goo_gaa.main`（`.venv` は `uv venv --python 3.12 .venv` で作成）

## 3. Architecture & Data Flow

責務分離の原則: **OS 依存コードは `watcher_macos.py` だけ**。判定と計測は純粋関数・純粋クラスにして
OS なしでテストできるようにする。

```
          1s ごと (main.py, Event.wait)
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
        標準出力（集計値のみ。URL・アプリ名は出さない）
```

### データモデル

| 型 | フィールド | 備考 |
| :--- | :--- | :--- |
| `Snapshot` (NamedTuple) | `app_name: str \| None`, `url: str \| None` | `url` は対応ブラウザのみ。ウィンドウタイトルは取得しない |
| `UsageTracker` | `social_seconds: float`, `total_seconds: float` | 直前サンプルの状態に経過時間を加算 |

### 外部通信スキーマ

未確定。Phase 2 以降でアバター UI / Gemini 連携を設計する際にここへ JSON 構造を追記する（PROBLEM.md [SPIKE-05]）。

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

### 4.8 `frontmostApplication()` は run loop を回さないと更新されない（Spike の結論）

`NSWorkspace.frontmostApplication()` は呼び出しごとに OS へ問い合わせず、**run loop 経由の通知で更新される
キャッシュ値**を返す。素の Python スクリプトには run loop がないため、起動時の値（ターミナル）のまま固定され、
ブラウザへ切り替えても検知できなかった。`get_snapshot()` の先頭で run loop を 0.05s 回して解決した。
（調査の経緯は PROBLEM.md [SPIKE-01]）

## 5. 技術スタックと要件との関係

| 項目 | 現状 | 要件 (REQUIREMENTS.md) |
| :--- | :--- | :--- |
| 実行基盤 | ローカル macOS のみ | Google Cloud の実行基盤を 1 つ以上使用が必須（**未対応**） |
| Google 技術 | 未使用 | Gemini / Google Cloud がコアであること（**未対応**） |
| カテゴリー | 未決定 | 医療・福祉 / 観光 / 教育 / エンタメ / クリエイティブのいずれか（**未決定**） |

→ [SPIKE-05] で扱う。
