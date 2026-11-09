// Settings, the running focus session, the user's YouTube, and the calls to Cloud Run. No UI here.
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// The apps the user registers as distractions. All of them are shielded during the focus session
/// (lumo_extension/). Lumo actually looks only at YouTube: the official API, with the user's permission.
const serviceNames = {'instagram': 'Instagram', 'x': 'X', 'youtube': 'YouTube'};

/// "Open it myself" goes to the web version.
const serviceWebUrls = {
  'instagram': 'https://www.instagram.com/',
  'x': 'https://x.com/',
  'youtube': 'https://www.youtube.com/',
};

/// 90 -> "1時間30分", 25 -> "25分", 60 -> "1時間".
String minutesLabel(int m) => [if (m >= 60) '${m ~/ 60}時間', if (m % 60 > 0 || m == 0) '${m % 60}分'].join();

class Seen {
  const Seen(this.title, this.gist);
  final String title, gist;
}

class Report {
  const Report(this.text, this.items);
  final String text;
  final List<Seen> items;

  factory Report.fromJson(Map<String, dynamic> j) => Report(j['report'] as String, [
    for (final i in j['items'] as List) Seen(i['title'] as String, i['gist'] as String),
  ]);
}

class _YouTubeSignedOut implements Exception {}

/// Everything is kept in the browser's storage, so a reload (or iOS suspending the tab) resumes the session.
class Lumo {
  Lumo._(this._p, this._http);
  final SharedPreferences _p;
  final http.Client _http;

  static Future<Lumo> load([http.Client? client]) async =>
      Lumo._(await SharedPreferences.getInstance(), client ?? http.Client());

  Set<String> get watched =>
      (_p.getStringList('watched') ?? ['instagram', 'youtube']).where(serviceNames.containsKey).toSet();
  set watched(Set<String> v) => _p.setStringList('watched', v.toList());

  String get task => _p.getString('task') ?? '';
  set task(String v) => _p.setString('task', v);

  int get minutes => _p.getInt('minutes') ?? 25;
  set minutes(int v) => _p.setInt('minutes', v);

  /// Shared secret for the API (API_TOKEN on Cloud Run). Typed once in Settings.
  String get token => _p.getString('token') ?? '';
  set token(String v) => _p.setString('token', v.trim());

  /// YouTube read-only access the user granted (Google Identity Services, about 1 hour). Kept only in
  /// this browser, sent only to Google: the Lumo server never sees it.
  bool get youtubeReady =>
      (_p.getInt('ytExpiry') ?? 0) > DateTime.now().add(const Duration(minutes: 1)).millisecondsSinceEpoch;
  void setYouTubeAccess(String accessToken, int expiresInSeconds) {
    _p.setString('ytToken', accessToken);
    _p.setInt('ytExpiry', DateTime.now().add(Duration(seconds: expiresInSeconds)).millisecondsSinceEpoch);
  }

  /// When the running focus session ends; null = no session.
  DateTime? get endsAt {
    final ms = _p.getInt('endsAt');
    return ms == null ? null : DateTime.fromMillisecondsSinceEpoch(ms);
  }

  /// When the latest focus session started (kept after it ends, for the report).
  DateTime get startedAt => DateTime.fromMillisecondsSinceEpoch(_p.getInt('startedAt') ?? 0);

  void start() {
    final now = DateTime.now();
    _p.setInt('startedAt', now.millisecondsSinceEpoch);
    _p.setInt('endsAt', now.add(Duration(minutes: minutes)).millisecondsSinceEpoch);
  }

  void stop() => _p.remove('endsAt');

