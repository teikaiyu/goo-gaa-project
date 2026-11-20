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

/// Apps the user adds by hand (Gmail, Discord, ...) are watched by their web address. They live in the same
/// `watched` list as the built-in ones, under the key `site:<host>`; lumo_extension/rules.js reads the host
/// straight from that key, so no second channel to the extension is needed.
const customPrefix = 'site:';

/// Friendly names for common sites; any other site shows its address.
const _siteNames = {
  'mail.google.com': 'Gmail',
  'discord.com': 'Discord',
  'web.whatsapp.com': 'WhatsApp',
  'slack.com': 'Slack',
  'facebook.com': 'Facebook',
  'tiktok.com': 'TikTok',
  'reddit.com': 'Reddit',
  'line.me': 'LINE',
};

/// Names people type that are not the address the app really lives at (gmail.com only redirects).
const _siteAliases = {'gmail.com': 'mail.google.com', 'discordapp.com': 'discord.com'};

/// What the user typed ("https://www.discord.com/app", "Discord.com", "gmail.com") -> the host to watch
/// ("discord.com", "mail.google.com"), or null if it is not a web address.
String? parseSite(String input) {
  var text = input.trim().toLowerCase();
  if (text.isEmpty || text.contains(RegExp(r'\s'))) return null;
  if (!text.contains('://')) text = 'https://$text';
  var host = Uri.tryParse(text)?.host ?? '';
  if (host.startsWith('www.')) host = host.substring(4);
  host = _siteAliases[host] ?? host;
  // letters, digits, hyphens, and at least one dot with a real ending ("localhost", "a.b", "1.2.3.4" are not apps)
  return RegExp(r'^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$').hasMatch(host) ? host : null;
}

/// Is this key one the app understands: a built-in app or a valid `site:<host>`?
bool isKnownService(String? key) =>
    key != null &&
    (serviceNames.containsKey(key) ||
        (key.startsWith(customPrefix) &&
            parseSite(key.substring(customPrefix.length)) == key.substring(customPrefix.length)));

/// The name to show for a key: "Instagram", "Gmail", or the address itself.
String serviceName(String key) {
  if (serviceNames.containsKey(key)) return serviceNames[key]!;
  final host = key.startsWith(customPrefix) ? key.substring(customPrefix.length) : key;
  return _siteNames[host] ?? host;
}

/// "Open it myself" goes to the web version.
String serviceWebUrl(String key) =>
    serviceWebUrls[key] ??
    'https://${_siteHome[key.substring(customPrefix.length)] ?? key.substring(customPrefix.length)}/';

/// A few sites whose front door is not the bare host.
const _siteHome = {'discord.com': 'discord.com/app', 'slack.com': 'app.slack.com'};

/// Can watched SNS be shielded in this browser? Only the Lumo Chrome extension can do it, so: it is running
/// (`ready`), it could be installed here (`needsExtension`: Chrome or another Chromium browser on a computer),
/// or this browser cannot shield at all (`unsupported`: iPhone, Android, Safari, Firefox).
enum ShieldSupport { ready, needsExtension, unsupported }

ShieldSupport shieldSupport({required bool extension, required bool computer, required String userAgent}) => extension
    ? ShieldSupport.ready
    // Chromium browsers say "Chrome/" (Edge too); Chrome on iPhone says "CriOS/", Safari and Firefox neither.
    : computer && userAgent.contains('Chrome/')
    ? ShieldSupport.needsExtension
    : ShieldSupport.unsupported;

/// Where the API is when this app is not served by it (the copy inside the Chrome extension):
/// flutter build web --dart-define=API_BASE=https://….run.app/  (lumo_extension/build.sh). Empty: same origin.
const apiBase = String.fromEnvironment('API_BASE');

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

  Set<String> get watched => (_p.getStringList('watched') ?? ['instagram', 'youtube']).where(isKnownService).toSet();
  set watched(Set<String> v) => _p.setStringList('watched', v.toList());

  /// The apps the user added by hand (hosts), kept even while their switch is off.
  List<String> get customSites =>
      (_p.getStringList('customSites') ?? const []).where((h) => parseSite(h) == h).toList();

  /// Adds an app by its web address and switches it on. Returns its key, or null if it is not a web address.
  String? addSite(String input) {
    final host = parseSite(input);
    if (host == null) return null;
    final key = '$customPrefix$host';
    if (!customSites.contains(host)) _p.setStringList('customSites', [...customSites, host]);
    watched = {...watched, key};
    return key;
  }

  /// Forgets an app the user added: gone from the list and no longer watched.
  void removeSite(String host) {
    _p.setStringList('customSites', [...customSites]..remove(host));
    watched = {...watched}..remove('$customPrefix$host');
  }

  String get task => _p.getString('task') ?? '';
  set task(String v) => _p.setString('task', v);

  int get minutes => _p.getInt('minutes') ?? 25;
  set minutes(int v) => _p.setInt('minutes', v);

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
    // Save what home shows: untouched switches are only defaults, and the extension reads the saved list.
    _p.setStringList('watched', watched.toList());
    _p.setInt('startedAt', now.millisecondsSinceEpoch);
    _p.setInt('endsAt', now.add(Duration(minutes: minutes)).millisecondsSinceEpoch);
  }

  void stop() => _p.remove('endsAt');

  /// Lumo comes back from patrol: the new videos on the user's YouTube subscriptions, picked to their
  /// taste and told in Lumo's voice (/patrol). The other apps were only guarded, and Lumo says so.
  Future<Report> fetchReport() async {
    final others = [
      for (final s in watched)
        if (s != 'youtube') serviceName(s),
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

  Future<Map<String, dynamic>?> _post(String path, Map<String, Object> body) async {
    try {
      final res = await _http
          .post(
            // Same origin on Cloud Run (it serves this app and the API); the extension's copy names the API.
            apiBase.isEmpty ? Uri.base.resolve(path) : Uri.parse(apiBase).resolve(path),
            headers: {'content-type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 60));
      return res.statusCode == 200 ? jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic> : null;
    } catch (_) {
      return null; // offline or timed out: the caller falls back
    }
  }
}
