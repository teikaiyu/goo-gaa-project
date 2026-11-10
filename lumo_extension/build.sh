#!/usr/bin/env bash
# Put the Lumo app inside this extension, so installing the extension is all a user does (no server to run).
#   app/   the Flutter app (lumo_app), built for an extension page: no CDN, no remote scripts (Chrome forbids them)
#   lumo/  Lumo's pictures (the app asks for /lumo/<name>.png, like on Cloud Run)
# The app calls the API (Gemini, /patrol) on Cloud Run. Override with API_BASE=https://….run.app/
# YouTube needs GOOGLE_CLIENT_ID (public, not a secret; same client as the web app, see docs/cicd.md).
# Usage (from anywhere): lumo_extension/build.sh
set -euo pipefail
ext=$(cd "$(dirname "$0")" && pwd)
repo=$(dirname "$ext")
api=${API_BASE:-https://avatar-api-ek3vs4df7q-an.a.run.app/}

rm -rf "$ext/app" "$ext/lumo"
(cd "$repo/lumo_app" && flutter build web --release --csp --no-web-resources-cdn --base-href /app/ \
  --dart-define=API_BASE="$api" --dart-define=GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}" -o "$ext/app")
cp -R "$repo/images" "$ext/lumo"

# Extension pages may run only their own scripts: drop Google's sign-in script (chrome.identity is used
# instead, lib/google_auth.dart) and load bridge.js, which tells the background about the patrol.
index="$ext/app/index.html"
grep -v 'accounts.google.com/gsi/client' "$index" \
  | sed 's|<script src="flutter_bootstrap.js" async></script>|<script src="/bridge.js"></script>\n  &|' > "$index.tmp"
mv "$index.tmp" "$index"
grep -q '/bridge.js' "$index" || { echo "build.sh: could not add bridge.js to $index" >&2; exit 1; }

# Flutter's offline service worker cannot register on an extension page: the app would wait 4 s for it on every
# open. Load without it, and drop the debug symbols nobody downloads here.
perl -0pi -e 's/_flutter\.loader\.load\(\{.*?\}\);/_flutter.loader.load();/s' "$ext/app/flutter_bootstrap.js"
grep -q 'serviceWorkerVersion: "' "$ext/app/flutter_bootstrap.js" && { echo "build.sh: service worker still on" >&2; exit 1; }
rm -f "$ext/app/flutter_service_worker.js"
find "$ext/app" -name '*.symbols' -delete
echo "built: load $ext in chrome://extensions (Load unpacked)"
