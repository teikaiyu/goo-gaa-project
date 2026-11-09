// Page logic: the "watch SNS for me" switch and what the avatar saw, small time line.
// Knows nothing about the avatar's internals - it only calls Avatar.update().

const card = document.getElementById('card');
const timeEl = document.getElementById('time');
const briefList = document.getElementById('brief-list');

const api = () => window.pywebview.api;

function formatHMS(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hh = String(Math.floor(s / 3600)).padStart(2, '0');
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

// ---------- rendering what the avatar saw ----------
// The text comes from an AI model: only ever textContent, never innerHTML.
function li(className, ...parts) {
  const el = document.createElement('li');
  el.className = className;
  for (const [cls, text] of parts) {
    const span = document.createElement('span');
    span.className = cls;
    span.textContent = text;
    el.appendChild(span);
  }
  return el;
}

// The watch view lists what the avatar SAW (watch.items).
let lastBriefKey = '';
function renderBriefing(watch) {
  const key = JSON.stringify(watch.items);
  if (key === lastBriefKey) return;  // unchanged: do not rebuild (it would reset the list's scroll position)
  lastBriefKey = key;
  briefList.replaceChildren();
  if (watch.items.length > 0) briefList.appendChild(li('brief-head', ['seen-head', 'いま見ているもの']));
  for (const it of watch.items) {
    briefList.appendChild(li('seen', ['seen-title', it.title], ['seen-gist', it.gist]));
  }
}

// ---------- views ----------
function setView(view) {
  card.dataset.view = view;
  document.body.classList.toggle('watching', view === 'watch');
}

// The avatar's own line about the watch, or null when it has nothing to say about it.
//   watching  -> what it is looking at now (the cloud's spoken line)
//   recapping -> "summing up..." (after the user pressed back)
//   recap     -> how it went (shown for a minute, on the home view)
function watchLine(watch) {
  if (watch.status === 'watching' || watch.status === 'recapping') return watch.report;
  if (watch.status === 'recap') return watch.recap;
  return null;
}

document.getElementById('watch-start').addEventListener('click', async () => {
  await api().set_watching(true);
  setView('watch');
});
document.getElementById('watch-stop').addEventListener('click', async () => {
  await api().set_watching(false);
  setView('home');
});

// ---------- polling ----------
function render(state) {
  timeEl.textContent = formatHMS(state.social_seconds);
  const watch = state.watch;
  if (state.watching) renderBriefing(watch);
  const line = watchLine(watch);
  // The avatar talks about the watch through the same speech line it always uses (Avatar contract unchanged).
  // While it browses SNS it wears the "watching" look (one of two phone pictures, random per session);
  // for the recap it is happy again.
  const mood = state.watching ? 'watching' : 'happy';
  window.Avatar.update(line
    ? { ...state, avatar: { mood, message: line, action: null, source: 'gemini' } }
    : state);
}

async function tick() {
  try {
    render(await api().get_state());
  } catch (e) {
    // Keep the last value on screen if one poll fails; the next tick retries.
  }
}

window.Avatar.mount(document.getElementById('avatar'));
document.getElementById('close').addEventListener('click', () => api().quit());

// The bridge to Python is not ready at page load; this event says when it is.
window.addEventListener('pywebviewready', () => {
  tick();
  setInterval(tick, 1000);
});
