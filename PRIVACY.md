# Lumo プライバシーポリシー

最終更新日: 2026 年 11 月 10 日

Lumo（Chrome 拡張機能と Web アプリ）が、どの情報を、何のために、どう扱うかを説明します。
Lumo は DevFest GDGoC Japan Hackathon 2026 のために作られた非営利のプロダクトです。

## 1. Google アカウント（YouTube）から読む情報
集中を始めるときに、あなたが Google の画面で許可した場合だけ、YouTube Data API（読み取り専用の権限
`youtube.readonly`）で次の情報を読みます。

- あなたが登録しているチャンネルの名前（最大 50 件）
- それらのチャンネルの新しい動画（各チャンネル最大 3 本）の題名、説明文の 1 行目、公開日時

許可しなければ、Lumo は YouTube を読みません（タイマーと SNS を遮る機能はそのまま使えます）。
Lumo は YouTube に書き込むことはなく、コメント・評価・登録の変更などは一切しません。

## 2. 情報の使い道
読んだ情報は、集中が終わったときに「あなたの登録チャンネルの新着から、好みに合いそうな動画を Lumo が紹介する」
報告を作るためだけに使います。広告、プロファイリング、ほかの目的には使いません。

## 3. サーバーに送る情報と、Gemini
報告の文章を作るために、次の情報を Lumo のサーバー（Google Cloud の Cloud Run）に送り、そこから
Google Cloud の Vertex AI（Gemini）に渡します。

- 登録チャンネルの名前（最大 50 件）
- 新しい動画（最大 20 本）のチャンネル名、題名、説明文の 1 行目（最大 200 文字）、集中中に公開されたかどうか
- 集中した時間（分）

サーバーはこれらを保存しません。サーバーの記録に残すのは、件数・処理時間・エラーの種類だけで、
チャンネル名や動画の文章は記録しません。なお、Google Cloud は通常の通信の記録（日時、IP アドレス、
アクセスした URL など）を残します。

## 4. あなたの端末の中だけに保存する情報
次の情報は、あなたのブラウザ（または拡張機能）の中だけに保存し、サーバーには送りません。

- YouTube の許可の鍵（アクセストークン。約 1 時間で無効になります）
- 「いまやること」、遮るアプリのスイッチ、集中する時間、集中の開始・終了時刻
- 集中中に開かれた SNS のタブの情報（遮る・「開く」で通すために拡張機能が使い、ブラウザを閉じると消えます）

## 5. Instagram と X
Lumo は Instagram と X にログインしたり、その内容を読んだりしません。拡張機能は、集中中にそれらのサイトの
URL が開かれたかどうかだけを見て、タブを Lumo の画面に切り替えます。

## 6. 第三者への提供
あなたの情報を第三者に売ったり、渡したりしません。上の 3 のとおり、報告を作るためにだけ
Google Cloud（Cloud Run、Vertex AI）を使います。

## 7. Google API サービスのユーザーデータに関するポリシー
Lumo が Google API から受け取った情報の利用と他のアプリへの転送は、
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy)
（Limited Use の要件を含む）に従います。

## 8. 許可の取り消しと削除
- **YouTube の許可を取り消す**: Google アカウントの管理 → セキュリティ → 「サードパーティ製のアプリとサービス」→ Lumo →
  アクセス権を削除。
- **端末の中の情報を消す**: Chrome の `chrome://extensions` で Lumo を削除すると、拡張機能に保存した情報はすべて消えます。
  Web アプリの情報は、Chrome の設定からそのサイトのデータを削除すると消えます。

## 9. 問い合わせ
<問い合わせ先のメールアドレス>

## 10. 変更
このポリシーを変えるときは、このページを更新し、最終更新日を改めます。

---

# Lumo Privacy Policy (English)

Last updated: November 10, 2026

Lumo (a Chrome extension and a web app) is a non-commercial product made for DevFest GDGoC Japan Hackathon 2026.

**What Lumo reads.** Only if you allow it in Google's consent screen, Lumo uses the YouTube Data API with the read-only
scope `youtube.readonly` to read the names of the channels you subscribe to (up to 50) and, for those channels, the
newest videos (up to 3 each): title, first line of the description, and publish time. Lumo never writes to YouTube.

**Why.** Only to write the report shown when your focus session ends, in which Lumo introduces new videos from your
subscriptions. Not for ads, profiling, or any other purpose.

**What is sent to the server.** To write that report, Lumo sends the channel names (up to 50), up to 20 new videos
(channel, title, first line of the description up to 200 characters, whether it came out during your session), and
the session length in minutes to Lumo's server on Google Cloud Run, which passes them to Gemini on Google Cloud Vertex
AI. The server does not store them; its logs hold only counts, timings, and error types, never channel names or video
text. Google Cloud keeps standard request logs (time, IP address, URL).

**What stays on your device.** The YouTube access token (expires in about an hour), your task, app switches, session
length and times, and the tabs the extension blocked stay in your browser or the extension and are never sent to the
server.

**Instagram and X.** Lumo never signs in to or reads Instagram or X. The extension only checks whether their URLs are
opened during a session, to show Lumo's screen instead.

**Sharing.** Lumo does not sell or share your data. It uses Google Cloud (Cloud Run, Vertex AI) only to write the report.

**Google API Services User Data Policy.** Lumo's use and transfer of information received from Google APIs adheres to
the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements.

**Revoking and deleting.** Revoke YouTube access in your Google Account: Security → Third-party apps & services →
Lumo → Delete access. Removing the extension at `chrome://extensions` deletes everything it stored.

**Contact.** <contact email address>
