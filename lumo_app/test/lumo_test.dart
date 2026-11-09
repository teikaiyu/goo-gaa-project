import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:lumo_app/lumo.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response _json(Object body) =>
    http.Response.bytes(utf8.encode(jsonEncode(body)), 200, headers: {'content-type': 'application/json'});

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('real look first', () async {
    final lumo = await Lumo.load(MockClient((req) async => _json({
          'report': '見てきたよ',
          'items': [{'title': 'a', 'gist': 'b'}],
          'source': 'gemini',
        })));
    final r = await lumo.fetchReport();
    expect(r.text, '見てきたよ');
    expect(r.items.single.gist, 'b');
  });

  test('patrol fails -> falls back to /watch', () async {
    final paths = <String>[];
    final lumo = await Lumo.load(MockClient((req) async {
      paths.add(req.url.path);
      return req.url.path == '/patrol'
          ? _json({'report': '', 'items': [], 'source': 'fallback'})
          : _json({'report': '話題はこれ', 'items': [], 'source': 'gemini'});
    }));
    expect((await lumo.fetchReport()).text, '話題はこれ');
    expect(paths, ['/patrol', '/watch']);
  });

  test('wrong key -> asks for the key, sends bearer token', () async {
    String? auth;
    final lumo = await Lumo.load(MockClient((req) async {
      auth = req.headers['authorization'];
      return http.Response('', 401);
    }));
    lumo.token = ' k ';
    expect((await lumo.fetchReport()).text, contains('鍵'));
    expect(auth, 'Bearer k');
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
}