  /// Lumo comes back from patrol: the new videos on the user's YouTube subscriptions, picked to their
  /// taste and told in Lumo's voice (/patrol). The other apps were only guarded, and Lumo says so.
  Future<Report> fetchReport() async {
    final others = [
      for (final s in watched)
        if (s != 'youtube') serviceNames[s]!,
    ].join('・');
    final guarded = others.isEmpty ? '' : '\n$others はボクがしっかり見張ってたよ';
    if (!watched.contains('youtube')) return Report('$others はボクがしっかり見張ってたよ！', const []);
    if (!youtubeReady) return Report('YouTube とつながってなかったから、見に行けなかったよ…$guarded', const []);

    final since = startedAt;
    final (List<String>, List<Map<String, Object>>)? yt;
    try {
      yt = await _youtube(_p.getString('ytToken')!, since);
    } on _YouTubeSignedOut {
      _p.remove('ytExpiry');
      return Report('YouTube とのつながりが切れちゃって、見に行けなかったよ…$guarded', const []);
    }
    if (yt == null) return Report('YouTube を見に行けなかったよ…$guarded', const []);
    final (channels, videos) = yt;

    final minutes = DateTime.now().difference(since).inSeconds / 60;
    final p = await _post('/patrol', {'videos': videos, 'channels': channels, 'minutes': minutes});
    if (p?['status'] == 'ok') return Report('${p!['report']}$guarded', Report.fromJson(p).items);
    if (_unauthorized) return const Report('設定で「鍵」を入れてね。そしたらお話しできるよ', []);
    // Gemini trouble: Lumo still shows what it found, without its comments.
    return videos.isEmpty
        ? Report('YouTube は静かだったよ$guarded', const [])
        : Report('新しい動画が出てたよ！$guarded', [
            for (final v in videos.take(5)) Seen(v['channel'] as String, v['title'] as String),
          ]);
  }

  /// The user's YouTube: their subscriptions (= their taste) and the newest uploads of those channels,
  /// newest first, from the last 7 days. Official Data API, read-only. null = YouTube did not answer.
  Future<(List<String>, List<Map<String, Object>>)?> _youtube(String accessToken, DateTime since) async {
    Future<Map<String, dynamic>?> get(String path, Map<String, String> query) async {
      final res = await _http
          .get(
            Uri.https('www.googleapis.com', '/youtube/v3/$path', query),
            headers: {'authorization': 'Bearer $accessToken'},
          )
          .timeout(const Duration(seconds: 20));
      if (res.statusCode == 401) throw _YouTubeSignedOut();
      return res.statusCode == 200 ? jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic> : null;
    }

    try {
      final subs = await get('subscriptions', {'mine': 'true', 'part': 'snippet', 'maxResults': '50'});
      if (subs == null) return null;
      final channels = [
        for (final s in subs['items'] as List)
          (name: s['snippet']['title'] as String, id: s['snippet']['resourceId']['channelId'] as String),
      ];
      // A channel's uploads playlist is its id with "UC" -> "UU": 1 quota unit per channel.
      final uploads = await Future.wait([
        for (final c in channels)
          get('playlistItems', {
            'playlistId': 'UU${c.id.substring(2)}',
            'part': 'snippet,contentDetails',
            'maxResults': '3',
          }).then((r) => (c.name, r?['items'] as List? ?? const []), onError: (Object _) => (c.name, const [])),
      ]);
      final recent = DateTime.now().subtract(const Duration(days: 7));
      final videos = <({DateTime at, Map<String, Object> v})>[
        for (final (channel, items) in uploads)
          for (final i in items)
            if (DateTime.tryParse('${i['contentDetails']?['videoPublishedAt'] ?? i['snippet']['publishedAt']}')
                case final at? when at.isAfter(recent))
              (
                at: at,
                v: {
                  'channel': channel,
                  'title': '${i['snippet']['title']}',
                  'description': '${i['snippet']['description'] ?? ''}'.split('\n').first,
                  'during': at.isAfter(since),
                },
              ),
      ]..sort((a, b) => b.at.compareTo(a.at));
      return ([for (final c in channels) c.name], [for (final x in videos.take(20)) x.v]);
    } on _YouTubeSignedOut {
      rethrow;
    } catch (_) {
      return null; // offline, timeout, or an unexpected answer
    }
  }

  bool _unauthorized = false;

  Future<Map<String, dynamic>?> _post(String path, Map<String, Object> body) async {
    try {
      final res = await _http
          .post(
            Uri.base.resolve(path), // same origin: Cloud Run serves this app and the API
            headers: {'content-type': 'application/json', if (token.isNotEmpty) 'authorization': 'Bearer $token'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 60));
      _unauthorized = res.statusCode == 401;
      return res.statusCode == 200 ? jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic> : null;
    } catch (_) {
      return null; // offline or timed out: the caller falls back
    }
  }
}
