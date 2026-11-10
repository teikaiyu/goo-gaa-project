// Permission to read the user's YouTube (read-only): via Google Identity Services (web/index.html loads it) on the
// web, or via chrome.identity inside the Chrome extension (an extension page may not load Google's script).
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

const _scope = 'https://www.googleapis.com/auth/youtube.readonly';

@JS('chrome.identity')
external JSObject? get _identity;

extension type _Identity(JSObject _) implements JSObject {
  external String getRedirectURL();
  external JSPromise<JSString?> launchWebAuthFlow(JSObject details);
}

/// -> (access token, seconds it lasts), or null if the user said no, closed the window, or Google is unreachable.
Future<(String, int)?> askYouTube() {
  final identity = _identity;
  if (identity != null) return _askInExtension(_Identity(identity));
  final done = Completer<(String, int)?>();
  void finish((String, int)? v) => done.isCompleted ? null : done.complete(v);
  try {
    final config = JSObject()
      ..['client_id'] = _clientId.toJS
      ..['scope'] = _scope.toJS
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

/// Inside the extension: Google's sign-in window, answered to `https://<extension id>.chromiumapp.org/` (that address
/// must be an authorized redirect URI of the OAuth client; the fixed ID comes from "key" in manifest.json).
Future<(String, int)?> _askInExtension(_Identity identity) async {
  try {
    final url = Uri.https('accounts.google.com', '/o/oauth2/v2/auth', {
      'client_id': _clientId,
      'response_type': 'token',
      'redirect_uri': identity.getRedirectURL(),
      'scope': _scope,
    });
    final details = JSObject()
      ..['url'] = url.toString().toJS
      ..['interactive'] = true.toJS;
    final back = (await identity.launchWebAuthFlow(details).toDart)?.toDart;
    final answer = back == null ? null : Uri.splitQueryString(Uri.parse(back).fragment);
    final token = answer?['access_token'];
    return token == null ? null : (token, int.tryParse(answer!['expires_in'] ?? '') ?? 3600);
  } catch (_) {
    return null; // the user closed the window or said no
  }
}
