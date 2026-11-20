import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumo_app/lumo.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response _json(Object body, [int status = 200]) =>
    http.Response.bytes(utf8.encode(jsonEncode(body)), status, headers: {'content-type': 'application/json'});

String _ago(Duration d) => DateTime.now().subtract(d).toUtc().toIso8601String();

/// A fake YouTube (2 subscriptions) + a fake Lumo server. Records what was sent to /patrol.
MockClient fakeWorld({int youtubeStatus = 200, int patrolStatus = 200, Map<String, Object>? patrol, List<Map>? sent}) =>
    MockClient((req) async {
      if (req.url.host == 'www.googleapis.com') {
        if (youtubeStatus != 200) return _json({}, youtubeStatus);
        if (req.url.path.endsWith('/subscriptions')) {
          return _json({
            'items': [
              {
                'snippet': {
                  'title': '料理チャンネル',
                  'resourceId': {'channelId': 'UCcook'},
                },
              },
              {
                'snippet': {
                  'title': '猫チャンネル',
                  'resourceId': {'channelId': 'UCcat'},
                },
              },
            ],
          });
        }
        final cook = req.url.queryParameters['playlistId'] == 'UUcook';
        return _json({
          'items': cook
              ? [
                  {
                    'snippet': {'title': '10分パスタ', 'description': '簡単!\n詳しくは…'},
                    'contentDetails': {'videoPublishedAt': _ago(const Duration(minutes: 5))},
                  },
                  {
                    'snippet': {'title': '去年の動画', 'description': ''},
                    'contentDetails': {'videoPublishedAt': _ago(const Duration(days: 30))},
                  },
                ]
              : [
                  {
                    'snippet': {'title': '猫が箱に入る', 'description': ''},
                    'contentDetails': {'videoPublishedAt': _ago(const Duration(days: 2))},
                  },
                ],
        });
      }
      sent?.add(jsonDecode(req.body) as Map);
      if (patrolStatus != 200) return http.Response('', patrolStatus);
      return _json(
        patrol ??
            {
              'report': 'パトロール中にこんなことがあったよ!',
              'items': [
                {'title': '料理チャンネル', 'gist': 'パスタ!'},
              ],
              'status': 'ok',
            },
      );
    });

