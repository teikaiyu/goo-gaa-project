// Permission to read the user's YouTube (read-only), via Google Identity Services (web/index.html loads it).
// Call askYouTube() straight from a tap: browsers only let the Google window open in response to one.
import 'dart:async';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

/// The OAuth client ID (public, not a secret): flutter build web --dart-define=GOOGLE_CLIENT_ID=...
const _clientId = String.fromEnvironment('GOOGLE_CLIENT_ID');
bool get youtubeConfigured => _clientId.isNotEmpty;

@JS('google.accounts.oauth2.initTokenClient')
external _TokenClient _initTokenClient(JSObject config);

extension type _TokenClient(JSObject _) implements JSObject {
  external void requestAccessToken();
}

/// -> (access token, seconds it lasts), or null if the user said no, closed the window, or Google is unreachable.
Future<(String, int)?> askYouTube() {
  final done = Completer<(String, int)?>();
  void finish((String, int)? v) => done.isCompleted ? null : done.complete(v);
  try {
    final config = JSObject()
      ..['client_id'] = _clientId.toJS
      ..['scope'] = 'https://www.googleapis.com/auth/youtube.readonly'.toJS
      ..['callback'] = ((JSObject r) {
        final token = r['access_token'] as JSString?;
        final seconds = (r['expires_in'] as JSNumber?)?.toDartDouble.round() ?? 3600;
        finish(token == null ? null : (token.toDart, seconds));
      }).toJS
      ..['error_callback'] = ((JSAny? _) => finish(null)).toJS;
    _initTokenClient(config).requestAccessToken();
  } catch (_) {
    finish(null); // the Google script did not load (offline, blocked)
  }
  return done.future;
}
