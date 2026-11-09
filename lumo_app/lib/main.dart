// Lumo for iPhone: Home -> (open an SNS app) -> Intercept -> Patrol (focus time) -> Report.
// Cupertino widgets, so it looks and behaves like iOS (Apple HIG).
import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show CircularProgressIndicator; // no Cupertino ring with progress
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'lumo.dart';

// Google blue in light mode (5.4:1 on white); a lighter blue in dark mode so it still reads.
const _blue = CupertinoDynamicColor.withBrightness(color: Color(0xFF1967D2), darkColor: Color(0xFF8AB4F8));
const _onBlue = CupertinoDynamicColor.withBrightness(color: CupertinoColors.white, darkColor: Color(0xFF0B1F3A));

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final lumo = await Lumo.load();
  final from = Uri.base.queryParameters['from']; // set by the iOS Shortcut that fires when an SNS app opens
  final Widget first = lumo.endsAt != null
      ? PatrolPage(lumo)
      : serviceNames.containsKey(from)
          ? InterceptPage(lumo, from!)
          : HomePage(lumo);
  runApp(CupertinoApp(
    title: 'Lumo',
    debugShowCheckedModeBanner: false,
    theme: const CupertinoThemeData(primaryColor: _blue, primaryContrastingColor: _onBlue),
    home: first,
  ));
}

// ---------- shared pieces ----------

/// Lumo plus what it says. The speech bubble is kept apart from buttons (HIG: words vs. actions).
class LumoSays extends StatelessWidget {
  const LumoSays(this.image, this.line, {super.key, this.size = 200, this.label = 'Lumo'});
  final String image, line, label;
  final double size;

  @override
  Widget build(BuildContext context) => Column(children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: CupertinoColors.secondarySystemGroupedBackground.resolveFrom(context),
            borderRadius: BorderRadius.circular(18),
          ),
          child: Text(line,
              textAlign: TextAlign.center,
              style: CupertinoTheme.of(context).textTheme.textStyle.copyWith(fontSize: 19, fontWeight: FontWeight.w600)),
        ),
        const SizedBox(height: 8),
        Image.network('/lumo/$image', height: size, semanticLabel: label),
      ]);
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

/// Leave the choice with the user, without guilt (HIG Agency): the web version, not the native app,
/// so the Shortcut does not fire again.
void _openMyself(String service) =>
    launchUrl(Uri.parse(serviceWebUrls[service]!), webOnlyWindowName: '_self');

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
        trailing: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => showCupertinoModalPopup(context: context, builder: (_) => SettingsSheet(lumo)),
          child: const Icon(CupertinoIcons.gear, semanticLabel: '設定'),
        ),
      ),
      child: SafeArea(
        child: ListView(padding: const EdgeInsets.symmetric(vertical: 16), children: [
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
            header: const Text('Lumo がかわりに見るアプリ'),
            footer: const Text('集中が終わったら、Lumo が見てきたことを教えてくれます'),
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
            ],
          ),
          CupertinoListSection.insetGrouped(
            header: const Text('集中する時間'),
            children: [
              Padding(
                padding: const EdgeInsets.all(12),
                child: CupertinoSlidingSegmentedControl<int>(
                  groupValue: lumo.minutes,
                  children: const {15: Text('15分'), 25: Text('25分'), 50: Text('50分')},
                  onValueChanged: (m) => setState(() => lumo.minutes = m ?? 25),
                ),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
            child: Column(children: [
              _primary('始める', lumo.watched.isEmpty ? null : () {
                lumo.start();
                _go(context, PatrolPage(lumo));
              }),
              _secondary('SNS を開いたときに Lumo を呼ぶ', () {
                showCupertinoModalPopup(context: context, builder: (_) => const ShortcutSheet());
              }),
            ]),
          ),
        ]),
      ),
    );
  }
}

// ---------- 2. Intercept (opened by the iOS Shortcut when an SNS app starts) ----------

class InterceptPage extends StatelessWidget {
  const InterceptPage(this.lumo, this.from, {super.key});
  final Lumo lumo;
  final String from;

