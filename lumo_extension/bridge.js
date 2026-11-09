// Runs on the Lumo app's pages (see manifest.json "matches"). Two jobs:
//  1. tell the extension about the patrol, read from the app's own storage (shared_preferences keys);
//  2. pass on the Shield's buttons. Only messages from this very page are accepted.
let last = '';

function report() {
  const endsAt = Number(localStorage.getItem('flutter.endsAt') || 0);
  let watched = [];
  try {
    watched = JSON.parse(localStorage.getItem('flutter.watched') || '[]');
  } catch {
    watched = [];
  }
  const now = JSON.stringify({ endsAt, watched });
  if (now !== last) {
    last = now;
    chrome.runtime.sendMessage({ type: 'state', endsAt, watched });
  }
}

report();
setInterval(report, 1000); // the app writes its storage itself; this just notices changes

window.addEventListener('message', (e) => {
  if (e.source !== window || e.origin !== location.origin) return;
  const action = e.data && e.data.lumo;
  if (action === 'sync') report(); // the app just changed the patrol: tell the extension now, not in 1s
  else if (action === 'close' || action === 'allow') chrome.runtime.sendMessage({ type: action });
});
