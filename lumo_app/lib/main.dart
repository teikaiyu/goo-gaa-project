// Lumo: Home -> Patrol (focus time; opening a watched SNS shows the Shield) -> Report.
// Cupertino widgets, so it looks and behaves like iOS (Apple HIG).
// The Shield is shown by the Lumo Chrome extension (lumo_extension/), which sends watched SNS tabs here.
import 'dart:async';
import 'dart:js_interop';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show TargetPlatform, defaultTargetPlatform;
import 'package:flutter/material.dart' show CircularProgressIndicator; // no Cupertino ring with progress
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:web/web.dart' as web;

import 'google_auth.dart';
import 'lumo.dart';

// Google blue in light mode (5.4:1 on white); a lighter blue in dark mode so it still reads.
const _blue = CupertinoDynamicColor.withBrightness(color: Color(0xFF1967D2), darkColor: Color(0xFF8AB4F8));
const _onBlue = CupertinoDynamicColor.withBrightness(color: CupertinoColors.white, darkColor: Color(0xFF0B1F3A));

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final lumo = await Lumo.load();
  final shield = Uri.base.queryParameters['shield']; // set by the extension when a watched SNS is opened
  final Widget first = serviceNames.containsKey(shield)
      ? ShieldPage(lumo, shield!)
      : lumo.endsAt != null
      ? PatrolPage(lumo)
      : HomePage(lumo);
  runApp(
    CupertinoApp(
      title: 'Lumo',
      debugShowCheckedModeBanner: false,
      theme: const CupertinoThemeData(primaryColor: _blue, primaryContrastingColor: _onBlue),
      // Japanese system labels: the timer wheel's 時間 / 分, the copy & paste menu.
      locale: const Locale('ja'),
      supportedLocales: const [Locale('ja')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: first,
    ),
  );
}

// ---------- shared pieces ----------

/// Lumo plus what it says. The speech bubble is kept apart from buttons (HIG: words vs. actions).
class LumoSays extends StatelessWidget {
  const LumoSays(this.image, this.line, {super.key, this.size = 200, this.label = 'Lumo'});
  final String image, line, label;
  final double size;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Container(
        margin: const EdgeInsets.symmetric(horizontal: 16), // never touches the screen edge
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: CupertinoColors.secondarySystemGroupedBackground.resolveFrom(context),
          borderRadius: BorderRadius.circular(18),
        ),
        child: Text(
          line,
          textAlign: TextAlign.center,
          style: CupertinoTheme.of(context).textTheme.textStyle.copyWith(fontSize: 19, fontWeight: FontWeight.w600),
        ),
      ),
      const SizedBox(height: 8),
      Image.network('/lumo/$image', height: size, semanticLabel: label),
    ],
  );
}

Widget _primary(String label, VoidCallback? onPressed) => SizedBox(
  width: double.infinity,
  child: CupertinoButton.filled(onPressed: onPressed, child: Text(label)),
);

Widget _secondary(String label, VoidCallback onPressed) => SizedBox(
  width: double.infinity,
  child: CupertinoButton(onPressed: onPressed, child: Text(label)),
);

void _go(BuildContext context, Widget page) =>
    Navigator.of(context).pushAndRemoveUntil(CupertinoPageRoute(builder: (_) => page), (_) => false);

/// Leave the choice with the user, without guilt (HIG Agency).
void _openMyself(String service) => launchUrl(Uri.parse(serviceWebUrls[service]!), webOnlyWindowName: '_self');

// ---------- 1. Home ----------

class HomePage extends StatefulWidget {
  const HomePage(this.lumo, {super.key});
  final Lumo lumo;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  late final _task = TextEditingController(text: widget.lumo.task);

