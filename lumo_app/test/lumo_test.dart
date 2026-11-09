import 'dart:async';
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

  test('looks once at the start and keeps the result for the end', () async {
    var calls = 0;
    final lumo = await Lumo.load(MockClient((req) async {
      calls++;
      return _json({'report': '見てきたよ', 'items': [{'title': 'a', 'gist': 'b'}], 'source': 'gemini'});
    }));
    lumo.start();
    expect(lumo.report, isNull); // not looked yet
    await lumo.look();
    await lumo.look(); // already has a result: does not look again
    expect(calls, 1);
    expect((await Lumo.load()).report!.items.single.title, 'a'); // survives a reload
    lumo.stop();
    expect(lumo.report, isNull);
  });

  test('a late answer does not leak into the next session', () async {
    final gate = Completer<void>();
    final lumo = await Lumo.load(MockClient((req) async {
      await gate.future;
      return _json({'report': '古い', 'items': [], 'source': 'gemini'});
    }));
    lumo.start();
    final looking = lumo.look();
    lumo.stop(); // called back early: nothing found this time
    lumo.start(); // next session
    gate.complete();
    await looking;
    expect(lumo.report, isNull);
  });
}
