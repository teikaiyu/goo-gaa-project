# CI/CD：いつも最新の main が動く仕組み

## 流れ

```
PR を出す / 更新する ──▶ テスト（API・アプリ）──▶ 結果が PR に表示される
                                                   （赤ならマージしない）

main にマージ ──▶ テスト ──▶ アプリのビルド ──▶ Cloud Run へデプロイ ──▶ 動作確認
                   │赤              （flutter build web）  （新しいリビジョン）   （/health、画面、画像、
                   ▼                                                            鍵なしで 401 になるか）
                デプロイしない
```

- 設定ファイル：`.github/workflows/deploy.yml`
- デプロイは、手で行うときと同じ `scripts/deploy_avatar_api.sh` を使う。手元と CI で手順が食い違わない。
- 同時に 2 つはデプロイしない。続けてマージしたときは、前のデプロイが終わってから次が走る。

## なぜ「いつも最新」になるのか

1. main にマージすると、自動でデプロイが走る。手でデプロイし忘れることがない。
2. Cloud Run はデプロイのたびに新しい**リビジョン**（版）を作る。新しい版が起動に成功してから、URL の行き先がそちらに切り替わる。
   起動に失敗したら、URL は前の版のまま動き続ける。
3. テストが赤ならデプロイしないので、壊れた版が URL に出ることはない。

## 鍵を GitHub に置かない（Workload Identity Federation）

GitHub は、実行のたびに「これは teikaiyu/goo-gaa-project の main の実行です」という短命の身分証（OIDC トークン）を発行する。
Google Cloud はそれを確認し、デプロイ専用のサービスアカウント（`github-deployer`）として 1 時間だけ動くことを許す。

- サービスアカウントの鍵ファイルを作らないので、漏れる鍵がない。
- このリポジトリ以外からの身分証は断る（`scripts/setup_cicd.sh` の `attribute-condition`）。
- `github-deployer` が持つのはデプロイに必要な権限だけ。Gemini を呼ぶ権限や Secret の中身を読む権限は持たない。

アプリが使う秘密（API トークン）は Secret Manager にあり、Cloud Run が起動時に読み込む。GitHub には置かない。

## 最初に 1 回だけやること（プロジェクトのオーナー）

1. `GCP_PROJECT=goo-gaa-513906 scripts/setup_cicd.sh` を実行する。
2. 最後に表示される 3 つの値を、GitHub の Settings > Secrets and variables > Actions > **Variables** に登録する。
   `GCP_PROJECT`、`WIF_PROVIDER`、`DEPLOY_SA`
3. YouTube を Lumo に見せるための OAuth クライアントを作る（Google Cloud コンソール。下の「YouTube 連携の準備」）。
   できた **クライアント ID** を GitHub の Variables に `GOOGLE_CLIENT_ID` として登録する。
   無くてもデプロイはできる。その場合 Lumo は「YouTube とつながってなかった」と報告する。

## YouTube 連携の準備（コンソールで 1 回）

Lumo が見に行くのは、ユーザー本人が許可した YouTube だけ（公式の YouTube Data API、読み取り専用）。
許可で受け取る鍵はユーザーのブラウザの中だけにあり、Lumo のサーバーには送らない。

1. **API とサービス** → **ライブラリ** で「YouTube Data API v3」を有効にする（`setup_cicd.sh` でも有効になる）。
2. **Google Auth Platform** → **ブランディング**：アプリ名「Lumo」、サポートメールを入れる。
3. **対象**：ユーザーの種類は「外部」。公開ステータスが「テスト中」の間は、**テストユーザー** に追加した Google アカウントだけが許可できる
   （チームと、デモで使うアカウントを追加する）。
4. **データアクセス**：スコープに `.../auth/youtube.readonly` を追加する。
5. **クライアント** → **クライアントを作成** → 種類「ウェブ アプリケーション」。**承認済みの JavaScript 生成元** に
   `http://localhost:8080` と Cloud Run の URL（`https://…run.app`）を入れる。
6. 表示された **クライアント ID**（`….apps.googleusercontent.com`。秘密ではない）を使う。
   - 手元: `flutter build web --release --dart-define=GOOGLE_CLIENT_ID=<クライアント ID>`
   - 自動デプロイ: GitHub の Variables の `GOOGLE_CLIENT_ID`

審査員など、テストユーザー以外にも使ってもらうには、公開ステータスを「本番」にする。
`youtube.readonly` は機密スコープなので、Google の審査が済むまでは「Google はこのアプリを確認していません」と出る
（「詳細」→「Lumo に移動」で進める。審査前は 100 ユーザーまで）。

## 困ったとき

| したいこと | 方法 |
|---|---|
| 今の main をもう一度デプロイする | GitHub の Actions > test-and-deploy > **Run workflow** |
| 前の版に戻す | `gcloud run services update-traffic avatar-api --to-revisions <前のリビジョン名>=100 --region asia-northeast1`（リビジョン名は `gcloud run revisions list --service avatar-api --region asia-northeast1`） |
| デプロイが失敗した理由を見る | GitHub の Actions の実行ログ。ビルドの詳細は Google Cloud の Cloud Build の履歴 |
