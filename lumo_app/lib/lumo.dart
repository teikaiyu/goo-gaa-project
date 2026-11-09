// Settings, the running focus session, and the calls to Cloud Run. No UI here.
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// The apps Lumo can look at for the user (must match PatrolRequest in avatar_api/schemas.py).
// Trial: Instagram only (X refused the automated login). The API also accepts 'x' and 'youtube'.
const serviceNames = {'instagram': 'Instagram'};

/// "Open it myself" goes to the WEB version: the native app would trigger the Shortcut and bring Lumo back.
const serviceWebUrls = {
  'instagram': 'https://www.instagram.com/',
  'x': 'https://x.com/',
  'youtube': 'https://www.youtube.com/',
};

class Seen {
  const Seen(this.title, this.gist);
  final String title, gist;
}

class Report {
  const Report(this.text, this.items);
  final String text;
  final List<Seen> items;

  factory Report.fromJson(Map<String, dynamic> j) => Report(
        j['report'] as String,
        [for (final i in j['items'] as List) Seen(i['title'] as String, i['gist'] as String)],
      );
}

/// Everything is kept in the browser's storage, so a reload (or iOS suspending the tab) resumes the session.
class Lumo {
  Lumo._(this._p, this._http);
  final SharedPreferences _p;
  final http.Client _http;

  static Future<Lumo> load([http.Client? client]) async =>
      Lumo._(await SharedPreferences.getInstance(), client ?? http.Client());

  Set<String> get watched => (_p.getStringList('watched') ?? ['instagram']).where(serviceNames.containsKey).toSet();
  set watched(Set<String> v) => _p.setStringList('watched', v.toList());

  String get task => _p.getString('task') ?? '';
  set task(String v) => _p.setString('task', v);

  int get minutes => _p.getInt('minutes') ?? 25;
  set minutes(int v) => _p.setInt('minutes', v);

  /// Shared secret for the API (API_TOKEN on Cloud Run). Typed once in Settings.
  String get token => _p.getString('token') ?? '';
  set token(String v) => _p.setString('token', v.trim());

  /// When the running focus session ends; null = no session.
  DateTime? get endsAt {
    final ms = _p.getInt('endsAt');
    return ms == null ? null : DateTime.fromMillisecondsSinceEpoch(ms);
  }

  void start() => _p.setInt('endsAt', DateTime.now().add(Duration(minutes: minutes)).millisecondsSinceEpoch);
  void stop() => _p.remove('endsAt');

  /// What Lumo saw. Really looks first (/patrol: logged-in browser + Gemini Computer Use); if that cannot
  /// work, tells what is being talked about on those apps (/watch: Gemini + Google Search).
  Future<Report> fetchReport() async {
    final services = watched.toList();
    final patrol = await _post('/patrol', {'services': services});
    if (patrol?['source'] == 'gemini') return Report.fromJson(patrol!);
    final watch = await _post('/watch', {
      'topics': [for (final s in services) '${serviceNames[s]} で話題になっていること'],
    });
    if (watch?['source'] == 'gemini') return Report.fromJson(watch!);
    return Report(
      _unauthorized ? '設定で「鍵」を入れてね。そしたら見てこられるよ' : 'ごめん、今日はうまく見られなかった…',
      const [],
    );
  }

  bool _unauthorized = false;

  Future<Map<String, dynamic>?> _post(String path, Map<String, Object> body) async {
    try {
      final res = await _http
          .post(
            Uri.base.resolve(path), // same origin: Cloud Run serves this app and the API
            headers: {
              'content-type': 'application/json',
              if (token.isNotEmpty) 'authorization': 'Bearer $token',
            },
            body: jsonEncode(body),
          )
          .timeout(const Duration(minutes: 10)); // a real look takes a minute or two
      _unauthorized = res.statusCode == 401;
      return res.statusCode == 200 ? jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic> : null;
    } catch (_) {
      return null; // offline or timed out: the caller falls back
    }
  }
}