  @override
  Widget build(BuildContext context) {
    final lumo = widget.lumo;
    return CupertinoPageScaffold(
      backgroundColor: CupertinoColors.systemGroupedBackground,
      navigationBar: CupertinoNavigationBar(
        middle: const Text('Lumo'),
      ),
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.symmetric(vertical: 16),
          children: [
            const LumoSays('Lumo_smile.png', 'SNSのチェックは任せて！', label: '手を振る Lumo'),
            CupertinoListSection.insetGrouped(
              header: const Text('いまやること'),
              children: [
                CupertinoTextField.borderless(
                  controller: _task,
                  placeholder: '例：見出しを3つ書く',
                  padding: const EdgeInsets.all(14),
                  onChanged: (v) => lumo.task = v,
                ),
              ],
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('集中をじゃまするアプリ'),
              footer: const Text(
                '集中しているあいだは、ここで選んだアプリを Lumo が見張ります。'
                'YouTube は Lumo がきみの登録チャンネルを見てきて、終わったらお話ししてくれます',
              ),
              children: [
                for (final s in serviceNames.entries)
                  CupertinoListTile(
                    title: Text(s.value),
                    trailing: CupertinoSwitch(
                      value: lumo.watched.contains(s.key),
                      onChanged: (on) => setState(() {
                        final w = lumo.watched;
                        on ? w.add(s.key) : w.remove(s.key);
                        lumo.watched = w;
                      }),
                    ),
                  ),
                _shieldStatus(context),
              ],
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('集中する時間'),
              children: [
                // The same wheel as the iPhone Clock app's timer (hours + minutes).
                CupertinoTheme(
                  // Bigger numbers, close to the Clock app's timer.
                  data: CupertinoTheme.of(context).copyWith(
                    textTheme: CupertinoTheme.of(context).textTheme.copyWith(
                      pickerTextStyle: CupertinoTheme.of(context).textTheme.pickerTextStyle.copyWith(fontSize: 24),
                    ),
                  ),
                  child: SizedBox(
                    height: 216, // the native picker height
                    child: CupertinoTimerPicker(
                      mode: CupertinoTimerPickerMode.hm,
                      initialTimerDuration: Duration(minutes: lumo.minutes),
                      onTimerDurationChanged: (d) => setState(() => lumo.minutes = d.inMinutes),
                    ),
                  ),
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
              child: Column(
                children: [
                  _primary(
                    '始める',
                    lumo.watched.isEmpty || lumo.minutes == 0
                        ? null
                        : () async {
                            // Open Google's YouTube window right in this tap (browsers allow it only here), but never
                            // wait for it to start: the shield must be on even if the user is still in that window,
                            // closes it, or Google refuses. YouTube access only matters for the report at the end.
                            final asking = lumo.watched.contains('youtube') && !lumo.youtubeReady && youtubeConfigured
                                ? askYouTube()
                                : null;
                            lumo.start();
                            _toExtension('sync'); // shield from this moment, not from the extension's next check
                            _go(context, PatrolPage(lumo));
                            final access = await asking;
                            if (access != null) lumo.setYouTubeAccess(access.$1, access.$2);
                          },
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------- Can this browser shield? (the Lumo extension) ----------

/// The extension marks the app's page when it runs here (lumo_extension/bridge.js). Read on each build: cheap,
/// and the extension reloads this tab when it is installed, so the answer is never stale.
ShieldSupport get _shieldSupport => shieldSupport(
  extension: web.document.documentElement?.hasAttribute('data-lumo-extension') ?? false,
  computer: const {TargetPlatform.macOS, TargetPlatform.windows, TargetPlatform.linux}.contains(defaultTargetPlatform),
  userAgent: web.window.navigator.userAgent,
);

/// A row under the apps to watch: does picking them really shield them here? Honest when it cannot.
Widget _shieldStatus(BuildContext context) {
  Icon icon(IconData i, CupertinoDynamicColor c) => Icon(i, color: c.resolveFrom(context));
  return switch (_shieldSupport) {
    ShieldSupport.ready => CupertinoListTile(
      leading: icon(CupertinoIcons.checkmark_shield_fill, CupertinoColors.systemGreen),
      title: const Text('拡張機能が動いています'),
      subtitle: const Text('集中中に開くと、Lumo が止めてくれます', maxLines: 2),
    ),
    ShieldSupport.needsExtension => CupertinoListTile(
      leading: icon(CupertinoIcons.exclamationmark_shield_fill, CupertinoColors.systemOrange),
      title: const Text('SNS を遮るには拡張機能を入れてね', maxLines: 2),
      subtitle: const Text('入れないと、開いた SNS はそのまま見られます', maxLines: 2),
      trailing: const CupertinoListTileChevron(),
      onTap: () => Navigator.of(context).push(CupertinoPageRoute(builder: (_) => const ExtensionGuidePage())),
    ),
    ShieldSupport.unsupported => CupertinoListTile(
      leading: icon(CupertinoIcons.shield_slash, CupertinoColors.systemGrey),
      title: const Text('この端末では SNS を遮れません', maxLines: 2),
      subtitle: const Text('遮れるのはパソコンの Chrome だけです。タイマーと報告はここでも使えます', maxLines: 3),
    ),
  };
}

/// How to install the extension. It is not on the Chrome Web Store: the app hands out the folder as a zip.
class ExtensionGuidePage extends StatelessWidget {
  const ExtensionGuidePage({super.key});

  @override
  Widget build(BuildContext context) {
    final number = TextStyle(fontWeight: FontWeight.w600, color: _blue.resolveFrom(context));
    Widget step(int n, String what, [String? detail]) => CupertinoListTile(
      leading: Text('$n', style: number),
      title: Text(what, maxLines: 3),
      subtitle: detail == null ? null : Text(detail, maxLines: 3),
    );
    Widget tip(String what, String detail) =>
        CupertinoListTile(title: Text(what, maxLines: 2), subtitle: Text(detail, maxLines: 3));
    return CupertinoPageScaffold(
      backgroundColor: CupertinoColors.systemGroupedBackground,
      navigationBar: const CupertinoNavigationBar(middle: Text('拡張機能を入れる')),
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.symmetric(vertical: 16),
          children: [
            const LumoSays('Lumo_smile.png', 'パソコンの Chrome に入れると\nSNS を開いたときにボクが出てくるよ', size: 140, label: '手を振る Lumo'),
            CupertinoListSection.insetGrouped(
              header: const Text('入れかた（1 回だけ）'),
              children: [
                step(1, '下のボタンで lumo_extension.zip をダウンロード'),
                step(2, 'zip を開いて、lumo_extension フォルダを取り出す', 'Mac はダブルクリック、Windows は右クリック →「すべて展開」'),
                step(3, 'Chrome のアドレスバーに chrome://extensions と入れて開く', 'このページからは開けないので、入力してね'),
                step(4, '右上の「デベロッパー モード」をオンにする'),
                step(
                  5,
                  '「パッケージ化されていない拡張機能を読み込む」を押して、lumo_extension フォルダを選ぶ',
                  'manifest.json が入っているフォルダです。使っているあいだは消さないでね',
                ),
                step(6, 'Lumo が新しいタブで開いたら完了', 'Lumo は拡張機能の中にいます。次からは Chrome 右上のパズルのアイコン → Lumo で開けます'),
              ],
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: _primary(
                'lumo_extension.zip をダウンロード',
                // An <a download> click: saves the file and keeps this page open.
                () =>
                    (web.HTMLAnchorElement()
                          ..href = '/lumo_extension.zip'
                          ..download = 'lumo_extension.zip')
                        .click(),
              ),
            ),
            CupertinoListSection.insetGrouped(
              header: const Text('入れたのに遮られないときは'),
              children: [
                tip('シークレット ウィンドウとゲストでは動きません', 'ふつうのウィンドウで Lumo と SNS を開いてね。ゲストには拡張機能を入れられません'),
                tip('「始める」の前に、遮りたいアプリのスイッチをオンに', 'オフのアプリは、集中中でも開けます'),
                tip('前に入れた Lumo があるときは、削除してから入れ直す', 'chrome://extensions の Lumo の「削除」を押してから、手順 5 をやり直してね'),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ---------- 2. Shield (a watched SNS was opened during the patrol) ----------

/// Tells the Lumo extension what the user chose. The extension's content script on this page passes it on
/// (only messages from this same page are accepted there).
void _toExtension(String action) => web.window.postMessage({'lumo': action}.jsify(), web.window.location.origin.toJS);

class ShieldPage extends StatelessWidget {
  const ShieldPage(this.lumo, this.service, {super.key});
  final Lumo lumo;
  final String service;

  @override
  Widget build(BuildContext context) => CupertinoPageScaffold(
    child: SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            const Spacer(),
            // shortcut: placeholder picture until the new art arrives (same file name -> just replace it).
            LumoSays(
              'Lumo_happy_phone.png',
              '今ボクが見てるよ〜\n${serviceNames[service]} はまかせてね',
              size: 260,
              label: '楽しそうにスマホを見る Lumo',
            ),
            const Spacer(),
            _primary('やっぱやめとく', () {
              _toExtension('close'); // the extension closes this tab
              // Without the extension (page opened by hand): back to the patrol, nothing else to close.
              _go(context, lumo.endsAt != null ? PatrolPage(lumo) : HomePage(lumo));
            }),
            _secondary('開く', () => _toExtension('allow')), // the extension lets this tab through
          ],
        ),
      ),
    ),
  );
}

// ---------- 3. Patrol (= the user's focus time) ----------

class PatrolPage extends StatefulWidget {
  const PatrolPage(this.lumo, {super.key});
  final Lumo lumo;

  @override
  State<PatrolPage> createState() => _PatrolPageState();
}

class _PatrolPageState extends State<PatrolPage> {
  late final DateTime _endsAt = widget.lumo.endsAt ?? DateTime.now();
  late final int _total = _endsAt.difference(widget.lumo.startedAt).inSeconds;
  Timer? _tick;
  bool _done = false;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) => _update());
    _update();
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  Duration get _left {
    final d = _endsAt.difference(DateTime.now());
    return d.isNegative ? Duration.zero : d;
  }

  void _update() {
    if (_left == Duration.zero && !_done) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _finish()); // may run from initState: wait a frame
    }
    if (mounted) setState(() {});
  }

  void _finish() {
    if (_done || !mounted) return;
    _done = true;
    _tick?.cancel();
    widget.lumo.stop();
    _toExtension('sync'); // the patrol is over: SNS open normally again
    _go(context, ReportPage(widget.lumo, widget.lumo.fetchReport())); // Lumo comes back from patrol now
  }

  @override
  Widget build(BuildContext context) {
    final left = _left;
    final mmss = '${left.inMinutes}:${(left.inSeconds % 60).toString().padLeft(2, '0')}';
    final names = widget.lumo.watched.map((s) => serviceNames[s]).join('・');
    return CupertinoPageScaffold(
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              const Spacer(),
              Text(
                'Lumo が $names を見てるよ',
                textAlign: TextAlign.center,
                style: CupertinoTheme.of(context).textTheme.navTitleTextStyle,
              ),
              const SizedBox(height: 24),
              Semantics(
                label: 'Lumo が戻るまで あと$mmss',
                child: SizedBox.square(
                  dimension: 280,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      SizedBox.expand(
                        child: CircularProgressIndicator(
                          value: _total == 0 ? 0 : left.inSeconds / _total,
                          strokeWidth: 10,
                          strokeCap: StrokeCap.round,
                          color: _blue.resolveFrom(context),
                          backgroundColor: CupertinoColors.systemFill.resolveFrom(context),
                        ),
                      ),
                      Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Image.network('/lumo/Lumo_happy_phone.png', height: 150, semanticLabel: '楽しそうにスマホを見る Lumo'),
                          Text(
                            mmss,
                            style: CupertinoTheme.of(context).textTheme.textStyle.copyWith(
                              fontSize: 34,
                              fontWeight: FontWeight.w600,
                              fontFeatures: const [FontFeature.tabularFigures()],
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                widget.lumo.task.isEmpty ? 'そのあいだに、やることを進めよう' : 'そのあいだに「${widget.lumo.task}」',
                textAlign: TextAlign.center,
                style: TextStyle(color: CupertinoColors.secondaryLabel.resolveFrom(context)),
              ),
              const Spacer(),
              _primary('完了して Lumo を呼び戻す', _finish),
              _secondary('自分で見る', () async {
                widget.lumo.stop();
                _toExtension('sync'); // the patrol is over: the extension must not shield the page opened next
                await Future<void>.delayed(const Duration(milliseconds: 500));
                _openMyself(widget.lumo.watched.first);
              }),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------- 4. Report ----------

class ReportPage extends StatelessWidget {
  const ReportPage(this.lumo, this.report, {super.key});
  final Lumo lumo;
  final Future<Report> report;

  @override
  Widget build(BuildContext context) {
    // How long the user really focused (called back early -> the real time, not the planned one).
    final focused = (DateTime.now().difference(lumo.startedAt).inSeconds / 60).round();
    return CupertinoPageScaffold(
      backgroundColor: CupertinoColors.systemGroupedBackground,
      child: SafeArea(
        child: FutureBuilder<Report>(
          future: report,
          builder: (context, snap) {
            final r = snap.data;
            return ListView(
              padding: const EdgeInsets.symmetric(vertical: 24),
              children: [
                if (r == null) ...[
                  const LumoSays('Lumo_happy_phone.png', 'ただいま！\nいま報告をまとめてるね…', label: 'スマホを見る Lumo'),
                  const SizedBox(height: 16),
                  const CupertinoActivityIndicator(radius: 14),
                ] else ...[
                  LumoSays(
                    r.items.isEmpty ? 'Lumo_disappointed.png' : 'Lumo_cheering.png',
                    'えらい！${minutesLabel(focused)}がんばったね\n${r.text}',
                    label: 'ほめる Lumo',
                  ),
                  if (r.items.isNotEmpty)
                    CupertinoListSection.insetGrouped(
                      header: const Text('パトロール中に YouTube で見つけたよ'),
                      footer: const Text('きみの登録チャンネルの新着から、Gemini が選んでまとめました'),
                      children: [
                        for (final i in r.items)
                          CupertinoListTile(title: Text(i.title), subtitle: Text(i.gist, maxLines: 3)),
                      ],
                    ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                    child: _primary('次のタスクに進む', () => _go(context, HomePage(lumo))),
                  ),
                ],
              ],
            );
          },
        ),
      ),
    );
  }
}