  @override
  Widget build(BuildContext context) {
    final task = lumo.task.isEmpty ? 'やることを進めて' : '「${lumo.task}」をやって';
    return CupertinoPageScaffold(
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(children: [
            const Spacer(),
            LumoSays('Lumo_happy.png', 'かわりに見てきてあげる！\nそのあいだに$taskてね', size: 240, label: '目を輝かせる Lumo'),
            const Spacer(),
            _primary('見てきてもらう（${lumo.minutes}分）', () {
              lumo.watched = {...lumo.watched, from};
              lumo.start();
              _go(context, PatrolPage(lumo));
            }),
            _secondary('自分で ${serviceNames[from]} を見る', () => _openMyself(from)),
          ]),
        ),
      ),
    );
  }
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
  late final int _total = widget.lumo.minutes * 60;
  Timer? _tick;
  bool _done = false;

  @override
  void initState() {
    super.initState();
    widget.lumo.look(); // Lumo goes to look right away; the user just works
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
    // Finished looking in time -> what it found. Still looking -> nothing this time (no waiting).
    final report = widget.lumo.report ?? Report.notFound;
    widget.lumo.stop();
    _go(context, ReportPage(widget.lumo, report, _total));
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
          child: Column(children: [
            const Spacer(),
            Text('Lumo が $names を見てるよ',
                textAlign: TextAlign.center, style: CupertinoTheme.of(context).textTheme.navTitleTextStyle),
            const SizedBox(height: 24),
            Semantics(
              label: 'Lumo が戻るまで あと$mmss',
              child: SizedBox.square(
                dimension: 280,
                child: Stack(alignment: Alignment.center, children: [
                  SizedBox.expand(
                    child: CircularProgressIndicator(
                      value: _total == 0 ? 0 : left.inSeconds / _total,
                      strokeWidth: 10,
                      strokeCap: StrokeCap.round,
                      color: _blue.resolveFrom(context),
                      backgroundColor: CupertinoColors.systemFill.resolveFrom(context),
                    ),
                  ),
                  Column(mainAxisSize: MainAxisSize.min, children: [
                    Image.network('/lumo/Lumo_happy_phone.png', height: 150, semanticLabel: '楽しそうにスマホを見る Lumo'),
                    Text(mmss,
                        style: CupertinoTheme.of(context).textTheme.textStyle.copyWith(
                            fontSize: 34, fontWeight: FontWeight.w600, fontFeatures: const [FontFeature.tabularFigures()])),
                  ]),
                ]),
              ),
            ),
            const SizedBox(height: 16),
            Text(widget.lumo.task.isEmpty ? 'そのあいだに、やることを進めよう' : 'そのあいだに「${widget.lumo.task}」',
                textAlign: TextAlign.center,
                style: TextStyle(color: CupertinoColors.secondaryLabel.resolveFrom(context))),
            const Spacer(),
            _primary('完了して Lumo を呼び戻す', _finish),
            _secondary('自分で見る', () {
              widget.lumo.stop();
              _openMyself(widget.lumo.watched.first);
            }),
          ]),
        ),
      ),
    );
  }
}

// ---------- 4. Report ----------

class ReportPage extends StatelessWidget {
  const ReportPage(this.lumo, this.report, this.totalSeconds, {super.key});
  final Lumo lumo;
  final Report report;
  final int totalSeconds;

  @override
  Widget build(BuildContext context) => CupertinoPageScaffold(
        backgroundColor: CupertinoColors.systemGroupedBackground,
        child: SafeArea(
          child: ListView(padding: const EdgeInsets.symmetric(vertical: 24), children: [
            LumoSays(
              report.items.isEmpty ? 'Lumo_disappointed.png' : 'Lumo_cheering.png',
              'えらい！${(totalSeconds / 60).round()}分がんばったね\n${report.text}',
              label: 'ほめる Lumo',
            ),
            if (report.items.isNotEmpty)
              CupertinoListSection.insetGrouped(
                header: const Text('Lumo が見てきたこと'),
                footer: const Text('Gemini が画面を読んでまとめたものです。まちがうこともあります'),
                children: [
                  for (final i in report.items)
                    CupertinoListTile(title: Text(i.title), subtitle: Text(i.gist, maxLines: 3)),
                ],
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
              child: _primary('次のタスクに進む', () => _go(context, HomePage(lumo))),
            ),
          ]),
        ),
      );
}

// ---------- sheets ----------

class ShortcutSheet extends StatelessWidget {
  const ShortcutSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return CupertinoActionSheet(
      title: const Text('SNS を開いたときに Lumo を呼ぶ'),
      message: const Text('「ショートカット」App →「オートメーション」→「＋」→「App」で、'
          'アプリを選んで「開いている」「すぐに実行」にします。'
          'アクションは「URLを開く」にして、下でコピーした URL を貼ってください。'),
      actions: [
        for (final s in serviceNames.entries)
          CupertinoActionSheetAction(
            onPressed: () {
              Clipboard.setData(ClipboardData(text: '${Uri.base.origin}/?from=${s.key}'));
              Navigator.pop(context);
            },
            child: Text('${s.value} 用の URL をコピー'),
          ),
      ],
      cancelButton: CupertinoActionSheetAction(onPressed: () => Navigator.pop(context), child: const Text('閉じる')),
    );
  }
}

class SettingsSheet extends StatelessWidget {
  const SettingsSheet(this.lumo, {super.key});
  final Lumo lumo;

  @override
  Widget build(BuildContext context) => CupertinoPopupSurface(
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const Text('鍵（API トークン）', style: TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              CupertinoTextField(
                controller: TextEditingController(text: lumo.token),
                obscureText: true,
                autocorrect: false,
                placeholder: 'チームから受け取った鍵',
                onChanged: (v) => lumo.token = v,
              ),
              const SizedBox(height: 8),
              Text('この端末の中だけに保存します。',
                  style: TextStyle(fontSize: 13, color: CupertinoColors.secondaryLabel.resolveFrom(context))),
              const SizedBox(height: 12),
              CupertinoButton(onPressed: () => Navigator.pop(context), child: const Text('完了')),
            ]),
          ),
        ),
      );
}