Future<Lumo> lumoWith(MockClient client, {bool youtube = true, bool signedIn = true}) async {
  final lumo = await Lumo.load(client);
  lumo.watched = {'instagram', if (youtube) 'youtube'};
  lumo.minutes = 25;
  lumo.start();
  if (signedIn) lumo.setYouTubeAccess('ya29.token', 3600);
  return lumo;
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('patrols YouTube: new videos of the subscriptions, newest first, [NEW] during the session', () async {
    final sent = <Map>[];
    final lumo = await lumoWith(fakeWorld(sent: sent));
    final r = await lumo.fetchReport();
    expect(r.text, startsWith('パトロール中にこんなことがあったよ!'));
    expect(r.text, contains('Instagram はボクがしっかり見張ってたよ'));
    expect(r.items.single.gist, 'パスタ!');
    final body = sent.single;
    expect(body['channels'], ['料理チャンネル', '猫チャンネル']);
    final videos = body['videos'] as List;
    expect([for (final v in videos) v['title']], ['10分パスタ', '猫が箱に入る']); // 30-day-old one left out
    expect(videos.first['description'], '簡単!'); // first line only
    expect(videos.first['during'], isFalse); // came out 5 min ago, the session started just now
  });

  test('a video that came out during the session is marked', () async {
    final sent = <Map>[];
    final lumo = await lumoWith(fakeWorld(sent: sent));
    // the session started 10 minutes ago
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt('startedAt', DateTime.now().subtract(const Duration(minutes: 10)).millisecondsSinceEpoch);
    await lumo.fetchReport();
    final videos = sent.single['videos'] as List;
    expect(videos.first['during'], isTrue);
    expect(videos.last['during'], isFalse);
    expect(sent.single['minutes'], closeTo(10, 0.1));
  });

  test('not connected to YouTube -> says so, calls nothing', () async {
    var calls = 0;
    final lumo = await lumoWith(MockClient((_) async => (calls++, _json({})).$2), signedIn: false);
    expect((await lumo.fetchReport()).text, contains('YouTube とつながってなかった'));
    expect(calls, 0);
  });

  test('YouTube access expired -> says so and forgets it', () async {
    final lumo = await lumoWith(fakeWorld(youtubeStatus: 401));
    expect((await lumo.fetchReport()).text, contains('つながりが切れちゃって'));
    expect(lumo.youtubeReady, isFalse);
  });

  test('Gemini trouble -> still shows the videos it found', () async {
    final lumo = await lumoWith(fakeWorld(patrol: {'report': '', 'items': [], 'status': 'failed'}));
    final r = await lumo.fetchReport();
    expect(r.text, startsWith('新しい動画が出てたよ'));
    expect([for (final i in r.items) i.gist], ['10分パスタ', '猫が箱に入る']);
  });

  test('daily report limit (429) -> still shows the videos it found', () async {
    final lumo = await lumoWith(fakeWorld(patrolStatus: 429));
    final r = await lumo.fetchReport();
    expect(r.text, startsWith('新しい動画が出てたよ'));
    expect(r.items, hasLength(2));
  });

  test('YouTube not registered -> Lumo only guarded the others', () async {
    var calls = 0;
    final lumo = await lumoWith(MockClient((_) async => (calls++, _json({})).$2), youtube: false);
    expect((await lumo.fetchReport()).text, 'Instagram はボクがしっかり見張ってたよ！');
    expect(calls, 0);
  });

  test('start saves the apps home shows, even if no switch was touched', () async {
    final lumo = await Lumo.load();
    lumo.start();
    final saved = (await SharedPreferences.getInstance()).getStringList('watched');
    expect(saved, unorderedEquals(['instagram', 'youtube']));
  });

  test('session survives a reload', () async {
    final lumo = await Lumo.load();
    lumo.minutes = 15;
    lumo.start();
    final again = await Lumo.load();
    expect(again.endsAt!.difference(DateTime.now()).inMinutes, 14);
    again.stop();
    expect((await Lumo.load()).endsAt, isNull);
  });

  test('parseSite: addresses people type become the host to watch', () {
    expect(parseSite('discord.com'), 'discord.com');
    expect(parseSite('  https://www.Discord.com/app  '), 'discord.com');
    expect(parseSite('gmail.com'), 'mail.google.com'); // gmail.com only redirects to mail.google.com
    expect(parseSite('https://mail.google.com/mail/u/0/'), 'mail.google.com');
    for (final bad in ['', '   ', 'discord', 'localhost', 'a b.com', '1.2.3.4', 'ほげ', 'http://']) {
      expect(parseSite(bad), isNull, reason: bad);
    }
  });

  test('apps the user added are saved, switched on, named, and can be removed', () async {
    final lumo = await Lumo.load();
    expect(lumo.addSite('gmail.com'), 'site:mail.google.com');
    expect(lumo.addSite('https://discord.com/'), 'site:discord.com');
    expect(lumo.addSite('nope'), isNull);
    expect(lumo.addSite('discord.com'), 'site:discord.com'); // again: no duplicate
    expect(lumo.customSites, ['mail.google.com', 'discord.com']);
    expect(lumo.watched, containsAll(['instagram', 'youtube', 'site:mail.google.com', 'site:discord.com']));
    expect(serviceName('site:mail.google.com'), 'Gmail');
    expect(serviceName('site:example.org'), 'example.org');

    final again = await Lumo.load(); // survives a reload
    expect(again.customSites, ['mail.google.com', 'discord.com']);
    again.removeSite('discord.com');
    expect(again.customSites, ['mail.google.com']);
    expect(again.watched, isNot(contains('site:discord.com')));
  });

  test('an added app that is switched off stays in the list but is not watched', () async {
    final lumo = await Lumo.load();
    lumo.addSite('discord.com');
    lumo.watched = {...lumo.watched}..remove('site:discord.com');
    expect(lumo.customSites, ['discord.com']);
    expect(lumo.watched, isNot(contains('site:discord.com')));
  });

  test('junk keys in saved settings are ignored', () async {
    SharedPreferences.setMockInitialValues({
      'watched': ['youtube', 'site:localhost', 'site:', 'whatever'],
      'customSites': ['localhost', 'discord.com'],
    });
    final lumo = await Lumo.load();
    expect(lumo.watched, {'youtube'});
    expect(lumo.customSites, ['discord.com']);
  });

  test('the report says Lumo guarded an added app by its name', () async {
    var calls = 0;
    final lumo = await lumoWith(MockClient((_) async => (calls++, _json({})).$2), youtube: false);
    lumo.addSite('discord.com');
    expect((await lumo.fetchReport()).text, allOf(contains('Instagram'), contains('Discord')));
    expect(calls, 0);
  });
}
